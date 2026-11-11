import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import styles from './MeetingListHistory.module.css';

const API_BASE = 'http://127.0.0.1:8000';

const MeetingListHistory = () => {
    const nav = useNavigate();
    const [meetings, setMeetings] = useState([]);
    const [loading, setLoading] = useState(true);
    const [modeFilter, setModeFilter] = useState('all');
    const [statusFilter, setStatusFilter] = useState('all');
    const [searchQuery, setSearchQuery] = useState('');
    const [dateFilter, setDateFilter] = useState('');

    const fetchMeetings = async () => {
        setLoading(true);
        try {
            const params = new URLSearchParams();
            if (modeFilter !== 'all') params.append('mode', modeFilter);
            if (statusFilter !== 'all') params.append('status', statusFilter);
            if (searchQuery.trim()) params.append('search', searchQuery.trim());
            if (dateFilter) params.append('date', dateFilter);

            const res = await fetch(`${API_BASE}/meeting/list/?${params.toString()}`);
            const data = await res.json();
            if (data.success && Array.isArray(data.meetings)) {
                setMeetings(data.meetings);
            }
        } catch (err) {
            console.error('Failed to fetch meeting list:', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchMeetings();
    }, [modeFilter, statusFilter, dateFilter]);

    // Debounced search
    useEffect(() => {
        const timer = setTimeout(() => {
            fetchMeetings();
        }, 300);
        return () => clearTimeout(timer);
    }, [searchQuery]);

    const handleStartMeeting = async (m) => {
        try {
            await fetch(`${API_BASE}/meeting/start/${m.meeting_id}/`, {
                method: 'POST',
            });
            if (m.meeting_mode === 'room') {
                nav(`/RoomMeeting/${m.meeting_id}`, {
                    state: { name: m.host_name, aiEnabled: m.ai_enabled },
                });
            } else {
                nav(`/Meeting/${m.meeting_id}`, {
                    state: { name: m.host_name, aiEnabled: m.ai_enabled },
                });
            }
        } catch (err) {
            console.error('Error starting meeting:', err);
        }
    };

    const handleCancelMeeting = async (meetingId) => {
        if (!window.confirm('Are you sure you want to cancel this meeting?')) return;
        try {
            const res = await fetch(`${API_BASE}/meeting/cancel/${meetingId}/`, {
                method: 'POST',
            });
            const data = await res.json();
            if (data.success) {
                fetchMeetings();
            } else {
                alert(data.message || 'Could not cancel meeting.');
            }
        } catch (err) {
            console.error('Cancel error:', err);
        }
    };

    const renderStatusBadge = (status) => {
        switch (status) {
            case 'scheduled':
                return (
                    <span className={`${styles.statusBadge} ${styles.statusScheduled}`}>
                        <span>⏳</span> Scheduled
                    </span>
                );
            case 'in_progress':
                return (
                    <span className={`${styles.statusBadge} ${styles.statusInProgress}`}>
                        <span className={styles.pulseDot} />
                        In Progress
                    </span>
                );
            case 'completed':
                return (
                    <span className={`${styles.statusBadge} ${styles.statusCompleted}`}>
                        <span>✓</span> Completed
                    </span>
                );
            case 'cancelled':
                return (
                    <span className={`${styles.statusBadge} ${styles.statusCancelled}`}>
                        <span>✕</span> Cancelled
                    </span>
                );
            default:
                return null;
        }
    };

    return (
        <section className={styles.container}>
            <div className={styles.sectionHeader}>
                <div className={styles.titleGroup}>
                    <h2 className={styles.heading}>Meeting Sessions & History</h2>
                    <span className={styles.subheading}>
                        Monitor scheduled appointments, live calls, and archived Minutes of Meeting (MoM)
                    </span>
                </div>
            </div>

            {/* Filter Controls */}
            <div className={styles.filterBar}>
                <div className={styles.searchRow}>
                    <input
                        type="text"
                        className={styles.searchInput}
                        placeholder="Search meetings by title, organizer, or venue..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                    />
                    <input
                        type="date"
                        className={styles.dateInput}
                        value={dateFilter}
                        onChange={(e) => setDateFilter(e.target.value)}
                        title="Filter by scheduled date"
                    />
                    {dateFilter && (
                        <button
                            type="button"
                            className={styles.filterPill}
                            onClick={() => setDateFilter('')}
                        >
                            Clear Date
                        </button>
                    )}
                </div>

                <div className={styles.pillRow}>
                    {/* Mode Filters */}
                    <div className={styles.pillGroup}>
                        <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: '600' }}>
                            TYPE:
                        </span>
                        {[
                            { key: 'all', label: 'All Modes' },
                            { key: 'video', label: '📹 Online Video' },
                            { key: 'room', label: '🎙️ In-Room' },
                        ].map((btn) => (
                            <button
                                key={btn.key}
                                type="button"
                                className={`${styles.filterPill} ${modeFilter === btn.key ? styles.filterPillActive : ''}`}
                                onClick={() => setModeFilter(btn.key)}
                            >
                                {btn.label}
                            </button>
                        ))}
                    </div>

                    {/* Status Filters */}
                    <div className={styles.pillGroup}>
                        <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: '600' }}>
                            STATUS:
                        </span>
                        {[
                            { key: 'all', label: 'All' },
                            { key: 'scheduled', label: 'Scheduled' },
                            { key: 'in_progress', label: 'In Progress' },
                            { key: 'completed', label: 'Completed' },
                            { key: 'cancelled', label: 'Cancelled' },
                        ].map((btn) => (
                            <button
                                key={btn.key}
                                type="button"
                                className={`${styles.filterPill} ${statusFilter === btn.key ? styles.filterPillActive : ''}`}
                                onClick={() => setStatusFilter(btn.key)}
                            >
                                {btn.label}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* Meetings Cards */}
            {loading ? (
                <div className={styles.emptyState}>Loading meeting sessions...</div>
            ) : meetings.length === 0 ? (
                <div className={styles.emptyState}>
                    No meetings found matching the selected filters.
                </div>
            ) : (
                <div className={styles.meetingsList}>
                    {meetings.map((m) => {
                        const isVideo = m.meeting_mode === 'video';
                        const isScheduled = m.lifecycle_status === 'scheduled';
                        const isInProgress = m.lifecycle_status === 'in_progress';
                        const isCompleted = m.lifecycle_status === 'completed';
                        const isCancelled = m.lifecycle_status === 'cancelled';

                        return (
                            <div key={m.meeting_id} className={styles.card}>
                                <div className={styles.cardTop}>
                                    <span className={styles.modeBadge}>
                                        {isVideo ? '📹 Online Call' : '🎙️ In-Room'}
                                    </span>
                                    {renderStatusBadge(m.lifecycle_status)}
                                </div>

                                <div className={styles.cardBody}>
                                    <h3 className={styles.cardTitle}>{m.title}</h3>

                                    <div className={styles.cardMetaRow}>
                                        <span>👤 Host:</span>
                                        <span style={{ fontWeight: '600', color: 'var(--text-primary)' }}>
                                            {m.host_name || 'Organizer'}
                                        </span>
                                    </div>

                                    {m.scheduled_date && (
                                        <div className={styles.cardMetaRow}>
                                            <span>📅 Date:</span>
                                            <span>
                                                {m.scheduled_date}{' '}
                                                {m.scheduled_start_time ? `@ ${m.scheduled_start_time}` : ''}
                                            </span>
                                        </div>
                                    )}

                                    <div className={styles.cardMetaRow}>
                                        <span>📍 Venue:</span>
                                        <span className={styles.venueText}>{m.venue || 'Online Room'}</span>
                                    </div>

                                    {m.expected_duration && (
                                        <div className={styles.cardMetaRow}>
                                            <span>⏱️ Duration:</span>
                                            <span>
                                                {isCompleted && m.actual_duration_seconds > 0
                                                    ? `${Math.floor(m.actual_duration_seconds / 60)}m ${m.actual_duration_seconds % 60}s (Actual)`
                                                    : m.expected_duration}
                                            </span>
                                        </div>
                                    )}

                                    {m.agenda_items_count > 0 && (
                                        <div className={styles.cardMetaRow}>
                                            <span>📋 Agenda:</span>
                                            <span>{m.agenda_items_count} topic(s)</span>
                                        </div>
                                    )}
                                </div>

                                <div className={styles.cardFooter}>
                                    {isScheduled && (
                                        <>
                                            <button
                                                type="button"
                                                className={`${styles.btnAction} ${styles.btnPrimary}`}
                                                onClick={() => handleStartMeeting(m)}
                                            >
                                                ▶ Start Meeting
                                            </button>
                                            <button
                                                type="button"
                                                className={`${styles.btnAction} ${styles.btnDanger}`}
                                                onClick={() => handleCancelMeeting(m.meeting_id)}
                                            >
                                                Cancel
                                            </button>
                                        </>
                                    )}

                                    {isInProgress && (
                                        <button
                                            type="button"
                                            className={`${styles.btnAction} ${styles.btnSuccess}`}
                                            onClick={() =>
                                                nav(
                                                    isVideo
                                                        ? `/Meeting/${m.meeting_id}`
                                                        : `/RoomMeeting/${m.meeting_id}`,
                                                    { state: { name: m.host_name, aiEnabled: m.ai_enabled } }
                                                )
                                            }
                                        >
                                            🟢 Join Live Session
                                        </button>
                                    )}

                                    {isCompleted && (
                                        <>
                                            <button
                                                type="button"
                                                className={`${styles.btnAction} ${styles.btnPrimary}`}
                                                onClick={() => nav(`/MeetingSummary/${m.meeting_id}`)}
                                            >
                                                📄 View MoM / Report
                                            </button>
                                        </>
                                    )}

                                    {isCancelled && (
                                        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                                            Meeting cancelled
                                        </span>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </section>
    );
};

export default MeetingListHistory;

