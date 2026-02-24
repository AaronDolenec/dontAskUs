"""Instance admin routes: login, 2FA, CRUD for users/groups/sets, dashboard, audit logs."""

import logging
import traceback
from datetime import datetime, timezone, timedelta
from typing import Optional, Union

import pyotp
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, and_, text
from sqlalchemy.orm import Session, joinedload

from auth.admin_auth import (
    authenticate_admin, verify_admin_totp, generate_temp_token, verify_temp_token,
    generate_access_token, generate_refresh_token,
    get_current_admin, get_admin_from_refresh_token,
    record_successful_login, log_admin_action, AdminAuthError,
    get_totp_secret, get_totp_uri, hash_password, verify_password,
)
from auth.admin_schemas import (
    AdminLoginRequest, AdminLoginResponse, AdminTOTPVerifyRequest, AdminTokenResponse,
    AdminRefreshRequest, AdminProfileResponse, AdminDashboardStats, UserSuspensionRequest,
    AccountPasswordResetRequest, AccountPasswordResetResponse, AuditLogResponse,
    ChangePasswordRequest, TOTPSetupStartResponse, TOTPSetupVerifyRequest,
)
from core.database import get_db
from core.models import (
    AdminUser, Account, Group, User, DailyQuestion, Vote,
    QuestionSet, QuestionTemplate, QuestionSetTemplate, GroupQuestionSet,
    AuditLog, QuestionTypeEnum, ApiRequestLog,
)
from auth.utils import (
    extract_client_ip, generate_invite_code,
    generate_qr_code, get_random_avatar_color,
)

router = APIRouter(prefix="/api/admin", tags=["Admin"])
limiter = Limiter(key_func=get_remote_address)


# ============= Helper =============

def _log_login(admin, ip_address, reason, db):
    log_admin_action(
        admin_id=admin.id, action="LOGIN", target_type="ADMIN_USER",
        target_id=admin.id, before_state=None,
        after_state={"last_login_ip": ip_address},
        ip_address=ip_address, reason=reason, db=db,
    )


def _log_totp_change(admin, action, enabled, ip_address, db):
    log_admin_action(
        admin_id=admin.id, action=action, target_type="ADMIN_USER",
        target_id=admin.id,
        before_state={"totp_enabled": not enabled},
        after_state={"totp_enabled": enabled},
        ip_address=ip_address,
        reason=f"Admin {'enabled' if enabled else 'disabled'} 2FA", db=db,
    )


# ============= Auth =============

@limiter.limit("5/minute")
@router.post("/login", response_model=Union[AdminLoginResponse, AdminTokenResponse])
async def admin_login(
    request: AdminLoginRequest, request_obj: Request,
    x_forwarded_for: str = Header(None), db: Session = Depends(get_db),
):
    """Admin login with username and password. Returns temp token for 2FA or full tokens."""
    ip_address = extract_client_ip(request_obj, x_forwarded_for)
    try:
        admin = authenticate_admin(request.username, request.password, ip_address, db)
    except AdminAuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    if not admin.totp_enabled:
        record_successful_login(admin, ip_address, db)
        _log_login(admin, ip_address, "Password-only login (TOTP not enabled)", db)
        return AdminTokenResponse(
            access_token=generate_access_token(admin.id),
            refresh_token=generate_refresh_token(admin.id), expires_in=3600,
        )
    return AdminLoginResponse(temp_token=generate_temp_token(admin.id))


@limiter.limit("10/minute")
@router.post("/2fa", response_model=AdminTokenResponse)
async def admin_2fa_verify(
    request: AdminTOTPVerifyRequest, request_obj: Request,
    x_forwarded_for: str = Header(None), db: Session = Depends(get_db),
):
    """Verify TOTP code and receive JWT tokens."""
    ip_address = extract_client_ip(request_obj, x_forwarded_for)
    try:
        admin_id = verify_temp_token(request.temp_token)
    except AdminAuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    admin = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found")
    try:
        if not verify_admin_totp(admin, request.totp_code):
            raise AdminAuthError("Invalid TOTP code")
    except AdminAuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    record_successful_login(admin, ip_address, db)
    _log_login(admin, ip_address, "Successful 2FA login", db)
    return AdminTokenResponse(
        access_token=generate_access_token(admin.id),
        refresh_token=generate_refresh_token(admin.id), expires_in=3600,
    )


@router.post("/refresh", response_model=AdminTokenResponse)
async def admin_refresh_token(request: AdminRefreshRequest, db: Session = Depends(get_db)):
    """Refresh admin access token."""
    admin = get_admin_from_refresh_token(request.refresh_token, db)
    return AdminTokenResponse(
        access_token=generate_access_token(admin.id),
        refresh_token=request.refresh_token, expires_in=3600,
    )


@router.get("/profile", response_model=AdminProfileResponse)
async def get_admin_profile(admin: AdminUser = Depends(get_current_admin)):
    """Get current admin's profile."""
    return AdminProfileResponse(
        id=admin.id, username=admin.username, email=getattr(admin, "email", None),
        is_active=admin.is_active, totp_configured=admin.totp_secret is not None,
        created_at=admin.created_at, last_login_ip=admin.last_login_ip,
    )


