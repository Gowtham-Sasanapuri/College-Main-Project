from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.http import HttpResponse
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging
import os
import uuid
from google import genai
from google.genai import types, errors
from .models import Meeting, TranscriptEntry, FollowUpMessage, MeetingParticipant
from .email_service import send_meeting_report_to_participants, validate_and_filter_emails
from .report_generator import generate_meeting_pdf_bytes, sanitize_filename



GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "120"))

logger = logging.getLogger(__name__)


def _call_gemini_chat(contents, system_instruction=None):
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    logger.info("[GEMINI] key configured: %s", bool(gemini_api_key))

    if not gemini_api_key:
        logger.error("[GEMINI] GEMINI_API_KEY is not configured")
        raise RuntimeError("GEMINI_API_KEY is not configured")

    model_name = os.getenv("GEMINI_MODEL", GEMINI_MODEL)
    logger.info("[GEMINI] model=%s", model_name)

    logger.info("[GEMINI] sending request")
    try:
        client = genai.Client(api_key=gemini_api_key)
        config = None
        if system_instruction:
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
            )
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config,
        )
    except errors.APIError as exc:
        code = getattr(exc, "code", None)
        message = getattr(exc, "message", str(exc))
        logger.error("[GEMINI] API error: code=%s message=%s", code, message)
        if code in (401, 403):
            raise PermissionError("Unable to authenticate with Google Gemini API.") from None
        if code == 429:
            raise RuntimeError("Gemini rate limit exceeded") from None
        if code == 400:
            raise ValueError(f"Gemini rejected request: {message}") from None
        if code in (500, 502, 503, 504):
            raise ConnectionError("Google Gemini model or service is temporarily unavailable") from None
        raise RuntimeError(f"Unexpected Gemini API error: {code}") from None
    except Exception as exc:
        logger.error("[GEMINI] request failed: %s", exc)
        exc_str = str(exc).lower()
        if "timeout" in exc_str or "timed out" in exc_str:
            raise TimeoutError("Gemini request timed out") from exc
        if "connection" in exc_str or "unavailable" in exc_str:
            raise ConnectionError("Gemini service is temporarily unavailable") from exc
        raise RuntimeError(f"Unexpected error communicating with Gemini: {str(exc)}") from exc

    if not response or not response.text:
        logger.error("[GEMINI] response parsing failed: missing generated content")
        raise RuntimeError("Unexpected Gemini response")

    generated_text = response.text.strip()
    if not generated_text:
        logger.error("[GEMINI] response parsing failed: empty generated text")
        raise RuntimeError("Unexpected Gemini response")

    logger.info("[GEMINI] generated content received")
    return generated_text


def _call_gemini(prompt):
    return _call_gemini_chat(
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
    )


def _format_transcript_entries(entries):
    return "\n".join(f"{entry.speaker_name}: {entry.text}" for entry in entries).strip()


def _chunk_transcript_lines(lines, max_chars=7000):
    chunks = []
    current = []
    current_length = 0

    for line in lines:
        line_length = len(line) + 1
        if current and current_length + line_length > max_chars:
            chunks.append("\n".join(current).strip())
            current = [line]
            current_length = line_length
        else:
            current.append(line)
            current_length += line_length

    if current:
        chunks.append("\n".join(current).strip())

    return [chunk for chunk in chunks if chunk]


def _build_prompt(agenda, transcript_text, chunk_summary=False):
    agenda_text = agenda.strip() if agenda and agenda.strip() else "No agenda provided"
    return (
        "You are an AI meeting assistant.\n\n"
        "Generate an accurate and concise summary of the meeting based ONLY on the information provided below.\n\n"
        f"Meeting Agenda:\n{agenda_text}\n\n"
        f"Meeting Transcript:\n{transcript_text}\n\n"
        "Generate the summary using these sections:\n\n"
        "1. Meeting Overview\n"
        "2. Key Discussion Points\n"
        "3. Decisions Made\n"
        "4. Action Items\n"
        "5. Important Conclusions\n\n"
        "Rules:\n"
        "- Do not hallucinate information.\n"
        "- Do not invent decisions.\n"
        "- Do not invent action items.\n"
        "- Do not invent names or responsibilities.\n"
        "- Use speaker names from the transcript when identifying responsibilities.\n"
        "- Only use information present in the agenda or transcript.\n"
        "- If there are no explicit decisions, say so.\n"
        "- If there are no explicit action items, say so.\n"
    )


