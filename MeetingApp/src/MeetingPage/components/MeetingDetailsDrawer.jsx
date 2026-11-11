import React, { useEffect, useState } from 'react';
import styles from './MeetingDetailsDrawer.module.css';

const API_BASE = 'http://127.0.0.1:8000';

const MeetingDetailsDrawer = ({
    isOpen,
    onClose,
    meetingId,
    details = {},
    onUpdateAgendaItem,
}) => {
    const [elapsedSeconds, setElapsedSeconds] = useState(0);
    const [copiedLink, setCopiedLink] = useState(false);
    const [agendaList, setAgendaList] = useState(details.agenda_items || []);

    // Sync agenda items if details update
    useEffect(() => {
        if (details.agenda_items) {
            setAgendaList(details.agenda_items);
        }
    }, [details.agenda_items]);

    // Live timer calculation
    useEffect(() => {
        if (!isOpen) return;

        const startTime = details.actual_start_time
            ? new Date(details.actual_start_time).getTime()
            : Date.now();

        const updateTimer = () => {
            const now = Date.now();
            const diffSec = Math.max(0, Math.floor((now - startTime) / 1000));
            setElapsedSeconds(diffSec);
        };

        updateTimer();
        const interval = setInterval(updateTimer, 1000);
        return () => clearInterval(interval);
    }, [isOpen, details.actual_start_time]);

    if (!isOpen) return null;

    const formatTimer = (totalSeconds) => {
        const hrs = Math.floor(totalSeconds / 3600);
        const mins = Math.floor((totalSeconds % 3600) / 60);
        const secs = totalSeconds % 60;
        if (hrs > 0) {
            return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    };

    const meetingUrl = `${window.location.origin}/Meeting/${meetingId}`;

    const handleCopyUrl = () => {
        navigator.clipboard.writeText(meetingUrl);
        setCopiedLink(true);
        setTimeout(() => setCopiedLink(false), 2000);
    };

    const handleStatusChange = async (itemId, newStatus) => {
        // Optimistic UI update
        setAgendaList((prev) =>
            prev.map((item) => (item.id === itemId ? { ...item, status: newStatus } : item))
        );

        if (onUpdateAgendaItem) {
            onUpdateAgendaItem(itemId, newStatus);
        }

        try {
            await fetch(`${API_BASE}/meeting/agenda/${itemId}/`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: newStatus }),
            });
        } catch (err) {
            console.error('Failed to update agenda item status:', err);
        }
    };

    const isVideoMode = details.meeting_mode === 'video';

    return (
        <div className={styles.drawerOverlay} onClick={onClose} role="dialog" aria-modal="true">
            <div className={styles.drawer} onClick={(e) => e.stopPropagation()}>
                <div className={styles.drawerHeader}>
                    <div className={styles.titleGroup}>
                        <h3 className={styles.drawerTitle}>{details.title || 'Meeting Details & Agenda'}</h3>
                        <span className={styles.drawerSubtitle}>
                            {isVideoMode ? 'Online WebRTC Conference' : 'In-Room Diarized Session'}
                        </span>
                    </div>
                    <button className={styles.closeBtn} onClick={onClose} aria-label="Close details">
                        ✕
                    </button>
                </div>

                <div className={styles.drawerBody}>
                    {/* Live Timer Card */}
                    <div className={styles.timerCard}>
                        <div className={styles.timerLabelGroup}>
                            <div className={styles.liveIndicator}>
                                <span className={styles.pulseDot} />
                                <span>Session Live</span>
                            </div>
                            <span className={styles.timerSub}>
                                Scheduled: {details.expected_duration || '30 mins'}
                            </span>
                        </div>
                        <span className={styles.timerValue}>{formatTimer(elapsedSeconds)}</span>
                    </div>

                    {/* Venue & Connection Info */}
                    <div className={styles.venueCard}>
                        <div className={styles.venueHeader}>
                            <span>{isVideoMode ? '🔗 Meeting URL' : '📍 Physical Venue'}</span>
                            {isVideoMode && (
                                <button className={styles.copyLinkBtn} onClick={handleCopyUrl}>
                                    {copiedLink ? 'Copied!' : 'Copy Link'}
                                </button>
                            )}
                        </div>
                        <span className={styles.venueText}>
                            {isVideoMode ? meetingUrl : details.venue || 'Main Conference Room'}
                        </span>
                    </div>

                    {/* General Metadata Grid */}
                    <div className={styles.metaGrid}>
                        <div className={styles.metaRow}>
                            <span className={styles.metaLabel}>Organizer / Host:</span>
                            <span className={styles.metaVal}>{details.host_name || 'Organizer'}</span>
                        </div>
                        {details.scheduled_date && (
                            <div className={styles.metaRow}>
                                <span className={styles.metaLabel}>Scheduled Date:</span>
                                <span className={styles.metaVal}>{details.scheduled_date}</span>
                            </div>
                        )}
                        {details.scheduled_start_time && (
                            <div className={styles.metaRow}>
                                <span className={styles.metaLabel}>Scheduled Window:</span>
                                <span className={styles.metaVal}>
                                    {details.scheduled_start_time} - {details.scheduled_end_time || 'N/A'}
                                </span>
                            </div>
                        )}
                        <div className={styles.metaRow}>
                            <span className={styles.metaLabel}>Session Mode:</span>
                            <span className={styles.metaVal}>
                                {isVideoMode ? 'WebRTC Mesh Video' : 'Central Acoustic Diarization'}
                            </span>
                        </div>
                    </div>

                    {/* Structured Agenda Tracker */}
                    <div className={styles.agendaContainer}>
                        <div className={styles.agendaHeader}>
                            <span className={styles.agendaTitle}>Structured Agenda Items</span>
                            <span className={styles.agendaBadge}>
                                {agendaList.filter((a) => a.status === 'Completed').length}/{agendaList.length} Done
                            </span>
                        </div>

                        {agendaList.length === 0 ? (
                            <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', fontStyle: 'italic' }}>
                                No specific agenda items registered for this meeting.
                            </div>
                        ) : (
                            <div className={styles.agendaList}>
                                {agendaList.map((item, idx) => {
                                    const statusClass =
                                        item.status === 'Completed'
                                            ? styles.agendaItemCompleted
                                            : item.status === 'In Progress'
                                            ? styles.agendaItemActive
                                            : '';

                                    return (
                                        <div key={item.id || idx} className={`${styles.agendaItem} ${statusClass}`}>
                                            <div className={styles.agendaItemTop}>
                                                <span className={styles.agendaItemTitle}>
                                                    {idx + 1}. {item.title}
                                                </span>
                                            </div>

                                            <div className={styles.agendaMeta}>
                                                {item.presenter && <span>👤 {item.presenter}</span>}
                                                {item.expected_duration && <span>⏱️ {item.expected_duration}</span>}
                                            </div>

                                            {item.description && (
                                                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                                                    {item.description}
                                                </div>
                                            )}

                                            <div className={styles.statusPillGroup}>
                                                {['Pending', 'In Progress', 'Completed', 'Skipped'].map((st) => {
                                                    const isSelected = item.status === st;
                                                    const selectedClass = isSelected
                                                        ? st === 'Completed'
                                                            ? styles.statusPillSelectedCompleted
                                                            : st === 'In Progress'
                                                            ? styles.statusPillSelectedInProgress
                                                            : st === 'Skipped'
                                                            ? styles.statusPillSelectedSkipped
                                                            : styles.statusPillSelectedPending
                                                        : '';

                                                    return (
                                                        <button
                                                            key={st}
                                                            type="button"
                                                            className={`${styles.statusPill} ${selectedClass}`}
                                                            onClick={() => handleStatusChange(item.id, st)}
                                                        >
                                                            {st === 'Completed'
                                                                ? '✓ Done'
                                                                : st === 'In Progress'
                                                                ? '▶ In Progress'
                                                                : st}
                                                        </button>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default MeetingDetailsDrawer;

