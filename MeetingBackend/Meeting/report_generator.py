"""
Meeting Report PDF Generator using ReportLab.
Generates publication-quality, A4-formatted meeting summary and MoM reports.
Used by backend email delivery service and report download API.
"""

import io
import re
import html
import zoneinfo
from datetime import datetime
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    HRFlowable,
)
from reportlab.pdfgen import canvas

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically calculate and render total page count,
    running headers, and running footers with exact coordinates.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages):
        self.saveState()
        page_w, page_h = self._pagesize

        # Running header (for pages after page 1)
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(colors.HexColor("#475569"))
            self.drawString(36, page_h - 26, "MEETSPACE MEETING REPORT")
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#94A3B8"))
            self.drawRightString(page_w - 36, page_h - 26, "Confidential")
            self.setStrokeColor(colors.HexColor("#E2E8F0"))
            self.setLineWidth(0.5)
            self.line(36, page_h - 30, page_w - 36, page_h - 30)

        # Running footer (on all pages)
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(36, 32, page_w - 36, 32)

        self.drawString(36, 20, "MeetSpace • Confidential")
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(page_w - 36, 20, page_str)

        self.restoreState()


def _to_ist(dt):
    """Converts a datetime object (naive or aware) to Asia/Kolkata timezone (IST)."""
    if not dt:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.utc)
    return dt.astimezone(IST)


def _format_time_ist(dt):
    """Formats datetime into 'hh:mm:ss AM/PM IST'."""
    dt_ist = _to_ist(dt)
    if not dt_ist:
        return "N/A"
    return dt_ist.strftime("%I:%M:%S %p IST").lstrip("0")


def _format_date_ist(dt):
    """Formats datetime into 'Month DD, YYYY' in IST."""
    dt_ist = _to_ist(dt)
    if not dt_ist:
        return "N/A"
    return dt_ist.strftime("%B %d, %Y")


def _format_duration_seconds(seconds):
    """Calculates human-readable duration from seconds: 'X minutes Y seconds'."""
    if seconds is None or seconds < 0:
        return "0 seconds"
    hours = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    parts = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
    if mins > 0:
        parts.append(f"{mins} minute{'s' if mins > 1 else ''}")
    if secs > 0 or not parts:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")
    return " ".join(parts)


def _sanitize_pdf_text(text):
    """Escapes XML entities and strips unprintable characters for ReportLab Paragraph."""
    if not text:
        return ""
    clean = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", str(text))
    return html.escape(clean)


def _format_inline_markdown(text):
    """
    Sanitizes text and safely converts markdown bold (**text**) and italic (*text*)
    into ReportLab XML markup (<b>text</b>, <i>text</i>).
    Removes raw markdown characters (#, *, |, etc.) so they never appear on the PDF.
    """
    if not text:
        return ""
    text = str(text).strip()
    
    # Strip any markdown table lines if present
    if text.startswith("|") and text.endswith("|"):
        cells = [c.strip() for c in text.strip("|").split("|")]
        # Skip divider rows like |---|---|
        if any(set(c).issubset({"-", ":", " "}) for c in cells if c):
            return ""
        text = " • ".join(cells)

    # Strip heading markers
    text = re.sub(r"^#+\s*", "", text)
    # Strip bullet markers
    text = re.sub(r"^[-*•]\s*", "", text)

    # Escape HTML entities
    clean = _sanitize_pdf_text(text)

    # Convert markdown bold and italic
    clean = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", clean)
    clean = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", clean)
    clean = clean.replace("\n", "<br/>")
    return clean


def sanitize_filename(meeting_id):
    """Generates a sanitized filename for the meeting report PDF."""
    if not meeting_id:
        return "meeting_report.pdf"
    clean_id = re.sub(r"[^a-zA-Z0-9_\-]", "", str(meeting_id))
    return f"meeting_report_{clean_id or 'session'}.pdf"


