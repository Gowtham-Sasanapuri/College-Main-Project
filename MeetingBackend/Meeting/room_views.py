import os
import uuid
import logging
import tempfile
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from .models import Meeting, TranscriptEntry, MeetingParticipant
from .audio_processor import process_audio_file
from .views import (
    _format_transcript_entries,
    _summarize_transcript,
    AskFollowUpQuestion,
    GetFollowUpHistory,
    SendMeetingReport,
    GetMeetingReportData,
    DownloadMeetingReport,
)


logger = logging.getLogger(__name__)


@api_view(["POST"])
def CreateRoomMeeting(request):
    """
    Creates a new Room Meeting instance.
    Accepts name (or host), Agenda (optional), and ai_enabled (optional boolean).
    """
    data = request.data
    host = data.get("name", "Central Device")
    agenda = data.get("Agenda", "")
    ai_enabled = bool(data.get("ai_enabled", False))
    meeting_id = uuid.uuid4()

    Meeting.objects.create(
        Meeting_id=meeting_id,
        Host_name=host,
        Agenda=agenda,
        Status=True,
        ai_enabled=ai_enabled,
        meeting_mode="room",
    )

    logger.info(f"[CREATE_ROOM_MEETING] Created room meeting: {meeting_id}")

    return Response({
        "success": True,
        "meeting_id": str(meeting_id),
        "message": "Room meeting created successfully.",
    })