def _build_followup_system_prompt(agenda, summary, transcript_text):
    agenda_str = agenda.strip() if agenda and agenda.strip() else "No agenda provided."
    summary_str = summary.strip() if summary and summary.strip() else "No summary available."
    transcript_str = transcript_text.strip() if transcript_text and transcript_text.strip() else "No transcript available."

    return (
        "You are an AI meeting assistant. Your task is to answer follow-up questions about this specific meeting "
        "based strictly on the meeting context provided below.\n\n"
        f"=== Meeting Agenda ===\n{agenda_str}\n\n"
        f"=== Generated Meeting Summary ===\n{summary_str}\n\n"
        f"=== Meeting Transcript ===\n{transcript_str}\n\n"
        "=== Strict Grounding Rules ===\n"
        "1. Answer using ONLY the information provided in the meeting context above.\n"
        "2. If the user asks about information, topics, decisions, or tasks that are NOT mentioned or found in the "
        "meeting transcript or summary, clearly and explicitly state:\n"
        "\"This information was not found in the meeting transcript or summary.\"\n"
        "Do NOT speculate, guess, invent, or extrapolate details.\n"
        "3. Always use the exact speaker names or labels recorded in the transcript (e.g., 'Speaker_001', 'Speaker_002', "
        "or participant names). Never guess or invent real participant identities.\n"
        "4. Understand conversational references (such as 'that task', 'the previous decision', 'who did that') "
        "based on the previous questions and answers in this follow-up conversation.\n"
        "5. Provide direct, concise, and helpful answers without generic chatbot filler.\n"
    )


def _answer_followup_question(agenda, summary, transcript_text, previous_messages, question):
    system_prompt = _build_followup_system_prompt(agenda, summary, transcript_text)

    contents = []

    # Bounded conversation memory: include up to the last 10 messages for context
    history_slice = previous_messages[-10:] if len(previous_messages) > 10 else previous_messages
    for msg in history_slice:
        role = "user" if msg.message_by == "user" else "model"
        contents.append(types.Content(
            role=role,
            parts=[types.Part.from_text(text=msg.content)]
        ))

    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=question)]
    ))

    return _call_gemini_chat(contents, system_instruction=system_prompt)




def _summarize_transcript(agenda, transcript_text):
    transcript_text = transcript_text.strip()
    if not transcript_text:
        return ""

    chunks = _chunk_transcript_lines(transcript_text.splitlines())
    if len(chunks) == 1:
        return _call_gemini(_build_prompt(agenda, chunks[0], chunk_summary=False))

    chunk_summaries = []
    for chunk in chunks:
        summary = _call_gemini(_build_prompt(agenda, chunk, chunk_summary=True))
        if summary:
            chunk_summaries.append(summary)

    if not chunk_summaries:
        return ""

    combined = "\n\n".join(
        f"Chunk {index + 1}:\n{summary}" for index, summary in enumerate(chunk_summaries)
    )
    final_prompt = (
        "You are a meeting summarization assistant. Combine the chunk summaries into one final summary. "
        "Use only the information present below. Do not invent facts, names, dates, decisions, or action items.\n\n"
        f"Meeting Agenda:\n{agenda.strip() if agenda and agenda.strip() else 'No agenda provided'}\n\n"
        f"Chunk Summaries:\n{combined}\n\n"
        "The summary should contain:\n"
        "1. Meeting Overview\n"
        "2. Key Discussion Points\n"
        "3. Decisions Made\n"
        "4. Action Items\n"
        "5. Important Conclusions\n"
    )
    return _call_gemini(final_prompt)


