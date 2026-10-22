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
	def test_end_meeting_missing_gemini_api_key_returns_clear_error(self):
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
				"message": "GEMINI_API_KEY is not configured",
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


class GeminiSummarizationUnitTests(TestCase):
	@patch.dict("os.environ", {}, clear=True)
	def test_call_gemini_missing_api_key(self):
		from Meeting.views import _call_gemini
		with self.assertRaises(RuntimeError) as ctx:
			_call_gemini("Test prompt")
		self.assertIn("GEMINI_API_KEY is not configured", str(ctx.exception))

	@patch("Meeting.views.genai.Client")
	@patch.dict("os.environ", {"GEMINI_API_KEY": "test_gemini_key", "GEMINI_MODEL": "gemini-2.5-flash"})
	def test_call_gemini_success(self, mock_client_cls):
		from Meeting.views import _call_gemini
		mock_client = mock_client_cls.return_value
		mock_response = type("MockResponse", (), {"text": "1. Meeting Overview\nEverything went well."})()
		mock_client.models.generate_content.return_value = mock_response

		result = _call_gemini("Summarize this meeting")
		self.assertEqual(result, "1. Meeting Overview\nEverything went well.")
		mock_client_cls.assert_called_once_with(api_key="test_gemini_key")
		self.assertEqual(mock_client.models.generate_content.call_count, 1)
		_, kwargs = mock_client.models.generate_content.call_args
		self.assertEqual(kwargs["model"], "gemini-2.5-flash")
		self.assertEqual(len(kwargs["contents"]), 1)
		self.assertEqual(kwargs["contents"][0].parts[0].text, "Summarize this meeting")
		self.assertIsNone(kwargs.get("config"))

	@patch("Meeting.views.genai.Client")
	@patch.dict("os.environ", {"GEMINI_API_KEY": "test_gemini_key"})
	def test_call_gemini_empty_response(self, mock_client_cls):
		from Meeting.views import _call_gemini
		mock_client = mock_client_cls.return_value
		mock_response = type("MockResponse", (), {"text": ""})()
		mock_client.models.generate_content.return_value = mock_response

		with self.assertRaises(RuntimeError) as ctx:
			_call_gemini("Summarize this meeting")
		self.assertIn("Unexpected Gemini response", str(ctx.exception))

	@patch.dict("os.environ", {}, clear=True)
	def test_ask_followup_missing_gemini_api_key_returns_clear_error(self):
		meeting = Meeting.objects.create(
			Meeting_id="77777777-7777-7777-7777-777777777777",
			Host_name="Alice",
			Agenda="Test Agenda",
			Status=False,
			ai_enabled=True,
			Summary="Meeting Overview:\nDiscussed Q3 release.",
		)
		TranscriptEntry.objects.create(
			meeting=meeting,
			speaker_name="Alice",
			text="Let's release on Friday.",
		)

		response = self.client.post(
			"/meeting/followup/",
			data={
				"meeting_id": str(meeting.Meeting_id),
				"question": "What was the release date?",
			},
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json().get("message"), "GEMINI_API_KEY is not configured")

	@patch("Meeting.views.genai.Client")
	@patch.dict("os.environ", {"GEMINI_API_KEY": "test_gemini_key", "GEMINI_MODEL": "gemini-2.5-flash"})
	def test_answer_followup_question_gemini_call(self, mock_client_cls):
		from Meeting.views import _answer_followup_question
		mock_client = mock_client_cls.return_value
		mock_response = type("MockResponse", (), {"text": "The release is on Friday."})()
		mock_client.models.generate_content.return_value = mock_response

		reply = _answer_followup_question(
			agenda="Ship release",
			summary="Summary overview",
			transcript_text="Alice: Release on Friday.",
			previous_messages=[],
			question="When is the release?",
		)

		self.assertEqual(reply, "The release is on Friday.")
		mock_client_cls.assert_called_once_with(api_key="test_gemini_key")
		self.assertEqual(mock_client.models.generate_content.call_count, 1)
		_, kwargs = mock_client.models.generate_content.call_args
		self.assertEqual(kwargs["model"], "gemini-2.5-flash")
		self.assertIsNotNone(kwargs.get("config"))


