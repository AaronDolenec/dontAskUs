"""Daily questions, voting, answer submission, and history routes."""

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Query, Path as PathParam
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import (
    Group, User, DailyQuestion, Vote, QuestionTemplate,
    QuestionSet, QuestionSetTemplate, GroupQuestionSet, QuestionTypeEnum,
)
from core.schemas import DailyQuestionResponse, AnswerSubmissionCreate
from auth.utils import (
    get_group_by_id, get_user_for_group,
    get_option_counts, get_user_vote, get_text_answers, get_answer_details,
    get_user_group_streak, update_user_group_streak, normalize_answer_submission,
    get_avatar_url,
)
from services.scheduler import create_today_question_for_group, get_group_question_day
from services.ws_manager import manager as ws_manager

router = APIRouter(prefix="/api", tags=["Questions"])
limiter = Limiter(key_func=get_remote_address)


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

    question_day = get_group_question_day(group)
    question = db.query(DailyQuestion).filter(
        and_(DailyQuestion.group_id == group.id, func.date(DailyQuestion.question_date) == question_day, DailyQuestion.is_active == True)
    ).first()

    # On-demand fallback: if the scheduler hasn't created this day's question yet
    # (e.g. scheduler thread died, container just started, timing edge-case),
    # create it now so the user never sees a stale "no question" state.
    if not question:
        logging.info("No question for group %s (question_day=%s, question_hour=%s) — creating on-demand",
                     group.group_id, question_day, group.question_hour)
        try:
            question = create_today_question_for_group(db, group)
        except Exception:
            logging.exception("On-demand question creation failed for group %s", group.group_id)
    if not question:
        raise HTTPException(status_code=404, detail="No question for today")

    options_list = json.loads(question.options) if question.options else []
    option_counts = get_option_counts(question.id, db)
    total_votes = db.query(func.count(Vote.id)).filter(Vote.question_id == question.id).scalar() or 0

    user_vote = get_user_vote(user.id, question.id, db)
    user_streak = user.answer_streak
    longest_streak = user.longest_answer_streak

    # For free_text questions, include all text answers so users can see what everyone wrote
    text_answers = None
    base_url = str(request.base_url).rstrip('/')
    if question.question_type == QuestionTypeEnum.FREE_TEXT:
        text_answers = get_text_answers(question.id, db, base_url)

    # Include who answered what for all question types (only if user has voted)
    answer_details = get_answer_details(question.id, db, base_url) if total_votes > 0 else None

    # Resolve featured member name if {member} placeholder was used
    featured_member = None
    if question.featured_member_id:
        fm = db.query(User).filter(User.id == question.featured_member_id).first()
        if fm:
            featured_member = fm.display_name

    return DailyQuestionResponse(
        id=question.id, question_id=question.question_id,
        question_text=question.question_text, question_type=question.question_type,
        options=options_list, option_counts=option_counts,
        question_date=question.question_date, is_active=question.is_active,
        total_votes=total_votes, allow_multiple=question.allow_multiple,
        user_vote=user_vote, user_streak=user_streak, longest_streak=longest_streak,
        text_answers=text_answers, answer_details=answer_details,
        featured_member=featured_member,
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

    # Resolve featured member name
    featured_member = None
    if question.featured_member_id:
        fm = db.query(User).filter(User.id == question.featured_member_id).first()
        if fm:
            featured_member = fm.display_name

    base_url = str(request.base_url).rstrip('/')
    response = {
        "success": True, "question_type": question.question_type.value,
        "vote_count_a": vote_count_a, "vote_count_b": vote_count_b,
        "total_votes": total_votes, "option_counts": option_counts,
        "options": options_list, "user_answer": user_answer_value,
        "current_streak": streak.current_streak, "longest_streak": streak.longest_streak,
        "answer_details": get_answer_details(question.id, db, base_url),
        "featured_member": featured_member,
    }
    if question.question_type == QuestionTypeEnum.FREE_TEXT:
        response["text_answers"] = get_text_answers(question.id, db, base_url)

    # ── Broadcast real-time updates to WebSocket clients ──
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    vote_ws_data = {
        "question_id": question.question_id,
        "option_counts": option_counts,
        "total_votes": total_votes,
        "allow_multiple": question.allow_multiple,
        "options": options_list,
        "user": {
            "display_name": user.display_name,
            "color_avatar": user.color_avatar,
            "voted": user_answer_value,
        },
    }
    streak_ws_data = {
        "user_id": user.user_id,
        "display_name": user.display_name,
        "current_streak": streak.current_streak,
        "longest_streak": streak.longest_streak,
    }
    if loop and loop.is_running():
        asyncio.ensure_future(ws_manager.broadcast_vote_update(group.group_id, question.question_id, vote_ws_data))
        asyncio.ensure_future(ws_manager.broadcast_streak_update(group.group_id, streak_ws_data))
    else:
        logging.debug("No running event loop; skipping WS broadcast for vote")

    return response


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

    base_url = str(request.base_url).rstrip('/')
    result = []
    for q in questions:
        opts = json.loads(q.options) if q.options else []
        oc = get_option_counts(q.id, db)
        tv = db.query(func.count(Vote.id)).filter(Vote.question_id == q.id).scalar() or 0
        user_vote = get_user_vote(user.id, q.id, db)

        # Resolve featured member name
        featured_member = None
        if q.featured_member_id:
            fm = db.query(User).filter(User.id == q.featured_member_id).first()
            if fm:
                featured_member = fm.display_name

        entry = {
            "question_id": q.question_id, "question_text": q.question_text,
            "question_type": q.question_type.value,
            "option_a": q.option_a, "option_b": q.option_b,
            "options": opts, "option_counts": oc, "question_date": q.question_date,
            "is_active": q.is_active,
            "vote_count_a": oc.get(opts[0], 0) if opts else 0,
            "vote_count_b": oc.get(opts[1], 0) if len(opts) > 1 else 0,
            "total_votes": tv, "allow_multiple": getattr(q, "allow_multiple", False),
            "user_vote": user_vote,
            "answer_details": get_answer_details(q.id, db, base_url) if tv > 0 else None,
            "featured_member": featured_member,
        }
        if q.question_type == QuestionTypeEnum.FREE_TEXT:
            entry["text_answers"] = get_text_answers(q.id, db, base_url)
        result.append(entry)
    return {"group_id": group_id, "total_count": total_count, "skip": skip, "limit": limit, "questions": result}


# ============= Group Creator Question Management =============

@router.get("/groups/{group_id}/leaderboard")
@limiter.limit("60/minute")
def get_leaderboard(request: Request, group_id: str, db: Session = Depends(get_db)):
    """Get group leaderboard by answer streak (group member, authenticated)."""
    group = get_group_by_id(group_id, db)
    user = get_user_for_group(request, group, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    members = db.query(User).filter(User.group_id == group.id).all()
    leaderboard = sorted(members, key=lambda x: (x.answer_streak, x.longest_answer_streak), reverse=True)
    group_streak = max((m.answer_streak for m in members), default=0)
    group_longest_streak = max((m.longest_answer_streak for m in members), default=0)
    base_url = str(request.base_url).rstrip('/')
    return {
        "group_streak": group_streak,
        "group_longest_streak": group_longest_streak,
        "members": [
            {
                "display_name": m.display_name, "color_avatar": m.color_avatar,
                "avatar_url": get_avatar_url(m.avatar_filename, base_url),
                "answer_streak": m.answer_streak, "longest_answer_streak": m.longest_answer_streak,
            }
            for m in leaderboard
        ],
    }


@router.get("/groups/{group_id}/question-status")
@limiter.limit("60/minute")
def get_question_status(request: Request, group_id: str, db: Session = Depends(get_db)):
    """Get question exhaustion status for a group (group creator only)."""
    group = get_group_by_id(group_id, db)
    user = get_user_for_group(request, group, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if group.creator_id != user.id:
        raise HTTPException(status_code=403, detail="Only the group creator can view question status")
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
