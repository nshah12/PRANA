"""
Email delivery — SMTP with TLS.
Dev mode: when smtp_host is empty, OTP and notifications are printed to console.
"""
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from config import settings

logger = logging.getLogger(__name__)


def _send(to: str, subject: str, html: str) -> None:
    if not settings.smtp_host:
        logger.warning(
            "[DEV EMAIL — not sent] To: %s | Subject: %s\n%s",
            to, subject,
            html.replace("<br>", "\n").replace("<b>", "").replace("</b>", ""),
        )
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = settings.smtp_from
    msg["To"]      = to
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as s:
        if settings.smtp_use_tls:
            s.starttls()
        if settings.smtp_user:
            s.login(settings.smtp_user, settings.smtp_password)
        s.sendmail(settings.smtp_from, [to], msg.as_string())


def send_otp_email(to: str, otp: str, org_name: str) -> None:
    """Send OTP for org self-registration email verification."""
    html = f"""
    <div style="font-family: 'DM Sans', sans-serif; max-width: 480px; margin: 0 auto; padding: 32px 24px;">
      <div style="margin-bottom: 24px;">
        <span style="font-family: monospace; font-size: 20px; font-weight: 700; color: #0F172A;">
          PRANA<span style="color: #6366F1;">·</span>
        </span>
      </div>
      <h1 style="font-size: 22px; font-weight: 700; color: #0F172A; margin-bottom: 8px;">
        Verify your email address
      </h1>
      <p style="color: #64748B; font-size: 14px; line-height: 1.6; margin-bottom: 24px;">
        You're registering <b>{org_name}</b> on PRANA. Enter the code below to verify
        your email address and continue with the registration.
      </p>
      <div style="background: #F1F5F9; border-radius: 16px; padding: 24px; text-align: center; margin-bottom: 24px;">
        <p style="font-size: 13px; color: #94A3B8; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em;">
          Your verification code
        </p>
        <div style="font-family: monospace; font-size: 40px; font-weight: 700; letter-spacing: 0.3em; color: #0F172A;">
          {otp}
        </div>
        <p style="font-size: 12px; color: #94A3B8; margin-top: 8px;">Expires in 10 minutes</p>
      </div>
      <p style="color: #94A3B8; font-size: 12px; line-height: 1.6;">
        If you didn't request this, please ignore this email.
        This code cannot be used to access any existing PRANA account.
      </p>
    </div>
    """
    _send(to, "Your PRANA registration code", html)


def send_contact_confirmation(to: str, name: str, enquiry_type: str) -> None:
    """Acknowledge receipt of a contact form submission."""
    html = f"""
    <div style="font-family: 'DM Sans', sans-serif; max-width: 480px; margin: 0 auto; padding: 32px 24px;">
      <div style="margin-bottom: 24px;">
        <span style="font-family: monospace; font-size: 20px; font-weight: 700; color: #0F172A;">
          PRANA<span style="color: #6366F1;">·</span>
        </span>
      </div>
      <h1 style="font-size: 22px; font-weight: 700; color: #0F172A; margin-bottom: 8px;">
        We've received your message
      </h1>
      <p style="color: #64748B; font-size: 14px; line-height: 1.6;">
        Hi {name},<br><br>
        Thank you for reaching out about <b>{enquiry_type}</b>.
        Our team will get back to you within 24 hours.
      </p>
    </div>
    """
    _send(to, "We've received your enquiry — PRANA", html)


def send_pa_contact_alert(name: str, email: str, org: str, enquiry_type: str) -> None:
    """Notify PA inbox of new contact inquiry (best-effort)."""
    if not settings.smtp_host:
        return
    html = f"""
    <div style="font-family: monospace; padding: 16px;">
      <b>New contact inquiry on PRANA</b><br><br>
      Name: {name}<br>
      Email: {email}<br>
      Org: {org or '—'}<br>
      Type: {enquiry_type}
    </div>
    """
    try:
        _send(settings.smtp_from, f"[PRANA] New inquiry — {enquiry_type}", html)
    except Exception as exc:
        logger.warning("PA alert email failed: %s", exc)
