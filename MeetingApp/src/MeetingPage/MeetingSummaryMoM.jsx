import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Navbar from '../Front/components/Navbar/Navbar';
import { generateMeetingPdfReport } from '../utils/generatePdfReport';
import styles from './MeetingSummaryMoM.module.css';

const API_BASE = 'http://127.0.0.1:8000';

const MeetingSummaryMoM = () => {
    const { id } = useParams();
    const nav = useNavigate();

    const [loading, setLoading] = useState(true);
    const [regenerating, setRegenerating] = useState(false);
    const [downloading, setDownloading] = useState(false);
    const [sendingEmail, setSendingEmail] = useState(false);
    const [emailMessage, setEmailMessage] = useState('');
    const [error, setError] = useState('');
    const [isEditing, setIsEditing] = useState(false);

    // Complete MoM Data Object
    const [mom, setMom] = useState(null);

    const fetchMoMData = async () => {
        setLoading(true);
        setError('');
        try {
            const res = await fetch(`${API_BASE}/meeting/mom/${id}/`);
            const data = await res.json();
            if (data.success && data.mom_data) {
                setMom(data.mom_data);
            } else {
                setError(data.message || 'Unable to retrieve Minutes of Meeting.');
            }
        } catch (err) {
            console.error('Fetch MoM error:', err);
            setError('Failed to connect to the meeting backend server.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (id) {
            fetchMoMData();
        }
    }, [id]);

    const handleSaveEdits = async () => {
        try {
            const res = await fetch(`${API_BASE}/meeting/mom/${id}/`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mom_data: mom }),
            });
            const data = await res.json();
            if (data.success) {
                setIsEditing(false);
                alert('Minutes of Meeting saved successfully.');
            } else {
                alert(data.message || 'Failed to save changes.');
            }
        } catch (err) {
            console.error('Save error:', err);
            alert('Failed to save changes to the server.');
        }
    };

    const handleRegenerate = async () => {
        if (!window.confirm('Regenerate Minutes of Meeting using Gemini AI? Any unsaved manual edits will be overwritten.')) {
            return;
        }
        setRegenerating(true);
        try {
            const res = await fetch(`${API_BASE}/meeting/mom/${id}/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });
            const data = await res.json();
            if (data.success && data.mom_data) {
                setMom(data.mom_data);
                alert('Minutes of Meeting regenerated successfully!');
            } else {
                alert(data.message || 'Failed to regenerate MoM.');
            }
        } catch (err) {
            console.error('Regenerate error:', err);
            alert('Connection error during AI regeneration.');
        } finally {
            setRegenerating(false);
        }
    };

    const handleDownloadPdf = async () => {
        setDownloading(true);
        try {
            const response = await fetch(`${API_BASE}/meeting/download-report/${id}/`);
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `Meeting_Report_${id.substring(0, 8)}.pdf`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);
                return;
            }
            throw new Error(`Server returned status ${response.status}`);
        } catch (err) {
            console.warn('Backend PDF download unavailable, generating via client jsPDF:', err);
            try {
                generateMeetingPdfReport({
                    meetingId: id,
                    title: mom?.meeting_info?.title || '',
                    agenda: mom?.meeting_info?.agenda ? (Array.isArray(mom.meeting_info.agenda) ? mom.meeting_info.agenda.map(a => a.title || a).join('; ') : String(mom.meeting_info.agenda)) : '',
                    hostName: mom?.meeting_info?.organizer || '',
                    meetingMode: mom?.meeting_info?.meeting_type?.toLowerCase().includes('room') ? 'room' : 'video',
                    venue: mom?.meeting_info?.venue || '',
                    scheduledDate: mom?.meeting_info?.date || '',
                    scheduledStartTime: mom?.meeting_info?.scheduled_start_time || '',
                    scheduledEndTime: mom?.meeting_info?.scheduled_end_time || '',
                    expectedDuration: mom?.meeting_info?.scheduled_duration || '',
                    actualStartTime: mom?.meeting_info?.actual_start_time || '',
                    actualEndTime: mom?.meeting_info?.actual_end_time || '',
                    actualDurationSeconds: mom?.meeting_info?.actual_duration_seconds || 0,
                    summary: mom?.summary?.meeting_overview || mom?.executive_summary || '',
                    momData: mom,
                    participants: mom?.meeting_info?.participants || mom?.attendance?.present || [],
                });
            } catch (pdfErr) {
                console.error('Client PDF generation error:', pdfErr);
                window.print();
            }
        } finally {
            setDownloading(false);
        }
    };

    const handleSendEmail = async () => {
        setSendingEmail(true);
        setEmailMessage('');
        try {
            const res = await fetch(`${API_BASE}/meeting/send-report/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ meeting_id: id }),
            });
            const data = await res.json();
            if (data.success) {
                setEmailMessage(`✓ Sent to ${data.sent_count} recipient(s).`);
            } else {
                setEmailMessage(`⚠ ${data.message || 'Failed to dispatch email.'}`);
            }
        } catch (err) {
            console.error('Email error:', err);
            setEmailMessage('⚠ Could not dispatch email report.');
        } finally {
            setSendingEmail(false);
        }
    };

    const toggleActionStatus = (index) => {
        setMom((prev) => {
            const next = { ...prev };
            const actions = [...(next.summary?.action_items || next.action_items || [])];
            const current = actions[index].status;
            actions[index] = {
                ...actions[index],
                status: current === 'Completed' ? 'Pending' : 'Completed',
            };
            if (next.summary) next.summary.action_items = actions;
            next.action_items = actions;
            return next;
        });
    };

    if (loading) {
        return (
            <div className={styles.page}>
                <Navbar />
                <div className={styles.container} style={{ textAlign: 'center', paddingTop: '100px' }}>
                    <div style={{ fontSize: '1.2rem', fontWeight: '600', color: 'var(--text-secondary)' }}>
                        Loading Minutes of Meeting...
                    </div>
                </div>
            </div>
        );
    }

    if (error || !mom) {
        return (
            <div className={styles.page}>
                <Navbar />
                <div className={styles.container} style={{ textAlign: 'center', paddingTop: '80px' }}>
                    <h2 style={{ color: 'var(--danger)' }}>Unable to Load Minutes</h2>
                    <p style={{ color: 'var(--text-muted)', margin: '12px 0 24px' }}>{error}</p>
                    <button className={styles.btnPrimary} onClick={() => nav('/')}>
                        ← Return to Dashboard
                    </button>
                </div>
            </div>
        );
    }

    const info = mom.meeting_info || {};
    const summaryData = mom.summary || {};

    const meetingTitle = info.title || 'Meeting Session';
    const meetingType = info.meeting_type || 'Online Video Meeting';
    const isRoom = meetingType.toLowerCase().includes('room');
    const venueLabel = isRoom ? 'Venue' : 'Online Meeting Link';
    const venueValue = info.venue || (isRoom ? 'Meeting Room' : `/Meeting/${id}`);

    // Participants list
    const participantsList = info.participants || mom.attendance?.present || [];

    // Agenda list or text
    const agendaItems = info.agenda || mom.agenda || [];

    // Section 2 elements
    const overview = summaryData.meeting_overview || mom.executive_summary || 'Meeting conducted and recorded.';
    const discussionPoints = summaryData.discussion_points || mom.discussion_points || [];

    // Decisions Made (only valid confirmed decisions, omit if empty)
    const rawDecisions = summaryData.decisions || mom.decisions_made || [];
    const decisionsMade = Array.isArray(rawDecisions)
        ? rawDecisions.filter(d => String(d).trim() && !['none', 'none agreed', 'n/a', 'no decisions made'].includes(String(d).toLowerCase().trim()))
        : [];

    // Action Items (omit if empty)
    const rawActions = summaryData.action_items || mom.action_items || [];
    const actionItems = Array.isArray(rawActions)
        ? rawActions.filter(a => {
            if (typeof a === 'object' && a !== null) {
                return Boolean((a.task || a.description || '').trim());
            }
            return Boolean(String(a).trim());
        })
        : [];

    // Pending Issues (omit if empty)
    const rawPending = summaryData.pending_issues || mom.unresolved_questions || [];
    const pendingIssues = Array.isArray(rawPending)
        ? rawPending.filter(p => {
            const clean = String(p).trim().toLowerCase();
            return clean && !['none', 'none identified', 'none identified during the meeting.', 'n/a', 'not discussed'].includes(clean);
        })
        : [];

    // Conclusion
    const conclusion = summaryData.conclusion || mom.conclusion || '';

    return (
        <div className={styles.page}>
            <Navbar />

            <div className={styles.container}>
                {/* Top Action Header */}
                <div className={styles.topBar}>
                    <button className={styles.backBtn} onClick={() => nav('/')}>
                        ← Dashboard
                    </button>

                    <div className={styles.actionGroup}>
                        {isEditing ? (
                            <>
                                <button className={styles.btnSecondary} onClick={() => setIsEditing(false)}>
                                    Cancel
                                </button>
                                <button className={styles.btnPrimary} onClick={handleSaveEdits}>
                                    💾 Save MoM
                                </button>
                            </>
                        ) : (
                            <button className={styles.btnSecondary} onClick={() => setIsEditing(true)}>
                                ✎ Edit MoM
                            </button>
                        )}

                        <button
                            className={styles.btnSecondary}
                            onClick={handleRegenerate}
                            disabled={regenerating}
                            title="Regenerate with Gemini AI"
                        >
                            {regenerating ? 'Regenerating...' : '✦ AI Regenerate'}
                        </button>

                        <button
                            className={styles.btnSecondary}
                            onClick={handleDownloadPdf}
                            disabled={downloading}
                        >
                            {downloading ? 'Preparing...' : '📥 Download PDF'}
                        </button>

                        <button className={styles.btnSecondary} onClick={() => window.print()}>
                            🖨️ Print
                        </button>

                        <button
                            className={styles.btnSecondary}
                            onClick={handleSendEmail}
                            disabled={sendingEmail}
                        >
                            {sendingEmail ? 'Sending...' : '✉️ Email Report'}
                        </button>
                    </div>
                </div>

                {emailMessage && (
                    <div
                        style={{
                            padding: '10px 16px',
                            borderRadius: '8px',
                            background: emailMessage.startsWith('✓') ? 'var(--success-subtle)' : 'var(--warning-subtle)',
                            color: emailMessage.startsWith('✓') ? 'var(--success)' : 'var(--warning)',
                            fontWeight: '600',
                            fontSize: '0.85rem',
                        }}
                    >
                        {emailMessage}
                    </div>
                )}

                {/* Printable MoM Paper Document */}
                <div className={styles.paper}>
                    {/* Header Banner */}
                    <div className={styles.momHeader}>
                        <div className={styles.momBadge}>
                            <span>✦ Official Minutes of Meeting</span>
                        </div>
                        <h1 className={styles.momTitle}>{meetingTitle}</h1>
                        <span className={styles.momSubtitle}>
                            {meetingType} • Organized by {info.organizer || 'Organizer'}
                        </span>
                    </div>

                    {/* ══════════════════════════════════════════════════════════
                        SECTION 1: MEETING INFORMATION
                        ══════════════════════════════════════════════════════════ */}
                    <div className={styles.section}>
                        <div className={styles.sectionHeader}>
                            <div className={styles.sectionTitle}>
                                <span className={styles.sectionLetter}>1</span>
                                <span>SECTION 1: MEETING INFORMATION</span>
                            </div>
                        </div>

                        <div className={styles.infoGrid}>
                            <div className={styles.infoCard}>
                                <span className={styles.infoLabel}>Meeting Title</span>
                                <span className={styles.infoValue}>{meetingTitle}</span>
                            </div>

                            <div className={styles.infoCard}>
                                <span className={styles.infoLabel}>Meeting ID</span>
                                <span className={styles.infoValue}>{info.meeting_id || id}</span>
                            </div>

                            <div className={styles.infoCard}>
                                <span className={styles.infoLabel}>Meeting Type</span>
                                <span className={styles.infoValue}>{meetingType}</span>
                            </div>

                            <div className={styles.infoCard}>
                                <span className={styles.infoLabel}>Date (IST)</span>
                                <span className={styles.infoValue}>{info.date || 'N/A'}</span>
                            </div>

                            <div className={styles.infoCard}>
                                <span className={styles.infoLabel}>Organizer</span>
                                <span className={styles.infoValue}>{info.organizer || 'Organizer'}</span>
                            </div>

                            <div className={styles.infoCard}>
                                <span className={styles.infoLabel}>{venueLabel}</span>
                                <span className={styles.infoValue}>{venueValue}</span>
                            </div>

                            <div className={styles.infoCard}>
                                <span className={styles.infoLabel}>Scheduled Window (IST)</span>
                                <span className={styles.infoValue}>
                                    {info.scheduled_start_time && info.scheduled_start_time !== 'N/A'
                                        ? `${info.scheduled_start_time} - ${info.scheduled_end_time || ''} (${info.scheduled_duration || ''})`
                                        : 'Not scheduled'}
                                </span>
                            </div>

                            <div className={styles.infoCard}>
                                <span className={styles.infoLabel}>Actual Timing (IST)</span>
                                <span className={styles.infoValue}>
                                    {info.actual_start_time || 'N/A'} - {info.actual_end_time || 'N/A'}
                                </span>
                            </div>

                            <div className={styles.infoCard}>
                                <span className={styles.infoLabel}>Actual Duration</span>
                                <span className={styles.infoValue} style={{ color: 'var(--accent-primary)' }}>
                                    {info.actual_duration || 'N/A'}
                                </span>
                            </div>
                        </div>

                        {/* Attendees / Participants */}
                        <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                            <span style={{ fontSize: '0.82rem', fontWeight: '700', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                                Attendees / Participants:
                            </span>
                            <div className={styles.badgesList}>
                                {participantsList && participantsList.length > 0 ? (
                                    participantsList.map((p, idx) => {
                                        const name = typeof p === 'object' ? (p.name || p.email) : String(p);
                                        const role = typeof p === 'object' ? p.role : null;
                                        return (
                                            <div key={idx} className={styles.participantBadge}>
                                                <span>👤</span>
                                                <span>{name}</span>
                                                {role && <span className={styles.roleTag}>{role}</span>}
                                            </div>
                                        );
                                    })
                                ) : (
                                    <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                                        {info.organizer || 'Organizer'}
                                    </span>
                                )}
                            </div>
                        </div>

                        {/* Meeting Agenda */}
                        <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                            <span style={{ fontSize: '0.82rem', fontWeight: '700', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                                Meeting Agenda:
                            </span>
                            <div className={styles.agendaGrid}>
                                {agendaItems && agendaItems.length > 0 ? (
                                    agendaItems.map((item, idx) => {
                                        const itemTitle = typeof item === 'object' ? item.title : String(item);
                                        const presenter = typeof item === 'object' ? item.presenter : null;
                                        const dur = typeof item === 'object' ? item.expected_duration : null;
                                        return (
                                            <div key={idx} className={styles.agendaCard}>
                                                <div className={styles.agendaInfo}>
                                                    <span className={styles.agendaItemTitle}>
                                                        {idx + 1}. {itemTitle}
                                                    </span>
                                                    {(presenter || dur) && (
                                                        <span className={styles.agendaItemMeta}>
                                                            {presenter ? `Presenter: ${presenter}` : ''}
                                                            {dur ? ` • Allocated: ${dur}` : ''}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        );
                                    })
                                ) : (
                                    <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                                        No formal agenda items specified.
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* ══════════════════════════════════════════════════════════
                        SECTION 2: MEETING SUMMARY
                        ══════════════════════════════════════════════════════════ */}
                    <div className={styles.section}>
                        <div className={styles.sectionHeader}>
                            <div className={styles.sectionTitle}>
                                <span className={styles.sectionLetter}>2</span>
                                <span>SECTION 2: MEETING SUMMARY</span>
                            </div>
                        </div>

                        {/* 1. Meeting Overview */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            <h3 style={{ fontSize: '1rem', fontWeight: '700', margin: 0, color: 'var(--text-primary)' }}>
                                Meeting Overview
                            </h3>
                            {isEditing ? (
                                <textarea
                                    className={styles.editTextarea}
                                    value={overview}
                                    onChange={(e) =>
                                        setMom((prev) => {
                                            const next = { ...prev };
                                            if (!next.summary) next.summary = {};
                                            next.summary.meeting_overview = e.target.value;
                                            next.executive_summary = e.target.value;
                                            return next;
                                        })
                                    }
                                />
                            ) : (
                                <div className={styles.summaryBox}>
                                    {overview}
                                </div>
                            )}
                        </div>

                        {/* 2. Key Discussion Points */}
                        {discussionPoints && discussionPoints.length > 0 && (
                            <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                <h3 style={{ fontSize: '1rem', fontWeight: '700', margin: 0, color: 'var(--text-primary)' }}>
                                    Key Discussion Points
                                </h3>
                                <div className={styles.discList}>
                                    {discussionPoints.map((dp, idx) => {
                                        const topic = typeof dp === 'object' ? dp.topic : null;
                                        const details = typeof dp === 'object' ? (dp.details || dp.text) : String(dp);
                                        return (
                                            <div key={idx} className={styles.discCard}>
                                                {topic && (
                                                    <div className={styles.discTopic}>
                                                        {idx + 1}. {topic}
                                                    </div>
                                                )}
                                                <div className={styles.discText}>{details}</div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}

                        {/* 3. Decisions Made (omitted if empty) */}
                        {decisionsMade.length > 0 && (
                            <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                <h3 style={{ fontSize: '1rem', fontWeight: '700', margin: 0, color: 'var(--text-primary)' }}>
                                    Decisions Made
                                </h3>
                                <div className={styles.decisionsList}>
                                    {decisionsMade.map((dec, idx) => (
                                        <div key={idx} className={styles.decisionItem}>
                                            <span className={styles.decNumber}>{idx + 1}.</span>
                                            <span>{String(dec)}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* 4. Action Items (omitted if empty) */}
                        {actionItems.length > 0 && (
                            <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                <h3 style={{ fontSize: '1rem', fontWeight: '700', margin: 0, color: 'var(--text-primary)' }}>
                                    Action Items
                                </h3>
                                <div className={styles.tableResponsive}>
                                    <table className={styles.actionTable}>
                                        <thead>
                                            <tr>
                                                <th style={{ width: '45px' }}>Done</th>
                                                <th>Task Description</th>
                                                <th>Assigned Owner</th>
                                                <th>Deadline</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {actionItems.map((act, idx) => {
                                                const task = typeof act === 'object' ? (act.task || act.description) : String(act);
                                                const owner = typeof act === 'object' ? (act.owner || 'Unassigned') : 'Unassigned';
                                                const deadline = typeof act === 'object' ? (act.deadline || 'Not specified') : 'Not specified';
                                                const isDone = typeof act === 'object' && act.status === 'Completed';

                                                return (
                                                    <tr key={idx} className={isDone ? styles.rowDone : ''}>
                                                        <td style={{ textAlign: 'center' }}>
                                                            <input
                                                                type="checkbox"
                                                                checked={isDone}
                                                                onChange={() => toggleActionStatus(idx)}
                                                            />
                                                        </td>
                                                        <td>{task}</td>
                                                        <td>{owner}</td>
                                                        <td>{deadline}</td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        )}

                        {/* 5. Pending Issues (omitted if empty) */}
                        {pendingIssues.length > 0 && (
                            <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                <h3 style={{ fontSize: '1rem', fontWeight: '700', margin: 0, color: 'var(--text-primary)' }}>
                                    Pending Issues
                                </h3>
                                <div className={styles.textBlock}>
                                    <ul style={{ margin: 0, paddingLeft: '20px' }}>
                                        {pendingIssues.map((p, idx) => (
                                            <li key={idx} style={{ marginBottom: '4px' }}>{String(p)}</li>
                                        ))}
                                    </ul>
                                </div>
                            </div>
                        )}

                        {/* 6. Conclusion */}
                        {conclusion && (
                            <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                <h3 style={{ fontSize: '1rem', fontWeight: '700', margin: 0, color: 'var(--text-primary)' }}>
                                    Conclusion
                                </h3>
                                {isEditing ? (
                                    <textarea
                                        className={styles.editTextarea}
                                        value={conclusion}
                                        onChange={(e) =>
                                            setMom((prev) => {
                                                const next = { ...prev };
                                                if (!next.summary) next.summary = {};
                                                next.summary.conclusion = e.target.value;
                                                next.conclusion = e.target.value;
                                                return next;
                                            })
                                        }
                                    />
                                ) : (
                                    <div className={styles.textBlock}>
                                        {conclusion}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default MeetingSummaryMoM;