def generate_meeting_pdf_bytes(meeting, participants=None, follow_up_messages=None):
    """
    Builds and returns the PDF file bytes for the given meeting following the strict
    two-section structure on A4 paper:
      SECTION 1: MEETING INFORMATION
      SECTION 2: MEETING SUMMARY
    """
    buffer = io.BytesIO()

    # Document geometry: A4 (595.28 x 841.89 pt), 36pt (0.5 in) margins -> 523.28pt content width
    content_width = 523.28
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=40,
        bottomMargin=42,
    )

    styles = getSampleStyleSheet()

    # Color palette
    primary_color = colors.HexColor("#0F172A")    # Slate 900
    brand_color = colors.HexColor("#4F46E5")      # Indigo 600
    muted_color = colors.HexColor("#64748B")      # Slate 500
    border_color = colors.HexColor("#CBD5E1")     # Slate 300
    bg_surface = colors.HexColor("#F8FAFC")       # Slate 50

    # Custom Typography Styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=primary_color,
        spaceAfter=3,
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=muted_color,
        spaceAfter=8,
    )

    section_heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=brand_color,
        spaceBefore=10,
        spaceAfter=8,
        keepWithNext=True,
    )

    subsection_title_style = ParagraphStyle(
        "SubsectionTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=13,
        textColor=primary_color,
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True,
    )

    meta_label_style = ParagraphStyle(
        "MetaLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#334155"),
    )

    meta_value_style = ParagraphStyle(
        "MetaValue",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#0F172A"),
    )

    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13.5,
        textColor=colors.HexColor("#1E293B"),
        spaceAfter=4,
    )

    bullet_style = ParagraphStyle(
        "ReportBullet",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1E293B"),
        leftIndent=14,
        firstLineIndent=-10,
        spaceAfter=3,
    )

    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#1E293B"),
    )

    table_cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#334155"),
    )

    story = []

    # ─────────────────────────────────────────────────────────────────
    # 1. Header Banner
    # ─────────────────────────────────────────────────────────────────
    story.append(Paragraph("MEETSPACE MEETING REPORT", title_style))

    gen_dt = timezone.now()
    gen_str = _to_ist(gen_dt).strftime("%B %d, %Y • %I:%M:%S %p IST")
    story.append(Paragraph(f"Generated on {gen_str} • Confidential", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=0.75, color=border_color, spaceBefore=0, spaceAfter=8))

    # ─────────────────────────────────────────────────────────────────
    # 2. SECTION 1: MEETING INFORMATION
    # ─────────────────────────────────────────────────────────────────
    story.append(Paragraph("SECTION 1: MEETING INFORMATION", section_heading_style))

    meeting_id_str = str(meeting.Meeting_id)
    is_video = (meeting.meeting_mode == "video")
    mode_display = "Online Video Meeting (WebRTC)" if is_video else "In-Room Meeting (Acoustic Diarization)"
    title_display = getattr(meeting, "title", None) or meeting.display_title if hasattr(meeting, "display_title") else f"Meeting {meeting_id_str[:8]}"

    # Date
    date_display = _format_date_ist(meeting.actual_start_time or meeting.Created_at)
    if meeting.scheduled_date and meeting.scheduled_date != "N/A":
        date_display = f"{meeting.scheduled_date} (IST)"

    organizer_display = meeting.Host_name or "Organizer"

    # Participants
    if participants is None:
        participants = list(meeting.participants.all())
    p_strs = []
    for p in participants:
        if p.name and p.name != p.email:
            p_strs.append(f"{_sanitize_pdf_text(p.name)} &lt;{_sanitize_pdf_text(p.email)}&gt;")
        else:
            p_strs.append(_sanitize_pdf_text(p.email))
    participants_formatted = ", ".join(p_strs) if p_strs else "None recorded"

    # Venue / Online Meeting Link
    if is_video:
        venue_display = getattr(meeting, "venue", "") or f"Online Room: /Meeting/{meeting_id_str}"
    else:
        venue_display = getattr(meeting, "venue", "") or "In-Person Conference Room"

    # Scheduled timings
    sched_start_display = f"{meeting.scheduled_start_time} IST" if getattr(meeting, "scheduled_start_time", None) else "N/A"
    sched_end_display = f"{meeting.scheduled_end_time} IST" if getattr(meeting, "scheduled_end_time", None) else "N/A"

    # Actual timings (strictly in IST)
    actual_start_display = _format_time_ist(meeting.actual_start_time) if meeting.actual_start_time else "N/A"
    actual_end_display = _format_time_ist(meeting.actual_end_time) if meeting.actual_end_time else "N/A"

    # Actual duration (calculated in seconds)
    if meeting.actual_start_time and meeting.actual_end_time:
        dur_seconds = max(0, int((meeting.actual_end_time - meeting.actual_start_time).total_seconds()))
    elif meeting.actual_duration_seconds and meeting.actual_duration_seconds > 0:
        dur_seconds = meeting.actual_duration_seconds
    elif meeting.Created_at and meeting.actual_end_time:
        dur_seconds = max(0, int((meeting.actual_end_time - meeting.Created_at).total_seconds()))
    else:
        dur_seconds = 0
    actual_duration_display = _format_duration_seconds(dur_seconds)

    # 4-column structured metadata table
    col_w = [115, 146, 115, 147]  # total = 523pt
    meta_table_rows = [
        [
            Paragraph("Meeting Title:", meta_label_style),
            Paragraph(_sanitize_pdf_text(title_display), meta_value_style),
            Paragraph("Meeting ID:", meta_label_style),
            Paragraph(_sanitize_pdf_text(meeting_id_str), meta_value_style),
        ],
        [
            Paragraph("Meeting Type:", meta_label_style),
            Paragraph(mode_display, meta_value_style),
            Paragraph("Date:", meta_label_style),
            Paragraph(date_display, meta_value_style),
        ],
        [
            Paragraph("Organizer:", meta_label_style),
            Paragraph(_sanitize_pdf_text(organizer_display), meta_value_style),
            Paragraph("Venue / Link:", meta_label_style),
            Paragraph(_sanitize_pdf_text(venue_display), meta_value_style),
        ],
        [
            Paragraph("Scheduled Start:", meta_label_style),
            Paragraph(sched_start_display, meta_value_style),
            Paragraph("Scheduled End:", meta_label_style),
            Paragraph(sched_end_display, meta_value_style),
        ],
        [
            Paragraph("Actual Start:", meta_label_style),
            Paragraph(actual_start_display, meta_value_style),
            Paragraph("Actual End:", meta_label_style),
            Paragraph(actual_end_display, meta_value_style),
        ],
        [
            Paragraph("Actual Duration:", meta_label_style),
            Paragraph(actual_duration_display, meta_value_style),
            Paragraph("Participants:", meta_label_style),
            Paragraph(participants_formatted, meta_value_style),
        ],
    ]

    # Agenda row if present
    agenda_str = getattr(meeting, "Agenda", "") or ""
    if agenda_str.strip():
        meta_table_rows.append([
            Paragraph("Agenda:", meta_label_style),
            Paragraph(_sanitize_pdf_text(agenda_str.strip()), meta_value_style),
            Paragraph("", meta_label_style),
            Paragraph("", meta_value_style),
        ])

    meta_table = Table(meta_table_rows, colWidths=col_w)
    meta_table_style = [
        ("BACKGROUND", (0, 0), (-1, -1), bg_surface),
        ("BOX", (0, 0), (-1, -1), 0.5, border_color),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    if agenda_str.strip():
        meta_table_style.append(("SPAN", (1, len(meta_table_rows) - 1), (3, len(meta_table_rows) - 1)))
    meta_table.setStyle(TableStyle(meta_table_style))

    story.append(meta_table)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.75, color=border_color, spaceBefore=0, spaceAfter=8))

    # ─────────────────────────────────────────────────────────────────
    # 3. SECTION 2: MEETING SUMMARY
    # ─────────────────────────────────────────────────────────────────
    story.append(Paragraph("SECTION 2: MEETING SUMMARY", section_heading_style))

    # Parse structured summary from mom_data or fallback from Summary
    mom_data = getattr(meeting, "mom_data", None) or {}
    summary_data = mom_data.get("summary") if isinstance(mom_data.get("summary"), dict) else mom_data

    # Extract individual fields safely
    meeting_overview = ""
    discussion_points = []
    decisions = []
    action_items = []
    pending_issues = []
    conclusion = ""

    if isinstance(summary_data, dict):
        meeting_overview = summary_data.get("meeting_overview") or summary_data.get("executive_summary") or ""
        discussion_points = summary_data.get("discussion_points") or []
        decisions = summary_data.get("decisions") or summary_data.get("decisions_made") or []
        action_items = summary_data.get("action_items") or []
        pending_issues = summary_data.get("pending_issues") or summary_data.get("unresolved_questions") or []
        conclusion = summary_data.get("conclusion") or ""

    # Fallback to parsing meeting.Summary text if structured fields are missing
    raw_summary = (getattr(meeting, "Summary", "") or "").strip()
    if not meeting_overview and raw_summary:
        meeting_overview = raw_summary

    has_any_content = bool(meeting_overview or discussion_points or decisions or action_items or pending_issues or conclusion)

    if not has_any_content:
        story.append(Paragraph("<i>No meeting summary was recorded for this session.</i>", body_style))
    else:
        # 1. Meeting Overview
        if meeting_overview and meeting_overview.strip():
            story.append(Paragraph("Meeting Overview", subsection_title_style))
            # Clean overview paragraphs
            for p in meeting_overview.split("\n\n"):
                p_clean = p.strip()
                if not p_clean:
                    continue
                # Skip any leftover markdown headers
                if p_clean.startswith("#"):
                    continue
                story.append(Paragraph(_format_inline_markdown(p_clean), body_style))
            story.append(Spacer(1, 4))

        # 2. Key Discussion Points (only if meaningful points exist)
        valid_points = []
        if isinstance(discussion_points, list):
            for dp in discussion_points:
                if isinstance(dp, dict) and (dp.get("topic") or dp.get("details")):
                    valid_points.append(dp)
                elif isinstance(dp, str) and dp.strip() and "none identified" not in dp.lower():
                    valid_points.append({"topic": "", "details": dp.strip()})

        if valid_points:
            story.append(Paragraph("Key Discussion Points", subsection_title_style))
            for idx, pt in enumerate(valid_points, 1):
                topic = pt.get("topic", "").strip()
                details = pt.get("details", "").strip()
                if topic:
                    heading_text = f"<b>{idx}. {_sanitize_pdf_text(topic)}</b>"
                    story.append(Paragraph(heading_text, body_style))
                if details:
                    detail_text = _format_inline_markdown(details)
                    story.append(Paragraph(detail_text, bullet_style if topic else body_style))
            story.append(Spacer(1, 4))

        # 3. Decisions Made (only if confirmed decisions exist)
        valid_decisions = []
        if isinstance(decisions, list):
            for d in decisions:
                d_str = str(d).strip()
                if d_str and "no explicit decisions" not in d_str.lower() and "none" not in d_str.lower():
                    valid_decisions.append(d_str)

        if valid_decisions:
            story.append(Paragraph("Decisions Made", subsection_title_style))
            for idx, dec in enumerate(valid_decisions, 1):
                clean_dec = _format_inline_markdown(dec)
                story.append(Paragraph(f"<b>{idx}.</b> {clean_dec}", bullet_style))
            story.append(Spacer(1, 4))

        # 4. Action Items (formatted as a clean A4 table, only if present)
        valid_actions = []
        if isinstance(action_items, list):
            for act in action_items:
                if isinstance(act, dict):
                    task = act.get("task") or act.get("description", "")
                    if task and "no action items" not in task.lower():
                        valid_actions.append({
                            "task": task.strip(),
                            "owner": act.get("owner", "").strip() or "Unassigned",
                            "deadline": act.get("deadline", "").strip() or "TBD",
                        })
                elif isinstance(act, str) and act.strip() and "no action items" not in act.lower():
                    valid_actions.append({"task": act.strip(), "owner": "Unassigned", "deadline": "TBD"})

        if valid_actions:
            story.append(Paragraph("Action Items", subsection_title_style))
            action_table_data = [
                [
                    Paragraph("Task / Responsibility", table_header_style),
                    Paragraph("Assigned Owner", table_header_style),
                    Paragraph("Deadline", table_header_style),
                ]
            ]
            for item in valid_actions:
                action_table_data.append([
                    Paragraph(_format_inline_markdown(item["task"]), table_cell_style),
                    Paragraph(_sanitize_pdf_text(item["owner"]), table_cell_style),
                    Paragraph(_sanitize_pdf_text(item["deadline"]), table_cell_style),
                ])

            action_table = Table(action_table_data, colWidths=[283.28, 130, 110])
            action_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 0.5, border_color),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(action_table)
            story.append(Spacer(1, 6))

        # 5. Pending Issues (only if relevant unresolved issues exist)
        valid_pending = []
        if isinstance(pending_issues, list):
            for pi in pending_issues:
                pi_str = str(pi).strip()
                if pi_str and "none identified" not in pi_str.lower() and "not discussed" not in pi_str.lower():
                    valid_pending.append(pi_str)

        if valid_pending:
            story.append(Paragraph("Pending Issues", subsection_title_style))
            for issue in valid_pending:
                story.append(Paragraph(f"• {_format_inline_markdown(issue)}", bullet_style))
            story.append(Spacer(1, 4))

        # 6. Conclusion
        if conclusion and conclusion.strip():
            story.append(Paragraph("Conclusion", subsection_title_style))
            story.append(Paragraph(_format_inline_markdown(conclusion.strip()), body_style))

    # Build the PDF using NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer.getvalue()
