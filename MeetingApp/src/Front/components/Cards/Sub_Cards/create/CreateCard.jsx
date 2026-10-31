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
    const [copied, setCopied] = useState(false);

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
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
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
                            <p className={styles.HeaderSub}>Configure host details and room options</p>
                        </div>
                    </div>
                    <button className={styles.CloseBtn} onClick={() => Create(false)} aria-label="Close dialog">
                        ✕
                    </button>
                </div>

                <div className={styles.formContent}>
                    <div className={styles.NameContainer}>
                        <label className={styles.FieldLabel} htmlFor="host-name">
                            Host Display Name <span className={styles.required}>*</span>
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
                            Host Email Address <span className={styles.optional}>(Optional / for reports)</span>
                        </label>
                        <input
                            id="host-email"
                            type="email"
                            placeholder="alex@company.com"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                        />
                    </div>

                    <div className={styles.NameContainer}>
                        <label className={styles.FieldLabel} htmlFor="meeting-agenda">
                            Meeting Agenda <span className={styles.optional}>(Optional)</span>
                        </label>
                        <textarea
                            id="meeting-agenda"
                            placeholder="Outline topics or primary goals for this session..."
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
                                <span className={styles.AiBeta}>Live Whisper</span>
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
                                <span>Real-time speech transcription & editable entries</span>
                            </div>
                            <div className={styles.AiFeatureItem}>
                                <span className={styles.AiFeatureDot} />
                                <span>Automated post-meeting summary & action items</span>
                            </div>
                            <div className={styles.AiFeatureItem}>
                                <span className={styles.AiFeatureDot} />
                                <span>Follow-up Q&A and PDF report generation</span>
                            </div>
                        </div>

                        <p className={styles.AiDisclaimer}>
                            Audio will only be transcribed when AI mode is enabled.
                        </p>
                    </div>

                    {!meeting_id ? (
                        <div className={styles.LinkCreateContainer}>
                            <button ref={btn} onClick={create} className={styles.PrimaryBtn}>
                                <img className={styles.link} src={link} alt="" />
                                <span>Generate Meeting Link</span>
                            </button>
                        </div>
                    ) : (
                        <div className={styles.MeetingIdContainer}>
                            <div className={styles.IDContent}>
                                <div className={styles.idInfo}>
                                    <span className={styles.idLabel}>Meeting ID:</span>
                                    <span className={styles.IdHighlight}>{meeting_id}</span>
                                </div>
                                <button className={styles.CopyBtn} onClick={Copy_Id} title="Copy ID">
                                    <img className={styles.CopyIcon} src={Copy} alt="" />
                                    <span>{copied ? 'Copied!' : 'Copy'}</span>
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
                                Enter Meeting Room →
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default CreateCard;
