"""WebSocket real-time endpoints.

Two WebSocket endpoints:
1. /ws/groups/{group_id} — Group-level: receives ALL real-time events for a group
   (vote_update, new_question, streak_update, member_joined, member_left)
2. /ws/groups/{group_id}/questions/{question_id} — Question-level (legacy): vote updates only
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import Account, DailyQuestion, Vote, QuestionTypeEnum, User
from auth.utils import (
    verify_user_jwt, get_membership, get_group_by_id, get_option_counts,
    normalize_answer_submission, get_user_group_streak,
)
from services.ws_manager import manager

router = APIRouter()


# ─── Group-Level WebSocket ───────────────────────────────────

@router.websocket("/ws/groups/{group_id}")
async def group_websocket_endpoint(
    websocket: WebSocket,
    group_id: str,
    token: str = Query(default=None),
    db: Session = Depends(get_db),
):
    """Group-level WebSocket connection for ALL real-time events.

    Authentication: Pass JWT access token as query param `token`.
    Example: ws://host/ws/groups/{group_id}?token=eyJ...

    Once connected, the client receives typed events:
    - vote_update: someone voted or changed their vote
    - new_question: the daily question rolled over
    - streak_update: a member's streak changed
    - member_joined: a new member joined the group
    - member_left: a member left the group

    Client can send:
    - {"type": "ping"} → receives {"type": "pong", "timestamp": "..."}
    """
    # ── Authenticate via query param ──
    user = None
    if token:
        try:
            acct_id = verify_user_jwt(token, "access")
            acct = db.query(Account).filter(Account.id == acct_id, Account.is_active == True).first()
            if acct:
                try:
                    group = get_group_by_id(group_id, db)
                except Exception:
                    group = None
                if group:
                    user = get_membership(acct, group.id, db)
        except Exception:
            pass

    if not user:
        await websocket.accept()
        await websocket.close(code=4001, reason="Authentication failed")
        return

    user_info = {
        "user_id": user.user_id,
        "display_name": user.display_name,
        "color_avatar": user.color_avatar,
    }

    await manager.connect_group(group_id, websocket, user_info)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                continue

            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({
                    "type": "pong",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "online_count": manager.get_group_connection_count(group_id),
                }))

    except WebSocketDisconnect:
        manager.disconnect_group(group_id, websocket)
    except Exception:
        logging.exception("Group WebSocket handler error")
        manager.disconnect_group(group_id, websocket)


# ─── Question-Level WebSocket (legacy) ───────────────────────

@router.websocket("/ws/groups/{group_id}/questions/{question_id}")
async def websocket_endpoint(
    websocket: WebSocket, group_id: str, question_id: str, db: Session = Depends(get_db),
):
    """WebSocket connection for real-time voting updates (legacy per-question endpoint)."""
    await manager.connect(group_id, question_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "vote":
                try:
                    group = get_group_by_id(group_id, db)
                except Exception:
                    group = None
                if not group:
                    continue

                question = db.query(DailyQuestion).filter(DailyQuestion.question_id == question_id).first()
                if not question:
                    continue

                # JWT auth for WebSocket
                user = None
                ws_token = message.get("token")
                if ws_token:
                    try:
                        from fastapi import HTTPException
                        acct_id = verify_user_jwt(ws_token, "access")
                        acct = db.query(Account).filter(Account.id == acct_id, Account.is_active == True).first()
                        if acct:
                            user = get_membership(acct, group.id, db)
                    except Exception:
                        pass

                if not user:
                    continue

                options_list = json.loads(question.options) if question.options else []
                allow_multiple = bool(getattr(question, "allow_multiple", False))
                stored_answer = None
                normalized_answers: list[str] = []
                text_answer = message.get("text_answer")

                if question.question_type == QuestionTypeEnum.FREE_TEXT:
                    if not text_answer:
                        await websocket.send_text(json.dumps({"error": "text_answer required"}))
                        continue
                    stored_answer = text_answer
                else:
                    raw_answer = message.get("answer")
                    normalized_answers = normalize_answer_submission(raw_answer, allow_multiple)
                    if not normalized_answers:
                        await websocket.send_text(json.dumps({"error": "answer required"}))
                        continue
                    if options_list:
                        invalid = [a for a in normalized_answers if a not in options_list]
                        if invalid:
                            await websocket.send_text(json.dumps({"error": "invalid option"}))
                            continue
                    stored_answer = json.dumps(normalized_answers) if allow_multiple else normalized_answers[0]

                existing_vote = db.query(Vote).filter(
                    and_(Vote.question_id == question.id, Vote.user_id == user.id)
                ).first()
                if existing_vote:
                    existing_vote.answer = stored_answer
                    existing_vote.text_answer = text_answer
                    existing_vote.voted_at = datetime.now(timezone.utc)
                else:
                    db.add(Vote(
                        question_id=question.id, user_id=user.id,
                        answer=stored_answer, text_answer=text_answer,
                    ))
                db.commit()

                option_counts = get_option_counts(question.id, db)
                total_votes = db.query(func.count(Vote.id)).filter(Vote.question_id == question.id).scalar() or 0

                vote_data = {
                    "option_counts": option_counts, "total_votes": total_votes,
                    "allow_multiple": allow_multiple, "options": options_list,
                    "user": {
                        "display_name": user.display_name,
                        "voted": text_answer if question.question_type == QuestionTypeEnum.FREE_TEXT else (
                            normalized_answers if allow_multiple else normalized_answers[0]
                        ),
                    },
                }

                # Broadcast to both question-level and group-level clients
                await manager.broadcast_vote_update(group_id, question_id, vote_data)

            elif message.get("type") == "ping":
                await websocket.send_text(json.dumps({
                    "type": "pong", "timestamp": datetime.now(timezone.utc).isoformat(),
                }))

    except WebSocketDisconnect:
        manager.disconnect(group_id, question_id, websocket)
    except Exception:
        logging.exception("WebSocket handler error")
        manager.disconnect(group_id, question_id, websocket)
