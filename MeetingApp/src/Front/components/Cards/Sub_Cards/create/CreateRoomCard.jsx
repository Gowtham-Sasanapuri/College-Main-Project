import React, { useRef, useState } from 'react';
import styles from './CreateCard.module.css';
import link from '../../assets/link-svgrepo-com.svg';
import Copy from '../../assets/copy-4-svgrepo-com.svg';
import { useNavigate } from 'react-router-dom';

const CreateRoomCard = ({ Create }) => {
    const nav = useNavigate();
    const [name, setName] = useState('');
    const [Agenda, setAgenda] = useState('');
    const [aiEnabled, setAiEnabled] = useState(false);
    const btn = useRef(null);
    const [meeting_id, setId] = useState('');
    const [copied, setCopied] = useState(false);

    const create = () => {
        btn.current.disabled = true;
        fetch('http://127.0.0.1:8000/roomMeeting/create/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name.trim() || 'Central Device', Agenda: Agenda.trim(), ai_enabled: aiEnabled }),
        })
            .then((response) => response.json())
            .then((data) => {
                if (data.success) {
                    setId(data.meeting_id);
                }
            })
            .catch((err) => console.error(err))
            .finally(() => {
                if (btn.current) btn.current.disabled = false;
            });
    };

    const Copy_Id = () => {
        navigator.clipboard.writeText(meeting_id);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
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
                            <h2 id="room-create-title" className={styles.HeaderTitle}>Create Room Meeting</h2>
                            <p className={styles.HeaderSub}>In-person recording with automated speaker diarization</p>
                        </div>
                    </div>
                    <button className={styles.CloseBtn} onClick={() => Create(false)} aria-label="Close dialog">
                        ✕
                    </button>
                </div>

                <div className={styles.formContent}>
                    <div className={styles.NameContainer}>
                        <label className={styles.FieldLabel} htmlFor="room-name">
                            Room or Device Identifier <span className={styles.optional}>(Optional)</span>
                        </label>
                        <input
                            id="room-name"
                            type="text"
                            placeholder="e.g. Conference Room 3B"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                        />
                    </div>

                    <div className={styles.NameContainer}>
                        <label className={styles.FieldLabel} htmlFor="room-agenda">
                            Meeting Agenda <span className={styles.optional}>(Optional)</span>
                        </label>
                        <textarea
                            id="room-agenda"
                            placeholder="Key topics to discuss in the room..."
                            onChange={(e) => setAgenda(e.target.value)}
                            value={Agenda}
                            maxLength={200}
                        />
                    </div>

                    {/* AI Meeting Assistant opt-in */}
                    <div className={`${styles.AiCard} ${aiEnabled ? styles.AiCardActive : ''}`}>
                        <div className={styles.AiCardHeader}>
                            <div className={styles.AiIconBadge}>✦</div>
                            <div className={styles.AiTitleGroup}>
                                <span className={styles.AiTitle}>AI Meeting Assistant</span>
                                <span className={styles.AiBeta}>Pyannote & Whisper</span>
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
                                <span>Complete meeting diarization and timeline segmentation</span>
                            </div>
                            <div className={styles.AiFeatureItem}>
                                <span className={styles.AiFeatureDot} />
                                <span>Automatic summary, action points, and PDF report delivery</span>
                            </div>
                        </div>

                        <p className={styles.AiDisclaimer}>
                            Audio is processed securely upon ending the in-room recording session.
                        </p>
                    </div>

                    {!meeting_id ? (
                        <div className={styles.LinkCreateContainer}>
                            <button ref={btn} onClick={create} className={`${styles.PrimaryBtn} ${styles.roomPrimaryBtn}`}>
                                <img className={styles.link} src={link} alt="" />
                                <span>Initialize Room Session</span>
                            </button>
                        </div>
                    ) : (
                        <div className={styles.MeetingIdContainer}>
                            <div className={styles.IDContent}>
                                <div className={styles.idInfo}>
                                    <span className={styles.idLabel}>Room Session ID:</span>
                                    <span className={styles.IdHighlight}>{meeting_id}</span>
                                </div>
                                <button className={styles.CopyBtn} onClick={Copy_Id} title="Copy ID">
                                    <img className={styles.CopyIcon} src={Copy} alt="" />
                                    <span>{copied ? 'Copied!' : 'Copy'}</span>
                                </button>
                            </div>
                            <button
                                className={`${styles.Meet} ${styles.roomPrimaryBtn}`}
                                onClick={() =>
                                    nav(`/RoomMeeting/${meeting_id}`, {
                                        state: { name, agenda: Agenda, aiEnabled },
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
