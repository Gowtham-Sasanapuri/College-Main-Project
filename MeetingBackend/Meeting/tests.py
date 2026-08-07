from django.test import TestCase
from unittest.mock import patch

from .models import Meeting, TranscriptEntry


class EndMeetingTests(TestCase):
	def setUp(self):
		self.meeting = Meeting.objects.create(
			Meeting_id="11111111-1111-1111-1111-111111111111",
			Host_name="Host",
			Agenda="Ship the release",
			Status=True,
			ai_enabled=True,
		)

	def test_end_meeting_without_ai_skips_summary(self):
		self.meeting.ai_enabled = False
		self.meeting.save(update_fields=["ai_enabled"])

		response = self.client.post(
			"/endMeeting/",
			data={"meeting_id": str(self.meeting.Meeting_id), "generate_summary": True},
			content_type="application/json",
		)

		self.meeting.refresh_from_db()

		self.assertEqual(response.status_code, 200)
		self.assertTrue(self.meeting.Status)
		self.assertFalse(self.meeting.Summary)
		self.assertJSONEqual(
			response.content,
			{
				"success": True,
				"ended": False,
				"summary_generated": False,
				"ai_enabled": False,
				"message": "AI is disabled for this meeting.",
			},
		)

	def test_end_meeting_with_no_transcript_returns_graceful_message(self):
		response = self.client.post(
			"/endMeeting/",
			data={"meeting_id": str(self.meeting.Meeting_id), "generate_summary": True},
			content_type="application/json",
		)

		self.meeting.refresh_from_db()

		self.assertEqual(response.status_code, 200)
		self.assertTrue(self.meeting.Status)
		self.assertJSONEqual(
			response.content,
			{
				"success": True,
				"ended": True,
				"summary_generated": False,
				"ai_enabled": True,
				"no_transcript": True,
				"message": "No transcript is available to summarize.",
			},
		)


	@patch("Meeting.views._summarize_transcript", return_value="Summary text")
	def test_end_meeting_generates_and_stores_summary(self, mocked_summary):
		TranscriptEntry.objects.create(
			meeting=self.meeting,
			speaker_name="Alice",
			text="We should finish the backend by Friday.",
		)

		response = self.client.post(
			"/endMeeting/",
			data={"meeting_id": str(self.meeting.Meeting_id), "generate_summary": True},
			content_type="application/json",
		)

		self.meeting.refresh_from_db()

		self.assertEqual(response.status_code, 200)
		self.assertEqual(self.meeting.Summary, "Summary text")
		self.assertJSONEqual(
			response.content,
			{
				"success": True,
				"ended": True,
				"summary_generated": True,
				"ai_enabled": True,
				"summary": "Summary text",
			},
		)
		mocked_summary.assert_called_once()

	@patch.dict("os.environ", {}, clear=True)
	def test_end_meeting_missing_hf_token_returns_clear_error(self):
		TranscriptEntry.objects.create(
			meeting=self.meeting,
			speaker_name="Alice",
			text="Let us discuss the release.",
		)

		response = self.client.post(
			"/endMeeting/",
			data={"meeting_id": str(self.meeting.Meeting_id), "generate_summary": True},
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 400)
		self.assertJSONEqual(
			response.content,
			{
				"success": False,
				"ended": True,
				"summary_generated": False,
				"ai_enabled": True,
				"message": "HF_TOKEN is not configured",
			},
		)


class UpdateTranscriptTests(TestCase):
	def setUp(self):
		self.meeting = Meeting.objects.create(
			Meeting_id="22222222-2222-2222-2222-222222222222",
			Host_name="Host",
			Agenda="Architecture review",
			Status=True,
			ai_enabled=True,
		)
		self.entry = TranscriptEntry.objects.create(
			meeting=self.meeting,
			speaker_name="Gowtham",
			speaker_id="p_gowtham123",
			text="We are using dock her for deployment.",
		)

	def test_owner_can_update_transcript_entry(self):
		response = self.client.patch(
			f"/transcript/edit/{self.entry.pk}/",
			data={"participant_id": "p_gowtham123", "text": "We are using Docker for deployment."},
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 200)
		self.entry.refresh_from_db()
		self.assertEqual(self.entry.text, "We are using Docker for deployment.")

	def test_non_owner_cannot_update_transcript_entry(self):
		response = self.client.patch(
			f"/transcript/edit/{self.entry.pk}/",
			data={"participant_id": "p_attacker999", "text": "Hacked transcript."},
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 403)
		self.entry.refresh_from_db()
		self.assertEqual(self.entry.text, "We are using dock her for deployment.")


