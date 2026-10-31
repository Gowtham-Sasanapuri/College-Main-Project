import React, { useState } from 'react';
import styles from './Cards.module.css';
import user from './assets/two-user-svgrepo-com.svg';
import cam from './assets/video-svgrepo-com.svg';
import CreateCard from './Sub_Cards/create/CreateCard';
import CreateRoomCard from './Sub_Cards/create/CreateRoomCard';
import JoinMeet from './Sub_Cards/Join/JoinMeet';

const MeetingCards = () => {
    const [create, setCreate] = useState(false);
    const [createRoom, setCreateRoom] = useState(false);
    const [join, setJoin] = useState(false);

    return (
        <>
            {!create && !createRoom && !join && (
                <div className={styles.Container}>
                    {/* 1. Create Video Meeting */}
                    <div className={`${styles.Card} ${styles.CardVideo}`}>
                        <div className={styles.cardTop}>
                            <div className={styles.ImgContainer}>
                                <img className={styles.Cam} src={cam} alt="Video Camera" />
                            </div>
                            <span className={styles.badge}>Live WebRTC</span>
                        </div>
                        <div className={styles.CardInfo}>
                            <h3>Create Video Meeting</h3>
                        </div>
                        <div className={styles.CardSubContentContainer}>
                            <p>Direct browser-to-browser video call with live transcriptions and AI follow-up.</p>
                        </div>
                        <div className={styles.MeetingBtn}>
                            <button
                                type="button"
                                onClick={() => {
                                    setCreate(true);
                                    setCreateRoom(false);
                                    setJoin(false);
                                }}
                            >
                                Start Video Room →
                            </button>
                        </div>
                    </div>

                    {/* 2. Create Room Meeting */}
                    <div className={`${styles.Card} ${styles.CardRoom}`}>
                        <div className={styles.cardTop}>
                            <div className={`${styles.ImgContainer} ${styles.ImgContainerRoom}`}>
                                <span className={styles.roomIcon}>🎙️</span>
                            </div>
                            <span className={`${styles.badge} ${styles.badgeRoom}`}>In-Person Central Device</span>
                        </div>
                        <div className={styles.CardInfo}>
                            <h3>Create Room Meeting</h3>
                        </div>
                        <div className={styles.CardSubContentContainer}>
                            <p>Place a single device in the room. Automatically diarize speakers and transcribe.</p>
                        </div>
                        <div className={styles.MeetingBtn}>
                            <button
                                type="button"
                                className={styles.btnRoom}
                                onClick={() => {
                                    setCreateRoom(true);
                                    setCreate(false);
                                    setJoin(false);
                                }}
                            >
                                Setup Room Device →
                            </button>
                        </div>
                    </div>

                    {/* 3. Join Meeting */}
                    <div className={`${styles.Card} ${styles.CardJoin}`}>
                        <div className={styles.cardTop}>
                            <div className={`${styles.ImgContainer} ${styles.ImgContainerJoin}`}>
                                <img className={styles.Cam} src={user} alt="Participants" />
                            </div>
                            <span className={styles.badge}>Existing Session</span>
                        </div>
                        <div className={styles.CardInfo}>
                            <h3>Join Meeting</h3>
                        </div>
                        <div className={styles.CardSubContentContainer}>
                            <p>Enter an active meeting ID provided by the host to connect your audio and video.</p>
                        </div>
                        <div className={styles.MeetingBtn}>
                            <button
                                type="button"
                                className={styles.btnJoin}
                                onClick={() => {
                                    setJoin(true);
                                    setCreate(false);
                                    setCreateRoom(false);
                                }}
                            >
                                Join by ID →
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {create && !createRoom && !join && (
                <CreateCard Create={setCreate} />
            )}

            {createRoom && !create && !join && (
                <CreateRoomCard Create={setCreateRoom} />
            )}

            {!create && !createRoom && join && (
                <JoinMeet Join={setJoin} />
            )}
        </>
    );
};

export default MeetingCards;
