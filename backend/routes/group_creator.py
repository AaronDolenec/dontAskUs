"""Group creator private question set endpoints (max 5 per group)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from database import get_db
from models import (
    Group, QuestionSet, QuestionTemplate, QuestionSetTemplate,
    GroupQuestionSet, GroupCustomSet, DailyQuestion, QuestionTypeEnum,
)
from utils import get_user_from_request

router = APIRouter(prefix="/api/groups/{group_id}/question-sets", tags=["Group Creator"])


def _require_group_creator(group_id: int, request: Request, db: Session):
    """Verify the request comes from the group creator. Returns (user, group)."""
    user = get_user_from_request(request, db)
    if not user or user.group_id != group_id:
        raise HTTPException(status_code=401, detail="Invalid authentication")
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if group.creator_id != user.id:
        raise HTTPException(status_code=403, detail="Only group creator can manage private sets")
    return user, group


@router.post("/private")
async def create_private_question_set(group_id: int, body: dict, request: Request, db: Session = Depends(get_db)):
    """Create a private question set for a group (max 5)."""
    user, group = _require_group_creator(group_id, request, db)

    existing_sets = db.query(func.count(GroupCustomSet.id)).filter(GroupCustomSet.group_id == group_id).scalar() or 0
    if existing_sets >= 5:
        raise HTTPException(status_code=400, detail="Maximum 5 private question sets per group reached")

    name = body.get("name", "").strip()
    if not name or len(name) < 3:
        raise HTTPException(status_code=400, detail="Set name must be at least 3 characters")
    if len(name) > 200:
        raise HTTPException(status_code=400, detail="Set name cannot exceed 200 characters")

    questions = body.get("questions", [])
    if not questions:
        raise HTTPException(status_code=400, detail="At least one question is required")
    if len(questions) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 questions per set")

    question_set = QuestionSet(
        name=name, is_public=False, creator_id=None,
        created_by_group_id=group_id, usage_count=0, created_at=datetime.now(timezone.utc),
    )
    db.add(question_set)
    db.flush()

    _add_templates(db, question_set.id, questions)

    db.add(GroupCustomSet(set_id=question_set.id, group_id=group_id, creator_user_id=user.id, created_at=datetime.now(timezone.utc)))
    group.total_sets_created = (group.total_sets_created or 0) + 1
    db.commit()

    return {"message": "Private question set created successfully", "set_id": question_set.id, "name": question_set.name,
            "question_count": len(questions), "is_public": False}


@router.get("/my")
async def list_group_creator_sets(
    group_id: int, request: Request, db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
):
    """List all private question sets for this group."""
    user, group = _require_group_creator(group_id, request, db)
    custom_sets = db.query(GroupCustomSet).filter(GroupCustomSet.group_id == group_id).all()
    set_ids = [cs.set_id for cs in custom_sets]
    if not set_ids:
        return {"sets": [], "total": 0, "limit": limit, "offset": offset, "max_sets": 5, "current_count": 0}
    total = db.query(func.count(QuestionSet.id)).filter(QuestionSet.id.in_(set_ids)).scalar()
    sets = db.query(QuestionSet).filter(QuestionSet.id.in_(set_ids)).order_by(QuestionSet.created_at.desc()).limit(limit).offset(offset).all()
    return {
        "sets": [
            {
                "id": qs.id, "name": qs.name,
                "question_count": db.query(func.count(QuestionSetTemplate.id)).filter(QuestionSetTemplate.question_set_id == qs.id).scalar() or 0,
                "usage_count": qs.usage_count or 0, "is_public": qs.is_public, "created_at": qs.created_at,
            }
            for qs in sets
        ],
        "total": total, "limit": limit, "offset": offset, "max_sets": 5, "current_count": len(custom_sets),
    }


@router.get("/{set_id}")
async def get_question_set_details(group_id: int, set_id: int, request: Request, db: Session = Depends(get_db)):
    """Get details of a question set including templates."""
    user = get_user_from_request(request, db)
    if not user or user.group_id != group_id:
        raise HTTPException(status_code=401, detail="Invalid authentication")
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    question_set = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()
    if not question_set:
        raise HTTPException(status_code=404, detail="Question set not found")
    if not question_set.is_public:
        custom_set = db.query(GroupCustomSet).filter(and_(GroupCustomSet.set_id == set_id, GroupCustomSet.group_id == group_id)).first()
        if not custom_set:
            raise HTTPException(status_code=403, detail="Access denied to this question set")
        if group.creator_id != user.id:
            raise HTTPException(status_code=403, detail="Only group creator can view private sets")
    template_ids = [r.template_id for r in db.query(QuestionSetTemplate.template_id).filter(QuestionSetTemplate.question_set_id == set_id).all()]
    templates = db.query(QuestionTemplate).filter(QuestionTemplate.id.in_(template_ids)).all() if template_ids else []
    return {
        "id": question_set.id, "name": question_set.name, "is_public": question_set.is_public,
        "creator_id": question_set.creator_id, "usage_count": question_set.usage_count or 0,
        "created_at": question_set.created_at, "question_count": len(templates),
        "questions": [
            {"id": t.id, "text": t.question_text,
             "question_type": t.question_type.value if hasattr(t.question_type, 'value') else str(t.question_type)}
            for t in templates
        ],
    }


@router.put("/{set_id}")
async def update_private_question_set(group_id: int, set_id: int, body: dict, request: Request, db: Session = Depends(get_db)):
    """Update a private question set (name and/or questions)."""
    user, group = _require_group_creator(group_id, request, db)
    custom_set = db.query(GroupCustomSet).filter(and_(GroupCustomSet.set_id == set_id, GroupCustomSet.group_id == group_id)).first()
    if not custom_set:
        raise HTTPException(status_code=403, detail="This is not a private set you created")
    question_set = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()
    if not question_set:
        raise HTTPException(status_code=404, detail="Question set not found")
    if "name" in body:
        name = body["name"].strip()
        if not name or len(name) < 3:
            raise HTTPException(status_code=400, detail="Set name must be at least 3 characters")
        if len(name) > 200:
            raise HTTPException(status_code=400, detail="Set name cannot exceed 200 characters")
        question_set.name = name
    if "questions" in body:
        questions = body["questions"]
        if not questions:
            raise HTTPException(status_code=400, detail="At least one question is required")
        if len(questions) > 100:
            raise HTTPException(status_code=400, detail="Maximum 100 questions per set")
        # Delete old templates via association table
        old_template_ids = [r.template_id for r in db.query(QuestionSetTemplate.template_id).filter(QuestionSetTemplate.question_set_id == set_id).all()]
        db.query(QuestionSetTemplate).filter(QuestionSetTemplate.question_set_id == set_id).delete()
        if old_template_ids:
            db.query(QuestionTemplate).filter(QuestionTemplate.id.in_(old_template_ids)).delete(synchronize_session=False)
        _add_templates(db, set_id, questions)
    db.commit()
    return {"message": "Question set updated successfully", "set_id": question_set.id, "name": question_set.name}


@router.delete("/{set_id}")
async def delete_private_question_set(group_id: int, set_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete a private question set."""
    user, group = _require_group_creator(group_id, request, db)
    custom_set = db.query(GroupCustomSet).filter(and_(GroupCustomSet.set_id == set_id, GroupCustomSet.group_id == group_id)).first()
    if not custom_set:
        raise HTTPException(status_code=403, detail="This is not a private set you created")
    is_assigned = db.query(GroupQuestionSet).filter(and_(GroupQuestionSet.group_id == group_id, GroupQuestionSet.question_set_id == set_id)).first()
    if is_assigned:
        raise HTTPException(status_code=400, detail="Cannot delete a question set that is currently assigned to the group. Unassign it first.")
    db.delete(custom_set)
    # Delete templates via association table
    old_template_ids = [r.template_id for r in db.query(QuestionSetTemplate.template_id).filter(QuestionSetTemplate.question_set_id == set_id).all()]
    db.query(QuestionSetTemplate).filter(QuestionSetTemplate.question_set_id == set_id).delete()
    if old_template_ids:
        db.query(QuestionTemplate).filter(QuestionTemplate.id.in_(old_template_ids)).delete(synchronize_session=False)
    question_set = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()
    if question_set:
        db.delete(question_set)
    db.commit()
    return {"message": "Question set deleted successfully", "set_id": set_id}


