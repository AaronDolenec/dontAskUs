"""Question set management routes (public CRUD + group assignment)."""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import (
    Account, QuestionSet, QuestionTemplate, QuestionSetTemplate,
    GroupQuestionSet, Group,
)
from core.schemas import (
    QuestionSetCreate, QuestionSetResponse, QuestionTemplateResponse,
    GroupQuestionSetsResponse, GroupAssignSetsRequest,
)
from auth.utils import get_group_by_id, require_group_creator, get_current_account

router = APIRouter(prefix="/api", tags=["Question Sets"])


def _template_to_dict(t: QuestionTemplate) -> dict:
    """Convert a QuestionTemplate to a serializable dict."""
    return {
        "template_id": t.template_id, "category": t.category,
        "question_text": t.question_text,
        "option_a_template": t.option_a_template,
        "option_b_template": t.option_b_template,
        "question_type": t.question_type.value if hasattr(t.question_type, 'value') else str(t.question_type),
        "allow_multiple": getattr(t, "allow_multiple", False),
        "is_public": t.is_public, "created_at": t.created_at,
    }


def _template_to_response(t: QuestionTemplate) -> QuestionTemplateResponse:
    """Convert a QuestionTemplate to a QuestionTemplateResponse."""
    return QuestionTemplateResponse(
        template_id=t.template_id, category=t.category,
        question_text=t.question_text, option_a_template=t.option_a_template,
        option_b_template=t.option_b_template, question_type=t.question_type,
        allow_multiple=getattr(t, "allow_multiple", False),
        is_public=t.is_public, created_at=t.created_at,
    )


def _get_set_templates(qs_id: int, db) -> list[QuestionTemplate]:
    """Get all templates associated with a question set."""
    templates = []
    for assoc in db.query(QuestionSetTemplate).filter(QuestionSetTemplate.question_set_id == qs_id).all():
        t = db.get(QuestionTemplate, assoc.template_id)
        if t:
            templates.append(t)
    return templates


@router.post("/question-sets", response_model=QuestionSetResponse)
def create_question_set(
    payload: QuestionSetCreate,
    account: Account = Depends(get_current_account), db: Session = Depends(get_db),
):
    """Create a new question set. Requires authentication."""
    qs = QuestionSet(name=payload.name, description=payload.description, is_public=payload.is_public)
    db.add(qs)
    db.commit()
    db.refresh(qs)
    if payload.template_ids:
        for tid in payload.template_ids:
            tmpl = db.query(QuestionTemplate).filter(QuestionTemplate.template_id == tid).first()
            if tmpl:
                db.add(QuestionSetTemplate(question_set_id=qs.id, template_id=tmpl.id))
        db.commit()
    templates = [_template_to_response(t) for t in _get_set_templates(qs.id, db)]
    return QuestionSetResponse(
        set_id=qs.set_id, name=qs.name, description=qs.description,
        is_public=qs.is_public, templates=templates, created_at=qs.created_at,
    )


@router.get("/question-sets")
def list_public_question_sets(
    db: Session = Depends(get_db),
):
    """List all public question sets. Public endpoint."""
    sets = db.query(QuestionSet).filter(QuestionSet.is_public == True).all()
    return [
        {
            "set_id": s.set_id, "name": s.name, "description": s.description,
            "is_public": s.is_public, "created_at": s.created_at,
            "templates": [_template_to_dict(t) for t in _get_set_templates(s.id, db)],
        }
        for s in sets
    ]


@router.get("/question-sets/{set_id}")
def get_question_set(
    set_id: str,
    db: Session = Depends(get_db),
):
    """Get a single question set by ID. Public endpoint."""
    qs = db.query(QuestionSet).filter(QuestionSet.set_id == set_id).first()
    if not qs:
        raise HTTPException(status_code=404, detail="Question set not found")
    return {
        "set_id": qs.set_id, "name": qs.name, "description": qs.description,
        "is_public": qs.is_public, "created_at": qs.created_at,
        "templates": [_template_to_dict(t) for t in _get_set_templates(qs.id, db)],
    }


@router.post("/groups/{group_id}/question-sets")
def assign_question_sets_to_group(
    group_id: str,
    payload: GroupAssignSetsRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Assign question sets to a group. Requires group creator (JWT)."""
    group = require_group_creator(group_id, request, db)
    if payload.replace:
        db.query(GroupQuestionSet).filter(GroupQuestionSet.group_id == group.id).delete()
        db.commit()
    for set_uuid in payload.question_set_ids:
        qs = db.query(QuestionSet).filter(QuestionSet.set_id == set_uuid).first()
        if not qs:
            continue
        existing = db.query(GroupQuestionSet).filter(
            GroupQuestionSet.group_id == group.id, GroupQuestionSet.question_set_id == qs.id
        ).first()
        if existing:
            existing.is_active = True
        else:
            db.add(GroupQuestionSet(group_id=group.id, question_set_id=qs.id, is_active=True))
    db.commit()
    assigned = db.query(GroupQuestionSet).filter(GroupQuestionSet.group_id == group.id, GroupQuestionSet.is_active == True).all()
    result_sets = []
    for a in assigned:
        s = db.get(QuestionSet, a.question_set_id)
        if s:
            result_sets.append({"set_id": s.set_id, "name": s.name, "description": s.description, "is_public": s.is_public})
    return {"group_id": group.group_id, "question_sets": result_sets}


@router.get("/groups/{group_id}/question-sets", response_model=GroupQuestionSetsResponse)
def get_group_question_sets(
    group_id: str,
    account: Account = Depends(get_current_account), db: Session = Depends(get_db),
):
    """Get all question sets assigned to a group. Requires authentication and group membership."""
    from auth.utils import get_membership
    group = get_group_by_id(group_id, db)
    membership = get_membership(account, group.id, db)
    if not membership:
        raise HTTPException(status_code=403, detail="You are not a member of this group")
    assigned = db.query(GroupQuestionSet).filter(GroupQuestionSet.group_id == group.id, GroupQuestionSet.is_active == True).all()
    result_sets = []
    for a in assigned:
        s = db.get(QuestionSet, a.question_set_id)
        if s:
            templates = [_template_to_response(t) for t in _get_set_templates(s.id, db)]
            result_sets.append(QuestionSetResponse(
                set_id=s.set_id, name=s.name, description=s.description,
                is_public=s.is_public, templates=templates, created_at=s.created_at,
            ))
    return GroupQuestionSetsResponse(group_id=group.group_id, question_sets=result_sets)