@api_view(["POST"])
def CreateLink(request):
    data = request.data
    host = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    agenda = data.get("Agenda", "")
    ai_enabled = bool(data.get("ai_enabled", False))
    meeting_id = uuid.uuid4()

    meeting = Meeting.objects.create(
        Meeting_id=meeting_id,
        Host_name=host,
        Agenda=agenda,
        Status=True,
        ai_enabled=ai_enabled,
    )

    if email:
        try:
            validate_email(email)
            MeetingParticipant.objects.create(
                meeting=meeting,
                email=email.lower(),
                name=host or email.lower(),
            )
        except ValidationError:
            logger.warning("[CREATE_LINK] Invalid host email ignored: %s", email)

    return Response({
        "success": True,
        "meeting_id": meeting_id,
        "message": "Meeting id Created",
    })



@api_view(["POST"])
def EndMeeting(request):
    logger.info("[END_MEETING] request received")
    data = request.data
    meeting_id = data.get("meeting_id")
    generate_summary = data.get("generate_summary", False)

    if not meeting_id:
        logger.warning("[END_MEETING] missing meeting_id")
        return Response({"success": False, "message": "Meeting ID is required."}, status=400)

    logger.info("[END_MEETING] meeting_id present")

    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)
        cutoff = timezone.now()

        logger.info("[END_MEETING] meeting found")

        if not meeting.ai_enabled:
            logger.info("[END_MEETING] AI disabled")
            return Response({
                "success": True,
                "ended": False,
                "summary_generated": False,
                "ai_enabled": False,
                "message": "AI is disabled for this meeting.",
            })

        logger.info("[END_MEETING] AI enabled")


        if not generate_summary:
            logger.info("[END_MEETING] generate_summary=False")
            return Response({
                "success": True,
                "ended": True,
                "summary_generated": False,
                "ai_enabled": True,
                "message": "Meeting ended without summary.",
            })

        logger.info("[END_MEETING] generate_summary=True")

        transcript_entries = list(
            TranscriptEntry.objects.filter(
                meeting=meeting,
                timestamp__lte=cutoff,
            ).order_by("timestamp", "pk")
        )

        logger.info("[END_MEETING] transcript entries=%d", len(transcript_entries))

        if not transcript_entries:
            return Response({
                "success": True,
                "ended": True,
                "summary_generated": False,
                "ai_enabled": True,
                "no_transcript": True,
                "message": "No transcript is available to summarize.",
            })

        transcript_text = _format_transcript_entries(transcript_entries)
        logger.info("[END_MEETING] transcript length=%d", len(transcript_text))

        try:
            summary = _summarize_transcript(meeting.Agenda or "", transcript_text)
        except ValueError as exc:
            logger.error("[END_MEETING] ValueError: %s", exc)
            return Response({
                "success": False,
                "ended": True,
                "summary_generated": False,
                "ai_enabled": True,
                "message": str(exc) or "The summary request was invalid.",
            }, status=400)
        except RuntimeError as exc:
            error_message = str(exc)
            logger.error("[END_MEETING] RuntimeError: %s", error_message)
            if error_message == "GEMINI_API_KEY is not configured":
                return Response({
                    "success": False,
                    "ended": True,
                    "summary_generated": False,
                    "ai_enabled": True,
                    "message": "GEMINI_API_KEY is not configured",
                }, status=400)
            if error_message == "Gemini rate limit exceeded":
                return Response({
                    "success": False,
                    "ended": True,
                    "summary_generated": False,
                    "ai_enabled": True,
                    "message": "The Gemini service is rate limited. Please try again shortly.",
                }, status=429)
            if error_message == "Unexpected Gemini response":
                return Response({
                    "success": False,
                    "ended": True,
                    "summary_generated": False,
                    "ai_enabled": True,
                    "message": "The Gemini response was unexpected.",
                }, status=502)
            return Response({
                "success": False,
                "ended": True,
                "summary_generated": False,
                "ai_enabled": True,
                "message": error_message or "AI summary could not be generated.",
            }, status=502)
        except PermissionError as exc:
            logger.error("[END_MEETING] PermissionError: %s", exc)
            return Response({
                "success": False,
                "ended": True,
                "summary_generated": False,
                "ai_enabled": True,
                "message": "Unable to authenticate with the Gemini API.",
            }, status=401)
        except TimeoutError as exc:
            logger.error("[END_MEETING] TimeoutError: %s", exc)
            return Response({
                "success": False,
                "ended": True,
                "summary_generated": False,
                "ai_enabled": True,
                "message": "The Gemini request timed out.",
            }, status=504)
        except ConnectionError as exc:
            logger.error("[END_MEETING] ConnectionError: %s", exc)
            return Response({
                "success": False,
                "ended": True,
                "summary_generated": False,
                "ai_enabled": True,
                "message": "The Gemini model provider is temporarily unavailable.",
            }, status=503)
        except Exception as exc:
            logger.exception("[END_MEETING] Unexpected exception in summary generation: %s", exc)
            return Response({
                "success": False,
                "ended": True,
                "summary_generated": False,
                "ai_enabled": True,
                "message": f"Unexpected error: {str(exc)}",
            }, status=500)

        if not summary:
            logger.warning("[END_MEETING] summary is empty")
            return Response({
                "success": False,
                "ended": True,
                "summary_generated": False,
                "ai_enabled": True,
                "message": "The Gemini response did not include a summary.",
            }, status=502)

        meeting.Summary = summary
        meeting.save(update_fields=["Summary"])
        logger.info("[END_MEETING] summary generated")

        return Response({
            "success": True,
            "ended": True,
            "summary_generated": True,
            "ai_enabled": True,
            "summary": summary,
        })

    except (Meeting.DoesNotExist, ValueError) as exc:
        logger.error("[END_MEETING] Meeting lookup failed: %s", exc)
        return Response({"success": False, "message": "Meeting does not exist or invalid ID."}, status=404)
    except Exception as exc:
        logger.exception("[END_MEETING] Unexpected top-level error in EndMeeting: %s", exc)
        return Response({"success": False, "message": f"Internal server error: {str(exc)}"}, status=500)



