import os
import uuid
import logging
import tempfile
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from .models import Meeting, TranscriptEntry, MeetingParticipant, MeetingAgendaItem
from .audio_processor import process_audio_file
from .views import (
    _format_transcript_entries,
    _summarize_transcript,
    _generate_mom_data,
    _build_default_mom_data,
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
    Accepts name (or host), title, description, venue (building, floor, room), scheduled times,
    Agenda, ai_enabled, and agenda_items.
    """
    data = request.data
    host = (data.get("name") or data.get("host") or "Central Device").strip()
    agenda = (data.get("Agenda") or "").strip()
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    venue = (data.get("venue") or "").strip()
    scheduled_date = (data.get("scheduled_date") or "").strip()
    scheduled_start_time = (data.get("scheduled_start_time") or "").strip()
    scheduled_end_time = (data.get("scheduled_end_time") or "").strip()
    expected_duration = (data.get("expected_duration") or "").strip()
    ai_enabled = bool(data.get("ai_enabled", False))
    auto_start = bool(data.get("auto_start", True))
    agenda_items_data = data.get("agenda_items", [])

    meeting_id = uuid.uuid4()
    now = timezone.now()

    meeting = Meeting.objects.create(
        Meeting_id=meeting_id,
        Host_name=host,
        title=title or agenda or f"Room Session {str(meeting_id)[:8]}",
        description=description,
        Agenda=agenda or title,
        Status=True if auto_start else False,
        lifecycle_status="in_progress" if auto_start else "scheduled",
        actual_start_time=now if auto_start else None,
        venue=venue or "Conference Room",
        scheduled_date=scheduled_date or (now.strftime("%Y-%m-%d") if auto_start else ""),
        scheduled_start_time=scheduled_start_time or (now.strftime("%H:%M") if auto_start else ""),
        scheduled_end_time=scheduled_end_time,
        expected_duration=expected_duration or ("45 mins" if auto_start else ""),
        ai_enabled=ai_enabled,
        meeting_mode="room",
    )

    if isinstance(agenda_items_data, list):
        for idx, item in enumerate(agenda_items_data):
            if isinstance(item, dict) and item.get("title"):
                MeetingAgendaItem.objects.create(
                    meeting=meeting,
                    title=item.get("title", "").strip(),
                    description=item.get("description", "").strip(),
                    presenter=item.get("presenter", host).strip(),
                    expected_duration=item.get("expected_duration", "").strip(),
                    order=idx,
                    status="Pending",
                )
            elif isinstance(item, str) and item.strip():
                MeetingAgendaItem.objects.create(
                    meeting=meeting,
                    title=item.strip(),
                    presenter=host,
                    order=idx,
                    status="Pending",
                )

    logger.info(f"[CREATE_ROOM_MEETING] Created room meeting: {meeting_id}")

    return Response({
        "success": True,
        "meeting_id": str(meeting_id),
        "title": meeting.display_title,
        "lifecycle_status": meeting.lifecycle_status,
        "venue": meeting.venue,
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

        cutoff = timezone.now()
        meeting.actual_end_time = cutoff
        meeting.lifecycle_status = "completed"
        meeting.Status = False
        start_time = meeting.actual_start_time or meeting.Created_at
        if start_time:
            meeting.actual_duration_seconds = max(0, int((cutoff - start_time).total_seconds()))
        meeting.save(update_fields=["actual_end_time", "lifecycle_status", "Status", "actual_duration_seconds"])

        summary_text = ""
        summary_generated = False
        mom_data = None
        if meeting.ai_enabled and db_entries:
            transcript_formatted = _format_transcript_entries(
                meeting.transcript_entries.order_by("timestamp")
            )
            try:
                mom_data, summary_text = _generate_mom_data(meeting, transcript_formatted)
                meeting.Summary = summary_text
                meeting.mom_data = mom_data
                meeting.save(update_fields=["Summary", "mom_data"])
                summary_generated = True
            except Exception as summary_exc:
                logger.error(f"[PROCESS_ROOM_AUDIO] Summary generation error: {summary_exc}")
        else:
            mom_data = _build_default_mom_data(meeting)
            meeting.mom_data = mom_data
            meeting.save(update_fields=["mom_data"])

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
            "mom_data": mom_data,
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
    Generates or updates room meeting summary and structured 10-section MoM using latest transcript.
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
        mom_data, summary = _generate_mom_data(meeting, transcript_formatted)
        meeting.Summary = summary
        meeting.mom_data = mom_data
        meeting.save(update_fields=["Summary", "mom_data"])

        return Response({
            "success": True,
            "summary": summary,
            "mom_data": mom_data,
            "message": "Minutes of Meeting and summary generated successfully."
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
        agenda_items = [
            {
                "id": a.pk,
                "title": a.title,
                "description": a.description,
                "presenter": a.presenter,
                "expected_duration": a.expected_duration,
                "order": a.order,
                "status": a.status,
            }
            for a in meeting.agenda_items.all()
        ]
        return Response({
            "success": True,
            "meeting_id": str(meeting.Meeting_id),
            "title": meeting.display_title,
            "description": meeting.description,
            "host_name": meeting.Host_name,
            "agenda": meeting.Agenda,
            "ai_enabled": meeting.ai_enabled,
            "summary": meeting.Summary or "",
            "mom_data": meeting.mom_data,
            "has_mom": bool(meeting.mom_data),
            "meeting_mode": meeting.meeting_mode,
            "status": meeting.Status,
            "lifecycle_status": meeting.lifecycle_status,
            "venue": meeting.venue,
            "scheduled_date": meeting.scheduled_date,
            "scheduled_start_time": meeting.scheduled_start_time,
            "scheduled_end_time": meeting.scheduled_end_time,
            "expected_duration": meeting.expected_duration,
            "actual_start_time": meeting.actual_start_time.isoformat() if meeting.actual_start_time else None,
            "actual_end_time": meeting.actual_end_time.isoformat() if meeting.actual_end_time else None,
            "actual_duration_seconds": meeting.actual_duration_seconds,
            "agenda_items": agenda_items,
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


