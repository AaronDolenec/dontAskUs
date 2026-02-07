"""Daily questions, voting, answer submission, and history routes."""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Query, Path as PathParam
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from database import get_db
from models import (
    Group, User, DailyQuestion, Vote, QuestionTemplate, QuestionSet,
    QuestionSetTemplate, GroupQuestionSet, QuestionTypeEnum, UserDeviceToken,
)
from push_notifications import push_service
from schemas import DailyQuestionCreate, DailyQuestionResponse, AnswerSubmissionCreate
from utils import (
    get_group_by_id, require_group_admin, get_user_for_group,
    get_group_member_names, generate_duos, get_option_counts, get_user_vote,
    get_user_group_streak, update_user_group_streak, normalize_answer_submission,
    get_avatar_url,
)

router = APIRouter(prefix="/api", tags=["Questions"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/groups/{group_id}/questions", response_model=DailyQuestionResponse)
@limiter.limit("10/minute")
def create_daily_question(
    request: Request,
    group: Group = Depends(require_group_admin),
    question: DailyQuestionCreate = None,
    db: Session = Depends(get_db),
):
    """Create a new daily question (admin endpoint)."""
    today = datetime.now(timezone.utc).date()
    existing = db.query(DailyQuestion).filter(
        and_(DailyQuestion.group_id == group.id, func.date(DailyQuestion.question_date) == today)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Question already exists for today")

    question_set = None
    if question.question_set_id:
        question_set = db.query(QuestionSet).filter(QuestionSet.set_id == question.question_set_id).first()
        if not question_set:
            raise HTTPException(status_code=404, detail="Question set not found")
    else:
        question_set = (
            db.query(QuestionSet).filter(QuestionSet.name == "Default").first()
            or db.query(QuestionSet).filter(QuestionSet.is_public == True).first()
        )
    if question_set:
        logging.info(f"Creating question for group {group.group_id} from set '{question_set.name}'")

    members = get_group_member_names(group, db)
    options_list = _build_options(question.question_type, members, question)

    option_a = options_list[0] if options_list else None
    option_b = options_list[1] if len(options_list) > 1 else None

    db_question = DailyQuestion(
        group_id=group.id, question_text=question.question_text,
        option_a=option_a, option_b=option_b,
        options=json.dumps(options_list) if options_list else None,
        question_type=question.question_type, allow_multiple=question.allow_multiple,
    )
    db.add(db_question)
    db.commit()
    db.refresh(db_question)

    _send_push_for_question(db, group, db_question)

    return DailyQuestionResponse(
        id=db_question.id, question_id=db_question.question_id,
        question_text=db_question.question_text, question_type=db_question.question_type,
        options=json.loads(db_question.options) if db_question.options else [],
        option_counts={}, question_date=db_question.question_date,
        is_active=db_question.is_active, total_votes=0,
        allow_multiple=db_question.allow_multiple,
    )


@router.get("/groups/{group_id}/questions/today")
@limiter.limit("200/minute")
def get_todays_question(request: Request, group_id: str = PathParam(...), db: Session = Depends(get_db)):
    """Get today's question for a group. Requires authentication and group membership."""
    group = get_group_by_id(group_id, db)
    user = get_user_for_group(request, group, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.group_id != group.id:
        raise HTTPException(status_code=403, detail="You are not a member of this group")

    today = datetime.now(timezone.utc).date()
    question = db.query(DailyQuestion).filter(
        and_(DailyQuestion.group_id == group.id, func.date(DailyQuestion.question_date) == today, DailyQuestion.is_active == True)
    ).first()
    if not question:
        raise HTTPException(status_code=404, detail="No question for today")

    options_list = json.loads(question.options) if question.options else []
    option_counts = get_option_counts(question.id, db)
    total_votes = db.query(func.count(Vote.id)).filter(Vote.question_id == question.id).scalar() or 0

    user_vote = get_user_vote(user.id, question.id, db)
    user_streak = user.answer_streak
    longest_streak = user.longest_answer_streak

    return DailyQuestionResponse(
        id=question.id, question_id=question.question_id,
        question_text=question.question_text, question_type=question.question_type,
        options=options_list, option_counts=option_counts,
        question_date=question.question_date, is_active=question.is_active,
        total_votes=total_votes, allow_multiple=question.allow_multiple,
        user_vote=user_vote, user_streak=user_streak, longest_streak=longest_streak,
    )


@router.post("/groups/{group_id}/questions/{question_id}/answer")
@limiter.limit("100/minute")
def submit_answer(
    request: Request, group_id: str = PathParam(...), question_id: str = PathParam(...),
    answer: AnswerSubmissionCreate = None, db: Session = Depends(get_db),
):
    """Submit an answer to a question."""
    group = get_group_by_id(group_id, db)
    user = get_user_for_group(request, group, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.group_id != group.id:
        raise HTTPException(status_code=403, detail="User not in this group")

    question = db.query(DailyQuestion).filter(DailyQuestion.question_id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    options_list = json.loads(question.options) if question.options else []
    allow_multiple = bool(getattr(question, "allow_multiple", False))
    stored_answer = None
    normalized_answers: list[str] = []

    if question.question_type == QuestionTypeEnum.FREE_TEXT:
        if not answer.text_answer:
            raise HTTPException(status_code=400, detail="Free text questions require a text answer")
    else:
        if answer.answer is None:
            raise HTTPException(status_code=400, detail="Answer is required")
        normalized_answers = normalize_answer_submission(answer.answer, allow_multiple)
        if not normalized_answers:
            raise HTTPException(status_code=400, detail="Answer is required")
        if not allow_multiple and len(normalized_answers) != 1:
            raise HTTPException(status_code=400, detail="Only one selection allowed")
        if options_list:
            invalid = [a for a in normalized_answers if a not in options_list]
            if invalid:
                raise HTTPException(status_code=400, detail="Answer must be one of the available options")
        stored_answer = json.dumps(normalized_answers) if allow_multiple else normalized_answers[0]

    existing_vote = db.query(Vote).filter(and_(Vote.question_id == question.id, Vote.user_id == user.id)).first()
    if existing_vote:
        existing_vote.answer = stored_answer if question.question_type != QuestionTypeEnum.FREE_TEXT else answer.text_answer
        existing_vote.text_answer = answer.text_answer
        existing_vote.voted_at = datetime.now(timezone.utc)
    else:
        db_vote = Vote(
            question_id=question.id, user_id=user.id,
            answer=stored_answer if question.question_type != QuestionTypeEnum.FREE_TEXT else answer.text_answer,
            text_answer=answer.text_answer,
        )
        db.add(db_vote)
        db.flush()
        update_user_group_streak(user.id, group.id, db)

    db.commit()

    option_counts = get_option_counts(question.id, db)
    total_votes = db.query(func.count(Vote.id)).filter(Vote.question_id == question.id).scalar() or 0
    vote_count_a = option_counts.get(options_list[0], 0) if options_list else 0
    vote_count_b = option_counts.get(options_list[1], 0) if len(options_list) > 1 else 0
    streak = get_user_group_streak(user.id, group.id, db)

    user_answer_value = answer.text_answer if question.question_type == QuestionTypeEnum.FREE_TEXT else (
        normalized_answers if allow_multiple else normalized_answers[0]
    )
    return {
        "success": True, "question_type": question.question_type.value,
        "vote_count_a": vote_count_a, "vote_count_b": vote_count_b,
        "total_votes": total_votes, "option_counts": option_counts,
        "options": options_list, "user_answer": user_answer_value,
        "current_streak": streak.current_streak, "longest_streak": streak.longest_streak,
    }


@router.get("/groups/{group_id}/questions/history")
@limiter.limit("200/minute")
def get_question_history(
    request: Request, group_id: str = PathParam(...),
    skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get historical questions for a group (paginated). Requires authentication and group membership."""
    group = get_group_by_id(group_id, db)
    user = get_user_for_group(request, group, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.group_id != group.id:
        raise HTTPException(status_code=403, detail="You are not a member of this group")
    questions = db.query(DailyQuestion).filter(
        DailyQuestion.group_id == group.id
    ).order_by(DailyQuestion.question_date.desc()).offset(skip).limit(limit).all()
    total_count = db.query(DailyQuestion).filter(DailyQuestion.group_id == group.id).count()

    result = []
    for q in questions:
        opts = json.loads(q.options) if q.options else []
        oc = get_option_counts(q.id, db)
        tv = db.query(func.count(Vote.id)).filter(Vote.question_id == q.id).scalar() or 0
        result.append({
            "question_id": q.question_id, "question_text": q.question_text,
            "question_type": q.question_type.value,
            "option_a": q.option_a, "option_b": q.option_b,
            "options": opts, "option_counts": oc, "question_date": q.question_date,
            "is_active": q.is_active,
            "vote_count_a": oc.get(opts[0], 0) if opts else 0,
            "vote_count_b": oc.get(opts[1], 0) if len(opts) > 1 else 0,
            "total_votes": tv, "allow_multiple": getattr(q, "allow_multiple", False),
        })
    return {"group_id": group_id, "total_count": total_count, "skip": skip, "limit": limit, "questions": result}


# ============= Group Admin Question Management =============

@router.get("/admin/groups/{group_id}/leaderboard")
@limiter.limit("60/minute")
def get_leaderboard(request: Request, group: Group = Depends(require_group_admin), db: Session = Depends(get_db)):
    """Get group leaderboard by answer streak (group admin only)."""
    members = db.query(User).filter(User.group_id == group.id).all()
    leaderboard = sorted(members, key=lambda x: (x.answer_streak, x.longest_answer_streak), reverse=True)
    base_url = str(request.base_url).rstrip('/')
    return [
        {
            "display_name": m.display_name, "color_avatar": m.color_avatar,
            "avatar_url": get_avatar_url(m.avatar_filename, base_url),
            "answer_streak": m.answer_streak, "longest_answer_streak": m.longest_answer_streak,
        }
        for m in leaderboard
    ]


@router.get("/admin/groups/{group_id}/question-status")
@limiter.limit("60/minute")
def get_question_status(request: Request, group: Group = Depends(require_group_admin), db: Session = Depends(get_db)):
    """Get question exhaustion status for a group (group admin only)."""
    assigned = db.query(GroupQuestionSet).filter(
        GroupQuestionSet.group_id == group.id, GroupQuestionSet.is_active == True
    ).all()
    available_templates = set()
    for a in assigned:
        s = db.get(QuestionSet, a.question_set_id)
        if s:
            for assoc in db.query(QuestionSetTemplate).filter(QuestionSetTemplate.question_set_id == s.id).all():
                available_templates.add(assoc.template_id)
    if not available_templates:
        public_templates = db.query(QuestionTemplate).filter(QuestionTemplate.is_public == True).all()
        available_templates = {t.id for t in public_templates}
    total_available = len(available_templates)

    used = db.query(DailyQuestion.template_id).filter(
        DailyQuestion.group_id == group.id, DailyQuestion.template_id.isnot(None)
    ).distinct().all()
    used_count = len({t[0] for t in used})
    exhausted = used_count >= total_available
    question_count = db.query(DailyQuestion).filter(DailyQuestion.group_id == group.id).count()

    return {
        "group_id": group.group_id, "total_available_templates": total_available,
        "used_templates_count": used_count, "exhausted": exhausted,
        "total_questions_created": question_count,
        "message": "All questions have been used. Cycle will reset on next question." if exhausted else "Questions available",
    }


@router.post("/admin/groups/{group_id}/reset-question-cycle")
@limiter.limit("10/minute")
def reset_question_cycle(request: Request, group: Group = Depends(require_group_admin), db: Session = Depends(get_db)):
    """Reset question cycle by clearing used questions (group admin only)."""
    # Delete votes for this group's daily questions first (FK constraint)
    question_ids = [q.id for q in db.query(DailyQuestion.id).filter(DailyQuestion.group_id == group.id).all()]
    if question_ids:
        db.query(Vote).filter(Vote.question_id.in_(question_ids)).delete(synchronize_session=False)
    deleted_count = db.query(DailyQuestion).filter(DailyQuestion.group_id == group.id).delete()
    db.commit()
    logging.info(f"Question cycle reset for group {group.group_id}. Deleted {deleted_count} questions.")
    return {"group_id": group.group_id, "message": f"Question cycle reset. {deleted_count} questions deleted.", "deleted_count": deleted_count}


@router.post("/admin/groups/{group_id}/regenerate-today")
@limiter.limit("10/minute")
def regenerate_todays_question(
    request: Request, group: Group = Depends(require_group_admin), db: Session = Depends(get_db),
):
    """Delete today's question and create a new one from current sets."""
    from scheduler import create_today_question_for_group
    today = datetime.now(timezone.utc).date()
    db.query(DailyQuestion).filter(
        and_(DailyQuestion.group_id == group.id, func.date(DailyQuestion.question_date) == today)
    ).delete()
    db.commit()
    dq = create_today_question_for_group(db, group)
    if not dq:
        raise HTTPException(status_code=400, detail="Unable to generate today's question (insufficient members or no templates)")
    options_list = json.loads(dq.options) if dq.options else []
    option_counts = get_option_counts(dq.id, db)
    total_votes = db.query(func.count(Vote.id)).filter(Vote.question_id == dq.id).scalar() or 0
    return DailyQuestionResponse(
        id=dq.id, question_id=dq.question_id, question_text=dq.question_text,
        question_type=dq.question_type, options=options_list, option_counts=option_counts,
        question_date=dq.question_date, is_active=dq.is_active, total_votes=total_votes,
    )


# ============= Helpers =============

def _build_options(question_type, members: list[str], question) -> list:
    """Build options list based on question type."""
    if question_type == QuestionTypeEnum.MEMBER_CHOICE:
        if len(members) < 2:
            raise HTTPException(status_code=400, detail="Need at least two group members for member_choice")
        return members
    elif question_type == QuestionTypeEnum.DUO_CHOICE:
        if len(members) < 2:
            raise HTTPException(status_code=400, detail="Need at least two group members for duo_choice")
        return generate_duos(members)
    elif question_type == QuestionTypeEnum.BINARY_VOTE:
        return ["Yes", "No"]
    elif question_type == QuestionTypeEnum.SINGLE_CHOICE:
        if question.option_a and question.option_b:
            return [question.option_a, question.option_b]
        return members if len(members) >= 2 else []
    return []  # FREE_TEXT


def _send_push_for_question(db: Session, group: Group, question: DailyQuestion):
    """Send push notifications for a new daily question if enabled."""
    if not push_service.is_enabled():
        return
    try:
        group_user_ids = [m.id for m in db.query(User).filter(User.group_id == group.id, User.is_suspended == False).all()]
        device_tokens = db.query(UserDeviceToken).filter(
            UserDeviceToken.user_id.in_(group_user_ids), UserDeviceToken.is_active == True
        ).all()
        if device_tokens:
            tokens = [dt.token for dt in device_tokens]
            import asyncio
            asyncio.create_task(
                push_service.send_daily_question_notification(
                    tokens=tokens, group_name=group.name, question_preview=question.question_text[:100]
                )
            )
            logging.info(f"Push notification sent to {len(tokens)} devices for group {group.group_id}")
    except Exception as e:
        logging.error(f"Failed to send push notifications: {e}")