@api_view(["POST"])
def SearchMeeting(request):
    data = request.data
    meeting_id = data.get("id")
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)

        # If email is provided, validate and associate participant with this meeting
        if email:
            try:
                validate_email(email)
                MeetingParticipant.objects.update_or_create(
                    meeting=meeting,
                    email=email.lower(),
                    defaults={"name": name or email.lower()}
                )
            except ValidationError:
                logger.warning("[JOIN_MEETING] Invalid email provided: %s", email)

        # Load existing transcript if AI is enabled (for late joiners)
        transcript = []
        if meeting.ai_enabled:
            entries = meeting.transcript_entries.order_by("timestamp")
            transcript = [
                {
                    "id": e.pk,
                    "speaker": e.speaker_name,
                    "speaker_id": e.speaker_id or "",
                    "text": e.text,
                    "timestamp": e.timestamp.isoformat(),
                }
                for e in entries
            ]

        participants = [
            {"id": p.pk, "email": p.email, "name": p.name}
            for p in meeting.participants.all()
        ]

        return Response({
            "success": True,
            "message": "Successfully joined meeting.",
            "ai_enabled": meeting.ai_enabled,
            "agenda": meeting.Agenda,
            "summary": meeting.Summary or "",
            "meeting_mode": meeting.meeting_mode,
            "status": meeting.Status,
            "transcript": transcript,
            "participants": participants,
            "report_sent_at": meeting.report_sent_at.isoformat() if meeting.report_sent_at else None,
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
                "id": e.pk,
                "speaker": e.speaker_name,
                "speaker_id": e.speaker_id or "",
                "text": e.text,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in entries
        ]
        return Response({"success": True, "transcript": transcript})
    except Meeting.DoesNotExist:
        return Response({"success": False, "message": "Meeting not found."})


@api_view(["PATCH", "PUT"])
def UpdateTranscript(request, entry_id):
    """
    Update the text of a specific TranscriptEntry.
    Backend authorization enforces that only the creator of the entry (matching speaker_id) can edit it.
    """
    participant_id = request.data.get("participant_id")
    new_text = request.data.get("text", "").strip()

    if not new_text:
        return Response({"success": False, "message": "Transcript text cannot be empty."}, status=400)

    try:
        entry = TranscriptEntry.objects.select_related("meeting").get(pk=entry_id)
    except TranscriptEntry.DoesNotExist:
        return Response({"success": False, "message": "Transcript entry not found."}, status=404)

    # Authorization check
    if not entry.speaker_id or entry.speaker_id != participant_id:
        return Response({
            "success": False,
            "message": "Forbidden: You are only allowed to edit your own transcript entries.",
        }, status=403)

    # Update text while preserving meeting, speaker, timestamp, ownership
    entry.text = new_text
    entry.save(update_fields=["text"])

    # Broadcast update to all participants via Django Channels
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            str(entry.meeting.Meeting_id),
            {
                "type": "send_transcript_update",
                "id": entry.pk,
                "text": new_text,
            },
        )

    return Response({
        "success": True,
        "id": entry.pk,
        "text": entry.text,
        "message": "Transcript entry updated.",
    })


