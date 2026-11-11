import { jsPDF } from 'jspdf';

/**
 * Sanitizes a meeting ID for safe filename usage.
 */
export function sanitizeFilename(meetingId) {
    if (!meetingId) return 'meeting_report.pdf';
    const clean = String(meetingId).replace(/[^a-zA-Z0-9_\-]/g, '');
    return `meeting_report_${clean || 'session'}.pdf`;
}

/**
 * Formats a Date/ISO string to Indian Standard Time (IST, UTC+05:30) with AM/PM.
 */
export function formatISTTime(dateOrIso) {
    if (!dateOrIso) return 'N/A';
    try {
        const d = new Date(dateOrIso);
        if (isNaN(d.getTime())) return String(dateOrIso);
        return new Intl.DateTimeFormat('en-IN', {
            timeZone: 'Asia/Kolkata',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: true,
        }).format(d) + ' IST';
    } catch {
        return String(dateOrIso);
    }
}

/**
 * Formats a Date/ISO string to IST Date string (e.g. "November 11, 2026").
 */
export function formatISTDate(dateOrIso) {
    if (!dateOrIso) return 'N/A';
    try {
        const d = new Date(dateOrIso);
        if (isNaN(d.getTime())) return String(dateOrIso);
        return new Intl.DateTimeFormat('en-IN', {
            timeZone: 'Asia/Kolkata',
            year: 'numeric',
            month: 'long',
            day: 'numeric',
        }).format(d);
    } catch {
        return String(dateOrIso);
    }
}

/**
 * Formats duration in seconds into human-readable hours, minutes, seconds.
 */
export function formatDuration(seconds) {
    const s = Math.max(0, Math.floor(Number(seconds) || 0));
    if (s <= 0) return 'N/A';
    const hrs = Math.floor(s / 3600);
    const mins = Math.floor((s % 3600) / 60);
    const secs = s % 60;
    const parts = [];
    if (hrs > 0) parts.push(`${hrs} hour${hrs !== 1 ? 's' : ''}`);
    if (mins > 0) parts.push(`${mins} minute${mins !== 1 ? 's' : ''}`);
    if (secs > 0 || parts.length === 0) parts.push(`${secs} second${secs !== 1 ? 's' : ''}`);
    return parts.join(' ');
}

/**
 * Strips raw markdown tokens (#, ##, **, *, `) from text so raw syntax never renders in PDF.
 */