@api_view(["POST"])
def ProcessRoomAudio(request):
    """
    Receives complete recorded audio file for a room meeting after End Meeting is clicked.
    Runs Pyannote speaker diarization + Whisper ASR, formats transcript as Speaker_001, Speaker_002...
    Generates summary using existing Qwen 2.5 7B integration if AI mode is enabled.
    """
    logger.info("[PROCESS_ROOM_AUDIO] Received room audio upload request")
    meeting_id = request.data.get("meeting_id")
    audio_file = request.FILES.get("audio")

    if not meeting_id or not audio_file:
        return Response({"success": False, "message": "Missing meeting_id or audio file."}, status=400)

    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)
    except Meeting.DoesNotExist:
        return Response({"success": False, "message": "Meeting not found."}, status=404)

    # Save uploaded audio file to temporary file
    file_ext = os.path.splitext(audio_file.name)[1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
        for chunk in audio_file.chunks():
            tmp.write(chunk)
        temp_audio_path = tmp.name

    logger.info(f"[PROCESS_ROOM_AUDIO] Saved room audio to temp path: {temp_audio_path}")

    try:
        hf_token = os.environ.get("HF_TOKEN")
        structured_entries = process_audio_file(temp_audio_path, hf_token=hf_token)

        # Clear any prior transcript entries for this room meeting
        meeting.transcript_entries.all().delete()

        db_entries = []
        identified_participants = {}

        for item in structured_entries:
            entry = TranscriptEntry.objects.create(
                meeting=meeting,
                speaker_name=item["speaker"],
                speaker_id=item.get("email") or item.get("speaker_id") or "",
                text=item["text"]
            )
            if item.get("is_identified") and item.get("email"):
                identified_participants[item["email"]] = item["speaker"]

            db_entries.append({
                "id": entry.pk,
                "speaker": entry.speaker_name,
                "speaker_id": entry.speaker_id or "",
                "email": item.get("email"),
                "anonymous_speaker": item.get("anonymous_speaker", entry.speaker_name),
                "is_identified": item.get("is_identified", False),
                "confidence": item.get("confidence", 0.0),
                "text": entry.text,
                "timestamp": entry.timestamp.isoformat()
            })

        # Automatically register identified participants for report delivery
        for p_email, p_name in identified_participants.items():
            MeetingParticipant.objects.get_or_create(
                meeting=meeting,
                email=p_email,
                defaults={"name": p_name}
            )

        summary_text = ""
        summary_generated = False
        if meeting.ai_enabled and db_entries:
            transcript_formatted = _format_transcript_entries(
                meeting.transcript_entries.order_by("timestamp")
            )
            try:
                summary_text = _summarize_transcript(meeting.Agenda or "", transcript_formatted)
                meeting.Summary = summary_text
                meeting.save(update_fields=["Summary"])
                summary_generated = True
            except Exception as summary_exc:
                logger.error(f"[PROCESS_ROOM_AUDIO] Summary generation error: {summary_exc}")

        return Response({
            "success": True,
            "meeting_id": str(meeting.Meeting_id),
            "transcript": db_entries,
            "participants": [
                {"id": p.pk, "email": p.email, "name": p.name}
                for p in meeting.participants.all()
            ],
            "ai_enabled": meeting.ai_enabled,
            "summary_generated": summary_generated,
            "summary": summary_text,
            "message": "Room meeting audio processed successfully."
        })

    except FileNotFoundError as fnf_exc:
        logger.error(f"[PROCESS_ROOM_AUDIO] Dependency error: {fnf_exc}")
        return Response({
            "success": False,
            "message": str(fnf_exc)
        }, status=400)
    except Exception as exc:
        logger.exception(f"[PROCESS_ROOM_AUDIO] Audio processing failed: {exc}")
        return Response({"success": False, "message": f"Audio processing failed: {str(exc)}"}, status=500)
    finally:
        if os.path.exists(temp_audio_path):
            try:
                os.remove(temp_audio_path)
            except Exception:
                pass


@api_view(["PATCH", "PUT"])
def UpdateRoomTranscript(request, entry_id):
    """
    Update the text of a specific room meeting TranscriptEntry.
    Only text can be edited; speaker_name remains unchanged.
    """
    new_text = request.data.get("text", "").strip()

    if not new_text:
        return Response({"success": False, "message": "Transcript text cannot be empty."}, status=400)

    try:
        entry = TranscriptEntry.objects.select_related("meeting").get(pk=entry_id)
    except TranscriptEntry.DoesNotExist:
        return Response({"success": False, "message": "Transcript entry not found."}, status=404)

    # Update text while preserving speaker_name and meeting relationship
    entry.text = new_text
    entry.save(update_fields=["text"])

    return Response({
        "success": True,
        "id": entry.pk,
        "speaker": entry.speaker_name,
        "text": entry.text,
        "message": "Room transcript entry updated successfully.",
    })


@api_view(["POST"])
def GenerateRoomSummary(request):
    """
    Generates or updates room meeting summary using latest (possibly edited) transcript.
    """
    meeting_id = request.data.get("meeting_id")
    if not meeting_id:
        return Response({"success": False, "message": "Meeting ID is required."}, status=400)

    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)
        entries = meeting.transcript_entries.order_by("timestamp")
        if not entries.exists():
            return Response({"success": False, "message": "No transcript is available to summarize."}, status=400)

        transcript_formatted = _format_transcript_entries(entries)
        summary = _summarize_transcript(meeting.Agenda or "", transcript_formatted)
        meeting.Summary = summary
        meeting.save(update_fields=["Summary"])

        return Response({
            "success": True,
            "summary": summary,
            "message": "Summary generated successfully."
        })
    except Meeting.DoesNotExist:
        return Response({"success": False, "message": "Meeting not found."}, status=404)
    except Exception as exc:
        logger.exception(f"[GENERATE_ROOM_SUMMARY] Error: {exc}")
        return Response({"success": False, "message": str(exc)}, status=500)


# Room-specific follow-up endpoints (aliases to shared service)
AskRoomFollowUpQuestion = AskFollowUpQuestion
GetRoomFollowUpHistory = GetFollowUpHistory


