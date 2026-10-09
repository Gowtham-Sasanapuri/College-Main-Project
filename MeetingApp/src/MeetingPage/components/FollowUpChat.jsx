import React, { useState, useEffect, useRef } from 'react';
import styles from './FollowUpChat.module.css';

const API_BASE = 'http://127.0.0.1:8000';

const SUGGESTED_PROMPTS = [
    'What were the main decisions made during this meeting?',
    'What tasks were assigned to each participant?',
    'Who was responsible for completing the deployment?',
    'Explain the second key point in more detail.',
    'What problems were discussed regarding the project?',
    "Give me a short explanation of the meeting's conclusion.",
];

export default function FollowUpChat({
    meetingId,
    meetingMode = 'video',
    isSummaryReady = true,
    className = '',
}) {
    const [messages, setMessages] = useState([]);
    const [inputQuestion, setInputQuestion] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');
    const [historyLoading, setHistoryLoading] = useState(true);

    const messagesEndRef = useRef(null);
    const textareaRef = useRef(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages, isLoading]);

    // Load existing follow-up messages on mount or meetingId change
    useEffect(() => {
        if (!meetingId) return;

        let isMounted = true;
        setHistoryLoading(true);
        setError('');

        const endpoint = meetingMode === 'room'
            ? `${API_BASE}/roomMeeting/followup/${meetingId}/`
            : `${API_BASE}/meeting/followup/${meetingId}/`;

        fetch(endpoint)
            .then((res) => {
                if (!res.ok) {
                    throw new Error(`Failed to load conversation history (Status ${res.status})`);
                }
                return res.json();
            })
            .then((data) => {
                if (isMounted && data.success) {
                    setMessages(data.messages || []);
                }
            })
            .catch((err) => {
                if (isMounted) {
                    console.warn('[FOLLOWUP] Could not fetch history:', err.message);
                }
            })
            .finally(() => {
                if (isMounted) {
                    setHistoryLoading(false);
                }
            });

        return () => {
            isMounted = false;
        };
    }, [meetingId, meetingMode]);

    const handleSend = async (questionText) => {
        const textToSend = (questionText !== undefined ? questionText : inputQuestion).trim();
        if (!textToSend || isLoading) return;

        setError('');
        setIsLoading(true);
        setInputQuestion('');

        // Temporary optimistic user message for immediate feedback
        const tempUserMsg = {
            id: `temp-${Date.now()}`,
            message_by: 'user',
            content: textToSend,
            timestamp: new Date().toISOString(),
        };

        setMessages((prev) => [...prev, tempUserMsg]);

        const endpoint = meetingMode === 'room'
            ? `${API_BASE}/roomMeeting/followup/`
            : `${API_BASE}/meeting/followup/`;

        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    meeting_id: meetingId,
                    question: textToSend,
                }),
            });

            const data = await response.json();

            if (response.ok && data.success) {
                // Replace optimistic message with persisted messages from backend
                setMessages((prev) => {
                    const withoutTemp = prev.filter((m) => m.id !== tempUserMsg.id);
                    return [...withoutTemp, data.user_message, data.ai_message];
                });
            } else {
                // Remove temporary message on error so user can re-try
                setMessages((prev) => prev.filter((m) => m.id !== tempUserMsg.id));
                setError(data.message || 'Failed to generate AI response. Please try again.');
                setInputQuestion(textToSend); // preserve input
            }
        } catch (err) {
            console.error('[FOLLOWUP] Send error:', err);
            setMessages((prev) => prev.filter((m) => m.id !== tempUserMsg.id));
            setError('Network error: Unable to contact the AI assistant server.');
            setInputQuestion(textToSend);
        } finally {
            setIsLoading(false);
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    const handleChipClick = (prompt) => {
        handleSend(prompt);
    };

    const formatTime = (isoString) => {
        if (!isoString) return '';
        try {
            const date = new Date(isoString);
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch {
            return '';
        }
    };

    return (
        <div className={`${styles.chatContainer} ${className}`}>
            {/* Header */}
            <div className={styles.chatHeader}>
                <div className={styles.headerLeft}>
                    <div className={styles.aiIconBadge}>✦</div>
                    <div>
                        <h4 className={styles.chatTitle}>Ask AI Follow-Up</h4>
                        <p className={styles.chatSubtitle}>Grounds answers on this meeting's summary & transcript</p>
                    </div>
                </div>
                <div className={styles.headerRight}>
                    {messages.length > 0 && (
                        <span className={styles.messageCountBadge}>
                            {messages.length} {messages.length === 1 ? 'message' : 'messages'}
                        </span>
                    )}
                </div>
            </div>

            {/* Conversation Messages */}
            <div className={styles.messagesArea}>
                {historyLoading ? (
                    <div className={styles.emptyState}>
                        <div className={styles.loadingDot} style={{ width: 12, height: 12 }} />
                        <p className={styles.emptyText} style={{ marginTop: 12 }}>Loading conversation history...</p>
                    </div>
                ) : messages.length === 0 ? (
                    <div className={styles.emptyState}>
                        <div className={styles.emptyIcon}>💬</div>
                        <h5 className={styles.emptyTitle}>Have questions about this meeting?</h5>
                        <p className={styles.emptyText}>
                            Ask anything about decisions made, assigned tasks, topics discussed, or specific participant statements.
                        </p>

                        <div className={styles.quickPromptsContainer}>
                            <span className={styles.quickPromptsLabel}>Suggested questions:</span>
                            <div className={styles.quickPromptsGrid}>
                                {SUGGESTED_PROMPTS.map((prompt, index) => (
                                    <button
                                        key={index}
                                        type="button"
                                        className={styles.promptChip}
                                        onClick={() => handleChipClick(prompt)}
                                        disabled={isLoading}
                                    >
                                        {prompt}
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>
                ) : (
                    <>
                        {messages.map((msg, index) => {
                            const isUser = msg.message_by === 'user';
                            return (
                                <div
                                    key={msg.id || index}
                                    className={`${styles.messageRow} ${isUser ? styles.messageRowUser : styles.messageRowAi}`}
                                >
                                    <div className={styles.messageMeta}>
                                        <span className={styles.senderName}>
                                            {isUser ? 'You' : '✦ AI Assistant'}
                                        </span>
                                        {msg.timestamp && (
                                            <span className={styles.timestamp}>
                                                • {formatTime(msg.timestamp)}
                                            </span>
                                        )}
                                    </div>
                                    <div className={`${styles.messageBubble} ${isUser ? styles.userBubble : styles.aiBubble}`}>
                                        <p className={styles.messageContent}>{msg.content}</p>
                                    </div>
                                </div>
                            );
                        })}

                        {isLoading && (
                            <div className={styles.loadingBubble}>
                                <div className={styles.loadingDot} />
                                <div className={styles.loadingDot} />
                                <div className={styles.loadingDot} />
                                <span className={styles.loadingText}>Analyzing meeting context...</span>
                            </div>
                        )}
                    </>
                )}
                <div ref={messagesEndRef} />
            </div>

            {/* Error Notification */}
            {error && (
                <div className={styles.errorAlert}>
                    <span>{error}</span>
                    <button
                        className={styles.dismissBtn}
                        onClick={() => setError('')}
                        aria-label="Dismiss error"
                    >
                        ✕
                    </button>
                </div>
            )}

            {/* Input Bar */}
            <form
                className={styles.inputForm}
                onSubmit={(e) => {
                    e.preventDefault();
                    handleSend();
                }}
            >
                <div className={styles.textareaWrapper}>
                    <textarea
                        ref={textareaRef}
                        className={styles.textarea}
                        placeholder={
                            isSummaryReady
                                ? "Ask a follow-up question about this meeting... (Press Enter to send)"
                                : "Meeting summary is generating..."
                        }
                        value={inputQuestion}
                        onChange={(e) => setInputQuestion(e.target.value)}
                        onKeyDown={handleKeyDown}
                        disabled={isLoading || !isSummaryReady}
                        rows={1}
                    />
                </div>
                <button
                    type="submit"
                    className={styles.sendBtn}
                    disabled={isLoading || !inputQuestion.trim() || !isSummaryReady}
                    title="Send question (Enter)"
                >
                    <span className={styles.sendIcon}>➤</span>
                    <span>Send</span>
                </button>
            </form>
        </div>
    );
}
