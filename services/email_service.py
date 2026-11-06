import smtplib
from email.message import EmailMessage

from flask import current_app


def is_configured():
    return bool(current_app.config.get("MAIL_SERVER") and current_app.config.get("MAIL_FROM"))


def send_otp_email(recipient, otp, purpose):
    """Send an OTP without exposing it in responses or application logs."""
    if not is_configured():
        return False

    subject = "Your PaisaPath AI Verification Code"
    if purpose == "password_reset":
        subject = "Your PaisaPath AI Password Reset Code"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = current_app.config["MAIL_FROM"]
    message["To"] = recipient
    message.set_content(
        "PaisaPath AI\n"
        "Your Personal AI Financial Co-Pilot\n\n"
        f"Your verification code: {otp}\n\n"
        f"This code expires in {current_app.config['OTP_EXPIRY_MINUTES']} minutes.\n\n"
        "If you did not request this code, you can ignore this email."
    )

    with smtplib.SMTP(current_app.config["MAIL_SERVER"], current_app.config["MAIL_PORT"], timeout=10) as smtp:
        smtp.starttls()
        username = current_app.config.get("MAIL_USERNAME")
        password = current_app.config.get("MAIL_PASSWORD")
        if username:
            smtp.login(username, password)
        smtp.send_message(message)
    return True