@router.get("/{set_id}/usage")
async def get_question_set_usage(group_id: int, set_id: int, request: Request, db: Session = Depends(get_db)):
    """Get usage statistics for a private question set."""
    user, group = _require_group_creator(group_id, request, db)
    custom_set = db.query(GroupCustomSet).filter(and_(GroupCustomSet.set_id == set_id, GroupCustomSet.group_id == group_id)).first()
    if not custom_set:
        raise HTTPException(status_code=403, detail="This is not a private set you created")
    question_set = db.query(QuestionSet).filter(QuestionSet.id == set_id).first()
    if not question_set:
        raise HTTPException(status_code=404, detail="Question set not found")
    template_ids = [r.template_id for r in db.query(QuestionSetTemplate.template_id).filter(QuestionSetTemplate.question_set_id == set_id).all()]
    templates = db.query(QuestionTemplate).filter(QuestionTemplate.id.in_(template_ids)).all() if template_ids else []
    questions_usage = []
    for template in templates:
        usage_count = db.query(func.count(DailyQuestion.id)).filter(DailyQuestion.template_id == template.id).scalar() or 0
        questions_usage.append({
            "template_id": template.id, "text": template.question_text,
            "question_type": template.question_type.value if hasattr(template.question_type, 'value') else str(template.question_type),
            "times_asked": usage_count,
        })
    return {
        "set_id": set_id, "set_name": question_set.name,
        "total_times_used": question_set.usage_count or 0,
        "total_questions_asked": sum(q["times_asked"] for q in questions_usage),
        "questions": questions_usage,
    }


# ============= Helpers =============

def _add_templates(db, set_id: int, questions: list):
    """Add question templates to a set."""
    valid_types = ["binary_vote", "single_choice", "free_text", "member_choice", "duo_choice"]
    for idx, q in enumerate(questions):
        q_text = q.get("text", "").strip()
        q_type = q.get("question_type", "binary_vote")
        if not q_text:
            raise HTTPException(status_code=400, detail=f"Question {idx + 1}: text is required")
        if q_type not in valid_types:
            raise HTTPException(status_code=400, detail=f"Question {idx + 1}: invalid question_type. Must be one of {valid_types}")
        if q_type == "single_choice" and not q.get("options"):
            raise HTTPException(status_code=400, detail=f"Question {idx + 1}: options required for single_choice")
        template = QuestionTemplate(question_text=q_text, question_type=QuestionTypeEnum[q_type.upper()], is_public=False)
        db.add(template)
        db.flush()
        db.add(QuestionSetTemplate(question_set_id=set_id, template_id=template.id))
