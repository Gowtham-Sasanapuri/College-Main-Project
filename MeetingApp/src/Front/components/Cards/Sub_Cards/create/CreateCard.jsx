import React, { useRef, useState } from 'react';
import styles from './CreateCard.module.css';
import Cam from '../../assets/video-svgrepo-com.svg';
import link from '../../assets/link-svgrepo-com.svg';
import Copy from '../../assets/copy-4-svgrepo-com.svg';
import { useNavigate } from 'react-router-dom';

const CreateCard = ({ Create }) => {
    const nav = useNavigate();
    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [Agenda, setAgenda] = useState('');
    const [aiEnabled, setAiEnabled] = useState(false);
    const btn = useRef(null);
    const [meeting_id, setId] = useState('');

    const create = () => {
        if (!name.trim()) {
            alert('Please enter your name');
            return;
        }
        btn.current.disabled = true;
        fetch('http://127.0.0.1:8000/createLink/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, email: email.trim().toLowerCase(), Agenda, ai_enabled: aiEnabled }),
        })
            .then(response => response.json())

            .then(data => {
                if (data.success) {
                    setId(data.meeting_id);
                }
            })
            .catch(err => console.error(err))
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
                    <img className={styles.CamLogo} src={Cam} alt="Camera Icon" />
                </div>

                <div className={styles.Header}>
                    <h1>Create Meeting</h1>
                    <p>Start a new room and share the ID with participants.</p>
                </div>

                <div className={styles.NameContainer}>
                    <label className={styles.FieldLabel}>Your Name</label>
                    <input
                        type="text"
                        placeholder="Enter your name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                    />
                </div>

                <div className={styles.NameContainer}>
                    <label className={styles.FieldLabel}>Your Email (optional / for meeting reports)</label>
                    <input
                        type="email"
                        placeholder="e.g. yourname@example.com"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                    />
                </div>

                <div className={styles.NameContainer}>
                    <label className={styles.FieldLabel}>Meeting Agenda (optional)</label>
                    <textarea
                        placeholder="What is this meeting about?"
                        onChange={(e) => setAgenda(e.target.value)}
                        value={Agenda}
                        maxLength={200}
                    />
                </div>


                {/* ── AI Meeting Assistant opt-in ─────────────────────── */}
                <div className={`${styles.AiCard} ${aiEnabled ? styles.AiCardActive : ''}`}>
                    <div className={styles.AiCardHeader}>
                        <div className={styles.AiIconBadge}>
                            <span className={styles.AiIcon}>✦</span>
                        </div>
                        <div className={styles.AiTitleGroup}>
                            <span className={styles.AiTitle}>AI Meeting Assistant</span>
                            <span className={styles.AiBeta}>Beta</span>
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
                            <span>Live meeting transcription</span>
                        </div>
                        <div className={styles.AiFeatureItem}>
                            <span className={styles.AiFeatureDot} />
                            <span>Automatic meeting summary <span className={styles.Soon}>soon</span></span>
                        </div>
                        <div className={styles.AiFeatureItem}>
                            <span className={styles.AiFeatureDot} />
                            <span>AI follow-up questions <span className={styles.Soon}>soon</span></span>
                        </div>
                        <div className={styles.AiFeatureItem}>
                            <span className={styles.AiFeatureDot} />
                            <span>Downloadable meeting report (PDF) <span className={styles.Soon}>soon</span></span>
                        </div>
                    </div>

                    <p className={styles.AiDisclaimer}>
                        Audio will be processed only for meetings where AI is enabled.
                    </p>
                </div>
                {/* ────────────────────────────────────────────────────── */}

                <div className={styles.Quote}>
                    <p>"Great meetings start with a clear purpose."</p>
                    <p>Keep your team aligned and make every discussion count.</p>
                </div>

                {!meeting_id ? (
                    <div className={styles.LinkCreateContainer}>
                        <button ref={btn} onClick={create} className={styles.PrimaryBtn}>
                            <img className={styles.link} src={link} alt="" />
                            <span>Create Meeting Link</span>
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
                                nav(`/Meeting/${meeting_id}`, {
                                    state: { name, email, aiEnabled },
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

export default CreateCard;
