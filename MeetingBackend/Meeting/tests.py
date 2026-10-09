from django.test import TestCase
from unittest.mock import patch

from .models import Meeting, TranscriptEntry, FollowUpMessage


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


class RoomMeetingTests(TestCase):
	def setUp(self):
		self.meeting = Meeting.objects.create(
			Meeting_id="33333333-3333-3333-3333-333333333333",
			Host_name="Central Device",
			Agenda="Discuss project architecture",
			meeting_mode="room",
			Status=True,
			ai_enabled=True,
		)
		self.entry = TranscriptEntry.objects.create(
			meeting=self.meeting,
			speaker_name="Speaker_001",
			text="We need to discuss deployment.",
		)

	def test_create_room_meeting(self):
		response = self.client.post(
			"/roomMeeting/create/",
			data={"name": "Conference Room A", "Agenda": "Deployment timeline", "ai_enabled": True},
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.json().get("success"))

	def test_room_meeting_transcript_text_edit(self):
		response = self.client.patch(
			f"/roomMeeting/transcript/{self.entry.pk}/",
			data={"text": "We need to discuss Kubernetes deployment."},
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 200)
		self.entry.refresh_from_db()
		self.assertEqual(self.entry.text, "We need to discuss Kubernetes deployment.")
		self.assertEqual(self.entry.speaker_name, "Speaker_001")

	@patch("Meeting.room_views._summarize_transcript", return_value="Updated Room Summary")
	def test_generate_room_summary(self, mock_summary):
		response = self.client.post(
			"/roomMeeting/generateSummary/",
			data={"meeting_id": str(self.meeting.Meeting_id)},
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 200)
		self.meeting.refresh_from_db()
		self.assertEqual(self.meeting.Summary, "Updated Room Summary")


