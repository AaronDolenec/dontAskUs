"""User authentication routes: register, login, refresh, /me, change-password, forgot/reset password, join/create group."""

import asyncio
import logging
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from core.config import USER_JWT_ACCESS_EXPIRE_MINUTES, MAX_LOGIN_ATTEMPTS, LOCKOUT_DURATION_MINUTES, PASSWORD_RESET_EXPIRE_MINUTES
from core.database import get_db
from core.models import Account, User, Group, QuestionSet, GroupQuestionSet, PasswordResetToken, DailyQuestion, Vote, UserGroupStreak, GroupCustomSet, UserDeviceToken, GroupAnalytics
from core.schemas import (
    AuthRegisterRequest, AuthLoginRequest, AuthTokenResponse, AuthRefreshRequest,
    AccountResponse, AccountGroupMembership, AccountMeResponse,
    UserChangePasswordRequest, JoinGroupRequest, GroupCreate,
    ForgotPasswordRequest, ResetPasswordRequest,
)
from scripts.seed_defaults import initialize_default_question_set
from services.email import send_password_reset_email, is_smtp_configured
from auth.utils import (
    hash_password, verify_password, create_user_jwt, verify_user_jwt,
    get_current_account, get_avatar_url, get_random_avatar_color,
    generate_invite_code,
    generate_qr_code,
)
from services.ws_manager import manager as ws_manager

router = APIRouter(prefix="/api/auth", tags=["User Auth"])
limiter = Limiter(key_func=get_remote_address)

# Dummy hash for timing-safe comparison when email not found
_DUMMY_HASH = hash_password("dummy-password-for-timing-safety")


