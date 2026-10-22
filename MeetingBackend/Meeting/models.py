from django.db import models
import uuid


class Meeting(models.Model):
    Meeting_id = models.UUIDField(editable=False, primary_key=True)
    Host_name = models.CharField(max_length=150)
    Agenda = models.CharField(max_length=200)
    Created_at = models.DateTimeField(auto_now_add=True)
    Status = models.BooleanField(default=False)
    meeting_mode = models.CharField(max_length=50, default="video")
    # AI Meeting Assistant — optional per-meeting feature
    ai_enabled = models.BooleanField(default=False)
    Summary = models.TextField(null=True, blank=True)
    report_sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.Host_name} [{self.meeting_mode}] — {str(self.Meeting_id)[:8]}"


class TranscriptEntry(models.Model):
    """
    A single speech-to-text result for a meeting.
    Created in real time as participants speak.
    """
    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name='transcript_entries',
    )
    speaker_name = models.CharField(max_length=150)
    speaker_id = models.CharField(max_length=255, null=True, blank=True)
    text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"[{self.speaker_name}] {self.text[:60]}"


class FollowUpMessage(models.Model):
    """
    Persisted follow-up conversation messages (user questions and AI answers)
    for a completed meeting session in both video and room meeting modes.
    """
    MESSAGE_BY_CHOICES = (
        ("user", "User"),
        ("ai", "AI"),
    )

    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="follow_up_messages",
    )
    message_by = models.CharField(max_length=10, choices=MESSAGE_BY_CHOICES)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp", "pk"]

    def __str__(self):
        return f"[{str(self.meeting.Meeting_id)[:8]}] {self.message_by}: {self.content[:40]}"


class MeetingParticipant(models.Model):
    """
    Stores participant emails and names for meeting report delivery and participant records.
    Applies to both Video Calling meetings and Room Meeting sessions.
    """
    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    email = models.EmailField(max_length=254)
    name = models.CharField(max_length=150, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["meeting", "email"], name="unique_meeting_participant_email")
        ]

    def __str__(self):
        return f"{self.email} ({str(self.meeting.Meeting_id)[:8]})"