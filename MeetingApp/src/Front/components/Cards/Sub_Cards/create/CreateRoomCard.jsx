import React, { useRef, useState } from 'react';
import styles from './CreateCard.module.css';
import link from '../../assets/link-svgrepo-com.svg';
import Copy from '../../assets/copy-4-svgrepo-com.svg';
import { useNavigate } from 'react-router-dom';
import { API_BASE } from '../../../../../config';

const CreateRoomCard = ({ Create }) => {
    const nav = useNavigate();
    const [creationMode, setCreationMode] = useState('instant'); // 'instant' | 'schedule'
    const [title, setTitle] = useState('');
    const [name, setName] = useState('');
    const [building, setBuilding] = useState('');
    const [floor, setFloor] = useState('');
    const [roomNumber, setRoomNumber] = useState('');
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
        d.setMinutes(d.getMinutes() + 55);
        return d.toTimeString().substring(0, 5);
    });
    const [expectedDuration, setExpectedDuration] = useState('45 mins');
    const [aiEnabled, setAiEnabled] = useState(false);

    // Dynamic agenda items list
    const [agendaItems, setAgendaItems] = useState([
        { title: 'Opening Remarks & Strategic Priorities', presenter: '', expected_duration: '15 mins', description: '' },
    ]);

    const btn = useRef(null);
    const [meeting_id, setId] = useState('');
    const [copiedId, setCopiedId] = useState(false);

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
        if (btn.current) btn.current.disabled = true;

        const venueParts = [
            roomNumber.trim() ? `Room: ${roomNumber.trim()}` : '',
            floor.trim() ? `Floor: ${floor.trim()}` : '',
            building.trim() ? `Building: ${building.trim()}` : '',
        ].filter(Boolean);

        const venueString = venueParts.length > 0 ? venueParts.join(', ') : 'Main Conference Room';

        const payload = {
            name: name.trim() || 'Central Device',
            title: title.trim() || `${name.trim() || 'Room'} Session`,
            description: description.trim(),
            venue: venueString,
            Agenda: agendaItems.map((a) => a.title).filter(Boolean).join('; ') || 'In-Room Discussion',
            scheduled_date: scheduledDate,
            scheduled_start_time: scheduledStartTime,
            scheduled_end_time: scheduledEndTime,
            expected_duration: expectedDuration,
            ai_enabled: aiEnabled,
            auto_start: creationMode === 'instant',
            agenda_items: agendaItems.filter((a) => a.title.trim() !== ''),
        };

        fetch(`${API_BASE}/roomMeeting/create/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
            .then((res) => res.json())
            .then((data) => {
                if (data.success) {
                    setId(data.meeting_id);
                } else {
                    alert(data.message || 'Failed to create room meeting.');
                }
            })
            .catch((err) => {
                console.error(err);
                alert('Connection error while creating room meeting.');
            })
            .finally(() => {
                if (btn.current) btn.current.disabled = false;
            });
    };

    const handleCopyId = () => {
        navigator.clipboard.writeText(meeting_id);
        setCopiedId(true);
        setTimeout(() => setCopiedId(false), 2000);
    };

    return (
        <div className={styles.Container} role="dialog" aria-modal="true" aria-labelledby="room-create-title">
            <div className={styles.CreateWindow}>
                <div className={styles.modalTopBar}>
                    <div className={styles.modalTitleGroup}>
                        <div className={`${styles.CamImgContainer} ${styles.roomDeviceBadge}`}>
                            <span className={styles.roomIcon}>🎙️</span>
                        </div>
                        <div>
                            <h2 id="room-create-title" className={styles.HeaderTitle}>Create In-Room Meeting</h2>
                            <p className={styles.HeaderSub}>Central microphone with speaker diarization & minutes</p>
                        </div>
                    </div>
                    <button className={styles.CloseBtn} onClick={() => Create(false)} aria-label="Close dialog">
                        ✕
                    </button>
                </div>

                <div className={styles.formContent}>
                    {/* Mode Toggle */}
                    <div className={styles.tabRow}>
                        <button
                            type="button"
                            className={`${styles.tabBtn} ${creationMode === 'instant' ? styles.tabBtnActive : ''}`}
                            onClick={() => setCreationMode('instant')}
                        >
                            🎙️ Record In-Room Now
                        </button>
                        <button
                            type="button"
                            className={`${styles.tabBtn} ${creationMode === 'schedule' ? styles.tabBtnActive : ''}`}
                            onClick={() => setCreationMode('schedule')}
                        >
                            📅 Schedule Room Session
                        </button>
                    </div>

                    {/* Meeting Title & Host/Device Name */}
                    <div className={styles.grid2}>
                        <div className={styles.NameContainer}>
                            <label className={styles.FieldLabel} htmlFor="room-title">
                                Meeting Title <span className={styles.optional}>(Optional)</span>
                            </label>
                            <input
                                id="room-title"
                                type="text"
                                placeholder="e.g. Executive Board Review"
                                value={title}
                                onChange={(e) => setTitle(e.target.value)}
                            />
                        </div>
                        <div className={styles.NameContainer}>
                            <label className={styles.FieldLabel} htmlFor="room-name">
                                Device / Host Name
                            </label>
                            <input
                                id="room-name"
                                type="text"
                                placeholder="e.g. Central Device 01"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                            />
                        </div>
                    </div>

                    {/* Physical Venue Management */}
                    <div className={styles.agendaSection}>
                        <span className={styles.agendaSectionTitle}>Physical Venue Location</span>
                        <div className={styles.grid2}>
                            <input
                                type="text"
                                className={styles.smallInput}
                                placeholder="Building (e.g. Tower A)"
                                value={building}
                                onChange={(e) => setBuilding(e.target.value)}
                            />
                            <input
                                type="text"
                                className={styles.smallInput}
                                placeholder="Floor (e.g. 4th Floor)"
                                value={floor}
                                onChange={(e) => setFloor(e.target.value)}
                            />
                        </div>
                        <input
                            type="text"
                            className={styles.smallInput}
                            placeholder="Room Number / Name (e.g. Boardroom 402)"
                            value={roomNumber}
                            onChange={(e) => setRoomNumber(e.target.value)}
                        />
                    </div>

                    {/* Scheduling & Timing */}
                    <div className={styles.grid2}>
                        <div className={styles.NameContainer}>
                            <label className={styles.FieldLabel} htmlFor="room-date">
                                Date
                            </label>
                            <input
                                id="room-date"
                                type="date"
                                value={scheduledDate}
                                onChange={(e) => setScheduledDate(e.target.value)}
                            />
                        </div>
                        <div className={styles.NameContainer}>
                            <label className={styles.FieldLabel} htmlFor="room-exp-dur">
                                Expected Duration
                            </label>
                            <input
                                id="room-exp-dur"
                                type="text"
                                placeholder="e.g. 60 mins"
                                value={expectedDuration}
                                onChange={(e) => setExpectedDuration(e.target.value)}
                            />
                        </div>
                    </div>

                    {creationMode === 'schedule' && (
                        <div className={styles.grid2}>
                            <div className={styles.NameContainer}>
                                <label className={styles.FieldLabel} htmlFor="room-start">
                                    Start Time
                                </label>
                                <input
                                    id="room-start"
                                    type="time"
                                    value={scheduledStartTime}
                                    onChange={(e) => setScheduledStartTime(e.target.value)}
                                />
                            </div>
                            <div className={styles.NameContainer}>
                                <label className={styles.FieldLabel} htmlFor="room-end">
                                    End Time
                                </label>
                                <input
                                    id="room-end"
                                    type="time"
                                    value={scheduledEndTime}
                                    onChange={(e) => setScheduledEndTime(e.target.value)}
                                />
                            </div>
                        </div>
                    )}

                    {/* Description */}
                    <div className={styles.NameContainer}>
                        <label className={styles.FieldLabel} htmlFor="room-desc">
                            Description / Context <span className={styles.optional}>(Optional)</span>
                        </label>
                        <input
                            id="room-desc"
                            type="text"
                            placeholder="Goals or context for the in-room attendees..."
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                        />
                    </div>

                    {/* Structured Agenda Items Builder */}
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
                                            placeholder="Duration (e.g. 15m)"
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
                                <span className={styles.AiBeta}>Pyannote & Whisper + Gemini</span>
                            </div>
                            <label className={styles.Toggle} htmlFor="ai-room-toggle" aria-label="Enable AI Meeting Assistant">
                                <input
                                    id="ai-room-toggle"
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
                                <span>Voice-matched speaker identification (Pinecone vector matching)</span>
                            </div>
                            <div className={styles.AiFeatureItem}>
                                <span className={styles.AiFeatureDot} />
                                <span>Acoustic diarization and structured timeline segmentation</span>
                            </div>
                            <div className={styles.AiFeatureItem}>
                                <span className={styles.AiFeatureDot} />
                                <span>Official 10-section Minutes of Meeting (MoM) & PDF distribution</span>
                            </div>
                        </div>
                    </div>

                    {!meeting_id ? (
                        <div className={styles.LinkCreateContainer}>
                            <button ref={btn} onClick={handleCreate} className={`${styles.PrimaryBtn} ${styles.roomPrimaryBtn}`}>
                                <img className={styles.link} src={link} alt="" />
                                <span>{creationMode === 'instant' ? 'Initialize Room Session Now' : 'Schedule In-Room Session'}</span>
                            </button>
                        </div>
                    ) : (
                        <div className={styles.MeetingIdContainer}>
                            <div className={styles.IDContent}>
                                <div className={styles.idInfo}>
                                    <span className={styles.idLabel}>Session ID:</span>
                                    <span className={styles.IdHighlight}>{meeting_id}</span>
                                </div>
                                <button className={styles.CopyBtn} onClick={handleCopyId} title="Copy ID">
                                    <img className={styles.CopyIcon} src={Copy} alt="" />
                                    <span>{copiedId ? 'Copied!' : 'Copy ID'}</span>
                                </button>
                            </div>
                            <button
                                className={`${styles.Meet} ${styles.roomPrimaryBtn}`}
                                onClick={() =>
                                    nav(`/RoomMeeting/${meeting_id}`, {
                                        state: { name, agenda: agendaItems.map((a) => a.title).join('; '), aiEnabled },
                                    })
                                }
                            >
                                Open Room Console →
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default CreateRoomCard;