class ParticipantAndReportTests(TestCase):
	def setUp(self):
		self.video_meeting = Meeting.objects.create(
			Meeting_id="22222222-2222-2222-2222-222222222222",
			Host_name="Alice Host",
			Agenda="Quarterly Review",
			Status=True,
			ai_enabled=True,
			meeting_mode="video",
			Summary="1. Meeting Overview\nQuarterly goals achieved.\n\n2. Key Points\n- Revenue up 20%",
		)
		self.room_meeting = Meeting.objects.create(
			Meeting_id="33333333-3333-3333-3333-333333333333",
			Host_name="Conference Room A",
			Agenda="Architecture Discussion",
			Status=True,
			ai_enabled=True,
			meeting_mode="room",
			Summary="1. Meeting Overview\nMigrating to microservices.\n\n2. Decisions Made\n- Use gRPC",
		)

	def test_video_join_registers_participant_email(self):
		response = self.client.post(
			"/JoinMeeting/",
			data={
				"id": str(self.video_meeting.Meeting_id),
				"name": "Bob Participant",
				"email": "bob@example.com",
			},
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.json()["success"])

		# Verify participant was saved to database
		from Meeting.models import MeetingParticipant
		p = MeetingParticipant.objects.filter(meeting=self.video_meeting, email="bob@example.com").first()
		self.assertIsNotNone(p)
		self.assertEqual(p.name, "Bob Participant")

	def test_video_join_avoids_duplicate_participants(self):
		from Meeting.models import MeetingParticipant
		# Join twice with same email
		self.client.post(
			"/JoinMeeting/",
			data={"id": str(self.video_meeting.Meeting_id), "name": "Bob", "email": "bob@example.com"},
			content_type="application/json",
		)
		self.client.post(
			"/JoinMeeting/",
			data={"id": str(self.video_meeting.Meeting_id), "name": "Bob Updated", "email": "bob@example.com"},
			content_type="application/json",
		)
		# Count should be exactly 1
		count = MeetingParticipant.objects.filter(meeting=self.video_meeting, email="bob@example.com").count()
		self.assertEqual(count, 1)

	def test_room_participant_setup_valid(self):
		response = self.client.post(
			"/roomMeeting/participants/",
			data={
				"meeting_id": str(self.room_meeting.Meeting_id),
				"participant_count": 3,
				"emails": ["user1@example.com", "user2@example.com", "user3@example.com"],
			},
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertTrue(data["success"])
		self.assertEqual(len(data["participants"]), 3)

	def test_room_participant_setup_invalid_count(self):
		# Count 0 should fail
		response = self.client.post(
			"/roomMeeting/participants/",
			data={"meeting_id": str(self.room_meeting.Meeting_id), "participant_count": 0, "emails": []},
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 400)

		# Mismatched count and emails length should fail
		response2 = self.client.post(
			"/roomMeeting/participants/",
			data={"meeting_id": str(self.room_meeting.Meeting_id), "participant_count": 2, "emails": ["a@example.com"]},
			content_type="application/json",
		)
		self.assertEqual(response2.status_code, 400)

	def test_room_participant_setup_duplicate_emails(self):
		response = self.client.post(
			"/roomMeeting/participants/",
			data={
				"meeting_id": str(self.room_meeting.Meeting_id),
				"participant_count": 2,
				"emails": ["same@example.com", "SAME@example.com"],
			},
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 400)
		self.assertIn("Duplicate", response.json()["message"])

	def test_room_participant_setup_invalid_email_format(self):
		response = self.client.post(
			"/roomMeeting/participants/",
			data={
				"meeting_id": str(self.room_meeting.Meeting_id),
				"participant_count": 1,
				"emails": ["not-an-email"],
			},
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 400)
		self.assertIn("valid email", response.json()["message"].lower())

	def test_meeting_report_data_endpoint(self):
		from Meeting.models import MeetingParticipant, FollowUpMessage
		MeetingParticipant.objects.create(
			meeting=self.video_meeting,
			email="alice@example.com",
			name="Alice",
		)
		FollowUpMessage.objects.create(
			meeting=self.video_meeting,
			message_by="user",
			content="What was the conclusion?",
		)
		FollowUpMessage.objects.create(
			meeting=self.video_meeting,
			message_by="ai",
			content="Revenue is up 20%.",
		)

		response = self.client.get(f"/meeting/report/{self.video_meeting.Meeting_id}/")
		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertTrue(data["success"])
		self.assertEqual(len(data["participants"]), 1)
		self.assertEqual(len(data["follow_up_messages"]), 2)
		self.assertIn("Quarterly goals achieved", data["summary"])

	def test_send_report_email_success_and_recipient_privacy(self):
		from django.core import mail
		from Meeting.models import MeetingParticipant, FollowUpMessage
		# Register two participants
		MeetingParticipant.objects.create(
			meeting=self.video_meeting,
			email="first@example.com",
			name="First User",
		)
		MeetingParticipant.objects.create(
			meeting=self.video_meeting,
			email="second@example.com",
			name="Second User",
		)
		FollowUpMessage.objects.create(
			meeting=self.video_meeting,
			message_by="user",
			content="Question 1?",
		)

		mail.outbox.clear()

		response = self.client.post(
			"/meeting/send-report/",
			data={"meeting_id": str(self.video_meeting.Meeting_id)},
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.json()["success"])
		self.assertEqual(response.json()["sent_count"], 2)

		# Verify emails in Django test outbox
		self.assertEqual(len(mail.outbox), 2)

		# Verify recipient privacy: each message is sent ONLY to that individual recipient
		recipients_in_messages = [msg.to for msg in mail.outbox]
		self.assertIn(["first@example.com"], recipients_in_messages)
		self.assertIn(["second@example.com"], recipients_in_messages)
		for msg in mail.outbox:
			# Verify no CC or BCC leakage
			self.assertEqual(len(msg.to), 1)
			self.assertEqual(len(msg.cc), 0)
			# Verify PDF attachment
			self.assertEqual(len(msg.attachments), 1)
			filename, content, mimetype = msg.attachments[0]
			self.assertTrue(filename.endswith(".pdf"))
			self.assertEqual(mimetype, "application/pdf")
			self.assertGreater(len(content), 1000)

	def test_send_report_without_summary_fails(self):
		meeting_no_summary = Meeting.objects.create(
			Meeting_id="44444444-4444-4444-4444-444444444444",
			Host_name="No Summary",
			Agenda="Draft",
			Status=True,
		)
		from Meeting.models import MeetingParticipant
		MeetingParticipant.objects.create(
			meeting=meeting_no_summary,
			email="user@example.com",
		)

		response = self.client.post(
			"/meeting/send-report/",
			data={"meeting_id": str(meeting_no_summary.Meeting_id)},
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 400)
		self.assertIn("summary is not available", response.json()["message"].lower())

	def test_send_report_no_participants_fails(self):
		response = self.client.post(
			"/roomMeeting/send-report/",
			data={"meeting_id": str(self.room_meeting.Meeting_id)},
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 400)
		self.assertIn("no participant email", response.json()["message"].lower())

	def test_download_report_pdf_endpoint(self):
		response = self.client.get(f"/meeting/download-report/{self.video_meeting.Meeting_id}/")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response["Content-Type"], "application/pdf")
		self.assertIn("attachment; filename=", response["Content-Disposition"])
		self.assertGreater(len(response.content), 1000)


