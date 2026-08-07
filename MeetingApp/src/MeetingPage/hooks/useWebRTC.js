import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

const ICE_SERVERS = {
    iceServers: [
        { urls: 'stun:stun.l.google.com:19302' },
        { urls: 'stun:stun1.l.google.com:19302' },
    ],
};

/**
 * useWebRTC — manages all WebRTC and WebSocket logic for a multi-user meeting.
 *
 * @param {string}  meetingId        - The meeting room ID from the URL
 * @param {string}  userName         - The local participant's display name
 * @param {boolean} initialAiEnabled - Hint from location.state (host only).
 *                                     The authoritative value always comes from
 *                                     the JoinMeeting API response and is stored
 *                                     in aiEnabledRef so it is available to the
 *                                     WS onmessage closure without re-creating it.
 * @returns hook state and controls
 */
export function useWebRTC(meetingId, userName, initialAiEnabled = false) {
    const navigate = useNavigate();

    // ── Refs (stable across renders) ──────────────────────────────────
    const localVideoRef         = useRef(null);
    const localStream           = useRef(null);
    const localStreamPromiseRef = useRef(null);
    const socket                = useRef(null);
    /** @type {React.MutableRefObject<Map<string, RTCPeerConnection>>} */
    const peerConnections       = useRef(new Map());

    // Unique, stable participant session ID for edit authorization
    const participantIdRef      = useRef(
        typeof crypto !== 'undefined' && crypto.randomUUID
            ? crypto.randomUUID()
            : 'p_' + Math.random().toString(36).substring(2) + Date.now().toString(36)
    );

    // ── Runtime AI flag ───────────────────────────────────────────────
    const aiEnabledRef = useRef(initialAiEnabled);

    // ── State (drives re-render) ───────────────────────────────────────
    const [remoteStreams,    setRemoteStreams]    = useState([]);
    const [participants,     setParticipants]     = useState([]);
    const [videoEnabled,     setVideoEnabled]     = useState(true);
    const [audioEnabled,     setAudioEnabled]     = useState(true);
    const [connectionStatus, setConnectionStatus] = useState('connecting');

    // meetingAiEnabled — the server-confirmed value exposed to the UI.
    const [meetingAiEnabled, setMeetingAiEnabled] = useState(initialAiEnabled);

    // Transcript entries — populated for ALL participants when the meeting has AI on.
    const [transcriptEntries, setTranscriptEntries] = useState([]);
    const [isMeetingEnded,    setIsMeetingEnded]    = useState(false);


    // ── Local media ───────────────────────────────────────────────────

    const getLocalStream = useCallback(async () => {
        if (localStream.current) return localStream.current;
        if (localStreamPromiseRef.current) return localStreamPromiseRef.current;

        localStreamPromiseRef.current = (async () => {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
                localStream.current = stream;
                if (localVideoRef.current) {
                    localVideoRef.current.srcObject = stream;
                }
                return stream;
            } finally {
                localStreamPromiseRef.current = null;
            }
        })();

        return localStreamPromiseRef.current;
    }, []);

    // Ensure local video element stays connected to localStream even after re-renders
    useEffect(() => {
        if (localStream.current && localVideoRef.current && !localVideoRef.current.srcObject) {
            localVideoRef.current.srcObject = localStream.current;
        }
    });

    const tryGetLocalStream = useCallback(async () => {
        try {
            return await getLocalStream();
        } catch (err) {
            console.warn(
                '[MEDIA] Could not acquire camera/microphone:', err.message,
                '— joining as audio/video-off participant.'
            );
            setVideoEnabled(false);
            setAudioEnabled(false);
            return null;
        }
    }, [getLocalStream]);

    // ── Peer connection factory ───────────────────────────────────────

    const createPeerConnection = useCallback((remoteName) => {
        if (peerConnections.current.has(remoteName)) {
            return peerConnections.current.get(remoteName);
        }

        const pc = new RTCPeerConnection(ICE_SERVERS);

        pc.onicecandidate = (event) => {
            if (event.candidate && socket.current?.readyState === WebSocket.OPEN) {
                socket.current.send(JSON.stringify({
                    message: 'Candidate',
                    sender:   userName,
                    receiver: remoteName,
                    candidate: event.candidate,
                }));
            }
        };

        pc.ontrack = (event) => {
            const stream = (event.streams && event.streams[0]) ? event.streams[0] : new MediaStream([event.track]);
            setRemoteStreams(prev => {
                const exists = prev.some(s => s.name === remoteName);
                if (exists) {
                    return prev.map(s =>
                        s.name === remoteName ? { name: remoteName, stream } : s
                    );
                }
                return [...prev, { name: remoteName, stream }];
            });
        };

        pc.onconnectionstatechange = () => {
            console.log(`[PC:${remoteName}] state=${pc.connectionState}`);
        };

        peerConnections.current.set(remoteName, pc);
        return pc;
    }, [userName]);

    // ── Add local stream tracks to a peer connection ──────────────────

    const addLocalTracks = useCallback((pc) => {
        if (localStream.current) {
            localStream.current.getTracks().forEach(track => {
                const senders = pc.getSenders();
                const exists = senders.some(s => s.track === track);
                if (!exists) {
                    pc.addTrack(track, localStream.current);
                }
            });
        } else {
            const transceivers = pc.getTransceivers();
            const hasAudio = transceivers.some(t => t.receiver.track?.kind === 'audio' || t.mid?.includes('audio'));
            const hasVideo = transceivers.some(t => t.receiver.track?.kind === 'video' || t.mid?.includes('video'));

            if (!hasAudio) {
                try { pc.addTransceiver('audio', { direction: 'recvonly' }); } catch (_) {}
            }
            if (!hasVideo) {
                try { pc.addTransceiver('video', { direction: 'recvonly' }); } catch (_) {}
            }
        }
    }, []);

    // ── Offer / Answer / Candidate ────────────────────────────────────

    const sendOffer = useCallback(async (remoteName) => {
        await tryGetLocalStream();
        const pc = createPeerConnection(remoteName);
        addLocalTracks(pc);

        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        socket.current.send(JSON.stringify({
            message:  'Offer',
            sender:   userName,
            receiver: remoteName,
            PeerOffer: offer,
        }));

        console.log(`[OFFER SENT] ${userName} → ${remoteName}`);
    }, [userName, tryGetLocalStream, createPeerConnection, addLocalTracks]);

    const handleIncomingOffer = useCallback(async ({ sender, PeerOffer }) => {
        console.log(`[OFFER RECEIVED] from ${sender}`);
        await tryGetLocalStream();
        const pc = createPeerConnection(sender);
        addLocalTracks(pc);

        await pc.setRemoteDescription(new RTCSessionDescription(PeerOffer));
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);

        socket.current.send(JSON.stringify({
            message:  'Answer',
            sender:   userName,
            receiver: sender,
            answer,
        }));
    }, [userName, tryGetLocalStream, createPeerConnection, addLocalTracks]);

    const handleIncomingAnswer = useCallback(async ({ sender, answer }) => {
        console.log(`[ANSWER RECEIVED] from ${sender}`);
        const pc = peerConnections.current.get(sender);
        if (!pc) return;
        await pc.setRemoteDescription(new RTCSessionDescription(answer));
    }, []);

    const handleIncomingCandidate = useCallback(async ({ sender, candidate }) => {
        const pc = peerConnections.current.get(sender);
        if (!pc) return;
        try {
            await pc.addIceCandidate(new RTCIceCandidate(candidate));
        } catch (err) {
            console.error('[ICE] Failed to add candidate:', err);
        }
    }, []);

    // ── Participant management ────────────────────────────────────────

    const addParticipant = useCallback((name) => {
        setParticipants(prev => prev.includes(name) ? prev : [...prev, name]);
    }, []);

    const removeParticipant = useCallback((name) => {
        const pc = peerConnections.current.get(name);
        if (pc) {
            pc.close();
            peerConnections.current.delete(name);
        }
        setRemoteStreams(prev => prev.filter(s => s.name !== name));
        setParticipants(prev => prev.filter(p => p !== name));
    }, []);

    // ── Transcript helpers ────────────────────────────────────────────

    const sendTranscriptEntry = useCallback((speaker, text) => {
        if (!aiEnabledRef.current) return;
        if (socket.current?.readyState !== WebSocket.OPEN) return;
        socket.current.send(JSON.stringify({
            message:    'Transcript',
            speaker,
            speaker_id: participantIdRef.current,
            text,
            timestamp:  new Date().toISOString(),
        }));
    }, []);

    const loadTranscriptHistory = useCallback((entries) => {
        if (!Array.isArray(entries) || entries.length === 0) return;
        setTranscriptEntries(entries.map(e => ({
            id:         e.id,
            speaker:    e.speaker,
            speaker_id: e.speaker_id || '',
            text:       e.text,
            timestamp:  e.timestamp,
        })));
    }, []);

    // ── WebSocket ─────────────────────────────────────────────────────

    const openSocket = useCallback((transcriptHistory) => {
        const ws = new WebSocket(`ws://127.0.0.1:8000/ws/Meeting/${meetingId}`);
        socket.current = ws;

        ws.onopen = () => {
            console.log('[WS] Connected');
            setConnectionStatus('connected');
            ws.send(JSON.stringify({ message: 'Join', name: userName }));
        };

        ws.onerror = (err) => {
            console.error('[WS] Error:', err);
            setConnectionStatus('error');
        };

        ws.onclose = () => {
            console.log('[WS] Closed');
        };

        ws.onmessage = async (event) => {
            const data = JSON.parse(event.data);
            console.log('[WS] Message:', data.message, data);

            switch (data.message) {
                case 'NewPeer':
                    addParticipant(data.name);
                    await sendOffer(data.name);
                    break;

                case 'Offer':
                    addParticipant(data.sender);
                    await handleIncomingOffer(data);
                    break;

                case 'Answer':
                    await handleIncomingAnswer(data);
                    break;

                case 'Candidate':
                    await handleIncomingCandidate(data);
                    break;

                case 'Leave':
                    removeParticipant(data.name);
                    break;

                case 'Transcript':
                    if (aiEnabledRef.current) {
                        setTranscriptEntries(prev => [
                            ...prev,
                            {
                                id:         data.id,
                                speaker:    data.speaker,
                                speaker_id: data.speaker_id || '',
                                text:       data.text,
                                timestamp:  data.timestamp,
                            },
                        ]);
                    }
                    break;

                case 'TranscriptUpdate':
                    if (aiEnabledRef.current && data.id) {
                        setTranscriptEntries(prev => prev.map(e =>
                            e.id === data.id ? { ...e, text: data.text } : e
                        ));
                    }
                    break;

                case 'MeetingEnded':
                    console.log('[WS] Meeting ended by host');
                    setIsMeetingEnded(true);
                    break;

                default:
                    console.warn('[WS] Unknown message type:', data.message);
            }

        };

        if (aiEnabledRef.current && Array.isArray(transcriptHistory) && transcriptHistory.length > 0) {
            loadTranscriptHistory(transcriptHistory);
        }
    }, [
        meetingId,
        userName,
        addParticipant,
        removeParticipant,
        sendOffer,
        handleIncomingOffer,
        handleIncomingAnswer,
        handleIncomingCandidate,
        loadTranscriptHistory,
    ]);


    // ── Controls ──────────────────────────────────────────────────────

    const toggleVideo = useCallback(() => {
        if (!localStream.current) return;
        const track = localStream.current.getVideoTracks()[0];
        if (track) {
            track.enabled = !track.enabled;
            setVideoEnabled(track.enabled);
        }
    }, []);

    const toggleAudio = useCallback(() => {
        if (!localStream.current) return;
        const track = localStream.current.getAudioTracks()[0];
        if (track) {
            track.enabled = !track.enabled;
            setAudioEnabled(track.enabled);
        }
    }, []);

    const hangUp = useCallback(() => {
        localStream.current?.getTracks().forEach(t => t.stop());
        peerConnections.current.forEach(pc => pc.close());
        peerConnections.current.clear();
        socket.current?.close();
        navigate(-1);
    }, [navigate]);

    // ── Lifecycle ─────────────────────────────────────────────────────

    useEffect(() => {
        fetch('http://127.0.0.1:8000/JoinMeeting/', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ id: meetingId }),
        })
            .then(r => r.json())
            .then(data => {
                if (!data.success) {
                    navigate(-1);
                } else {
                    // ── FIX: set the runtime AI flag from the server response ──
                    //
                    // The server (models.py Meeting.ai_enabled) is the single source
                    // of truth. We write it to:
                    //   1. aiEnabledRef.current — read synchronously by the WS
                    //      onmessage closure and sendTranscriptEntry without needing
                    //      those callbacks to be recreated.
                    //   2. setMeetingAiEnabled — triggers a React re-render so the
                    //      UI (TranscriptPanel, AI badge, useTranscription) responds.
                    //
                    // This is done BEFORE openSocket() is called, so by the time the
                    // first Transcript WS message arrives, the ref already has the
                    // correct value for every participant — host or joiner.
                    const serverAiEnabled = data.ai_enabled === true;
                    aiEnabledRef.current = serverAiEnabled;
                    setMeetingAiEnabled(serverAiEnabled);

                    // ── Decouple signaling from media acquisition ────────────
                    //
                    // tryGetLocalStream() is awaited BEFORE openSocket() so that:
                    //   1. Local media state is fully established before WebRTC
                    //      signaling (Join → NewPeer → Offer/Answer) begins.
                    //   2. tryGetLocalStream() catches permission denials gracefully
                    //      and returns null (never rejects/throws), so awaiting it
                    //      NEVER blocks or hangs the meeting join flow.
                    //   3. Whether media is granted or denied, openSocket() connects
                    //      cleanly and WebRTC SDP offers/answers are formed correctly.
                    tryGetLocalStream().then(() => {
                        openSocket(data.transcript || []);
                    });
                }
            })
            .catch(err => {
                console.error('[FETCH] JoinMeeting failed:', err);
                setConnectionStatus('error');
            });

        return () => {
            localStream.current?.getTracks().forEach(t => t.stop());
            peerConnections.current.forEach(pc => pc.close());
            peerConnections.current.clear();
            socket.current?.close();
            localStream.current = null;
            socket.current      = null;
        };
    }, [meetingId, navigate, tryGetLocalStream, openSocket]);

    return {
        localVideoRef,
        remoteStreams,
        participants,
        videoEnabled,
        audioEnabled,
        connectionStatus,
        toggleVideo,
        toggleAudio,
        hangUp,
        // Transcript
        transcriptEntries,
        sendTranscriptEntry,
        // Expose the server-confirmed flag so Meeting.jsx can drive all rendering
        // decisions from it instead of from location.state.aiEnabled
        meetingAiEnabled,
        participantId: participantIdRef.current,
        isMeetingEnded,
    };
}