function stripMarkdown(text) {
    if (!text) return '';
    return String(text)
        .replace(/^#{1,6}\s+/gm, '')
        .replace(/\*\*([^*]+)\*\*/g, '$1')
        .replace(/\*([^*]+)\*/g, '$1')
        .replace(/`([^`]+)`/g, '$1')
        .replace(/^\s*[-*+]\s+/gm, '• ')
        .trim();
}

/**
 * Generates and downloads an A4 PDF Meeting Report adhering to the 2-section MoM specification.
 */
export function generateMeetingPdfReport({
    meetingId,
    title = '',
    agenda = '',
    hostName = '',
    meetingMode = 'video',
    venue = '',
    scheduledDate = '',
    scheduledStartTime = '',
    scheduledEndTime = '',
    expectedDuration = '',
    actualStartTime = '',
    actualEndTime = '',
    actualDurationSeconds = 0,
    createdAt = '',
    summary = '',
    momData = null,
    participants = [],
    followUpMessages = [],
}) {
    const doc = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: 'a4',
    });

    const pageWidth = 210;
    const pageHeight = 297;
    const margin = 14;
    const contentWidth = pageWidth - margin * 2;
    const topLimit = 22;
    const bottomLimit = pageHeight - 18;

    let y = topLimit;

    // Helper: Page management
    const checkAddPage = (neededHeight) => {
        if (y + neededHeight > bottomLimit) {
            doc.addPage();
            y = topLimit;
            return true;
        }
        return false;
    };

    // Extract structured data from momData or parameters
    const momInfo = momData?.meeting_info || {};
    const momSummary = momData?.summary || {};

    const displayTitle = title || momInfo.title || (agenda ? `Meeting: ${agenda.slice(0, 40)}` : `Meeting ${String(meetingId).slice(0, 8)}`);
    const isRoom = meetingMode === 'room' || (momInfo.meeting_type && momInfo.meeting_type.toLowerCase().includes('room'));
    const modeLabel = isRoom ? 'In-Room Meeting' : 'Online Video Meeting';

    const organizer = hostName || momInfo.organizer || 'Organizer';
    const dateStr = scheduledDate || momInfo.date || (actualStartTime ? formatISTDate(actualStartTime) : (createdAt ? formatISTDate(createdAt) : formatISTDate(new Date())));

    // Calculate actual duration
    let durSecs = Number(actualDurationSeconds || momInfo.actual_duration_seconds || 0);
    if (durSecs <= 0 && actualStartTime && actualEndTime) {
        try {
            const startMs = new Date(actualStartTime).getTime();
            const endMs = new Date(actualEndTime).getTime();
            if (!isNaN(startMs) && !isNaN(endMs) && endMs >= startMs) {
                durSecs = Math.floor((endMs - startMs) / 1000);
            }
        } catch {
            durSecs = 0;
        }
    }
    const actualDurStr = durSecs > 0 ? formatDuration(durSecs) : (momInfo.actual_duration || 'N/A');

    const actStartStr = actualStartTime ? formatISTTime(actualStartTime) : (momInfo.actual_start_time || 'N/A');
    const actEndStr = actualEndTime ? formatISTTime(actualEndTime) : (momInfo.actual_end_time || 'N/A');

    const schedStartStr = scheduledStartTime || momInfo.scheduled_start_time || 'N/A';
    const schedEndStr = scheduledEndTime || momInfo.scheduled_end_time || 'N/A';
    const schedDurStr = expectedDuration || momInfo.scheduled_duration || 'N/A';
    const schedCombined = schedStartStr !== 'N/A' ? `${schedStartStr} - ${schedEndStr} (${schedDurStr})` : 'Not scheduled';

    const venueOrLink = venue || momInfo.venue || (isRoom ? 'Meeting Room' : `Online Link: /Meeting/${meetingId}`);
    const venueLabel = isRoom ? 'Venue' : 'Online Meeting Link';

    // Participants list
    const participantList = participants && participants.length > 0
        ? participants.map(p => (p.name && p.name !== p.email ? `${p.name} (${p.email})` : (p.email || p.name))).join(', ')
        : (momInfo.participants ? momInfo.participants.map(p => p.name || p.email || p).join(', ') : organizer);

    // Agenda text
    let agendaStr = agenda || 'None specified';
    if (momInfo.agenda && Array.isArray(momInfo.agenda) && momInfo.agenda.length > 0) {
        agendaStr = momInfo.agenda.map((a, i) => `${i + 1}. ${a.title || a}`).join('; ');
    }

    // ── 1. Document Header ──────────────────────────────────────────────
    doc.setFillColor(30, 41, 59); // Slate-800
    doc.rect(margin, y, contentWidth, 12, 'F');

    doc.setFont('helvetica', 'bold');
    doc.setFontSize(13);
    doc.setTextColor(255, 255, 255);
    doc.text('MEETSPACE MEETING REPORT', margin + 4, y + 8);

    doc.setFontSize(8);
    doc.setTextColor(203, 213, 225);
    doc.text('CONFIDENTIAL', margin + contentWidth - 4, y + 8, { align: 'right' });

    y += 16;

    // Title & Subtitle
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(15);
    doc.setTextColor(15, 23, 42);
    const titleLines = doc.splitTextToSize(displayTitle, contentWidth);
    doc.text(titleLines, margin, y);
    y += titleLines.length * 6 + 1;

    doc.setFont('helvetica', 'normal');
    doc.setFontSize(9);
    doc.setTextColor(100, 116, 139);
    doc.text(`${modeLabel} • Generated: ${formatISTTime(new Date())}`, margin, y);
    y += 7;

    // ── SECTION 1: MEETING INFORMATION ──────────────────────────────────
    checkAddPage(20);
    doc.setFillColor(241, 245, 249); // slate-100
    doc.rect(margin, y, contentWidth, 7, 'F');
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(10);
    doc.setTextColor(30, 41, 59);
    doc.text('SECTION 1: MEETING INFORMATION', margin + 3, y + 5);
    y += 10;

    const renderMetaRow = (label1, val1, label2, val2) => {
        const col1W = 28;
        const col2W = 60;
        const col3W = 28;
        const col4W = contentWidth - (col1W + col2W + col3W);

        doc.setFontSize(8.5);
        const wrapped1 = doc.splitTextToSize(String(val1 || 'N/A'), col2W - 2);
        const wrapped2 = label2 ? doc.splitTextToSize(String(val2 || 'N/A'), col4W - 2) : [];
        const maxLines = Math.max(wrapped1.length, wrapped2.length || 1);
        const rowH = Math.max(6, maxLines * 4.2 + 2);

        checkAddPage(rowH);

        doc.setFont('helvetica', 'bold');
        doc.setTextColor(71, 85, 105);
        doc.text(label1, margin + 2, y + 4);

        doc.setFont('helvetica', 'normal');
        doc.setTextColor(15, 23, 42);
        doc.text(wrapped1, margin + col1W, y + 4);

        if (label2) {
            doc.setFont('helvetica', 'bold');
            doc.setTextColor(71, 85, 105);
            doc.text(label2, margin + col1W + col2W + 2, y + 4);

            doc.setFont('helvetica', 'normal');
            doc.setTextColor(15, 23, 42);
            doc.text(wrapped2, margin + col1W + col2W + col3W, y + 4);
        }

        // Bottom border line
        doc.setDrawColor(241, 245, 249);
        doc.setLineWidth(0.2);
        doc.line(margin, y + rowH, margin + contentWidth, y + rowH);

        y += rowH;
    };

    renderMetaRow('Meeting Title:', displayTitle, 'Meeting ID:', String(meetingId || 'N/A').slice(0, 36));
    renderMetaRow('Meeting Type:', modeLabel, 'Date (IST):', dateStr);
    renderMetaRow('Organizer:', organizer, venueLabel + ':', venueOrLink);
    renderMetaRow('Attendees:', participantList);
    renderMetaRow('Meeting Agenda:', agendaStr);
    renderMetaRow('Scheduled (IST):', schedCombined);
    renderMetaRow('Actual (IST):', `${actStartStr} - ${actEndStr}`, 'Actual Duration:', actualDurStr);

    y += 6;

    // ── SECTION 2: MEETING SUMMARY ──────────────────────────────────────
    checkAddPage(20);
    doc.setFillColor(241, 245, 249);
    doc.rect(margin, y, contentWidth, 7, 'F');
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(10);
    doc.setTextColor(30, 41, 59);
    doc.text('SECTION 2: MEETING SUMMARY', margin + 3, y + 5);
    y += 11;

    // 1. Meeting Overview
    const overviewText = stripMarkdown(
        momSummary.meeting_overview || momData?.executive_summary || summary || 'Meeting completed and recorded successfully.'
    );
    checkAddPage(14);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(9.5);
    doc.setTextColor(15, 23, 42);
    doc.text('Meeting Overview', margin, y);
    y += 5;

    doc.setFont('helvetica', 'normal');
    doc.setFontSize(8.5);
    doc.setTextColor(51, 65, 85);
    const wrappedOverview = doc.splitTextToSize(overviewText, contentWidth);
    checkAddPage(wrappedOverview.length * 4.2 + 2);
    doc.text(wrappedOverview, margin, y);
    y += wrappedOverview.length * 4.2 + 4;

    // 2. Key Discussion Points
    const rawPoints = momSummary.discussion_points || momData?.discussion_points || [];
    if (rawPoints && rawPoints.length > 0) {
        checkAddPage(12);
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(9.5);
        doc.setTextColor(15, 23, 42);
        doc.text('Key Discussion Points', margin, y);
        y += 5;

        doc.setFont('helvetica', 'normal');
        doc.setFontSize(8.5);
        doc.setTextColor(51, 65, 85);

        for (const pt of rawPoints) {
            let ptText = '';
            if (typeof pt === 'object' && pt !== null) {
                const topic = pt.topic ? `[${stripMarkdown(pt.topic)}] ` : '';
                ptText = topic + stripMarkdown(pt.details || pt.text || '');
            } else {
                ptText = stripMarkdown(String(pt));
            }
            if (!ptText.trim()) continue;

            const wrappedPt = doc.splitTextToSize(`•  ${ptText}`, contentWidth - 4);
            checkAddPage(wrappedPt.length * 4.2 + 1);
            doc.text(wrappedPt, margin + 2, y);
            y += wrappedPt.length * 4.2 + 1.5;
        }
        y += 3;
    }

    // 3. Decisions Made (omitted if empty)
    const rawDecisions = momSummary.decisions || momData?.decisions_made || [];
    const validDecisions = Array.isArray(rawDecisions)
        ? rawDecisions.filter(d => String(d).trim() && !['none', 'none agreed', 'n/a', 'no decisions made'].includes(String(d).toLowerCase().trim()))
        : [];

    if (validDecisions.length > 0) {
        checkAddPage(12);
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(9.5);
        doc.setTextColor(15, 23, 42);
        doc.text('Decisions Made', margin, y);
        y += 5;

        doc.setFont('helvetica', 'normal');
        doc.setFontSize(8.5);
        doc.setTextColor(51, 65, 85);

        validDecisions.forEach((dec, idx) => {
            const decText = stripMarkdown(String(dec));
            const wrappedDec = doc.splitTextToSize(`${idx + 1}.  ${decText}`, contentWidth - 4);
            checkAddPage(wrappedDec.length * 4.2 + 1);
            doc.text(wrappedDec, margin + 2, y);
            y += wrappedDec.length * 4.2 + 1.5;
        });
        y += 3;
    }

    // 4. Action Items (omitted if empty)
    const rawActions = momSummary.action_items || momData?.action_items || [];
    const validActions = Array.isArray(rawActions)
        ? rawActions.filter(a => {
            if (typeof a === 'object' && a !== null) {
                const desc = a.task || a.description || '';
                return desc.trim().length > 0;
            }
            return String(a).trim().length > 0;
        })
        : [];

    if (validActions.length > 0) {
        checkAddPage(16);
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(9.5);
        doc.setTextColor(15, 23, 42);
        doc.text('Action Items', margin, y);
        y += 5;

        // Table Header
        const colWTask = 100;
        const colWOwner = 46;
        const colWDeadline = contentWidth - colWTask - colWOwner;

        doc.setFillColor(241, 245, 249);
        doc.rect(margin, y, contentWidth, 6, 'F');
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(8);
        doc.setTextColor(51, 65, 85);
        doc.text('Task Description', margin + 2, y + 4.2);
        doc.text('Assigned Owner', margin + colWTask + 2, y + 4.2);
        doc.text('Deadline', margin + colWTask + colWOwner + 2, y + 4.2);
        y += 6;

        // Table Rows
        doc.setFont('helvetica', 'normal');
        doc.setTextColor(15, 23, 42);

        validActions.forEach((act) => {
            let taskText = '';
            let ownerText = 'Unassigned';
            let deadlineText = 'Not specified';

            if (typeof act === 'object' && act !== null) {
                taskText = stripMarkdown(act.task || act.description || '');
                ownerText = stripMarkdown(act.owner || 'Unassigned');
                deadlineText = stripMarkdown(act.deadline || 'Not specified');
            } else {
                taskText = stripMarkdown(String(act));
            }

            const wrappedTask = doc.splitTextToSize(taskText, colWTask - 4);
            const wrappedOwner = doc.splitTextToSize(ownerText, colWOwner - 4);
            const wrappedDeadline = doc.splitTextToSize(deadlineText, colWDeadline - 4);

            const rowLines = Math.max(wrappedTask.length, wrappedOwner.length, wrappedDeadline.length);
            const rowH = Math.max(5.5, rowLines * 4 + 2);

            checkAddPage(rowH);

            doc.text(wrappedTask, margin + 2, y + 3.8);
            doc.text(wrappedOwner, margin + colWTask + 2, y + 3.8);
            doc.text(wrappedDeadline, margin + colWTask + colWOwner + 2, y + 3.8);

            doc.setDrawColor(226, 232, 240);
            doc.setLineWidth(0.2);
            doc.line(margin, y + rowH, margin + contentWidth, y + rowH);

            y += rowH;
        });
        y += 4;
    }

    // 5. Pending Issues (omitted if empty)
    const rawPending = momSummary.pending_issues || momData?.unresolved_questions || [];
    const validPending = Array.isArray(rawPending)
        ? rawPending.filter(p => {
            const clean = String(p).trim().toLowerCase();
            return clean && !['none', 'none identified', 'none identified during the meeting.', 'n/a', 'not discussed'].includes(clean);
        })
        : [];

    if (validPending.length > 0) {
        checkAddPage(12);
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(9.5);
        doc.setTextColor(15, 23, 42);
        doc.text('Pending Issues', margin, y);
        y += 5;

        doc.setFont('helvetica', 'normal');
        doc.setFontSize(8.5);
        doc.setTextColor(51, 65, 85);

        validPending.forEach((issue) => {
            const issueText = stripMarkdown(String(issue));
            const wrappedIssue = doc.splitTextToSize(`•  ${issueText}`, contentWidth - 4);
            checkAddPage(wrappedIssue.length * 4.2 + 1);
            doc.text(wrappedIssue, margin + 2, y);
            y += wrappedIssue.length * 4.2 + 1.5;
        });
        y += 3;
    }

    // 6. Conclusion
    const rawConclusion = momSummary.conclusion || momData?.conclusion;
    if (rawConclusion && rawConclusion.trim()) {
        const conclusionText = stripMarkdown(rawConclusion);
        checkAddPage(12);
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(9.5);
        doc.setTextColor(15, 23, 42);
        doc.text('Conclusion', margin, y);
        y += 5;

        doc.setFont('helvetica', 'normal');
        doc.setFontSize(8.5);
        doc.setTextColor(51, 65, 85);
        const wrappedConclusion = doc.splitTextToSize(conclusionText, contentWidth);
        checkAddPage(wrappedConclusion.length * 4.2 + 2);
        doc.text(wrappedConclusion, margin, y);
        y += wrappedConclusion.length * 4.2 + 4;
    }

    // ── Optional: Follow-Up Questions (if available and requested) ──────
    if (followUpMessages && followUpMessages.length > 0) {
        checkAddPage(16);
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(9.5);
        doc.setTextColor(15, 23, 42);
        doc.text('Follow-Up Q&A History', margin, y);
        y += 5;

        followUpMessages.forEach((msg) => {
            const isUser = msg.message_by === 'user';
            const sender = isUser ? 'User' : 'MeetSpace AI';
            const cleanContent = stripMarkdown(msg.content || '');
            const wrapped = doc.splitTextToSize(`${sender}: ${cleanContent}`, contentWidth - 6);
            const cardH = wrapped.length * 4 + 3;

            checkAddPage(cardH);

            doc.setFillColor(isUser ? 248 : 240, isUser ? 250 : 249, isUser ? 252 : 255);
            doc.roundedRect(margin, y, contentWidth, cardH, 1, 1, 'F');

            doc.setFont('helvetica', isUser ? 'normal' : 'normal');
            doc.setFontSize(8);
            doc.setTextColor(30, 41, 59);
            doc.text(wrapped, margin + 3, y + 3.2);

            y += cardH + 2;
        });
    }

    // ── Running Header & Footer on All Pages ────────────────────────────
    const totalPages = doc.getNumberOfPages();
    for (let i = 1; i <= totalPages; i++) {
        doc.setPage(i);

        // Header on pages > 1
        if (i > 1) {
            doc.setFont('helvetica', 'normal');
            doc.setFontSize(7.5);
            doc.setTextColor(148, 163, 184);
            doc.text('MeetSpace Meeting Report • Confidential', margin, 10);
            doc.text(displayTitle.slice(0, 45), margin + contentWidth, 10, { align: 'right' });

            doc.setDrawColor(226, 232, 240);
            doc.setLineWidth(0.2);
            doc.line(margin, 12, margin + contentWidth, 12);
        }

        // Running Footer
        doc.setDrawColor(226, 232, 240);
        doc.setLineWidth(0.2);
        doc.line(margin, pageHeight - 11, margin + contentWidth, pageHeight - 11);

        doc.setFont('helvetica', 'normal');
        doc.setFontSize(7.5);
        doc.setTextColor(148, 163, 184);
        doc.text('MeetSpace • Confidential Meeting Report', margin, pageHeight - 7);
        doc.text(`Page ${i} of ${totalPages}`, margin + contentWidth, pageHeight - 7, { align: 'right' });
    }

    const filename = sanitizeFilename(meetingId);
    doc.save(filename);
    return filename;
}
