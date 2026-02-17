"""
Shared utility functions used across the application.
Consolidates duplicate code for password hashing, token management, etc.
"""

import base64
import io
import json
import secrets
import string
import random
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

import bcrypt
import jwt
import qrcode
from PIL import Image
from fastapi import HTTPException, Header, Depends, Request
from sqlalchemy import and_
from sqlalchemy.orm import Session

from core.config import (
    USER_JWT_SECRET, USER_JWT_ALGO, USER_JWT_ACCESS_EXPIRE_MINUTES,
    USER_JWT_REFRESH_EXPIRE_DAYS, AVATAR_MAGIC_BYTES, AVATAR_MAX_DIMENSION,
)
from core.database import get_db
from core.models import Account, User, Group


# ============= Password / Token Hashing =============

def hash_password(password: str) -> str:
    """Hash a password using bcrypt for secure storage."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


# ============= User JWT Functions =============

def create_user_jwt(account_id: int, token_type: str = "access") -> str:
    """Create a JWT token for user authentication."""
    now = datetime.now(timezone.utc)
    if token_type == "access":
        exp = now + timedelta(minutes=USER_JWT_ACCESS_EXPIRE_MINUTES)
    else:
        exp = now + timedelta(days=USER_JWT_REFRESH_EXPIRE_DAYS)
    payload = {
        "sub": str(account_id),
        "type": token_type,
        "exp": exp,
        "iat": now,
    }
    return jwt.encode(payload, USER_JWT_SECRET, algorithm=USER_JWT_ALGO)


def verify_user_jwt(token: str, expected_type: str = "access") -> int:
    """Verify a user JWT token and return the account ID."""
    try:
        payload = jwt.decode(token, USER_JWT_SECRET, algorithms=[USER_JWT_ALGO])
        if payload.get("type") != expected_type:
            raise HTTPException(status_code=401, detail="Invalid token type")
        return int(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ============= Auth Dependencies =============

def get_current_account(request: Request, db: Session = Depends(get_db)) -> Account:
    """Dependency to get the current authenticated user account from Bearer token."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header required")
    token = auth_header.split(" ", 1)[1]
    account_id = verify_user_jwt(token, "access")
    account = db.query(Account).filter(Account.id == account_id, Account.is_active == True).first()
    if not account:
        raise HTTPException(status_code=401, detail="Account not found or deactivated")
    return account


def get_current_account_optional(request: Request, db: Session = Depends(get_db)) -> Optional[Account]:
    """Optionally gets the current authenticated account. Returns None if no valid auth."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    try:
        token = auth_header.split(" ", 1)[1]
        account_id = verify_user_jwt(token, "access")
        return db.query(Account).filter(Account.id == account_id, Account.is_active == True).first()
    except HTTPException:
        return None


# ============= User / Group Lookup Helpers =============

def get_membership(account: Account, group_id: int, db: Session) -> Optional[User]:
    """Get the User (membership) record for an account in a specific group."""
    return db.query(User).filter(
        and_(User.account_id == account.id, User.group_id == group_id)
    ).first()


def get_user_from_request(
    request: Request, db: Session, user_id: Optional[str] = None
) -> Optional[User]:
    """Resolve a User from JWT Bearer token."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ", 1)[1]
            account_id_int = verify_user_jwt(token, "access")
            account = db.query(Account).filter(Account.id == account_id_int, Account.is_active == True).first()
            if account:
                if user_id:
                    specific = db.query(User).filter(
                        and_(User.account_id == account.id, User.user_id == user_id)
                    ).first()
                    if specific:
                        return specific
                memberships = db.query(User).filter(User.account_id == account.id).all()
                if memberships:
                    return memberships[0]
        except HTTPException:
            pass
    return None


