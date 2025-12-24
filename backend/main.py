def verify_token(token: str, hashed_token: str) -> bool:
    """Verify a plaintext token against its bcrypt hash."""
    return bcrypt.checkpw(token.encode('utf-8'), hashed_token.encode('utf-8'))
import bcrypt
def hash_token(token: str) -> str:
    """Hash a token using bcrypt for secure storage."""
    return bcrypt.hashpw(token.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, Path, Request, Header, Body
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, date, timezone, timedelta
from contextlib import asynccontextmanager
import threading
import time
import random
import os
import json
# pylint: disable=broad-except,logging-fstring-interpolation
import secrets
import string
import qrcode
import base64
import io
from typing import Optional, Tuple
import logging
from fastapi.responses import JSONResponse, FileResponse, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from database import engine, get_db, Base, SessionLocal
from seed_defaults import initialize_default_question_set, assign_default_set_to_unassigned_groups
from models import (
    Group, User, DailyQuestion, Vote, QuestionTemplate, QuestionSet, QuestionSetTemplate, 
    GroupQuestionSet, UserGroupStreak, QuestionTypeEnum, AdminUser, AuditLog, GroupCustomSet,
    hash_password, verify_password, generate_totp_secret, verify_totp
)
from schemas import (
    GroupCreate, GroupResponse, GroupResponsePublic, UserCreate, UserResponse,
    DailyQuestionCreate, DailyQuestionResponse, VoteCreate, AnswerSubmissionCreate,
    QuestionTemplateResponse, QuestionSetCreate, QuestionSetResponse, GroupQuestionSetsResponse, 
    GroupAssignSetsRequest,
    AdminLoginRequest, AdminLoginResponse, Admin2FARequest, Admin2FAResponse
)
import jwt
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import status
## duplicate import removed (see above)

# ============= Admin Auth Config =============
ADMIN_JWT_SECRET = os.getenv("ADMIN_JWT_SECRET", "supersecretkey")
ADMIN_JWT_ALGO = "HS256"
ADMIN_JWT_EXPIRE_MINUTES = 60 * 8  # 8 hours

security = HTTPBearer()



def create_admin_jwt(admin_id: int) -> str:
    payload = {
        "sub": str(admin_id),
        "exp": datetime.utcnow() + timedelta(minutes=ADMIN_JWT_EXPIRE_MINUTES)
    }
    return jwt.encode(payload, ADMIN_JWT_SECRET, algorithm=ADMIN_JWT_ALGO)

def verify_admin_jwt(token: str) -> int:
    try:
        payload = jwt.decode(token, ADMIN_JWT_SECRET, algorithms=[ADMIN_JWT_ALGO])
        return int(payload["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired admin token")

def get_current_admin(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)) -> AdminUser:
    token = credentials.credentials
    admin_id = verify_admin_jwt(token)
    admin = db.query(AdminUser).filter(AdminUser.id == admin_id, AdminUser.is_active == True).first()
    if not admin:
        raise HTTPException(status_code=401, detail="Admin not found or inactive")
    return admin



# ============= Admin Auth Endpoints =============

# (Moved below app = FastAPI(...))
from ws_manager import manager
from dotenv import load_dotenv

load_dotenv()

# Central logging configuration
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# Get configuration from environment
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000,http://localhost:8085,http://127.0.0.1:8085").split(",")
SESSION_TOKEN_EXPIRY_DAYS = int(os.getenv("SESSION_TOKEN_EXPIRY_DAYS", "7"))

# Create tables (guarded so app doesn't crash if DB is unavailable during dev)
try:
    Base.metadata.create_all(bind=engine)
except Exception:
    logging.exception("Database unavailable at startup; continuing without creating tables")



# Move lifespan definition above app initialization
@asynccontextmanager
async def lifespan(_app):
    # Run startup tasks: seed default data and start the background scheduler
    try:
        # seed default templates and sets
        try:
            initialize_default_question_set()
        except Exception:
            logging.exception("initialize_default_question_set failed during lifespan startup")
        # Ensure all groups have the Default set if none assigned
        try:
            assign_default_set_to_unassigned_groups()
        except Exception:
            logging.exception("assign_default_set_to_unassigned_groups failed during lifespan startup")

        # start scheduler thread
        try:
            interval = int(os.getenv("SCHEDULE_INTERVAL_SECONDS", "86400"))
            t = threading.Thread(target=_background_scheduler, args=(interval,), daemon=True)
            t.start()
        except Exception:
            logging.exception("background scheduler failed to start during lifespan startup")

        yield
        
        # Startup complete - log access information to console and logs
        startup_msg = (
            "\n" + "=" * 80 + "\n"
            "🚀 DontAskUs Backend Started Successfully!\n"
            "=" * 80 + "\n"
            "📚 API Documentation: http://localhost:8000/docs\n"
            "🔐 Admin UI: http://localhost:5173/admin\n"
            "📊 API Base URL: http://localhost:8000/api\n"
            "=" * 80 + "\n"
        )
        print(startup_msg)
        logging.info(startup_msg)
    finally:
        # no-op shutdown
        pass

app = FastAPI(
    title="DontAskUs - Real-Time Q&A Platform",
    version="1.0.0",
    description="A self-hosted alternative to AskUs with real-time voting",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# CORS - Whitelist specific origins instead of wildcard
allowed_origins_list = [origin.strip() for origin in ALLOWED_ORIGINS if origin.strip()]
logging.info(f"CORS allowed origins: {allowed_origins_list}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Token"],
)

SWAGGER_DARK_CSS = """
@import url('https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css');

:root { color-scheme: dark; }
body { background: #0b1220; }
/* Force readable text colors */
.swagger-ui, .swagger-ui p, .swagger-ui li, .swagger-ui span,
.swagger-ui h1, .swagger-ui h2, .swagger-ui h3, .swagger-ui h4,
.swagger-ui td, .swagger-ui th, .swagger-ui label,
.swagger-ui .info, .swagger-ui .opblock-tag, .swagger-ui .parameter__name,
.swagger-ui .parameter__type, .swagger-ui .response__status,
.swagger-ui .parameters-col_description, .swagger-ui .response-col_description,
.swagger-ui .opblock-summary-description, .swagger-ui .model-title {
    color: #f8fafc !important;
}
.swagger-ui a { color: #67e8f9 !important; }
.swagger-ui .topbar { background: #0b1220; border-bottom: 1px solid #1f2937; }
.swagger-ui .topbar .download-url-wrapper { display: none; }
.swagger-ui .topbar .link span { color: #e2e8f0; }
.swagger-ui .scheme-container { background: #0f172a; border: 1px solid #1f2937; }
.swagger-ui .opblock { background: #0f172a; border: 1px solid #1f2937; }
.swagger-ui .opblock .opblock-summary { background: #0f172a; }
.swagger-ui .opblock .opblock-section-header { background: #111827; border-color: #1f2937; }
.swagger-ui table thead tr th { background: #111827; border-color: #1f2937; }
.swagger-ui table tbody tr td { border-color: #1f2937; }
.swagger-ui .model-box { background: #0b1220; border-color: #1f2937; }
.swagger-ui .prop-type { color: #67e8f9 !important; }
.swagger-ui .opblock-description-wrapper p { color: #cbd5e1 !important; }
.swagger-ui .btn { background: #22d3ee; color: #0b1220; border: none; }
.swagger-ui .btn:hover { background: #0ea5e9; }
.swagger-ui .btn.authorize { background: #22c55e; color: #0b1220; }
.swagger-ui .btn.authorize:hover { background: #16a34a; }
.swagger-ui .btn.authorize svg { fill: #0b1220; }
.swagger-ui .authorization__btn svg { fill: #f8fafc !important; }
.swagger-ui .locked svg, .swagger-ui .unlocked svg { fill: #f8fafc !important; }
.swagger-ui .opblock-summary-operation-id svg,
.swagger-ui .opblock-summary svg,
.swagger-ui .authorization__btn.locked svg,
.swagger-ui .authorization__btn.unlocked svg,
.swagger-ui .opblock .authorization__btn svg { fill: #f8fafc !important; }
.swagger-ui .copy-to-clipboard { color: #22d3ee; }
.swagger-ui .markdown code, .swagger-ui .code code { background: #111827; color: #e2e8f0; }
.swagger-ui .response-control-media-range { color: #e2e8f0; }
.swagger-ui textarea, .swagger-ui input[type=\"text\"], .swagger-ui select {
    background: #0b1220; color: #e2e8f0; border: 1px solid #1f2937;
}
.swagger-ui input::placeholder, .swagger-ui textarea::placeholder { color: #94a3b8; }
"""

@app.get("/swagger-ui-dark.css", include_in_schema=False)
async def swagger_dark_css():
        return Response(content=SWAGGER_DARK_CSS, media_type="text/css")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title="DontAskUs API Docs",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="/swagger-ui-dark.css",
        swagger_ui_parameters={
            "defaultModelsExpandDepth": -1,
            "displayRequestDuration": True,
            "persistAuthorization": True,
            "syntaxHighlight.theme": "monokai",
        },
    )

# Rate limiting error handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(_request, _exc):
    return JSONResponse(status_code=429, content={"detail": "Too many requests. Please try again later."})

# Mount admin UI static files
ui_dist_path = os.path.join(os.path.dirname(__file__), "admin_ui_dist")
if os.path.exists(ui_dist_path):
    app.mount("/admin", StaticFiles(directory=ui_dist_path, html=True), name="admin-ui")
    logging.info(f"Admin UI mounted at /admin from {ui_dist_path}")
else:
    logging.warning(f"Admin UI dist directory not found at {ui_dist_path}")

# ============= Helper Functions =============

def generate_invite_code() -> str:
    """Generate a unique 6-8 character invite code"""
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))

def generate_session_token() -> str:
    """Generate a secure session token"""
    return secrets.token_urlsafe(32)

def generate_admin_token() -> str:
    """Generate secure admin token"""
    return secrets.token_urlsafe(32)

def _hash_and_store_token(plaintext_token: str) -> str:
    """Hash a token for secure storage in database."""
    return hash_token(plaintext_token)

def _verify_session_token(plaintext_token: str, stored_hash: str) -> bool:
    """Verify a plaintext session token against its hash."""
    try:
        return verify_token(plaintext_token, stored_hash)
    except Exception:
        return False

def get_random_avatar_color() -> str:
    """Return a random avatar color from predefined palette"""
    colors = [
        "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A",
        "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E2",
        "#F8B88B", "#A8E6CF"
    ]
    return secrets.choice(colors)


def _pick_two_group_members(group: Group, db: Session) -> Tuple[str, str]:
    """Select two distinct member display names from a group for answer options."""
    member_names = [row[0] for row in db.query(User.display_name).filter(User.group_id == group.id).all()]
    if len(member_names) < 2:
        raise HTTPException(status_code=400, detail="Need at least two members to generate answer options")
    a, b = random.sample(member_names, 2)
    return a, b


def _get_group_member_names(group: Group, db: Session) -> list[str]:
    return [row[0] for row in db.query(User.display_name).filter(User.group_id == group.id).all()]


def _generate_duos(member_names: list[str], max_pairs: int = 5) -> list[str]:
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


# ==================== COMMON LOOKUP HELPERS ====================

def get_group_by_id(group_id: str, db: Session) -> Group:
    """Get group by group_id, raise 404 if not found"""
    group = db.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


def get_user_by_id(user_id: str, db: Session) -> User:
    """Get user by user_id, raise 404 if not found"""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def get_question_set_by_id(set_id: str, db: Session) -> QuestionSet:
    """Get question set by set_id, raise 404 if not found"""
    qs = db.query(QuestionSet).filter(QuestionSet.set_id == set_id).first()
    if not qs:
        raise HTTPException(status_code=404, detail="Question set not found")
    return qs


