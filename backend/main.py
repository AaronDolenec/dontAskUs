from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, Path, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, date, timezone, timedelta
from contextlib import asynccontextmanager
import threading
import time
import random
import os
# pylint: disable=broad-except,logging-fstring-interpolation
import secrets
import string
import json
import qrcode
import base64
import io
from typing import Optional
import logging
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from database import engine, get_db, Base, SessionLocal
from models import (
    Group, User, DailyQuestion, Vote, QuestionTemplate, QuestionSet, QuestionSetTemplate, 
    GroupQuestionSet, UserGroupStreak, QuestionTypeEnum, hash_token, verify_token
)
from schemas import (
    GroupCreate, GroupResponse, GroupResponsePublic, UserCreate, UserResponse,
    DailyQuestionCreate, DailyQuestionResponse, VoteCreate, AnswerSubmissionCreate,
    QuestionTemplateResponse, QuestionSetCreate, QuestionSetResponse, GroupQuestionSetsResponse, 
    GroupAssignSetsRequest
)
from ws_manager import manager
from dotenv import load_dotenv

load_dotenv()

# Central logging configuration
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# Get configuration from environment
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
SESSION_TOKEN_EXPIRY_DAYS = int(os.getenv("SESSION_TOKEN_EXPIRY_DAYS", "7"))

# Create tables (guarded so app doesn't crash if DB is unavailable during dev)
try:
    Base.metadata.create_all(bind=engine)
except Exception:
    logging.exception("Database unavailable at startup; continuing without creating tables")


@asynccontextmanager
async def lifespan(_app):
    # Run startup tasks: seed default data and start the background scheduler
    try:
        # seed default templates and sets
        try:
            seed_default_question_sets()
        except Exception:
            logging.exception("seed_default_question_sets failed during lifespan startup")

        # start scheduler thread
        try:
            interval = int(os.getenv("SCHEDULE_INTERVAL_SECONDS", "86400"))
            t = threading.Thread(target=_background_scheduler, args=(interval,), daemon=True)
            t.start()
        except Exception:
            logging.exception("background scheduler failed to start during lifespan startup")

        yield
    finally:
        # no-op shutdown
        pass

