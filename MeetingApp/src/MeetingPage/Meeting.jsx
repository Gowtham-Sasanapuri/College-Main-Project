import React, { useState, useEffect } from 'react';
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
        // meetingAiEnabled — server-confirmed; use this for ALL rendering decisions.
        // For the host it equals initialAiEnabled immediately.
        // For joiners it starts false and becomes true once the API responds.
        meetingAiEnabled,
    } = useWebRTC(id, name, initialAiEnabled);

    // Panel visibility — closed by default; opens automatically when the server
    // confirms AI is on for this meeting (works for both host and joiner).
    const [transcriptOpen, setTranscriptOpen] = useState(false);

    useEffect(() => {
        if (meetingAiEnabled) {
            setTranscriptOpen(true);
        }
    }, [meetingAiEnabled]);

    // ── FIX FOR BUG 2 (speaker identification) ────────────────────────
    //
    // useTranscription now receives `meetingAiEnabled` (server-confirmed) instead
    // of `initialAiEnabled` (from location.state, always false for joiners).
    //
    // Effect: once the API confirms AI is on, every participant's browser starts
    // its own SpeechRecognition instance and calls sendTranscriptEntry with that
    // participant's own `name`. Speaker attribution is therefore always correct
    // for real multi-user sessions (different browsers / different devices).
    //
    // Same-browser tab limitation (Edge multi-tab testing):
    // When multiple tabs run in the same browser process, they all share the
    // same physical microphone. Every tab's SpeechRecognition hears the same
    // audio, so all tabs will transcribe simultaneously and attribute the text
    // to their own user's name. This causes duplicate entries and does NOT
    // reflect which tab the user is "speaking into" — that concept does not
    // exist at the OS level. This is an inherent limitation of same-browser
    // testing, not a bug. With separate browsers or devices each participant's
    // mic is isolated and attribution is correct.
    // Pass `audioEnabled` so SpeechRecognition pauses when the mic is muted.
    // Without this, the recognition engine opens its own independent OS-level
    // audio capture that is unaffected by the WebRTC track.enabled toggle,
    // causing transcription to continue even when the participant is muted.
    useTranscription(meetingAiEnabled, audioEnabled, name, sendTranscriptEntry);

    const totalParticipants = 1 + remoteStreams.length;

    return (
        // Use meetingAiEnabled — not initialAiEnabled — for every conditional below.
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
                onHangUp={hangUp}
                participantCount={totalParticipants}
            />

            {/* ── Transcript Panel ─────────────────────────────────── */}
            {/* Gated on meetingAiEnabled — mounts for every participant whose
                meeting has AI on, not just the creator. */}
            {meetingAiEnabled && (
                <TranscriptPanel
                    entries={transcriptEntries}
                    isOpen={transcriptOpen}
                    onToggle={() => setTranscriptOpen(o => !o)}
                />
            )}
        </div>
    );
};

export default Meeting;
