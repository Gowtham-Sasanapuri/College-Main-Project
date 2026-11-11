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
import json
import zoneinfo
from google import genai
from google.genai import types, errors
from .models import Meeting, TranscriptEntry, FollowUpMessage, MeetingParticipant, MeetingAgendaItem
from .email_service import send_meeting_report_to_participants, validate_and_filter_emails
from .report_generator import generate_meeting_pdf_bytes, sanitize_filename, IST, _to_ist, _format_time_ist, _format_date_ist, _format_duration_seconds



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


def _extract_json_from_llm(text):
    text = (text or "").strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    try:
        return json.loads(text)
    except Exception:
        s = text.find("{")
        e = text.rfind("}")
        if s != -1 and e != -1 and e > s:
            return json.loads(text[s:e+1])
        raise


def _format_mom_markdown(mom_data):
    """Formats structured MoM data dictionary into a publication-ready 10-section markdown document."""
    info = mom_data.get("meeting_info", {})
    att = mom_data.get("attendance", {})
    agenda_list = mom_data.get("agenda", [])
    exec_summary = mom_data.get("executive_summary", "")
    disc_points = mom_data.get("discussion_points", [])
    decisions = mom_data.get("decisions_made", [])
    actions = mom_data.get("action_items", [])
    unresolved = mom_data.get("unresolved_questions", [])
    conclusion = mom_data.get("conclusion", "")
    next_meet = mom_data.get("next_meeting", {})

    lines = [
        f"# Minutes of Meeting (MoM): {info.get('title', 'Meeting')}",
        "",
        "## A. Meeting Information",
        f"- **Meeting Title:** {info.get('title', 'N/A')}",
        f"- **Meeting Type:** {info.get('meeting_type', 'N/A')}",
        f"- **Date:** {info.get('date', 'N/A')}",
        f"- **Scheduled Time:** {info.get('scheduled_start_time', 'N/A')} - {info.get('scheduled_end_time', 'N/A')} (Expected Duration: {info.get('scheduled_duration', 'N/A')})",
        f"- **Actual Time:** {info.get('actual_start_time', 'N/A')} - {info.get('actual_end_time', 'N/A')} (Actual Duration: {info.get('actual_duration', 'N/A')})",
        f"- **Venue:** {info.get('venue', 'N/A')}",
        f"- **Organizer:** {info.get('organizer', 'N/A')}",
        "",
        "## B. Attendance and Participants",
        "### Present Participants:",
    ]
    present_list = att.get("present", [])
    if present_list:
        for p in present_list:
            p_name = p.get("name") if isinstance(p, dict) else str(p)
            p_role = f" ({p.get('role')})" if isinstance(p, dict) and p.get("role") else ""
            lines.append(f"- {p_name}{p_role}")
    else:
        lines.append("- None recorded")

    absent_list = att.get("absent", [])
    if absent_list:
        lines.append("### Absent Participants:")
        for a in absent_list:
            lines.append(f"- {a}")

    speakers = att.get("speakers_identified", [])
    if speakers:
        lines.append(f"### Identified Speakers: {', '.join(speakers)}")

    lines.extend([
        "",
        "## C. Meeting Agenda",
    ])
    if agenda_list:
        for idx, item in enumerate(agenda_list, 1):
            if isinstance(item, dict):
                p_text = f" (Presenter: {item.get('presenter')})" if item.get('presenter') else ""
                s_text = f" — [{item.get('status', 'Discussed')}]"
                lines.append(f"{idx}. **{item.get('title', 'Topic')}**{p_text}{s_text}")
                if item.get("notes") or item.get("description"):
                    lines.append(f"   - {item.get('notes') or item.get('description')}")
            else:
                lines.append(f"{idx}. {item}")
    else:
        lines.append("- No formal agenda specified.")

    lines.extend([
        "",
        "## D. Executive Summary",
        exec_summary or "No executive summary available.",
        "",
        "## E. Detailed Discussion Points",
    ])
    if disc_points:
        for dp in disc_points:
            if isinstance(dp, dict):
                topic = dp.get("topic", "Discussion Topic")
                details = dp.get("details", "")
                speakers_str = f" [Speakers: {', '.join(dp.get('speakers', []))}]" if dp.get("speakers") else ""
                lines.append(f"### {topic}{speakers_str}")
                lines.append(f"{details}")
            else:
                lines.append(f"- {dp}")
    else:
        lines.append("No detailed discussion points recorded.")

    lines.extend([
        "",
        "## F. Decisions Made",
    ])
    if decisions:
        for idx, dec in enumerate(decisions, 1):
            lines.append(f"{idx}. {dec}")
    else:
        lines.append("No explicit decisions agreed upon during the meeting.")

    lines.extend([
        "",
        "## G. Action Items",
    ])
    if actions:
        lines.append("| Item Description | Assigned Owner | Priority | Deadline | Status |")
        lines.append("| --- | --- | --- | --- | --- |")
        for act in actions:
            if isinstance(act, dict):
                lines.append(f"| {act.get('description', '')} | {act.get('owner', 'Unassigned')} | {act.get('priority', 'Medium')} | {act.get('deadline', 'TBD')} | {act.get('status', 'Pending')} |")
            else:
                lines.append(f"| {act} | Unassigned | Medium | TBD | Pending |")
    else:
        lines.append("No action items assigned.")

    lines.extend([
        "",
        "## H. Unresolved Questions and Pending Issues",
    ])
    if unresolved and any(unresolved):
        for q in unresolved:
            lines.append(f"- {q}")
    else:
        lines.append("None identified during the meeting.")

    lines.extend([
        "",
        "## I. Conclusion",
        conclusion or "Meeting adjourned with planned follow-ups as indicated in the action items.",
        "",
        "## J. Next Meeting Details",
    ])
    if isinstance(next_meet, dict) and any(next_meet.values()) and any(str(v).lower() not in ["not discussed", "none scheduled", "none", ""] for v in next_meet.values()):
        lines.append(f"- **Proposed Date:** {next_meet.get('date', 'Not specified')}")
        lines.append(f"- **Time:** {next_meet.get('time', 'Not specified')}")
        lines.append(f"- **Venue:** {next_meet.get('venue', 'Not specified')}")
        if next_meet.get("agenda"):
            lines.append(f"- **Preliminary Agenda:** {next_meet.get('agenda')}")
        if next_meet.get("notes"):
            lines.append(f"- **Notes:** {next_meet.get('notes')}")
    else:
        lines.append("Not discussed during the meeting.")

    return "\n".join(lines).strip()


