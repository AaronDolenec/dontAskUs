"""User authentication routes: register, login, refresh, /me, change-password, join/create group."""

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from core.config import USER_JWT_ACCESS_EXPIRE_MINUTES, MAX_LOGIN_ATTEMPTS, LOCKOUT_DURATION_MINUTES
from core.database import get_db
from core.models import Account, User, Group, QuestionSet, GroupQuestionSet
from core.schemas import (
    AuthRegisterRequest, AuthLoginRequest, AuthTokenResponse, AuthRefreshRequest,
    AccountResponse, AccountGroupMembership, AccountMeResponse,
    UserChangePasswordRequest, JoinGroupRequest, GroupCreate,
)
from scripts.seed_defaults import initialize_default_question_set
from auth.utils import (
    hash_password, verify_password, create_user_jwt, verify_user_jwt,
    get_current_account, get_avatar_url, get_random_avatar_color,
    generate_invite_code,
    generate_qr_code,
)

router = APIRouter(prefix="/api/auth", tags=["User Auth"])
limiter = Limiter(key_func=get_remote_address)

# Dummy hash for timing-safe comparison when email not found
_DUMMY_HASH = hash_password("dummy-password-for-timing-safety")


@router.post("/register", response_model=AuthTokenResponse)
@limiter.limit("10/minute")
def register_account(request: Request, body: AuthRegisterRequest, db: Session = Depends(get_db)):
    """Register a new user account with email and password."""
    existing = db.query(Account).filter(func.lower(Account.email) == body.email.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    account = Account(
        email=body.email.lower().strip(),
        password_hash=hash_password(body.password),
        display_name=body.display_name.strip(),
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    logging.info(f"New account registered: {account.account_id} ({account.email})")

    access_token = create_user_jwt(account.id, "access")
    refresh_token = create_user_jwt(account.id, "refresh")

    return AuthTokenResponse(
        access_token=access_token, refresh_token=refresh_token,
        token_type="bearer", expires_in=USER_JWT_ACCESS_EXPIRE_MINUTES * 60,
        account_id=account.account_id, display_name=account.display_name, email=account.email,
    )


@router.post("/login", response_model=AuthTokenResponse)
@limiter.limit("10/minute")
def login_account(request: Request, body: AuthLoginRequest, db: Session = Depends(get_db)):
    """Login with email and password. Returns JWT tokens."""
    account = db.query(Account).filter(func.lower(Account.email) == body.email.lower()).first()

    if not account:
        # Timing-safe: perform dummy hash check to prevent email enumeration
        verify_password(body.password, _DUMMY_HASH)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not account.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    # Check lockout
    if account.is_locked_until:
        lock_until = account.is_locked_until
        if lock_until.tzinfo is None:
            lock_until = lock_until.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < lock_until:
            remaining = int((lock_until - datetime.now(timezone.utc)).total_seconds() / 60)
            raise HTTPException(status_code=429, detail=f"Account temporarily locked. Try again in {remaining} minutes.")
        else:
            account.is_locked_until = None
            account.login_attempt_count = 0

    if not account.check_password(body.password):
        account.login_attempt_count = (account.login_attempt_count or 0) + 1
        account.last_login_attempt = datetime.now(timezone.utc)
        if account.login_attempt_count >= MAX_LOGIN_ATTEMPTS:
            account.is_locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            db.commit()
            raise HTTPException(status_code=429, detail=f"Too many failed attempts. Account locked for {LOCKOUT_DURATION_MINUTES} minutes.")
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    account.login_attempt_count = 0
    account.is_locked_until = None
    account.last_login = datetime.now(timezone.utc)
    account.last_login_ip = request.client.host if request.client else None
    db.commit()

    logging.info(f"Account login: {account.account_id} ({account.email})")

    access_token = create_user_jwt(account.id, "access")
    refresh_token = create_user_jwt(account.id, "refresh")

    return AuthTokenResponse(
        access_token=access_token, refresh_token=refresh_token,
        token_type="bearer", expires_in=USER_JWT_ACCESS_EXPIRE_MINUTES * 60,
        account_id=account.account_id, display_name=account.display_name, email=account.email,
    )


@router.post("/refresh", response_model=AuthTokenResponse)
@limiter.limit("30/minute")
def refresh_user_token(request: Request, body: AuthRefreshRequest, db: Session = Depends(get_db)):
    """Refresh an access token using a valid refresh token."""
    account_id = verify_user_jwt(body.refresh_token, "refresh")
    account = db.query(Account).filter(Account.id == account_id, Account.is_active == True).first()
    if not account:
        raise HTTPException(status_code=401, detail="Account not found or deactivated")

    access_token = create_user_jwt(account.id, "access")
    refresh_token = create_user_jwt(account.id, "refresh")

    return AuthTokenResponse(
        access_token=access_token, refresh_token=refresh_token,
        token_type="bearer", expires_in=USER_JWT_ACCESS_EXPIRE_MINUTES * 60,
        account_id=account.account_id, display_name=account.display_name, email=account.email,
    )


@router.get("/me", response_model=AccountMeResponse)
@limiter.limit("200/minute")
def get_me(request: Request, account: Account = Depends(get_current_account), db: Session = Depends(get_db)):
    """Get the current authenticated user's account info and all group memberships."""
    base_url = str(request.base_url).rstrip('/')
    memberships = db.query(User).filter(User.account_id == account.id).all()
    groups = []
    for m in memberships:
        group = db.query(Group).filter(Group.id == m.group_id).first()
        if group:
            groups.append(AccountGroupMembership(
                user_id=m.user_id, group_id=group.group_id, group_name=group.name,
                display_name=m.display_name, color_avatar=m.color_avatar or "#3498db",
                avatar_url=get_avatar_url(m.avatar_filename, base_url),
                answer_streak=m.answer_streak or 0, longest_answer_streak=m.longest_answer_streak or 0,
                joined_at=m.created_at,
            ))
    return AccountMeResponse(
        account=AccountResponse(
            account_id=account.account_id, email=account.email, display_name=account.display_name,
            is_active=account.is_active, is_verified=account.is_verified,
            created_at=account.created_at, last_login=account.last_login,
        ),
        groups=groups,
    )


@router.post("/change-password")
@limiter.limit("5/minute")
def change_password(
    request: Request, body: UserChangePasswordRequest,
    account: Account = Depends(get_current_account), db: Session = Depends(get_db),
):
    """Change the current user's password."""
    if not account.check_password(body.current_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    account.password_hash = hash_password(body.new_password)
    account.updated_at = datetime.now(timezone.utc)
    db.commit()
    logging.info(f"Password changed for account {account.account_id}")
    return {"message": "Password changed successfully"}


@router.post("/groups/join", response_model=AccountGroupMembership)
@limiter.limit("30/minute")
def join_group_authenticated(
    request: Request, body: JoinGroupRequest,
    account: Account = Depends(get_current_account), db: Session = Depends(get_db),
):
    """Join a group using invite code (authenticated)."""
    group = db.query(Group).filter(Group.invite_code == body.invite_code.strip().upper()).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found. Invalid invite code.")
    existing = db.query(User).filter(and_(User.account_id == account.id, User.group_id == group.id)).first()
    if existing:
        raise HTTPException(status_code=400, detail="You are already a member of this group")
    display_name = (body.display_name or account.display_name).strip()
    name_taken = db.query(User).filter(and_(User.group_id == group.id, User.display_name == display_name)).first()
    if name_taken:
        raise HTTPException(status_code=400, detail="Display name already taken in this group")
    avatar_color = body.color_avatar or get_random_avatar_color()
    db_user = User(account_id=account.id, group_id=group.id, display_name=display_name, color_avatar=avatar_color)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    base_url = str(request.base_url).rstrip('/')
    logging.info(f"Account {account.account_id} joined group {group.group_id} as '{display_name}'")
    return AccountGroupMembership(
        user_id=db_user.user_id, group_id=group.group_id, group_name=group.name,
        display_name=db_user.display_name, color_avatar=db_user.color_avatar,
        avatar_url=get_avatar_url(db_user.avatar_filename, base_url),
        answer_streak=db_user.answer_streak or 0, longest_answer_streak=db_user.longest_answer_streak or 0,
        joined_at=db_user.created_at,
    )


@router.post("/groups/create")
@limiter.limit("20/minute")
def create_group_authenticated(
    request: Request, group: GroupCreate,
    account: Account = Depends(get_current_account), db: Session = Depends(get_db),
):
    """Create a new group (authenticated). Auto-joins the creator and assigns today's question."""
    invite_code = generate_invite_code()
    while db.query(Group).filter(Group.invite_code == invite_code).first():
        invite_code = generate_invite_code()
    db_group = Group(name=group.name, invite_code=invite_code)
    db.add(db_group)
    db.commit()
    db.refresh(db_group)
    db_user = User(
        account_id=account.id, group_id=db_group.id,
        display_name=account.display_name, color_avatar=get_random_avatar_color(),
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    db_group.creator_id = db_user.id
    db_group.qr_data = generate_qr_code(invite_code)
    db.commit()
    # Assign Default question set
    try:
        default_set = db.query(QuestionSet).filter(QuestionSet.name == "Default").first()
        if not default_set:
            initialize_default_question_set()
            default_set = db.query(QuestionSet).filter(QuestionSet.name == "Default").first()
        if default_set and not db.query(GroupQuestionSet).filter(GroupQuestionSet.group_id == db_group.id, GroupQuestionSet.question_set_id == default_set.id).first():
            db.add(GroupQuestionSet(group_id=db_group.id, question_set_id=default_set.id, is_active=True))
            db.commit()
    except Exception:
        logging.exception("Failed to assign Default question set to new group")
    # Auto-create today's daily question for the new group
    try:
        from services.scheduler import create_today_question_for_group
        create_today_question_for_group(db, db_group)
    except Exception:
        logging.exception("Failed to auto-create today's question for new group")
    logging.info(f"Account {account.account_id} created group {db_group.group_id} ('{group.name}')")
    return {
        "id": db_group.id, "group_id": db_group.group_id, "name": db_group.name,
        "invite_code": db_group.invite_code,
        "created_at": db_group.created_at.isoformat(), "member_count": 1,
    }
