import React, { useState } from 'react';
import styles from './Join.module.css';
import People from '../../assets/two-user-svgrepo-com.svg';
import link from '../../assets/session-join-svgrepo-com.svg';
import { useNavigate } from 'react-router-dom';

const JoinMeet = ({ Join }) => {
    const nav = useNavigate();
    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [MeetLink, setMeetLink] = useState('');
    const [emailError, setEmailError] = useState('');

    const validateEmailFormat = (val) => {
        const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return regex.test(val.trim());
    };

    const handleJoin = () => {
        if (!name.trim()) {
            alert('Please enter your name');
            return;
        }
        if (!email.trim()) {
            setEmailError('Please enter your email address');
            return;
        }
        if (!validateEmailFormat(email)) {
            setEmailError('Please enter a valid email address (e.g. name@example.com)');
            return;
        }
        setEmailError('');
        if (!MeetLink.trim()) {
            alert('Please enter a valid Meeting ID');
            return;
        }
        nav(`/Meeting/${MeetLink.trim()}`, {
            state: { name: name.trim(), email: email.trim().toLowerCase() },
        });
    };

    return (
        <div className={styles.Container} role="dialog" aria-modal="true" aria-labelledby="join-title">
            <div className={styles.CreateWindow}>
                <div className={styles.modalTopBar}>
                    <div className={styles.modalTitleGroup}>
                        <div className={styles.CamImgContainer}>
                            <img className={styles.CamLogo} src={People} alt="" />
                        </div>
                        <div>
                            <h2 id="join-title" className={styles.HeaderTitle}>Join Meeting</h2>
                            <p className={styles.HeaderSub}>Connect to an existing conference session</p>
                        </div>
                    </div>
                    <button className={styles.CloseBtn} onClick={() => Join(false)} aria-label="Close dialog">
                        ✕
                    </button>
                </div>

                <div className={styles.formContent}>
                    <div className={styles.NameContainer}>
                        <label className={styles.FieldLabel} htmlFor="join-name">
                            Your Name <span className={styles.required}>*</span>
                        </label>
                        <input
                            id="join-name"
                            type="text"
                            placeholder="e.g. Jordan Lee"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                        />
                    </div>

                    <div className={styles.NameContainer}>
                        <label className={styles.FieldLabel} htmlFor="join-email">
                            Your Email <span className={styles.required}>*</span> <span className={styles.optional}>(for reports & summaries)</span>
                        </label>
                        <input
                            id="join-email"
                            type="email"
                            placeholder="jordan@company.com"
                            value={email}
                            onChange={(e) => {
                                setEmail(e.target.value);
                                if (emailError) setEmailError('');
                            }}
                        />
                        {emailError && <span className={styles.errorText}>{emailError}</span>}
                    </div>

                    <div className={styles.NameContainer}>
                        <label className={styles.FieldLabel} htmlFor="join-meeting-id">
                            Meeting ID <span className={styles.required}>*</span>
                        </label>
                        <input
                            id="join-meeting-id"
                            type="text"
                            placeholder="Paste meeting UUID or code"
                            onChange={(e) => setMeetLink(e.target.value)}
                            value={MeetLink}
                        />
                    </div>

                    <div className={styles.tipBox}>
                        <span className={styles.tipIcon}>ℹ</span>
                        <p className={styles.tipText}>
                            Meeting IDs are provided by the session host. Make sure to paste the exact code.
                        </p>
                    </div>

                    <div className={styles.LinkCreateContainer}>
                        <button className={styles.PrimaryBtn} onClick={handleJoin}>
                            <img className={styles.link} src={link} alt="" />
                            <span>Connect to Meeting</span>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default JoinMeet;