@router.post("/account/change-password")
async def change_admin_password(
    request: ChangePasswordRequest, admin: AdminUser = Depends(get_current_admin),
    request_obj: Request = None, x_forwarded_for: str = Header(None),
    db: Session = Depends(get_db),
):
    """Change admin password."""
    ip_address = extract_client_ip(request_obj, x_forwarded_for) if request_obj else "unknown"
    if not verify_password(request.current_password, admin.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    try:
        db.execute(text("UPDATE admin_users SET password_hash = :h WHERE id = :id"), {"h": hash_password(request.new_password), "id": admin.id})
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update password")
    log_admin_action(admin_id=admin.id, action="PASSWORD_CHANGE", target_type="ADMIN_USER",
                     target_id=admin.id, before_state=None, after_state={"password_changed": True},
                     ip_address=ip_address, reason="Admin changed own password", db=db)
    return {"message": "Password updated successfully"}


# ============= TOTP Management =============

@router.post("/account/totp/setup-initiate", response_model=TOTPSetupStartResponse)
async def totp_setup_initiate(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    """Initiate TOTP setup for an admin."""
    if admin.totp_secret:
        raise HTTPException(status_code=400, detail="TOTP already configured")
    secret = get_totp_secret()
    try:
        db.execute(text("UPDATE admin_users SET temp_token = :s WHERE id = :id"), {"s": secret, "id": admin.id})
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to initiate TOTP setup")
    return TOTPSetupStartResponse(secret=secret, provisioning_uri=get_totp_uri(admin.username, secret))


@router.post("/account/totp/setup-verify")
async def totp_setup_verify(
    request: TOTPSetupVerifyRequest, admin: AdminUser = Depends(get_current_admin),
    request_obj: Request = None, x_forwarded_for: str = Header(None),
    db: Session = Depends(get_db),
):
    """Verify TOTP setup with a code."""
    ip_address = extract_client_ip(request_obj, x_forwarded_for) if request_obj else "unknown"
    if admin.totp_secret:
        raise HTTPException(status_code=400, detail="TOTP already configured")
    if not admin.temp_token:
        raise HTTPException(status_code=400, detail="No TOTP setup session. Initiate first.")
    totp_secret = admin.temp_token
    if not pyotp.TOTP(totp_secret).verify(request.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")
    try:
        db_admin = db.query(AdminUser).filter(AdminUser.id == admin.id).first()
        if not db_admin:
            raise Exception("Admin user not found")
        db_admin.totp_secret = totp_secret
        db_admin.totp_enabled = True
        db_admin.temp_token = None
        db.commit()
        db.refresh(db_admin)
        if not db_admin.totp_enabled:
            raise Exception("TOTP enabled flag was not persisted")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to configure TOTP: {str(e)}")
    log_admin_action(admin_id=admin.id, action="TOTP_CONFIGURED", target_type="ADMIN_USER",
                     target_id=admin.id, before_state=None, after_state={"totp_configured": True},
                     ip_address=ip_address, reason="Admin enabled TOTP", db=db)
    return {"message": "TOTP configured successfully"}


@router.post("/totp/setup")
async def setup_totp(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    """Generate a new TOTP secret."""
    from auth.admin_auth import get_totp_secret
    totp_secret = get_totp_secret()
    totp = pyotp.TOTP(totp_secret)
    return {
        "totp_secret": totp_secret,
        "provisioning_uri": totp.provisioning_uri(name=admin.username, issuer_name="dontAskUs"),
        "message": "Scan the QR code with your authenticator app or enter the secret manually",
    }


@router.post("/totp/enable")
async def enable_totp(
    request: dict, admin: AdminUser = Depends(get_current_admin),
    ip: str = Header(None), db: Session = Depends(get_db),
):
    """Enable TOTP after verifying the code."""
    totp_secret = request.get("totp_secret")
    verification_code = request.get("verification_code")
    if not totp_secret or not verification_code:
        raise HTTPException(status_code=400, detail="Missing totp_secret or verification_code")
    if not pyotp.TOTP(totp_secret).verify(verification_code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid verification code")
    admin.totp_secret = totp_secret
    admin.totp_enabled = True
    db.commit()
    _log_totp_change(admin, "TOTP_ENABLED", True, ip or "unknown", db)
    return {"message": "TOTP enabled successfully"}


@router.post("/totp/disable")
async def disable_totp(
    request: dict, admin: AdminUser = Depends(get_current_admin),
    ip: str = Header(None), db: Session = Depends(get_db),
):
    """Disable TOTP (requires password)."""
    password = request.get("password")
    if not password:
        raise HTTPException(status_code=400, detail="Password required to disable TOTP")
    if not verify_password(password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid password")
    admin.totp_secret = None
    admin.totp_enabled = False
    db.commit()
    _log_totp_change(admin, "TOTP_DISABLED", False, ip or "unknown", db)
    return {"message": "TOTP disabled successfully"}


@router.get("/totp/status")
async def get_totp_status(admin: AdminUser = Depends(get_current_admin)):
    """Get TOTP status."""
    return {"totp_enabled": admin.totp_enabled, "totp_configured": admin.totp_secret is not None}


@router.post("/logout")
async def admin_logout(
    admin: AdminUser = Depends(get_current_admin), request_obj: Request = None,
    x_forwarded_for: str = Header(None), db: Session = Depends(get_db),
):
    """Admin logout. Client should discard tokens."""
    ip_address = extract_client_ip(request_obj, x_forwarded_for) if request_obj else "unknown"
    log_admin_action(admin_id=admin.id, action="LOGOUT", target_type="ADMIN_USER",
                     target_id=admin.id, before_state=None, after_state=None,
                     ip_address=ip_address, reason="Admin logout", db=db)
    return {"message": "Logged out successfully"}


# ============= Dashboard & Audit =============

@router.get("/dashboard/stats", response_model=AdminDashboardStats)
async def get_dashboard_stats(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    """Get admin dashboard statistics."""
    total_groups = db.query(func.count(Group.id)).scalar() or 0
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_sets = db.query(func.count(QuestionSet.id)).scalar() or 0
    public_sets = db.query(func.count(QuestionSet.id)).filter(QuestionSet.is_public == True).scalar() or 0
    audit_logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(10).all()
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    active_sessions = db.query(func.count(AuditLog.id)).filter(
        and_(AuditLog.action == "LOGIN", AuditLog.timestamp >= yesterday)
    ).scalar() or 0
    return AdminDashboardStats(
        total_groups=total_groups, total_users=total_users,
        total_question_sets=total_sets, public_sets=public_sets,
        private_sets=total_sets - public_sets, active_sessions_today=active_sessions,
        recent_audit_logs=[AuditLogResponse.model_validate(log) for log in audit_logs],
    )


@router.get("/audit-logs")
async def get_audit_logs(
    admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
):
    """Get paginated audit logs."""
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).offset(offset).all()
    total = db.query(func.count(AuditLog.id)).scalar()
    return {
        "logs": [AuditLogResponse.model_validate(log) for log in logs],
        "total": total, "limit": limit, "offset": offset,
    }


# ============= User Management =============

@router.get("/users")
async def list_all_users(
    admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    suspended_only: bool = False,
):
    """List all users."""
    query = db.query(User)
    if suspended_only:
        query = query.filter(User.is_suspended == True)
    total = query.count()
    users = query.order_by(User.created_at.desc()).limit(limit).offset(offset).all()
    return {
        "users": [
            {
                "id": u.id, "user_id": u.user_id, "display_name": u.display_name,
                "group_id": u.group_id, "group_name": u.group.name if u.group else None,
                "color_avatar": u.color_avatar, "created_at": u.created_at,
                "answer_streak": u.answer_streak, "longest_answer_streak": u.longest_answer_streak,
                "last_answer_date": u.last_answer_date,
                "account_id": u.account.account_id if u.account else None,
                "account_email": u.account.email if u.account else None,
                "is_suspended": u.is_suspended, "suspension_reason": u.suspension_reason,
                "last_known_ip": str(u.last_known_ip) if u.last_known_ip else None,
            }
            for u in users
        ],
        "total": total, "limit": limit, "offset": offset,
    }


@router.put("/users/{user_id}/suspension")
async def update_user_suspension(
    user_id: int, request: UserSuspensionRequest,
    admin: AdminUser = Depends(get_current_admin), ip: str = Header(None),
    db: Session = Depends(get_db),
):
    """Suspend or unsuspend a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    before = {"is_suspended": user.is_suspended, "suspension_reason": user.suspension_reason}
    user.is_suspended = request.is_suspended
    user.suspension_reason = request.suspension_reason if request.is_suspended else None
    db.commit()
    after = {"is_suspended": user.is_suspended, "suspension_reason": user.suspension_reason}
    log_admin_action(admin_id=admin.id, action="UPDATE_USER_SUSPENSION" if request.is_suspended else "UNSUSPEND_USER",
                     target_type="USER", target_id=user_id, before_state=before, after_state=after,
                     ip_address=ip or "unknown", reason=request.suspension_reason, db=db)
    return {"message": "User suspension status updated", "user_id": user_id}


@router.post("/users/{user_id}/reset-password")
async def admin_reset_user_password(
    user_id: int, request: AccountPasswordResetRequest,
    admin: AdminUser = Depends(get_current_admin), ip: str = Header(None),
    db: Session = Depends(get_db),
):
    """Reset a user account's password (admin recovery)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.account:
        raise HTTPException(status_code=400, detail="User has no linked account. Cannot reset password.")
    account = user.account
    account.set_password(request.new_password)
    account.is_locked_until = None
    account.login_attempt_count = 0
    account.updated_at = datetime.now(timezone.utc)
    db.commit()
    log_admin_action(admin_id=admin.id, action="RESET_USER_PASSWORD", target_type="ACCOUNT",
                     target_id=account.id, before_state=None,
                     after_state={"password_reset": True, "account_email": account.email, "lockout_cleared": True},
                     ip_address=ip or "unknown", reason=request.reason, db=db)
    return AccountPasswordResetResponse(message=f"Password reset for {account.email}", account_email=account.email)


# ============= Account Management =============

@router.get("/accounts")
async def list_all_accounts(
    admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Search by email or display name"),
):
    """List all accounts (platform-level user identities)."""
    query = db.query(Account)
    if search:
        search_term = f"%{search.lower()}%"
        query = query.filter(
            (func.lower(Account.email).like(search_term)) |
            (func.lower(Account.display_name).like(search_term))
        )
    total = query.count()
    accounts = (
        query.options(joinedload(Account.memberships).joinedload(User.group))
        .order_by(Account.created_at.desc()).limit(limit).offset(offset).all()
    )
    # Deduplicate because joinedload with limit can produce dupes
    seen = set()
    unique_accounts = []
    for a in accounts:
        if a.id not in seen:
            seen.add(a.id)
            unique_accounts.append(a)
    result = []
    for a in unique_accounts:
        group_memberships = [
            {
                "user_id": m.id, "group_id": m.group_id,
                "group_name": m.group.name if m.group else None,
                "display_name": m.display_name,
            }
            for m in a.memberships
        ]
        result.append({
            "id": a.id, "account_id": a.account_id, "email": a.email,
            "display_name": a.display_name, "is_active": a.is_active,
            "created_at": a.created_at, "last_login": a.last_login,
            "group_count": len(group_memberships), "groups": group_memberships,
        })
    return {"accounts": result, "total": total, "limit": limit, "offset": offset}


@router.post("/accounts", response_model=dict)
async def admin_create_account(
    request_data: dict = Body(...), admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db), x_forwarded_for: str = Header(None), request_obj: Request = None,
):
    """Create a new user account (without requiring a group). Optionally add to a group."""
    try:
        email = request_data.get("email", "").strip().lower()
        password = request_data.get("password", "")
        display_name = request_data.get("display_name", "").strip()
        group_id = request_data.get("group_id")  # optional

        if not email:
            raise ValueError("Email is required")
        if not password or len(password) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not display_name or len(display_name) < 1:
            raise ValueError("Display name is required")

        # Check for existing account
        existing = db.query(Account).filter(func.lower(Account.email) == email).first()
        if existing:
            raise ValueError(f"Account with email '{email}' already exists")

        # Create the account
        account = Account(
            email=email,
            password_hash=hash_password(password),
            display_name=display_name,
        )
        db.add(account)
        db.flush()

        result = {
            "id": account.id, "account_id": account.account_id, "email": account.email,
            "display_name": account.display_name, "is_active": account.is_active,
            "created_at": account.created_at, "group_membership": None,
        }

        # Optionally add to a group
        if group_id:
            group = db.query(Group).filter(Group.id == group_id).first()
            if not group:
                raise ValueError(f"Group with ID {group_id} not found")
            group_display_name = request_data.get("group_display_name", display_name).strip()
            if db.query(User).filter(and_(User.group_id == group_id, User.display_name == group_display_name)).first():
                raise ValueError(f"Display name '{group_display_name}' already taken in group '{group.name}'")
            color_avatar = request_data.get("color_avatar") or get_random_avatar_color()
            user = User(
                group_id=group_id, display_name=group_display_name,
                account_id=account.id, color_avatar=color_avatar,
            )
            db.add(user)
            db.flush()
            result["group_membership"] = {
                "user_id": user.id, "group_id": group_id, "group_name": group.name,
                "display_name": group_display_name,
            }

        db.commit()
        ip_address = extract_client_ip(request_obj, x_forwarded_for)
        log_admin_action(
            admin_id=admin.id, action="CREATE_ACCOUNT", target_type="ACCOUNT",
            target_id=account.id, before_state=None,
            after_state={"email": email, "display_name": display_name, "group_id": group_id},
            ip_address=ip_address, reason=None, db=db,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="Error creating account: " + str(e))


@router.delete("/accounts/{account_id}")
async def admin_delete_account(
    account_id: int, admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db), x_forwarded_for: str = Header(None), request_obj: Request = None,
):
    """Delete an account and all their group memberships and votes."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    before_state = {"email": account.email, "display_name": account.display_name}
    # Delete votes for all user memberships
    memberships = db.query(User).filter(User.account_id == account.id).all()
    for m in memberships:
        db.query(Vote).filter(Vote.user_id == m.id).delete()
    # Cascade will handle User deletions via relationship
    db.delete(account)
    db.commit()
    ip_address = extract_client_ip(request_obj, x_forwarded_for)
    log_admin_action(
        admin_id=admin.id, action="DELETE_ACCOUNT", target_type="ACCOUNT",
        target_id=account_id, before_state=before_state, after_state=None,
        ip_address=ip_address, reason=None, db=db,
    )
    return {"status": "deleted", "email": before_state["email"]}


@router.post("/users", response_model=dict)
async def admin_create_user(
    request_data: dict = Body(...), admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db), x_forwarded_for: str = Header(None), request_obj: Request = None,
):
    """Create a new user membership in a group (admin only)."""
    try:
        display_name = request_data.get("display_name", "").strip()
        group_id = request_data.get("group_id")
        color_avatar = request_data.get("color_avatar")
        account_email = request_data.get("account_email", "").strip().lower() if request_data.get("account_email") else None
        if not display_name or len(display_name) < 2:
            raise ValueError("Display name must be at least 2 characters")
        if not group_id:
            raise ValueError("Group ID is required")
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            raise ValueError("Group not found")
        if db.query(User).filter(and_(User.group_id == group_id, User.display_name == display_name)).first():
            raise ValueError("Display name already taken in this group")
        account_id = None
        if account_email:
            account = db.query(Account).filter(func.lower(Account.email) == account_email).first()
            if not account:
                raise ValueError(f"No account found with email: {account_email}")
            if db.query(User).filter(and_(User.account_id == account.id, User.group_id == group_id)).first():
                raise ValueError("This account is already a member of this group")
            account_id = account.id
        user = User(
            group_id=group_id, display_name=display_name,
            account_id=account_id, color_avatar=color_avatar or get_random_avatar_color(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        ip_address = extract_client_ip(request_obj, x_forwarded_for)
        log_admin_action(admin_id=admin.id, action="CREATE_USER", target_type="USER",
                         target_id=user.id, before_state=None,
                         after_state={"display_name": display_name, "group_id": group_id, "account_email": account_email},
                         ip_address=ip_address, reason=None, db=db)
        return {
            "id": user.id, "user_id": user.user_id, "display_name": user.display_name,
            "group_id": user.group_id, "color_avatar": user.color_avatar, "account_email": account_email,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="Error creating user: " + str(e))


@router.delete("/users/{user_id}")
async def admin_delete_user(
    user_id: int, admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db), x_forwarded_for: str = Header(None), request_obj: Request = None,
):
    """Delete a user (admin only)."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        # Delete user's votes
        db.query(Vote).filter(Vote.user_id == user_id).delete()
        db.delete(user)
        db.commit()
        ip_address = extract_client_ip(request_obj, x_forwarded_for)
        log_admin_action(admin_id=admin.id, action="DELETE_USER", target_type="USER",
                         target_id=user_id, before_state={"display_name": user.display_name, "group_id": user.group_id},
                         after_state=None, ip_address=ip_address, reason=None, db=db)
        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# ============= Group Management =============

@router.get("/groups")
async def list_all_groups(
    admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
):
    """List all groups."""
    groups = db.query(Group).order_by(Group.created_at.desc()).limit(limit).offset(offset).all()
    total = db.query(func.count(Group.id)).scalar()
    return {
        "groups": [
            {
                "id": g.id, "group_id": g.group_id, "name": g.name,
                "invite_code": g.invite_code, "created_by": g.creator_id,
                "created_at": g.created_at, "updated_at": g.updated_at,
                "member_count": db.query(func.count(User.id)).filter(User.group_id == g.id).scalar() or 0,
                "total_sets_created": g.total_sets_created or 0,
                "instance_admin_notes": g.instance_admin_notes,
            }
            for g in groups
        ],
        "total": total, "limit": limit, "offset": offset,
    }


@router.post("/groups", response_model=dict)
async def admin_create_group(
    request_data: dict = Body(...), admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db), x_forwarded_for: str = Header(None), request_obj: Request = None,
):
    """Create a new group (admin only)."""
    try:
        name = request_data.get("name", "").strip()
        if not name or len(name) < 2:
            raise ValueError("Group name must be at least 2 characters")
        if len(name) > 255:
            raise ValueError("Group name must be at most 255 characters")
        if db.query(Group).filter(Group.name == name).first():
            raise ValueError("Group name already exists")
        invite_code = generate_invite_code()
        while db.query(Group).filter(Group.invite_code == invite_code).first():
            invite_code = generate_invite_code()
        group = Group(
            name=name, invite_code=invite_code, creator_id=None,
        )
        # Set per-group rollover hour (~24h after creation ±3h jitter)
        from services.scheduler import compute_question_hour
        group.question_hour = compute_question_hour(datetime.now(timezone.utc))
        db.add(group)
        db.commit()
        db.refresh(group)
        group.qr_data = generate_qr_code(invite_code)
        db.commit()
        # Auto-assign default question set and create today's question
        try:
            from scripts.seed_defaults import initialize_default_question_set
            default_set = db.query(QuestionSet).filter(QuestionSet.name == "Default").first()
            if not default_set:
                initialize_default_question_set()
                default_set = db.query(QuestionSet).filter(QuestionSet.name == "Default").first()
            if default_set and not db.query(GroupQuestionSet).filter(
                GroupQuestionSet.group_id == group.id, GroupQuestionSet.question_set_id == default_set.id
            ).first():
                db.add(GroupQuestionSet(group_id=group.id, question_set_id=default_set.id, is_active=True))
                db.commit()
        except Exception:
            logging.exception("Failed to assign Default question set to admin-created group")
        try:
            from services.scheduler import create_today_question_for_group
            create_today_question_for_group(db, group)
        except Exception:
            logging.exception("Failed to auto-create today's question for admin-created group")
        ip_address = extract_client_ip(request_obj, x_forwarded_for)
        log_admin_action(admin_id=admin.id, action="CREATE_GROUP", target_type="GROUP",
                         target_id=group.id, before_state=None, after_state={"name": name},
                         ip_address=ip_address, reason=None, db=db)
        return {"id": group.id, "name": group.name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="Error creating group: " + str(e))


@router.delete("/groups/{group_id}")
async def admin_delete_group(
    group_id: int, admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db), x_forwarded_for: str = Header(None), request_obj: Request = None,
):
    """Delete a group and all related data (admin only)."""
    try:
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        db.query(User).filter(User.group_id == group_id).delete()
        db.query(DailyQuestion).filter(DailyQuestion.group_id == group_id).delete()
        db.query(GroupQuestionSet).filter(GroupQuestionSet.group_id == group_id).delete()
        db.delete(group)
        db.commit()
        ip_address = extract_client_ip(request_obj, x_forwarded_for)
        log_admin_action(admin_id=admin.id, action="DELETE_GROUP", target_type="GROUP",
                         target_id=group_id, before_state={"name": group.name},
                         after_state=None, ip_address=ip_address, reason=None, db=db)
        return {"status": "deleted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/groups/{group_id}/notes")
async def update_group_notes(
    group_id: int, request: dict, admin: AdminUser = Depends(get_current_admin),
    ip: str = Header(None), db: Session = Depends(get_db),
):
    """Update instance admin notes for a group."""
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    before = {"instance_admin_notes": group.instance_admin_notes}
    group.instance_admin_notes = request.get("notes", "")
    db.commit()
    log_admin_action(admin_id=admin.id, action="UPDATE_GROUP_NOTES", target_type="GROUP",
                     target_id=group_id, before_state=before,
                     after_state={"instance_admin_notes": group.instance_admin_notes},
                     ip_address=ip or "unknown", reason="Admin updated group notes", db=db)
    return {"message": "Group notes updated", "group_id": group_id}


@router.post("/groups/{group_id}/set-today-question")
async def admin_set_today_question(
    group_id: int, admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db), x_forwarded_for: str = Header(None), request_obj: Request = None,
):
    """Regenerate today's question for a group (instance admin only). Deactivates old question, preserving history."""
    from services.scheduler import create_today_question_for_group, get_group_question_day
    import json as _json

    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    question_day = get_group_question_day(group)
    old_template_id = None
    old_q = db.query(DailyQuestion).filter(
        and_(DailyQuestion.group_id == group.id, func.date(DailyQuestion.question_date) == question_day,
             DailyQuestion.is_active == True)
    ).first()
    if old_q:
        old_template_id = old_q.template_id
        old_q.is_active = False
        db.commit()

    dq = create_today_question_for_group(db, group, exclude_template_ids={old_template_id} if old_template_id else None)
    if not dq:
        raise HTTPException(status_code=400, detail="Unable to generate question (not enough members or templates)")

    ip_address = extract_client_ip(request_obj, x_forwarded_for)
    log_admin_action(admin_id=admin.id, action="SET_TODAY_QUESTION", target_type="GROUP",
                     target_id=group_id, before_state=None,
                     after_state={"question_id": dq.question_id, "question_text": dq.question_text},
                     ip_address=ip_address, reason="Admin set today's question", db=db)

    return {
        "message": "Today's question set successfully",
        "question_id": dq.question_id,
        "question_text": dq.question_text,
        "question_type": dq.question_type.value if hasattr(dq.question_type, "value") else str(dq.question_type),
        "options": _json.loads(dq.options) if dq.options else [],
    }


@router.post("/groups/{group_id}/reset-question-cycle")
async def admin_reset_question_cycle(
    group_id: int, admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db), x_forwarded_for: str = Header(None), request_obj: Request = None,
):
    """Reset question cycle for a group (instance admin only). Clears template tracking so all templates become available again. Preserves question history."""
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Clear template_id on all past questions so _select_template sees them as unused
    reset_count = db.query(DailyQuestion).filter(
        DailyQuestion.group_id == group.id, DailyQuestion.template_id.isnot(None)
    ).update({DailyQuestion.template_id: None}, synchronize_session=False)
    db.commit()

    ip_address = extract_client_ip(request_obj, x_forwarded_for)
    log_admin_action(admin_id=admin.id, action="RESET_QUESTION_CYCLE", target_type="GROUP",
                     target_id=group_id, before_state=None,
                     after_state={"reset_count": reset_count},
                     ip_address=ip_address, reason="Admin reset question cycle", db=db)
    logging.info(f"Question cycle reset for group {group.group_id}. Reset {reset_count} template references.")
    return {"group_id": group.group_id, "message": f"Question cycle reset. {reset_count} template references cleared.", "reset_count": reset_count}