@api_view(["GET"])
def GetRoomMeetingDetails(request, meeting_id):
    """
    Retrieve room meeting details, transcript, summary, participants, and status for restoring view on page reload.
    """
    if not meeting_id:
        return Response({"success": False, "message": "Meeting ID is required."}, status=400)

    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)
        entries = meeting.transcript_entries.order_by("timestamp")
        transcript = [
            {
                "id": e.pk,
                "speaker": e.speaker_name,
                "speaker_id": e.speaker_id or "",
                "email": e.speaker_id if ("@" in (e.speaker_id or "")) else None,
                "is_identified": bool("@" in (e.speaker_id or "")),
                "text": e.text,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in entries
        ]
        participants = [
            {
                "id": p.pk,
                "email": p.email,
                "name": p.name,
                "created_at": p.created_at.isoformat(),
            }
            for p in meeting.participants.all()
        ]
        return Response({
            "success": True,
            "meeting_id": str(meeting.Meeting_id),
            "host_name": meeting.Host_name,
            "agenda": meeting.Agenda,
            "ai_enabled": meeting.ai_enabled,
            "summary": meeting.Summary or "",
            "meeting_mode": meeting.meeting_mode,
            "status": meeting.Status,
            "transcript": transcript,
            "participants": participants,
            "report_sent_at": meeting.report_sent_at.isoformat() if meeting.report_sent_at else None,
        })
    except (Meeting.DoesNotExist, ValueError):
        return Response({"success": False, "message": "Room meeting not found."}, status=404)


@api_view(["POST"])
def SetupRoomParticipants(request):
    """
    Saves the expected participant count and email addresses for an in-person Room Meeting.
    Validates count, email format, and checks for duplicates.
    Persists participants against the Room Meeting session.
    """
    data = request.data
    meeting_id = data.get("meeting_id")
    participant_count = data.get("participant_count")
    emails = data.get("emails", [])

    if not meeting_id:
        return Response({"success": False, "message": "Meeting ID is required."}, status=400)

    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)
    except (Meeting.DoesNotExist, ValueError):
        return Response({"success": False, "message": "Room meeting not found."}, status=404)

    # Validate count
    try:
        count = int(participant_count)
        if count <= 0:
            return Response({"success": False, "message": "Participant count must be at least 1."}, status=400)
        if count > 50:
            return Response({"success": False, "message": "Participant count cannot exceed 50."}, status=400)
    except (TypeError, ValueError):
        return Response({"success": False, "message": "Please enter a valid positive number for participant count."}, status=400)

    # Validate emails list length
    if not isinstance(emails, list) or len(emails) != count:
        return Response({
            "success": False,
            "message": f"Expected exactly {count} email address(es), but received {len(emails) if isinstance(emails, list) else 0}."
        }, status=400)

    # Validate each email and check for duplicates
    cleaned_emails = []
    seen = set()

    for idx, raw_email in enumerate(emails, start=1):
        email_str = (raw_email or "").strip().lower()
        if not email_str:
            return Response({
                "success": False,
                "message": f"Participant {idx} email cannot be empty."
            }, status=400)

        try:
            validate_email(email_str)
        except ValidationError:
            return Response({
                "success": False,
                "message": f"Participant {idx} ('{email_str}') is not a valid email address."
            }, status=400)

        if email_str in seen:
            return Response({
                "success": False,
                "message": f"Duplicate email address detected: '{email_str}'."
            }, status=400)

        seen.add(email_str)
        cleaned_emails.append(email_str)

    # Persist validated recipients for this room meeting
    meeting.participants.all().delete()

    created_objs = []
    for idx, email in enumerate(cleaned_emails, start=1):
        p = MeetingParticipant.objects.create(
            meeting=meeting,
            email=email,
            name=f"Participant {idx}",
        )
        created_objs.append({
            "id": p.pk,
            "email": p.email,
            "name": p.name,
            "created_at": p.created_at.isoformat(),
        })

    logger.info(f"[ROOM_PARTICIPANTS] Saved {len(created_objs)} participants for room meeting {meeting_id}")

    return Response({
        "success": True,
        "message": f"{len(created_objs)} participant email(s) saved successfully.",
        "participants": created_objs,
    })


@api_view(["GET"])
def GetRoomParticipants(request, meeting_id):
    """
    Returns list of saved participants for a room meeting.
    """
    if not meeting_id:
        return Response({"success": False, "message": "Meeting ID is required."}, status=400)

    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)
    except (Meeting.DoesNotExist, ValueError):
        return Response({"success": False, "message": "Room meeting not found."}, status=404)

    participants = [
        {
            "id": p.pk,
            "email": p.email,
            "name": p.name,
            "created_at": p.created_at.isoformat(),
        }
        for p in meeting.participants.all()
    ]

    return Response({
        "success": True,
        "meeting_id": str(meeting.Meeting_id),
        "participants": participants,
    })


# Room Meeting Report & Email endpoints (aliases to shared service)
SendRoomMeetingReport = SendMeetingReport
GetRoomMeetingReportData = GetMeetingReportData
DownloadRoomMeetingReport = DownloadMeetingReport


