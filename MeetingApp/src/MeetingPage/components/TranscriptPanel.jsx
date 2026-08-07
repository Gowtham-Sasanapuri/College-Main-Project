import React, { useEffect, useRef, useState } from 'react';
import styles from './TranscriptPanel.module.css';

/**
 * TranscriptPanel — collapsible right-side panel displaying live meeting transcript.
 *
 * @param {Array}    entries    - [{ speaker, text, timestamp }]
 * @param {boolean}  isOpen     - Controlled open/close state
 * @param {Function} onToggle   - Called when the toggle button is clicked
 */
const TranscriptPanel = ({ entries = [], isOpen, onToggle }) => {
    const bottomRef = useRef(null);
    const [animateLast, setAnimateLast] = useState(false);

    // Auto-scroll to the latest entry
    useEffect(() => {
        if (isOpen && bottomRef.current) {
            bottomRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [entries, isOpen]);

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
                            return (
                                <div
                                    key={`${entry.timestamp}-${idx}`}
                                    className={`${styles.entry} ${isLatest && animateLast ? styles.entryNew : ''}`}
                                >
                                    <div className={styles.entryMeta}>
                                        <span className={styles.entrySpeaker}>{entry.speaker}</span>
                                        <span className={styles.entryTime}>{formatTime(entry.timestamp)}</span>
                                    </div>
                                    <p className={styles.entryText}>{entry.text}</p>
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