# ============= Question Set Management =============

@router.get("/question-sets")
async def list_all_question_sets(
    admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
    public_only: bool = False, private_only: bool = False,
):
    """List all question sets."""
    query = db.query(QuestionSet)
    if public_only:
        query = query.filter(QuestionSet.is_public == True)
    elif private_only:
        query = query.filter(QuestionSet.is_public == False)
    total = query.count()
    sets = query.order_by(QuestionSet.created_at.desc()).limit(limit).offset(offset).all()
    return {
        "sets": [
            {
                "id": qs.id, "name": qs.name, "is_public": qs.is_public,
                "creator_id": qs.creator_id, "usage_count": qs.usage_count or 0,
                "created_at": qs.created_at,
                "question_count": db.query(func.count(QuestionSetTemplate.id)).filter(
                    QuestionSetTemplate.question_set_id == qs.id
                ).scalar() or 0,
            }
            for qs in sets
        ],
        "total": total, "limit": limit, "offset": offset,
    }


@router.get("/question-sets/{set_id}/questions")
async def get_admin_question_set_questions(
    set_id: int, admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db),
):
    """Get all questions in a question set."""
    question_set = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()
    if not question_set:
        raise HTTPException(status_code=404, detail="Question set not found")
    templates = (
        db.query(QuestionTemplate)
        .join(QuestionSetTemplate, QuestionSetTemplate.template_id == QuestionTemplate.id)
        .filter(QuestionSetTemplate.question_set_id == set_id)
        .order_by(QuestionTemplate.created_at.asc()).all()
    )
    return {
        "set_id": set_id,
        "questions": [
            {
                "id": t.id, "template_id": t.template_id, "question_text": t.question_text,
                "type": t.question_type.value if hasattr(t.question_type, "value") else t.question_type,
                "options": [o for o in [t.option_a_template, t.option_b_template] if o]
                if t.question_type == QuestionTypeEnum.BINARY_VOTE else [],
                "allow_multiple": getattr(t, "allow_multiple", False),
            }
            for t in templates
        ],
    }


