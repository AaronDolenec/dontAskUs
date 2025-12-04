from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc
from datetime import datetime, timedelta, date
import secrets
import string
import json
from typing import Optional, List

from database import engine, SessionLocal, get_db, Base
from models import Group, User, DailyQuestion, Vote, QuestionTemplate, GroupAnalytics
from schemas import (
    GroupCreate, GroupResponse, UserCreate, UserResponse,
    DailyQuestionCreate, DailyQuestionResponse, VoteCreate
)
from websocket_manager import manager
import os
from dotenv import load_dotenv

load_dotenv()

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AskUs Clone - Real-Time Q&A Platform",
    version="1.0.0",
    description="A self-hosted alternative to AskUs with real-time voting"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# ============= Group Routes =============

@app.post("/api/groups", response_model=GroupResponse)
def create_group(group: GroupCreate, db: Session = Depends(get_db)):
    """Create a new group"""
    invite_code = generate_invite_code()
    admin_token = generate_admin_token()
    
    # Ensure unique invite code
    while db.query(Group).filter(Group.invite_code == invite_code).first():
        invite_code = generate_invite_code()
    
    db_group = Group(
        name=group.name,
        invite_code=invite_code,
        admin_token=admin_token
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
        created_at=db_group.created_at,
        member_count=0
    )

@app.get("/api/groups/{invite_code}", response_model=GroupResponse)
def get_group_by_code(invite_code: str, db: Session = Depends(get_db)):
    """Get group info by invite code (for joining)"""
    group = db.query(Group).filter(Group.invite_code == invite_code).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    member_count = db.query(User).filter(User.group_id == group.id).count()
    
    return GroupResponse(
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
def join_group(user: UserCreate, db: Session = Depends(get_db)):
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
    session_token = generate_session_token()
    avatar_color = user.color_avatar or get_random_avatar_color()
    
    db_user = User(
        group_id=group.id,
        display_name=user.display_name,
        session_token=session_token,
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
        session_token=db_user.session_token,
        created_at=db_user.created_at,
        answer_streak=db_user.answer_streak,
        longest_answer_streak=db_user.longest_answer_streak
    )

@app.get("/api/users/validate-session/{session_token}")
def validate_session(session_token: str, db: Session = Depends(get_db)):
    """Validate user session token"""
    user = db.query(User).filter(User.session_token == session_token).first()
    
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
def get_group_members(group_id: str, db: Session = Depends(get_db)):
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
def create_daily_question(
    group_id: str = Path(...),
    question: DailyQuestionCreate = None,
    db: Session = Depends(get_db)
):
    """Create a new daily question (admin endpoint)"""
    
    group = db.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Check if question already exists for today
    today = datetime.utcnow().date()
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

@app.get("/api/groups/{group_id}/questions/today")
def get_todays_question(
    group_id: str = Path(...),
    session_token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get today's question for a group"""
    
    group = db.query(Group).filter(Group.group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    today = datetime.utcnow().date()
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
    vote_count_a = db.query(Vote).filter(
        and_(Vote.question_id == question.id, Vote.answer == 'A')
    ).count()
    vote_count_b = db.query(Vote).filter(
        and_(Vote.question_id == question.id, Vote.answer == 'B')
    ).count()
    
    # Get user's vote if authenticated
    user_vote = None
    user_streak = 0
    longest_streak = 0
    if session_token:
        user = db.query(User).filter(User.session_token == session_token).first()
        if user:
            vote = db.query(Vote).filter(
                and_(Vote.question_id == question.id, Vote.user_id == user.id)
            ).first()
            if vote:
                user_vote = vote.answer
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
def vote_on_question(
    question_id: str = Path(...),
    vote: VoteCreate = None,
    session_token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Cast a vote on a question"""
    
    if not session_token:
        raise HTTPException(status_code=401, detail="Session token required")
    
    user = db.query(User).filter(User.session_token == session_token).first()
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
        existing_vote.voted_at = datetime.utcnow()
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
        
        user.last_answer_date = datetime.utcnow()
    
    db.commit()
    
    # Get updated vote counts
    vote_count_a = db.query(Vote).filter(
        and_(Vote.question_id == question.id, Vote.answer == 'A')
    ).count()
    vote_count_b = db.query(Vote).filter(
        and_(Vote.question_id == question.id, Vote.answer == 'B')
    ).count()
    
    return {
        "success": True,
        "vote_count_a": vote_count_a,
        "vote_count_b": vote_count_b,
        "total_votes": vote_count_a + vote_count_b,
        "user_vote": vote.answer,
        "answer_streak": user.answer_streak,
        "longest_answer_streak": user.longest_answer_streak
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
                        user = db.query(User).filter(
                            User.session_token == message.get("session_token")
                        ).first()
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
                            vote_a = db.query(Vote).filter(
                                and_(
                                    Vote.question_id == question.id,
                                    Vote.answer == 'A'
                                )
                            ).count()
                            vote_b = db.query(Vote).filter(
                                and_(
                                    Vote.question_id == question.id,
                                    Vote.answer == 'B'
                                )
                            ).count()
                            
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
                    "timestamp": datetime.utcnow().isoformat()
                }))
    
    except WebSocketDisconnect:
        manager.disconnect(group_id, question_id, websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(group_id, question_id, websocket)

# ============= Admin Routes =============

@app.get("/api/admin/groups/{admin_token}/leaderboard")
def get_leaderboard(
    admin_token: str = Path(...),
    db: Session = Depends(get_db)
):
    """Get group leaderboard by answer streak"""
    group = db.query(Group).filter(Group.admin_token == admin_token).first()
    
    if not group:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    
    # Get all members with their streaks
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

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
