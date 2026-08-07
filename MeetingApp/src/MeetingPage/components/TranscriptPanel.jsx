import React, { useEffect, useRef, useState } from 'react';
import styles from './TranscriptPanel.module.css';

/**
 * TranscriptPanel — collapsible right-side panel displaying live meeting transcript.
 *
 * @param {Array}    entries    - [{ speaker, text, timestamp }]
 * @param {boolean}  isOpen     - Controlled open/close state
 * @param {Function} onToggle   - Called when the toggle button is clicked
 */
/**
 * TranscriptPanel — collapsible right-side panel displaying live meeting transcript.
 *
 * @param {Array}    entries        - [{ id, speaker, speaker_id, text, timestamp }]
 * @param {boolean}  isOpen         - Controlled open/close state
 * @param {Function} onToggle       - Called when the toggle button is clicked
 * @param {string}   participantId  - The current user's unique session participant ID
 * @param {string}   localUserName  - The current user's display name
 */
const TranscriptPanel = ({
    entries = [],
    isOpen,
    onToggle,
    participantId,
    localUserName,
}) => {
    const bottomRef = useRef(null);
    const [animateLast, setAnimateLast] = useState(false);
    const [editingId, setEditingId] = useState(null);
    const [editText, setEditText] = useState('');
    const [editError, setEditError] = useState('');
    const [isSaving, setIsSaving] = useState(false);

    // Auto-scroll to the latest entry
    useEffect(() => {
        if (isOpen && bottomRef.current && !editingId) {
            bottomRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [entries, isOpen, editingId]);

    // Pulse animation on new entry
    useEffect(() => {
        if (entries.length === 0) return;
        setAnimateLast(true);
        const t = setTimeout(() => setAnimateLast(false), 600);
        return () => clearTimeout(t);
    }, [entries.length]);

    const formatTime = (isoString) => {
        try {
            return new Date(isoString).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false,
            });
        } catch {
            return '';
        }
    };

    const handleStartEdit = (entry) => {
        setEditingId(entry.id || entry.timestamp);
        setEditText(entry.text);
        setEditError('');
    };

    const handleCancelEdit = () => {
        setEditingId(null);
        setEditText('');
        setEditError('');
    };

    const handleSaveEdit = async (entry) => {
        if (!editText.trim()) {
            setEditError('Text cannot be empty');
            return;
        }

        setIsSaving(true);
        setEditError('');

        try {
            const response = await fetch(`http://127.0.0.1:8000/transcript/edit/${entry.id}/`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    participant_id: participantId,
                    text: editText.trim(),
                }),
            });

            const data = await response.json();

            if (response.ok && data.success) {
                setEditingId(null);
                setEditText('');
            } else {
                setEditError(data.message || 'Could not update transcript entry.');
            }
        } catch (err) {
            console.error('[EDIT] Failed to update transcript entry:', err);
            setEditError('Failed to connect to server.');
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <>
            {/* ── Toggle button — always visible ────────────────────── */}
            <button
                id="btn-toggle-transcript"
                className={`${styles.toggleBtn} ${isOpen ? styles.toggleBtnOpen : ''}`}
                onClick={onToggle}
                title={isOpen ? 'Close transcript' : 'Open transcript'}
                aria-label={isOpen ? 'Close transcript' : 'Open transcript'}
            >
                <span className={styles.toggleIcon}>✦</span>
                {!isOpen && entries.length > 0 && (
                    <span className={styles.entryBadge}>{entries.length}</span>
                )}
            </button>

            {/* ── Panel ─────────────────────────────────────────────── */}
            <aside
                className={`${styles.panel} ${isOpen ? styles.panelOpen : ''}`}
                aria-label="Meeting transcript"
            >
                {/* Panel header */}
                <div className={styles.panelHeader}>
                    <div className={styles.panelTitleGroup}>
                        <span className={styles.panelIcon}>✦</span>
                        <span className={styles.panelTitle}>Live Transcript</span>
                        <span className={styles.liveChip}>
                            <span className={styles.liveDot} />
                            Live
                        </span>
                    </div>
                    <button
                        className={styles.closeBtn}
                        onClick={onToggle}
                        aria-label="Close transcript panel"
                    >
                        ✕
                    </button>
                </div>

                {/* Entry list */}
                <div className={styles.entryList}>
                    {entries.length === 0 ? (
                        <div className={styles.emptyState}>
                            <div className={styles.emptyIcon}>🎤</div>
                            <p className={styles.emptyTitle}>No transcript yet</p>
                            <p className={styles.emptyHint}>
                                Start speaking and the transcript will appear here in real time.
                            </p>
                        </div>
                    ) : (
                        entries.map((entry, idx) => {
                            const isLatest = idx === entries.length - 1;
                            const entryKey = entry.id ? `id-${entry.id}` : `${entry.timestamp}-${idx}`;
                            const isEditing = editingId === (entry.id || entry.timestamp);
                            
                            // Authorization: A participant can edit ONLY their own transcript entries.
                            const isOwn = entry.speaker_id
                                ? entry.speaker_id === participantId
                                : entry.speaker === localUserName;

                            return (
                                <div
                                    key={entryKey}
                                    className={`${styles.entry} ${isLatest && animateLast ? styles.entryNew : ''}`}
                                >
                                    <div className={styles.entryMeta}>
                                        <div className={styles.entrySpeakerGroup}>
                                            <span className={styles.entrySpeaker}>{entry.speaker}</span>
                                            {isOwn && !isEditing && entry.id && (
                                                <button
                                                    className={styles.editBtn}
                                                    onClick={() => handleStartEdit(entry)}
                                                    title="Edit your transcript entry"
                                                    aria-label="Edit transcript entry"
                                                >
                                                    ✎
                                                </button>
                                            )}
                                        </div>
                                        <span className={styles.entryTime}>{formatTime(entry.timestamp)}</span>
                                    </div>

                                    {isEditing ? (
                                        <div className={styles.editContainer}>
                                            <textarea
                                                className={styles.editInput}
                                                value={editText}
                                                onChange={(e) => setEditText(e.target.value)}
                                                rows={2}
                                            />
                                            {editError && <div className={styles.editError}>{editError}</div>}
                                            <div className={styles.editActions}>
                                                <button
                                                    className={styles.saveBtn}
                                                    onClick={() => handleSaveEdit(entry)}
                                                    disabled={isSaving}
                                                >
                                                    {isSaving ? 'Saving...' : 'Save'}
                                                </button>
                                                <button
                                                    className={styles.cancelBtn}
                                                    onClick={handleCancelEdit}
                                                    disabled={isSaving}
                                                >
                                                    Cancel
                                                </button>
                                            </div>
                                        </div>
                                    ) : (
                                        <p className={styles.entryText}>{entry.text}</p>
                                    )}
                                </div>
                            );
                        })
                    )}
                    <div ref={bottomRef} />
                </div>

                {/* Footer */}
                <div className={styles.panelFooter}>
                    <span className={styles.footerNote}>
                        {entries.length} entr{entries.length !== 1 ? 'ies' : 'y'}
                    </span>
                    <span className={styles.footerNote}>Powered by AI Meeting Assistant</span>
                </div>
            </aside>
        </>
    );
};

export default TranscriptPanel;

