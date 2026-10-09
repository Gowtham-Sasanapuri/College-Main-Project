import React, { useRef, useState } from 'react';
import styles from './CreateCard.module.css';
import Cam from '../../assets/video-svgrepo-com.svg';
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
        alert('Meeting ID copied to clipboard!');
    };

    return (
        <div className={styles.Container}>
            <div className={styles.CreateWindow}>
                <div className={styles.CloseBtnContainer}>
                    <button className={styles.CloseBtn} onClick={() => Create(false)}>
                        ✕ Close
                    </button>
                </div>

                <div className={styles.CamImgContainer}>
                    <img className={styles.CamLogo} src={Cam} alt="Room Icon" />
                </div>

                <div className={styles.Header}>
                    <h1>Create Room Meeting</h1>
                    <p>In-person central device recording with speaker diarization & ASR.</p>
                </div>

                <div className={styles.NameContainer}>
                    <label className={styles.FieldLabel}>Meeting / Device Name (Optional)</label>
                    <input
                        type="text"
                        placeholder="e.g. Conference Room A"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                    />
                </div>

                <div className={styles.NameContainer}>
                    <label className={styles.FieldLabel}>Agenda (Optional)</label>
                    <textarea
                        placeholder="Discuss project architecture, deployment strategy and timeline..."
                        onChange={(e) => setAgenda(e.target.value)}
                        value={Agenda}
                        maxLength={200}
                    />
                </div>

                {/* AI Meeting Assistant opt-in */}
                <div className={`${styles.AiCard} ${aiEnabled ? styles.AiCardActive : ''}`}>
                    <div className={styles.AiCardHeader}>
                        <div className={styles.AiIconBadge}>
                            <span className={styles.AiIcon}>✦</span>
                        </div>
                        <div className={styles.AiTitleGroup}>
                            <span className={styles.AiTitle}>AI Meeting Assistant</span>
                            <span className={styles.AiBeta}>Qwen 2.5 7B</span>
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
                            <span>Speaker Diarization (Speaker_001, Speaker_002...)</span>
                        </div>
                        <div className={styles.AiFeatureItem}>
                            <span className={styles.AiFeatureDot} />
                            <span>Post-meeting Speech-to-Text</span>
                        </div>
                        <div className={styles.AiFeatureItem}>
                            <span className={styles.AiFeatureDot} />
                            <span>Editable transcript entries</span>
                        </div>
                        <div className={styles.AiFeatureItem}>
                            <span className={styles.AiFeatureDot} />
                            <span>Automatic Hugging Face Qwen 2.5 7B summary</span>
                        </div>
                    </div>

                    <p className={styles.AiDisclaimer}>
                        Full meeting audio is recorded and processed after the meeting ends.
                    </p>
                </div>

                <div className={styles.Quote}>
                    <p>"Great meetings start with a clear purpose."</p>
                    <p>Place the central device in the room and tap to start when ready.</p>
                </div>

                {!meeting_id ? (
                    <div className={styles.LinkCreateContainer}>
                        <button ref={btn} onClick={create} className={styles.PrimaryBtn}>
                            <img className={styles.link} src={link} alt="" />
                            <span>Create Room Meeting</span>
                        </button>
                    </div>
                ) : (
                    <div className={styles.MeetingIdContainer}>
                        <div className={styles.IDContent}>
                            <p className={styles.IdText}>
                                Meeting ID: <span className={styles.IdHighlight}>{meeting_id}</span>
                            </p>
                            <button className={styles.CopyBtn} onClick={Copy_Id} title="Copy ID">
                                <img className={styles.CopyIcon} src={Copy} alt="Copy" />
                            </button>
                        </div>
                        <button
                            className={styles.Meet}
                            onClick={() =>
                                nav(`/RoomMeeting/${meeting_id}`, {
                                    state: { name, agenda: Agenda, aiEnabled },
                                })
                            }
                        >
                            Enter Meeting →
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
};

export default CreateRoomCard;
