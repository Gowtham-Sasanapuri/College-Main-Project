from django.db import models
import uuid


class Meeting(models.Model):
    STATUS_CHOICES = (
        ("scheduled", "Scheduled"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    )

    Meeting_id = models.UUIDField(editable=False, primary_key=True)
    Host_name = models.CharField(max_length=150)
    title = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    Agenda = models.CharField(max_length=200, blank=True, default="")
    Created_at = models.DateTimeField(auto_now_add=True)
    Status = models.BooleanField(default=False)
    lifecycle_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled")
    meeting_mode = models.CharField(max_length=50, default="video")
    venue = models.CharField(max_length=255, blank=True, default="")
    scheduled_date = models.CharField(max_length=50, blank=True, default="")
    scheduled_start_time = models.CharField(max_length=50, blank=True, default="")
    scheduled_end_time = models.CharField(max_length=50, blank=True, default="")
    expected_duration = models.CharField(max_length=50, blank=True, default="")
    actual_start_time = models.DateTimeField(null=True, blank=True)
    actual_end_time = models.DateTimeField(null=True, blank=True)
    actual_duration_seconds = models.IntegerField(default=0, null=True, blank=True)
    # AI Meeting Assistant — optional per-meeting feature
    ai_enabled = models.BooleanField(default=False)
    Summary = models.TextField(null=True, blank=True)
    mom_data = models.JSONField(null=True, blank=True)
    report_sent_at = models.DateTimeField(null=True, blank=True)

    @property
    def display_title(self):
        return self.title or self.Agenda or f"Meeting {str(self.Meeting_id)[:8]}"

    @property
    def status_value(self):
        return self.lifecycle_status

    def __str__(self):
        return f"{self.display_title} [{self.meeting_mode}] — {str(self.Meeting_id)[:8]}"


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


class MeetingAgendaItem(models.Model):
    """
    Structured agenda item associated with a meeting session.
    Supports title, notes, presenter, allocated duration, order, and status tracking.
    """
    AGENDA_STATUS_CHOICES = (
        ("Pending", "Pending"),
        ("In Progress", "In Progress"),
        ("Completed", "Completed"),
        ("Skipped", "Skipped"),
    )

    meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="agenda_items",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    presenter = models.CharField(max_length=150, blank=True, default="")
    expected_duration = models.CharField(max_length=50, blank=True, default="")
    order = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=50, choices=AGENDA_STATUS_CHOICES, default="Pending")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return f"[{self.order}] {self.title} ({self.status}) - {str(self.meeting.Meeting_id)[:8]}"
