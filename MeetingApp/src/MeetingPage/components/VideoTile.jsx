import React, { useEffect, useRef, forwardRef } from 'react';
import styles from './VideoTile.module.css';

/**
 * VideoTile — renders a single participant's video feed with a clean status label.
 *
 * For the local tile, pass `externalRef` (from useWebRTC) so the hook can
 * assign srcObject directly. For remote tiles, pass `stream` as a prop.
 *
 * @param {MediaStream|null}  stream       - Remote stream to display
 * @param {string}            name         - Participant's display name
 * @param {boolean}           isLocal      - Whether this is the local user's tile
 * @param {boolean}           videoEnabled - For local tile avatar fallback
 * @param {React.Ref}         externalRef  - Forward ref for local video element
 */
const VideoTile = forwardRef(function VideoTile(
    { stream, name, isLocal = false, videoEnabled = true },
    externalRef
) {
    const internalRef = useRef(null);
    const videoRef = externalRef || internalRef;

    // Attach remote stream whenever it changes
    useEffect(() => {
        if (!isLocal && videoRef.current && stream) {
            if (videoRef.current.srcObject !== stream) {
                videoRef.current.srcObject = stream;
            }
            videoRef.current.play().catch(err => console.log('[VIDEO] Auto-play caught:', err));
        }
    }, [stream, isLocal, videoRef]);

    const initial = name ? name.trim().charAt(0).toUpperCase() : '?';

    return (
        <div className={`${styles.tile} ${isLocal ? styles.localTile : ''}`}>
            <video
                ref={videoRef}
                autoPlay
                playsInline
                muted={isLocal}
                className={styles.video}
            />

            {/* Avatar overlay when video is disabled */}
            {isLocal && !videoEnabled && (
                <div className={styles.avatarOverlay}>
                    <div className={styles.avatar}>
                        {initial}
                    </div>
                    <span className={styles.avatarName}>{name} (Camera off)</span>
                </div>
            )}

            <div className={styles.nameBar}>
                <div className={styles.nameBadge}>
                    {isLocal && <span className={styles.localDot} title="You" />}
                    <span className={styles.name}>
                        {name}{isLocal ? ' (You)' : ''}
                    </span>
                </div>
            </div>
        </div>
    );
});

export default VideoTile;
