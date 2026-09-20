"""Email Notification Service for Password Resets.

Integrates with Resend REST API (free tier, 3,000 emails/month) to deliver
time-limited, single-use password reset tokens to registered user emails.
"""

from typing import Optional
import requests

from src.config import settings
from src.logger import get_logger

logger = get_logger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


def send_password_reset_email(to_email: str, reset_link: str) -> bool:
    """Send a password reset email via the Resend REST API.

    Args:
        to_email: The recipient's email address.
        reset_link: The unique password reset URL / CLI command token.

    Returns:
        True if email was sent (or logged in dev/mock mode), False otherwise.

    Raises:
        ValueError: If to_email or reset_link is empty.
    """
    if not to_email or not to_email.strip():
        raise ValueError("Recipient email address cannot be empty.")
    if not reset_link or not reset_link.strip():
        raise ValueError("Reset link/token cannot be empty.")

    clean_email = to_email.strip()
    expire_mins = settings.password_reset_token_expire_minutes

    subject = "Password Reset Request — Multi-Agent Research Assistant"
    text_content = (
        f"Hello,\n\n"
        f"A password reset request was initiated for your Multi-Agent Research Assistant account.\n\n"
        f"To reset your password, use the following link or token (valid for {expire_mins} minutes):\n"
        f"{reset_link}\n\n"
        f"If you did not request this password reset, please ignore this email. Your password will remain unchanged.\n\n"
        f"— Multi-Agent Research Assistant Security Team"
    )
    html_content = (
        f"<div style='font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;'>"
        f"<h2 style='color: #0f172a;'>Password Reset Request</h2>"
        f"<p style='color: #334155;'>A password reset request was initiated for your <strong>Multi-Agent Research Assistant</strong> account.</p>"
        f"<p style='color: #334155;'>Click the button below or use the token to set a new password. This link is valid for <strong>{expire_mins} minutes</strong> and can only be used once:</p>"
        f"<div style='margin: 24px 0;'>"
        f"<a href='{reset_link}' style='background-color: #2563eb; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;'>Reset Password</a>"
        f"</div>"
        f"<p style='color: #64748b; font-size: 13px;'>Or copy and paste this URL into your browser / CLI:<br><code style='color: #0284c7;'>{reset_link}</code></p>"
        f"<hr style='border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;' />"
        f"<p style='color: #94a3b8; font-size: 12px;'>If you did not make this request, you can safely ignore this email. Your account remains secure.</p>"
        f"</div>"
    )

    api_key = settings.resend_api_key.strip()

    # Development / Mock Mode fallback when Resend API key is not configured
    if not api_key or api_key == "your_resend_api_key_here":
        logger.info(
            f"[DEV/MOCK EMAIL] Password reset email generated for '{clean_email}'. "
            f"Reset Link: {reset_link}"
        )
        return True

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "from": settings.resend_from_email,
        "to": [clean_email],
        "subject": subject,
        "text": text_content,
        "html": html_content,
    }

    try:
        response = requests.post(RESEND_API_URL, json=payload, headers=headers, timeout=10.0)
        if response.status_code in [200, 201]:
            logger.info(f"Password reset email sent successfully to '{clean_email}'.")
            return True
        else:
            logger.error(
                f"Resend API error sending email to '{clean_email}' "
                f"(Status {response.status_code}): {response.text}"
            )
            return False
    except Exception as e:
        logger.error(f"Failed to communicate with Resend API: {e}")
        return False