def _generate_qr_code(data: str) -> str:
    """Generate QR code and return as base64 data URL"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"

def _get_vote_counts(question_id: int, db: Session) -> tuple:
    """Get vote counts for a question. Returns (count_a, count_b)"""
    vote_count_a = db.query(Vote).filter(
        and_(Vote.question_id == question_id, Vote.answer == 'A')
    ).count()
    vote_count_b = db.query(Vote).filter(
        and_(Vote.question_id == question_id, Vote.answer == 'B')
    ).count()
    return vote_count_a, vote_count_b


def _get_option_counts(question_id: int, db: Session) -> dict:
    """Aggregate counts per answer value, flattening multi-select payloads."""
    rows = db.query(Vote.answer).filter(Vote.question_id == question_id).all()
    counts: dict[str, int] = {}
    for (raw_answer,) in rows:
        if raw_answer is None:
            continue
        parsed = _parse_vote_answer(raw_answer)
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


def _parse_vote_answer(raw_answer: Optional[str]):
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


def _normalize_answer_submission(raw_answer, allow_multiple: bool) -> list[str]:
    """Normalize inbound answer into a list while enforcing single/multi rules."""
    if raw_answer is None:
        return []

    # Try to parse JSON arrays that might come as strings
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

    # Any other scalar
    return [str(raw_answer).strip()]

def _get_user_by_session(session_token: str, db: Session) -> Optional[User]:
    """Get user from session token, verifying hash and expiry."""
    # Find all users with potential matching tokens (limited lookup)
    users = db.query(User).all()  # In production, optimize this with indexed lookup
    
    for user in users:
        # Check if token is expired
        if user.session_token_expires_at:
            # Ensure both datetimes are timezone-aware for comparison
            expires_at = user.session_token_expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expires_at:
                logging.info(f"Session token expired for user {user.user_id}")
                return None
        
        # Verify token hash
        if _verify_session_token(session_token, user.session_token):
            return user
    
    return None

def _get_user_vote(user_id: int, question_id: int, db: Session) -> Optional[str]:
    """Get user's vote answer for a question"""
    vote = db.query(Vote).filter(
        and_(Vote.question_id == question_id, Vote.user_id == user_id)
    ).first()
    if not vote:
        return None
    return _parse_vote_answer(vote.answer)


def _get_user_group_streak(user_id: int, group_id: int, db: Session) -> UserGroupStreak:
    """Get or create per-group streak record for a user"""
    streak = db.query(UserGroupStreak).filter(
        and_(UserGroupStreak.user_id == user_id, UserGroupStreak.group_id == group_id)
    ).first()
    if not streak:
        streak = UserGroupStreak(user_id=user_id, group_id=group_id)
        db.add(streak)
        db.commit()
        db.refresh(streak)
    return streak


def _update_user_group_streak(user_id: int, group_id: int, db: Session):
    """Update per-group streak for a user after answering a question"""
    streak = _get_user_group_streak(user_id, group_id, db)
    today = date.today()
    
    if streak.last_answer_date:
        last_date = streak.last_answer_date.date()
        if last_date == today:
            # Already answered today
            pass
        elif (today - last_date).days == 1:
            # Continued streak
            streak.current_streak += 1
        else:
            # Streak broken
            streak.current_streak = 1
    else:
        streak.current_streak = 1
    
    if streak.current_streak > streak.longest_streak:
        streak.longest_streak = streak.current_streak
    
    streak.last_answer_date = datetime.now(timezone.utc)
    db.commit()


