"""
Email Delivery Service for Meeting Reports.
Sends generated meeting report PDFs as attachments to participants via Django EmailMessage.
Guarantees recipient privacy by sending individual messages.
"""

import logging
from django.core.mail import EmailMessage
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.conf import settings
from django.utils import timezone
from .report_generator import generate_meeting_pdf_bytes, sanitize_filename

logger = logging.getLogger(__name__)


def validate_and_filter_emails(email_list):
    """
    Validates a list of email strings, returning only clean, valid, deduplicated lowercase emails.
    """
    valid_emails = []
    seen = set()
    for raw in email_list:
        if not raw:
            continue
        email = str(raw).strip().lower()
        if not email or email in seen:
            continue
        try:
            validate_email(email)
            valid_emails.append(email)
            seen.add(email)
        except ValidationError:
            logger.warning("[EMAIL_VALIDATE] Invalid email skipped: %s", raw)
    return valid_emails


def send_meeting_report_to_participants(meeting, recipients=None):
    """
    Generates the PDF report for the meeting and sends it to all validated participant emails.

    Args:
        meeting: The Meeting model instance.
        recipients: Optional list of email strings. If omitted, fetched from meeting.participants.

    Returns:
        dict: {"success": True, "sent_count": int, "recipients": list}
    """
    # 1. Verify summary exists
    if not meeting.Summary or not meeting.Summary.strip():
        raise ValueError("Meeting summary is not available yet. Please generate the summary before sending the report.")

    # 2. Collect and validate recipient emails
    if recipients is None:
        participant_objs = list(meeting.participants.all())
        raw_emails = [p.email for p in participant_objs]
    else:
        raw_emails = recipients
        participant_objs = list(meeting.participants.all())

    validated_emails = validate_and_filter_emails(raw_emails)

    if not validated_emails:
        raise ValueError("No valid participant email addresses found for this meeting.")

    # 3. Retrieve conversation messages and generate PDF
    follow_up_messages = list(meeting.follow_up_messages.order_by("timestamp", "pk"))
    pdf_bytes = generate_meeting_pdf_bytes(
        meeting=meeting,
        participants=participant_objs,
        follow_up_messages=follow_up_messages,
    )
    pdf_filename = sanitize_filename(meeting.Meeting_id)

    # 4. Construct email subject and body
    meeting_title = meeting.Agenda.strip() if (meeting.Agenda and meeting.Agenda.strip()) else str(meeting.Meeting_id)[:8]
    subject = f"Meeting Report - {meeting_title}"

    mode_name = "Room Meeting" if meeting.meeting_mode == "room" else "Video Calling"
    date_str = meeting.Created_at.strftime("%Y-%m-%d %H:%M UTC") if meeting.Created_at else "Recent"

    body = (
        f"Hello,\n\n"
        f"Attached is the official meeting report for your recent {mode_name} session.\n\n"
        f"Meeting ID: {meeting.Meeting_id}\n"
        f"Mode: {mode_name}\n"
        f"Date: {date_str}\n"
        f"Agenda: {meeting.Agenda or 'None'}\n\n"
        f"The attached PDF includes:\n"
        f"• Complete meeting summary and key discussion points\n"
        f"• Decisions made and action items\n"
        f"• Complete AI follow-up conversation\n\n"
        f"Best regards,\n"
        f"MeetSpace Team\n"
    )

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@meetspace.com")

    # 4b. Verify SMTP credentials if using smtp backend
    backend_name = str(getattr(settings, "EMAIL_BACKEND", "")).lower()
    if "smtp" in backend_name:
        if not getattr(settings, "EMAIL_HOST_USER", ""):
            raise ValueError(
                "SMTP configuration incomplete: EMAIL_HOST_USER (your Gmail address) is not set in your .env file."
            )
        if not getattr(settings, "EMAIL_HOST_PASSWORD", ""):
            raise ValueError(
                "SMTP configuration incomplete: GOOGLE_APP_PASSWORD is not set in your .env file."
            )

    # 5. Send individual emails to preserve recipient privacy (no recipient sees other emails in To/CC)
    successful_recipients = []
    failed_recipients = []

    for recipient in validated_emails:
        try:
            msg = EmailMessage(
                subject=subject,
                body=body,
                from_email=from_email,
                to=[recipient],
            )
            msg.attach(
                filename=pdf_filename,
                content=pdf_bytes,
                mimetype="application/pdf",
            )
            msg.send(fail_silently=False)
            successful_recipients.append(recipient)
            logger.info("[EMAIL] Sent meeting report to %s", recipient)
        except Exception as exc:
            logger.exception("[EMAIL] Failed to send report to %s: %s", recipient, exc)
            failed_recipients.append({"email": recipient, "error": str(exc)})

    if not successful_recipients:
        # If all recipients failed
        first_error = failed_recipients[0]["error"] if failed_recipients else "Unknown email sending error"
        raise RuntimeError(f"Failed to deliver meeting report email: {first_error}")

    # 6. Update report_sent_at timestamp on meeting
    meeting.report_sent_at = timezone.now()
    meeting.save(update_fields=["report_sent_at"])

    return {
        "success": True,
        "sent_count": len(successful_recipients),
        "recipients": successful_recipients,
        "failed_recipients": failed_recipients,
    }
