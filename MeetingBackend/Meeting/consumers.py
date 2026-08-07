from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import json

# Room registry: { room_name: { channel_name: display_name } }
# Stored at class level so all consumer instances share it.
ROOMS = {}


class MyConsumer(AsyncWebsocketConsumer):

    # ------------------------------------------------------------------ #
    #  Connection lifecycle                                                #
    # ------------------------------------------------------------------ #

    async def connect(self):
        self.room_name = self.scope["url_route"]["kwargs"]["id"]
        self.display_name = None  # Set when the Join message arrives

        # Register channel in the Channels layer group
        await self.channel_layer.group_add(self.room_name, self.channel_name)

        # Ensure the room dict exists
        if self.room_name not in ROOMS:
            ROOMS[self.room_name] = {}

        await self.accept()
        print(f"[CONNECT] channel={self.channel_name} room={self.room_name}")

    async def disconnect(self, close_code):
        print(f"[DISCONNECT] channel={self.channel_name} name={self.display_name}")

        # Remove from room registry
        room = ROOMS.get(self.room_name, {})
        room.pop(self.channel_name, None)

        # Notify remaining participants so they can remove the tile
        if self.display_name:
            await self.channel_layer.group_send(
                self.room_name,
                {
                    "type": "send_leave",
                    "name": self.display_name,
                    "channel_name": self.channel_name,
                },
            )

        await self.channel_layer.group_discard(self.room_name, self.channel_name)

        # Automatically clean up the meeting from the database when participant count == 0
        if len(room) == 0:
            ROOMS.pop(self.room_name, None)
            await self._cleanup_meeting_if_empty(self.room_name)


    # ------------------------------------------------------------------ #
    #  Receive — dispatch by message type                                  #
    # ------------------------------------------------------------------ #

    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data.get("message")
        print(f"[RECEIVE] type={message} from={self.channel_name}")

        if message == "Join":
            await self.handle_join(data)
        elif message == "Offer":
            await self.handle_offer(data)
        elif message == "Answer":
            await self.handle_answer(data)
        elif message == "Candidate":
            await self.handle_candidate(data)
        elif message == "Transcript":
            await self.handle_transcript(data)

    # ------------------------------------------------------------------ #
    #  Signaling handlers                                                  #
    # ------------------------------------------------------------------ #

    async def handle_join(self, data):
        """
        A new participant announces themselves.
        1. Register them in the room.
        2. Tell every *existing* participant about the newcomer so that
           each of them initiates an Offer to the newcomer.
        """
        name = data.get("name")
        self.display_name = name

        room = ROOMS[self.room_name]

        # Collect existing participants BEFORE adding the newcomer
        existing = dict(room)

        # Register newcomer
        room[self.channel_name] = name

        print(f"[JOIN] {name} joined room {self.room_name}. Existing: {list(existing.values())}")

        # Notify each existing participant — they will send an Offer to the newcomer
        for ch, participant_name in existing.items():
            await self.channel_layer.send(
                ch,
                {
                    "type": "send_new_peer",
                    "new_peer_name": name,
                },
            )

    async def handle_offer(self, data):
        """
        Route an Offer from sender to a specific receiver (by name).
        Never broadcast to the whole group.
        """
        sender = data.get("sender")
        receiver_name = data.get("receiver")
        offer = data.get("PeerOffer")

        receiver_channel = self._resolve_channel(receiver_name)
        if not receiver_channel:
            print(f"[OFFER] Could not resolve channel for receiver={receiver_name}")
            return

        print(f"[OFFER] {sender} → {receiver_name}")
        await self.channel_layer.send(
            receiver_channel,
            {
                "type": "send_offer",
                "sender": sender,
                "offer": offer,
            },
        )

    async def handle_answer(self, data):
        """
        Route an Answer from sender to a specific receiver (by name).
        """
        sender = data.get("sender")
        receiver_name = data.get("receiver")
        answer = data.get("answer")

        receiver_channel = self._resolve_channel(receiver_name)
        if not receiver_channel:
            print(f"[ANSWER] Could not resolve channel for receiver={receiver_name}")
            return

        print(f"[ANSWER] {sender} → {receiver_name}")
        await self.channel_layer.send(
            receiver_channel,
            {
                "type": "send_answer",
                "sender": sender,
                "answer": answer,
            },
        )

    async def handle_candidate(self, data):
        """
        Route an ICE candidate from sender to a specific receiver (by name).
        """
        sender = data.get("sender")
        receiver_name = data.get("receiver")
        candidate = data.get("candidate")

        receiver_channel = self._resolve_channel(receiver_name)
        if not receiver_channel:
            print(f"[CANDIDATE] Could not resolve channel for receiver={receiver_name}")
            return

        await self.channel_layer.send(
            receiver_channel,
            {
                "type": "send_candidate",
                "sender": sender,
                "candidate": candidate,
            },
        )

    async def handle_transcript(self, data):
        """
        A participant sends a transcript entry (from their local SpeechRecognition).
        1. Persist the entry to the database.
        2. Broadcast it to every participant in the room (including sender).
        """
        speaker = data.get("speaker", self.display_name or "Unknown")
        speaker_id = data.get("speaker_id", "")
        text = data.get("text", "").strip()
        meeting_id = self.room_name

        if not text:
            return

        # Persist to DB
        entry = await self._save_transcript_entry(meeting_id, speaker, speaker_id, text)
        if entry is None:
            # Silently ignore transcripts after meeting ended or when AI is disabled
            return

        print(f"[TRANSCRIPT] {speaker}: {text[:60]}")

        # Broadcast to the whole room group
        await self.channel_layer.group_send(
            self.room_name,
            {
                "type": "send_transcript",
                "id": entry["id"],
                "speaker": speaker,
                "speaker_id": speaker_id,
                "text": text,
                "timestamp": entry["timestamp"],
            },
        )

    # ------------------------------------------------------------------ #
    #  Channel layer event handlers (called by group_send / send)         #
    # ------------------------------------------------------------------ #

    async def send_new_peer(self, event):
        """Tell this client that a new peer just joined — they should send an Offer."""
        await self.send(text_data=json.dumps({
            "message": "NewPeer",
            "name": event["new_peer_name"],
        }))

    async def send_offer(self, event):
        """Deliver an Offer to this client."""
        await self.send(text_data=json.dumps({
            "message": "Offer",
            "sender": event["sender"],
            "PeerOffer": event["offer"],
        }))

    async def send_answer(self, event):
        """Deliver an Answer to this client."""
        await self.send(text_data=json.dumps({
            "message": "Answer",
            "sender": event["sender"],
            "answer": event["answer"],
        }))

    async def send_candidate(self, event):
        """Deliver an ICE Candidate to this client."""
        await self.send(text_data=json.dumps({
            "message": "Candidate",
            "sender": event["sender"],
            "candidate": event["candidate"],
        }))

    async def send_leave(self, event):
        """Notify remaining clients that a participant left."""
        # Don't send to the leaving participant's own channel
        if self.channel_name == event["channel_name"]:
            return
        await self.send(text_data=json.dumps({
            "message": "Leave",
            "name": event["name"],
        }))

    async def send_transcript(self, event):
        """Broadcast a transcript entry to this client."""
        await self.send(text_data=json.dumps({
            "message": "Transcript",
            "id": event.get("id"),
            "speaker": event["speaker"],
            "speaker_id": event.get("speaker_id", ""),
            "text": event["text"],
            "timestamp": event["timestamp"],
        }))

    async def send_transcript_update(self, event):
        """Broadcast an edited transcript update to this client."""
        await self.send(text_data=json.dumps({
            "message": "TranscriptUpdate",
            "id": event["id"],
            "text": event["text"],
        }))

    async def send_meeting_ended(self, event):
        """Notify clients that the meeting has ended."""
        await self.send(text_data=json.dumps({
            "message": "MeetingEnded",
        }))


    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _resolve_channel(self, display_name):
        """Return the channel_name for a given display_name in this room."""
        room = ROOMS.get(self.room_name, {})
        for ch, name in room.items():
            if name == display_name:
                return ch
        return None

    @database_sync_to_async
    def _save_transcript_entry(self, meeting_id, speaker, speaker_id, text):
        """
        Persist a TranscriptEntry synchronously (called via database_sync_to_async).
        Returns a dict with the saved entry data, or None if meeting not found/AI disabled.
        """
        from .models import Meeting, TranscriptEntry
        try:
            meeting = Meeting.objects.get(Meeting_id=meeting_id)
            if not meeting.ai_enabled or not meeting.Status:
                return None
            entry = TranscriptEntry.objects.create(
                meeting=meeting,
                speaker_name=speaker,
                speaker_id=speaker_id,
                text=text,
            )
            return {
                "id": entry.pk,
                "speaker": entry.speaker_name,
                "speaker_id": entry.speaker_id,
                "text": entry.text,
                "timestamp": entry.timestamp.isoformat(),
            }
        except Meeting.DoesNotExist:
            return None

    @database_sync_to_async
    def _cleanup_meeting_if_empty(self, meeting_id):
        """Clean up the meeting record when all participants have left."""
        from .models import Meeting
        try:
            Meeting.objects.filter(Meeting_id=meeting_id).delete()
            print(f"[CLEANUP] Meeting {meeting_id} deleted (0 participants remaining).")
        except Exception as exc:
            print(f"[CLEANUP] Error deleting meeting {meeting_id}: {exc}")