"""Background scheduler for creating daily questions.

Each group has its own "new day" boundary defined by `group.question_hour` (0-23 UTC).
The group's daily question rolls over at that hour, so different groups get new questions
at different times of day.

Provides:
- compute_question_hour(created_at): deterministic rollover hour for a group
- get_group_question_day(group): the current "question day" for a group
- create_daily_questions_for_all(): batch question creation for all groups
- create_today_question_for_group(): on-demand question creation for one group
- background_scheduler(): thread target that runs every hour to check all groups
"""

import asyncio
import json
import logging
import random
import time
from datetime import datetime, timezone, timedelta, date as datetype

from sqlalchemy import func, and_

from core.database import SessionLocal
from core.models import (
    Group, User, DailyQuestion, QuestionSet, QuestionSetTemplate,
    QuestionTemplate, GroupQuestionSet, QuestionTypeEnum, UserDeviceToken,
    Vote,
)
from .push_notifications import push_service
from .ws_manager import manager as ws_manager
from auth.utils import get_group_member_names, generate_duos

# ============= Per-Group Day Helpers =============

DEFAULT_QUESTION_HOUR = 0  # fallback if group.question_hour is not set


def compute_question_hour(created_at: datetime | None = None) -> int:
    """Compute the question_hour for a new group.
    
    Based on the creation hour + a random offset of ±3 hours.
    This means a group created at 14:00 UTC might get a rollover hour
    anywhere between 11:00 and 17:00 UTC.
    
    The result is always 0-23.
    """
    if created_at is not None:
        base_hour = created_at.hour
    else:
        base_hour = datetime.now(timezone.utc).hour
    offset = random.randint(-3, 3)
    return (base_hour + offset) % 24


def get_group_question_day(group) -> datetype:
    """Return the current 'question day' for a group based on its question_hour.
    
    The group's day flips at question_hour UTC. Before that hour, we're still
    on the previous calendar day (from the group's perspective).
    
    Example: group.question_hour = 14
      - At 13:59 UTC Feb 19 → question day is Feb 18
      - At 14:00 UTC Feb 19 → question day is Feb 19
    """
    qh = group.question_hour if group.question_hour is not None else DEFAULT_QUESTION_HOUR
    now = datetime.now(timezone.utc)
    if now.hour < qh:
        return (now - timedelta(days=1)).date()
    return now.date()


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


def _build_daily_question(db, group, tmpl, question_day=None):
    """
    Build a DailyQuestion from a template, generating options as needed.
    Returns the DailyQuestion instance or None if the group can't support the question type.
    
    Supports {member} placeholder in question_text: replaced with a random group member's name.
    The chosen member is stored in featured_member_id.
    
    question_day: the group's logical question day (date). Used to set question_date so that
    queries by date match correctly even when the calendar date differs from the group's day.
    """
    members = db.query(User).filter(User.group_id == group.id).all()
    member_names = [m.display_name for m in members]
    options_list = []
    option_a = None
    option_b = None
    featured_member_id = None

    # Resolve {member} placeholder if present in the question text
    question_text = tmpl.question_text
    if "{member}" in question_text and members:
        chosen = random.choice(members)
        question_text = question_text.replace("{member}", chosen.display_name)
        featured_member_id = chosen.id

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

    # Build the question_date: use the group's logical question day so date-based queries work
    if question_day is not None:
        from datetime import time as dt_time
        qd = datetime.combine(question_day, dt_time(), tzinfo=timezone.utc)
    else:
        qd = datetime.now(timezone.utc)

    return DailyQuestion(
        group_id=group.id,
        template_id=tmpl.id,
        question_text=question_text,
        option_a=option_a,
        option_b=option_b,
        options=json.dumps(options_list) if options_list else None,
        question_type=tmpl.question_type,
        allow_multiple=getattr(tmpl, "allow_multiple", False),
        is_active=True,
        featured_member_id=featured_member_id,
        question_date=qd,
    )


# ============= Streak / Deactivation Helpers =============

