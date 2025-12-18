import logging
from typing import List, Dict

from sqlalchemy.orm import Session

from database import SessionLocal
from models import (
    QuestionTemplate,
    QuestionSet,
    QuestionSetTemplate,
    QuestionTypeEnum,
)


DEFAULT_SET_NAME = "Default"
DEFAULT_SET_DESCRIPTION = "Default question set for new groups"


def _default_templates() -> List[Dict]:
    """Return the canonical list of default question templates.

    Note: Keep texts as-is; categorize as 'Default'.
    """
    return [
        {"category": "Default", "question_text": "Who is most likely to cheat on their partner?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would you trust least with a secret?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who is the biggest backstabber?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Would you abandon a friend for €10,000?", "option_a_template": "Yes", "option_b_template": "No", "question_type": QuestionTypeEnum.BINARY_VOTE},
        {"category": "Default", "question_text": "Who do you think is secretly jealous of you?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would sell you out to save themselves?", "question_type": QuestionTypeEnum.MEMBER_CHOICE, "allow_multiple": True},
        {"category": "Default", "question_text": "Which duo would most likely get arrested together?", "question_type": QuestionTypeEnum.DUO_CHOICE},
        {"category": "Default", "question_text": "Which duo has the most toxic friendship?", "question_type": QuestionTypeEnum.DUO_CHOICE},
        {"category": "Default", "question_text": "Describe the most embarrassing thing someone in this group did", "question_type": QuestionTypeEnum.FREE_TEXT},
        {"category": "Default", "question_text": "What's a secret you know about someone here that would shock everyone?", "question_type": QuestionTypeEnum.FREE_TEXT},
        {"category": "Default", "question_text": "Who would leak the group chat if paid enough?", "question_type": QuestionTypeEnum.MEMBER_CHOICE, "allow_multiple": True},
        {"category": "Default", "question_text": "Who is quietly keeping receipts on everyone else?", "question_type": QuestionTypeEnum.MEMBER_CHOICE, "allow_multiple": True},
        {"category": "Default", "question_text": "Who would fake an illness to skip a friend's wedding?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Which duo is most likely to start a doomed business together?", "question_type": QuestionTypeEnum.DUO_CHOICE},
        {"category": "Default", "question_text": "Which duo would instantly sell out for fame?", "question_type": QuestionTypeEnum.DUO_CHOICE},
        {"category": "Default", "question_text": "Would you expose your closest friend's worst secret for five minutes of internet fame?", "option_a_template": "Absolutely", "option_b_template": "Never", "question_type": QuestionTypeEnum.BINARY_VOTE},
        {"category": "Default", "question_text": "Would you rather be loved by everyone here or feared by everyone here?", "option_a_template": "Loved", "option_b_template": "Feared", "question_type": QuestionTypeEnum.BINARY_VOTE},
        {"category": "Default", "question_text": "Share a petty thought you have about someone in this room", "question_type": QuestionTypeEnum.FREE_TEXT},
        {"category": "Default", "question_text": "What rumor about you would hurt the most if everyone believed it?", "question_type": QuestionTypeEnum.FREE_TEXT},
        {"category": "Default", "question_text": "Who would secretly enjoy being cancelled?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
    ]


def initialize_default_question_set():
    """Create/ensure the Default question set and its templates exist.

    Idempotent: safe to call on every startup.
    - Ensures a QuestionSet named 'Default' exists and is public
    - Ensures templates exist (matched by question_text + question_type)
    - Ensures associations between the set and templates
    - Updates description away from any previous 'extreme' wording
    """
    db: Session = SessionLocal()
    try:
        # Ensure the default set exists
        default_set = db.query(QuestionSet).filter(QuestionSet.name == DEFAULT_SET_NAME).first()
        if not default_set:
            default_set = QuestionSet(
                name=DEFAULT_SET_NAME,
                description=DEFAULT_SET_DESCRIPTION,
                is_public=True,
            )
            db.add(default_set)
            db.commit()
            db.refresh(default_set)
        else:
            # Normalize description and visibility
            changed = False
            if not default_set.description or "extreme" in (default_set.description or "").lower():
                default_set.description = DEFAULT_SET_DESCRIPTION
                changed = True
            if default_set.is_public is not True:
                default_set.is_public = True
                changed = True
            if changed:
                db.commit()

        # Ensure templates and associations
        for t in _default_templates():
            # Try to find by question_text + question_type to avoid duplicates across runs
            existing = (
                db.query(QuestionTemplate)
                .filter(
                    QuestionTemplate.question_text == t["question_text"],
                    QuestionTemplate.question_type == t["question_type"],
                )
                .first()
            )
            if not existing:
                existing = QuestionTemplate(
                    category=t.get("category", "Default"),
                    question_text=t["question_text"],
                    option_a_template=t.get("option_a_template"),
                    option_b_template=t.get("option_b_template"),
                    question_type=t["question_type"],
                    allow_multiple=t.get("allow_multiple", False),
                    is_public=True,
                )
                db.add(existing)
                db.flush()
            else:
                # Keep allow_multiple in sync with the seed definition
                desired_multi = t.get("allow_multiple", False)
                if getattr(existing, "allow_multiple", False) != desired_multi:
                    existing.allow_multiple = desired_multi

            # Ensure association to Default set
            assoc_exists = (
                db.query(QuestionSetTemplate)
                .filter(
                    QuestionSetTemplate.question_set_id == default_set.id,
                    QuestionSetTemplate.template_id == existing.id,
                )
                .first()
            )
            if not assoc_exists:
                db.add(QuestionSetTemplate(question_set_id=default_set.id, template_id=existing.id))

        db.commit()
    except Exception:
        logging.exception("initialize_default_question_set failed")
        db.rollback()
    finally:
        db.close()


def assign_default_set_to_unassigned_groups():
    """Assign the Default set to any groups without an active question set.

    Idempotent: skips groups already assigned. Useful for existing groups
    created before this feature.
    """
    db: Session = SessionLocal()
    try:
        default_set = db.query(QuestionSet).filter(QuestionSet.name == DEFAULT_SET_NAME).first()
        if not default_set:
            initialize_default_question_set()
            default_set = db.query(QuestionSet).filter(QuestionSet.name == DEFAULT_SET_NAME).first()
            if not default_set:
                logging.warning("Default set not found; cannot assign to groups")
                return

        # Late import to avoid circulars at module import time
        from models import Group, GroupQuestionSet

        groups = db.query(Group).all()
        for g in groups:
            has_set = db.query(GroupQuestionSet).filter(
                GroupQuestionSet.group_id == g.id,
                GroupQuestionSet.is_active == True,
            ).first()
            if not has_set:
                db.add(GroupQuestionSet(group_id=g.id, question_set_id=default_set.id, is_active=True))
        db.commit()
    except Exception:
        logging.exception("assign_default_set_to_unassigned_groups failed")
        db.rollback()
    finally:
        db.close()