@api_view(["POST"])
def AskFollowUpQuestion(request):
    """
    Accepts meeting_id and user question.
    Verifies meeting existence, AI status, and presence of summary.
    Constructs bounded conversation context and queries the AI model.
    Persists user question and AI response atomically.
    """
    data = request.data
    meeting_id = data.get("meeting_id")
    question = (data.get("question") or "").strip()

    if not meeting_id:
        return Response({"success": False, "message": "Meeting ID is required."}, status=400)

    if not question:
        return Response({"success": False, "message": "Question cannot be empty."}, status=400)

    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)
    except (Meeting.DoesNotExist, ValueError):
        return Response({"success": False, "message": "Meeting not found."}, status=404)

    if not meeting.ai_enabled:
        return Response({"success": False, "message": "AI is disabled for this meeting."}, status=400)

    # Check if summary is available
    if not meeting.Summary or not meeting.Summary.strip():
        return Response({
            "success": False,
            "message": "Meeting summary is not yet available. Please generate the summary before asking follow-up questions.",
        }, status=400)

    # Retrieve transcript
    entries = meeting.transcript_entries.order_by("timestamp")
    transcript_text = _format_transcript_entries(entries)

    # Retrieve existing follow-up messages for conversation memory
    previous_messages = list(meeting.follow_up_messages.order_by("timestamp", "pk"))

    # Generate answer from AI
    try:
        ai_reply = _answer_followup_question(
            agenda=meeting.Agenda or "",
            summary=meeting.Summary,
            transcript_text=transcript_text,
            previous_messages=previous_messages,
            question=question,
        )
    except ValueError as exc:
        return Response({"success": False, "message": str(exc) or "Invalid request."}, status=400)
    except RuntimeError as exc:
        msg = str(exc)
        if msg == "GEMINI_API_KEY is not configured":
            return Response({"success": False, "message": "GEMINI_API_KEY is not configured"}, status=400)
        if msg == "Gemini rate limit exceeded":
            return Response({"success": False, "message": "The Gemini service is rate limited. Please try again shortly."}, status=429)
        if msg == "Unexpected Gemini response":
            return Response({"success": False, "message": "The Gemini response was unexpected."}, status=502)
        return Response({"success": False, "message": msg or "AI response could not be generated."}, status=502)
    except PermissionError:
        return Response({"success": False, "message": "Unable to authenticate with the Gemini API."}, status=401)
    except TimeoutError:
        return Response({"success": False, "message": "The Gemini request timed out."}, status=504)
    except ConnectionError:
        return Response({"success": False, "message": "The Gemini model provider is temporarily unavailable."}, status=503)
    except Exception as exc:
        logger.exception("[FOLLOWUP] Unexpected error generating AI reply: %s", exc)
        return Response({"success": False, "message": f"Unexpected error: {str(exc)}"}, status=500)

    if not ai_reply:
        return Response({"success": False, "message": "AI did not generate a response."}, status=502)

    # Persist user question and AI response atomically
    try:
        with transaction.atomic():
            user_msg = FollowUpMessage.objects.create(
                meeting=meeting,
                message_by="user",
                content=question,
            )
            ai_msg = FollowUpMessage.objects.create(
                meeting=meeting,
                message_by="ai",
                content=ai_reply,
            )
    except Exception as exc:
        logger.exception("[FOLLOWUP] Database persistence error: %s", exc)
        return Response({"success": False, "message": "Failed to persist conversation message."}, status=500)

    return Response({
        "success": True,
        "message": "AI response generated successfully.",
        "user_message": {
            "id": user_msg.pk,
            "meeting_id": str(meeting.Meeting_id),
            "message_by": user_msg.message_by,
            "content": user_msg.content,
            "timestamp": user_msg.timestamp.isoformat(),
        },
        "ai_message": {
            "id": ai_msg.pk,
            "meeting_id": str(meeting.Meeting_id),
            "message_by": ai_msg.message_by,
            "content": ai_msg.content,
            "timestamp": ai_msg.timestamp.isoformat(),
        },
    })