def _deactivate_old_questions(db, group):
    """Deactivate all previously active questions for a group.
    
    Called before creating a new daily question so that only one question
    is active per group at any time.
    """
    old_active = db.query(DailyQuestion).filter(
        DailyQuestion.group_id == group.id,
        DailyQuestion.is_active == True,
    ).all()
    for q in old_active:
        q.is_active = False
    if old_active:
        db.flush()  # ensure deactivation is visible to subsequent queries


def _check_streaks_on_new_question(db, group):
    """Check streaks when a new question is about to be created.
    
    For each member: if the most recent (now-deactivated) question was NOT
    answered by the member, reset their streak to 0. This means a streak is
    only broken when a user completely misses a question.
    
    Also syncs longest_streak from UserGroupStreak to User.longest_answer_streak
    for ALL members (voters and non-voters) to keep the data consistent.
    """
    from core.models import UserGroupStreak

    # Find the most recent question that was just deactivated
    last_question = (
        db.query(DailyQuestion)
        .filter(
            DailyQuestion.group_id == group.id,
            DailyQuestion.is_active == False,
        )
        .order_by(DailyQuestion.question_date.desc(), DailyQuestion.id.desc())
        .first()
    )
    if not last_question:
        return  # No previous question — nothing to check

    members = db.query(User).filter(User.group_id == group.id).all()
    for member in members:
        voted = (
            db.query(Vote)
            .filter(Vote.question_id == last_question.id, Vote.user_id == member.id)
            .first()
        )

        streak = (
            db.query(UserGroupStreak)
            .filter(
                UserGroupStreak.user_id == member.id,
                UserGroupStreak.group_id == group.id,
            )
            .first()
        )

        if not voted:
            # User missed the last question — reset their streak
            if streak:
                streak.current_streak = 0
            member.answer_streak = 0

        # Always sync longest_streak from UserGroupStreak → User model
        # so leaderboard/members endpoints return correct data
        if streak:
            member.longest_answer_streak = max(
                streak.longest_streak or 0,
                member.longest_answer_streak or 0,
            )
            member.answer_streak = streak.current_streak


# ============= Public API =============

def create_today_question_for_group(db, group, exclude_template_ids: set | None = None):
    """
    Create today's daily question for a single group (on-demand).
    Uses the group's per-group question_hour to determine the current "question day".
    Returns the DailyQuestion or None.
    Retries with different templates if the first pick is incompatible with group size.
    exclude_template_ids: optional set of template IDs to skip (e.g. the just-deleted question).
    """
    question_day = get_group_question_day(group)
    if existing := db.query(DailyQuestion).filter(
        and_(DailyQuestion.group_id == group.id, func.date(DailyQuestion.question_date) == question_day,
             DailyQuestion.is_active == True)
    ).first():
        return existing

    # Guard: don't create a new question if the last one was created less than 20h ago.
    # This prevents rapid question cycling when question_hour jitter causes day boundaries
    # to shift (e.g. group created at 14:00, question_hour set to 12:00, so the "day"
    # immediately rolls over and creates a second question).
    MIN_QUESTION_GAP_HOURS = 20
    last_question = (
        db.query(DailyQuestion)
        .filter(DailyQuestion.group_id == group.id)
        .order_by(DailyQuestion.created_at.desc())
        .first()
    )
    if last_question and last_question.created_at:
        # Ensure timezone-aware comparison (DB may store naive datetimes)
        created = last_question.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        hours_since_last = (datetime.now(timezone.utc) - created).total_seconds() / 3600
        if hours_since_last < MIN_QUESTION_GAP_HOURS:
            logging.debug(
                "Skipping question creation for group %s — last question was %.1fh ago (min %dh)",
                group.group_id, hours_since_last, MIN_QUESTION_GAP_HOURS,
            )
            # Return the last question if it's still active, otherwise None
            if last_question.is_active:
                return last_question
            return None

    # Deactivate old questions and check streaks before creating the new one
    _deactivate_old_questions(db, group)
    _check_streaks_on_new_question(db, group)

    tried: set[int] = set(exclude_template_ids) if exclude_template_ids else set()
    for _ in range(20):  # max attempts to find a compatible template
        tmpl, _ = _select_template(db, group, tried)
        if not tmpl:
            return None
        tried.add(tmpl.id)

        dq = _build_daily_question(db, group, tmpl, question_day)
        if dq:
            db.add(dq)
            db.commit()
            db.refresh(dq)
            # Broadcast new question to group-level WS clients
            _broadcast_new_question_ws(db, group, question_day)
            return dq

    return None