class FollowUpQuestionTests(TestCase):
	def setUp(self):
		self.meeting = Meeting.objects.create(
			Meeting_id="44444444-4444-4444-4444-444444444444",
			Host_name="Alice",
			Agenda="Q3 Product Roadmap",
			Status=False,
			ai_enabled=True,
			Summary="Meeting Overview:\nDiscussed Q3 release.\nDecisions Made:\n1. Deploy backend first.",
		)
		TranscriptEntry.objects.create(
			meeting=self.meeting,
			speaker_name="Alice",
			text="Let's finish backend deployment first.",
		)
		TranscriptEntry.objects.create(
			meeting=self.meeting,
			speaker_name="Bob",
			text="I will handle the Docker setup.",
		)

	@patch("Meeting.views._answer_followup_question", return_value="The team decided to deploy backend first.")
	def test_ask_followup_success(self, mock_answer):
		response = self.client.post(
			"/meeting/followup/",
			data={
				"meeting_id": str(self.meeting.Meeting_id),
				"question": "What were the main decisions made?",
			},
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertTrue(data.get("success"))
		self.assertEqual(data["user_message"]["message_by"], "user")
		self.assertEqual(data["user_message"]["content"], "What were the main decisions made?")
		self.assertEqual(data["ai_message"]["message_by"], "ai")
		self.assertEqual(data["ai_message"]["content"], "The team decided to deploy backend first.")

		# Verify DB persistence
		messages = FollowUpMessage.objects.filter(meeting=self.meeting).order_by("timestamp", "pk")
		self.assertEqual(messages.count(), 2)
		self.assertEqual(messages[0].message_by, "user")
		self.assertEqual(messages[1].message_by, "ai")

	@patch("Meeting.views._answer_followup_question")
	def test_multi_turn_history_passed_to_model(self, mock_answer):
		mock_answer.return_value = "Bob was assigned that task."

		# Existing first turn
		FollowUpMessage.objects.create(
			meeting=self.meeting,
			message_by="user",
			content="What was decided?",
		)
		FollowUpMessage.objects.create(
			meeting=self.meeting,
			message_by="ai",
			content="Deploy backend first.",
		)

		response = self.client.post(
			"/meeting/followup/",
			data={
				"meeting_id": str(self.meeting.Meeting_id),
				"question": "Who was assigned that task?",
			},
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 200)
		mock_answer.assert_called_once()
		_, kwargs = mock_answer.call_args
		self.assertEqual(len(kwargs["previous_messages"]), 2)
		self.assertEqual(kwargs["question"], "Who was assigned that task?")

	def test_ask_followup_missing_summary_fails(self):
		self.meeting.Summary = None
		self.meeting.save(update_fields=["Summary"])

		response = self.client.post(
			"/meeting/followup/",
			data={
				"meeting_id": str(self.meeting.Meeting_id),
				"question": "What happened?",
			},
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 400)
		self.assertIn("summary is not yet available", response.json().get("message", "").lower())

	def test_ask_followup_empty_question_fails(self):
		response = self.client.post(
			"/meeting/followup/",
			data={
				"meeting_id": str(self.meeting.Meeting_id),
				"question": "   ",
			},
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 400)
		self.assertIn("Question cannot be empty", response.json().get("message"))

	def test_ask_followup_invalid_meeting_fails(self):
		response = self.client.post(
			"/meeting/followup/",
			data={
				"meeting_id": "99999999-9999-9999-9999-999999999999",
				"question": "What happened?",
			},
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 404)

	def test_ask_followup_ai_disabled_fails(self):
		self.meeting.ai_enabled = False
		self.meeting.save(update_fields=["ai_enabled"])

		response = self.client.post(
			"/meeting/followup/",
			data={
				"meeting_id": str(self.meeting.Meeting_id),
				"question": "What happened?",
			},
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 400)
		self.assertIn("AI is disabled", response.json().get("message"))

	def test_get_followup_history_chronological(self):
		m1 = FollowUpMessage.objects.create(
			meeting=self.meeting,
			message_by="user",
			content="First question",
		)
		m2 = FollowUpMessage.objects.create(
			meeting=self.meeting,
			message_by="ai",
			content="First answer",
		)

		response = self.client.get(f"/meeting/followup/{self.meeting.Meeting_id}/")
		self.assertEqual(response.status_code, 200)
		messages = response.json().get("messages", [])
		self.assertEqual(len(messages), 2)
		self.assertEqual(messages[0]["content"], "First question")
		self.assertEqual(messages[1]["content"], "First answer")

	def test_followup_isolation_between_meetings(self):
		other_meeting = Meeting.objects.create(
			Meeting_id="55555555-5555-5555-5555-555555555555",
			Host_name="Charlie",
			Agenda="Secret Meeting",
			ai_enabled=True,
			Summary="Confidential",
		)
		FollowUpMessage.objects.create(
			meeting=other_meeting,
			message_by="user",
			content="Secret question",
		)

		response = self.client.get(f"/meeting/followup/{self.meeting.Meeting_id}/")
		messages = response.json().get("messages", [])
		self.assertEqual(len(messages), 0)

	@patch("Meeting.views._answer_followup_question", return_value="Speaker_001 discussed the budget.")
	def test_room_meeting_followup_endpoint(self, mock_answer):
		room_meeting = Meeting.objects.create(
			Meeting_id="66666666-6666-6666-6666-666666666666",
			Host_name="Central Device",
			Agenda="Budget Meeting",
			meeting_mode="room",
			ai_enabled=True,
			Summary="Budget discussion",
		)
		TranscriptEntry.objects.create(
			meeting=room_meeting,
			speaker_name="Speaker_001",
			text="The budget is approved.",
		)

		response = self.client.post(
			"/roomMeeting/followup/",
			data={
				"meeting_id": str(room_meeting.Meeting_id),
				"question": "What did Speaker_001 say?",
			},
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.json().get("success"))
		self.assertEqual(response.json()["ai_message"]["content"], "Speaker_001 discussed the budget.")




