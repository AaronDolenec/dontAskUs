"""Group CRUD and member listing routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import Account, Group, User, QuestionSet, GroupQuestionSet
from core.schemas import GroupResponsePublic
from auth.utils import (
    get_group_by_id, get_current_account, get_membership, get_avatar_url,
)

router = APIRouter(prefix="/api/groups", tags=["Groups"])
limiter = Limiter(key_func=get_remote_address)


# Group creation is only available via POST /api/auth/groups/create (requires account).


@router.get("/{invite_code}", response_model=GroupResponsePublic)
@limiter.limit("200/minute")
def get_group_by_code(
    request: Request, invite_code: str,
    db: Session = Depends(get_db),
):
    """Get group info by invite code (for joining). Public endpoint."""
    group = db.query(Group).filter(Group.invite_code == invite_code).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    member_count = db.query(User).filter(User.group_id == group.id).count()
    return GroupResponsePublic(
        id=group.id, group_id=group.group_id, name=group.name,
        invite_code=group.invite_code, created_at=group.created_at, member_count=member_count,
    )


@router.get("/{group_id}/info", response_model=dict)
def get_group_full_info(
    group_id: str,
    account: Account = Depends(get_current_account), db: Session = Depends(get_db),
):
    """Get complete group information. Requires authentication and group membership."""
    group = get_group_by_id(group_id, db)
    membership = get_membership(account, group.id, db)
    if not membership:
        raise HTTPException(status_code=403, detail="You are not a member of this group")
    member_count = db.query(User).filter(User.group_id == group.id).count()
    return {
        "id": group.id, "group_id": group.group_id, "name": group.name,
        "invite_code": group.invite_code, "member_count": member_count,
        "created_at": group.created_at,
    }


@router.get("/{group_id}/members")
@limiter.limit("200/minute")
def get_group_members(
    request: Request, group_id: str,
    account: Account = Depends(get_current_account), db: Session = Depends(get_db),
):
    """Get all members in a group. Requires authentication and group membership."""
    group = get_group_by_id(group_id, db)
    membership = get_membership(account, group.id, db)
    if not membership:
        raise HTTPException(status_code=403, detail="You are not a member of this group")
    members = db.query(User).filter(User.group_id == group.id).all()
    base_url = str(request.base_url).rstrip('/')
    return [
        {
            "user_id": m.user_id, "display_name": m.display_name,
            "color_avatar": m.color_avatar,
            "avatar_url": get_avatar_url(m.avatar_filename, base_url),
            "created_at": m.created_at, "answer_streak": m.answer_streak,
            "longest_answer_streak": m.longest_answer_streak,
        }
        for m in members
    ]


@router.get("/{group_id}/leaderboard")
@limiter.limit("200/minute")
def get_leaderboard_member(
    request: Request, group_id: str,
    account: Account = Depends(get_current_account), db: Session = Depends(get_db),
):
    """Get group leaderboard by answer streak. Requires authentication and group membership."""
    group = get_group_by_id(group_id, db)
    membership = get_membership(account, group.id, db)
    if not membership:
        raise HTTPException(status_code=403, detail="You are not a member of this group")
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
