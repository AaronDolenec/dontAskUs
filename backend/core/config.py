"""
Centralized application configuration.
All environment variables and shared settings are defined here.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_logger = logging.getLogger(__name__)

# ============= Secret Defaults Warning =============
_INSECURE_DEFAULTS = {"supersecretkey", "your-super-secret-key-change-in-production", "user_jwt_insecure_default"}


def _get_secret(env_var: str, fallback: str) -> str:
    """Get a secret from env, warn loudly if using insecure default."""
    value = os.getenv(env_var, fallback)
    if value in _INSECURE_DEFAULTS or value == fallback:
        _logger.warning(
            "\n" + "!" * 72 + "\n"
            "  SECURITY WARNING: %s is using an insecure default value!\n"
            "  Set %s in your .env file to a strong random value.\n"
            "  Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\"\n"
            + "!" * 72,
            env_var, env_var,
        )
    return value


# ============= Database =============
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://qauser:securepassword@postgres:5432/qadb")

# ============= Admin JWT (used by admin_auth.py) =============
# Note: ADMIN_JWT_SECRET is kept for backward compat but admin_auth.py uses SECRET_KEY.
ADMIN_JWT_SECRET = _get_secret("ADMIN_JWT_SECRET", "supersecretkey")
ADMIN_JWT_ALGO = "HS256"
ADMIN_JWT_EXPIRE_MINUTES = 60 * 8  # 8 hours

# ============= User JWT =============
# USER_JWT_SECRET MUST be independent of ADMIN_JWT_SECRET
USER_JWT_SECRET = _get_secret("USER_JWT_SECRET", "user_jwt_insecure_default")
USER_JWT_ALGO = "HS256"
USER_JWT_ACCESS_EXPIRE_MINUTES = int(os.getenv("USER_JWT_ACCESS_EXPIRE_MINUTES", "30"))
USER_JWT_REFRESH_EXPIRE_DAYS = int(os.getenv("USER_JWT_REFRESH_EXPIRE_DAYS", "30"))

# ============= Security =============
MAX_LOGIN_ATTEMPTS = 10
LOCKOUT_DURATION_MINUTES = 15

# ============= Admin Auth (admin_auth.py) =============
ADMIN_AUTH_SECRET_KEY = _get_secret("SECRET_KEY", "your-super-secret-key-change-in-production")
ADMIN_AUTH_JWT_EXPIRY_MINUTES = 60
ADMIN_AUTH_REFRESH_EXPIRY_DAYS = 7
ADMIN_LOGIN_ATTEMPT_LIMIT = 5
ADMIN_LOGIN_ATTEMPT_WINDOW_MINUTES = 15
ADMIN_LOCKOUT_DURATION_MINUTES = 30

# ============= CORS =============
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:3000,http://localhost:8085,http://127.0.0.1:8085"
).split(",")

# ============= Avatar Upload =============
AVATAR_UPLOAD_DIR = Path(__file__).parent / "uploads" / "avatars"
AVATAR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
AVATAR_MAX_SIZE_MB = 2
AVATAR_MAX_SIZE_BYTES = AVATAR_MAX_SIZE_MB * 1024 * 1024
AVATAR_MAX_DIMENSION = 256
AVATAR_ALLOWED_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "image/bmp", "image/tiff", "image/x-icon", "image/vnd.microsoft.icon",
    "image/heic", "image/heif", "image/avif", "image/svg+xml",
}
AVATAR_MAGIC_BYTES = {
    b'\xff\xd8\xff': 'image/jpeg',
    b'\x89PNG\r\n\x1a\n': 'image/png',
    b'GIF87a': 'image/gif',
    b'GIF89a': 'image/gif',
    b'RIFF': 'image/webp',
    b'BM': 'image/bmp',
    b'II': 'image/tiff',  # little-endian TIFF
    b'MM': 'image/tiff',  # big-endian TIFF
    b'\x00\x00\x01\x00': 'image/x-icon',  # ICO
    b'\x00\x00\x02\x00': 'image/x-icon',  # CUR (cursor, similar to ICO)
}

# ============= Reverse Proxy =============
# Comma-separated list of trusted proxy IPs/CIDRs.
# When set, X-Forwarded-For headers from these proxies are trusted
# to determine the real client IP address.
# Examples:
#   TRUSTED_PROXIES=172.16.0.0/12           (Docker default bridge network)
#   TRUSTED_PROXIES=10.0.0.1,172.18.0.0/16  (specific proxy + Docker network)
#   TRUSTED_PROXIES=*                        (trust all — only if behind a known proxy)
_raw_proxies = os.getenv("TRUSTED_PROXIES", "").strip()
TRUSTED_PROXIES: list[str] = [p.strip() for p in _raw_proxies.split(",") if p.strip()] if _raw_proxies else []

if TRUSTED_PROXIES:
    _logger.info("Trusted proxies configured: %s", TRUSTED_PROXIES)
else:
    _logger.info("No trusted proxies configured — X-Forwarded-For headers will be ignored")

# ============= Scheduler =============
SCHEDULE_INTERVAL_SECONDS = int(os.getenv("SCHEDULE_INTERVAL_SECONDS", "86400"))

# ============= Logging =============
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ============= SMTP (Email) =============
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "").strip()
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "DontAskUs").strip()
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "false").strip().lower() in ("true", "1", "yes")
PASSWORD_RESET_EXPIRE_MINUTES = 15

if SMTP_HOST:
    _logger.info("SMTP configured: %s:%s (TLS=%s)", SMTP_HOST, SMTP_PORT, SMTP_USE_TLS)
else:
    _logger.info("SMTP not configured — password reset emails will not be sent")