def _build_default_mom_data(meeting):
    """Builds a structured 10-section MoM fallback structure from meeting metadata."""
    title = meeting.display_title
    mode_label = "Online Video Meeting (WebRTC)" if meeting.meeting_mode == "video" else "In-Room Meeting (Acoustic Diarization)"
    date_str = meeting.scheduled_date or (meeting.actual_start_time.strftime("%Y-%m-%d") if meeting.actual_start_time else meeting.Created_at.strftime("%Y-%m-%d"))
    sched_start = meeting.scheduled_start_time or "N/A"
    sched_end = meeting.scheduled_end_time or "N/A"
    sched_dur = meeting.expected_duration or "N/A"

    act_start = meeting.actual_start_time.strftime("%H:%M:%S") if meeting.actual_start_time else meeting.Created_at.strftime("%H:%M:%S")
    act_end = meeting.actual_end_time.strftime("%H:%M:%S") if meeting.actual_end_time else "Ongoing"

    dur_secs = meeting.actual_duration_seconds or 0
    actual_dur_str = f"{dur_secs // 60}m {dur_secs % 60}s" if dur_secs > 0 else "N/A"

    venue_str = meeting.venue or (f"Online Link: /Meeting/{meeting.Meeting_id}" if meeting.meeting_mode == "video" else "Meeting Room")
    organizer_str = meeting.Host_name or "Organizer"

    participants = list(meeting.participants.all())
    present_list = [{"name": p.name or p.email, "email": p.email, "role": "Organizer" if p.name == meeting.Host_name else "Participant"} for p in participants]
    if not present_list:
        present_list = [{"name": organizer_str, "email": "", "role": "Organizer"}]

    agenda_objs = list(meeting.agenda_items.all())
    agenda_list = [
        {
            "title": a.title,
            "presenter": a.presenter or organizer_str,
            "expected_duration": a.expected_duration or "",
            "status": a.status or "Discussed",
            "notes": a.description or "",
        }
        for a in agenda_objs
    ]
    if not agenda_list and meeting.Agenda:
        agenda_list = [{"title": meeting.Agenda, "presenter": organizer_str, "status": "Discussed", "notes": ""}]

    entries = meeting.transcript_entries.all()
    speakers_set = set()
    for e in entries:
        if e.speaker_name:
            speakers_set.add(e.speaker_name)
    speakers_list = sorted(list(speakers_set))

    return {
        "meeting_info": {
            "title": title,
            "meeting_type": mode_label,
            "date": date_str,
            "scheduled_start_time": sched_start,
            "scheduled_end_time": sched_end,
            "scheduled_duration": sched_dur,
            "actual_start_time": act_start,
            "actual_end_time": act_end,
            "actual_duration": actual_dur_str,
            "actual_duration_seconds": dur_secs,
            "venue": venue_str,
            "organizer": organizer_str,
        },
        "attendance": {
            "present": present_list,
            "absent": [],
            "speakers_identified": speakers_list,
        },
        "agenda": agenda_list,
        "executive_summary": meeting.Summary or "Meeting recorded.",
        "discussion_points": [],
        "decisions_made": [],
        "action_items": [],
        "unresolved_questions": ["None identified during the meeting."],
        "conclusion": "Meeting adjourned successfully.",
        "next_meeting": {
            "date": "Not discussed",
            "time": "Not discussed",
            "venue": "Not discussed",
            "agenda": "None scheduled",
            "notes": ""
        }
    }