@router.post("/question-sets", response_model=dict)
async def admin_create_question_set(
    admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db),
    x_forwarded_for: str = Header(None), request_obj: Request = None, request_data: dict = Body(...),
):
    """Create a new question set (admin only)."""
    try:
        name = request_data.get("name", "").strip() if isinstance(request_data, dict) else ""
        is_public = request_data.get("is_public", True) if isinstance(request_data, dict) else True
        if not name or len(name) < 2:
            raise ValueError("Question set name must be at least 2 characters")
        if len(name) > 255:
            raise ValueError("Question set name must be at most 255 characters")
        if db.query(QuestionSet).filter(QuestionSet.name == name).first():
            raise ValueError("Question set name already exists")
        qs = QuestionSet(name=name, is_public=is_public, creator_id=admin.id)
        db.add(qs)
        db.commit()
        db.refresh(qs)
        ip_address = extract_client_ip(request_obj, x_forwarded_for)
        log_admin_action(admin_id=admin.id, action="CREATE_QUESTION_SET", target_type="QUESTION_SET",
                         target_id=qs.id, before_state=None, after_state={"name": name, "is_public": is_public},
                         ip_address=ip_address, reason=None, db=db)
        return {"id": qs.id, "name": qs.name, "is_public": is_public}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="Error creating question set: " + str(e))


