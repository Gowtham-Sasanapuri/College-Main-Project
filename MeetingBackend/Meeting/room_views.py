import os
import uuid
import logging
import tempfile
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Meeting, TranscriptEntry
from .audio_processor import process_audio_file
from .views import (
    _format_transcript_entries,
    _summarize_transcript,
    AskFollowUpQuestion,
    GetFollowUpHistory,
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
        for item in structured_entries:
            entry = TranscriptEntry.objects.create(
                meeting=meeting,
                speaker_name=item["speaker"],
                text=item["text"]
            )
            db_entries.append({
                "id": entry.pk,
                "speaker": entry.speaker_name,
                "text": entry.text,
                "timestamp": entry.timestamp.isoformat()
            })

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
    Retrieve room meeting details, transcript, summary, and status for restoring view on page reload.
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
                "text": e.text,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in entries
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
        })
    except (Meeting.DoesNotExist, ValueError):
        return Response({"success": False, "message": "Room meeting not found."}, status=404)

