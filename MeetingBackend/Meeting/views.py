from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging
import os
import uuid
import requests
from .models import Meeting, TranscriptEntry, FollowUpMessage



HF_ROUTER_ENDPOINT = "https://router.huggingface.co/v1/chat/completions"
HF_MODEL = os.getenv("HF_MODEL", "Qwen/Qwen3-8B")
HF_TIMEOUT_SECONDS = int(os.getenv("HF_TIMEOUT_SECONDS", "120"))

logger = logging.getLogger(__name__)


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


def _extract_generated_text(payload):
    if isinstance(payload, dict):
        if "choices" in payload and payload["choices"]:
            choice = payload["choices"][0]
            if isinstance(choice, dict):
                message = choice.get("message")
                if isinstance(message, dict):
                    return message.get("content", "").strip()
                if isinstance(message, str):
                    return message.strip()
                return choice.get("text", "")
    return ""


def _call_hugging_face_chat(messages):
    hf_token_configured = bool(os.environ.get("HF_TOKEN"))
    logger.info("[HF] token configured: %s", hf_token_configured)

    if not hf_token_configured:
        logger.error("[HF] HF_TOKEN is not configured")
        raise RuntimeError("HF_TOKEN is not configured")

    hf_token = os.environ["HF_TOKEN"]
    model_name = os.getenv("HF_MODEL", HF_MODEL)
    logger.info("[HF] model=%s", model_name)

    payload = {
        "messages": messages,
        "model": model_name,
    }

    logger.info("[HF] sending request")
    try:
        response = requests.post(
            HF_ROUTER_ENDPOINT,
            headers={"Authorization": f"Bearer {hf_token}"},
            json=payload,
            timeout=HF_TIMEOUT_SECONDS,
        )
    except requests.exceptions.Timeout as exc:
        logger.error("[HF] request timed out: %s", exc)
        raise TimeoutError("Hugging Face request timed out") from exc
    except requests.exceptions.RequestException as exc:
        logger.error("[HF] request failed: %s", exc)
        raise ConnectionError("Hugging Face request failed") from exc

    logger.info("[HF] response status=%s", response.status_code)
    logger.info("[HF] response received")

    if response.status_code != 200:
        logger.error(
            "Hugging Face error: status=%s body=%s",
            response.status_code,
            response.text[:1000]
        )
        status_code = response.status_code
        if status_code in (401, 403):
            raise PermissionError("Unable to authenticate with the Hugging Face Router.") from None
        if status_code == 429:
            raise RuntimeError("Hugging Face rate limit exceeded") from None
        if status_code == 400:
            raise ValueError(f"Hugging Face rejected request: {response.text[:200]}") from None
        if status_code in (500, 502, 503, 504):
            raise ConnectionError("Hugging Face model or provider is unavailable") from None
        raise RuntimeError(f"Unexpected Hugging Face error status {status_code}") from None

    logger.info("[HF] parsing response")
    try:
        response_payload = response.json()
    except ValueError as exc:
        logger.error("[HF] response parsing failed: invalid JSON payload")
        raise RuntimeError("Unexpected Hugging Face response") from exc

    generated_text = _extract_generated_text(response_payload)
    if not generated_text:
        logger.error("[HF] response parsing failed: missing generated content")
        raise RuntimeError("Unexpected Hugging Face response")

    logger.info("[HF] generated content received")
    return generated_text.strip()


def _call_hugging_face(prompt):
    return _call_hugging_face_chat([{"role": "user", "content": prompt}])


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

    messages = [{"role": "system", "content": system_prompt}]

    # Bounded conversation memory: include up to the last 10 messages for context
    history_slice = previous_messages[-10:] if len(previous_messages) > 10 else previous_messages
    for msg in history_slice:
        role = "user" if msg.message_by == "user" else "assistant"
        messages.append({"role": role, "content": msg.content})

    messages.append({"role": "user", "content": question})

    return _call_hugging_face_chat(messages)



def _summarize_transcript(agenda, transcript_text):
    transcript_text = transcript_text.strip()
    if not transcript_text:
        return ""

    chunks = _chunk_transcript_lines(transcript_text.splitlines())
    if len(chunks) == 1:
        return _call_hugging_face(_build_prompt(agenda, chunks[0], chunk_summary=False))

    chunk_summaries = []
    for chunk in chunks:
        summary = _call_hugging_face(_build_prompt(agenda, chunk, chunk_summary=True))
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
    return _call_hugging_face(final_prompt)


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
            if error_message == "HF_TOKEN is not configured":
                return Response({
                    "success": False,
                    "ended": True,
                    "summary_generated": False,
                    "ai_enabled": True,
                    "message": "HF_TOKEN is not configured",
                }, status=400)
            if error_message == "Hugging Face rate limit exceeded":
                return Response({
                    "success": False,
                    "ended": True,
                    "summary_generated": False,
                    "ai_enabled": True,
                    "message": "The Hugging Face service is rate limited. Please try again shortly.",
                }, status=429)
            if error_message == "Unexpected Hugging Face response":
                return Response({
                    "success": False,
                    "ended": True,
                    "summary_generated": False,
                    "ai_enabled": True,
                    "message": "The Hugging Face response was unexpected.",
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
                "message": "Unable to authenticate with the Hugging Face Router.",
            }, status=401)
        except TimeoutError as exc:
            logger.error("[END_MEETING] TimeoutError: %s", exc)
            return Response({
                "success": False,
                "ended": True,
                "summary_generated": False,
                "ai_enabled": True,
                "message": "The Hugging Face request timed out.",
            }, status=504)
        except ConnectionError as exc:
            logger.error("[END_MEETING] ConnectionError: %s", exc)
            return Response({
                "success": False,
                "ended": True,
                "summary_generated": False,
                "ai_enabled": True,
                "message": "The Hugging Face model provider is temporarily unavailable.",
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
                "message": "The Hugging Face response did not include a summary.",
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
    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)

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

        return Response({
            "success": True,
            "message": "Successfully joined meeting.",
            "ai_enabled": meeting.ai_enabled,
            "agenda": meeting.Agenda,
            "summary": meeting.Summary or "",
            "meeting_mode": meeting.meeting_mode,
            "status": meeting.Status,
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
        if msg == "HF_TOKEN is not configured":
            return Response({"success": False, "message": "HF_TOKEN is not configured"}, status=400)
        if msg == "Hugging Face rate limit exceeded":
            return Response({"success": False, "message": "The Hugging Face service is rate limited. Please try again shortly."}, status=429)
        if msg == "Unexpected Hugging Face response":
            return Response({"success": False, "message": "The Hugging Face response was unexpected."}, status=502)
        return Response({"success": False, "message": msg or "AI response could not be generated."}, status=502)
    except PermissionError:
        return Response({"success": False, "message": "Unable to authenticate with the Hugging Face Router."}, status=401)
    except TimeoutError:
        return Response({"success": False, "message": "The Hugging Face request timed out."}, status=504)
    except ConnectionError:
        return Response({"success": False, "message": "The Hugging Face model provider is temporarily unavailable."}, status=503)
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
    })