@router.post("/question-sets/{set_id}/questions", response_model=dict)
async def admin_add_question_to_set(
    set_id: int, request_data: dict = Body(...), admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db), x_forwarded_for: str = Header(None), request_obj: Request = None,
):
    """Add a question to a question set (admin only)."""
    try:
        question_set = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()
        if not question_set:
            raise HTTPException(status_code=404, detail="Question set not found")
        question_text = request_data.get("question_text", "").strip()
        question_type = request_data.get("question_type", "choice").lower()
        options = request_data.get("options", [])
        if not question_text or len(question_text) < 3:
            raise ValueError("Question text must be at least 3 characters")
        allowed_types = ["choice", "yesno", "text", "member_choice", "duo_choice", "free_text"]
        if question_type not in allowed_types:
            raise ValueError("Invalid question type")
        if question_type == "choice" and len(options) < 2:
            raise ValueError("Choice questions need at least 2 options")

        # Map types
        type_map = {
            "yesno": (QuestionTypeEnum.BINARY_VOTE, ["Yes", "No"]),
            "text": (QuestionTypeEnum.FREE_TEXT, []),
            "free_text": (QuestionTypeEnum.FREE_TEXT, []),
            "member_choice": (QuestionTypeEnum.MEMBER_CHOICE, []),
            "duo_choice": (QuestionTypeEnum.DUO_CHOICE, []),
        }
        if question_type in type_map:
            qt_enum, mapped_options = type_map[question_type]
        else:
            qt_enum, mapped_options = QuestionTypeEnum.SINGLE_CHOICE, options

        template = QuestionTemplate(
            category="Admin", question_text=question_text,
            option_a_template=mapped_options[0] if mapped_options else None,
            option_b_template=mapped_options[1] if len(mapped_options) > 1 else None,
            question_type=qt_enum, allow_multiple=False, is_public=True,
        )
        db.add(template)
        db.flush()
        db.add(QuestionSetTemplate(question_set_id=set_id, template_id=template.id))
        db.commit()
        db.refresh(template)
        ip_address = extract_client_ip(request_obj, x_forwarded_for)
        log_admin_action(admin_id=admin.id, action="ADD_QUESTION", target_type="QUESTION",
                         target_id=template.id, before_state=None,
                         after_state={"question_text": question_text, "type": qt_enum.value if hasattr(qt_enum, "value") else str(qt_enum)},
                         ip_address=ip_address, reason=None, db=db)
        return {
            "id": template.id, "question_text": template.question_text,
            "type": template.question_type.value if hasattr(template.question_type, "value") else template.question_type,
            "options": [o for o in mapped_options if o],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/question-sets/{set_id}")
async def admin_delete_question_set(
    set_id: int, admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db), x_forwarded_for: str = Header(None), request_obj: Request = None,
):
    """Delete a question set and all related data."""
    try:
        question_set = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()
        if not question_set:
            raise HTTPException(status_code=404, detail="Question set not found")
        db.query(QuestionSetTemplate).filter(QuestionSetTemplate.question_set_id == set_id).delete()
        db.query(GroupQuestionSet).filter(GroupQuestionSet.question_set_id == set_id).delete()
        db.delete(question_set)
        db.commit()
        ip_address = extract_client_ip(request_obj, x_forwarded_for)
        log_admin_action(admin_id=admin.id, action="DELETE_QUESTION_SET", target_type="QUESTION_SET",
                         target_id=set_id, before_state={"name": question_set.name},
                         after_state=None, ip_address=ip_address, reason=None, db=db)
        return {"status": "deleted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/question-sets/{set_id}/questions/{question_id}")
