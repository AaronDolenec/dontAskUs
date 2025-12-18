"""
Admin authentication system with 2FA (TOTP) support
Handles instance admin login, token generation, and session management
"""

import os
import pyotp
import jwt
import bcrypt
import ipaddress
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy import and_
from sqlalchemy.orm import Session

from database import SessionLocal
from models import AdminUser, AuditLog

# Security configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-super-secret-key-change-in-production")
ADMIN_JWT_EXPIRY_MINUTES = 60
ADMIN_REFRESH_EXPIRY_DAYS = 7
LOGIN_ATTEMPT_LIMIT = 5
LOGIN_ATTEMPT_WINDOW_MINUTES = 15
LOCKOUT_DURATION_MINUTES = 30

# Bearer token scheme
security = HTTPBearer()


class AdminAuthError(Exception):
    """Custom exception for admin auth errors"""
    pass


class AdminLoginRequest:
    """Request model for admin login"""
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password


class AdminTOTPRequest:
    """Request model for TOTP verification"""
    def __init__(self, temp_token: str, totp_code: str):
        self.temp_token = temp_token
        self.totp_code = totp_code


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode(), salt).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode(), hashed.encode())


def generate_temp_token(admin_id: int) -> str:
    """Generate a temporary token for 2FA step (valid for 5 minutes)"""
    payload = {
        "sub": f"admin_{admin_id}",
        "type": "temp",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        "iat": datetime.now(timezone.utc)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def verify_temp_token(token: str) -> int:
    """Verify temporary token and extract admin_id"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "temp":
            raise AdminAuthError("Invalid token type")
        admin_id = int(payload["sub"].replace("admin_", ""))
        return admin_id
    except jwt.ExpiredSignatureError:
        raise AdminAuthError("Temporary token expired")
    except (jwt.InvalidTokenError, ValueError):
        raise AdminAuthError("Invalid temporary token")


def generate_access_token(admin_id: int) -> str:
    """Generate JWT access token (short-lived)"""
    payload = {
        "sub": f"admin_{admin_id}",
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ADMIN_JWT_EXPIRY_MINUTES),
        "iat": datetime.now(timezone.utc)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def generate_refresh_token(admin_id: int) -> str:
    """Generate JWT refresh token (long-lived)"""
    payload = {
        "sub": f"admin_{admin_id}",
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(days=ADMIN_REFRESH_EXPIRY_DAYS),
        "iat": datetime.now(timezone.utc)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def verify_access_token(token: str) -> int:
    """Verify access token and extract admin_id"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "access":
            raise AdminAuthError("Invalid token type")
        admin_id = int(payload["sub"].replace("admin_", ""))
        return admin_id
    except jwt.ExpiredSignatureError:
        raise AdminAuthError("Access token expired")
    except (jwt.InvalidTokenError, ValueError):
        raise AdminAuthError("Invalid access token")


def verify_refresh_token(token: str) -> int:
    """Verify refresh token and extract admin_id"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "refresh":
            raise AdminAuthError("Invalid token type")
        admin_id = int(payload["sub"].replace("admin_", ""))
        return admin_id
    except jwt.ExpiredSignatureError:
        raise AdminAuthError("Refresh token expired")
    except (jwt.InvalidTokenError, ValueError):
        raise AdminAuthError("Invalid refresh token")


def check_login_attempts(admin: AdminUser) -> None:
    """Check if admin account is locked due to too many login attempts"""
    if admin.is_locked_until and admin.is_locked_until > datetime.now(timezone.utc):
        remaining_seconds = (admin.is_locked_until - datetime.now(timezone.utc)).total_seconds()
        raise AdminAuthError(f"Account locked. Try again in {int(remaining_seconds)} seconds.")


def record_failed_login_attempt(admin: AdminUser, ip_address: str, db: Session) -> None:
    """Record failed login attempt and lock account if limit exceeded"""
    now = datetime.now(timezone.utc)
    
    # Reset counter if outside the window
    if admin.last_login_attempt is None or \
       (now - admin.last_login_attempt).total_seconds() > LOGIN_ATTEMPT_WINDOW_MINUTES * 60:
        admin.login_attempt_count = 1
    else:
        admin.login_attempt_count += 1
    
    admin.last_login_attempt = now
    try:
        admin.last_login_ip = str(ipaddress.ip_address(ip_address))
    except Exception:
        admin.last_login_ip = None
    
    # Lock account if limit exceeded
    if admin.login_attempt_count >= LOGIN_ATTEMPT_LIMIT:
        admin.is_locked_until = now + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
    
    db.commit()


def record_successful_login(admin: AdminUser, ip_address: str, db: Session) -> None:
    """Record successful login and reset attempt counter"""
    admin.login_attempt_count = 0
    admin.last_login_attempt = None
    try:
        admin.last_login_ip = str(ipaddress.ip_address(ip_address))
    except Exception:
        admin.last_login_ip = None
    db.commit()


def log_admin_action(
    admin_id: int,
    action: str,
    target_type: str,
    target_id: Optional[int],
    before_state: Optional[dict],
    after_state: Optional[dict],
    ip_address: Optional[str],
    reason: Optional[str],
    db: Session
) -> AuditLog:
    """Create an audit log entry for admin actions"""
    try:
        sanitized_ip = str(ipaddress.ip_address(ip_address)) if ip_address else None
    except Exception:
        sanitized_ip = None

    audit_log = AuditLog(
        admin_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_state=before_state,
        after_state=after_state,
        timestamp=datetime.now(timezone.utc),
        ip_address=sanitized_ip,
        reason=reason
    )
    db.add(audit_log)
    db.commit()
    return audit_log


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_admin(credentials = Depends(security), db: Session = Depends(get_db)) -> AdminUser:
    """Dependency to get current authenticated admin from JWT token"""
    token = credentials.credentials
    
    try:
        admin_id = verify_access_token(token)
    except AdminAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    admin = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin user not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return admin


def get_admin_from_refresh_token(token: str, db: Session) -> AdminUser:
    """Get admin from refresh token (used for token refresh)"""
    try:
        admin_id = verify_refresh_token(token)
    except AdminAuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    
    admin = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin user not found",
        )
    
    return admin


def authenticate_admin(username: str, password: str, ip_address: str, db: Session) -> AdminUser:
    """Authenticate admin with username and password"""
    admin = db.query(AdminUser).filter(AdminUser.username == username).first()
    
    if not admin:
        raise AdminAuthError("Invalid username or password")
    
    # Check if account is locked
    check_login_attempts(admin)
    
    # Verify password
    if not verify_password(password, admin.password_hash):
        record_failed_login_attempt(admin, ip_address, db)
        raise AdminAuthError("Invalid username or password")
    
    return admin


def verify_admin_totp(admin: AdminUser, totp_code: str) -> bool:
    """Verify TOTP code for 2FA"""
    if not admin.totp_enabled or not admin.totp_secret:
        raise AdminAuthError("2FA not configured for this admin")
    
    totp = pyotp.TOTP(admin.totp_secret)
    
    # Allow for time skew (current, +30s, -30s)
    return totp.verify(totp_code, valid_window=1)


def get_totp_secret() -> str:
    """Generate a new TOTP secret"""
    return pyotp.random_base32()


def get_totp_uri(username: str, totp_secret: str, issuer: str = "dontAskUs") -> str:
    """Generate provisioning URI for QR code"""
    totp = pyotp.TOTP(totp_secret)
    return totp.provisioning_uri(username, issuer_name=issuer)