def _process_group_question(db, group, selected_today):
    """Create a question for a single group if its 'question day' has rolled over."""
    question_day = get_group_question_day(group)
    if db.query(DailyQuestion).filter(
        and_(DailyQuestion.group_id == group.id, func.date(DailyQuestion.question_date) == question_day)
    ).first():
        return

    # Guard: don't create a new question if the last one was created less than 20h ago
    MIN_QUESTION_GAP_HOURS = 20
    last_question = (
        db.query(DailyQuestion)
        .filter(DailyQuestion.group_id == group.id)
        .order_by(DailyQuestion.created_at.desc())
        .first()
    )
    if last_question and last_question.created_at:
        # Ensure timezone-aware comparison (DB may store naive datetimes)
        created = last_question.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        hours_since_last = (datetime.now(timezone.utc) - created).total_seconds() / 3600
        if hours_since_last < MIN_QUESTION_GAP_HOURS:
            logging.debug(
                "Scheduler: skipping group %s — last question was %.1fh ago (min %dh)",
                group.group_id, hours_since_last, MIN_QUESTION_GAP_HOURS,
            )
            return

    # Deactivate old questions and check streaks before creating the new one
    _deactivate_old_questions(db, group)
    _check_streaks_on_new_question(db, group)

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

    dq = _build_daily_question(db, group, tmpl, question_day)
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
    """Core logic: check all groups and create questions for those whose day has rolled over."""
    groups = db.query(Group).all()
    selected_today: set[int] = set()
    groups_needing_push: list[tuple] = []  # (group, question_day)

    for group in groups:
        question_day = get_group_question_day(group)
        had_question = db.query(DailyQuestion).filter(
            and_(DailyQuestion.group_id == group.id, func.date(DailyQuestion.question_date) == question_day)
        ).first()
        if not had_question:
            _process_group_question(db, group, selected_today)
            groups_needing_push.append((group, question_day))

    db.commit()

    # Broadcast new_question to WebSocket clients and send push notifications
    for group, question_day in groups_needing_push:
        _broadcast_new_question_ws(db, group, question_day)
        if push_service.is_enabled():
            _send_new_question_notification(db, group, question_day)
            _send_streak_at_risk_reminders(db, group)


def create_daily_questions_for_all():
    """
    Check all groups and create daily questions for those whose per-group day has rolled over.
    - Each group's "new day" is determined by its question_hour (0-23 UTC)
    - Never repeat a question within the same group (until all exhausted)
    - Different groups get different questions on the same day
    - Sends push notifications for new questions
    """
    db = SessionLocal()
    try:
        _run_daily_question_creation(db)
    except Exception:
        logging.exception("create_daily_questions_for_all failed, rolling back DB")
        db.rollback()
    finally:
        db.close()


# Keep old name as alias for backward compatibility
create_daily_questions_for_today = create_daily_questions_for_all


def _send_new_question_notification(db, group, question_day):
    """Send push notification for a newly created daily question for one group."""
    try:
        question = db.query(DailyQuestion).filter(
            and_(DailyQuestion.group_id == group.id, func.date(DailyQuestion.question_date) == question_day)
        ).first()
        if not question:
            return

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