async def admin_delete_question(
    set_id: int, question_id: int, admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db), x_forwarded_for: str = Header(None), request_obj: Request = None,
):
    """Delete a question from a question set."""
    try:
        question = db.query(QuestionSetTemplate).filter(
            QuestionSetTemplate.id == question_id, QuestionSetTemplate.question_set_id == set_id
        ).first()
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")
        db.delete(question)
        db.commit()
        ip_address = extract_client_ip(request_obj, x_forwarded_for)
        log_admin_action(admin_id=admin.id, action="DELETE_QUESTION", target_type="QUESTION",
                         target_id=question_id, before_state=None,
                         after_state=None, ip_address=ip_address, reason=None, db=db)
        return {"status": "deleted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# ============= API Request Logs =============

@router.get("/api-logs")
async def get_api_request_logs(
    admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    method: Optional[str] = Query(None, description="Filter by HTTP method"),
    path_filter: Optional[str] = Query(None, description="Filter by path (substring)"),
    status_code: Optional[int] = Query(None, description="Filter by status code"),
    min_duration: Optional[int] = Query(None, description="Minimum duration in ms"),
):
    """Get server-side API request logs (all endpoints, all users)."""
    query = db.query(ApiRequestLog)
    if method:
        query = query.filter(ApiRequestLog.method == method.upper())
    if path_filter:
        query = query.filter(ApiRequestLog.path.ilike(f"%{path_filter}%"))
    if status_code is not None:
        query = query.filter(ApiRequestLog.status_code == status_code)
    if min_duration is not None:
        query = query.filter(ApiRequestLog.duration_ms >= min_duration)
    total = query.count()
    logs = query.order_by(ApiRequestLog.id.desc()).limit(limit).offset(offset).all()
    return {
        "logs": [
            {
                "id": l.id,
                "timestamp": l.timestamp.isoformat() if l.timestamp else None,
                "method": l.method,
                "path": l.path,
                "query_string": l.query_string,
                "status_code": l.status_code,
                "duration_ms": l.duration_ms,
                "client_ip": l.client_ip,
                "user_agent": l.user_agent,
                "account_id": l.account_id,
                "request_body_preview": l.request_body_preview,
                "response_size": l.response_size,
            }
            for l in logs
        ],
        "total": total, "limit": limit, "offset": offset,
    }


@router.delete("/api-logs")
async def clear_api_request_logs(
    admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db),
    x_forwarded_for: str = Header(None), request_obj: Request = None,
):
    """Clear all API request logs."""
    deleted = db.query(ApiRequestLog).delete()
    db.commit()
    ip_address = extract_client_ip(request_obj, x_forwarded_for)
    log_admin_action(admin_id=admin.id, action="CLEAR_API_LOGS", target_type="API_LOGS",
                     target_id="all", before_state=None,
                     after_state={"deleted_count": deleted},
                     ip_address=ip_address, reason="Admin cleared API logs", db=db)
    return {"message": f"Cleared {deleted} API log entries"}


