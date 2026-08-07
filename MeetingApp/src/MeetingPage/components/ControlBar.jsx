import React from 'react';
import styles from './ControlBar.module.css';

/* ── SVG Icons (inline — no extra assets needed) ── */

const MicOnIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
        <path d="M12 1a4 4 0 0 1 4 4v7a4 4 0 0 1-8 0V5a4 4 0 0 1 4-4zm-1.5 18.93A8.001 8.001 0 0 1 4 12H2a10 10 0 0 0 9 9.95V24h2v-2.05A10 10 0 0 0 22 12h-2a8 8 0 0 1-6.5 7.93V20h-1v-.07z" />
    </svg>
);

const MicOffIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
        <path d="M3.41 1.59L2 3l6 6v3a4 4 0 0 0 5.91 3.51l1.49 1.49A6 6 0 0 1 6 12H4a8 8 0 0 0 6.5 7.93V22H8v2h8v-2h-2.5v-2.07A10 10 0 0 0 22 12h-2a8 8 0 0 1-1.93 5.24l-1.43-1.43A6 6 0 0 0 18 12v-1l-6-6V3A4 4 0 0 0 8 3a3.94 3.94 0 0 0-.17.59L3.41 1.59zM16 12a4 4 0 0 1-6 3.46V12h2V9.41l4 4V12z" />
    </svg>
);

const CamOnIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
        <path d="M15 8v8H5V8h10m1-2H4a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3.5l4 4V6.5l-4 4V7a1 1 0 0 0-1-1z" />
    </svg>
);

const CamOffIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
        <path d="M3.41 1.59L2 3l2.29 2.29A1 1 0 0 0 4 6v10a1 1 0 0 0 1 1h12c.18 0 .35-.05.5-.13L20 20l1.41-1.41L3.41 1.59zM5 15V8.41l8.59 8.59H5zm15-1.5l-4-4V7a1 1 0 0 0-1-1H7.41l-2-2H16a1 1 0 0 1 1 1v3.5l4-4v11l-1-.97V13.5z" />
    </svg>
);

const HangUpIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="22" height="22">
        <path d="M12 9c-1.6 0-3.15.25-4.6.72v3.1c0 .39-.23.74-.56.9-.98.49-1.87 1.12-2.66 1.85-.18.18-.43.28-.7.28-.28 0-.53-.11-.71-.29L.29 13.08A.996.996 0 0 1 0 12.37c0-.28.11-.53.29-.71C3.34 8.77 7.46 7 12 7s8.66 1.77 11.71 4.66c.18.18.29.43.29.71 0 .28-.11.53-.29.71l-2.48 2.48a.997.997 0 0 1-.71.29c-.27 0-.52-.1-.7-.28a11.27 11.27 0 0 0-2.67-1.85.998.998 0 0 1-.56-.9v-3.1C15.15 9.25 13.6 9 12 9z" />
    </svg>
);

/**
 * ControlBar — fixed bottom bar with camera, mic, and leave controls.
 */
const ControlBar = ({
    videoEnabled,
    audioEnabled,
    onToggleVideo,
    onToggleAudio,
    onHangUp,
    participantCount,
}) => {
    return (
        <div className={styles.bar}>
            {/* Left: meeting info */}
            <div className={styles.info}>
                <span className={styles.dot} />
                <span className={styles.count}>
                    {participantCount} participant{participantCount !== 1 ? 's' : ''}
                </span>
            </div>

            {/* Center: controls */}
            <div className={styles.controls}>
                <button
                    id="btn-toggle-mic"
                    className={`${styles.btn} ${!audioEnabled ? styles.off : ''}`}
                    onClick={onToggleAudio}
                    title={audioEnabled ? 'Mute microphone' : 'Unmute microphone'}
                    aria-label={audioEnabled ? 'Mute microphone' : 'Unmute microphone'}
                >
                    {audioEnabled ? <MicOnIcon /> : <MicOffIcon />}
                </button>

                <button
                    id="btn-toggle-cam"
                    className={`${styles.btn} ${!videoEnabled ? styles.off : ''}`}
                    onClick={onToggleVideo}
                    title={videoEnabled ? 'Turn off camera' : 'Turn on camera'}
                    aria-label={videoEnabled ? 'Turn off camera' : 'Turn on camera'}
                >
                    {videoEnabled ? <CamOnIcon /> : <CamOffIcon />}
                </button>

                <button
                    id="btn-hang-up"
                    className={`${styles.btn} ${styles.hangUp}`}
                    onClick={onHangUp}
                    title="Leave meeting"
                    aria-label="Leave meeting"
                >
                    <HangUpIcon />
                </button>
            </div>

            {/* Right: spacer to keep controls centered */}
            <div className={styles.rightSpacer} />
        </div>
    );
};

export default ControlBar;