def _generate_mom_data(meeting, transcript_text):
    """
    Generates structured 10-section Minutes of Meeting (MoM) data using Gemini 2.5 Flash.
    Strictly grounded on transcript and agenda metadata with zero hallucinations.
    """
    base_mom = _build_default_mom_data(meeting)
    title = base_mom["meeting_info"]["title"]
    organizer_str = base_mom["meeting_info"]["organizer"]
    mode_label = base_mom["meeting_info"]["meeting_type"]
    date_str = base_mom["meeting_info"]["date"]
    agenda_list = base_mom["agenda"]
    speakers_list = base_mom["attendance"]["speakers_identified"]

    if not (transcript_text or "").strip():
        base_mom["executive_summary"] = f"Meeting conducted by {organizer_str}. No spoken audio or transcript was recorded."
        markdown_text = _format_mom_markdown(base_mom)
        return base_mom, markdown_text

    system_instruction = (
        "You are an executive meeting documentation secretary and AI assistant. "
        "Your duty is to generate accurate, professional, objective Minutes of Meeting (MoM) "
        "strictly based on the supplied meeting metadata and transcript.\n"
        "Follow these strict grounding rules:\n"
        "1. Never invent or hallucinate information not present in the transcript or metadata.\n"
        "2. Only extract facts, discussions, decisions, and action items that were genuinely stated.\n"
        "3. If a section was not discussed (e.g. next meeting or unresolved questions), state 'None identified during the meeting' or 'Not discussed' instead of inventing details.\n"
        "4. Assign action items only to participants explicitly mentioned in the transcript or metadata.\n"
        "5. Output valid JSON only, without markdown wrapping or conversational comments."
    )

    prompt = (
        f"Meeting Title: {title}\n"
        f"Organizer: {organizer_str}\n"
        f"Meeting Mode: {mode_label}\n"
        f"Scheduled Date: {date_str}\n"
        f"Agenda Items: {json.dumps(agenda_list)}\n"
        f"Identified Speakers: {json.dumps(speakers_list)}\n\n"
        f"=== TRANSCRIPT ===\n"
        f"{transcript_text}\n"
        f"==================\n\n"
        "Generate a structured JSON object representing the meeting analysis with the following exact keys:\n"
        "{\n"
        '  "executive_summary": "Concise high-level executive summary of key discussions and outcomes",\n'
        '  "agenda_evaluation": [\n'
        '    {"title": "Agenda Item Title", "presenter": "Presenter Name", "status": "Discussed | Partially Discussed | Skipped", "notes": "Summary of discussion on this item"}\n'
        '  ],\n'
        '  "discussion_points": [\n'
        '    {"topic": "Topic Heading", "details": "Detailed explanation of points, perspectives, and data discussed", "speakers": ["Speaker Name(s)"]}\n'
        '  ],\n'
        '  "decisions_made": [\n'
        '    "Numbered clear decision agreed upon"\n'
        '  ],\n'
        '  "action_items": [\n'
        '    {"description": "Action item description", "owner": "Assigned Person or Unassigned", "priority": "High | Medium | Low", "deadline": "Target date or TBD", "status": "Pending"}\n'
        '  ],\n'
        '  "unresolved_questions": [\n'
        '    "Pending issue or question requiring follow-up (or \'None identified during the meeting\')"\n'
        '  ],\n'
        '  "conclusion": "Final wrap-up summary and general consensus",\n'
        '  "next_meeting": {\n'
        '    "date": "Date or \'Not discussed\'",\n'
        '    "time": "Time or \'Not discussed\'",\n'
        '    "venue": "Venue or \'Not discussed\'",\n'
        '    "agenda": "Preliminary topics or \'None scheduled\'",\n'
        '    "notes": ""\n'
        '  }\n'
        "}\n\n"
        "Return ONLY the valid JSON object."
    )

    try:
        raw_res = _call_gemini_chat(
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            system_instruction=system_instruction
        )
        parsed = _extract_json_from_llm(raw_res)

        if parsed.get("executive_summary"):
            base_mom["executive_summary"] = parsed["executive_summary"]
        if parsed.get("agenda_evaluation") and isinstance(parsed["agenda_evaluation"], list):
            base_mom["agenda"] = parsed["agenda_evaluation"]
        if parsed.get("discussion_points") and isinstance(parsed["discussion_points"], list):
            base_mom["discussion_points"] = parsed["discussion_points"]
        if parsed.get("decisions_made") and isinstance(parsed["decisions_made"], list):
            base_mom["decisions_made"] = parsed["decisions_made"]
        if parsed.get("action_items") and isinstance(parsed["action_items"], list):
            base_mom["action_items"] = parsed["action_items"]
        if parsed.get("unresolved_questions") and isinstance(parsed["unresolved_questions"], list):
            base_mom["unresolved_questions"] = parsed["unresolved_questions"]
        if parsed.get("conclusion"):
            base_mom["conclusion"] = parsed["conclusion"]
        if parsed.get("next_meeting") and isinstance(parsed["next_meeting"], dict):
            base_mom["next_meeting"] = parsed["next_meeting"]

    except Exception as exc:
        logger.error("[GENERATE_MOM] Gemini JSON parsing failed: %s; falling back to text summary", exc)
        try:
            summary_txt = _summarize_transcript(meeting.Agenda or "", transcript_text)
            base_mom["executive_summary"] = summary_txt
        except Exception:
            base_mom["executive_summary"] = "AI summary generation could not be completed."

    markdown_text = _format_mom_markdown(base_mom)
    return base_mom, markdown_text


