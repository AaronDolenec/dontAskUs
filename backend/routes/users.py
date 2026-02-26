"""User profile routes: update display name and email notification preferences."""

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from core.database import get_db
from auth.utils import get_user_from_request
from core.models import User

router = APIRouter(prefix="/api/users/{user_id}", tags=["User Profile"])


@router.put("/display-name")
async def update_display_name(request: Request, user_id: str, db: Session = Depends(get_db)):
    """Update the display name for this membership (per-group)."""
    user = get_user_from_request(request, db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    data = await request.json()
    new_name = (data.get("display_name") or "").strip()
    if not new_name or len(new_name) < 1 or len(new_name) > 50:
        raise HTTPException(status_code=400, detail="Display name must be 1-50 characters")

    # Check uniqueness within group
    exists = db.query(User).filter(
        User.group_id == user.group_id,
        User.display_name == new_name,
        User.id != user.id,
    ).first()
    if exists:
        raise HTTPException(status_code=409, detail="Display name already taken in group")

    user.display_name = new_name
    db.commit()
    return {"message": "Display name updated", "display_name": user.display_name}


@router.put("/email-settings")
async def update_email_settings(request: Request, user_id: str, db: Session = Depends(get_db)):
    """Toggle per-group email notification preferences. Defaults are False."""
    user = get_user_from_request(request, db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    data = await request.json()
    # Accept either booleans or string values
    new_q = data.get("email_on_new_question")
    rem = data.get("email_on_reminder")

    if isinstance(new_q, bool):
        user.email_notify_new_question = new_q
    if isinstance(rem, bool):
        user.email_notify_reminder = rem

    db.commit()
    return {
        "message": "Email settings updated",
        "email_on_new_question": bool(user.email_notify_new_question),
        "email_on_reminder": bool(user.email_notify_reminder),
    }


@router.get("/settings")
async def get_user_settings(request: Request, user_id: str, db: Session = Depends(get_db)):
    """Get membership-specific settings (display name, avatar, email prefs)."""
    user = get_user_from_request(request, db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    return {
        "user_id": user.user_id,
        "display_name": user.display_name,
        "avatar_filename": user.avatar_filename,
        "email_on_new_question": bool(user.email_notify_new_question),
        "email_on_reminder": bool(user.email_notify_reminder),
        "push_notifications_enabled": bool(getattr(user, "push_notify_enabled", False)),
    }


@router.put("/push-settings")
async def update_push_settings(request: Request, user_id: str, db: Session = Depends(get_db)):
    """Toggle per-membership system-level push notification opt-in (FCM). Defaults to False."""
    user = get_user_from_request(request, db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    data = await request.json()
    push_flag = data.get("push_notifications_enabled")
    if isinstance(push_flag, bool):
        user.push_notify_enabled = push_flag
        db.commit()
    else:
        raise HTTPException(status_code=400, detail="push_notifications_enabled must be a boolean")

    return {
        "message": "Push settings updated",
        "push_notifications_enabled": bool(user.push_notify_enabled),
    }
