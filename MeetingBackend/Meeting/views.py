from django.shortcuts import render

# Create your views here.

from rest_framework.decorators import api_view
from rest_framework.response import Response
import uuid
from .models import Meeting, TranscriptEntry


@api_view(["POST"])
def CreateLink(request):
    data = request.data
    host = data.get("name")
    agenda = data.get("Agenda", "")
    ai_enabled = bool(data.get("ai_enabled", False))
    meeting_id = uuid.uuid4()

    Meeting.objects.create(
        Meeting_id=meeting_id,
        Host_name=host,
        Agenda=agenda,
        Status=True,
        ai_enabled=ai_enabled,
    )

    return Response({
        "success": True,
        "meeting_id": meeting_id,
        "message": "Meeting id Created",
    })


@api_view(["POST"])
def SearchMeeting(request):
    data = request.data
    meeting_id = data.get("id")
    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)

        # Load existing transcript if AI is enabled (for late joiners)
        transcript = []
        if meeting.ai_enabled:
            entries = meeting.transcript_entries.order_by("timestamp")
            transcript = [
                {
                    "speaker": e.speaker_name,
                    "text": e.text,
                    "timestamp": e.timestamp.isoformat(),
                }
                for e in entries
            ]

        return Response({
            "success": True,
            "message": "Successfully joined meeting.",
            "ai_enabled": meeting.ai_enabled,
            "transcript": transcript,
        })
    except Meeting.DoesNotExist:
        return Response({
            "success": False,
            "message": "Meeting does not exist.",
        })


@api_view(["GET"])
def GetTranscript(request, meeting_id):
    """Load full transcript history for a meeting (used on late join)."""
    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)
        if not meeting.ai_enabled:
            return Response({"success": True, "transcript": []})

        entries = meeting.transcript_entries.order_by("timestamp")
        transcript = [
            {
                "speaker": e.speaker_name,
                "text": e.text,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in entries
        ]
        return Response({"success": True, "transcript": transcript})
    except Meeting.DoesNotExist:
        return Response({"success": False, "message": "Meeting not found."})