def get_user_for_group(request: Request, group: Group, db: Session) -> Optional[User]:
    """Resolve the authenticated user's membership in a specific group."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ", 1)[1]
            account_id_int = verify_user_jwt(token, "access")
            account = db.query(Account).filter(Account.id == account_id_int, Account.is_active == True).first()
            if account:
                return get_membership(account, group.id, db)
        except HTTPException:
            pass
    return None


def get_group_by_id(group_id: str, db: Session) -> Group:
    """Get group by group_id, raise 404 if not found."""
    group = db.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


def get_user_by_id(user_id: str, db: Session) -> User:
    """Get user by user_id, raise 404 if not found."""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ============= Common Helpers =============

def generate_invite_code() -> str:
    """Generate a unique 6-character invite code."""
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))


def get_random_avatar_color() -> str:
    """Return a random avatar color from a predefined palette."""
    colors = [
        "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A",
        "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E2",
        "#F8B88B", "#A8E6CF"
    ]
    return secrets.choice(colors)


def get_avatar_url(avatar_filename: Optional[str], base_url: str = "") -> Optional[str]:
    """Generate full URL for avatar. Returns None if no avatar."""
    if not avatar_filename:
        return None
    return f"{base_url}/uploads/avatars/{avatar_filename}"


def validate_image_magic_bytes(file_bytes: bytes) -> Optional[str]:
    """Validate file by checking magic bytes. Returns detected MIME type or None."""
    for magic, mime_type in AVATAR_MAGIC_BYTES.items():
        if file_bytes.startswith(magic):
            return mime_type
    if file_bytes[:4] == b'RIFF' and file_bytes[8:12] == b'WEBP':
        return 'image/webp'
    return None


def process_avatar_image(file_bytes: bytes) -> bytes:
    """Process uploaded avatar: validate, resize to 256x256 max, convert to WebP."""
    try:
        img = Image.open(io.BytesIO(file_bytes))
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        img.thumbnail((AVATAR_MAX_DIMENSION, AVATAR_MAX_DIMENSION), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        img.save(output, format='WEBP', quality=85, method=6)
        return output.getvalue()
    except Exception as e:
        logging.error(f"Error processing avatar image: {e}")
        raise ValueError("Invalid or corrupted image file")


def generate_qr_code(data: str) -> str:
    """Generate QR code and return as base64 data URL."""
    qr = qrcode.QRCode(
        version=1, error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10, border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{img_str}"


def get_group_member_names(group: Group, db: Session) -> list[str]:
    """Get all display names for members of a group."""
    return [row[0] for row in db.query(User.display_name).filter(User.group_id == group.id).all()]


def generate_duos(member_names: list[str], max_pairs: int = 5) -> list[str]:
    """Generate up to max_pairs random unique duos as labels 'Name1 + Name2'."""
    if len(member_names) < 2:
        return []
    pairs = []
    seen = set()
    attempts = 0
    target = min(max_pairs, len(member_names) * (len(member_names) - 1) // 2)
    while len(pairs) < target and attempts < 50:
        a, b = random.sample(member_names, 2)
        key = tuple(sorted([a, b]))
        if key in seen:
            attempts += 1
            continue
        seen.add(key)
        pairs.append(f"{a} + {b}")
        attempts += 1
    return pairs


def extract_client_ip(request: Request, header_ip: Optional[str] = None) -> str:
    """Extract real client IP from request, handling proxies and Docker."""
    import ipaddress as _ipaddress
    if header_ip:
        raw_ip = header_ip.split(',')[0].strip()
        try:
            _ipaddress.ip_address(raw_ip)
            return raw_ip
        except ValueError:
            pass  # Ignore malformed IP, fall through
    if request and request.client:
        ip = request.client.host
        if ip and ip.startswith("172."):
            return "docker"
        return ip
    return "unknown"


# ============= Vote/Answer Helpers =============

def parse_vote_answer(raw_answer: Optional[str]):
    """Return stored answer as list or scalar if JSON array is stored."""
    if raw_answer is None:
        return None
    try:
        parsed = json.loads(raw_answer)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    return raw_answer


def normalize_answer_submission(raw_answer, allow_multiple: bool) -> list[str]:
    """Normalize inbound answer into a list while enforcing single/multi rules."""
    if raw_answer is None:
        return []
    if isinstance(raw_answer, str):
        stripped = raw_answer.strip()
        if allow_multiple:
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    raw_answer = parsed
            except Exception:
                raw_answer = stripped
        else:
            return [stripped]
    if isinstance(raw_answer, list):
        normalized = []
        seen = set()
        for item in raw_answer:
            if item is None:
                continue
            val = str(item).strip()
            if not val or val in seen:
                continue
            seen.add(val)
            normalized.append(val)
        return normalized
    return [str(raw_answer).strip()]


def get_option_counts(question_id: int, db: Session) -> dict:
    """Aggregate counts per answer value, flattening multi-select payloads."""
    from core.models import Vote
    rows = db.query(Vote.answer).filter(Vote.question_id == question_id).all()
    counts: dict[str, int] = {}
    for (raw_answer,) in rows:
        if raw_answer is None:
            continue
        parsed = parse_vote_answer(raw_answer)
        if isinstance(parsed, list):
            for item in parsed:
                if item is None:
                    continue
                key = str(item)
                counts[key] = counts.get(key, 0) + 1
        else:
            key = str(parsed)
            counts[key] = counts.get(key, 0) + 1
    return counts


def get_user_vote(user_id: int, question_id: int, db: Session) -> Optional[str]:
    """Get user's vote answer for a question."""
    from core.models import Vote
    vote = db.query(Vote).filter(
        and_(Vote.question_id == question_id, Vote.user_id == user_id)
    ).first()
    if not vote:
        return None
    return parse_vote_answer(vote.answer)


# ============= Streak Helpers =============

def get_user_group_streak(user_id: int, group_id: int, db: Session):
    """Get or create per-group streak record for a user."""
    from core.models import UserGroupStreak
    streak = db.query(UserGroupStreak).filter(
        and_(UserGroupStreak.user_id == user_id, UserGroupStreak.group_id == group_id)
    ).first()
    if not streak:
        streak = UserGroupStreak(user_id=user_id, group_id=group_id)
        db.add(streak)
        db.commit()
        db.refresh(streak)
    return streak


def update_user_group_streak(user_id: int, group_id: int, db: Session):
    """Update per-group streak for a user after answering a question."""
    from datetime import date as date_type
    streak = get_user_group_streak(user_id, group_id, db)
    today = date_type.today()
    if streak.last_answer_date:
        last_date = streak.last_answer_date.date()
        if last_date == today:
            pass
        elif (today - last_date).days == 1:
            streak.current_streak += 1
        else:
            streak.current_streak = 1
    else:
        streak.current_streak = 1
    if streak.current_streak > streak.longest_streak:
        streak.longest_streak = streak.current_streak
    streak.last_answer_date = datetime.now(timezone.utc)
    db.commit()


# ============= Group Admin (Creator) Dependency =============

def require_group_creator(
    group_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Dependency to ensure the caller is the group creator via JWT Bearer token."""
    group = db.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header required")
    token = auth_header.split(" ", 1)[1]
    account_id = verify_user_jwt(token, "access")
    account = db.query(Account).filter(Account.id == account_id, Account.is_active == True).first()
    if not account:
        raise HTTPException(status_code=401, detail="Account not found or deactivated")
    # Find user membership in this group
    user = db.query(User).filter(
        and_(User.account_id == account.id, User.group_id == group.id)
    ).first()
    if not user:
        raise HTTPException(status_code=403, detail="You are not a member of this group")
    if group.creator_id != user.id:
        raise HTTPException(status_code=403, detail="Only the group creator can perform this action")
    return group
