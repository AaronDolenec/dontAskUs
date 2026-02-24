import logging
from typing import List, Dict

from sqlalchemy.orm import Session

from core.database import SessionLocal
from core.models import (
    QuestionTemplate,
    QuestionSet,
    QuestionSetTemplate,
    QuestionTypeEnum,
)


DEFAULT_SET_NAME = "Default"
DEFAULT_SET_DESCRIPTION = "Default question set for new groups"


def _default_templates() -> List[Dict]:
    """Return the canonical list of default question templates.

    Distribution philosophy:
    - ~50% MEMBER_CHOICE — vote for one group member
    - ~15% DUO_CHOICE — vote for a pair of members
    - ~15% {member} placeholder questions — personalized to a random member
    - ~10% SINGLE_CHOICE / BINARY_VOTE — classic either/or picks
    - ~10% FREE_TEXT — open-ended (rare, keeps things interesting)

    All questions are unique, creative, and designed for friend groups.
    """
    return [
        # ===== MEMBER_CHOICE (vote for one member) =====
        {"category": "Default", "question_text": "Who would survive the longest in a zombie apocalypse?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who is secretly a genius but hides it?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would be the worst roommate?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who is most likely to become famous?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would you call first if you needed to hide a body?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who has the most questionable search history?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would accidentally start a cult?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who is most likely to go viral on social media?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would be the best spy?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who talks the most trash but can't back it up?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who is most likely to cry during a movie?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would eat something off the floor without hesitation?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who is the biggest drama queen?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would survive a horror movie?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who gives the worst advice but thinks it's gold?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would be the first to betray the group on a reality show?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who is secretly the most competitive?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would you trust to plan your surprise birthday party?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who has the best taste in music?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would get lost in their own city?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who is most likely to win a cooking competition?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would last the longest without their phone?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who is the worst liar in the group?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would accidentally cause an international incident?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would be the funniest stand-up comedian?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who is most likely to marry a celebrity?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would be the best leader in a crisis?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would get scammed the easiest?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who is secretly the kindest person in the group?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who takes the longest to get ready?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would be the best villain in a movie?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who is most likely to become a millionaire?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would survive alone on a deserted island the longest?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who has the most chaotic energy?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would be the worst at keeping a surprise?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who is most likely to show up to their own wedding late?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would win in a group-wide pillow fight?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would be the most entertaining on a podcast?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who is the biggest people-pleaser?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who has the most random useless talent?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would start a fight at a family dinner?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who is most likely to accidentally text the wrong person something embarrassing?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would be the best teacher?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who sleeps the most?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would go the furthest on a dare?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who is the most likely to ghost someone?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would have the best mugshot?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},

        # ===== MEMBER_CHOICE with allow_multiple =====
        {"category": "Default", "question_text": "Who would you want on your team in a bar trivia night?", "question_type": QuestionTypeEnum.MEMBER_CHOICE, "allow_multiple": True},
        {"category": "Default", "question_text": "Who would you trust with your phone unlocked for 5 minutes?", "question_type": QuestionTypeEnum.MEMBER_CHOICE, "allow_multiple": True},
        {"category": "Default", "question_text": "Who would you want with you during an alien invasion?", "question_type": QuestionTypeEnum.MEMBER_CHOICE, "allow_multiple": True},
        {"category": "Default", "question_text": "Who could you live with for a full year without going insane?", "question_type": QuestionTypeEnum.MEMBER_CHOICE, "allow_multiple": True},

        # ===== DUO_CHOICE (vote for a pair of members) =====
        {"category": "Default", "question_text": "Which duo would most likely get arrested together?", "question_type": QuestionTypeEnum.DUO_CHOICE},
        {"category": "Default", "question_text": "Which duo would win The Amazing Race?", "question_type": QuestionTypeEnum.DUO_CHOICE},
        {"category": "Default", "question_text": "Which duo has the most unhinged group chat energy?", "question_type": QuestionTypeEnum.DUO_CHOICE},
        {"category": "Default", "question_text": "Which duo would start the most successful business together?", "question_type": QuestionTypeEnum.DUO_CHOICE},
        {"category": "Default", "question_text": "Which duo would make the best comedy movie?", "question_type": QuestionTypeEnum.DUO_CHOICE},
        {"category": "Default", "question_text": "Which duo would cause the most chaos at a party?", "question_type": QuestionTypeEnum.DUO_CHOICE},
        {"category": "Default", "question_text": "Which duo should never be left unsupervised?", "question_type": QuestionTypeEnum.DUO_CHOICE},
        {"category": "Default", "question_text": "Which duo would survive a haunted house together?", "question_type": QuestionTypeEnum.DUO_CHOICE},
        {"category": "Default", "question_text": "Which duo would dominate a dance battle?", "question_type": QuestionTypeEnum.DUO_CHOICE},
        {"category": "Default", "question_text": "Which duo is secretly plotting something at all times?", "question_type": QuestionTypeEnum.DUO_CHOICE},
        {"category": "Default", "question_text": "Which duo would have the best travel vlog?", "question_type": QuestionTypeEnum.DUO_CHOICE},
        {"category": "Default", "question_text": "Which duo argues like an old married couple?", "question_type": QuestionTypeEnum.DUO_CHOICE},
        {"category": "Default", "question_text": "Which duo would be the most dangerous on a game show?", "question_type": QuestionTypeEnum.DUO_CHOICE},

        # ===== {member} placeholder questions (personalized to a random member) =====
        {"category": "Default", "question_text": "What job would {member} be terrible at?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Who would {member} call first in an emergency?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "What animal best represents {member}?", "option_a_template": "Golden Retriever 🐕", "option_b_template": "Cat 🐱", "question_type": QuestionTypeEnum.BINARY_VOTE},
        {"category": "Default", "question_text": "Could {member} survive a week without Wi-Fi?", "option_a_template": "Easily", "option_b_template": "No chance", "question_type": QuestionTypeEnum.BINARY_VOTE},
        {"category": "Default", "question_text": "What would {member}'s autobiography be titled?", "question_type": QuestionTypeEnum.FREE_TEXT},
        {"category": "Default", "question_text": "On a scale from chill to chaos, where does {member} land?", "option_a_template": "Total chill 😌", "option_b_template": "Pure chaos 🔥", "question_type": QuestionTypeEnum.BINARY_VOTE},
        {"category": "Default", "question_text": "Would {member} rather fight 100 duck-sized horses or 1 horse-sized duck?", "option_a_template": "100 duck-sized horses", "option_b_template": "1 horse-sized duck", "question_type": QuestionTypeEnum.BINARY_VOTE},
        {"category": "Default", "question_text": "Who in the group does {member} secretly admire the most?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Rate {member}'s cooking skills", "option_a_template": "Chef's kiss 👨‍🍳", "option_b_template": "Fire hazard 🧯", "question_type": QuestionTypeEnum.BINARY_VOTE},
        {"category": "Default", "question_text": "Would {member} survive as a contestant on Survivor?", "option_a_template": "Winner material", "option_b_template": "First voted out", "question_type": QuestionTypeEnum.BINARY_VOTE},
        {"category": "Default", "question_text": "What is {member}'s most iconic catchphrase?", "question_type": QuestionTypeEnum.FREE_TEXT},
        {"category": "Default", "question_text": "Who is {member}'s secret twin in the group?", "question_type": QuestionTypeEnum.MEMBER_CHOICE},
        {"category": "Default", "question_text": "Would you trust {member} to cut your hair?", "option_a_template": "Absolutely", "option_b_template": "Never in a million years", "question_type": QuestionTypeEnum.BINARY_VOTE},
        {"category": "Default", "question_text": "What superpower would {member} misuse immediately?", "question_type": QuestionTypeEnum.FREE_TEXT},
        {"category": "Default", "question_text": "Rate {member}'s dance moves", "option_a_template": "Smooth 💃", "option_b_template": "Disaster 🪩", "question_type": QuestionTypeEnum.BINARY_VOTE},

        # ===== BINARY_VOTE (either/or) =====
        {"category": "Default", "question_text": "Would you rather have everyone in this group read your DMs or your search history?", "option_a_template": "DMs", "option_b_template": "Search history", "question_type": QuestionTypeEnum.BINARY_VOTE},
        {"category": "Default", "question_text": "Would you rather be stuck in an elevator with the group for 24 hours or go a month without seeing anyone?", "option_a_template": "Elevator chaos", "option_b_template": "Month alone", "question_type": QuestionTypeEnum.BINARY_VOTE},
        {"category": "Default", "question_text": "Would you rather know when you'll die or how you'll die?", "option_a_template": "When", "option_b_template": "How", "question_type": QuestionTypeEnum.BINARY_VOTE},
        {"category": "Default", "question_text": "Is it acceptable to recline your airplane seat?", "option_a_template": "Yes, I paid for it", "option_b_template": "No, it's rude", "question_type": QuestionTypeEnum.BINARY_VOTE},
        {"category": "Default", "question_text": "Pineapple on pizza?", "option_a_template": "Delicious 🍍", "option_b_template": "Criminal 🚫", "question_type": QuestionTypeEnum.BINARY_VOTE},
        {"category": "Default", "question_text": "Would you rather always have to say everything on your mind or never speak again?", "option_a_template": "Say everything", "option_b_template": "Never speak", "question_type": QuestionTypeEnum.BINARY_VOTE},

        # ===== FREE_TEXT (rare, open-ended) =====
        {"category": "Default", "question_text": "Describe this group in exactly three words", "question_type": QuestionTypeEnum.FREE_TEXT},
        {"category": "Default", "question_text": "What's one thing someone in this group has said that you'll never forget?", "question_type": QuestionTypeEnum.FREE_TEXT},
        {"category": "Default", "question_text": "What would be the name of a reality show about this group?", "question_type": QuestionTypeEnum.FREE_TEXT},
        {"category": "Default", "question_text": "If this group had a motto, what would it be?", "question_type": QuestionTypeEnum.FREE_TEXT},
        {"category": "Default", "question_text": "What's the most unhinged plan this group has ever had?", "question_type": QuestionTypeEnum.FREE_TEXT},
        {"category": "Default", "question_text": "Write a one-sentence roast of this group", "question_type": QuestionTypeEnum.FREE_TEXT},
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
        from core.models import Group, GroupQuestionSet

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