app = FastAPI(
    title="DontAskUs - Real-Time Q&A Platform",
    version="1.0.0",
    description="A self-hosted alternative to AskUs with real-time voting",
    lifespan=lifespan,
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

# Rate limiting error handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(_request, _exc):
    return JSONResponse(status_code=429, content={"detail": "Too many requests. Please try again later."})

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

def _get_user_by_session(session_token: str, db: Session) -> Optional[User]:
    """Get user from session token, verifying hash and expiry."""
    # Find all users with potential matching tokens (limited lookup)
    users = db.query(User).all()  # In production, optimize this with indexed lookup
    
    for user in users:
        # Check if token is expired
        if user.session_token_expires_at:
            if datetime.now(timezone.utc) > user.session_token_expires_at:
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
    return vote.answer if vote else None


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


def seed_default_question_sets():
    db = SessionLocal()
    try:
        # Seed templates if none exist
        if db.query(QuestionTemplate).count() == 0:
            templates_data = [
                {
                    "category": "General",
                    "question_text": "Do you prefer coffee or tea?",
                    "option_a_template": "Coffee",
                    "option_b_template": "Tea",
                    "question_type": QuestionTypeEnum.BINARY_VOTE
                },
                {
                    "category": "Work",
                    "question_text": "Do you feel productive today?",
                    "option_a_template": "Yes",
                    "option_b_template": "No",
                    "question_type": QuestionTypeEnum.BINARY_VOTE
                },
                {
                    "category": "Fun",
                    "question_text": "Would you rather go hiking or watch a movie?",
                    "option_a_template": "Hiking",
                    "option_b_template": "Movie",
                    "question_type": QuestionTypeEnum.BINARY_VOTE
                },
                {
                    "category": "Opinion",
                    "question_text": "What's your preferred programming language?",
                    "option_a_template": None,
                    "option_b_template": None,
                    "question_type": QuestionTypeEnum.FREE_TEXT
                }
            ]
            for t in templates_data:
                qt = QuestionTemplate(
                    category=t["category"],
                    question_text=t["question_text"],
                    option_a_template=t["option_a_template"],
                    option_b_template=t["option_b_template"],
                    question_type=t["question_type"],
                    is_public=True
                )
                db.add(qt)
            db.commit()

        # Seed a default question set if none exist
        if db.query(QuestionSet).count() == 0:
            templates = db.query(QuestionTemplate).all()
            default_set = QuestionSet(
                name="Default Set",
                description="A starter set of questions",
                is_public=True
            )
            db.add(default_set)
            db.commit()
            db.refresh(default_set)
            for t in templates:
                assoc = QuestionSetTemplate(question_set_id=default_set.id, template_id=t.id)
                db.add(assoc)
            db.commit()
    finally:
        db.close()


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

            # Create daily question with question_type from template
            dq = DailyQuestion(
                group_id=group.id,
                template_id=tmpl.id,
                question_text=tmpl.question_text,
                option_a=tmpl.option_a_template,
                option_b=tmpl.option_b_template,
                question_type=tmpl.question_type,
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
    group = db.query(Group).filter(Group.group_id == group_id).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
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
    group = db.query(Group).filter(Group.group_id == group_id).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
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
    
    db_question = DailyQuestion(
        group_id=group.id,
        question_text=question.question_text,
        option_a=question.option_a,
        option_b=question.option_b
    )
    
    db.add(db_question)
    db.commit()
    db.refresh(db_question)
    
    return DailyQuestionResponse(
        id=db_question.id,
        question_id=db_question.question_id,
        question_text=db_question.question_text,
        option_a=db_question.option_a,
        option_b=db_question.option_b,
        question_date=db_question.question_date,
        is_active=db_question.is_active,
        vote_count_a=0,
        vote_count_b=0,
        total_votes=0
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
    group = db.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
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
    
    group = db.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
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
    
    # Count votes
    vote_count_a, vote_count_b = _get_vote_counts(question.id, db)
    
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
        option_a=question.option_a,
        option_b=question.option_b,
        question_date=question.question_date,
        is_active=question.is_active,
        vote_count_a=vote_count_a,
        vote_count_b=vote_count_b,
        total_votes=vote_count_a + vote_count_b,
        user_vote=user_vote,
        user_streak=user_streak,
        longest_streak=longest_streak
    )

# ============= Voting Routes =============

@app.post("/api/questions/{question_id}/vote")
@limiter.limit("100/minute")
def vote_on_question(
    request: Request,
    question_id: str = Path(...),
    vote: VoteCreate = None,
    session_token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Cast a vote on a question"""
    
    if not session_token:
        raise HTTPException(status_code=401, detail="Session token required")
    
    user = _get_user_by_session(session_token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    question = db.query(DailyQuestion).filter(
        DailyQuestion.question_id == question_id
    ).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Check if user already voted
    existing_vote = db.query(Vote).filter(
        and_(Vote.question_id == question.id, Vote.user_id == user.id)
    ).first()
    
    if existing_vote:
        # Update existing vote
        existing_vote.answer = vote.answer
        existing_vote.voted_at = datetime.now(timezone.utc)
    else:
        # Create new vote
        db_vote = Vote(
            question_id=question.id,
            user_id=user.id,
            answer=vote.answer
        )
        db.add(db_vote)
        
        # Update streak
        today = date.today()
        if user.last_answer_date:
            last_date = user.last_answer_date.date()
            if last_date == today:
                # Already voted today
                pass
            elif (today - last_date).days == 1:
                # Continued streak
                user.answer_streak += 1
            else:
                # Streak broken
                user.answer_streak = 1
        
        if user.answer_streak > user.longest_answer_streak:
            user.longest_answer_streak = user.answer_streak
        
        user.last_answer_date = datetime.now(timezone.utc)
    
    db.commit()
    
    # Get updated vote counts
    vote_count_a, vote_count_b = _get_vote_counts(question.id, db)
    
    return {
        "success": True,
        "vote_count_a": vote_count_a,
        "vote_count_b": vote_count_b,
        "total_votes": vote_count_a + vote_count_b,
        "user_vote": vote.answer,
        "answer_streak": user.answer_streak,
        "longest_answer_streak": user.longest_answer_streak
    }


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
    
    group = db.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    if user.group_id != group.id:
        raise HTTPException(status_code=403, detail="User not in this group")
    
    question = db.query(DailyQuestion).filter(
        DailyQuestion.question_id == question_id
    ).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Validate answer based on question type
    if question.question_type == QuestionTypeEnum.BINARY_VOTE and not answer.answer:
        raise HTTPException(status_code=400, detail="Binary questions require an answer (A or B)")
    if question.question_type == QuestionTypeEnum.SINGLE_CHOICE and not answer.answer:
        raise HTTPException(status_code=400, detail="Single choice questions require an answer")
    if question.question_type == QuestionTypeEnum.FREE_TEXT and not answer.text_answer:
        raise HTTPException(status_code=400, detail="Free text questions require a text answer")
    
    # Check if user already answered
    existing_vote = db.query(Vote).filter(
        and_(Vote.question_id == question.id, Vote.user_id == user.id)
    ).first()
    
    if existing_vote:
        # Update existing answer
        existing_vote.answer = answer.answer
        existing_vote.text_answer = answer.text_answer
        existing_vote.voted_at = datetime.now(timezone.utc)
    else:
        # Create new answer
        db_vote = Vote(
            question_id=question.id,
            user_id=user.id,
            answer=answer.answer,
            text_answer=answer.text_answer
        )
        db.add(db_vote)
        db.flush()
        
        # Update per-group streak
        _update_user_group_streak(user.id, group.id, db)
    
    db.commit()
    
    # Get updated vote counts
    vote_count_a, vote_count_b = _get_vote_counts(question.id, db)
    
    # Get user's current streak for this group
    streak = _get_user_group_streak(user.id, group.id, db)
    
    return {
        "success": True,
        "question_type": question.question_type.value,
        "vote_count_a": vote_count_a,
        "vote_count_b": vote_count_b,
        "total_votes": vote_count_a + vote_count_b,
        "user_answer": answer.answer or answer.text_answer,
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
    
    group = db.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
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
        vote_count_a, vote_count_b = _get_vote_counts(question.id, db)
        result.append({
            "question_id": question.question_id,
            "question_text": question.question_text,
            "question_type": question.question_type.value,
            "option_a": question.option_a,
            "option_b": question.option_b,
            "question_date": question.question_date,
            "is_active": question.is_active,
            "vote_count_a": vote_count_a,
            "vote_count_b": vote_count_b,
            "total_votes": vote_count_a + vote_count_b
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
                group = db.query(Group).filter(Group.group_id == group_id).first()
                if group:
                    question = db.query(DailyQuestion).filter(
                        DailyQuestion.question_id == question_id
                    ).first()
                    if question:
                        user = _get_user_by_session(message.get("session_token"), db)
                        if user:
                            existing_vote = db.query(Vote).filter(
                                and_(
                                    Vote.question_id == question.id,
                                    Vote.user_id == user.id
                                )
                            ).first()
                            
                            if existing_vote:
                                existing_vote.answer = message.get("answer")
                            else:
                                db_vote = Vote(
                                    question_id=question.id,
                                    user_id=user.id,
                                    answer=message.get("answer")
                                )
                                db.add(db_vote)
                            
                            db.commit()
                            
                            # Get updated counts
                            vote_a, vote_b = _get_vote_counts(question.id, db)
                            
                            # Broadcast to all users
                            await manager.broadcast_update(group_id, question_id, {
                                "vote_count_a": vote_a,
                                "vote_count_b": vote_b,
                                "total_votes": vote_a + vote_b,
                                "user": {
                                    "display_name": user.display_name,
                                    "voted": message.get("answer")
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

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
