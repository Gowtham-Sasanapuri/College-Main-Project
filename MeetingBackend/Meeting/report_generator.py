"""
Meeting Report PDF Generator using ReportLab.
Generates multi-page, publication-quality meeting summary & AI conversation reports.
Used by backend email delivery service and report API.
"""

import io
import re
import html
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)
from reportlab.pdfgen import canvas


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically calculate and render the total page count
    along with running header and footer.
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

        # Running footer
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(40, 36, page_w - 40, 36)

        self.drawString(40, 24, "MeetSpace • Confidential Meeting Report")
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(page_w - 40, 24, page_str)

        self.restoreState()


def _sanitize_pdf_text(text):
    """Escapes XML entities and strips unprintable characters for ReportLab Paragraph."""
    if not text:
        return ""
    # Strip null bytes or invalid control chars
    clean = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", str(text))
    return html.escape(clean)


def sanitize_filename(meeting_id):
    """Generates a sanitized filename for the meeting report PDF."""
    if not meeting_id:
        return "meeting_report.pdf"
    # Keep alphanumeric and dashes/underscores
    clean_id = re.sub(r"[^a-zA-Z0-9_\-]", "", str(meeting_id))
    return f"meeting_report_{clean_id or 'session'}.pdf"


def generate_meeting_pdf_bytes(meeting, participants=None, follow_up_messages=None):
    """
    Builds and returns the PDF file bytes for the given meeting.
    """
    buffer = io.BytesIO()

    # Document geometry: Letter size, 40pt (0.55in) margins
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=48,
    )

    styles = getSampleStyleSheet()

    # Custom typography styles
    primary_color = colors.HexColor("#1E293B")
    accent_color = colors.HexColor("#4F46E5")
    muted_color = colors.HexColor("#64748B")
    user_bubble_color = colors.HexColor("#F1F5F9")
    ai_bubble_color = colors.HexColor("#EEF2FF")

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=accent_color,
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=muted_color,
        spaceAfter=14,
    )

    section_heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=primary_color,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True,
    )

    meta_label_style = ParagraphStyle(
        "MetaLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155"),
    )

    meta_value_style = ParagraphStyle(
        "MetaValue",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#0F172A"),
    )

    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#1E293B"),
        spaceAfter=6,
    )

    msg_sender_style = ParagraphStyle(
        "MsgSender",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=accent_color,
    )

    msg_time_style = ParagraphStyle(
        "MsgTime",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=muted_color,
        alignment=2,  # Right-aligned
    )

    msg_content_style = ParagraphStyle(
        "MsgContent",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=3,
    )

    story = []

    # 1. Header Banner
    story.append(Paragraph("MEETSPACE MEETING REPORT", title_style))
    created_str = (
        meeting.Created_at.strftime("%B %d, %Y at %H:%M UTC")
        if meeting.Created_at
        else datetime.utcnow().strftime("%B %d, %Y")
    )
    story.append(Paragraph(f"Generated on {datetime.utcnow().strftime('%B %d, %Y • %H:%M UTC')}", subtitle_style))

    # 2. Metadata Section (Table)
    mode_display = "Room Meeting (In-Person Diarized)" if meeting.meeting_mode == "room" else "Video Calling"
    meeting_id_str = str(meeting.Meeting_id)

    # Participant list formatting
    if participants is None:
        participants = list(meeting.participants.all())

    participant_strs = []
    for p in participants:
        if p.name and p.name != p.email:
            participant_strs.append(f"{_sanitize_pdf_text(p.name)} &lt;{_sanitize_pdf_text(p.email)}&gt;")
        else:
            participant_strs.append(_sanitize_pdf_text(p.email))
    
    participants_formatted = ", ".join(participant_strs) if participant_strs else "None recorded"

    meta_table_data = [
        [
            Paragraph("Meeting ID:", meta_label_style),
            Paragraph(_sanitize_pdf_text(meeting_id_str), meta_value_style),
            Paragraph("Mode:", meta_label_style),
            Paragraph(mode_display, meta_value_style),
        ],
        [
            Paragraph("Date & Time:", meta_label_style),
            Paragraph(created_str, meta_value_style),
            Paragraph("Host / Device:", meta_label_style),
            Paragraph(_sanitize_pdf_text(meeting.Host_name or "Organizer"), meta_value_style),
        ],
        [
            Paragraph("Agenda:", meta_label_style),
            Paragraph(_sanitize_pdf_text(meeting.Agenda or "No specific agenda provided"), meta_value_style),
            Paragraph("AI Enabled:", meta_label_style),
            Paragraph("Yes" if meeting.ai_enabled else "No", meta_value_style),
        ],
        [
            Paragraph("Recipients:", meta_label_style),
            Paragraph(participants_formatted, meta_value_style),
            Paragraph("", meta_label_style),
            Paragraph("", meta_value_style),
        ],
    ]

    col_widths = [75, 190, 75, 192]
    meta_table = Table(meta_table_data, colWidths=col_widths)
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
        ("SPAN", (1, 3), (3, 3)),  # Span participants across columns
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 14))

    # 3. Meeting Summary & Structured Points
    story.append(Paragraph("1. Generated Meeting Summary", section_heading_style))

    summary_text = (meeting.Summary or "").strip()
    if summary_text:
        # Render line by line, preserving structured headings and paragraphs
        paragraphs = summary_text.split("\n\n")
        for para in paragraphs:
            para_clean = para.strip()
            if not para_clean:
                continue
            
            # Check if this paragraph is a major numbered heading (e.g., "1. Meeting Overview")
            if re.match(r"^\d+\.\s+[A-Za-z]", para_clean):
                sub_heading_style = ParagraphStyle(
                    "SubHeading",
                    parent=styles["Normal"],
                    fontName="Helvetica-Bold",
                    fontSize=10.5,
                    leading=14,
                    textColor=colors.HexColor("#334155"),
                    spaceBefore=8,
                    spaceAfter=4,
                    keepWithNext=True,
                )
                story.append(Paragraph(_sanitize_pdf_text(para_clean), sub_heading_style))
            else:
                # Format bullet items or standard body text
                lines = para_clean.split("\n")
                formatted_lines = []
                for line in lines:
                    line_clean = line.strip()
                    if line_clean.startswith("- ") or line_clean.startswith("* "):
                        formatted_lines.append(f"• {_sanitize_pdf_text(line_clean[2:])}")
                    else:
                        formatted_lines.append(_sanitize_pdf_text(line_clean))
                story.append(Paragraph("<br/>".join(formatted_lines), body_style))
    else:
        story.append(Paragraph("<i>No meeting summary was generated for this session.</i>", body_style))

    story.append(Spacer(1, 14))

    # 4. AI Follow-Up Conversation
    story.append(Paragraph("2. Complete AI Follow-Up Conversation", section_heading_style))

    if follow_up_messages is None:
        follow_up_messages = list(meeting.follow_up_messages.order_by("timestamp", "pk"))

    if follow_up_messages:
        for idx, msg in enumerate(follow_up_messages):
            is_user = msg.message_by == "user"
            sender_name = "User / Participant" if is_user else "✦ AI Assistant"
            time_display = (
                msg.timestamp.strftime("%H:%M:%S UTC")
                if msg.timestamp
                else ""
            )

            card_bg = user_bubble_color if is_user else ai_bubble_color
            border_color = colors.HexColor("#CBD5E1") if is_user else colors.HexColor("#C7D2FE")

            content_clean = _sanitize_pdf_text(msg.content).replace("\n", "<br/>")

            msg_table_data = [
                [
                    Paragraph(f"<b>{sender_name}</b>", msg_sender_style),
                    Paragraph(time_display, msg_time_style),
                ],
                [
                    Paragraph(content_clean, msg_content_style),
                    Paragraph("", msg_content_style),
                ],
            ]

            msg_table = Table(msg_table_data, colWidths=[380, 152])
            msg_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), card_bg),
                ("BOX", (0, 0), (-1, -1), 0.5, border_color),
                ("SPAN", (0, 1), (1, 1)),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))

            story.append(KeepTogether([msg_table, Spacer(1, 6)]))
    else:
        story.append(
            Paragraph("<i>No follow-up questions were asked for this meeting.</i>", body_style)
        )

    # Build the PDF using NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()
