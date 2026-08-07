from django.db import models
import uuid


class Meeting(models.Model):
    Meeting_id = models.UUIDField(editable=False, primary_key=True)
    Host_name = models.CharField(max_length=150)
    Agenda = models.CharField(max_length=200)
    Created_at = models.DateTimeField(auto_now_add=True)
    Status = models.BooleanField(default=False)
    # AI Meeting Assistant — optional per-meeting feature
    ai_enabled = models.BooleanField(default=False)
    Summary = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.Host_name} — {str(self.Meeting_id)[:8]}"


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