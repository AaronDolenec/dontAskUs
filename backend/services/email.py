"""
Email service for sending transactional emails (e.g. password reset).
Uses SMTP with TLS/STARTTLS support.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from core.config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    SMTP_FROM_EMAIL, SMTP_FROM_NAME, SMTP_USE_TLS,
)

_logger = logging.getLogger(__name__)


def is_smtp_configured() -> bool:
    """Check whether SMTP settings are configured."""
    return bool(SMTP_HOST and SMTP_FROM_EMAIL)


def send_email(to: str, subject: str, html_body: str) -> bool:
    """
    Send an email via SMTP.  Returns True on success, False on failure.
    Fails silently (logs the error) so callers don't leak SMTP details.
    """
    if not is_smtp_configured():
        _logger.warning("SMTP not configured — skipping email to %s", to)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>" if SMTP_FROM_NAME else SMTP_FROM_EMAIL
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html"))

    try:
        if SMTP_USE_TLS:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
            server.ehlo()
            server.starttls()
            server.ehlo()

        if SMTP_USER and SMTP_PASSWORD:
            server.login(SMTP_USER, SMTP_PASSWORD)

        server.sendmail(SMTP_FROM_EMAIL, to, msg.as_string())
        server.quit()
        _logger.info("Email sent to %s: %s", to, subject)
        return True
    except Exception:
        _logger.exception("Failed to send email to %s", to)
        return False


def send_password_reset_email(to: str, reset_token: str, app_name: str = "DontAskUs") -> bool:
    """Send a password-reset email with the reset token."""
    subject = f"{app_name} — Password Reset"
    html = f"""\
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background:#f4f4f5; padding:32px;">
  <div style="max-width:480px; margin:0 auto; background:#fff; border-radius:8px; padding:32px; box-shadow:0 1px 3px rgba(0,0,0,.1);">
    <h2 style="margin:0 0 16px; color:#111827;">{app_name}</h2>
    <p style="color:#374151; line-height:1.6;">
      You requested a password reset. Use the code below in the app to set a new password.
      This code expires in <strong>15 minutes</strong>.
    </p>
    <div style="text-align:center; margin:24px 0;">
      <span style="display:inline-block; font-size:28px; letter-spacing:6px; font-weight:700; color:#111827;
                    background:#f3f4f6; padding:12px 24px; border-radius:8px; font-family:monospace;">
        {reset_token}
      </span>
    </div>
    <p style="color:#6b7280; font-size:14px; line-height:1.5;">
      If you did not request this, you can safely ignore this email.
    </p>
  </div>
</body>
</html>"""
    return send_email(to, subject, html)
