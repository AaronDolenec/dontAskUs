"""Core infrastructure: database, models, config, schemas."""

from .database import engine, Base, SessionLocal, get_db
from .models import (
    AdminUser, Account, User, Group, DailyQuestion, Vote,
    QuestionTemplate, QuestionSet, QuestionSetTemplate, GroupQuestionSet,
    AuditLog, UserDeviceToken, QuestionTypeEnum, ApiRequestLog,
)
from .config import (
    DATABASE_URL, ALLOWED_ORIGINS, AVATAR_UPLOAD_DIR, AVATAR_MAX_SIZE_BYTES,
    AVATAR_MAX_SIZE_MB, AVATAR_ALLOWED_TYPES, AVATAR_MAGIC_BYTES, AVATAR_MAX_DIMENSION,
    USER_JWT_SECRET, USER_JWT_ALGO, USER_JWT_ACCESS_EXPIRE_MINUTES, USER_JWT_REFRESH_EXPIRE_DAYS,
    ADMIN_JWT_SECRET, ADMIN_JWT_ALGO, ADMIN_JWT_EXPIRE_MINUTES,
    ADMIN_AUTH_SECRET_KEY, ADMIN_AUTH_JWT_EXPIRY_MINUTES, ADMIN_AUTH_REFRESH_EXPIRY_DAYS,
    ADMIN_LOGIN_ATTEMPT_LIMIT, ADMIN_LOGIN_ATTEMPT_WINDOW_MINUTES, ADMIN_LOCKOUT_DURATION_MINUTES,
    MAX_LOGIN_ATTEMPTS, LOCKOUT_DURATION_MINUTES,
    SCHEDULE_INTERVAL_SECONDS, LOG_LEVEL, TRUSTED_PROXIES,
)
from .schemas import (
    AuthRegisterRequest, AuthLoginRequest, AuthTokenResponse, AuthRefreshRequest,
    AccountResponse, AccountGroupMembership, AccountMeResponse,
    UserChangePasswordRequest, JoinGroupRequest, GroupCreate,
    GroupResponsePublic, DailyQuestionCreate, DailyQuestionResponse,
    AnswerSubmissionCreate, QuestionSetCreate, QuestionSetResponse,
    QuestionTemplateResponse, GroupQuestionSetsResponse, GroupAssignSetsRequest,
    DeviceTokenRegister, DeviceTokenResponse, PushNotificationStatus,
)

__all__ = [
    "engine", "Base", "SessionLocal", "get_db",
    "AdminUser", "Account", "User", "Group", "DailyQuestion", "Vote",
    "QuestionTemplate", "QuestionSet", "QuestionSetTemplate", "GroupQuestionSet",
    "AuditLog", "UserDeviceToken", "QuestionTypeEnum", "ApiRequestLog",
    "DATABASE_URL", "ALLOWED_ORIGINS", "AVATAR_UPLOAD_DIR", "AVATAR_MAX_SIZE_BYTES",
    "AVATAR_MAX_SIZE_MB", "AVATAR_ALLOWED_TYPES", "AVATAR_MAGIC_BYTES", "AVATAR_MAX_DIMENSION",
    "USER_JWT_SECRET", "USER_JWT_ALGO", "USER_JWT_ACCESS_EXPIRE_MINUTES", "USER_JWT_REFRESH_EXPIRE_DAYS",
    "ADMIN_JWT_SECRET", "ADMIN_JWT_ALGO", "ADMIN_JWT_EXPIRE_MINUTES",
    "ADMIN_AUTH_SECRET_KEY", "ADMIN_AUTH_JWT_EXPIRY_MINUTES", "ADMIN_AUTH_REFRESH_EXPIRY_DAYS",
    "ADMIN_LOGIN_ATTEMPT_LIMIT", "ADMIN_LOGIN_ATTEMPT_WINDOW_MINUTES", "ADMIN_LOCKOUT_DURATION_MINUTES",
    "MAX_LOGIN_ATTEMPTS", "LOCKOUT_DURATION_MINUTES",
    "SCHEDULE_INTERVAL_SECONDS", "LOG_LEVEL", "TRUSTED_PROXIES",
    "AuthRegisterRequest", "AuthLoginRequest", "AuthTokenResponse", "AuthRefreshRequest",
    "AccountResponse", "AccountGroupMembership", "AccountMeResponse",
    "UserChangePasswordRequest", "JoinGroupRequest", "GroupCreate",
    "GroupResponsePublic", "DailyQuestionCreate", "DailyQuestionResponse",
    "AnswerSubmissionCreate", "QuestionSetCreate", "QuestionSetResponse",
    "QuestionTemplateResponse", "GroupQuestionSetsResponse", "GroupAssignSetsRequest",
    "DeviceTokenRegister", "DeviceTokenResponse", "PushNotificationStatus",
]
