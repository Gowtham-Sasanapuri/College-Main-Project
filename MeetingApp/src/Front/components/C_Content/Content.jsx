import React from 'react';
import styles from './Content.module.css';

const Content = () => {
    return (
        <section className={styles.Container}>
            <div className={styles.badge}>
                <span className={styles.badgeDot} />
                <span>WebRTC Conferencing & In-Person Diarization</span>
            </div>
            <div className={styles.heading}>
                <h1 className={styles.headingContent}>
                    Unified meetings with <span className={styles.inline}>built-in intelligence</span>
                </h1>
            </div>
            <div className={styles.SubContentContainer}>
                <p className={styles.SubContent}>
                    High-performance video rooms, automated speaker diarization, real-time transcription, and structured meeting reports.
                </p>
            </div>
        </section>
    );
};

export default Content;
