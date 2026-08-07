import React, { useEffect, useRef, forwardRef } from 'react';
import styles from './VideoTile.module.css';

/**
 * VideoTile — renders a single participant's video feed with a name label.
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
            videoRef.current.srcObject = stream;
        }
    }, [stream, isLocal, videoRef]);

    return (
        <div className={`${styles.tile} ${isLocal ? styles.localTile : ''}`}>
            <video
                ref={videoRef}
                autoPlay
                playsInline
                muted={isLocal}
                className={styles.video}
            />

            {/* Avatar overlay when local video is disabled */}
            {isLocal && !videoEnabled && (
                <div className={styles.avatarOverlay}>
                    <div className={styles.avatar}>
                        {name?.charAt(0).toUpperCase()}
                    </div>
                </div>
            )}

            <div className={styles.nameBar}>
                <span className={styles.name}>
                    {name}{isLocal ? ' (You)' : ''}
                </span>
                {isLocal && <span className={styles.localBadge}>●</span>}
            </div>
        </div>
    );
});

export default VideoTile;