@api_view(["GET"])
def GetFollowUpHistory(request, meeting_id):
    """
    Returns the complete follow-up conversation history for a given meeting
    in strict chronological order.
    """
    if not meeting_id:
        return Response({"success": False, "message": "Meeting ID is required."}, status=400)

    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)
    except (Meeting.DoesNotExist, ValueError):
        return Response({"success": False, "message": "Meeting not found."}, status=404)

    messages = meeting.follow_up_messages.order_by("timestamp", "pk")
    serialized = [
        {
            "id": m.pk,
            "meeting_id": str(meeting.Meeting_id),
            "message_by": m.message_by,
            "content": m.content,
            "timestamp": m.timestamp.isoformat(),
        }
        for m in messages
    ]

    return Response({
        "success": True,
        "meeting_id": str(meeting.Meeting_id),
        "messages": serialized,
    })


@api_view(["GET"])
def GetMeetingDetails(request, meeting_id):
    """
    Returns meeting details including summary, status, and transcript.
    Used for restoring completed meeting view on reload.
    """
    if not meeting_id:
        return Response({"success": False, "message": "Meeting ID is required."}, status=400)

    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)
    except (Meeting.DoesNotExist, ValueError):
        return Response({"success": False, "message": "Meeting not found."}, status=404)

    transcript = []
    if meeting.ai_enabled:
        entries = meeting.transcript_entries.order_by("timestamp")
        transcript = [
            {
                "id": e.pk,
                "speaker": e.speaker_name,
                "speaker_id": e.speaker_id or "",
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
        "participants": [
            {"id": p.pk, "email": p.email, "name": p.name}
            for p in meeting.participants.all()
        ],
        "report_sent_at": meeting.report_sent_at.isoformat() if meeting.report_sent_at else None,
    })


@api_view(["POST"])
def RegisterParticipant(request):
    """
    Register or update a participant for a meeting.
    Validates email format. Avoids duplicate registrations.
    """
    data = request.data
    meeting_id = data.get("meeting_id")
    email = (data.get("email") or "").strip().lower()
    name = (data.get("name") or "").strip()

    if not meeting_id:
        return Response({"success": False, "message": "Meeting ID is required."}, status=400)
    if not email:
        return Response({"success": False, "message": "Email address is required."}, status=400)

    try:
        validate_email(email)
    except ValidationError:
        return Response({"success": False, "message": "Please enter a valid email address."}, status=400)

    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)
    except (Meeting.DoesNotExist, ValueError):
        return Response({"success": False, "message": "Meeting not found."}, status=404)

    participant, created = MeetingParticipant.objects.update_or_create(
        meeting=meeting,
        email=email,
        defaults={"name": name or email}
    )

    return Response({
        "success": True,
        "message": "Participant registered successfully.",
        "participant": {
            "id": participant.pk,
            "email": participant.email,
            "name": participant.name,
            "created_at": participant.created_at.isoformat(),
        }
    })


