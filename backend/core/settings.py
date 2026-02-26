from sqlalchemy.orm import Session
from .models import AppSetting


def get_setting(db: Session, key: str, default: str | None = None) -> str | None:
    """Retrieve a setting value as string from the database."""
    setting = db.query(AppSetting).filter(AppSetting.key == key).first()
    if setting:
        return setting.value
    return default


def set_setting(db: Session, key: str, value: str) -> AppSetting:
    """Insert or update a setting in the database."""
    setting = db.query(AppSetting).filter(AppSetting.key == key).first()
    if setting is None:
        setting = AppSetting(key=key, value=value)
        db.add(setting)
    else:
        setting.value = value
    db.commit()
    db.refresh(setting)
    return setting


def get_require_email_verification(db: Session) -> bool:
    """Return whether email verification is required for new registrations."""
    val = get_setting(db, 'require_email_verification', 'false')
    return str(val).lower() in ('true', '1', 'yes')


def set_require_email_verification(db: Session, enabled: bool) -> AppSetting:
    """Set the require_email_verification flag."""
    return set_setting(db, 'require_email_verification', 'true' if enabled else 'false')
