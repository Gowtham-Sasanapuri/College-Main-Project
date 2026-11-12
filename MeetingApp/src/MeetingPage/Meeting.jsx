import { useState, useEffect } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import { useWebRTC } from './hooks/useWebRTC';
import { useTranscription } from './hooks/useTranscription';
import { generateMeetingPdfReport } from '../utils/generatePdfReport';
import VideoTile from './components/VideoTile';
import ControlBar from './components/ControlBar';
import TranscriptPanel from './components/TranscriptPanel';
import FollowUpChat from './components/FollowUpChat';
import MeetingDetailsDrawer from './components/MeetingDetailsDrawer';
import { API_BASE } from '../config';
import styles from './Meeting.module.css';

const Meeting = () => {
    const { id } = useParams();
    const location = useLocation();
    const nav = useNavigate();

    // `initialAiEnabled` is only a hint from the host's navigation state.
    // Joiners arrive with `location.state = { name, email }` — no aiEnabled field.
    // The authoritative value always comes from the server via useWebRTC's
    // JoinMeeting fetch and is returned as `meetingAiEnabled`.
    const { name, email = '', aiEnabled: initialAiEnabled = false } = location.state || {};

    const {
        localVideoRef,
        remoteStreams,
        videoEnabled,
        audioEnabled,
        connectionStatus,
        toggleVideo,
        toggleAudio,
        hangUp,
        transcriptEntries,
        sendTranscriptEntry,
        meetingAiEnabled,
        existingSummary,
        registeredParticipants,
        participantId,
        isMeetingEnded,
    } = useWebRTC(id, name, email, initialAiEnabled);

    // Panel visibility — closed by default; opens automatically when the server
    // confirms AI is on for this meeting (works for both host and joiner).
    const [transcriptOpen, setTranscriptOpen] = useState(false);
    const [transcriptUserControlled, setTranscriptUserControlled] = useState(false);
    const [endDialogOpen, setEndDialogOpen] = useState(false);
    const [summaryLoading, setSummaryLoading] = useState(false);
    const [summaryError, setSummaryError] = useState('');
    const [summaryMessage, setSummaryMessage] = useState('');
    const [summaryText, setSummaryText] = useState('');
    const [summaryReady, setSummaryReady] = useState(false);
    const [modalTab, setModalTab] = useState('summary'); // 'summary' | 'followup'
    const [idCopied, setIdCopied] = useState(false);

    // Meeting report & email delivery states
    const [isDownloadingPdf, setIsDownloadingPdf] = useState(false);
    const [isSendingEmail, setIsSendingEmail] = useState(false);
    const [showEmailReview, setShowEmailReview] = useState(false);
    const [emailNotice, setEmailNotice] = useState({ type: '', message: '' });
    const [currentParticipants, setCurrentParticipants] = useState([]);
    const [detailsDrawerOpen, setDetailsDrawerOpen] = useState(false);
    const [meetingDetails, setMeetingDetails] = useState({});

    // Fetch meeting details and start session if scheduled
    useEffect(() => {
        if (!id) return;
        fetch(`${API_BASE}/meeting/details/${id}/`)
            .then((r) => (r.ok ? r.json() : null))
            .then((data) => {
                if (data && data.success) {
                    setMeetingDetails(data);
                    if (data.lifecycle_status === 'scheduled') {
                        fetch(`${API_BASE}/meeting/start/${id}/`, { method: 'POST' }).catch(() => {});
                    }
                }
            })
            .catch((e) => console.error('Fetch meeting details error:', e));
    }, [id]);

    // Keep participant list synchronized
    useEffect(() => {
        if (registeredParticipants && registeredParticipants.length > 0) {
            setCurrentParticipants(registeredParticipants);
        }
    }, [registeredParticipants]);

    // Fetch participant list when dialog opens
    useEffect(() => {
        if (endDialogOpen && id) {
            fetch(`${API_BASE}/meeting/participants/${id}/`)
                .then(r => r.ok ? r.json() : null)
                .then(data => {
                    if (data && data.success && Array.isArray(data.participants)) {
                        setCurrentParticipants(data.participants);
                    }
                })
                .catch(() => {});
        }
    }, [endDialogOpen, id]);

    // Download complete PDF report (Official backend PDF with client fallback)
    const handleDownloadReportPdf = async () => {
        setIsDownloadingPdf(true);
        try {
            const backendRes = await fetch(`${API_BASE}/meeting/download-report/${id}/`);
            if (backendRes.ok) {
                const blob = await backendRes.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `meeting_report_${String(id).slice(0, 8)}.pdf`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);
                return;
            }
        } catch (fetchErr) {
            console.warn('[PDF_DOWNLOAD] Backend download unavailable, trying client fallback:', fetchErr);
        }

        try {
            const res = await fetch(`${API_BASE}/meeting/report/${id}/`);
            const data = await res.json();
            if (res.ok && data.success) {
                generateMeetingPdfReport({
                    meetingId: id,
                    title: data.title || '',
                    agenda: data.agenda || '',
                    hostName: data.host_name || '',
                    meetingMode: 'video',
                    venue: data.venue || '',
                    scheduledDate: data.scheduled_date || '',
                    scheduledStartTime: data.scheduled_start_time || '',
                    scheduledEndTime: data.scheduled_end_time || '',
                    expectedDuration: data.expected_duration || '',
                    actualStartTime: data.actual_start_time || '',
                    actualEndTime: data.actual_end_time || '',
                    actualDurationSeconds: data.actual_duration_seconds || 0,
                    createdAt: data.created_at || '',
                    summary: data.summary || summaryText,
                    momData: data.mom_data || null,
                    followUpMessages: data.follow_up_messages || [],
                    participants: data.participants || currentParticipants,
                });
            } else {
                generateMeetingPdfReport({
                    meetingId: id,
                    agenda: '',
                    hostName: name || 'Participant',
                    meetingMode: 'video',
                    createdAt: new Date().toISOString(),
                    summary: summaryText,
                    followUpMessages: [],
                    participants: currentParticipants,
                });
            }
        } catch (err) {
            console.error('[REPORT_DOWNLOAD] Fallback Failed:', err);
            generateMeetingPdfReport({
                meetingId: id,
                agenda: '',
                hostName: name || 'Participant',
                meetingMode: 'video',
                createdAt: new Date().toISOString(),
                summary: summaryText,
                followUpMessages: [],
                participants: currentParticipants,
            });
        } finally {
            setIsDownloadingPdf(false);
        }
    };

    // Send report PDF to participant emails via backend Django service
    const handleSendReportEmail = async () => {
        setIsSendingEmail(true);
        setEmailNotice({ type: '', message: '' });

        try {
            const res = await fetch(`${API_BASE}/meeting/send-report/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ meeting_id: id }),
            });
            const data = await res.json();

            if (res.ok && data.success) {
                setEmailNotice({
                    type: 'success',
                    message: data.message || `Meeting report sent successfully to ${data.sent_count} recipient(s).`,
                });
            } else {
                setEmailNotice({
                    type: 'error',
                    message: data.message || 'Failed to send meeting report emails.',
                });
            }
        } catch (err) {
            console.error('[SEND_EMAIL] Error:', err);
            setEmailNotice({
                type: 'error',
                message: 'Network error: could not connect to server to send report emails.',
            });
        } finally {
            setIsSendingEmail(false);
        }
    };

    // Synchronize existing summary if meeting was already summarized
    useEffect(() => {
        if (existingSummary && !summaryText) {
            setSummaryText(existingSummary);
            setSummaryReady(true);
        }
    }, [existingSummary, summaryText]);

    // Live speech recognition
    const { stopRecognition } = useTranscription(
        meetingAiEnabled && !isMeetingEnded,
        audioEnabled,
        name,
        sendTranscriptEntry
    );

    const closeEndDialog = () => {
        if (summaryLoading) return;
        setEndDialogOpen(false);
        setSummaryError('');
        setSummaryMessage('');
        setSummaryText('');
        setSummaryReady(false);
    };

    const handleHangUp = () => {
        if (!meetingAiEnabled) {
            stopRecognition();
            hangUp();
            return;
        }

        setSummaryError('');
        setSummaryMessage('');
        setSummaryText('');
        setSummaryReady(false);
        setEndDialogOpen(true);
    };

    const handleLeaveOnly = () => {
        if (summaryLoading) return;
        stopRecognition();
        setEndDialogOpen(false);
        hangUp();
    };

    const transcriptPanelOpen = transcriptUserControlled ? transcriptOpen : meetingAiEnabled;

    const endMeetingRequest = async (generateSummary) => {
        setSummaryLoading(true);
        setSummaryError('');
        setSummaryMessage('');
        setSummaryText('');
        setSummaryReady(false);

        try {
            const response = await fetch(`${API_BASE}/endMeeting/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    meeting_id: id,
                    generate_summary: generateSummary,
                }),
            });

            const data = await response.json();

            if (data.success && data.summary_generated) {
                setSummaryText(data.summary || '');
                setSummaryReady(true);
                setEndDialogOpen(true);
                return;
            }

            if (data.success && data.no_transcript) {
                setSummaryMessage(data.message || 'No transcript is available to summarize.');
                setSummaryReady(true);
                setEndDialogOpen(true);
                return;
            }

            setSummaryError(data.message || 'AI summary could not be generated.');
            setEndDialogOpen(true);
        } catch {
            setSummaryError('AI summary could not be generated.');
            setEndDialogOpen(true);
        } finally {
            setSummaryLoading(false);
        }
    };

    const handleGenerateSummary = () => {
        endMeetingRequest(true);
    };

    const copyMeetingId = () => {
        if (id) {
            navigator.clipboard.writeText(id);
            setIdCopied(true);
            setTimeout(() => setIdCopied(false), 2000);
        }
    };

    const totalParticipants = 1 + remoteStreams.length;

    return (
        <div className={`${styles.page} ${meetingAiEnabled && transcriptOpen ? styles.pageWithPanel : ''}`}>

            {/* ── Top Bar ──────────────────────────────────────────── */}
            <header className={styles.header}>
                <div className={styles.headerLeft}>
                    <div className={styles.logo}>
                        <span className={styles.logoIcon}>⬡</span>
                        <span className={styles.logoText}>MeetSpace</span>
                    </div>
                </div>

                <div className={styles.headerCenter}>
                    <button
                        type="button"
                        className={styles.meetingIdBtn}
                        onClick={copyMeetingId}
                        title="Click to copy room ID"
                    >
                        <span className={styles.idPrefix}>Room</span>
                        <span className={styles.idValue}>{id?.slice(0, 8)}…</span>
                        <span className={styles.idCopyTip}>{idCopied ? 'Copied!' : 'Copy'}</span>
                    </button>
                </div>

                <div className={styles.headerRight}>
                    <button
                        type="button"
                        onClick={() => setDetailsDrawerOpen(true)}
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                            padding: '6px 12px',
                            borderRadius: 'var(--radius-sm)',
                            background: 'var(--bg-surface-raised)',
                            border: '1px solid var(--border-default)',
                            color: 'var(--text-primary)',
                            fontSize: '0.82rem',
                            fontWeight: '600',
                            cursor: 'pointer',
                        }}
                    >
                        <span>📋 Details & Agenda</span>
                    </button>
                    {summaryReady && summaryText && (
                        <button
                            type="button"
                            className={styles.viewSummaryBtn}
                            onClick={() => {
                                setEndDialogOpen(true);
                                setModalTab('summary');
                            }}
                            title="View Meeting Summary & Follow-Up Questions"
                        >
                            ✦ Summary & AI
                        </button>
                    )}
                    {meetingAiEnabled && (
                        <span className={styles.aiBadge}>
                            <span className={styles.aiDot} />
                            AI Mode
                        </span>
                    )}
                    <span className={`${styles.statusBadge} ${styles[connectionStatus]}`}>
                        <span className={styles.statusIndicatorDot} />
                        {connectionStatus === 'connected'
                            ? 'Connected'
                            : connectionStatus === 'error'
                                ? 'Disconnected'
                                : 'Connecting'}
                    </span>
                </div>
            </header>

            {/* ── Video Workspace ──────────────────────────────────── */}
            <main className={styles.gridContainer}>
                <div className={styles.grid} data-count={totalParticipants}>
                    <VideoTile
                        ref={localVideoRef}
                        name={name}
                        isLocal={true}
                        videoEnabled={videoEnabled}
                    />

                    {remoteStreams.map(({ name: remoteName, stream }) => (
                        <VideoTile
                            key={remoteName}
                            stream={stream}
                            name={remoteName}
                            isLocal={false}
                        />
                    ))}

                    {remoteStreams.length === 0 && (
                        <div className={styles.waitingCard}>
                            <div className={styles.waitingIconBadge}>
                                <span>👥</span>
                            </div>
                            <h3 className={styles.waitingTitle}>You're the only one here</h3>
                            <p className={styles.waitingHint}>Share the room ID with colleagues or guests to begin.</p>
                            <div className={styles.meetingIdCopyBox}>
                                <code className={styles.idText}>{id}</code>
                                <button type="button" className={styles.waitingCopyBtn} onClick={copyMeetingId}>
                                    {idCopied ? '✓ Copied' : 'Copy ID'}
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            </main>

            {/* ── Control Bar ─────────────────────────────────────── */}
            <ControlBar
                videoEnabled={videoEnabled}
                audioEnabled={audioEnabled}
                onToggleVideo={toggleVideo}
                onToggleAudio={toggleAudio}
                onHangUp={handleHangUp}
                participantCount={totalParticipants}
            />

            {/* ── Meeting Details & Agenda Drawer ─────────────────── */}
            <MeetingDetailsDrawer
                isOpen={detailsDrawerOpen}
                onClose={() => setDetailsDrawerOpen(false)}
                meetingId={id}
                details={meetingDetails}
            />

            {/* ── Transcript Panel ─────────────────────────────────── */}
            {meetingAiEnabled && (
                <TranscriptPanel
                    entries={transcriptEntries}
                    isOpen={transcriptPanelOpen}
                    onToggle={() => {
                        setTranscriptUserControlled(true);
                        setTranscriptOpen(o => !o);
                    }}
                    participantId={participantId}
                    localUserName={name}
                />
            )}

            {/* ── Call Options / Summary Modal ─────────────────────── */}
            {endDialogOpen && (
                <div className={styles.modalBackdrop} role="presentation">
                    <div className={styles.modalCard} role="dialog" aria-modal="true" aria-labelledby="end-meeting-title">
                        <div className={styles.modalHeader}>
                            <div>
                                <p className={styles.modalEyebrow}>Meeting Overview</p>
                                <h2 id="end-meeting-title" className={styles.modalTitle}>
                                    {summaryReady && (summaryText || summaryMessage || summaryError)
                                        ? 'Meeting Summary & Report'
                                        : 'Leave Video Meeting'}
                                </h2>
                                {summaryReady && summaryText && (
                                    <div className={styles.modalNav}>
                                        <button
                                            type="button"
                                            className={`${styles.modalTabBtn} ${modalTab === 'summary' ? styles.modalTabActive : ''}`}
                                            onClick={() => setModalTab('summary')}
                                        >
                                            Summary & Key Decisions
                                        </button>
                                        <button
                                            type="button"
                                            className={`${styles.modalTabBtn} ${modalTab === 'followup' ? styles.modalTabActive : ''}`}
                                            onClick={() => setModalTab('followup')}
                                        >
                                            ✦ Ask AI Follow-Up
                                        </button>
                                    </div>
                                )}
                            </div>
                            {!summaryLoading && (
                                <button className={styles.modalClose} onClick={closeEndDialog} aria-label="Close dialog">
                                    ✕
                                </button>
                            )}
                        </div>

                        {summaryLoading ? (
                            <div className={styles.modalBody}>
                                <div className={styles.loadingSpinner} />
                                <p className={styles.modalStatus}>Synthesizing meeting discussion with Gemini AI...</p>
                            </div>
                        ) : summaryReady ? (
                            <div className={styles.modalBody}>
                                {summaryError ? (
                                    <p className={styles.modalError}>{summaryError}</p>
                                ) : summaryMessage ? (
                                    <p className={styles.modalHint}>{summaryMessage}</p>
                                ) : modalTab === 'followup' ? (
                                    <>
                                        <FollowUpChat meetingId={id} meetingMode="video" isSummaryReady={true} />

                                        {/* Meeting Report Actions (PDF Download & Email Delivery) */}
                                        <div className={styles.reportSection}>
                                            <h4 className={styles.reportSectionTitle}>
                                                <span>📄</span> Meeting Report & PDF Distribution
                                            </h4>

                                            <div className={styles.reportButtonsRow}>
                                                <button
                                                    type="button"
                                                    className={styles.downloadPdfButton}
                                                    onClick={handleDownloadReportPdf}
                                                    disabled={isDownloadingPdf}
                                                >
                                                    <span>{isDownloadingPdf ? 'Generating PDF...' : '📥 Download Report PDF'}</span>
                                                </button>

                                                <button
                                                    type="button"
                                                    className={styles.sendEmailButton}
                                                    onClick={() => setShowEmailReview(prev => !prev)}
                                                    disabled={isSendingEmail}
                                                >
                                                    <span>✉ Send Report to Participants</span>
                                                </button>
                                            </div>

                                            {/* Recipient list review before sending */}
                                            {showEmailReview && (
                                                <div className={styles.recipientReviewBox}>
                                                    <p className={styles.recipientReviewLabel}>
                                                        Recipients who will receive the official PDF summary:
                                                    </p>

                                                    {currentParticipants.length > 0 ? (
                                                        <>
                                                            <div className={styles.recipientListTags}>
                                                                {currentParticipants.map((p, idx) => (
                                                                    <span key={p.id || idx} className={styles.recipientTag}>
                                                                        ✉ {p.name && p.name !== p.email ? `${p.name} (${p.email})` : p.email}
                                                                    </span>
                                                                ))}
                                                            </div>

                                                            <div className={styles.recipientActionsRow}>
                                                                <button
                                                                    type="button"
                                                                    className={styles.sendEmailButtonSmall}
                                                                    onClick={handleSendReportEmail}
                                                                    disabled={isSendingEmail}
                                                                >
                                                                    {isSendingEmail ? 'Sending...' : 'Confirm & Send Now'}
                                                                </button>
                                                                <button
                                                                    type="button"
                                                                    className={styles.secondaryButtonSmall}
                                                                    onClick={() => setShowEmailReview(false)}
                                                                >
                                                                    Cancel
                                                                </button>
                                                            </div>
                                                        </>
                                                    ) : (
                                                        <div className={styles.recipientEmptyWarning}>
                                                            ⚠️ No participant email addresses were recorded for this session.
                                                        </div>
                                                    )}

                                                    {emailNotice.message && (
                                                        <div className={emailNotice.type === 'success' ? styles.reportSuccessNotice : styles.reportErrorNotice}>
                                                            {emailNotice.type === 'success' ? '✓ ' : '✕ '} {emailNotice.message}
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </div>

                                        <div className={styles.modalActions}>
                                            <button
                                                type="button"
                                                className={styles.secondaryButton}
                                                onClick={() => setModalTab('summary')}
                                            >
                                                ← Back to Summary
                                            </button>
                                            <button className={styles.leaveButton} onClick={handleLeaveOnly}>
                                                Leave Session
                                            </button>
                                        </div>
                                    </>
                                ) : (
                                    <>
                                        <div className={styles.summaryBox}>
                                            <pre className={styles.summaryText}>{summaryText}</pre>
                                        </div>

                                        {/* Meeting Report Actions (PDF Download & Email Delivery) */}
                                        <div className={styles.reportSection}>
                                            <h4 className={styles.reportSectionTitle}>
                                                <span>📄</span> Meeting Report & PDF Distribution
                                            </h4>

                                            <div className={styles.reportButtonsRow}>
                                                <button
                                                    type="button"
                                                    className={styles.downloadPdfButton}
                                                    onClick={handleDownloadReportPdf}
                                                    disabled={isDownloadingPdf}
                                                >
                                                    <span>{isDownloadingPdf ? 'Generating PDF...' : '📥 Download Report PDF'}</span>
                                                </button>

                                                <button
                                                    type="button"
                                                    className={styles.sendEmailButton}
                                                    onClick={() => setShowEmailReview(prev => !prev)}
                                                    disabled={isSendingEmail}
                                                >
                                                    <span>✉ Send Report to Participants</span>
                                                </button>
                                            </div>

                                            {/* Recipient list review before sending */}
                                            {showEmailReview && (
                                                <div className={styles.recipientReviewBox}>
                                                    <p className={styles.recipientReviewLabel}>
                                                        Recipients who will receive the official PDF summary:
                                                    </p>

                                                    {currentParticipants.length > 0 ? (
                                                        <>
                                                            <div className={styles.recipientListTags}>
                                                                {currentParticipants.map((p, idx) => (
                                                                    <span key={p.id || idx} className={styles.recipientTag}>
                                                                        ✉ {p.name && p.name !== p.email ? `${p.name} (${p.email})` : p.email}
                                                                    </span>
                                                                ))}
                                                            </div>

                                                            <div className={styles.recipientActionsRow}>
                                                                <button
                                                                    type="button"
                                                                    className={styles.sendEmailButtonSmall}
                                                                    onClick={handleSendReportEmail}
                                                                    disabled={isSendingEmail}
                                                                >
                                                                    {isSendingEmail ? 'Sending...' : 'Confirm & Send Now'}
                                                                </button>
                                                                <button
                                                                    type="button"
                                                                    className={styles.secondaryButtonSmall}
                                                                    onClick={() => setShowEmailReview(false)}
                                                                >
                                                                    Cancel
                                                                </button>
                                                            </div>
                                                        </>
                                                    ) : (
                                                        <div className={styles.recipientEmptyWarning}>
                                                            ⚠️ No participant email addresses were recorded for this session.
                                                        </div>
                                                    )}

                                                    {emailNotice.message && (
                                                        <div className={emailNotice.type === 'success' ? styles.reportSuccessNotice : styles.reportErrorNotice}>
                                                            {emailNotice.type === 'success' ? '✓ ' : '✕ '} {emailNotice.message}
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </div>

                                        <div className={styles.modalActions}>
                                            <button
                                                type="button"
                                                className={styles.followUpSwitchBtn}
                                                style={{ background: 'var(--accent-subtle)', color: 'var(--accent-primary)', borderColor: 'var(--accent-border)' }}
                                                onClick={() => nav(`/MeetingSummary/${id}`)}
                                            >
                                                📄 View Full Minutes of Meeting (MoM) →
                                            </button>
                                            <button
                                                type="button"
                                                className={styles.followUpSwitchBtn}
                                                onClick={() => setModalTab('followup')}
                                            >
                                                ✦ Ask AI Follow-Up Questions →
                                            </button>
                                            <button className={styles.leaveButton} onClick={handleLeaveOnly}>
                                                Leave Session
                                            </button>
                                        </div>
                                    </>
                                )}
                            </div>
                        ) : (
                            <div className={styles.modalBody}>
                                <p className={styles.modalHint}>
                                    Generate an AI summary of all transcribed discussions up to this point, or exit directly.
                                </p>
                                <div className={styles.modalActions}>
                                    <button className={styles.leaveButton} onClick={handleLeaveOnly}>
                                        Leave Meeting
                                    </button>
                                    <button className={styles.primaryButton} onClick={handleGenerateSummary}>
                                        ✦ Generate AI Summary
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default Meeting;