@api_view(["POST"])
def CreateLink(request):
    data = request.data
    host = (data.get("name") or data.get("host") or "").strip()
    email = (data.get("email") or "").strip()
    agenda = data.get("Agenda", "")
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
        Host_name=host or "Organizer",
        title=title or agenda or f"Video Meeting {str(meeting_id)[:8]}",
        description=description,
        Agenda=agenda or title,
        Status=True if auto_start else False,
        lifecycle_status="in_progress" if auto_start else "scheduled",
        actual_start_time=now if auto_start else None,
        venue=venue or f"Online (Meeting ID: {meeting_id})",
        scheduled_date=scheduled_date or (now.strftime("%Y-%m-%d") if auto_start else ""),
        scheduled_start_time=scheduled_start_time or (now.strftime("%H:%M") if auto_start else ""),
        scheduled_end_time=scheduled_end_time,
        expected_duration=expected_duration or ("30 mins" if auto_start else ""),
        meeting_mode="video",
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

    return Response({
        "success": True,
        "meeting_id": str(meeting_id),
        "title": meeting.display_title,
        "lifecycle_status": meeting.lifecycle_status,
        "message": "Meeting created successfully.",
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

        # Update meeting lifecycle to completed and calculate actual duration
        meeting.actual_end_time = cutoff
        meeting.lifecycle_status = "completed"
        meeting.Status = False
        start_time = meeting.actual_start_time or meeting.Created_at
        if start_time:
            meeting.actual_duration_seconds = max(0, int((cutoff - start_time).total_seconds()))
        meeting.save(update_fields=["actual_end_time", "lifecycle_status", "Status", "actual_duration_seconds"])

        logger.info("[END_MEETING] meeting found and marked completed")

        if not meeting.ai_enabled:
            logger.info("[END_MEETING] AI disabled")
            meeting.mom_data = _build_default_mom_data(meeting)
            meeting.save(update_fields=["mom_data"])
            return Response({
                "success": True,
                "ended": True,
                "summary_generated": False,
                "ai_enabled": False,
                "mom_data": meeting.mom_data,
                "message": "AI is disabled for this meeting.",
            })

        logger.info("[END_MEETING] AI enabled")

        if not generate_summary:
            logger.info("[END_MEETING] generate_summary=False")
            meeting.mom_data = _build_default_mom_data(meeting)
            meeting.save(update_fields=["mom_data"])
            return Response({
                "success": True,
                "ended": True,
                "summary_generated": False,
                "ai_enabled": True,
                "mom_data": meeting.mom_data,
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
            meeting.mom_data = _build_default_mom_data(meeting)
            meeting.save(update_fields=["mom_data"])
            return Response({
                "success": True,
                "ended": True,
                "summary_generated": False,
                "ai_enabled": True,
                "no_transcript": True,
                "mom_data": meeting.mom_data,
                "message": "No transcript is available to summarize.",
            })

        transcript_text = _format_transcript_entries(transcript_entries)
        logger.info("[END_MEETING] transcript length=%d", len(transcript_text))

        try:
            mom_data, summary = _generate_mom_data(meeting, transcript_text)
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
        meeting.mom_data = mom_data
        meeting.save(update_fields=["Summary", "mom_data"])
        logger.info("[END_MEETING] summary and MoM data generated and saved")

        return Response({
            "success": True,
            "ended": True,
            "summary_generated": True,
            "ai_enabled": True,
            "summary": summary,
            "mom_data": mom_data,
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
        "has_mom": bool(meeting.mom_data),
        "mom_data": meeting.mom_data,
        "agenda_items": agenda_items,
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
        "agenda": meeting.Agenda,
        "host_name": meeting.Host_name,
        "meeting_mode": meeting.meeting_mode,
        "venue": meeting.venue,
        "scheduled_date": meeting.scheduled_date,
        "scheduled_start_time": meeting.scheduled_start_time,
        "scheduled_end_time": meeting.scheduled_end_time,
        "expected_duration": meeting.expected_duration,
        "actual_start_time": meeting.actual_start_time.isoformat() if meeting.actual_start_time else None,
        "actual_end_time": meeting.actual_end_time.isoformat() if meeting.actual_end_time else None,
        "actual_duration_seconds": meeting.actual_duration_seconds,
        "created_at": meeting.Created_at.isoformat() if meeting.Created_at else None,
        "summary": meeting.Summary or "",
        "mom_data": meeting.mom_data,
        "ai_enabled": meeting.ai_enabled,
        "report_sent_at": meeting.report_sent_at.isoformat() if meeting.report_sent_at else None,
        "participants": participants,
        "agenda_items": agenda_items,
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


@api_view(["GET"])
def ListMeetings(request):
    """
    List all meetings with flexible filtering:
    - mode: "all" | "video" | "room"
    - status: "all" | "scheduled" | "in_progress" | "completed" | "cancelled"
    - search: keyword search in title, host_name, venue, description, agenda
    - date: scheduled_date filter (YYYY-MM-DD)
    """
    qs = Meeting.objects.all().order_by("-Created_at")

    mode = request.GET.get("mode", "all")
    if mode and mode != "all":
        qs = qs.filter(meeting_mode=mode)

    status_filter = request.GET.get("status", "all")
    if status_filter and status_filter != "all":
        qs = qs.filter(lifecycle_status=status_filter)

    search = request.GET.get("search", "").strip()
    if search:
        from django.db.models import Q
        qs = qs.filter(
            Q(title__icontains=search)
            | Q(Host_name__icontains=search)
            | Q(venue__icontains=search)
            | Q(description__icontains=search)
            | Q(Agenda__icontains=search)
        )

    date_filter = request.GET.get("date", "").strip()
    if date_filter:
        qs = qs.filter(scheduled_date=date_filter)

    results = []
    for m in qs:
        results.append({
            "meeting_id": str(m.Meeting_id),
            "title": m.display_title,
            "host_name": m.Host_name,
            "agenda": m.Agenda,
            "description": m.description,
            "meeting_mode": m.meeting_mode,
            "lifecycle_status": m.lifecycle_status,
            "status": m.Status,
            "venue": m.venue,
            "scheduled_date": m.scheduled_date,
            "scheduled_start_time": m.scheduled_start_time,
            "scheduled_end_time": m.scheduled_end_time,
            "expected_duration": m.expected_duration,
            "actual_start_time": m.actual_start_time.isoformat() if m.actual_start_time else None,
            "actual_end_time": m.actual_end_time.isoformat() if m.actual_end_time else None,
            "actual_duration_seconds": m.actual_duration_seconds,
            "created_at": m.Created_at.isoformat() if m.Created_at else None,
            "ai_enabled": m.ai_enabled,
            "has_summary": bool(m.Summary),
            "has_mom": bool(m.mom_data),
            "participants_count": m.participants.count(),
            "agenda_items_count": m.agenda_items.count(),
            "agenda_items": [
                {
                    "id": a.pk,
                    "title": a.title,
                    "presenter": a.presenter,
                    "expected_duration": a.expected_duration,
                    "status": a.status,
                    "order": a.order,
                }
                for a in m.agenda_items.all()
            ],
        })

    return Response({"success": True, "meetings": results, "count": len(results)})


@api_view(["POST"])
def StartMeeting(request, meeting_id):
    """Transition a scheduled meeting into in_progress and record actual_start_time."""
    if not meeting_id:
        return Response({"success": False, "message": "Meeting ID is required."}, status=400)

    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)
    except (Meeting.DoesNotExist, ValueError):
        return Response({"success": False, "message": "Meeting not found."}, status=404)

    if meeting.lifecycle_status != "in_progress":
        meeting.lifecycle_status = "in_progress"
        meeting.Status = True
        if not meeting.actual_start_time:
            meeting.actual_start_time = timezone.now()
        meeting.save(update_fields=["lifecycle_status", "Status", "actual_start_time"])

    return Response({
        "success": True,
        "meeting_id": str(meeting.Meeting_id),
        "lifecycle_status": meeting.lifecycle_status,
        "actual_start_time": meeting.actual_start_time.isoformat(),
        "message": "Meeting started successfully."
    })


@api_view(["POST"])
def CancelMeeting(request, meeting_id):
    """Mark a meeting as cancelled."""
    if not meeting_id:
        return Response({"success": False, "message": "Meeting ID is required."}, status=400)

    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)
    except (Meeting.DoesNotExist, ValueError):
        return Response({"success": False, "message": "Meeting not found."}, status=404)

    meeting.lifecycle_status = "cancelled"
    meeting.Status = False
    meeting.save(update_fields=["lifecycle_status", "Status"])

    return Response({
        "success": True,
        "meeting_id": str(meeting.Meeting_id),
        "lifecycle_status": meeting.lifecycle_status,
        "message": "Meeting cancelled successfully."
    })


@api_view(["PUT", "POST"])
def UpdateMeeting(request, meeting_id):
    """Update editable meeting fields and agenda items."""
    if not meeting_id:
        return Response({"success": False, "message": "Meeting ID is required."}, status=400)

    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)
    except (Meeting.DoesNotExist, ValueError):
        return Response({"success": False, "message": "Meeting not found."}, status=404)

    data = request.data
    update_fields = []

    if "title" in data:
        meeting.title = data["title"].strip()
        update_fields.append("title")
    if "description" in data:
        meeting.description = data["description"].strip()
        update_fields.append("description")
    if "venue" in data:
        meeting.venue = data["venue"].strip()
        update_fields.append("venue")
    if "scheduled_date" in data:
        meeting.scheduled_date = data["scheduled_date"].strip()
        update_fields.append("scheduled_date")
    if "scheduled_start_time" in data:
        meeting.scheduled_start_time = data["scheduled_start_time"].strip()
        update_fields.append("scheduled_start_time")
    if "scheduled_end_time" in data:
        meeting.scheduled_end_time = data["scheduled_end_time"].strip()
        update_fields.append("scheduled_end_time")
    if "expected_duration" in data:
        meeting.expected_duration = data["expected_duration"].strip()
        update_fields.append("expected_duration")

    if update_fields:
        meeting.save(update_fields=update_fields)

    if "agenda_items" in data and isinstance(data["agenda_items"], list):
        meeting.agenda_items.all().delete()
        for idx, item in enumerate(data["agenda_items"]):
            if isinstance(item, dict):
                MeetingAgendaItem.objects.create(
                    meeting=meeting,
                    title=item.get("title", f"Topic {idx + 1}").strip(),
                    description=item.get("description", "").strip(),
                    presenter=item.get("presenter", "").strip(),
                    expected_duration=item.get("expected_duration", "").strip(),
                    status=item.get("status", "Pending"),
                    order=idx,
                )
            elif isinstance(item, str) and item.strip():
                MeetingAgendaItem.objects.create(
                    meeting=meeting,
                    title=item.strip(),
                    order=idx,
                    status="Pending",
                )

    return Response({"success": True, "message": "Meeting updated successfully."})


@api_view(["PATCH", "POST"])
def UpdateAgendaItem(request, item_id):
    """Update status, notes, or presenter for an individual agenda item."""
    try:
        item = MeetingAgendaItem.objects.get(pk=item_id)
    except MeetingAgendaItem.DoesNotExist:
        return Response({"success": False, "message": "Agenda item not found."}, status=404)

    data = request.data
    update_fields = []
    if "status" in data:
        item.status = data["status"]
        update_fields.append("status")
    if "title" in data:
        item.title = data["title"]
        update_fields.append("title")
    if "description" in data:
        item.description = data["description"]
        update_fields.append("description")
    if "presenter" in data:
        item.presenter = data["presenter"]
        update_fields.append("presenter")
    if "expected_duration" in data:
        item.expected_duration = data["expected_duration"]
        update_fields.append("expected_duration")

    if update_fields:
        item.save(update_fields=update_fields)

    return Response({
        "success": True,
        "item": {
            "id": item.pk,
            "title": item.title,
            "description": item.description,
            "presenter": item.presenter,
            "expected_duration": item.expected_duration,
            "status": item.status,
            "order": item.order,
        }
    })


@api_view(["GET", "PUT", "PATCH", "POST"])
def MeetingMoMView(request, meeting_id):
    """
    Dedicated endpoint for Minutes of Meeting (MoM):
    - GET: Retrieves structured 10-section MoM.
    - PUT / PATCH: Saves user edits to MoM data and synchronizes Summary markdown.
    - POST: Regenerates MoM using Gemini 2.5 Flash from transcript and agenda.
    """
    if not meeting_id:
        return Response({"success": False, "message": "Meeting ID is required."}, status=400)

    try:
        meeting = Meeting.objects.get(Meeting_id=meeting_id)
    except (Meeting.DoesNotExist, ValueError):
        return Response({"success": False, "message": "Meeting not found."}, status=404)

    if request.method == "GET":
        mom_data = meeting.mom_data
        if not mom_data:
            mom_data = _build_default_mom_data(meeting)
            meeting.mom_data = mom_data
            meeting.save(update_fields=["mom_data"])

        return Response({
            "success": True,
            "meeting_id": str(meeting.Meeting_id),
            "mom_data": mom_data,
            "summary": meeting.Summary or "",
            "ai_enabled": meeting.ai_enabled,
            "meeting_mode": meeting.meeting_mode,
            "lifecycle_status": meeting.lifecycle_status,
            "title": meeting.display_title,
            "venue": meeting.venue,
            "scheduled_date": meeting.scheduled_date,
        })

    elif request.method in ["PUT", "PATCH"]:
        new_mom_data = request.data.get("mom_data")
        if not new_mom_data or not isinstance(new_mom_data, dict):
            return Response({"success": False, "message": "A valid mom_data object is required."}, status=400)

        meeting.mom_data = new_mom_data
        meeting.Summary = _format_mom_markdown(new_mom_data)
        meeting.save(update_fields=["mom_data", "Summary"])

        return Response({
            "success": True,
            "message": "Minutes of Meeting saved successfully.",
            "mom_data": meeting.mom_data,
            "summary": meeting.Summary,
        })

    elif request.method == "POST":
        # Force re-generation of MoM using Gemini
        transcript_entries = list(
            TranscriptEntry.objects.filter(meeting=meeting).order_by("timestamp", "pk")
        )
        transcript_text = _format_transcript_entries(transcript_entries)

        try:
            mom_data, summary_md = _generate_mom_data(meeting, transcript_text)
            meeting.mom_data = mom_data
            meeting.Summary = summary_md
            meeting.save(update_fields=["mom_data", "Summary"])

            return Response({
                "success": True,
                "message": "Minutes of Meeting regenerated successfully.",
                "mom_data": mom_data,
                "summary": summary_md,
            })
        except Exception as exc:
            logger.exception("[MOM_REGENERATE] Error: %s", exc)
            return Response({"success": False, "message": f"Regeneration failed: {str(exc)}"}, status=500)