# ============= DB Browser =============

# Allowlisted tables for safe read-only browsing
_DB_BROWSER_TABLES = [
    "accounts", "admin_users", "groups", "users", "daily_questions",
    "question_templates", "question_sets", "question_set_templates",
    "group_question_sets", "votes", "user_group_streaks", "group_analytics",
    "audit_logs", "api_request_logs", "group_custom_sets",
    "user_device_tokens", "password_reset_tokens", "alembic_version",
]


@router.get("/db/tables")
async def db_browser_tables(
    admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db),
):
    """List all browsable database tables with row counts."""
    tables = []
    for table_name in _DB_BROWSER_TABLES:
        try:
            row = db.execute(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = :t"),
                {"t": table_name},
            ).scalar()
            if not row:
                continue
            count = db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
            tables.append({"name": table_name, "row_count": count})
        except Exception:
            continue
    return {"tables": tables}


@router.get("/db/tables/{table_name}/schema")
async def db_browser_schema(
    table_name: str,
    admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db),
):
    """Get column information for a table."""
    if table_name not in _DB_BROWSER_TABLES:
        raise HTTPException(status_code=400, detail="Table not allowed")
    rows = db.execute(
        text(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_name = :t ORDER BY ordinal_position"
        ),
        {"t": table_name},
    ).fetchall()
    return {
        "table": table_name,
        "columns": [
            {
                "name": r[0],
                "type": r[1],
                "nullable": r[2] == "YES",
                "default": r[3],
            }
            for r in rows
        ],
    }