def require_group_admin(group_id: str = Path(...), x_admin_token: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """Dependency to ensure the caller is group admin via `X-Admin-Token` header."""
    if not x_admin_token:
        raise HTTPException(status_code=401, detail="Admin token required in 'X-Admin-Token' header")
    
    group = db.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    
    # Verify admin token hash
    if not verify_token(x_admin_token, group.admin_token):
        raise HTTPException(status_code=401, detail="Invalid admin token")
    
    return group


## Seeding moved to seed_defaults.initialize_default_question_set


def create_daily_questions_for_today():
    """
    Create daily questions for all groups with smart selection:
    - Never repeat a question within the same group
    - Different groups get different questions on the same day
    - Warn admin if all questions have been exhausted
    """
    db = SessionLocal()
    try:
        today = datetime.now(timezone.utc).date()
        groups = db.query(Group).all()
        selected_today = set()  # Track which templates were selected today to prevent duplicates across groups
        
        for group in groups:
            # Skip if question exists for today
            existing = db.query(DailyQuestion).filter(
                and_(DailyQuestion.group_id == group.id, func.date(DailyQuestion.question_date) == today)
            ).first()
            if existing:
                continue

            # Collect templates from active sets
            assigned = db.query(GroupQuestionSet).filter(
                GroupQuestionSet.group_id == group.id, 
                GroupQuestionSet.is_active == True
            ).all()
            template_candidates = []
            for a in assigned:
                s = db.get(QuestionSet, a.question_set_id)
                if not s:
                    continue
                for assoc in db.query(QuestionSetTemplate).filter(QuestionSetTemplate.question_set_id == s.id).all():
                    t = db.get(QuestionTemplate, assoc.template_id)
                    if t:
                        template_candidates.append(t)

            # Fallback to any public template if none assigned
            if not template_candidates:
                template_candidates = db.query(QuestionTemplate).filter(QuestionTemplate.is_public == True).all()

            if not template_candidates:
                logging.warning(f"No templates available for group {group.group_id}")
                continue

            # Get previously used templates for this group to avoid repeats
            previously_used = db.query(DailyQuestion.template_id).filter(
                DailyQuestion.group_id == group.id,
                DailyQuestion.template_id.isnot(None)
            ).distinct().all()
            previously_used_ids = {t[0] for t in previously_used}

            # Filter out already-used templates for this group
            available = [t for t in template_candidates if t.id not in previously_used_ids]
            
            # If all templates have been used, reset and use all
            exhausted = False
            if not available:
                available = template_candidates
                exhausted = True
                if group.creator_id:
                    logging.warning(
                        f"All questions exhausted for group {group.group_id}. "
                        f"Cycling back to available questions. "
                        f"Admin user_id: {group.creator_id}"
                    )

            # Filter out templates already selected today (to prevent same question across groups)
            available = [t for t in available if t.id not in selected_today]
            
            # If all remaining are taken today, fall back to any available
            if not available:
                available = [t for t in template_candidates if t.id not in selected_today]
            
            # Last resort: pick from all candidates
            if not available:
                available = template_candidates

            if not available:
                continue

            # Select random template
            tmpl = random.choice(available)
            selected_today.add(tmpl.id)

            member_names = _get_group_member_names(group, db)
            
            # Generate options based on question type
            options_list = []
            option_a = None
            option_b = None
            
            if tmpl.question_type == QuestionTypeEnum.MEMBER_CHOICE:
                if len(member_names) < 2:
                    logging.warning("Skipping daily question for group %s - member_choice requires at least two members", group.group_id)
                    continue
                options_list = member_names
            elif tmpl.question_type == QuestionTypeEnum.DUO_CHOICE:
                if len(member_names) < 2:
                    logging.warning("Skipping daily question for group %s - duo_choice requires at least two members", group.group_id)
                    continue
                options_list = _generate_duos(member_names)
            elif tmpl.question_type == QuestionTypeEnum.BINARY_VOTE:
                # Use template options if provided, otherwise default to Yes/No
                if tmpl.option_a_template and tmpl.option_b_template:
                    options_list = [tmpl.option_a_template, tmpl.option_b_template]
                else:
                    options_list = ["Yes", "No"]
            elif tmpl.question_type == QuestionTypeEnum.SINGLE_CHOICE:
                # Use template options if provided, otherwise use members
                if tmpl.option_a_template and tmpl.option_b_template:
                    options_list = [tmpl.option_a_template, tmpl.option_b_template]
                elif len(member_names) >= 2:
                    options_list = member_names
            # FREE_TEXT gets no options

            if options_list:
                option_a = options_list[0]
                option_b = options_list[1] if len(options_list) > 1 else None

            dq = DailyQuestion(
                group_id=group.id,
                template_id=tmpl.id,
                question_text=tmpl.question_text,
                option_a=option_a,
                option_b=option_b,
                options=json.dumps(options_list) if options_list else None,
                question_type=tmpl.question_type,
                allow_multiple=getattr(tmpl, "allow_multiple", False),
                is_active=True
            )
            db.add(dq)
            
            # Log if exhausted
            if exhausted:
                logging.info(f"Question cycle reset for group {group.group_id} - all templates used")
        
        db.commit()
    except Exception:
        logging.exception("create_daily_questions_for_today failed, rolling back DB")
        db.rollback()
    finally:
        db.close()


def _background_scheduler(interval_seconds: int = 86400):
    # run once at startup
    try:
        create_daily_questions_for_today()
    except Exception:
        logging.exception("Initial create_daily_questions_for_today call failed in scheduler")
    while True:
        time.sleep(interval_seconds)
        try:
            create_daily_questions_for_today()
        except Exception:
            logging.exception("Scheduled create_daily_questions_for_today call failed in scheduler")


# Scheduler is started in the application's lifespan handler

def _create_today_question_for_group(db: Session, group: Group):
    today = datetime.now(timezone.utc).date()
    existing = db.query(DailyQuestion).filter(
        and_(DailyQuestion.group_id == group.id, func.date(DailyQuestion.question_date) == today)
    ).first()
    if existing:
        return existing

    # Collect templates from active sets
    assigned = db.query(GroupQuestionSet).filter(
        GroupQuestionSet.group_id == group.id,
        GroupQuestionSet.is_active == True,
    ).all()
    template_candidates = []
    for a in assigned:
        s = db.get(QuestionSet, a.question_set_id)
        if not s:
            continue
        for assoc in db.query(QuestionSetTemplate).filter(QuestionSetTemplate.question_set_id == s.id).all():
            t = db.get(QuestionTemplate, assoc.template_id)
            if t:
                template_candidates.append(t)

    # Fallback to any public template if none assigned
    if not template_candidates:
        template_candidates = db.query(QuestionTemplate).filter(QuestionTemplate.is_public == True).all()
    if not template_candidates:
        return None

    # Get previously used templates for this group to avoid repeats
    previously_used = db.query(DailyQuestion.template_id).filter(
        DailyQuestion.group_id == group.id,
        DailyQuestion.template_id.isnot(None),
    ).distinct().all()
    previously_used_ids = {t[0] for t in previously_used}

    available = [t for t in template_candidates if t.id not in previously_used_ids]
    if not available:
        available = template_candidates

    tmpl = random.choice(available)

    member_names = _get_group_member_names(group, db)
    options_list = []
    option_a = None
    option_b = None

    if tmpl.question_type == QuestionTypeEnum.MEMBER_CHOICE:
        if len(member_names) < 2:
            return None
        options_list = member_names
    elif tmpl.question_type == QuestionTypeEnum.DUO_CHOICE:
        if len(member_names) < 2:
            return None
        options_list = _generate_duos(member_names)
    elif tmpl.question_type == QuestionTypeEnum.BINARY_VOTE:
        options_list = [tmpl.option_a_template, tmpl.option_b_template] if (tmpl.option_a_template and tmpl.option_b_template) else ["Yes", "No"]
    elif tmpl.question_type == QuestionTypeEnum.SINGLE_CHOICE:
        if tmpl.option_a_template and tmpl.option_b_template:
            options_list = [tmpl.option_a_template, tmpl.option_b_template]
        elif len(member_names) >= 2:
            options_list = member_names

    if options_list:
        option_a = options_list[0]
        option_b = options_list[1] if len(options_list) > 1 else None

    dq = DailyQuestion(
        group_id=group.id,
        template_id=tmpl.id,
        question_text=tmpl.question_text,
        option_a=option_a,
        option_b=option_b,
        options=json.dumps(options_list) if options_list else None,
        question_type=tmpl.question_type,
        allow_multiple=getattr(tmpl, "allow_multiple", False),
        is_active=True,
    )
    db.add(dq)
    db.commit()
    db.refresh(dq)
    return dq

# ============= Group Routes =============

@app.post("/api/groups", response_model=GroupResponse)
@limiter.limit("20/minute")
def create_group(request: Request, group: GroupCreate, db: Session = Depends(get_db)):
    """Create a new group"""
    invite_code = generate_invite_code()
    admin_token_plaintext = generate_admin_token()
    admin_token_hash = _hash_and_store_token(admin_token_plaintext)
    
    # Ensure unique invite code
    while db.query(Group).filter(Group.invite_code == invite_code).first():
        invite_code = generate_invite_code()
    
    db_group = Group(
        name=group.name,
        invite_code=invite_code,
        admin_token=admin_token_hash  # Store hash, not plaintext
    )
    db.add(db_group)
    db.commit()
    db.refresh(db_group)
    
    # Generate QR code
    qr_data = _generate_qr_code(invite_code)
    db_group.qr_data = qr_data
    db.commit()

    # Automatically assign the Default question set to the new group
    try:
        default_set = db.query(QuestionSet).filter(QuestionSet.name == "Default").first()
        if not default_set:
            # Ensure it's created (idempotent)
            initialize_default_question_set()
            default_set = db.query(QuestionSet).filter(QuestionSet.name == "Default").first()
        if default_set:
            existing = db.query(GroupQuestionSet).filter(
                GroupQuestionSet.group_id == db_group.id,
                GroupQuestionSet.question_set_id == default_set.id,
            ).first()
            if not existing:
                db.add(GroupQuestionSet(group_id=db_group.id, question_set_id=default_set.id, is_active=True))
                db.commit()
    except Exception:
        logging.exception("Failed to assign Default question set to new group")
    
    return GroupResponse(
        id=db_group.id,
        group_id=db_group.group_id,
        name=db_group.name,
        invite_code=db_group.invite_code,
        admin_token=admin_token_plaintext,  # Return plaintext to user (only time shown)
        created_at=db_group.created_at,
        member_count=0
    )

@app.get("/api/groups/{invite_code}", response_model=GroupResponsePublic)
@limiter.limit("200/minute")
def get_group_by_code(request: Request, invite_code: str, db: Session = Depends(get_db)):
    """Get group info by invite code (for joining)"""
    group = db.query(Group).filter(Group.invite_code == invite_code).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    member_count = db.query(User).filter(User.group_id == group.id).count()
    
    return GroupResponsePublic(
        id=group.id,
        group_id=group.group_id,
        name=group.name,
        invite_code=group.invite_code,
        created_at=group.created_at,
        member_count=member_count
    )

@app.get("/api/groups/{group_id}/info", response_model=dict)
def get_group_full_info(
    group_id: str = Path(...),
    db: Session = Depends(get_db)
):
    """Get complete group information"""
    group = get_group_by_id(group_id, db)
    
    member_count = db.query(User).filter(User.group_id == group.id).count()
    
    return {
        "id": group.id,
        "group_id": group.group_id,
        "name": group.name,
        "invite_code": group.invite_code,
        "member_count": member_count,
        "created_at": group.created_at
    }

# ============= User Routes =============

@app.post("/api/users/join", response_model=UserResponse)
@limiter.limit("30/minute")
def join_group(request: Request, user: UserCreate, db: Session = Depends(get_db)):
    """Join a group with invite code and create user session"""
    
    # Find group by invite code
    group = db.query(Group).filter(
        Group.invite_code == user.group_invite_code
    ).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Group not found. Invalid invite code.")
    
    # Check if user with same display name exists in group
    existing_user = db.query(User).filter(
        and_(
            User.group_id == group.id,
            User.display_name == user.display_name
        )
    ).first()
    
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Display name already taken in this group"
        )
    
    # Create new user session
    session_token_plaintext = generate_session_token()
    session_token_hash = _hash_and_store_token(session_token_plaintext)
    session_expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_TOKEN_EXPIRY_DAYS)
    avatar_color = user.color_avatar or get_random_avatar_color()
    
    db_user = User(
        group_id=group.id,
        display_name=user.display_name,
        session_token=session_token_hash,  # Store hash
        session_token_expires_at=session_expires_at,  # Set expiry
        color_avatar=avatar_color
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return UserResponse(
        id=db_user.id,
        user_id=db_user.user_id,
        display_name=db_user.display_name,
        color_avatar=db_user.color_avatar,
        session_token=session_token_plaintext,  # Return plaintext to user (only time shown)
        created_at=db_user.created_at,
        answer_streak=db_user.answer_streak,
        longest_answer_streak=db_user.longest_answer_streak
    )

@app.get("/api/users/validate-session/{session_token}")
@limiter.limit("200/minute")
def validate_session(request: Request, session_token: str, db: Session = Depends(get_db)):
    """Validate user session token"""
    user = _get_user_by_session(session_token, db)
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    return {
        "valid": True,
        "user_id": user.user_id,
        "display_name": user.display_name,
        "group_id": user.group.group_id,
        "answer_streak": user.answer_streak,
        "longest_answer_streak": user.longest_answer_streak
    }

@app.get("/api/groups/{group_id}/members")
@limiter.limit("200/minute")
def get_group_members(request: Request, group_id: str, db: Session = Depends(get_db)):
    """Get all members in a group"""
    group = get_group_by_id(group_id, db)
    
    members = db.query(User).filter(User.group_id == group.id).all()
    
    return [
        {
            "user_id": m.user_id,
            "display_name": m.display_name,
            "color_avatar": m.color_avatar,
            "created_at": m.created_at,
            "answer_streak": m.answer_streak,
            "longest_answer_streak": m.longest_answer_streak
        }
        for m in members
    ]

# ============= Daily Question Routes =============

@app.post("/api/groups/{group_id}/questions", response_model=DailyQuestionResponse)
@limiter.limit("10/minute")
def create_daily_question(
    request: Request,
    group: Group = Depends(require_group_admin),
    question: DailyQuestionCreate = None,
    db: Session = Depends(get_db)
):
    """Create a new daily question (admin endpoint)"""
    
    # `group` is provided by the `require_group_admin` dependency and validated already
    
    # Check if question already exists for today
    today = datetime.now(timezone.utc).date()
    existing = db.query(DailyQuestion).filter(
        and_(
            DailyQuestion.group_id == group.id,
            func.date(DailyQuestion.question_date) == today
        )
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Question already exists for today")
    
    # Get or default to "Default" question set
    question_set = None
    if question.question_set_id:
        question_set = db.query(QuestionSet).filter(QuestionSet.set_id == question.question_set_id).first()
        if not question_set:
            raise HTTPException(status_code=404, detail="Question set not found")
    else:
        # Default to "Default" set
        question_set = db.query(QuestionSet).filter(QuestionSet.name == "Default").first()
        if not question_set:
            # Fallback to any public set
            question_set = db.query(QuestionSet).filter(QuestionSet.is_public == True).first()
    
    # Store the question set relationship (we'll track which set questions come from)
    # For now, we'll just log it; later we can add a column to DailyQuestion
    if question_set:
        logging.info(f"Creating question for group {group.group_id} from set '{question_set.name}'")
    
    members = _get_group_member_names(group, db)

    # Derive options based on question type
    if question.question_type == QuestionTypeEnum.MEMBER_CHOICE:
        if len(members) < 2:
            raise HTTPException(status_code=400, detail="Need at least two group members for member_choice")
        options_list = members
    elif question.question_type == QuestionTypeEnum.DUO_CHOICE:
        if len(members) < 2:
            raise HTTPException(status_code=400, detail="Need at least two group members for duo_choice")
        options_list = _generate_duos(members)
    elif question.question_type == QuestionTypeEnum.BINARY_VOTE:
        # Binary vote defaults to Yes/No
        options_list = ["Yes", "No"]
    elif question.question_type == QuestionTypeEnum.SINGLE_CHOICE:
        # Single choice uses provided options or defaults to members
        if question.option_a and question.option_b:
            options_list = [question.option_a, question.option_b]
        else:
            options_list = members if len(members) >= 2 else []
    else:  # FREE_TEXT
        options_list = []

    option_a = options_list[0] if options_list else None
    option_b = options_list[1] if len(options_list) > 1 else None

    db_question = DailyQuestion(
        group_id=group.id,
        question_text=question.question_text,
        option_a=option_a,
        option_b=option_b,
        options=json.dumps(options_list) if options_list else None,
        question_type=question.question_type,
        allow_multiple=question.allow_multiple
    )
    
    db.add(db_question)
    db.commit()
    db.refresh(db_question)
    
    options_list_resp = json.loads(db_question.options) if db_question.options else []
    
    return DailyQuestionResponse(
        id=db_question.id,
        question_id=db_question.question_id,
        question_text=db_question.question_text,
        question_type=db_question.question_type,
        options=options_list_resp,
        option_counts={},
        question_date=db_question.question_date,
        is_active=db_question.is_active,
        total_votes=0,
        allow_multiple=db_question.allow_multiple
    )


# ============= Question Set Endpoints =============


@app.post("/api/question-sets", response_model=QuestionSetResponse)
def create_question_set(
    _request: Request,
    payload: QuestionSetCreate,
    db: Session = Depends(get_db)
):
    """Create a new question set (contains templates)"""
    qs = QuestionSet(
        name=payload.name,
        description=payload.description,
        is_public=payload.is_public
    )
    db.add(qs)
    db.commit()
    db.refresh(qs)

    # attach templates if provided (template_ids are template_id strings)
    if payload.template_ids:
        for tid in payload.template_ids:
            tmpl = db.query(QuestionTemplate).filter(QuestionTemplate.template_id == tid).first()
            if tmpl:
                assoc = QuestionSetTemplate(question_set_id=qs.id, template_id=tmpl.id)
                db.add(assoc)
        db.commit()

    # build response
    templates = []
    for assoc in db.query(QuestionSetTemplate).filter(QuestionSetTemplate.question_set_id == qs.id).all():
        t = db.get(QuestionTemplate, assoc.template_id)
        if t:
            templates.append(QuestionTemplateResponse(
                template_id=t.template_id,
                category=t.category,
                question_text=t.question_text,
                option_a_template=t.option_a_template,
                option_b_template=t.option_b_template,
                question_type=t.question_type,
                allow_multiple=getattr(t, "allow_multiple", False),
                is_public=t.is_public,
                created_at=t.created_at
            ))

    return QuestionSetResponse(
        set_id=qs.set_id,
        name=qs.name,
        description=qs.description,
        is_public=qs.is_public,
        templates=templates,
        created_at=qs.created_at
    )


@app.get("/api/question-sets")
def list_public_question_sets(db: Session = Depends(get_db)):
    sets = db.query(QuestionSet).filter(QuestionSet.is_public == True).all()
    out = []
    for s in sets:
        templates = []
        for assoc in db.query(QuestionSetTemplate).filter(QuestionSetTemplate.question_set_id == s.id).all():
            t = db.get(QuestionTemplate, assoc.template_id)
            if t:
                templates.append({
                    "template_id": t.template_id,
                    "category": t.category,
                    "question_text": t.question_text,
                    "option_a_template": t.option_a_template,
                    "option_b_template": t.option_b_template,
                    "question_type": t.question_type.value if hasattr(t.question_type, 'value') else str(t.question_type),
                        "allow_multiple": getattr(t, "allow_multiple", False),
                    "is_public": t.is_public,
                    "created_at": t.created_at
                })
        out.append({
            "set_id": s.set_id,
            "name": s.name,
            "description": s.description,
            "is_public": s.is_public,
            "templates": templates,
            "created_at": s.created_at
        })
    return out


@app.get("/api/question-sets/{set_id}")
def get_question_set(set_id: str, db: Session = Depends(get_db)):
    qs = db.query(QuestionSet).filter(QuestionSet.set_id == set_id).first()
    if not qs:
        raise HTTPException(status_code=404, detail="Question set not found")
    templates = []
    for assoc in db.query(QuestionSetTemplate).filter(QuestionSetTemplate.question_set_id == qs.id).all():
        t = db.get(QuestionTemplate, assoc.template_id)
        if t:
            templates.append({
                "template_id": t.template_id,
                "category": t.category,
                "question_text": t.question_text,
                "option_a_template": t.option_a_template,
                "option_b_template": t.option_b_template,
                "question_type": t.question_type.value if hasattr(t.question_type, 'value') else str(t.question_type),
                "allow_multiple": getattr(t, "allow_multiple", False),
                "is_public": t.is_public,
                "created_at": t.created_at
            })
    return {
        "set_id": qs.set_id,
        "name": qs.name,
        "description": qs.description,
        "is_public": qs.is_public,
        "templates": templates,
        "created_at": qs.created_at
    }


@app.post("/api/groups/{group_id}/question-sets")
def assign_question_sets_to_group(
    payload: GroupAssignSetsRequest,
    group: Group = Depends(require_group_admin),
    db: Session = Depends(get_db)
):
    """Assign question sets to a group. Requires admin_token of the group in query param."""
    # `group` is validated by require_group_admin
    if payload.replace:
        db.query(GroupQuestionSet).filter(GroupQuestionSet.group_id == group.id).delete()
        db.commit()

    for set_uuid in payload.question_set_ids:
        qs = db.query(QuestionSet).filter(QuestionSet.set_id == set_uuid).first()
        if not qs:
            continue
        existing = db.query(GroupQuestionSet).filter(
            GroupQuestionSet.group_id == group.id,
            GroupQuestionSet.question_set_id == qs.id
        ).first()
        if existing:
            existing.is_active = True
        else:
            gq = GroupQuestionSet(group_id=group.id, question_set_id=qs.id, is_active=True)
            db.add(gq)
    db.commit()

    # return current group sets
    assigned = db.query(GroupQuestionSet).filter(GroupQuestionSet.group_id == group.id, GroupQuestionSet.is_active == True).all()
    result_sets = []
    for a in assigned:
        s = db.get(QuestionSet, a.question_set_id)
        if s:
            result_sets.append({
                "set_id": s.set_id,
                "name": s.name,
                "description": s.description,
                "is_public": s.is_public
            })
    return {"group_id": group.group_id, "question_sets": result_sets}


@app.get("/api/groups/{group_id}/question-sets", response_model=GroupQuestionSetsResponse)
def get_group_question_sets(group_id: str, db: Session = Depends(get_db)):
    group = get_group_by_id(group_id, db)
    assigned = db.query(GroupQuestionSet).filter(GroupQuestionSet.group_id == group.id, GroupQuestionSet.is_active == True).all()
    result_sets = []
    for a in assigned:
        s = db.get(QuestionSet, a.question_set_id)
        if s:
            # include templates
            templates = []
            for assoc in db.query(QuestionSetTemplate).filter(QuestionSetTemplate.question_set_id == s.id).all():
                t = db.get(QuestionTemplate, assoc.template_id)
                if t:
                    templates.append(QuestionTemplateResponse(
                        template_id=t.template_id,
                        category=t.category,
                        question_text=t.question_text,
                        option_a_template=t.option_a_template,
                        option_b_template=t.option_b_template,
                        question_type=t.question_type,
                        allow_multiple=getattr(t, "allow_multiple", False),
                        is_public=t.is_public,
                        created_at=t.created_at
                    ))
            result_sets.append(QuestionSetResponse(
                set_id=s.set_id,
                name=s.name,
                description=s.description,
                is_public=s.is_public,
                templates=templates,
                created_at=s.created_at
            ))
    return GroupQuestionSetsResponse(group_id=group.group_id, question_sets=result_sets)

@app.get("/api/groups/{group_id}/questions/today")
@limiter.limit("200/minute")
def get_todays_question(
    request: Request,
    group_id: str = Path(...),
    session_token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get today's question for a group"""
    
    group = get_group_by_id(group_id, db)
    
    today = datetime.now(timezone.utc).date()
    question = db.query(DailyQuestion).filter(
        and_(
            DailyQuestion.group_id == group.id,
            func.date(DailyQuestion.question_date) == today,
            DailyQuestion.is_active == True
        )
    ).first()
    
    if not question:
        raise HTTPException(status_code=404, detail="No question for today")
    
    options_list = json.loads(question.options) if question.options else []
    option_counts = _get_option_counts(question.id, db)
    total_votes = db.query(func.count(Vote.id)).filter(Vote.question_id == question.id).scalar() or 0
    
    # Get user's vote if authenticated
    user_vote = None
    user_streak = 0
    longest_streak = 0
    if session_token:
        user = _get_user_by_session(session_token, db)
        if user:
            user_vote = _get_user_vote(user.id, question.id, db)
            user_streak = user.answer_streak
            longest_streak = user.longest_answer_streak
    
    return DailyQuestionResponse(
        id=question.id,
        question_id=question.question_id,
        question_text=question.question_text,
        question_type=question.question_type,
        options=options_list,
        option_counts=option_counts,
        question_date=question.question_date,
        is_active=question.is_active,
        total_votes=total_votes,
        allow_multiple=question.allow_multiple,
        user_vote=user_vote,
        user_streak=user_streak,
        longest_streak=longest_streak
    )

# ============= Voting Routes =============

@app.post("/api/groups/{group_id}/questions/{question_id}/answer")
@limiter.limit("100/minute")
def submit_answer(
    request: Request,
    group_id: str = Path(...),
    question_id: str = Path(...),
    answer: AnswerSubmissionCreate = None,
    session_token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Submit an answer (binary, single-choice, or free-text) to a question"""
    
    if not session_token:
        raise HTTPException(status_code=401, detail="Session token required")
    
    user = _get_user_by_session(session_token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    group = get_group_by_id(group_id, db)
    
    if user.group_id != group.id:
        raise HTTPException(status_code=403, detail="User not in this group")
    
    question = db.query(DailyQuestion).filter(
        DailyQuestion.question_id == question_id
    ).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    options_list = json.loads(question.options) if question.options else []
    allow_multiple = bool(getattr(question, "allow_multiple", False))

    # Validate answer based on question type
    stored_answer: Optional[str] = None

    normalized_answers: list[str] = []

    if question.question_type == QuestionTypeEnum.FREE_TEXT:
        if not answer.text_answer:
            raise HTTPException(status_code=400, detail="Free text questions require a text answer")
    else:
        if answer.answer is None:
            raise HTTPException(status_code=400, detail="Answer is required")
        normalized_answers = _normalize_answer_submission(answer.answer, allow_multiple)
        if not normalized_answers:
            raise HTTPException(status_code=400, detail="Answer is required")
        if not allow_multiple and len(normalized_answers) != 1:
            raise HTTPException(status_code=400, detail="Only one selection allowed")
        if options_list:
            invalid = [a for a in normalized_answers if a not in options_list]
            if invalid:
                raise HTTPException(status_code=400, detail="Answer must be one of the available options")
        stored_answer = json.dumps(normalized_answers) if allow_multiple else normalized_answers[0]
    
    # Check if user already answered
    existing_vote = db.query(Vote).filter(
        and_(Vote.question_id == question.id, Vote.user_id == user.id)
    ).first()
    
    if existing_vote:
        # Update existing answer
        existing_vote.answer = stored_answer if question.question_type != QuestionTypeEnum.FREE_TEXT else answer.text_answer
        existing_vote.text_answer = answer.text_answer
        existing_vote.voted_at = datetime.now(timezone.utc)
    else:
        # Create new answer
        db_vote = Vote(
            question_id=question.id,
            user_id=user.id,
            answer=stored_answer if question.question_type != QuestionTypeEnum.FREE_TEXT else answer.text_answer,
            text_answer=answer.text_answer
        )
        db.add(db_vote)
        db.flush()
        
        # Update per-group streak
        _update_user_group_streak(user.id, group.id, db)
    
    db.commit()
    
    option_counts = _get_option_counts(question.id, db)
    total_votes = db.query(func.count(Vote.id)).filter(Vote.question_id == question.id).scalar() or 0
    vote_count_a = option_counts.get(options_list[0], 0) if options_list else 0
    vote_count_b = option_counts.get(options_list[1], 0) if len(options_list) > 1 else 0
    
    # Get user's current streak for this group
    streak = _get_user_group_streak(user.id, group.id, db)
    
    user_answer_value = answer.text_answer if question.question_type == QuestionTypeEnum.FREE_TEXT else (
        normalized_answers if allow_multiple else normalized_answers[0]
    )

    return {
        "success": True,
        "question_type": question.question_type.value,
        "vote_count_a": vote_count_a,
        "vote_count_b": vote_count_b,
        "total_votes": total_votes,
        "option_counts": option_counts,
        "options": options_list,
        "user_answer": user_answer_value,
        "current_streak": streak.current_streak,
        "longest_streak": streak.longest_streak
    }


@app.get("/api/groups/{group_id}/questions/history")
@limiter.limit("200/minute")
def get_question_history(
    request: Request,
    group_id: str = Path(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get historical questions for a group (paginated)"""
    
    group = get_group_by_id(group_id, db)
    
    # Get paginated questions ordered by date (most recent first)
    questions = db.query(DailyQuestion).filter(
        DailyQuestion.group_id == group.id
    ).order_by(
        DailyQuestion.question_date.desc()
    ).offset(skip).limit(limit).all()
    
    total_count = db.query(DailyQuestion).filter(
        DailyQuestion.group_id == group.id
    ).count()
    
    result = []
    for question in questions:
        options_list = json.loads(question.options) if question.options else []
        option_counts = _get_option_counts(question.id, db)
        vote_count_a = option_counts.get(options_list[0], 0) if options_list else 0
        vote_count_b = option_counts.get(options_list[1], 0) if len(options_list) > 1 else 0
        total_votes = db.query(func.count(Vote.id)).filter(Vote.question_id == question.id).scalar() or 0
        result.append({
            "question_id": question.question_id,
            "question_text": question.question_text,
            "question_type": question.question_type.value,
            "option_a": question.option_a,
            "option_b": question.option_b,
            "options": options_list,
            "option_counts": option_counts,
            "question_date": question.question_date,
            "is_active": question.is_active,
            "vote_count_a": vote_count_a,
            "vote_count_b": vote_count_b,
            "total_votes": total_votes,
            "allow_multiple": getattr(question, "allow_multiple", False)
        })
    
    return {
        "group_id": group_id,
        "total_count": total_count,
        "skip": skip,
        "limit": limit,
        "questions": result
    }

# ============= WebSocket Real-Time Endpoints =============

@app.websocket("/ws/groups/{group_id}/questions/{question_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    group_id: str,
    question_id: str,
    db: Session = Depends(get_db)
):
    """WebSocket connection for real-time updates"""
    
    await manager.connect(group_id, question_id, websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types
            if message.get("type") == "vote":
                # Update vote in database
                try:
                    group = get_group_by_id(group_id, db)
                except HTTPException:
                    group = None
                if group:
                    question = db.query(DailyQuestion).filter(
                        DailyQuestion.question_id == question_id
                    ).first()
                    if question:
                        user = _get_user_by_session(message.get("session_token"), db)
                        if user:
                            options_list = json.loads(question.options) if question.options else []
                            allow_multiple = bool(getattr(question, "allow_multiple", False))

                            stored_answer = None
                            normalized_answers: list[str] = []
                            text_answer = message.get("text_answer")

                            if question.question_type == QuestionTypeEnum.FREE_TEXT:
                                if not text_answer:
                                    await websocket.send_text(json.dumps({"error": "text_answer required"}))
                                    continue
                                stored_answer = text_answer
                            else:
                                raw_answer = message.get("answer")
                                normalized_answers = _normalize_answer_submission(raw_answer, allow_multiple)
                                if not normalized_answers:
                                    await websocket.send_text(json.dumps({"error": "answer required"}))
                                    continue
                                if options_list:
                                    invalid = [a for a in normalized_answers if a not in options_list]
                                    if invalid:
                                        await websocket.send_text(json.dumps({"error": "invalid option"}))
                                        continue
                                stored_answer = json.dumps(normalized_answers) if allow_multiple else normalized_answers[0]
                            
                            existing_vote = db.query(Vote).filter(
                                and_(
                                    Vote.question_id == question.id,
                                    Vote.user_id == user.id
                                )
                            ).first()
                            
                            if existing_vote:
                                existing_vote.answer = stored_answer
                                existing_vote.text_answer = text_answer
                                existing_vote.voted_at = datetime.now(timezone.utc)
                            else:
                                db_vote = Vote(
                                    question_id=question.id,
                                    user_id=user.id,
                                    answer=stored_answer,
                                    text_answer=text_answer
                                )
                                db.add(db_vote)
                            
                            db.commit()
                            
                            # Get updated counts
                            option_counts = _get_option_counts(question.id, db)
                            total_votes = db.query(func.count(Vote.id)).filter(Vote.question_id == question.id).scalar() or 0
                            
                            # Broadcast to all users
                            await manager.broadcast_update(group_id, question_id, {
                                "option_counts": option_counts,
                                "total_votes": total_votes,
                                "allow_multiple": allow_multiple,
                                "options": options_list,
                                "user": {
                                    "display_name": user.display_name,
                                    "voted": text_answer if question.question_type == QuestionTypeEnum.FREE_TEXT else (normalized_answers if allow_multiple else normalized_answers[0])
                                }
                            })
            
            elif message.get("type") == "ping":
                await websocket.send_text(json.dumps({
                    "type": "pong",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }))
    
    except WebSocketDisconnect:
        manager.disconnect(group_id, question_id, websocket)
    except Exception:
        logging.exception("WebSocket handler error")
        manager.disconnect(group_id, question_id, websocket)

# ============= Admin Routes =============

@app.get("/api/admin/groups/{group_id}/leaderboard")
@limiter.limit("60/minute")
def get_leaderboard(
    request: Request,
    group: Group = Depends(require_group_admin),
    db: Session = Depends(get_db)
):
    """Get group leaderboard by answer streak (admin only)"""
    members = db.query(User).filter(User.group_id == group.id).all()
    leaderboard = sorted(
        members,
        key=lambda x: (x.answer_streak, x.longest_answer_streak),
        reverse=True
    )
    return [
        {
            "display_name": m.display_name,
            "color_avatar": m.color_avatar,
            "answer_streak": m.answer_streak,
            "longest_answer_streak": m.longest_answer_streak
        }
        for m in leaderboard
    ]


# Member-accessible leaderboard (session-token based)
@app.get("/api/groups/{group_id}/leaderboard")
@limiter.limit("200/minute")
def get_leaderboard_member(
    request: Request,
    group_id: str = Path(...),
    session_token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Get group leaderboard by answer streak (any member with a valid session).

    Auth: Requires a valid `session_token` for a user in the specified group.
    """
    if not session_token:
        raise HTTPException(status_code=401, detail="Session token required")

    group = get_group_by_id(group_id, db)

    user = _get_user_by_session(session_token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    if user.group_id != group.id:
        raise HTTPException(status_code=403, detail="User not in this group")

    members = db.query(User).filter(User.group_id == group.id).all()
    leaderboard = sorted(
        members,
        key=lambda x: (x.answer_streak, x.longest_answer_streak),
        reverse=True,
    )
    return [
        {
            "display_name": m.display_name,
            "color_avatar": m.color_avatar,
            "answer_streak": m.answer_streak,
            "longest_answer_streak": m.longest_answer_streak,
        }
        for m in leaderboard
    ]


@app.get("/api/admin/groups/{group_id}/question-status")
@limiter.limit("60/minute")
def get_question_status(
    request: Request,
    group: Group = Depends(require_group_admin),
    db: Session = Depends(get_db)
):
    """Get question exhaustion status for a group (admin only)"""
    # Get available question templates for this group
    assigned = db.query(GroupQuestionSet).filter(
        GroupQuestionSet.group_id == group.id,
        GroupQuestionSet.is_active == True
    ).all()
    available_templates = set()
    for a in assigned:
        s = db.get(QuestionSet, a.question_set_id)
        if s:
            for assoc in db.query(QuestionSetTemplate).filter(QuestionSetTemplate.question_set_id == s.id).all():
                available_templates.add(assoc.template_id)
    
    # Fallback to public templates if none assigned
    if not available_templates:
        public_templates = db.query(QuestionTemplate).filter(QuestionTemplate.is_public == True).all()
        available_templates = {t.id for t in public_templates}
    
    total_available = len(available_templates)
    
    # Get used templates
    used = db.query(DailyQuestion.template_id).filter(
        DailyQuestion.group_id == group.id,
        DailyQuestion.template_id.isnot(None)
    ).distinct().all()
    used_templates = {t[0] for t in used}
    used_count = len(used_templates)
    
    # Check if exhausted
    exhausted = used_count >= total_available
    
    # Get count of questions created
    question_count = db.query(DailyQuestion).filter(
        DailyQuestion.group_id == group.id
    ).count()
    
    return {
        "group_id": group.group_id,
        "total_available_templates": total_available,
        "used_templates_count": used_count,
        "exhausted": exhausted,
        "total_questions_created": question_count,
        "message": "All questions have been used. Cycle will reset on next question." if exhausted else "Questions available"
    }


@app.post("/api/admin/groups/{group_id}/reset-question-cycle")
@limiter.limit("10/minute")
def reset_question_cycle(
    request: Request,
    group: Group = Depends(require_group_admin),
    db: Session = Depends(get_db)
):
    """Reset question cycle by clearing used questions (admin only)"""
    # Delete all questions for this group to reset the cycle
    deleted_count = db.query(DailyQuestion).filter(
        DailyQuestion.group_id == group.id
    ).delete()
    db.commit()
    
    logging.info(f"Question cycle reset for group {group.group_id}. Deleted {deleted_count} questions.")
    
    return {
        "group_id": group.group_id,
        "message": f"Question cycle reset. {deleted_count} questions deleted.",
        "deleted_count": deleted_count
    }


@app.post("/api/admin/groups/{group_id}/regenerate-today")
@limiter.limit("10/minute")
def regenerate_todays_question(
    request: Request,
    group: Group = Depends(require_group_admin),
    db: Session = Depends(get_db),
):
    """Delete today's question (if present) and create a new one from current sets."""
    today = datetime.now(timezone.utc).date()

    # Delete today's existing question if any
    db.query(DailyQuestion).filter(
        and_(DailyQuestion.group_id == group.id, func.date(DailyQuestion.question_date) == today)
    ).delete()
    db.commit()

    # Create new question
    dq = _create_today_question_for_group(db, group)
    if not dq:
        raise HTTPException(status_code=400, detail="Unable to generate today's question (insufficient members or no templates)")

    options_list = json.loads(dq.options) if dq.options else []
    option_counts = _get_option_counts(dq.id, db)
    total_votes = db.query(func.count(Vote.id)).filter(Vote.question_id == dq.id).scalar() or 0

    return DailyQuestionResponse(
        id=dq.id,
        question_id=dq.question_id,
        question_text=dq.question_text,
        question_type=dq.question_type,
        options=options_list,
        option_counts=option_counts,
        question_date=dq.question_date,
        is_active=dq.is_active,
        total_votes=total_votes,
    )

# ==================== ADMIN ENDPOINTS ====================

from admin_auth import (
    authenticate_admin, verify_admin_totp, generate_temp_token, verify_temp_token,
    generate_access_token, generate_refresh_token, get_current_admin, get_admin_from_refresh_token,
    record_successful_login, log_admin_action, AdminAuthError, get_totp_secret, get_totp_uri,
    hash_password, verify_password
)
from admin_schemas import (
    AdminLoginRequest, AdminLoginResponse, AdminTOTPVerifyRequest, AdminTokenResponse,
    AdminRefreshRequest, AdminProfileResponse, AdminDashboardStats, UserSuspensionRequest,
    TokenRecoveryRequest, TokenRecoveryResponse, AuditLogResponse,
    ChangePasswordRequest, TOTPSetupStartResponse, TOTPSetupVerifyRequest
)
from typing import Union


# ==================== ADMIN HELPER FUNCTIONS ====================

def extract_client_ip(request: Request, header_ip: Optional[str] = None) -> str:
    """Extract real client IP from request, handling proxies and Docker."""
    # First try X-Forwarded-For header (set by reverse proxies/nginx)
    if header_ip:
        # Take the first IP if multiple are present
        ip = header_ip.split(',')[0].strip()
        return ip
    
    # Then try to get from request object
    if request and request.client:
        ip = request.client.host
        # Map Docker internal IPs to "docker" for audit logs in development
        if ip and ip.startswith("172."):
            return "docker"
        return ip
    
    return "unknown"


def log_admin_login(admin: "AdminUser", ip_address: str, reason: str, db: Session):
    """Helper to log admin login actions (reduces duplication)"""
    log_admin_action(
        admin_id=admin.id,
        action="LOGIN",
        target_type="ADMIN_USER",
        target_id=admin.id,
        before_state=None,
        after_state={"last_login_ip": ip_address},
        ip_address=ip_address,
        reason=reason,
        db=db
    )


def log_admin_totp_change(admin: "AdminUser", action: str, enabled: bool, ip_address: str, db: Session):
    """Helper to log TOTP enable/disable actions"""
    log_admin_action(
        admin_id=admin.id,
        action=action,
        target_type="ADMIN_USER",
        target_id=admin.id,
        before_state={"totp_enabled": not enabled},
        after_state={"totp_enabled": enabled},
        ip_address=ip_address,
        reason=f"Admin {'enabled' if enabled else 'disabled'} 2FA",
        db=db
    )


@limiter.limit("5/minute")
@app.post("/api/admin/login", response_model=Union[AdminLoginResponse, AdminTokenResponse])
async def admin_login(request: AdminLoginRequest, request_obj: Request, x_forwarded_for: str = Header(None), db: Session = Depends(get_db)):
    """
    Step 1: Admin login with username and password.
    Returns temporary token for 2FA verification if enabled, otherwise returns tokens.
    Rate limited to prevent brute force attacks.
    """
    # Get client IP (X-Forwarded-For for reverse proxy, fallback to request IP)
    ip_address = extract_client_ip(request_obj, x_forwarded_for)
    
    try:
        admin = authenticate_admin(request.username, request.password, ip_address, db)
    except AdminAuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    
    # Debug: Log the totp_enabled value
    print(f"[DEBUG] Admin {admin.username} (id={admin.id}): totp_enabled={admin.totp_enabled}, totp_secret={admin.totp_secret is not None}")
    
    # If TOTP not enabled yet, login immediately and return tokens
    if not admin.totp_enabled:
        record_successful_login(admin, ip_address, db)
        log_admin_login(admin, ip_address, "Password-only login (TOTP not enabled)", db)
        access_token = generate_access_token(admin.id)
        refresh_token = generate_refresh_token(admin.id)
        return AdminTokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=60 * 60
        )

    # Otherwise, generate temporary token for 2FA step
    temp_token = generate_temp_token(admin.id)
    return AdminLoginResponse(temp_token=temp_token)


@limiter.limit("10/minute")
@app.post("/api/admin/2fa", response_model=AdminTokenResponse)
async def admin_2fa_verify(request: AdminTOTPVerifyRequest, request_obj: Request, x_forwarded_for: str = Header(None), db: Session = Depends(get_db)):
    """
    Step 2: Verify TOTP code and receive JWT tokens.
    """
    ip_address = extract_client_ip(request_obj, x_forwarded_for)
    
    try:
        admin_id = verify_temp_token(request.temp_token)
    except AdminAuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    
    admin = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found")
    
    # Verify TOTP code
    try:
        if not verify_admin_totp(admin, request.totp_code):
            raise AdminAuthError("Invalid TOTP code")
    except AdminAuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    
    # Record successful login and reset attempt counter
    record_successful_login(admin, ip_address, db)
    log_admin_login(admin, ip_address, "Successful 2FA login", db)
    
    # Generate tokens
    access_token = generate_access_token(admin.id)
    refresh_token = generate_refresh_token(admin.id)
    
    return AdminTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=60 * 60  # 60 minutes in seconds
    )


@app.post("/api/admin/refresh", response_model=AdminTokenResponse)
async def admin_refresh_token(request: AdminRefreshRequest, db: Session = Depends(get_db)):
    """
    Refresh access token using refresh token.
    """
    try:
        admin = get_admin_from_refresh_token(request.refresh_token, db)
    except HTTPException:
        raise
    
    # Generate new access token
    access_token = generate_access_token(admin.id)
    
    return AdminTokenResponse(
        access_token=access_token,
        refresh_token=request.refresh_token,  # Return same refresh token
        expires_in=60 * 60
    )


@app.get("/api/admin/profile", response_model=AdminProfileResponse)
async def get_admin_profile(admin: AdminUser = Depends(get_current_admin)):
    """
    Get current admin's profile information.
    """
    return AdminProfileResponse(
        id=admin.id,
        username=admin.username,
        email=getattr(admin, "email", None),
        is_active=admin.is_active,
        totp_configured=admin.totp_secret is not None,
        created_at=admin.created_at,
        last_login_ip=admin.last_login_ip
    )


# ===== Account management: change password =====
@app.post("/api/admin/account/change-password")
async def change_admin_password(
    request: ChangePasswordRequest,
    admin: AdminUser = Depends(get_current_admin),
    request_obj: Request = None,
    x_forwarded_for: str = Header(None),
    db: Session = Depends(get_db)
):
    from sqlalchemy import text
    
    ip_address = extract_client_ip(request_obj, x_forwarded_for) if request_obj else "unknown"
    
    # Verify current password
    if not verify_password(request.current_password, admin.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    # Generate new hash
    new_hash = hash_password(request.new_password)
    
    # Use direct SQL update to ensure it commits properly
    try:
        db.execute(
            text("UPDATE admin_users SET password_hash = :new_hash WHERE id = :admin_id"),
            {"new_hash": new_hash, "admin_id": admin.id}
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update password")
    
    log_admin_action(
        admin_id=admin.id,
        action="PASSWORD_CHANGE",
        target_type="ADMIN_USER",
        target_id=admin.id,
        before_state=None,
        after_state={"password_changed": True},
        ip_address=ip_address,
        reason="Admin changed own password",
        db=db
    )
    return {"message": "Password updated successfully"}


# ===== Account management: TOTP setup (initiate and verify) =====
@app.post("/api/admin/account/totp/setup-initiate", response_model=TOTPSetupStartResponse)
async def totp_setup_initiate(
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    from sqlalchemy import text
    
    if admin.totp_secret:
        raise HTTPException(status_code=400, detail="TOTP already configured")
    
    # Generate a new secret and store temporarily in temp_token field
    secret = get_totp_secret()
    
    # Use raw SQL to ensure it commits
    try:
        db.execute(
            text("UPDATE admin_users SET temp_token = :secret WHERE id = :admin_id"),
            {"secret": secret, "admin_id": admin.id}
        )
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to initiate TOTP setup")
    
    provisioning_uri = get_totp_uri(admin.username, secret)
    return TOTPSetupStartResponse(secret=secret, provisioning_uri=provisioning_uri)


@app.post("/api/admin/account/totp/setup-verify")
async def totp_setup_verify(
    request: TOTPSetupVerifyRequest,
    admin: AdminUser = Depends(get_current_admin),
    request_obj: Request = None,
    x_forwarded_for: str = Header(None),
    db: Session = Depends(get_db)
):
    import pyotp
    
    ip_address = extract_client_ip(request_obj, x_forwarded_for) if request_obj else "unknown"
    if admin.totp_secret:
        raise HTTPException(status_code=400, detail="TOTP already configured")
    if not admin.temp_token:
        raise HTTPException(status_code=400, detail="No TOTP setup session. Initiate first.")
    
    # Store the secret before verification
    totp_secret = admin.temp_token
    
    # Verify provided code against pending secret
    if not pyotp.TOTP(totp_secret).verify(request.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")
    
    # Query the admin fresh from the database using the same session
    try:
        admin_id = admin.id
        db_admin = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
        
        if not db_admin:
            raise Exception("Admin user not found in database")
        
        # Update using ORM
        db_admin.totp_secret = totp_secret
        db_admin.totp_enabled = True
        db_admin.temp_token = None
        
        # Commit the changes
        db.commit()
        
        # Verify the update worked by re-querying
        db.refresh(db_admin)
        
        if not db_admin.totp_enabled:
            raise Exception("TOTP enabled flag was not persisted to database")
            
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to configure TOTP: {str(e)}")
    
    log_admin_action(
        admin_id=admin.id,
        action="TOTP_CONFIGURED",
        target_type="ADMIN_USER",
        target_id=admin.id,
        before_state=None,
        after_state={"totp_configured": True},
        ip_address=ip_address,
        reason="Admin enabled TOTP",
        db=db
    )
    return {"message": "TOTP configured successfully"}


@app.post("/api/admin/logout")
async def admin_logout(admin: AdminUser = Depends(get_current_admin), request_obj: Request = None, x_forwarded_for: str = Header(None), db: Session = Depends(get_db)):
    """
    Admin logout. Client should discard tokens.
    Logs the logout action.
    """
    ip_address = extract_client_ip(request_obj, x_forwarded_for) if request_obj else "unknown"
    
    log_admin_action(
        admin_id=admin.id,
        action="LOGOUT",
        target_type="ADMIN_USER",
        target_id=admin.id,
        before_state=None,
        after_state=None,
        ip_address=ip_address,
        reason="Admin logout",
        db=db
    )
    
    return {"message": "Logged out successfully"}


@app.post("/api/admin/totp/setup")
async def setup_totp(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    """
    Generate a new TOTP secret for the admin.
    Returns the secret and provisioning URI for QR code generation.
    """
    from admin_auth import generate_totp_secret
    import pyotp
    
    totp_secret = generate_totp_secret()
    totp = pyotp.TOTP(totp_secret)
    provisioning_uri = totp.provisioning_uri(
        name=admin.username,
        issuer_name="dontAskUs"
    )
    
    return {
        "totp_secret": totp_secret,
        "provisioning_uri": provisioning_uri,
        "message": "Scan the QR code with your authenticator app or enter the secret manually"
    }


@app.post("/api/admin/totp/enable")
async def enable_totp(request: dict, admin: AdminUser = Depends(get_current_admin), ip: str = Header(None), db: Session = Depends(get_db)):
    """
    Enable TOTP after verifying the code matches the secret.
    Requires the admin to provide the totp_secret and a valid verification code.
    """
    totp_secret = request.get("totp_secret")
    verification_code = request.get("verification_code")
    
    if not totp_secret or not verification_code:
        raise HTTPException(status_code=400, detail="Missing totp_secret or verification_code")
    
    # Verify the code with the provided secret
    import pyotp
    totp = pyotp.TOTP(totp_secret)
    if not totp.verify(verification_code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid verification code")
    
    # Store the secret and enable TOTP
    admin.totp_secret = totp_secret
    admin.totp_enabled = True
    db.commit()
    
    ip_address = ip or "unknown"
    log_admin_totp_change(admin, "TOTP_ENABLED", True, ip_address, db)
    
    return {"message": "TOTP enabled successfully"}


@app.post("/api/admin/totp/disable")
async def disable_totp(request: dict, admin: AdminUser = Depends(get_current_admin), ip: str = Header(None), db: Session = Depends(get_db)):
    """
    Disable TOTP (requires password verification for security).
    """
    password = request.get("password")
    
    if not password:
        raise HTTPException(status_code=400, detail="Password required to disable TOTP")
    
    from admin_auth import verify_password
    if not verify_password(password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid password")
    
    # Disable TOTP
    admin.totp_secret = None
    admin.totp_enabled = False
    db.commit()
    
    ip_address = ip or "unknown"
    log_admin_totp_change(admin, "TOTP_DISABLED", False, ip_address, db)
    
    return {"message": "TOTP disabled successfully"}


@app.get("/api/admin/totp/status")
async def get_totp_status(admin: AdminUser = Depends(get_current_admin)):
    """
    Get the current TOTP status for the admin.
    """
    return {
        "totp_enabled": admin.totp_enabled,
        "totp_configured": admin.totp_secret is not None
    }


@app.get("/api/admin/dashboard/stats", response_model=AdminDashboardStats)
async def get_dashboard_stats(admin: AdminUser = Depends(get_current_admin), db: Session = Depends(get_db)):
    """
    Get admin dashboard statistics.
    """
    # Get counts
    total_groups = db.query(func.count(Group.id)).scalar() or 0
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_sets = db.query(func.count(QuestionSet.id)).scalar() or 0
    public_sets = db.query(func.count(QuestionSet.id)).filter(QuestionSet.is_public == True).scalar() or 0
    private_sets = total_sets - public_sets
    
    # Get recent audit logs (last 10)
    audit_logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(10).all()
    audit_logs_response = [
        AuditLogResponse.model_validate(log) for log in audit_logs
    ]
    
    # Count active sessions in last 24 hours
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    active_sessions = db.query(func.count(AuditLog.id)).filter(
        and_(
            AuditLog.action == "LOGIN",
            AuditLog.timestamp >= yesterday
        )
    ).scalar() or 0
    
    return AdminDashboardStats(
        total_groups=total_groups,
        total_users=total_users,
        total_question_sets=total_sets,
        public_sets=public_sets,
        private_sets=private_sets,
        active_sessions_today=active_sessions,
        recent_audit_logs=audit_logs_response
    )


@app.get("/api/admin/audit-logs")
async def get_audit_logs(
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """
    Get paginated audit logs.
    """
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).offset(offset).all()
    total = db.query(func.count(AuditLog.id)).scalar()
    
    return {
        "logs": [AuditLogResponse.model_validate(log) for log in logs],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.get("/api/admin/users")
async def list_all_users(
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    suspended_only: bool = False
):
    """
    List all users with optional filtering for suspended users.
    """
    query = db.query(User)
    
    if suspended_only:
        query = query.filter(User.is_suspended == True)
    
    total = query.count()
    users = query.order_by(User.created_at.desc()).limit(limit).offset(offset).all()
    
    return {
        "users": [
            {
                "id": u.id,
                "user_id": u.user_id,
                "display_name": u.display_name,
                "group_id": u.group_id,
                "group_name": u.group.name if u.group else None,
                "color_avatar": u.color_avatar,
                "created_at": u.created_at,
                "answer_streak": u.answer_streak,
                "longest_answer_streak": u.longest_answer_streak,
                "last_answer_date": u.last_answer_date,
                "session_token_expires_at": u.session_token_expires_at,
                "is_suspended": u.is_suspended,
                "suspension_reason": u.suspension_reason,
                "last_known_ip": str(u.last_known_ip) if u.last_known_ip else None
            }
            for u in users
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.put("/api/admin/users/{user_id}/suspension")
async def update_user_suspension(
    user_id: int,
    request: UserSuspensionRequest,
    admin: AdminUser = Depends(get_current_admin),
    ip: str = Header(None),
    db: Session = Depends(get_db)
):
    """
    Suspend or unsuspend a user.
    """
    ip_address = ip or "unknown"
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    before_state = {
        "is_suspended": user.is_suspended,
        "suspension_reason": user.suspension_reason
    }
    
    user.is_suspended = request.is_suspended
    user.suspension_reason = request.suspension_reason if request.is_suspended else None
    db.commit()
    
    after_state = {
        "is_suspended": user.is_suspended,
        "suspension_reason": user.suspension_reason
    }
    
    # Log action
    log_admin_action(
        admin_id=admin.id,
        action="UPDATE_USER_SUSPENSION" if request.is_suspended else "UNSUSPEND_USER",
        target_type="USER",
        target_id=user_id,
        before_state=before_state,
        after_state=after_state,
        ip_address=ip_address,
        reason=request.suspension_reason,
        db=db
    )
    
    return {"message": "User suspension status updated", "user_id": user_id}


@app.post("/api/admin/users/{user_id}/recover-token")
async def recover_user_token(
    user_id: int,
    request: TokenRecoveryRequest,
    admin: AdminUser = Depends(get_current_admin),
    ip: str = Header(None),
    db: Session = Depends(get_db)
):
    """
    Generate a new session token for a user (for account recovery).
    """
    ip_address = ip or "unknown"
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Generate new token
    new_token_plaintext = generate_session_token()
    new_token_hash = _hash_and_store_token(new_token_plaintext)
    
    user.session_token = new_token_hash
    user.session_token_expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_TOKEN_EXPIRY_DAYS)
    db.commit()
    
    # Log action
    log_admin_action(
        admin_id=admin.id,
        action="RECOVER_USER_TOKEN",
        target_type="USER",
        target_id=user_id,
        before_state=None,
        after_state={"token_regenerated": True},
        ip_address=ip_address,
        reason=request.reason,
        db=db
    )
    
    return TokenRecoveryResponse(
        session_token=new_token_plaintext,
        message=f"New session token generated for user {user.display_name}"
    )


@app.get("/api/admin/groups")
async def list_all_groups(
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """
    List all groups with member counts.
    """
    groups = db.query(Group).order_by(Group.created_at.desc()).limit(limit).offset(offset).all()
    total = db.query(func.count(Group.id)).scalar()
    
    group_list = []
    for g in groups:
        member_count = db.query(func.count(User.id)).filter(User.group_id == g.id).scalar() or 0
        group_list.append({
            "id": g.id,
            "group_id": g.group_id,
            "name": g.name,
            "invite_code": g.invite_code,
            "created_by": g.creator_id,
            "created_at": g.created_at,
            "updated_at": g.updated_at,
            "member_count": member_count,
            "total_sets_created": g.total_sets_created or 0,
            "instance_admin_notes": g.instance_admin_notes
        })
    
    return {
        "groups": group_list,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.put("/api/admin/groups/{group_id}/notes")
async def update_group_notes(
    group_id: int,
    request: dict,
    admin: AdminUser = Depends(get_current_admin),
    ip: str = Header(None),
    db: Session = Depends(get_db)
):
    """
    Update instance admin notes for a group.
    """
    ip_address = ip or "unknown"
    
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    notes = request.get("notes", "")
    before_state = {"instance_admin_notes": group.instance_admin_notes}
    
    group.instance_admin_notes = notes
    db.commit()
    
    after_state = {"instance_admin_notes": group.instance_admin_notes}
    
    log_admin_action(
        admin_id=admin.id,
        action="UPDATE_GROUP_NOTES",
        target_type="GROUP",
        target_id=group_id,
        before_state=before_state,
        after_state=after_state,
        ip_address=ip_address,
        reason="Admin updated group notes",
        db=db
    )
    
    return {"message": "Group notes updated", "group_id": group_id}


@app.get("/api/admin/question-sets")
async def list_all_question_sets(
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    public_only: bool = False,
    private_only: bool = False
):
    """
    List all question sets with filtering options.
    """
    query = db.query(QuestionSet)
    
    if public_only:
        query = query.filter(QuestionSet.is_public == True)
    elif private_only:
        query = query.filter(QuestionSet.is_public == False)
    
    total = query.count()
    sets = query.order_by(QuestionSet.created_at.desc()).limit(limit).offset(offset).all()
    
    set_list = []
    for qs in sets:
        template_count = db.query(func.count(QuestionSetTemplate.id)).filter(
            QuestionSetTemplate.question_set_id == qs.id
        ).scalar() or 0
        set_list.append({
            "id": qs.id,
            "name": qs.name,
            "is_public": qs.is_public,
            "creator_id": qs.creator_id,
            "usage_count": qs.usage_count or 0,
            "created_at": qs.created_at,
            "question_count": template_count
        })
    
    return {
        "sets": set_list,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.get("/api/admin/question-sets/{set_id}/questions")
async def get_admin_question_set_questions(
    set_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Get all questions in a question set (admin only).
    """
    question_set = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()
    if not question_set:
        raise HTTPException(status_code=404, detail="Question set not found")
    
    # Fetch templates associated with this set
    templates = (
        db.query(QuestionTemplate)
        .join(QuestionSetTemplate, QuestionSetTemplate.template_id == QuestionTemplate.id)
        .filter(QuestionSetTemplate.question_set_id == set_id)
        .order_by(QuestionTemplate.created_at.asc())
        .all()
    )
    
    questions = []
    for t in templates:
        opts: list[str] = []
        if t.question_type == QuestionTypeEnum.BINARY_VOTE:
            opts = [o for o in [t.option_a_template, t.option_b_template] if o]
        questions.append({
            "id": t.id,
            "template_id": t.template_id,
            "question_text": t.question_text,
            "type": t.question_type.value if hasattr(t.question_type, "value") else t.question_type,
            "options": opts,
            "allow_multiple": getattr(t, "allow_multiple", False)
        })
    
    return {
        "set_id": set_id,
        "questions": questions
    }


# ==================== GROUP CREATOR ENDPOINTS ====================
# Endpoints for group creators to manage their private question sets (max 5 per group)

@app.post("/api/groups/{group_id}/question-sets/private")
async def create_private_question_set(
    group_id: int,
    request: dict,
    session_token: str = Header(None),
    db: Session = Depends(get_db)
):
    """
    Create a private question set for a group.
    Only group creator can use this endpoint.
    Maximum 5 private sets per group.
    
    Request body:
    {
        "name": "My Custom Questions",
        "description": "Optional description",
        "questions": [
            {
                "text": "Question text?",
                "question_type": "binary_vote",
                "options": ["Yes", "No"]
            }
        ]
    }
    """
    # Verify user and get session
    user = db.query(User).filter(
        and_(User.group_id == group_id, User.session_token == hash_token(session_token))
    ).first()
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session token")
    
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Check if user is group creator
    if group.created_by != user.email:
        raise HTTPException(status_code=403, detail="Only group creator can create private sets")
    
    # Check set limit (max 5 private sets per group)
    existing_sets = db.query(func.count(GroupCustomSet.id)).filter(
        GroupCustomSet.group_id == group_id
    ).scalar() or 0
    
    if existing_sets >= 5:
        raise HTTPException(
            status_code=400,
            detail="Maximum 5 private question sets per group reached"
        )
    
    # Validate request
    name = request.get("name", "").strip()
    if not name or len(name) < 3:
        raise HTTPException(status_code=400, detail="Set name must be at least 3 characters")
    
    if len(name) > 200:
        raise HTTPException(status_code=400, detail="Set name cannot exceed 200 characters")
    
    questions = request.get("questions", [])
    if not questions:
        raise HTTPException(status_code=400, detail="At least one question is required")
    
    if len(questions) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 questions per set")
    
    # Create question set
    question_set = QuestionSet(
        name=name,
        is_public=False,
        creator_id=user.id,
        created_by_group_id=group_id,
        usage_count=0,
        created_at=datetime.now(timezone.utc)
    )
    db.add(question_set)
    db.flush()  # Get the set ID
    
    # Create question templates for this set
    for idx, q in enumerate(questions):
        q_text = q.get("text", "").strip()
        q_type = q.get("question_type", "binary_vote")
        options = q.get("options", [])
        
        if not q_text:
            raise HTTPException(status_code=400, detail=f"Question {idx + 1}: text is required")
        
        # Validate question type
        valid_types = ["binary_vote", "single_choice", "free_text", "member_choice", "duo_choice"]
        if q_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Question {idx + 1}: invalid question_type. Must be one of {valid_types}"
            )
        
        # Validate options for choice-based questions
        if q_type in ["single_choice"] and not options:
            raise HTTPException(
                status_code=400,
                detail=f"Question {idx + 1}: options required for single_choice"
            )
        
        template = QuestionTemplate(
            text=q_text,
            question_type=QuestionTypeEnum[q_type.upper()],
            set_id=question_set.id
        )
        db.add(template)
    
    # Track this as a group custom set
    custom_set = GroupCustomSet(
        set_id=question_set.id,
        group_id=group_id,
        creator_user_id=user.id,
        created_at=datetime.now(timezone.utc)
    )
    db.add(custom_set)
    
    # Update group's total sets created count
    group.total_sets_created = (group.total_sets_created or 0) + 1
    
    db.commit()
    
    return {
        "message": "Private question set created successfully",
        "set_id": question_set.id,
        "name": question_set.name,
        "question_count": len(questions),
        "is_public": False
    }


@app.get("/api/groups/{group_id}/question-sets/my")
async def list_group_creator_sets(
    group_id: int,
    session_token: str = Header(None),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """
    List all private question sets created by the group creator for this group.
    Only group creator can access this endpoint.
    """
    # Verify user and get session
    user = db.query(User).filter(
        and_(User.group_id == group_id, User.session_token == hash_token(session_token))
    ).first()
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session token")
    
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Check if user is group creator
    if group.created_by != user.email:
        raise HTTPException(status_code=403, detail="Only group creator can view their sets")
    
    # Get custom sets
    custom_sets = db.query(GroupCustomSet).filter(
        GroupCustomSet.group_id == group_id
    ).all()
    
    set_ids = [cs.set_id for cs in custom_sets]
    
    if not set_ids:
        return {
            "sets": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "max_sets": 5,
            "current_count": 0
        }
    
    # Get question sets with pagination
    total = db.query(func.count(QuestionSet.id)).filter(
        QuestionSet.id.in_(set_ids)
    ).scalar()
    
    sets = db.query(QuestionSet).filter(
        QuestionSet.id.in_(set_ids)
    ).order_by(QuestionSet.created_at.desc()).limit(limit).offset(offset).all()
    
    set_list = []
    for qs in sets:
        template_count = db.query(func.count(QuestionSetTemplate.id)).filter(
            QuestionSetTemplate.question_set_id == qs.id
        ).scalar() or 0
        
        set_list.append({
            "id": qs.id,
            "name": qs.name,
            "question_count": template_count,
            "usage_count": qs.usage_count or 0,
            "is_public": qs.is_public,
            "created_at": qs.created_at
        })
    
    return {
        "sets": set_list,
        "total": total,
        "limit": limit,
        "offset": offset,
        "max_sets": 5,
        "current_count": len(custom_sets)
    }


@app.get("/api/groups/{group_id}/question-sets/{set_id}")
async def get_question_set_details(
    group_id: int,
    set_id: int,
    session_token: str = Header(None),
    db: Session = Depends(get_db)
):
    """
    Get details of a question set including all templates.
    Only group creator can view their private sets.
    """
    # Verify user and get session
    user = db.query(User).filter(
        and_(User.group_id == group_id, User.session_token == hash_token(session_token))
    ).first()
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session token")
    
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Get the set
    question_set = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()
    if not question_set:
        raise HTTPException(status_code=404, detail="Question set not found")
    
    # Check if this is a private set from this group
    if not question_set.is_public:
        custom_set = db.query(GroupCustomSet).filter(
            and_(GroupCustomSet.set_id == set_id, GroupCustomSet.group_id == group_id)
        ).first()
        
        if not custom_set:
            raise HTTPException(status_code=403, detail="Access denied to this question set")
        
        # Check if user is group creator
        if group.created_by != user.email:
            raise HTTPException(status_code=403, detail="Only group creator can view private sets")
    
    # Get templates
    templates = db.query(QuestionTemplate).filter(
        QuestionTemplate.set_id == set_id
    ).all()
    
    templates_list = [
        {
            "id": t.id,
            "text": t.text,
            "question_type": t.question_type.value if hasattr(t.question_type, 'value') else str(t.question_type),
        }
        for t in templates
    ]
    
    return {
        "id": question_set.id,
        "name": question_set.name,
        "is_public": question_set.is_public,
        "creator_id": question_set.creator_id,
        "usage_count": question_set.usage_count or 0,
        "created_at": question_set.created_at,
        "question_count": len(templates_list),
        "questions": templates_list
    }


@app.put("/api/groups/{group_id}/question-sets/{set_id}")
async def update_private_question_set(
    group_id: int,
    set_id: int,
    request: dict,
    session_token: str = Header(None),
    db: Session = Depends(get_db)
):
    """
    Update a private question set (name and/or questions).
    Only group creator can update their sets.
    """
    # Verify user and get session
    user = db.query(User).filter(
        and_(User.group_id == group_id, User.session_token == hash_token(session_token))
    ).first()
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session token")
    
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Check if user is group creator
    if group.created_by != user.email:
        raise HTTPException(status_code=403, detail="Only group creator can update private sets")
    
    # Verify this is a private set from this group
    custom_set = db.query(GroupCustomSet).filter(
        and_(GroupCustomSet.set_id == set_id, GroupCustomSet.group_id == group_id)
    ).first()
    
    if not custom_set:
        raise HTTPException(status_code=403, detail="This is not a private set you created")
    
    question_set = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()
    if not question_set:
        raise HTTPException(status_code=404, detail="Question set not found")
    
    # Update name if provided
    if "name" in request:
        name = request["name"].strip()
        if not name or len(name) < 3:
            raise HTTPException(status_code=400, detail="Set name must be at least 3 characters")
        if len(name) > 200:
            raise HTTPException(status_code=400, detail="Set name cannot exceed 200 characters")
        question_set.name = name
    
    # Update questions if provided
    if "questions" in request:
        questions = request["questions"]
        if not questions:
            raise HTTPException(status_code=400, detail="At least one question is required")
        if len(questions) > 100:
            raise HTTPException(status_code=400, detail="Maximum 100 questions per set")
        
        # Delete existing templates
        db.query(QuestionTemplate).filter(QuestionTemplate.set_id == set_id).delete()
        
        # Create new templates
        for idx, q in enumerate(questions):
            q_text = q.get("text", "").strip()
            q_type = q.get("question_type", "binary_vote")
            options = q.get("options", [])
            
            if not q_text:
                raise HTTPException(status_code=400, detail=f"Question {idx + 1}: text is required")
            
            valid_types = ["binary_vote", "single_choice", "free_text", "member_choice", "duo_choice"]
            if q_type not in valid_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"Question {idx + 1}: invalid question_type"
                )
            
            template = QuestionTemplate(
                text=q_text,
                question_type=QuestionTypeEnum[q_type.upper()],
                set_id=set_id
            )
            db.add(template)
    
    db.commit()
    
    return {
        "message": "Question set updated successfully",
        "set_id": question_set.id,
        "name": question_set.name
    }


@app.delete("/api/groups/{group_id}/question-sets/{set_id}")
async def delete_private_question_set(
    group_id: int,
    set_id: int,
    session_token: str = Header(None),
    db: Session = Depends(get_db)
):
    """
    Delete a private question set.
    Only group creator can delete their sets.
    Cannot delete sets that are currently assigned to the group.
    """
    # Verify user and get session
    user = db.query(User).filter(
        and_(User.group_id == group_id, User.session_token == hash_token(session_token))
    ).first()
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session token")
    
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Check if user is group creator
    if group.created_by != user.email:
        raise HTTPException(status_code=403, detail="Only group creator can delete private sets")
    
    # Verify this is a private set from this group
    custom_set = db.query(GroupCustomSet).filter(
        and_(GroupCustomSet.set_id == set_id, GroupCustomSet.group_id == group_id)
    ).first()
    
    if not custom_set:
        raise HTTPException(status_code=403, detail="This is not a private set you created")
    
    # Check if set is assigned to the group
    is_assigned = db.query(GroupQuestionSet).filter(
        and_(GroupQuestionSet.group_id == group_id, GroupQuestionSet.set_id == set_id)
    ).first()
    
    if is_assigned:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a question set that is currently assigned to the group. Unassign it first."
        )
    
    # Delete the custom set tracking
    db.delete(custom_set)
    
    # Delete question templates
    db.query(QuestionTemplate).filter(QuestionTemplate.set_id == set_id).delete()
    
    # Delete the question set
    question_set = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()
    if question_set:
        db.delete(question_set)
    
    db.commit()
    
    return {"message": "Question set deleted successfully", "set_id": set_id}


@app.get("/api/groups/{group_id}/question-sets/{set_id}/usage")
async def get_question_set_usage(
    group_id: int,
    set_id: int,
    session_token: str = Header(None),
    db: Session = Depends(get_db)
):
    """
    Get usage statistics for a private question set.
    Shows how many times each question has been asked.
    """
    # Verify user and get session
    user = db.query(User).filter(
        and_(User.group_id == group_id, User.session_token == hash_token(session_token))
    ).first()
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session token")
    
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Check if user is group creator
    if group.created_by != user.email:
        raise HTTPException(status_code=403, detail="Only group creator can view usage stats")
    
    # Verify this is a private set from this group
    custom_set = db.query(GroupCustomSet).filter(
        and_(GroupCustomSet.set_id == set_id, GroupCustomSet.group_id == group_id)
    ).first()
    
    if not custom_set:
        raise HTTPException(status_code=403, detail="This is not a private set you created")
    
    question_set = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()
    if not question_set:
        raise HTTPException(status_code=404, detail="Question set not found")
    
    # Get templates and their usage
    templates = db.query(QuestionTemplate).filter(
        QuestionTemplate.set_id == set_id
    ).all()
    
    questions_usage = []
    for template in templates:
        # Count how many times this template was used in daily questions
        usage_count = db.query(func.count(DailyQuestion.id)).filter(
            DailyQuestion.question_id == template.id
        ).scalar() or 0
        
        questions_usage.append({
            "template_id": template.id,
            "text": template.text,
            "question_type": template.question_type.value if hasattr(template.question_type, 'value') else str(template.question_type),
            "times_asked": usage_count
        })
    
    total_asks = sum(q["times_asked"] for q in questions_usage)
    
    return {
        "set_id": set_id,
        "set_name": question_set.name,
        "total_times_used": question_set.usage_count or 0,
        "total_questions_asked": total_asks,
        "questions": questions_usage
    }


# ==================== ADMIN MANAGEMENT ENDPOINTS ====================

@app.post("/api/admin/groups", response_model=dict)
async def admin_create_group(
    request_data: dict = Body(...),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
    x_forwarded_for: str = Header(None),
    request_obj: Request = None
):
    """Create a new group (admin only)"""
    try:
        name = request_data.get("name", "").strip()
        if not name or len(name) < 2:
            raise ValueError("Group name must be at least 2 characters")
        if len(name) > 255:
            raise ValueError("Group name must be at most 255 characters")
        
        # Check for duplicates
        existing = db.query(Group).filter(Group.name == name).first()
        if existing:
            raise ValueError("Group name already exists")
        
        # Generate invite code and admin token
        invite_code = generate_invite_code()
        admin_token_plaintext = generate_admin_token()
        admin_token_hash = _hash_and_store_token(admin_token_plaintext)
        
        # Ensure unique invite code
        while db.query(Group).filter(Group.invite_code == invite_code).first():
            invite_code = generate_invite_code()
        
        group = Group(
            name=name,
            invite_code=invite_code,
            admin_token=admin_token_hash,
            creator_id=None  # Admin-created groups have no specific user creator
        )
        db.add(group)
        db.commit()
        db.refresh(group)
        
        # Generate QR code
        qr_data = _generate_qr_code(invite_code)
        group.qr_data = qr_data
        db.commit()
        
        ip_address = extract_client_ip(request_obj, x_forwarded_for)
        log_admin_action(
            admin_id=admin.id,
            action="CREATE_GROUP",
            target_type="GROUP",
            target_id=group.id,
            before_state=None,
            after_state={"name": name},
            ip_address=ip_address,
            reason=None,
            db=db
        )
        
        return {"id": group.id, "name": group.name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="Error creating group: " + str(e))


@app.delete("/api/admin/groups/{group_id}")
async def admin_delete_group(
    group_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
    x_forwarded_for: str = Header(None),
    request_obj: Request = None
):
    """Delete a group and all related data (admin only)"""
    try:
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        
        # Delete all users in group
        db.query(User).filter(User.group_id == group_id).delete()
        
        # Delete all daily questions
        db.query(DailyQuestion).filter(DailyQuestion.group_id == group_id).delete()
        
        # Delete group-question set associations
        db.query(GroupQuestionSet).filter(GroupQuestionSet.group_id == group_id).delete()
        
        db.delete(group)
        db.commit()
        
        ip_address = extract_client_ip(request_obj, x_forwarded_for)
        log_admin_action(
            admin_id=admin.id,
            action="DELETE_GROUP",
            target_type="GROUP",
            target_id=group_id,
            before_state={"name": group.name},
            after_state=None,
            ip_address=ip_address,
            reason=None,
            db=db
        )
        
        return {"status": "deleted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/admin/users", response_model=dict)
async def admin_create_user(
    request_data: dict = Body(...),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
    x_forwarded_for: str = Header(None),
    request_obj: Request = None
):
    """Create a new user in a group (admin only)"""
    try:
        display_name = request_data.get("display_name", "").strip()
        group_id = request_data.get("group_id")
        color_avatar = request_data.get("color_avatar", None)
        
        if not display_name or len(display_name) < 2:
            raise ValueError("Display name must be at least 2 characters")
        if not group_id:
            raise ValueError("Group ID is required")
        
        # Check if group exists
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            raise ValueError("Group not found")
        
        # Check if user with same display name exists in group
        existing_user = db.query(User).filter(
            and_(User.group_id == group_id, User.display_name == display_name)
        ).first()
        if existing_user:
            raise ValueError("Display name already taken in this group")
        
        # Generate session token
        session_token_plaintext = generate_session_token()
        session_token_hash = _hash_and_store_token(session_token_plaintext)
        session_expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_TOKEN_EXPIRY_DAYS)
        avatar_color = color_avatar or get_random_avatar_color()
        
        user = User(
            group_id=group_id,
            display_name=display_name,
            session_token=session_token_hash,
            session_token_expires_at=session_expires_at,
            color_avatar=avatar_color
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        ip_address = extract_client_ip(request_obj, x_forwarded_for)
        log_admin_action(
            admin_id=admin.id,
            action="CREATE_USER",
            target_type="USER",
            target_id=user.id,
            before_state=None,
            after_state={"display_name": display_name, "group_id": group_id},
            ip_address=ip_address,
            reason=None,
            db=db
        )
        
        return {
            "id": user.id,
            "display_name": user.display_name,
            "group_id": user.group_id,
            "session_token": session_token_plaintext,
            "color_avatar": user.color_avatar
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="Error creating user: " + str(e))


@app.delete("/api/admin/users/{user_id}")
async def admin_delete_user(
    user_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
    x_forwarded_for: str = Header(None),
    request_obj: Request = None
):
    """Delete a user (admin only)"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Delete user's answers
        db.query(Answer).filter(Answer.user_id == user_id).delete()
        
        db.delete(user)
        db.commit()
        
        ip_address = extract_client_ip(request_obj, x_forwarded_for)
        log_admin_action(
            admin_id=admin.id,
            action="DELETE_USER",
            target_type="USER",
            target_id=user_id,
            before_state={"username": user.username, "group_id": user.group_id},
            after_state=None,
            ip_address=ip_address,
            reason=None,
            db=db
        )
        
        return {"status": "deleted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/admin/question-sets", response_model=dict)
async def admin_create_question_set(
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
    x_forwarded_for: str = Header(None),
    request_obj: Request = None,
    request_data: dict = Body(...)
):
    """Create a new question set (admin only)"""
    try:
        name = request_data.get("name", "").strip() if isinstance(request_data, dict) else ""
        is_public = request_data.get("is_public", True) if isinstance(request_data, dict) else True
        
        if not name or len(name) < 2:
            raise ValueError("Question set name must be at least 2 characters")
        if len(name) > 255:
            raise ValueError("Question set name must be at most 255 characters")
        
        existing = db.query(QuestionSet).filter(QuestionSet.name == name).first()
        if existing:
            raise ValueError("Question set name already exists")
        
        question_set = QuestionSet(
            name=name,
            is_public=is_public,
            creator_id=admin.id
        )
        db.add(question_set)
        db.commit()
        db.refresh(question_set)
        
        ip_address = extract_client_ip(request_obj, x_forwarded_for)
        log_admin_action(
            admin_id=admin.id,
            action="CREATE_QUESTION_SET",
            target_type="QUESTION_SET",
            target_id=question_set.id,
            before_state=None,
            after_state={"name": name, "is_public": is_public},
            ip_address=ip_address,
            reason=None,
            db=db
        )
        
        return {"id": question_set.id, "name": question_set.name, "is_public": is_public}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail="Error creating question set: " + str(e))


@app.post("/api/admin/question-sets/{set_id}/questions", response_model=dict)
async def admin_add_question_to_set(
    set_id: int,
    request_data: dict = Body(...),
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
    x_forwarded_for: str = Header(None),
    request_obj: Request = None
):
    """Add a question to a question set (admin only)"""
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

        # Map UI types to enums and option templates
        if question_type == "yesno":
            qt_enum = QuestionTypeEnum.BINARY_VOTE
            mapped_options = ["Yes", "No"]
        elif question_type in ["text", "free_text"]:
            qt_enum = QuestionTypeEnum.FREE_TEXT
            mapped_options = []
        elif question_type == "member_choice":
            qt_enum = QuestionTypeEnum.MEMBER_CHOICE
            mapped_options = []
        elif question_type == "duo_choice":
            qt_enum = QuestionTypeEnum.DUO_CHOICE
            mapped_options = []
        else:
            qt_enum = QuestionTypeEnum.SINGLE_CHOICE
            mapped_options = options

        # Create a QuestionTemplate and link it to the set
        template = QuestionTemplate(
            category="Admin",
            question_text=question_text,
            option_a_template=mapped_options[0] if mapped_options else None,
            option_b_template=mapped_options[1] if len(mapped_options) > 1 else None,
            question_type=qt_enum,
            allow_multiple=False,
            is_public=True,
        )
        db.add(template)
        db.flush()

        db.add(QuestionSetTemplate(question_set_id=set_id, template_id=template.id))
        db.commit()
        db.refresh(template)
        
        ip_address = extract_client_ip(request_obj, x_forwarded_for)
        log_admin_action(
            admin_id=admin.id,
            action="ADD_QUESTION",
            target_type="QUESTION",
            target_id=template.id,
            before_state=None,
            after_state={"question_text": question_text, "type": qt_enum.value if hasattr(qt_enum, "value") else str(qt_enum)},
            ip_address=ip_address,
            reason=None,
            db=db
        )
        
        return {
            "id": template.id,
            "question_text": template.question_text,
            "type": template.question_type.value if hasattr(template.question_type, "value") else template.question_type,
            "options": [o for o in mapped_options if o]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/admin/question-sets/{set_id}")
async def admin_delete_question_set(
    set_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
    x_forwarded_for: str = Header(None),
    request_obj: Request = None
):
    """Delete a question set and all related data (admin only)"""
    try:
        question_set = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()
        if not question_set:
            raise HTTPException(status_code=404, detail="Question set not found")
        
        # Delete all templates in this set
        db.query(QuestionSetTemplate).filter(QuestionSetTemplate.question_set_id == set_id).delete()
        
        # Delete all group associations
        db.query(GroupQuestionSet).filter(GroupQuestionSet.question_set_id == set_id).delete()
        
        db.delete(question_set)
        db.commit()
        
        ip_address = extract_client_ip(request_obj, x_forwarded_for)
        log_admin_action(
            admin_id=admin.id,
            action="DELETE_QUESTION_SET",
            target_type="QUESTION_SET",
            target_id=set_id,
            before_state={"name": question_set.name},
            after_state=None,
            ip_address=ip_address,
            reason=None,
            db=db
        )
        
        return {"status": "deleted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/admin/question-sets/{set_id}/questions/{question_id}")
async def admin_delete_question(
    set_id: int,
    question_id: int,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
    x_forwarded_for: str = Header(None),
    request_obj: Request = None
):
    """Delete a question from a question set (admin only)"""
    try:
        question = db.query(QuestionSetTemplate).filter(
            QuestionSetTemplate.id == question_id,
            QuestionSetTemplate.question_set_id == set_id
        ).first()
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")
        
        db.delete(question)
        db.commit()
        
        ip_address = extract_client_ip(request_obj, x_forwarded_for)
        log_admin_action(
            admin_id=admin.id,
            action="DELETE_QUESTION",
            target_type="QUESTION",
            target_id=question_id,
            before_state={"question_text": question.question_text},
            after_state=None,
            ip_address=ip_address,
            reason=None,
            db=db
        )
        
        return {"status": "deleted"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
