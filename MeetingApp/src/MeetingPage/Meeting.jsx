import { useState } from 'react';
import { useParams, useLocation } from 'react-router-dom';
import { useWebRTC } from './hooks/useWebRTC';
import { useTranscription } from './hooks/useTranscription';
import VideoTile from './components/VideoTile';
import ControlBar from './components/ControlBar';
import TranscriptPanel from './components/TranscriptPanel';
import styles from './Meeting.module.css';

const Meeting = () => {
    const { id } = useParams();
    const location = useLocation();

    // `initialAiEnabled` is only a hint from the host's navigation state.
    // Joiners arrive with `location.state = { name }` — no aiEnabled field.
    // The authoritative value always comes from the server via useWebRTC's
    // JoinMeeting fetch and is returned as `meetingAiEnabled`.
    const { name, aiEnabled: initialAiEnabled = false } = location.state || {};

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
        participantId,
        isMeetingEnded,
    } = useWebRTC(id, name, initialAiEnabled);

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
            const response = await fetch('http://127.0.0.1:8000/endMeeting/', {
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

    const totalParticipants = 1 + remoteStreams.length;

    return (
        <div className={`${styles.page} ${meetingAiEnabled && transcriptOpen ? styles.pageWithPanel : ''}`}>

            {/* ── Header ──────────────────────────────────────────── */}
            <header className={styles.header}>
                <div className={styles.headerLeft}>
                    <div className={styles.logo}>
                        <span className={styles.logoIcon}>⬡</span>
                        <span className={styles.logoText}>MeetSpace</span>
                    </div>
                </div>

                <div className={styles.headerCenter}>
                    <span className={styles.meetingId}>
                        ID: <strong>{id?.slice(0, 8)}…</strong>
                    </span>
                </div>

                <div className={styles.headerRight}>
                    {meetingAiEnabled && (
                        <span className={styles.aiBadge}>
                            <span className={styles.aiDot} />
                            AI On
                        </span>
                    )}
                    <span className={`${styles.statusBadge} ${styles[connectionStatus]}`}>
                        {connectionStatus === 'connected'
                            ? '● Live'
                            : connectionStatus === 'error'
                                ? '✕ Error'
                                : '○ Connecting…'}
                    </span>
                </div>
            </header>

            {/* ── Video Grid ──────────────────────────────────────── */}
            <main className={styles.grid} data-count={totalParticipants}>

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
                        <div className={styles.waitingIcon}>👋</div>
                        <p className={styles.waitingTitle}>Waiting for others…</p>
                        <p className={styles.waitingHint}>Share your meeting ID to invite participants.</p>
                        <div className={styles.meetingIdCopy}>
                            <code className={styles.idText}>{id}</code>
                        </div>
                    </div>
                )}
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
                                <p className={styles.modalEyebrow}>Meeting Options</p>
                                <h2 id="end-meeting-title" className={styles.modalTitle}>
                                    {summaryReady && (summaryText || summaryMessage || summaryError)
                                        ? 'Meeting Summary'
                                        : 'Are you sure you want to leave?'}
                                </h2>
                            </div>
                            {!summaryLoading && (
                                <button className={styles.modalClose} onClick={closeEndDialog} aria-label="Close end meeting dialog">
                                    ✕
                                </button>
                            )}
                        </div>

                        {summaryLoading ? (
                            <div className={styles.modalBody}>
                                <div className={styles.loadingSpinner} />
                                <p className={styles.modalStatus}>Generating meeting summary...</p>
                            </div>
                        ) : summaryReady ? (
                            <div className={styles.modalBody}>
                                {summaryError ? (
                                    <p className={styles.modalError}>{summaryError}</p>
                                ) : summaryMessage ? (
                                    <p className={styles.modalHint}>{summaryMessage}</p>
                                ) : (
                                    <pre className={styles.summaryText}>{summaryText}</pre>
                                )}
                                <div className={styles.modalActions}>
                                    <button className={styles.primaryButton} onClick={handleLeaveOnly}>
                                        Leave
                                    </button>
                                </div>
                            </div>
                        ) : (
                            <div className={styles.modalBody}>
                                <p className={styles.modalHint}>
                                    Generate an AI summary of the conversation up to this point, or leave the meeting directly.
                                </p>
                                <div className={styles.modalActions}>
                                    <button className={styles.secondaryButton} onClick={handleLeaveOnly}>
                                        Leave Meeting
                                    </button>
                                    <button className={styles.primaryButton} onClick={handleGenerateSummary}>
                                        Generate Summary
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