@api_view(["GET"])
def GetMeetingParticipants(request, meeting_id):
    """
    Returns list of registered participants for a meeting.
    """
    if not meeting_id:
        return Response({"success": False, "message": "Meeting ID is required."}, status=400)

    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)
    except (Meeting.DoesNotExist, ValueError):
        return Response({"success": False, "message": "Meeting not found."}, status=404)

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


@api_view(["GET"])
def GetMeetingReportData(request, meeting_id):
    """
    Retrieves complete meeting report data:
    - Metadata (ID, mode, host, agenda, created_at, report_sent_at)
    - Summary
    - Validated participants
    - Complete chronological AI follow-up conversation
    """
    if not meeting_id:
        return Response({"success": False, "message": "Meeting ID is required."}, status=400)

    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)
    except (Meeting.DoesNotExist, ValueError):
        return Response({"success": False, "message": "Meeting not found."}, status=404)

    participants = [
        {
            "id": p.pk,
            "email": p.email,
            "name": p.name,
            "created_at": p.created_at.isoformat(),
        }
        for p in meeting.participants.all()
    ]

    messages = [
        {
            "id": m.pk,
            "message_by": m.message_by,
            "content": m.content,
            "timestamp": m.timestamp.isoformat(),
        }
        for m in meeting.follow_up_messages.order_by("timestamp", "pk")
    ]

    return Response({
        "success": True,
        "meeting_id": str(meeting.Meeting_id),
        "agenda": meeting.Agenda,
        "host_name": meeting.Host_name,
        "meeting_mode": meeting.meeting_mode,
        "created_at": meeting.Created_at.isoformat() if meeting.Created_at else None,
        "summary": meeting.Summary or "",
        "ai_enabled": meeting.ai_enabled,
        "report_sent_at": meeting.report_sent_at.isoformat() if meeting.report_sent_at else None,
        "participants": participants,
        "follow_up_messages": messages,
    })


@api_view(["POST"])
def SendMeetingReport(request):
    """
    Generates meeting report PDF and emails it to all registered participants.
    Validates meeting existence, presence of summary, and registered email addresses.
    """
    meeting_id = request.data.get("meeting_id")
    if not meeting_id:
        return Response({"success": False, "message": "Meeting ID is required."}, status=400)

    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)
    except (Meeting.DoesNotExist, ValueError):
        return Response({"success": False, "message": "Meeting not found."}, status=404)

    if not meeting.Summary or not meeting.Summary.strip():
        return Response({
            "success": False,
            "message": "Meeting summary is not available yet. Please generate the summary before sending the report."
        }, status=400)

    participants = list(meeting.participants.all())
    if not participants:
        return Response({
            "success": False,
            "message": "No participant email addresses have been registered for this meeting."
        }, status=400)

    try:
        result = send_meeting_report_to_participants(meeting)
        return Response({
            "success": True,
            "message": f"Meeting report successfully sent to {result['sent_count']} participant(s).",
            "recipients": result["recipients"],
            "sent_count": result["sent_count"],
            "report_sent_at": meeting.report_sent_at.isoformat() if meeting.report_sent_at else None,
        })
    except ValueError as val_err:
        return Response({"success": False, "message": str(val_err)}, status=400)
    except Exception as exc:
        logger.exception("[SEND_REPORT] Failed to send meeting report: %s", exc)
        return Response({
            "success": False,
            "message": f"Failed to deliver email: {str(exc)}"
        }, status=502)


@api_view(["GET"])
def DownloadMeetingReport(request, meeting_id):
    """
    Generates and downloads the meeting report PDF.
    Can be used directly or as backend fallback.
    """
    if not meeting_id:
        return Response({"success": False, "message": "Meeting ID is required."}, status=400)

    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)
    except (Meeting.DoesNotExist, ValueError):
        return Response({"success": False, "message": "Meeting not found."}, status=404)

    if not meeting.Summary or not meeting.Summary.strip():
        return Response({
            "success": False,
            "message": "Meeting summary is not available yet."
        }, status=400)

    pdf_bytes = generate_meeting_pdf_bytes(meeting)
    filename = sanitize_filename(meeting.Meeting_id)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response



