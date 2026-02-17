"""Authentication and authorization: admin auth, user auth, utilities."""

from .admin_auth import (
    authenticate_admin, verify_admin_totp, generate_temp_token, verify_temp_token,
    generate_access_token, generate_refresh_token,
    get_current_admin, get_admin_from_refresh_token,
    record_successful_login, log_admin_action, AdminAuthError,
    get_totp_secret, get_totp_uri, hash_password as admin_hash_password,
    verify_password as admin_verify_password,
)
from .admin_schemas import (
    AdminLoginRequest, AdminLoginResponse, AdminTOTPVerifyRequest, AdminTokenResponse,
    AdminRefreshRequest, AdminProfileResponse, AdminDashboardStats, UserSuspensionRequest,
    AccountPasswordResetRequest, AccountPasswordResetResponse, AuditLogResponse,
    ChangePasswordRequest, TOTPSetupStartResponse, TOTPSetupVerifyRequest,
)
from .utils import (
    hash_password, verify_password, create_user_jwt, verify_user_jwt,
    get_current_account, get_avatar_url, get_random_avatar_color,
    generate_invite_code,
    generate_qr_code, get_group_by_id, require_group_creator,
    get_user_for_group, get_membership, get_user_from_request,
    validate_image_magic_bytes, process_avatar_image,
    get_group_member_names, generate_duos, get_option_counts,
    get_user_vote, get_user_group_streak, update_user_group_streak,
    normalize_answer_submission, extract_client_ip,
)

__all__ = [
    "authenticate_admin", "verify_admin_totp", "generate_temp_token", "verify_temp_token",
    "generate_access_token", "generate_refresh_token",
    "get_current_admin", "get_admin_from_refresh_token",
    "record_successful_login", "log_admin_action", "AdminAuthError",
    "get_totp_secret", "get_totp_uri", "admin_hash_password", "admin_verify_password",
    "AdminLoginRequest", "AdminLoginResponse", "AdminTOTPVerifyRequest", "AdminTokenResponse",
    "AdminRefreshRequest", "AdminProfileResponse", "AdminDashboardStats", "UserSuspensionRequest",
    "AccountPasswordResetRequest", "AccountPasswordResetResponse", "AuditLogResponse",
    "ChangePasswordRequest", "TOTPSetupStartResponse", "TOTPSetupVerifyRequest",
    "hash_password", "verify_password", "create_user_jwt", "verify_user_jwt",
    "get_current_account", "get_avatar_url", "get_random_avatar_color",
    "generate_invite_code",
    "generate_qr_code", "get_group_by_id", "require_group_creator",
    "get_user_for_group", "get_membership", "get_user_from_request",
    "validate_image_magic_bytes", "process_avatar_image",
    "get_group_member_names", "generate_duos", "get_option_counts",
    "get_user_vote", "get_user_group_streak", "update_user_group_streak",
    "normalize_answer_submission", "extract_client_ip",
]
