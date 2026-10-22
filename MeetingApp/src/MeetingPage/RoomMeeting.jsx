import React, { useState, useRef, useEffect } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import FollowUpChat from './components/FollowUpChat';
import { generateMeetingPdfReport } from '../utils/generatePdfReport';
import styles from './RoomMeeting.module.css';

const API_BASE = 'http://127.0.0.1:8000';

const RoomMeeting = () => {
    const { id } = useParams();
    const location = useLocation();
    const navigate = useNavigate();

    const { name = 'Central Device', agenda: initialAgenda = '', aiEnabled: initialAiEnabled = false } = location.state || {};

    // Meeting state machine: NOT_STARTED -> RECORDING -> CONFIRM_END -> PROCESSING -> COMPLETE
    const [meetingState, setMeetingState] = useState('NOT_STARTED');
    const [agenda, setAgenda] = useState(initialAgenda);
    const [aiEnabled, setAiEnabled] = useState(initialAiEnabled);

    // Participant setup before recording starts
    const [participantCount, setParticipantCount] = useState('3');
    const [participantEmails, setParticipantEmails] = useState(['', '', '']);
    const [emailErrors, setEmailErrors] = useState({});
    const [setupCountError, setSetupCountError] = useState('');
    const [setupDuplicateWarning, setSetupDuplicateWarning] = useState('');
    const [isSetupSaved, setIsSetupSaved] = useState(false);
    const [isSavingSetup, setIsSavingSetup] = useState(false);
    const [setupError, setSetupError] = useState('');
    const [setupSuccess, setSetupSuccess] = useState('');
    const [savedParticipants, setSavedParticipants] = useState([]);

    // Report download and email delivery states
    const [isDownloadingPdf, setIsDownloadingPdf] = useState(false);
    const [isSendingEmail, setIsSendingEmail] = useState(false);
    const [reportSendNotice, setReportSendNotice] = useState({ type: '', message: '' });

    // Mic & Recording states
    const [micPermissionError, setMicPermissionError] = useState('');
    const [isRecording, setIsRecording] = useState(false);


    // Audio recording refs
    const mediaRecorderRef = useRef(null);
    const audioChunksRef = useRef([]);
    const mediaStreamRef = useRef(null);

    // Processing progress steps
    const [processingStep, setProcessingStep] = useState(0);
    const [processingError, setProcessingError] = useState('');

    // Transcript & Summary states
    const [transcript, setTranscript] = useState([]);
    const [summary, setSummary] = useState('');
    const [activeTab, setActiveTab] = useState('transcript'); // 'transcript' | 'summary'

    // Editing state
    const [editingId, setEditingId] = useState(null);
    const [editText, setEditText] = useState('');
    const [isSavingEdit, setIsSavingEdit] = useState(false);
    const [editError, setEditError] = useState('');
    const [isRegeneratingSummary, setIsRegeneratingSummary] = useState(false);

    // Clean up media stream on unmount
    useEffect(() => {
        return () => {
            if (mediaStreamRef.current) {
                mediaStreamRef.current.getTracks().forEach((t) => t.stop());
            }
        };
    }, []);

    // 0. Restore existing room meeting if already processed/ended on server
    useEffect(() => {
        if (!id) return;
        fetch(`${API_BASE}/roomMeeting/details/${id}/`)
            .then((res) => (res.ok ? res.json() : null))
            .then((data) => {
                if (data && data.success) {
                    if (data.ai_enabled !== undefined) setAiEnabled(data.ai_enabled);
                    if (data.agenda) setAgenda(data.agenda);
                    if (data.participants && data.participants.length > 0) {
                        setSavedParticipants(data.participants);
                        setParticipantCount(String(data.participants.length));
                        setParticipantEmails(data.participants.map(p => p.email));
                        setIsSetupSaved(true);
                    }
                    if (data.transcript && data.transcript.length > 0) {
                        setTranscript(data.transcript);
                    }
                    if (data.summary) {
                        setSummary(data.summary);
                    }
                    if ((data.transcript && data.transcript.length > 0) || data.summary) {
                        setMeetingState('COMPLETE');
                        if (data.summary) {
                            setActiveTab('summary');
                        }
                    }
                }
            })
            .catch((err) => {
                console.warn('[ROOM] Could not restore room meeting details:', err);
            });
    }, [id]);

    const validateEmailFormat = (val) => {
        const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return regex.test(String(val).trim());
    };

    const handleCountChange = (e) => {
        const val = e.target.value;
        setParticipantCount(val);
        setIsSetupSaved(false);
        setSetupSuccess('');
        setSetupError('');

        const num = parseInt(val, 10);
        if (!val.trim()) {
            setSetupCountError('Please enter a participant count between 1 and 50.');
            return;
        }

        if (isNaN(num) || num <= 0) {
            setSetupCountError('Please enter a valid positive number for expected participant count (1–50).');
            return;
        }

        if (num > 50) {
            setSetupCountError('Maximum allowed participant count is 50.');
            return;
        }

        setSetupCountError('');

        setParticipantEmails((prev) => {
            const updated = [...prev];
            if (num > prev.length) {
                while (updated.length < num) updated.push('');
            } else if (num < prev.length) {
                return updated.slice(0, num);
            }
            return updated;
        });
    };

    const handleEmailChange = (index, val) => {
        setIsSetupSaved(false);
        setSetupSuccess('');
        setSetupError('');
        setSetupDuplicateWarning('');

        const updated = [...participantEmails];
        updated[index] = val;
        setParticipantEmails(updated);

        setEmailErrors((prev) => {
            const copy = { ...prev };
            delete copy[index];
            return copy;
        });
    };

    const handleSaveParticipantSetup = async () => {
        setSetupError('');
        setSetupSuccess('');
        setSetupCountError('');
        setSetupDuplicateWarning('');

        const count = parseInt(participantCount, 10);
        if (isNaN(count) || count <= 0) {
            setSetupCountError('Please enter a valid positive number for expected participant count (1–50).');
            return;
        }
        if (count > 50) {
            setSetupCountError('Maximum allowed participant count is 50.');
            return;
        }

        const newErrors = {};
        const seen = new Set();
        const trimmedEmails = [];
        let hasDuplicate = false;

        for (let i = 0; i < count; i++) {
            const email = (participantEmails[i] || '').trim().toLowerCase();
            if (!email) {
                newErrors[i] = 'Email address cannot be empty.';
            } else if (!validateEmailFormat(email)) {
                newErrors[i] = 'Invalid email address format.';
            } else if (seen.has(email)) {
                newErrors[i] = `Duplicate email address: ${email}`;
                hasDuplicate = true;
            } else {
                seen.add(email);
            }
            trimmedEmails.push(email);
        }

        if (hasDuplicate) {
            setSetupDuplicateWarning('Warning: duplicate recipient emails detected.');
        }

        if (Object.keys(newErrors).length > 0) {
            setEmailErrors(newErrors);
            setSetupError('Please fix the highlighted email address errors before saving.');
            return;
        }

        setEmailErrors({});
        setIsSavingSetup(true);

        try {
            const res = await fetch(`${API_BASE}/roomMeeting/participants/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    meeting_id: id,
                    participant_count: count,
                    emails: trimmedEmails,
                }),
            });
            const data = await res.json();
            if (res.ok && data.success) {
                setIsSetupSaved(true);
                setSavedParticipants(data.participants || []);
                setSetupSuccess(`✓ ${count} participant email(s) successfully saved!`);
            } else {
                setSetupError(data.message || 'Failed to save participant emails.');
            }
        } catch (err) {
            console.error('[ROOM_PARTICIPANTS] Save failed:', err);
            setSetupError('Network error: unable to save participants to server.');
        } finally {
            setIsSavingSetup(false);
        }
    };

    // Report actions for Room Meeting (Download PDF & Send Email)
    const handleDownloadRoomReportPdf = async () => {
        setIsDownloadingPdf(true);
        try {
            const res = await fetch(`${API_BASE}/roomMeeting/report/${id}/`);
            const data = await res.json();
            if (res.ok && data.success) {
                generateMeetingPdfReport({
                    meetingId: id,
                    agenda: data.agenda || agenda,
                    hostName: data.host_name || name,
                    meetingMode: 'room',
                    createdAt: data.created_at || '',
                    summary: data.summary || summary,
                    followUpMessages: data.follow_up_messages || [],
                    participants: data.participants || savedParticipants,
                });
            } else {
                generateMeetingPdfReport({
                    meetingId: id,
                    agenda: agenda,
                    hostName: name,
                    meetingMode: 'room',
                    createdAt: new Date().toISOString(),
                    summary: summary,
                    followUpMessages: [],
                    participants: savedParticipants,
                });
            }
        } catch (err) {
            console.error('[ROOM_REPORT_DOWNLOAD] Failed:', err);
            generateMeetingPdfReport({
                meetingId: id,
                agenda: agenda,
                hostName: name,
                meetingMode: 'room',
                createdAt: new Date().toISOString(),
                summary: summary,
                followUpMessages: [],
                participants: savedParticipants,
            });
        } finally {
            setIsDownloadingPdf(false);
        }
    };

    const handleSendRoomReportEmail = async () => {
        setIsSendingEmail(true);
        setReportSendNotice({ type: '', message: '' });

        try {
            const res = await fetch(`${API_BASE}/roomMeeting/send-report/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ meeting_id: id }),
            });
            const data = await res.json();
            if (res.ok && data.success) {
                setReportSendNotice({
                    type: 'success',
                    message: data.message || `Meeting report successfully sent to ${data.sent_count} participant(s)!`,
                });
            } else {
                setReportSendNotice({
                    type: 'error',
                    message: data.message || 'Failed to deliver report emails.',
                });
            }
        } catch (err) {
            console.error('[ROOM_SEND_EMAIL] Error:', err);
            setReportSendNotice({
                type: 'error',
                message: 'Network error: could not connect to server to send report emails.',
            });
        } finally {
            setIsSendingEmail(false);
        }
    };

    // 1. Request microphone permission & start recording
    const handleStartRecording = async () => {
        setMicPermissionError('');
        setSetupError('');

        if (!isSetupSaved) {
            setSetupError('Please configure and save the expected recipient emails before starting the recording.');
            return;
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

            mediaStreamRef.current = stream;

            audioChunksRef.current = [];

            // Prefer WAV audio format if supported by browser for native Python decoding fallback
            let mimeType = 'audio/webm';
            if (MediaRecorder.isTypeSupported('audio/wav')) {
                mimeType = 'audio/wav';
            } else if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
                mimeType = 'audio/webm;codecs=opus';
            }

            const recorder = new MediaRecorder(stream, { mimeType });

            recorder.ondataavailable = (event) => {
                if (event.data && event.data.size > 0) {
                    audioChunksRef.current.push(event.data);
                }
            };

            mediaRecorderRef.current = recorder;
            recorder.start(500); // chunk every 500ms into memory array accumulator

            setIsRecording(true);
            setMeetingState('RECORDING');
        } catch (err) {
            console.error('Microphone access denied/error:', err);
            setMicPermissionError('Microphone permission is required to record this meeting.');
        }
    };

    // 2. Open confirmation dialog
    const handlePromptEndMeeting = () => {
        setMeetingState('CONFIRM_END');
    };

    const handleCancelEnd = () => {
        setMeetingState('RECORDING');
    };

    // 3. Confirm End Meeting & Upload Recording
    const handleConfirmEndMeeting = () => {
        setMeetingState('PROCESSING');
        setIsRecording(false);
        setProcessingStep(0);
        setProcessingError('');

        if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
            mediaRecorderRef.current.onstop = () => {
                if (mediaStreamRef.current) {
                    mediaStreamRef.current.getTracks().forEach((t) => t.stop());
                }

                const mimeType = mediaRecorderRef.current.mimeType || 'audio/webm';
                const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
                uploadAndProcessAudio(audioBlob, mimeType.includes('wav') ? 'wav' : 'webm');
            };

            mediaRecorderRef.current.stop();
        } else {
            setProcessingError('No audio recording was captured.');
        }
    };

    // 4. Send complete audio Blob to backend
    const uploadAndProcessAudio = async (audioBlob, extension = 'webm') => {
        const formData = new FormData();
        formData.append('meeting_id', id);
        formData.append('audio', audioBlob, `room_meeting_${id}.${extension}`);

        setProcessingStep(1);

        try {
            const stepTimer1 = setTimeout(() => setProcessingStep(2), 1500);
            const stepTimer2 = setTimeout(() => setProcessingStep(3), 3000);
            const stepTimer3 = setTimeout(() => setProcessingStep(4), 4500);

            const response = await fetch(`${API_BASE}/roomMeeting/process/`, {
                method: 'POST',
                body: formData,
            });

            clearTimeout(stepTimer1);
            clearTimeout(stepTimer2);
            clearTimeout(stepTimer3);

            const data = await response.json();

            if (response.ok && data.success) {
                setProcessingStep(5);
                setTranscript(data.transcript || []);
                setSummary(data.summary || '');
                setMeetingState('COMPLETE');
            } else {
                setProcessingError(data.message || 'Failed to process room meeting audio.');
            }
        } catch (err) {
            console.error('Audio processing upload error:', err);
            setProcessingError('Server network error during audio processing.');
        }
    };

    // 5. Transcript Inline Editing (Text only, speaker label immutable)
    const handleStartEdit = (entry) => {
        setEditingId(entry.id);
        setEditText(entry.text);
        setEditError('');
    };

    const handleCancelEdit = () => {
        setEditingId(null);
        setEditText('');
        setEditError('');
    };

    const handleSaveEdit = async (entry) => {
        if (!editText.trim()) {
            setEditError('Transcript text cannot be empty.');
            return;
        }

        setIsSavingEdit(true);
        setEditError('');

        try {
            const response = await fetch(`${API_BASE}/roomMeeting/transcript/${entry.id}/`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: editText.trim() }),
            });

            const data = await response.json();

            if (response.ok && data.success) {
                setTranscript((prev) =>
                    prev.map((item) => (item.id === entry.id ? { ...item, text: editText.trim() } : item))
                );
                setEditingId(null);
                setEditText('');
            } else {
                setEditError(data.message || 'Failed to update transcript entry.');
            }
        } catch (err) {
            console.error('Transcript edit error:', err);
            setEditError('Failed to connect to server.');
        } finally {
            setIsSavingEdit(false);
        }
    };

    // 6. Regenerate Summary with corrected transcript
    const handleRegenerateSummary = async () => {
        setIsRegeneratingSummary(true);
        try {
            const response = await fetch(`${API_BASE}/roomMeeting/generateSummary/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ meeting_id: id }),
            });
            const data = await response.json();
            if (response.ok && data.success) {
                setSummary(data.summary);
            }
        } catch (err) {
            console.error('Regenerate summary error:', err);
        } finally {
            setIsRegeneratingSummary(false);
        }
    };

    return (
        <div className={styles.page}>
            {/* Header */}
            <header className={styles.header}>
                <div className={styles.headerLeft}>
                    <button className={styles.backBtn} onClick={() => navigate('/')}>
                        ← Home
                    </button>
                    <div className={styles.logo}>
                        <span className={styles.logoIcon}>🎙</span>
                        <span className={styles.logoText}>Room Meeting</span>
                    </div>
                </div>
                <div className={styles.headerCenter}>
                    <span className={styles.meetingIdBadge}>
                        Room ID: <strong>{id}</strong>
                    </span>
                </div>
                <div className={styles.headerRight}>
                    {aiEnabled && <span className={styles.aiChip}>✦ AI Mode Enabled</span>}
                </div>
            </header>

            <main className={styles.mainContainer}>
                {/* STATE 1: NOT_STARTED */}
                {meetingState === 'NOT_STARTED' && (
                    <div className={styles.card}>
                        <div className={styles.cardHeader}>
                            <h2>In-Person Room Meeting</h2>
                            <p className={styles.subtitle}>Place this central device in the meeting room.</p>
                        </div>

                        {agenda && (
                            <div className={styles.agendaSection}>
                                <label className={styles.label}>Agenda:</label>
                                <div className={styles.agendaBox}>{agenda}</div>
                            </div>
                        )}

                        <div className={styles.statusGrid}>
                            <div className={styles.statusTile}>
                                <span className={styles.statusLabel}>Microphone</span>
                                <span className={styles.statusValueReady}>● Ready</span>
                            </div>
                            <div className={styles.statusTile}>
                                <span className={styles.statusLabel}>Recording</span>
                                <span className={styles.statusValueOff}>○ Not Started</span>
                            </div>
                        </div>

                        {/* Participant Setup Step */}
                        <div className={styles.participantSetupSection}>
                            <div className={styles.setupTitleGroup}>
                                <h3 className={styles.setupTitle}>👥 Participant Report Setup</h3>
                                <p className={styles.setupSubtitle}>Configure who will receive the meeting report PDF after the session.</p>
                            </div>

                            {isSetupSaved ? (
                                <div className={styles.setupSavedBanner}>
                                    <div>
                                        <strong>✓ Participants Configured ({savedParticipants.length}):</strong>
                                        <div style={{ marginTop: '4px', fontSize: '0.85rem' }}>
                                            {savedParticipants.map(p => p.email).join(', ')}
                                        </div>
                                    </div>
                                    <button 
                                        type="button" 
                                        className={styles.editSetupBtn}
                                        onClick={() => setIsSetupSaved(false)}
                                    >
                                        Edit List
                                    </button>
                                </div>
                            ) : (
                                <>
                                    <div className={styles.countInputRow}>
                                        <label className={styles.questionLabel} htmlFor="participant-count-input">
                                            How many participants should receive this meeting report?
                                        </label>
                                        <input
                                            id="participant-count-input"
                                            type="number"
                                            min="1"
                                            max="50"
                                            className={styles.countInput}
                                            value={participantCount}
                                            onChange={handleCountChange}
                                            placeholder="e.g. 3"
                                        />
                                    </div>

                                    {setupCountError && (
                                        <p className={styles.fieldValidationMsg}>{setupCountError}</p>
                                    )}

                                    {participantEmails.length > 0 && (
                                        <div className={styles.emailFieldsList}>
                                            {participantEmails.map((email, idx) => (
                                                <div key={idx} className={styles.emailFieldItem}>
                                                    <label className={styles.emailFieldItemLabel} htmlFor={`participant-email-${idx}`}>
                                                        Participant {idx + 1} email:
                                                    </label>
                                                    <input
                                                        id={`participant-email-${idx}`}
                                                        type="email"
                                                        className={`${styles.emailInput} ${emailErrors[idx] ? styles.emailInputError : ''}`}
                                                        value={email}
                                                        placeholder={`participant${idx + 1}@example.com`}
                                                        onChange={(e) => handleEmailChange(idx, e.target.value)}
                                                    />
                                                    {emailErrors[idx] && (
                                                        <p className={styles.fieldValidationMsg}>{emailErrors[idx]}</p>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    {setupDuplicateWarning && (
                                        <p className={styles.fieldWarningMsg}>{setupDuplicateWarning}</p>
                                    )}

                                    {setupError && (
                                        <p className={styles.fieldValidationMsg}>{setupError}</p>
                                    )}

                                    <div className={styles.setupActionsRow}>
                                        <button
                                            type="button"
                                            className={styles.saveSetupBtn}
                                            onClick={handleSaveParticipantSetup}
                                            disabled={isSavingSetup}
                                        >
                                            {isSavingSetup ? 'Saving Recipients...' : 'Save Recipient List'}
                                        </button>
                                    </div>
                                </>
                            )}
                        </div>

                        {micPermissionError && (
                            <div className={styles.errorAlert}>
                                <p>{micPermissionError}</p>
                                <button className={styles.retryBtn} onClick={handleStartRecording}>
                                    Retry Permission
                                </button>
                            </div>
                        )}

                        <div className={styles.actionCenter}>
                            <button className={styles.tapToStartBtn} onClick={handleStartRecording}>
                                TAP TO START
                            </button>
                        </div>
                    </div>
                )}

                {/* STATE 2: RECORDING */}
                {meetingState === 'RECORDING' && (
                    <div className={styles.card}>
                        <div className={styles.recordingHeader}>
                            <div className={styles.liveIndicator}>
                                <span className={styles.redPulse} />
                                <h3>🔴 Recording...</h3>
                            </div>
                            <p className={styles.progressText}>Meeting in progress. Recording complete room audio.</p>
                        </div>

                        {agenda && (
                            <div className={styles.agendaSection}>
                                <label className={styles.label}>Agenda:</label>
                                <div className={styles.agendaBox}>{agenda}</div>
                            </div>
                        )}

                        <div className={styles.recordingVisualizer}>
                            <div className={styles.waveBar} />
                            <div className={styles.waveBar} />
                            <div className={styles.waveBar} />
                            <div className={styles.waveBar} />
                            <div className={styles.waveBar} />
                        </div>

                        <div className={styles.actionCenter}>
                            <button className={styles.endMeetingBtn} onClick={handlePromptEndMeeting}>
                                END MEETING
                            </button>
                        </div>
                    </div>
                )}

                {/* STATE 3: CONFIRM_END */}
                {meetingState === 'CONFIRM_END' && (
                    <div className={styles.modalBackdrop}>
                        <div className={styles.modalCard}>
                            <h3>End Room Meeting?</h3>
                            <p>
                                The complete meeting recording will now be processed to identify speakers and generate
                                the transcript.
                            </p>
                            <div className={styles.modalActions}>
                                <button className={styles.cancelBtn} onClick={handleCancelEnd}>
                                    Cancel
                                </button>
                                <button className={styles.confirmEndBtn} onClick={handleConfirmEndMeeting}>
                                    End Meeting
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* STATE 4: PROCESSING */}
                {meetingState === 'PROCESSING' && (
                    <div className={styles.card}>
                        <div className={styles.cardHeader}>
                            <h2>Processing Meeting...</h2>
                            <p className={styles.subtitle}>Please wait while complete audio is analyzed.</p>
                        </div>

                        <div className={styles.progressList}>
                            <div className={`${styles.progressStep} ${processingStep >= 1 ? styles.stepDone : styles.stepActive}`}>
                                <span className={styles.stepIcon}>{processingStep >= 1 ? '✓' : '●'}</span>
                                <span>Recording uploaded</span>
                            </div>
                            <div className={`${styles.progressStep} ${processingStep >= 2 ? styles.stepDone : processingStep === 1 ? styles.stepActive : styles.stepPending}`}>
                                <span className={styles.stepIcon}>{processingStep >= 2 ? '✓' : processingStep === 1 ? '●' : '○'}</span>
                                <span>Detecting speakers (Pyannote Diarization)</span>
                            </div>
                            <div className={`${styles.progressStep} ${processingStep >= 3 ? styles.stepDone : processingStep === 2 ? styles.stepActive : styles.stepPending}`}>
                                <span className={styles.stepIcon}>{processingStep >= 3 ? '✓' : processingStep === 2 ? '●' : '○'}</span>
                                <span>Converting speech to text (Whisper ASR)</span>
                            </div>
                            <div className={`${styles.progressStep} ${processingStep >= 4 ? styles.stepDone : processingStep === 3 ? styles.stepActive : styles.stepPending}`}>
                                <span className={styles.stepIcon}>{processingStep >= 4 ? '✓' : processingStep === 3 ? '●' : '○'}</span>
                                <span>Building speaker-labelled transcript</span>
                            </div>
                            {aiEnabled && (
                                <div className={`${styles.progressStep} ${processingStep >= 5 ? styles.stepDone : processingStep === 4 ? styles.stepActive : styles.stepPending}`}>
                                    <span className={styles.stepIcon}>{processingStep >= 5 ? '✓' : processingStep === 4 ? '●' : '○'}</span>
                                    <span>Generating meeting summary (Gemini)</span>
                                </div>
                            )}
                        </div>

                        {processingError && (
                            <div className={styles.errorAlert}>
                                <p>{processingError}</p>
                                <button className={styles.retryBtn} onClick={() => setMeetingState('RECORDING')}>
                                    Return to Meeting
                                </button>
                            </div>
                        )}
                    </div>
                )}

                {/* STATE 5: COMPLETE */}
                {meetingState === 'COMPLETE' && (
                    <div className={styles.cardLarge}>
                        <div className={styles.completeHeader}>
                            <div>
                                <h2>Meeting Processing Complete ✓</h2>
                                <p className={styles.subtitle}>Speaker-labelled transcript & AI analysis</p>
                            </div>
                            <div className={styles.tabButtons}>
                                <button
                                    className={`${styles.tabBtn} ${activeTab === 'transcript' ? styles.tabActive : ''}`}
                                    onClick={() => setActiveTab('transcript')}
                                >
                                    View Transcript ({transcript.length})
                                </button>
                                {aiEnabled && (
                                    <button
                                        className={`${styles.tabBtn} ${activeTab === 'summary' ? styles.tabActive : ''}`}
                                        onClick={() => setActiveTab('summary')}
                                    >
                                        View Summary
                                    </button>
                                )}
                                {aiEnabled && (
                                    <button
                                        className={`${styles.tabBtn} ${activeTab === 'followup' ? styles.tabActive : ''}`}
                                        onClick={() => setActiveTab('followup')}
                                    >
                                        ✦ Ask AI Follow-Up
                                    </button>
                                )}
                            </div>
                        </div>

                        {/* Transcript Tab */}
                        {activeTab === 'transcript' && (
                            <div className={styles.transcriptContainer}>
                                <h3 className={styles.sectionTitle}>Meeting Transcript</h3>
                                {transcript.length === 0 ? (
                                    <p className={styles.emptyText}>No speech detected in this meeting recording.</p>
                                ) : (
                                    <div className={styles.entryList}>
                                        {transcript.map((entry) => {
                                            const isEditing = editingId === entry.id;
                                            return (
                                                <div key={entry.id} className={styles.transcriptCard}>
                                                    <div className={styles.entryHeader}>
                                                        <span className={styles.speakerTag}>{entry.speaker}</span>
                                                        {!isEditing && (
                                                            <button
                                                                className={styles.pencilEditBtn}
                                                                onClick={() => handleStartEdit(entry)}
                                                                title="Edit transcript text"
                                                            >
                                                                ✏
                                                            </button>
                                                        )}
                                                    </div>

                                                    {isEditing ? (
                                                        <div className={styles.editBox}>
                                                            <textarea
                                                                className={styles.editTextarea}
                                                                value={editText}
                                                                onChange={(e) => setEditText(e.target.value)}
                                                                rows={3}
                                                            />
                                                            {editError && <p className={styles.editErrorMsg}>{editError}</p>}
                                                            <div className={styles.editActions}>
                                                                <button
                                                                    className={styles.saveBtn}
                                                                    onClick={() => handleSaveEdit(entry)}
                                                                    disabled={isSavingEdit}
                                                                >
                                                                    {isSavingEdit ? 'Saving...' : 'Save'}
                                                                </button>
                                                                <button
                                                                    className={styles.cancelEditBtn}
                                                                    onClick={handleCancelEdit}
                                                                    disabled={isSavingEdit}
                                                                >
                                                                    Cancel
                                                                </button>
                                                            </div>
                                                        </div>
                                                    ) : (
                                                        <p className={styles.entryBodyText}>{entry.text}</p>
                                                    )}
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Summary Tab */}
                        {activeTab === 'summary' && aiEnabled && (
                            <div className={styles.summaryContainer}>
                                <div className={styles.summaryHeaderBar}>
                                    <h3 className={styles.sectionTitle}>AI Meeting Summary (Gemini)</h3>
                                    <button
                                        className={styles.regenBtn}
                                        onClick={handleRegenerateSummary}
                                        disabled={isRegeneratingSummary}
                                    >
                                        {isRegeneratingSummary ? 'Regenerating...' : '🔄 Update Summary with Edited Transcript'}
                                    </button>
                                </div>
                                {summary ? (
                                    <>
                                        <pre className={styles.summaryContent}>{summary}</pre>
                                        <div style={{ marginTop: '20px' }}>
                                            <FollowUpChat meetingId={id} meetingMode="room" isSummaryReady={!!summary} />
                                        </div>
                                    </>
                                ) : (
                                    <p className={styles.emptyText}>Summary is being generated or was not requested.</p>
                                )}
                            </div>
                        )}

                        {/* Dedicated Follow-Up Tab */}
                        {activeTab === 'followup' && aiEnabled && (
                            <div className={styles.summaryContainer}>
                                <FollowUpChat meetingId={id} meetingMode="room" isSummaryReady={!!summary} />
                            </div>
                        )}

                        {/* Report Actions Card */}
                        <div className={styles.roomReportActionsCard}>
                            <div className={styles.roomReportHeader}>
                                <div>
                                    <h3 className={styles.roomReportTitle}>📄 Meeting Report & Distribution</h3>
                                    <p className={styles.subtitle} style={{ margin: 0, fontSize: '0.85rem' }}>
                                        Export or distribute the official meeting report with AI summary and follow-up conversation.
                                    </p>
                                </div>
                                <div className={styles.roomReportButtons}>
                                    <button
                                        type="button"
                                        className={styles.roomDownloadPdfBtn}
                                        onClick={handleDownloadRoomReportPdf}
                                        disabled={isDownloadingPdf}
                                    >
                                        {isDownloadingPdf ? 'Generating PDF...' : '⬇ Download Meeting Report PDF'}
                                    </button>
                                    <button
                                        type="button"
                                        className={styles.roomSendEmailBtn}
                                        onClick={handleSendRoomReportEmail}
                                        disabled={isSendingEmail || savedParticipants.length === 0}
                                        title={savedParticipants.length === 0 ? 'No recipient emails configured' : 'Send PDF to participants'}
                                    >
                                        {isSendingEmail ? 'Sending Emails...' : '✉ Send Meeting Report to Participants'}
                                    </button>
                                </div>
                            </div>

                            {/* Recipient review */}
                            <div className={styles.roomRecipientListBox}>
                                <p className={styles.roomRecipientLabel}>
                                    <strong>Configured Recipients ({savedParticipants.length}):</strong>
                                    {savedParticipants.length === 0
                                        ? ' No recipient emails were configured before recording.'
                                        : ' The report will be delivered individually to:'}
                                </p>
                                {savedParticipants.length > 0 && (
                                    <div className={styles.roomRecipientTags}>
                                        {savedParticipants.map((p, idx) => (
                                            <span key={idx} className={styles.roomRecipientChip}>
                                                ✉ {p.email}
                                            </span>
                                        ))}
                                    </div>
                                )}
                            </div>

                            {reportSendNotice.message && (
                                <p className={reportSendNotice.type === 'success' ? styles.successAlert : styles.dangerAlert}>
                                    {reportSendNotice.message}
                                </p>
                            )}
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
};

export default RoomMeeting;
