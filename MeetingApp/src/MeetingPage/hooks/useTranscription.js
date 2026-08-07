import { useEffect, useRef, useCallback } from 'react';

/**
 * useTranscription — wraps the browser-native SpeechRecognition API.
 *
 * Only activates when `aiEnabled` and `audioEnabled` are true AND the browser supports the API.
 * On each recognition result, calls `onResult(speaker, text)` which
 * routes through useWebRTC → WebSocket → backend → all participants.
 *
 * Each browser tab transcribes its own mic and broadcasts the result.
 * This keeps the architecture simple and engine-agnostic.
 *
 * @param {boolean}  aiEnabled    - Whether AI is enabled for this meeting
 * @param {boolean}  audioEnabled - Whether the local mic is unmuted
 * @param {string}   userName     - The local participant's display name (speaker label)
 * @param {Function} onResult     - Callback: (speaker: string, text: string) => void
 */
export function useTranscription(aiEnabled, audioEnabled, userName, onResult) {
    const recognitionRef = useRef(null);
    const isRunningRef = useRef(false);
    const onResultRef = useRef(onResult);

    // Keep onResult ref current without re-creating the effect
    useEffect(() => {
        onResultRef.current = onResult;
    }, [onResult]);

    const stopRecognition = useCallback(() => {
        if (recognitionRef.current) {
            isRunningRef.current = false;
            try {
                recognitionRef.current.stop();
            } catch (_) {
                // ignore if already stopped
            }
        }
    }, []);

    useEffect(() => {
        if (!aiEnabled || !audioEnabled) {
            stopRecognition();
            return;
        }

        // Check browser support
        const SpeechRecognition =
            window.SpeechRecognition || window.webkitSpeechRecognition;

        if (!SpeechRecognition) {
            console.warn(
                '[useTranscription] SpeechRecognition is not supported in this browser. ' +
                'Use Chrome or Edge for AI transcription.'
            );
            return;
        }

        const recognition = new SpeechRecognition();
        recognitionRef.current = recognition;

        // Configuration
        recognition.continuous = true;       // don't stop after each phrase
        recognition.interimResults = false;  // only emit final results
        recognition.lang = 'en-US';
        recognition.maxAlternatives = 1;

        recognition.onstart = () => {
            isRunningRef.current = true;
            console.log('[useTranscription] Started');
        };

        recognition.onresult = (event) => {
            // Collect all new final results from this batch
            for (let i = event.resultIndex; i < event.results.length; i++) {
                const result = event.results[i];
                if (result.isFinal) {
                    const text = result[0].transcript.trim();
                    if (text) {
                        console.log(`[useTranscription] "${text}"`);
                        onResultRef.current(userName, text);
                    }
                }
            }
        };

        recognition.onerror = (event) => {
            // 'no-speech' is harmless — just silence; restart below handles it
            if (event.error !== 'no-speech') {
                console.error('[useTranscription] Error:', event.error);
            }
        };

        recognition.onend = () => {
            // Auto-restart so recognition stays continuous across phrase gaps
            if (isRunningRef.current) {
                console.log('[useTranscription] Restarting...');
                try {
                    recognition.start();
                } catch (_) {
                    // may throw if already starting; safe to ignore
                }
            } else {
                console.log('[useTranscription] Stopped');
            }
        };

        // Start listening
        isRunningRef.current = true;
        try {
            recognition.start();
        } catch (err) {
            console.error('[useTranscription] Could not start:', err);
        }

        return () => {
            stopRecognition();
        };
    }, [aiEnabled, audioEnabled, userName, stopRecognition]);

    return { stopRecognition };
}
