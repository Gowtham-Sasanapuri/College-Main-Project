import React, { useRef, useState } from 'react';
import styles from './CreateCard.module.css';
import Cam from '../../assets/video-svgrepo-com.svg';
import link from '../../assets/link-svgrepo-com.svg';
import Copy from '../../assets/copy-4-svgrepo-com.svg';
import { useNavigate } from 'react-router-dom';
import { API_BASE } from '../../../../../config';

const CreateCard = ({ Create }) => {
    const nav = useNavigate();
    const [creationMode, setCreationMode] = useState('instant'); // 'instant' | 'schedule'
    const [title, setTitle] = useState('');
    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [description, setDescription] = useState('');
    const [scheduledDate, setScheduledDate] = useState(() => {
        const d = new Date();
        return d.toISOString().split('T')[0];
    });
    const [scheduledStartTime, setScheduledStartTime] = useState(() => {
        const d = new Date();
        d.setMinutes(d.getMinutes() + 10);
        return d.toTimeString().substring(0, 5);
    });
    const [scheduledEndTime, setScheduledEndTime] = useState(() => {
        const d = new Date();
        d.setMinutes(d.getMinutes() + 40);
        return d.toTimeString().substring(0, 5);
    });
    const [expectedDuration, setExpectedDuration] = useState('30 mins');
    const [aiEnabled, setAiEnabled] = useState(false);

    // Dynamic agenda items list
    const [agendaItems, setAgendaItems] = useState([
        { title: 'Project Status & Key Milestones', presenter: '', expected_duration: '10 mins', description: '' },
    ]);

    const btn = useRef(null);
    const [meeting_id, setId] = useState('');
    const [copiedId, setCopiedId] = useState(false);
    const [copiedUrl, setCopiedUrl] = useState(false);

    const handleAddAgendaItem = () => {
        setAgendaItems((prev) => [
            ...prev,
            { title: '', presenter: name || '', expected_duration: '15 mins', description: '' },
        ]);
    };

    const handleUpdateAgendaItem = (index, field, value) => {
        setAgendaItems((prev) => {
            const next = [...prev];
            next[index] = { ...next[index], [field]: value };
            return next;
        });
    };

    const handleRemoveAgendaItem = (index) => {
        setAgendaItems((prev) => prev.filter((_, idx) => idx !== index));
    };

    const handleMoveAgendaItem = (index, direction) => {
        setAgendaItems((prev) => {
            const next = [...prev];
            const targetIndex = index + direction;
            if (targetIndex < 0 || targetIndex >= next.length) return prev;
            const temp = next[index];
            next[index] = next[targetIndex];
            next[targetIndex] = temp;
            return next;
        });
    };

    const handleCreate = () => {
        if (!name.trim()) {
            alert('Please enter your host display name');
            return;
        }

        if (btn.current) btn.current.disabled = true;

        const payload = {
            name: name.trim(),
            email: email.trim().toLowerCase(),
            title: title.trim() || `${name.trim()}'s Video Meeting`,
            description: description.trim(),
            Agenda: agendaItems.map((a) => a.title).filter(Boolean).join('; ') || 'General Discussion',
            venue: 'Online (WebRTC Video Room)',
            scheduled_date: scheduledDate,
            scheduled_start_time: scheduledStartTime,
            scheduled_end_time: scheduledEndTime,
            expected_duration: expectedDuration,
            ai_enabled: aiEnabled,
            auto_start: creationMode === 'instant',
            agenda_items: agendaItems.filter((a) => a.title.trim() !== ''),
        };

        fetch(`${API_BASE}/createLink/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
            .then((res) => res.json())
            .then((data) => {
                if (data.success) {
                    setId(data.meeting_id);
                } else {
                    alert(data.message || 'Failed to create meeting.');
                }
            })
            .catch((err) => {
                console.error(err);
                alert('Connection error while creating meeting.');
            })
            .finally(() => {
                if (btn.current) btn.current.disabled = false;
            });
    };

    const meetingUrl = meeting_id ? `${window.location.origin}/Meeting/${meeting_id}` : '';

    const handleCopyId = () => {
        navigator.clipboard.writeText(meeting_id);
        setCopiedId(true);
        setTimeout(() => setCopiedId(false), 2000);
    };

    const handleCopyUrl = () => {
        navigator.clipboard.writeText(meetingUrl);
        setCopiedUrl(true);
        setTimeout(() => setCopiedUrl(false), 2000);
    };

    return (
        <div className={styles.Container} role="dialog" aria-modal="true" aria-labelledby="create-title">
            <div className={styles.CreateWindow}>
                <div className={styles.modalTopBar}>
                    <div className={styles.modalTitleGroup}>
                        <div className={styles.CamImgContainer}>
                            <img className={styles.CamLogo} src={Cam} alt="" />
                        </div>
                        <div>
                            <h2 id="create-title" className={styles.HeaderTitle}>Create Video Meeting</h2>
                            <p className={styles.HeaderSub}>WebRTC online conference with live AI transcription</p>
                        </div>
                    </div>
                    <button className={styles.CloseBtn} onClick={() => Create(false)} aria-label="Close dialog">
                        ✕
                    </button>
                </div>

                <div className={styles.formContent}>
                    {/* Creation Mode Toggle */}
                    <div className={styles.tabRow}>
                        <button
                            type="button"
                            className={`${styles.tabBtn} ${creationMode === 'instant' ? styles.tabBtnActive : ''}`}
                            onClick={() => setCreationMode('instant')}
                        >
                            ⚡ Start Meeting Now
                        </button>
                        <button
                            type="button"
                            className={`${styles.tabBtn} ${creationMode === 'schedule' ? styles.tabBtnActive : ''}`}
                            onClick={() => setCreationMode('schedule')}
                        >
                            📅 Schedule for Later
                        </button>
                    </div>

                    {/* Meeting Title */}
                    <div className={styles.NameContainer}>
                        <label className={styles.FieldLabel} htmlFor="meeting-title">
                            Meeting Title <span className={styles.optional}>(Optional)</span>
                        </label>
                        <input
                            id="meeting-title"
                            type="text"
                            placeholder="e.g. Weekly Engineering Sync"
                            value={title}
                            onChange={(e) => setTitle(e.target.value)}
                        />
                    </div>

                    {/* Host Name & Email */}
                    <div className={styles.grid2}>
                        <div className={styles.NameContainer}>
                            <label className={styles.FieldLabel} htmlFor="host-name">
                                Organizer / Host <span className={styles.required}>*</span>
                            </label>
                            <input
                                id="host-name"
                                type="text"
                                placeholder="e.g. Alex Rivera"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                            />
                        </div>
                        <div className={styles.NameContainer}>
                            <label className={styles.FieldLabel} htmlFor="host-email">
                                Organizer Email <span className={styles.optional}>(For reports)</span>
                            </label>
                            <input
                                id="host-email"
                                type="email"
                                placeholder="alex@company.com"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                            />
                        </div>
                    </div>

                    {/* Scheduling Fields (if Schedule mode or for duration metadata) */}
                    <div className={styles.grid2}>
                        <div className={styles.NameContainer}>
                            <label className={styles.FieldLabel} htmlFor="sched-date">
                                Meeting Date
                            </label>
                            <input
                                id="sched-date"
                                type="date"
                                value={scheduledDate}
                                onChange={(e) => setScheduledDate(e.target.value)}
                            />
                        </div>
                        <div className={styles.NameContainer}>
                            <label className={styles.FieldLabel} htmlFor="exp-dur">
                                Expected Duration
                            </label>
                            <input
                                id="exp-dur"
                                type="text"
                                placeholder="e.g. 45 mins"
                                value={expectedDuration}
                                onChange={(e) => setExpectedDuration(e.target.value)}
                            />
                        </div>
                    </div>

                    {creationMode === 'schedule' && (
                        <div className={styles.grid2}>
                            <div className={styles.NameContainer}>
                                <label className={styles.FieldLabel} htmlFor="sched-start">
                                    Start Time
                                </label>
                                <input
                                    id="sched-start"
                                    type="time"
                                    value={scheduledStartTime}
                                    onChange={(e) => setScheduledStartTime(e.target.value)}
                                />
                            </div>
                            <div className={styles.NameContainer}>
                                <label className={styles.FieldLabel} htmlFor="sched-end">
                                    End Time
                                </label>
                                <input
                                    id="sched-end"
                                    type="time"
                                    value={scheduledEndTime}
                                    onChange={(e) => setScheduledEndTime(e.target.value)}
                                />
                            </div>
                        </div>
                    )}

                    {/* Description */}
                    <div className={styles.NameContainer}>
                        <label className={styles.FieldLabel} htmlFor="meeting-desc">
                            Description / Context <span className={styles.optional}>(Optional)</span>
                        </label>
                        <input
                            id="meeting-desc"
                            type="text"
                            placeholder="Brief context or goals for this session..."
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                        />
                    </div>

                    {/* Structured Agenda Builder */}
                    <div className={styles.agendaSection}>
                        <div className={styles.agendaSectionHeader}>
                            <span className={styles.agendaSectionTitle}>Meeting Agenda Items ({agendaItems.length})</span>
                            <button
                                type="button"
                                className={styles.addItemBtn}
                                onClick={handleAddAgendaItem}
                            >
                                + Add Topic
                            </button>
                        </div>

                        <div className={styles.agendaItemsList}>
                            {agendaItems.map((item, idx) => (
                                <div key={idx} className={styles.agendaItemCard}>
                                    <div className={styles.agendaItemTop}>
                                        <span className={styles.itemOrderBadge}>{idx + 1}</span>
                                        <input
                                            type="text"
                                            className={styles.agendaItemTitleInput}
                                            placeholder={`Agenda item #${idx + 1} title...`}
                                            value={item.title}
                                            onChange={(e) => handleUpdateAgendaItem(idx, 'title', e.target.value)}
                                        />
                                        <div className={styles.itemControls}>
                                            <button
                                                type="button"
                                                className={styles.iconBtn}
                                                disabled={idx === 0}
                                                onClick={() => handleMoveAgendaItem(idx, -1)}
                                                title="Move Up"
                                            >
                                                ▲
                                            </button>
                                            <button
                                                type="button"
                                                className={styles.iconBtn}
                                                disabled={idx === agendaItems.length - 1}
                                                onClick={() => handleMoveAgendaItem(idx, 1)}
                                                title="Move Down"
                                            >
                                                ▼
                                            </button>
                                            <button
                                                type="button"
                                                className={`${styles.iconBtn} ${styles.iconBtnDanger}`}
                                                onClick={() => handleRemoveAgendaItem(idx)}
                                                title="Remove Item"
                                            >
                                                ✕
                                            </button>
                                        </div>
                                    </div>
                                    <div className={styles.agendaItemDetails}>
                                        <input
                                            type="text"
                                            className={styles.smallInput}
                                            placeholder="Presenter (optional)"
                                            value={item.presenter}
                                            onChange={(e) => handleUpdateAgendaItem(idx, 'presenter', e.target.value)}
                                        />
                                        <input
                                            type="text"
                                            className={styles.smallInput}
                                            placeholder="Duration (e.g. 10m)"
                                            value={item.expected_duration}
                                            onChange={(e) => handleUpdateAgendaItem(idx, 'expected_duration', e.target.value)}
                                        />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* AI Meeting Assistant opt-in */}
                    <div className={`${styles.AiCard} ${aiEnabled ? styles.AiCardActive : ''}`}>
                        <div className={styles.AiCardHeader}>
                            <div className={styles.AiIconBadge}>✦</div>
                            <div className={styles.AiTitleGroup}>
                                <span className={styles.AiTitle}>AI Meeting Assistant & MoM</span>
                                <span className={styles.AiBeta}>Live Whisper + Gemini 2.5</span>
                            </div>
                            <label className={styles.Toggle} htmlFor="ai-toggle" aria-label="Enable AI Meeting Assistant">
                                <input
                                    id="ai-toggle"
                                    type="checkbox"
                                    checked={aiEnabled}
                                    onChange={(e) => setAiEnabled(e.target.checked)}
                                />
                                <span className={styles.ToggleSlider} />
                            </label>
                        </div>

                        <div className={styles.AiFeatureList}>
                            <div className={styles.AiFeatureItem}>
                                <span className={styles.AiFeatureDot} />
                                <span>Real-time speech transcription & live agenda tracking</span>
                            </div>
                            <div className={styles.AiFeatureItem}>
                                <span className={styles.AiFeatureDot} />
                                <span>Automated 10-section Minutes of Meeting (MoM) generation</span>
                            </div>
                            <div className={styles.AiFeatureItem}>
                                <span className={styles.AiFeatureDot} />
                                <span>Action items table, follow-up Q&A, and PDF export</span>
                            </div>
                        </div>
                    </div>

                    {!meeting_id ? (
                        <div className={styles.LinkCreateContainer}>
                            <button ref={btn} onClick={handleCreate} className={styles.PrimaryBtn}>
                                <img className={styles.link} src={link} alt="" />
                                <span>{creationMode === 'instant' ? 'Launch Meeting Room Now' : 'Schedule Video Meeting'}</span>
                            </button>
                        </div>
                    ) : (
                        <div className={styles.MeetingIdContainer}>
                            <div className={styles.urlBox}>
                                <div className={styles.idInfo}>
                                    <span className={styles.idLabel}>Link:</span>
                                    <span className={styles.urlText}>{meetingUrl}</span>
                                </div>
                                <button className={styles.CopyBtn} onClick={handleCopyUrl} title="Copy Meeting URL">
                                    <img className={styles.CopyIcon} src={Copy} alt="" />
                                    <span>{copiedUrl ? 'Copied!' : 'Copy Link'}</span>
                                </button>
                            </div>

                            <div className={styles.IDContent}>
                                <div className={styles.idInfo}>
                                    <span className={styles.idLabel}>Meeting ID:</span>
                                    <span className={styles.IdHighlight}>{meeting_id}</span>
                                </div>
                                <button className={styles.CopyBtn} onClick={handleCopyId} title="Copy ID">
                                    <img className={styles.CopyIcon} src={Copy} alt="" />
                                    <span>{copiedId ? 'Copied!' : 'Copy ID'}</span>
                                </button>
                            </div>

                            <button
                                className={styles.Meet}
                                onClick={() =>
                                    nav(`/Meeting/${meeting_id}`, {
                                        state: { name, email, aiEnabled },
                                    })
                                }
                            >
                                Enter Meeting Room Now →
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default CreateCard;
