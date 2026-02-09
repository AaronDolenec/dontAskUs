"""Push notification device token routes."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import UserDeviceToken
from services.push_notifications import push_service
from core.schemas import DeviceTokenRegister, DeviceTokenResponse, PushNotificationStatus
from auth.utils import get_user_from_request

router = APIRouter(prefix="/api", tags=["Push Notifications"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/push-notifications/status")
async def get_push_notification_status() -> PushNotificationStatus:
    """Check if push notifications are enabled on this server."""
    if push_service.is_enabled():
        return PushNotificationStatus(enabled=True, message="Push notifications are enabled")
    return PushNotificationStatus(enabled=False, message="Push notifications are not configured on this server")


@router.post("/users/{user_id}/device-token", response_model=DeviceTokenResponse)
@limiter.limit("10/minute")
async def register_device_token(
    request: Request, user_id: str, token_data: DeviceTokenRegister, db: Session = Depends(get_db),
):
    """Register a device token for push notifications."""
    user = get_user_from_request(request, db, user_id=user_id)
    if not user or user.user_id != user_id:
        raise HTTPException(status_code=401, detail="Invalid authentication")
    if not push_service.is_enabled():
        raise HTTPException(status_code=503, detail="Push notifications are not enabled on this server")

    existing = db.query(UserDeviceToken).filter(
        UserDeviceToken.user_id == user.id, UserDeviceToken.token == token_data.token
    ).first()
    if existing:
        existing.platform = token_data.platform
        existing.device_name = token_data.device_name
        existing.last_used_at = datetime.now(timezone.utc)
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return DeviceTokenResponse(
            id=existing.id, token=existing.token, platform=existing.platform,
            device_name=existing.device_name, created_at=existing.created_at, is_active=existing.is_active,
        )

    device_token = UserDeviceToken(
        user_id=user.id, token=token_data.token,
        platform=token_data.platform, device_name=token_data.device_name,
    )
    db.add(device_token)
    db.commit()
    db.refresh(device_token)
    logging.info(f"Registered device token for user {user_id} on {token_data.platform}")
    return DeviceTokenResponse(
        id=device_token.id, token=device_token.token, platform=device_token.platform,
        device_name=device_token.device_name, created_at=device_token.created_at, is_active=device_token.is_active,
    )


@router.delete("/users/{user_id}/device-token")
@limiter.limit("10/minute")
async def unregister_device_token(
    request: Request, user_id: str,
    token: str = Query(..., description="The device token to remove"),
    db: Session = Depends(get_db),
):
    """Unregister a device token for push notifications."""
    user = get_user_from_request(request, db, user_id=user_id)
    if not user or user.user_id != user_id:
        raise HTTPException(status_code=401, detail="Invalid authentication")
    device_token = db.query(UserDeviceToken).filter(
        UserDeviceToken.user_id == user.id, UserDeviceToken.token == token
    ).first()
    if device_token:
        db.delete(device_token)
        db.commit()
        logging.info(f"Unregistered device token for user {user_id}")
        return {"message": "Device token removed successfully"}
    return {"message": "Device token not found"}


@router.get("/users/{user_id}/device-tokens", response_model=list[DeviceTokenResponse])
async def list_device_tokens(request: Request, user_id: str, db: Session = Depends(get_db)):
    """List all registered device tokens for a user."""
    user = get_user_from_request(request, db, user_id=user_id)
    if not user or user.user_id != user_id:
        raise HTTPException(status_code=401, detail="Invalid authentication")
    tokens = db.query(UserDeviceToken).filter(
        UserDeviceToken.user_id == user.id, UserDeviceToken.is_active == True
    ).all()
    return [
        DeviceTokenResponse(
            id=t.id, token=t.token, platform=t.platform,
            device_name=t.device_name, created_at=t.created_at, is_active=t.is_active,
        )
        for t in tokens
    ]
