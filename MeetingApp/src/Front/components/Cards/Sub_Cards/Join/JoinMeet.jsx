import React, { useState } from 'react';
import styles from './Join.module.css';
import People from '../../assets/two-user-svgrepo-com.svg';
import link from '../../assets/session-join-svgrepo-com.svg';
import { useNavigate } from 'react-router-dom';

const JoinMeet = ({ Join }) => {
    const nav = useNavigate();
    let [name, setName] = useState('');
    let [email, setEmail] = useState('');
    let [MeetLink, setMeetLink] = useState('');
    let [emailError, setEmailError] = useState('');

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
        <div className={styles.Container}>
            <div className={styles.CreateWindow}>
                <div className={styles.CloseBtnContainer}>
                    <button className={styles.CloseBtn} onClick={() => Join(false)}>
                        ✕ Close
                    </button>
                </div>

                <div className={styles.CamImgContainer}>
                    <img className={styles.CamLogo} src={People} alt="Join Icon" />
                </div>

                <div className={styles.Header}>
                    <h1>Join Meeting</h1>
                    <p>Enter the meeting ID provided by the host to join.</p>
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
                    <label className={styles.FieldLabel}>Your Email (for meeting reports)</label>
                    <input
                        type="email"
                        placeholder="e.g. yourname@example.com"
                        value={email}
                        onChange={(e) => {
                            setEmail(e.target.value);
                            if (emailError) setEmailError('');
                        }}
                    />
                    {emailError && <span className={styles.errorText}>{emailError}</span>}
                </div>

                <div className={styles.NameContainer}>
                    <label className={styles.FieldLabel}>Meeting ID</label>
                    <input
                        type="text"
                        placeholder="Paste or type meeting ID"
                        onChange={(e) => setMeetLink(e.target.value)}
                        value={MeetLink}
                    />
                </div>


                <div className={styles.Quote}>
                    <p>💡 Tip: Make sure you have the exact meeting ID.</p>
                    <p>You can get the ID from the meeting creator.</p>
                </div>

                <div className={styles.LinkCreateContainer}>
                    <button className={styles.PrimaryBtn} onClick={handleJoin}>
                        <img className={styles.link} src={link} alt="" />
                        <span>Join Meeting</span>
                    </button>
                </div>
            </div>
        </div>
    );
};

export default JoinMeet;
