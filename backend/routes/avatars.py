"""Avatar upload and deletion routes."""

import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from config import AVATAR_UPLOAD_DIR, AVATAR_MAX_SIZE_BYTES, AVATAR_MAX_SIZE_MB, AVATAR_ALLOWED_TYPES
from database import get_db
from utils import get_user_from_request, validate_image_magic_bytes, process_avatar_image

router = APIRouter(prefix="/api/users/{user_id}/avatar", tags=["User Profile"])
limiter = Limiter(key_func=get_remote_address)


@router.post("")
@limiter.limit("10/minute")
async def upload_avatar(request: Request, user_id: str, file: UploadFile = File(...), db=Depends(get_db)):
    """Upload a profile avatar image (max 2MB, auto-resized to 256x256 WebP)."""
    user = get_user_from_request(request, db, user_id=user_id)
    if not user or user.user_id != user_id:
        raise HTTPException(status_code=401, detail="Invalid authentication")

    file_bytes = await file.read()
    if len(file_bytes) > AVATAR_MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail=f"File too large. Maximum size is {AVATAR_MAX_SIZE_MB}MB")
    if file.content_type not in AVATAR_ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Invalid file type. Allowed: JPEG, PNG, GIF, WebP")

    detected_type = validate_image_magic_bytes(file_bytes)
    if not detected_type:
        raise HTTPException(status_code=400, detail="Invalid image file. Could not verify file format.")

    try:
        processed_bytes = process_avatar_image(file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    filename = f"{user.user_id}_{secrets.token_hex(8)}.webp"
    filepath = AVATAR_UPLOAD_DIR / filename

    # Delete old avatar
    if user.avatar_filename:
        old_filepath = AVATAR_UPLOAD_DIR / user.avatar_filename
        if old_filepath.exists():
            try:
                old_filepath.unlink()
            except Exception as e:
                logging.warning(f"Failed to delete old avatar: {e}")

    try:
        with open(filepath, "wb") as f:
            f.write(processed_bytes)
    except Exception as e:
        logging.error(f"Failed to save avatar: {e}")
        raise HTTPException(status_code=500, detail="Failed to save avatar file")

    user.avatar_filename = filename
    user.avatar_uploaded_at = datetime.now(timezone.utc)
    db.commit()

    base_url = str(request.base_url).rstrip("/")
    return {
        "message": "Avatar uploaded successfully",
        "avatar_url": f"{base_url}/uploads/avatars/{filename}",
        "avatar_filename": filename,
        "uploaded_at": user.avatar_uploaded_at.isoformat(),
    }


@router.delete("")
@limiter.limit("10/minute")
async def delete_avatar(request: Request, user_id: str, db=Depends(get_db)):
    """Delete profile avatar and revert to color-based avatar."""
    user = get_user_from_request(request, db, user_id=user_id)
    if not user or user.user_id != user_id:
        raise HTTPException(status_code=401, detail="Invalid authentication")
    if not user.avatar_filename:
        raise HTTPException(status_code=404, detail="No avatar to delete")

    filepath = AVATAR_UPLOAD_DIR / user.avatar_filename
    if filepath.exists():
        try:
            filepath.unlink()
        except Exception as e:
            logging.warning(f"Failed to delete avatar file: {e}")

    user.avatar_filename = None
    user.avatar_uploaded_at = None
    db.commit()
    return {"message": "Avatar deleted successfully", "color_avatar": user.color_avatar}
