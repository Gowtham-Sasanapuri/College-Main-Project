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
 * Generates and downloads a multi-page PDF meeting report using jsPDF.
 *
 * @param {Object} reportData
 * @param {string} reportData.meetingId
 * @param {string} [reportData.agenda]
 * @param {string} [reportData.hostName]
 * @param {string} [reportData.meetingMode] - 'video' | 'room'
 * @param {string} [reportData.createdAt]
 * @param {string} [reportData.summary]
 * @param {Array}  [reportData.followUpMessages]
 * @param {Array}  [reportData.participants]
 */
export function generateMeetingPdfReport({
    meetingId,
    agenda = '',
    hostName = '',
    meetingMode = 'video',
    createdAt = '',
    summary = '',
    followUpMessages = [],
    participants = [],
}) {
    const doc = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: 'a4',
    });

    const pageWidth = 210;
    const pageHeight = 297;
    const margin = 15;
    const contentWidth = pageWidth - margin * 2;
    const bottomLimit = pageHeight - 20;

    let y = 18;

    const checkAddPage = (neededHeight) => {
        if (y + neededHeight > bottomLimit) {
            doc.addPage();
            y = 18;
            return true;
        }
        return false;
    };

    // ── 1. Document Header ──────────────────────────────────────────────
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(18);
    doc.setTextColor(79, 70, 229); // #4F46E5 primary indigo
    doc.text('MEETSPACE MEETING REPORT', margin, y);
    y += 6;

    doc.setFont('helvetica', 'normal');
    doc.setFontSize(8.5);
    doc.setTextColor(100, 116, 139); // #64748B
    const genDate = new Date().toUTCString();
    doc.text(`Generated on ${genDate} • Confidential`, margin, y);
    y += 5;

    doc.setDrawColor(203, 213, 225); // #CBD5E1
    doc.setLineWidth(0.4);
    doc.line(margin, y, margin + contentWidth, y);
    y += 6;

    // ── 2. Metadata Card ────────────────────────────────────────────────
    const modeLabel = meetingMode === 'room' ? 'Room Meeting (In-Person Diarized)' : 'Video Calling';
    const dateFormatted = createdAt ? new Date(createdAt).toLocaleString() : 'N/A';

    const participantList = participants && participants.length > 0
        ? participants.map(p => (p.name && p.name !== p.email ? `${p.name} <${p.email}>` : p.email)).join(', ')
        : 'None recorded';

    const metaItems = [
        ['Meeting ID:', String(meetingId || 'N/A'), 'Mode:', modeLabel],
        ['Host / Device:', hostName || 'Organizer', 'Date & Time:', dateFormatted],
        ['Agenda:', agenda || 'No specific agenda provided', '', ''],
        ['Recipients:', participantList, '', ''],
    ];

    // Calculate metadata box height dynamically
    doc.setFontSize(8.5);
    const agendaLines = doc.splitTextToSize(`Agenda: ${agenda || 'None'}`, contentWidth - 8);
    const recipientLines = doc.splitTextToSize(`Recipients: ${participantList}`, contentWidth - 8);
    const metaBoxHeight = 22 + (agendaLines.length - 1) * 4 + (recipientLines.length - 1) * 4;

    checkAddPage(metaBoxHeight + 6);

    doc.setFillColor(248, 250, 252); // #F8FAFC
    doc.setDrawColor(203, 213, 225);
    doc.roundedRect(margin, y, contentWidth, metaBoxHeight, 2, 2, 'FD');

    let metaY = y + 5;
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(30, 41, 59);
    doc.text('Meeting ID:', margin + 4, metaY);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(15, 23, 42);
    doc.text(String(meetingId || 'N/A').slice(0, 36), margin + 25, metaY);

    doc.setFont('helvetica', 'bold');
    doc.setTextColor(30, 41, 59);
    doc.text('Mode:', margin + 98, metaY);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(15, 23, 42);
    doc.text(modeLabel, margin + 112, metaY);

    metaY += 5;
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(30, 41, 59);
    doc.text('Host:', margin + 4, metaY);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(15, 23, 42);
    doc.text(String(hostName || 'Organizer').slice(0, 32), margin + 25, metaY);

    doc.setFont('helvetica', 'bold');
    doc.setTextColor(30, 41, 59);
    doc.text('Date:', margin + 98, metaY);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(15, 23, 42);
    doc.text(dateFormatted, margin + 112, metaY);

    metaY += 5;
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(30, 41, 59);
    doc.text('Agenda:', margin + 4, metaY);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(15, 23, 42);
    const wrappedAgenda = doc.splitTextToSize(agenda || 'No specific agenda provided', contentWidth - 30);
    doc.text(wrappedAgenda, margin + 25, metaY);
    metaY += wrappedAgenda.length * 4;

    doc.setFont('helvetica', 'bold');
    doc.setTextColor(30, 41, 59);
    doc.text('Recipients:', margin + 4, metaY);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(15, 23, 42);
    const wrappedRecipients = doc.splitTextToSize(participantList, contentWidth - 30);
    doc.text(wrappedRecipients, margin + 25, metaY);

    y += metaBoxHeight + 8;

    // ── 3. Generated Meeting Summary ────────────────────────────────────
    checkAddPage(15);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(12);
    doc.setTextColor(15, 23, 42);
    doc.text('1. Generated Meeting Summary', margin, y);
    y += 6;

    if (summary && summary.trim()) {
        const paragraphs = summary.trim().split(/\n\n+/);
        doc.setFontSize(9);
        doc.setFont('helvetica', 'normal');

        for (const para of paragraphs) {
            const cleanPara = para.trim();
            if (!cleanPara) continue;

            // Check if major heading like "1. Meeting Overview" or "## Overview"
            const isHeading = /^(\d+\.\s+[A-Za-z]|##+\s+)/.test(cleanPara);

            if (isHeading) {
                checkAddPage(10);
                doc.setFont('helvetica', 'bold');
                doc.setTextColor(30, 41, 59);
                const headingText = cleanPara.replace(/^##+\s*/, '');
                doc.text(headingText, margin, y);
                y += 5;
                doc.setFont('helvetica', 'normal');
                doc.setTextColor(30, 41, 59);
            } else {
                const lines = cleanPara.split('\n');
                for (const line of lines) {
                    const cleanLine = line.trim();
                    if (!cleanLine) continue;

                    const isBullet = cleanLine.startsWith('- ') || cleanLine.startsWith('* ');
                    const textToRender = isBullet ? `•  ${cleanLine.slice(2)}` : cleanLine;
                    const xIndent = isBullet ? margin + 3 : margin;
                    const renderWidth = isBullet ? contentWidth - 3 : contentWidth;

                    const wrapped = doc.splitTextToSize(textToRender, renderWidth);
                    checkAddPage(wrapped.length * 4.5 + 2);

                    doc.text(wrapped, xIndent, y);
                    y += wrapped.length * 4.5 + 1;
                }
                y += 2; // paragraph spacing
            }
        }
    } else {
        checkAddPage(8);
        doc.setFont('helvetica', 'italic');
        doc.setFontSize(9);
        doc.setTextColor(100, 116, 139);
        doc.text('No meeting summary was generated for this session.', margin, y);
        y += 6;
    }

    y += 5;

    // ── 4. AI Follow-Up Conversation ───────────────────────────────────
    checkAddPage(15);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(12);
    doc.setTextColor(15, 23, 42);
    doc.text('2. Complete AI Follow-Up Conversation', margin, y);
    y += 6;

    if (followUpMessages && followUpMessages.length > 0) {
        for (const msg of followUpMessages) {
            const isUser = msg.message_by === 'user';
            const senderLabel = isUser ? 'User / Participant' : '✦ AI Assistant';
            const timeStr = msg.timestamp
                ? new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                : '';

            doc.setFontSize(8.5);
            const wrappedContent = doc.splitTextToSize(msg.content || '', contentWidth - 10);
            const cardHeight = 10 + wrappedContent.length * 4.2;

            checkAddPage(cardHeight + 4);

            // Card background & border
            if (isUser) {
                doc.setFillColor(241, 245, 249); // #F1F5F9 slate
                doc.setDrawColor(203, 213, 225);
            } else {
                doc.setFillColor(238, 242, 255); // #EEF2FF indigo light
                doc.setDrawColor(199, 210, 254);
            }

            doc.roundedRect(margin, y, contentWidth, cardHeight, 1.5, 1.5, 'FD');

            // Header line inside card
            doc.setFont('helvetica', 'bold');
            doc.setTextColor(isUser ? 51 : 79, isUser ? 65 : 70, isUser ? 85 : 229);
            doc.text(senderLabel, margin + 4, y + 4.5);

            if (timeStr) {
                doc.setFont('helvetica', 'normal');
                doc.setFontSize(7.5);
                doc.setTextColor(148, 163, 184);
                doc.text(timeStr, margin + contentWidth - 4, y + 4.5, { align: 'right' });
            }

            // Message content
            doc.setFont('helvetica', 'normal');
            doc.setFontSize(8.5);
            doc.setTextColor(15, 23, 42);
            doc.text(wrappedContent, margin + 4, y + 9);

            y += cardHeight + 3.5;
        }
    } else {
        checkAddPage(8);
        doc.setFont('helvetica', 'italic');
        doc.setFontSize(9);
        doc.setTextColor(100, 116, 139);
        doc.text('No follow-up questions were asked for this meeting.', margin, y);
        y += 6;
    }

    // ── 5. Add Page Numbers and Running Footers to All Pages ─────────────
    const totalPages = doc.getNumberOfPages();
    for (let i = 1; i <= totalPages; i++) {
        doc.setPage(i);
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(7.5);
        doc.setTextColor(148, 163, 184);
        doc.setDrawColor(226, 232, 240);
        doc.setLineWidth(0.3);
        doc.line(margin, pageHeight - 12, margin + contentWidth, pageHeight - 12);

        doc.text('MeetSpace • Meeting Summary & AI Report', margin, pageHeight - 8);
        doc.text(`Page ${i} of ${totalPages}`, margin + contentWidth, pageHeight - 8, { align: 'right' });
    }

    // Save PDF
    const filename = sanitizeFilename(meetingId);
    doc.save(filename);
    return filename;
}