@router.get("/db/tables/{table_name}/rows")
async def db_browser_rows(
    table_name: str,
    admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort_column: Optional[str] = Query(None),
    sort_dir: Optional[str] = Query("asc", regex="^(asc|desc)$"),
    search: Optional[str] = Query(None, description="Search across all text columns"),
):
    """Fetch rows from a table with pagination, sorting, and search."""
    if table_name not in _DB_BROWSER_TABLES:
        raise HTTPException(status_code=400, detail="Table not allowed")

    # Get text columns for search
    col_rows = db.execute(
        text(
            "SELECT column_name, data_type "
            "FROM information_schema.columns WHERE table_name = :t ORDER BY ordinal_position"
        ),
        {"t": table_name},
    ).fetchall()
    columns = [r[0] for r in col_rows]
    text_cols = [r[0] for r in col_rows if r[1] in (
        "character varying", "text", "character", "uuid", "inet",
    )]

    # Validate sort column
    order_clause = ""
    if sort_column and sort_column in columns:
        direction = "DESC" if sort_dir == "desc" else "ASC"
        order_clause = f'ORDER BY "{sort_column}" {direction} NULLS LAST'
    elif "id" in columns:
        order_clause = "ORDER BY id ASC"

    # Build search filter
    where_clause = ""
    params: dict = {"lim": limit, "off": offset}
    if search and text_cols:
        conditions = []
        for i, col in enumerate(text_cols):
            param_key = f"s{i}"
            conditions.append(f'CAST("{col}" AS TEXT) ILIKE :{param_key}')
            params[param_key] = f"%{search}%"
        where_clause = "WHERE " + " OR ".join(conditions)

    count_sql = f'SELECT COUNT(*) FROM "{table_name}" {where_clause}'
    total = db.execute(text(count_sql), params).scalar()

    data_sql = f'SELECT * FROM "{table_name}" {where_clause} {order_clause} LIMIT :lim OFFSET :off'
    rows = db.execute(text(data_sql), params).fetchall()

    # Serialize rows
    serialized = []
    for row in rows:
        row_dict = {}
        for idx, col in enumerate(columns):
            val = row[idx]
            if isinstance(val, datetime):
                val = val.isoformat()
            elif val is not None and not isinstance(val, (str, int, float, bool)):
                val = str(val)
            row_dict[col] = val
        serialized.append(row_dict)

    return {
        "table": table_name,
        "columns": columns,
        "rows": serialized,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
