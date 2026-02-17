"""
Background scheduler for creating daily questions.

Provides:
- create_daily_questions_for_today(): batch question creation for all groups
- create_today_question_for_group(): on-demand question creation for one group
- background_scheduler(): thread target that runs create_daily_questions_for_today periodically
"""

import asyncio
import json
import logging
import random
import time
from datetime import datetime, timezone

from sqlalchemy import func, and_

from core.database import SessionLocal
from core.models import (
    Group, User, DailyQuestion, QuestionSet, QuestionSetTemplate,
    QuestionTemplate, GroupQuestionSet, QuestionTypeEnum, UserDeviceToken,
)
from .push_notifications import push_service
from auth.utils import get_group_member_names, generate_duos


def _select_template(db, group, selected_today: set | None = None):
    """
    Select a random template for a group, avoiding repeats.
    Returns (template, exhausted) or (None, False) if nothing available.
    """
    # Collect templates from active assigned sets
    assigned = db.query(GroupQuestionSet).filter(
        GroupQuestionSet.group_id == group.id,
        GroupQuestionSet.is_active == True,
    ).all()
    template_candidates = []
    for a in assigned:
        s = db.get(QuestionSet, a.question_set_id)
        if not s:
            continue
        for assoc in db.query(QuestionSetTemplate).filter(
            QuestionSetTemplate.question_set_id == s.id
        ).all():
            if t := db.get(QuestionTemplate, assoc.template_id):
                template_candidates.append(t)

    # Fallback to any public template if none assigned
    if not template_candidates:
        template_candidates = db.query(QuestionTemplate).filter(
            QuestionTemplate.is_public == True
        ).all()

    if not template_candidates:
        return None, False

    # Get previously used template IDs for this group
    previously_used_ids = {
        t[0]
        for t in db.query(DailyQuestion.template_id)
        .filter(DailyQuestion.group_id == group.id, DailyQuestion.template_id.isnot(None))
        .distinct()
        .all()
    }

    available = [t for t in template_candidates if t.id not in previously_used_ids]
    exhausted = False
    if not available:
        available = template_candidates
        exhausted = True

    # Optionally exclude templates already selected today (cross-group de-dup)
    if selected_today is not None:
        filtered = (
            [t for t in available if t.id not in selected_today]
            or [t for t in template_candidates if t.id not in selected_today]
            or template_candidates
        )
        available = filtered

    return (random.choice(available), exhausted) if available else (None, False)


def _build_daily_question(db, group, tmpl):
    """
    Build a DailyQuestion from a template, generating options as needed.
    Returns the DailyQuestion instance or None if the group can't support the question type.
    """
    member_names = get_group_member_names(group, db)
    options_list = []
    option_a = None
    option_b = None

    if tmpl.question_type == QuestionTypeEnum.MEMBER_CHOICE:
        if len(member_names) < 2:
            return None
        options_list = member_names
    elif tmpl.question_type == QuestionTypeEnum.DUO_CHOICE:
        if len(member_names) < 4:
            return None
        options_list = generate_duos(member_names)
    elif tmpl.question_type == QuestionTypeEnum.BINARY_VOTE:
        if tmpl.option_a_template and tmpl.option_b_template:
            options_list = [tmpl.option_a_template, tmpl.option_b_template]
        else:
            options_list = ["Yes", "No"]
    elif tmpl.question_type == QuestionTypeEnum.SINGLE_CHOICE:
        if tmpl.option_a_template and tmpl.option_b_template:
            options_list = [tmpl.option_a_template, tmpl.option_b_template]
        elif len(member_names) >= 2:
            options_list = member_names
    # FREE_TEXT gets no options

    if options_list:
        option_a = options_list[0]
        option_b = options_list[1] if len(options_list) > 1 else None

    return DailyQuestion(
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


# ============= Public API =============

def create_today_question_for_group(db, group):
    """
    Create today's daily question for a single group (on-demand).
    Returns the DailyQuestion or None.
    Retries with different templates if the first pick is incompatible with group size.
    """
    today = datetime.now(timezone.utc).date()
    if existing := db.query(DailyQuestion).filter(
        and_(DailyQuestion.group_id == group.id, func.date(DailyQuestion.question_date) == today)
    ).first():
        return existing

    tried: set[int] = set()
    for _ in range(20):  # max attempts to find a compatible template
        tmpl, _ = _select_template(db, group, tried)
        if not tmpl:
            return None
        tried.add(tmpl.id)

        dq = _build_daily_question(db, group, tmpl)
        if dq:
            db.add(dq)
            db.commit()
            db.refresh(dq)
            return dq

    return None


def _process_group_question(db, group, today, selected_today):
    """Create today's question for a single group during the batch run."""
    if db.query(DailyQuestion).filter(
        and_(DailyQuestion.group_id == group.id, func.date(DailyQuestion.question_date) == today)
    ).first():
        return

    tmpl, exhausted = _select_template(db, group, selected_today)
    if not tmpl:
        logging.warning("No templates available for group %s", group.group_id)
        return

    selected_today.add(tmpl.id)

    if exhausted and group.creator_id:
        logging.warning(
            "All questions exhausted for group %s. Cycling back. Admin user_id: %s",
            group.group_id, group.creator_id,
        )

    dq = _build_daily_question(db, group, tmpl)
    if not dq:
        logging.warning(
            "Skipping daily question for group %s - not enough members for %s",
            group.group_id, tmpl.question_type,
        )
        return

    db.add(dq)

    if exhausted:
        logging.info("Question cycle reset for group %s - all templates used", group.group_id)


def _run_daily_question_creation(db):
    """Core logic for creating daily questions for all groups."""
    today = datetime.now(timezone.utc).date()
    groups = db.query(Group).all()
    selected_today: set[int] = set()

    for group in groups:
        _process_group_question(db, group, today, selected_today)

    db.commit()

    if push_service.is_enabled():
        _send_new_question_notifications(db, groups, today)


def create_daily_questions_for_today():
    """
    Create daily questions for all groups with smart selection:
    - Never repeat a question within the same group (until all exhausted)
    - Different groups get different questions on the same day
    - Sends push notifications for new questions
    """
    db = SessionLocal()
    try:
        _run_daily_question_creation(db)
    except Exception:
        logging.exception("create_daily_questions_for_today failed, rolling back DB")
        db.rollback()
    finally:
        db.close()


def _send_new_question_notifications(db, groups, today):
    """Send push notifications for newly created daily questions."""
    for group in groups:
        try:
            question = db.query(DailyQuestion).filter(
                and_(DailyQuestion.group_id == group.id, func.date(DailyQuestion.question_date) == today)
            ).first()
            if not question:
                continue

            group_user_ids = [
                m.id for m in db.query(User).filter(User.group_id == group.id, User.is_suspended == False).all()
            ]
            if device_tokens := db.query(UserDeviceToken).filter(
                UserDeviceToken.user_id.in_(group_user_ids),
                UserDeviceToken.is_active == True,
            ).all():
                tokens = [dt.token for dt in device_tokens]
                asyncio.run(
                    push_service.send_daily_question_notification(
                        tokens=tokens,
                        group_name=group.name,
                        question_preview=question.question_text[:100],
                    )
                )
                logging.info("Push notification sent to %d devices for group %s", len(tokens), group.group_id)
        except Exception as e:
            logging.error("Failed to send push notification for group %s: %s", group.group_id, e)


def background_scheduler(interval_seconds: int = 86400):
    """Thread target: run create_daily_questions_for_today at startup then every interval."""
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