def _get_account_avatar_and_streak(account: Account, db: Session, base_url: str = "") -> dict:
    """Aggregate avatar/streak info from an account's memberships.
    
    Uses the first membership that has an uploaded avatar, otherwise falls back
    to the first membership's color_avatar. Streak values are the max across
    all memberships (read from UserGroupStreak for accuracy).
    """
    memberships = db.query(User).filter(User.account_id == account.id).all()
    avatar_url = None
    color_avatar = None
    answer_streak = 0
    longest_answer_streak = 0
    for m in memberships:
        # Pick avatar from the first membership that has an uploaded file
        if not avatar_url and m.avatar_filename:
            avatar_url = get_avatar_url(m.avatar_filename, base_url)
        if not color_avatar and m.color_avatar:
            color_avatar = m.color_avatar
        # Read authoritative streak from UserGroupStreak table
        gs = db.query(UserGroupStreak).filter(
            UserGroupStreak.user_id == m.id,
            UserGroupStreak.group_id == m.group_id,
        ).first()
        if gs:
            answer_streak = max(answer_streak, gs.current_streak or 0)
            longest_answer_streak = max(longest_answer_streak, gs.longest_streak or 0)
        else:
            answer_streak = max(answer_streak, m.answer_streak or 0)
            longest_answer_streak = max(longest_answer_streak, m.longest_answer_streak or 0)
    return {
        "avatar_url": avatar_url,
        "color_avatar": color_avatar,
        "answer_streak": answer_streak,
        "longest_answer_streak": longest_answer_streak,
    }


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
        avatar_url=None, color_avatar=None, answer_streak=0, longest_answer_streak=0,
        login_count=0,
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
    account.login_count = (account.login_count or 0) + 1
    db.flush()
    db.commit()
    db.refresh(account)

    logging.info(f"Account login: {account.account_id} ({account.email}) [login #{account.login_count}]")

    access_token = create_user_jwt(account.id, "access")
    refresh_token = create_user_jwt(account.id, "refresh")

    base_url = str(request.base_url).rstrip('/')
    extra = _get_account_avatar_and_streak(account, db, base_url)

    return AuthTokenResponse(
        access_token=access_token, refresh_token=refresh_token,
        token_type="bearer", expires_in=USER_JWT_ACCESS_EXPIRE_MINUTES * 60,
        account_id=account.account_id, display_name=account.display_name, email=account.email,
        login_count=account.login_count or 0,
        **extra,
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

    base_url = str(request.base_url).rstrip('/')
    extra = _get_account_avatar_and_streak(account, db, base_url)

    return AuthTokenResponse(
        access_token=access_token, refresh_token=refresh_token,
        token_type="bearer", expires_in=USER_JWT_ACCESS_EXPIRE_MINUTES * 60,
        account_id=account.account_id, display_name=account.display_name, email=account.email,
        login_count=account.login_count or 0,
        **extra,
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
    extra = _get_account_avatar_and_streak(account, db, base_url)
    return AccountMeResponse(
        account=AccountResponse(
            account_id=account.account_id, email=account.email, display_name=account.display_name,
            is_active=account.is_active, is_verified=account.is_verified,
            created_at=account.created_at, last_login=account.last_login,
            login_count=account.login_count or 0,
            **extra,
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


@router.post("/forgot-password")
@limiter.limit("5/minute")
def forgot_password(request: Request, body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Request a password reset code. A 6-digit code is sent to the email address.
    
    Always returns 200 regardless of whether the email exists to prevent
    email enumeration. If SMTP is not configured, the code is logged at
    WARNING level for development/debugging.
    """
    account = db.query(Account).filter(func.lower(Account.email) == body.email.lower()).first()

    if not account:
        # Don't reveal whether the email exists
        return {"message": "If an account with that email exists, a reset code has been sent."}

    # Invalidate any existing unused tokens for this account
    db.query(PasswordResetToken).filter(
        PasswordResetToken.account_id == account.id,
        PasswordResetToken.used_at.is_(None),
    ).update({"used_at": datetime.now(timezone.utc)})

    # Generate a 6-digit numeric code
    code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
    token_hash = hash_password(code)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=PASSWORD_RESET_EXPIRE_MINUTES)

    reset_token = PasswordResetToken(
        account_id=account.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(reset_token)
    db.commit()

    # Send the email (or log the code if SMTP is not configured)
    if is_smtp_configured():
        send_password_reset_email(account.email, code)
    else:
        logging.warning(
            "SMTP not configured — password reset code for %s: %s (expires in %d min)",
            account.email, code, PASSWORD_RESET_EXPIRE_MINUTES,
        )

    logging.info(f"Password reset requested for {account.account_id}")
    return {"message": "If an account with that email exists, a reset code has been sent."}


@router.post("/reset-password")
@limiter.limit("10/minute")
def reset_password(request: Request, body: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Reset the account password using a code received via email."""
    account = db.query(Account).filter(func.lower(Account.email) == body.email.lower()).first()
    if not account:
        raise HTTPException(status_code=400, detail="Invalid or expired reset code")

    # Find valid (unused, non-expired) tokens for this account, newest first
    tokens = db.query(PasswordResetToken).filter(
        PasswordResetToken.account_id == account.id,
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.expires_at > datetime.now(timezone.utc),
    ).order_by(PasswordResetToken.created_at.desc()).all()

    matched = False
    for token in tokens:
        if verify_password(body.token, token.token_hash):
            token.used_at = datetime.now(timezone.utc)
            matched = True
            break

    if not matched:
        raise HTTPException(status_code=400, detail="Invalid or expired reset code")

    # Update the password
    account.password_hash = hash_password(body.new_password)
    account.updated_at = datetime.now(timezone.utc)
    # Clear any lockout
    account.login_attempt_count = 0
    account.is_locked_until = None
    db.commit()

    logging.info(f"Password reset completed for {account.account_id}")
    return {"message": "Password has been reset successfully. You can now log in with your new password."}


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

    # Broadcast member_joined to group-level WebSocket clients
    member_count = db.query(func.count(User.id)).filter(User.group_id == group.id).scalar() or 0
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(ws_manager.broadcast_member_event(group.group_id, "member_joined", {
                "user_id": db_user.user_id,
                "display_name": db_user.display_name,
                "color_avatar": db_user.color_avatar,
                "avatar_url": get_avatar_url(db_user.avatar_filename, base_url),
                "member_count": member_count,
            }))
        else:
            asyncio.run(ws_manager.broadcast_member_event(group.group_id, "member_joined", {
                "user_id": db_user.user_id,
                "display_name": db_user.display_name,
                "color_avatar": db_user.color_avatar,
                "avatar_url": get_avatar_url(db_user.avatar_filename, base_url),
                "member_count": member_count,
            }))
    except Exception as e:
        logging.warning("Could not broadcast member_joined event for group %s: %s", group.group_id, e)

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
    # Set per-group rollover hour (~24h after creation ±3h jitter)
    from services.scheduler import compute_question_hour
    db_group.question_hour = compute_question_hour(datetime.now(timezone.utc))
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


@router.delete("/groups/{group_id}")
@limiter.limit("10/minute")
def delete_group(
    request: Request, group_id: str,
    account: Account = Depends(get_current_account), db: Session = Depends(get_db),
):
    """Delete a group. Only the group creator (owner) can delete their group.
    
    This permanently deletes the group and all associated data:
    - All members (user memberships)
    - All daily questions and votes
    - All streaks, device tokens, and question set assignments
    - Group analytics
    
    Member accounts themselves are NOT deleted, only their membership in this group.
    """
    group = db.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Verify the caller is the group creator
    membership = db.query(User).filter(
        and_(User.account_id == account.id, User.group_id == group.id)
    ).first()
    if not membership:
        raise HTTPException(status_code=403, detail="You are not a member of this group")
    if group.creator_id != membership.id:
        raise HTTPException(status_code=403, detail="Only the group creator can delete this group")

    group_name = group.name
    try:
        member_ids = [m.id for m in db.query(User).filter(User.group_id == group.id).all()]

        # Clean up ALL FK references to members being deleted (including cross-group refs)
        if member_ids:
            # Nullify Group.creator_id for ANY group where these members are creators
            db.query(Group).filter(Group.creator_id.in_(member_ids)).update(
                {Group.creator_id: None}, synchronize_session=False)
            # Nullify DailyQuestion.featured_member_id for ANY question referencing these members
            db.query(DailyQuestion).filter(DailyQuestion.featured_member_id.in_(member_ids)).update(
                {DailyQuestion.featured_member_id: None}, synchronize_session=False)
            # Delete GroupCustomSet entries where these members are creators
            db.query(GroupCustomSet).filter(GroupCustomSet.creator_user_id.in_(member_ids)).delete(
                synchronize_session=False)
            # Delete device tokens
            db.query(UserDeviceToken).filter(UserDeviceToken.user_id.in_(member_ids)).delete(
                synchronize_session=False)
        # Clean up group-level records
        db.query(UserGroupStreak).filter(UserGroupStreak.group_id == group.id).delete()
        db.query(GroupQuestionSet).filter(GroupQuestionSet.group_id == group.id).delete()
        db.query(GroupCustomSet).filter(GroupCustomSet.group_id == group.id).delete()
        db.query(QuestionSet).filter(QuestionSet.created_by_group_id == group.id).update(
            {"created_by_group_id": None}, synchronize_session=False,
        )
        db.flush()

        # Delete votes, questions, analytics, members explicitly (avoid SQLAlchemy circular dep)
        question_ids = [q.id for q in db.query(DailyQuestion.id).filter(
            DailyQuestion.group_id == group.id).all()]
        if question_ids:
            db.query(Vote).filter(Vote.question_id.in_(question_ids)).delete(synchronize_session=False)
        db.query(DailyQuestion).filter(DailyQuestion.group_id == group.id).delete(synchronize_session=False)
        db.query(GroupAnalytics).filter(GroupAnalytics.group_id == group.id).delete(synchronize_session=False)
        db.query(User).filter(User.group_id == group.id).delete(synchronize_session=False)

        # Expire the group object so SQLAlchemy doesn't try to cascade-delete stale children
        db.expire(group)
        db.delete(group)
        db.commit()
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logging.exception("Error deleting group %s", group_id)
        raise HTTPException(status_code=400, detail=f"Error deleting group: {e}")

    # Broadcast to any connected WebSocket clients
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(ws_manager.broadcast_to_group(
                group_id, {"type": "group_deleted", "group_id": group_id, "group_name": group_name},
            ))
    except Exception:
        logging.debug("Could not broadcast group_deleted event")

    logging.info(f"Account {account.account_id} deleted group {group_id} ('{group_name}')")
    return {"message": f"Group '{group_name}' has been permanently deleted"}