def _broadcast_new_question_ws(db, group, question_day):
    """Broadcast new_question event to all group-level WebSocket clients."""
    try:
        question = db.query(DailyQuestion).filter(
            and_(DailyQuestion.group_id == group.id,
                 func.date(DailyQuestion.question_date) == question_day,
                 DailyQuestion.is_active == True)
        ).first()
        if not question:
            return

        options_list = json.loads(question.options) if question.options else []

        # Resolve featured member name
        featured_member = None
        if question.featured_member_id:
            fm = db.query(User).filter(User.id == question.featured_member_id).first()
            if fm:
                featured_member = fm.display_name

        question_data = {
            "question_id": question.question_id,
            "question_text": question.question_text,
            "question_type": question.question_type.value,
            "options": options_list,
            "question_date": question.question_date.isoformat(),
            "is_active": True,
            "allow_multiple": question.allow_multiple,
            "featured_member": featured_member,
        }

        # Also build streak_reset data for members whose streaks were just reset
        from core.models import UserGroupStreak
        members = db.query(User).filter(User.group_id == group.id).all()
        streak_resets = []
        for m in members:
            s = db.query(UserGroupStreak).filter(
                UserGroupStreak.user_id == m.id, UserGroupStreak.group_id == group.id
            ).first()
            if s:
                streak_resets.append({
                    "user_id": m.user_id,
                    "display_name": m.display_name,
                    "current_streak": s.current_streak,
                    "longest_streak": s.longest_streak,
                })

        asyncio.run(ws_manager.broadcast_new_question(group.group_id, question_data))
        if streak_resets:
            asyncio.run(ws_manager.broadcast_streak_update(group.group_id, {
                "reason": "question_rollover",
                "members": streak_resets,
            }))
        logging.info("WS broadcast new_question for group %s", group.group_id)
    except Exception as e:
        logging.error("Failed to broadcast new_question for group %s: %s", group.group_id, e)


def _send_streak_at_risk_reminders(db, group):
    """Send FCM push reminders to members who didn't answer the previous question.

    Called after a new question is created. Members who missed the last question
    and had a streak > 0 get a 'streak at risk' notification.
    """
    try:
        from core.models import UserGroupStreak

        members = db.query(User).filter(User.group_id == group.id, User.is_suspended == False).all()
        for member in members:
            streak = db.query(UserGroupStreak).filter(
                UserGroupStreak.user_id == member.id, UserGroupStreak.group_id == group.id
            ).first()
            # Streak was just reset to 0 — they missed the previous question
            # But we only remind them if they previously had a streak (longest_streak > 0)
            if streak and streak.current_streak == 0 and streak.longest_streak > 0:
                device_tokens = db.query(UserDeviceToken).filter(
                    UserDeviceToken.user_id == member.id,
                    UserDeviceToken.is_active == True,
                ).all()
                if device_tokens:
                    tokens = [dt.token for dt in device_tokens]
                    asyncio.run(
                        push_service.send_reminder_notification(
                            tokens=tokens,
                            group_name=group.name,
                            streak_count=streak.longest_streak,
                        )
                    )
                    logging.info("Streak-at-risk reminder sent to %s in group %s",
                                 member.display_name, group.group_id)
    except Exception as e:
        logging.error("Failed to send streak reminders for group %s: %s", group.group_id, e)


SCHEDULER_CHECK_INTERVAL = 3600  # Check every hour


def background_scheduler(interval_seconds: int = 86400):
    """Thread target: check all groups hourly and create questions when their day rolls over.
    
    Each group has a `question_hour` (0-23 UTC) that defines when its "new day" starts.
    The scheduler runs every hour to check which groups need new questions.
    
    Even if this thread fails, individual endpoints will create questions
    on-demand via create_today_question_for_group() as a fallback.
    """
    try:
        create_daily_questions_for_all()
        logging.info("Initial question creation check completed")
    except Exception:
        logging.exception("Initial create_daily_questions_for_all call failed in scheduler")
    while True:
        logging.info("Scheduler sleeping %d seconds until next check", SCHEDULER_CHECK_INTERVAL)
        try:
            time.sleep(SCHEDULER_CHECK_INTERVAL)
        except Exception:
            logging.exception("Scheduler sleep interrupted, retrying in 60s")
            time.sleep(60)
            continue
        try:
            create_daily_questions_for_all()
            logging.info("Scheduled question creation check completed")
        except Exception:
            logging.exception("Scheduled create_daily_questions_for_all call failed, will retry next cycle")
