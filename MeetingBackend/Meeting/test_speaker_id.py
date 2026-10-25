"""
Comprehensive Test Suite for Speaker Identification Integration.
Tests all requirements: Pinecone index validation, audio loading, embedding extraction,
short/silent rejection, filename metadata parsing, multi-sample enrollment, idempotency,
matching against enrolled participants, unknown/ambiguous speaker rejection,
and transcript format preservation.
"""

import os
import sys
import unittest
import numpy as np
import torch
from pathlib import Path

# Setup paths
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

try:
    import dotenv
    dotenv.load_dotenv(BASE_DIR / ".env")
    dotenv.load_dotenv(BASE_DIR.parent / ".env")
except ImportError:
    pass

from Meeting.speaker_index import (
    get_or_create_speaker_index,
    get_pinecone_config,
    query_speaker_embedding,
    upsert_speaker_embedding,
    EMBEDDING_DIMENSION,
    SIMILARITY_METRIC,
)
from Meeting.speaker_model import (
    extract_speaker_embedding,
    normalize_vector,
    SAMPLE_RATE,
    MIN_AUDIO_DURATION_SEC,
)
from Meeting.speaker_identifier import (
    resolve_speaker_identities,
    get_thresholds,
)
from Meeting.audio_processor import load_audio_file, normalize_speaker_label
from store_voices import parse_filename, generate_deterministic_vector_id, DEFAULT_VOICES_DIR


class SpeakerIdentificationTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.voices_dir = DEFAULT_VOICES_DIR
        cls.gowtham_sample1 = cls.voices_dir / "gowtham_gowthamsasanapuri@gmail.com.wav"
        cls.gowtham_sample2 = cls.voices_dir / "gowtham_gowthamsasanapuri.personal@gmail.com.wav"
        cls.navya_sample = cls.voices_dir / "navya_Pittanavya0@gmail.com.wav"
        cls.bhuvan_sample = cls.voices_dir / "bhuvan_23341a05p3@gmail.com.wav"

    def test_01_pinecone_index_validation(self):
        """1. Verify Pinecone index exists, has correct dimension (256) and metric (cosine)."""
        cfg = get_pinecone_config()
        self.assertEqual(cfg["dimension"], 256)
        self.assertEqual(cfg["metric"], "cosine")
        self.assertEqual(cfg["index_name"], "meeting-speakers")

        index = get_or_create_speaker_index(create_if_missing=False)
        self.assertIsNotNone(index)
        stats = index.describe_index_stats()
        self.assertIn("namespaces", stats)
        print(" [PASS] test_01_pinecone_index_validation: Index is online and validated.")

    def test_02_load_existing_wav_file(self):
        """2. Verify loading actual WAV file from Voices folder via load_audio_file."""
        self.assertTrue(self.gowtham_sample1.is_file(), f"Missing file {self.gowtham_sample1}")
        audio = load_audio_file(str(self.gowtham_sample1))
        self.assertIsInstance(audio, np.ndarray)
        self.assertEqual(audio.dtype, np.float32)
        duration = len(audio) / SAMPLE_RATE
        self.assertGreater(duration, 10.0, "Sample recording duration should be > 10s")
        print(f" [PASS] test_02_load_existing_wav_file: Loaded {len(audio)} samples ({duration:.2f}s).")

    def test_03_extract_valid_speaker_embedding(self):
        """3. Extract 256-dimensional unit-normalized embedding from actual voice file."""
        emb = extract_speaker_embedding(str(self.gowtham_sample1))
        self.assertIsNotNone(emb)
        self.assertEqual(len(emb), 256)
        self.assertTrue(np.isfinite(emb).all(), "Embedding must contain only finite numbers")
        norm = np.linalg.norm(emb)
        self.assertAlmostEqual(norm, 1.0, places=3, msg="Embedding must be L2 unit-normalized")
        print(" [PASS] test_03_extract_valid_speaker_embedding: Extracted finite 256-dim unit vector.")

    def test_04_handle_invalid_silent_or_short_audio(self):
        """4. Verify safe rejection of empty, too-short (<0.5s), and silent audio."""
        # Empty array
        res_empty = extract_speaker_embedding(np.array([], dtype=np.float32))
        self.assertIsNone(res_empty, "Empty audio must return None")

        # Too short (<0.5s = <8000 samples at 16kHz)
        short_audio = np.random.randn(int(0.3 * SAMPLE_RATE)).astype(np.float32) * 0.1
        res_short = extract_speaker_embedding(short_audio)
        self.assertIsNone(res_short, "Audio shorter than minimum duration must return None")

        # Silence (all zeros)
        silent_audio = np.zeros(int(2.0 * SAMPLE_RATE), dtype=np.float32)
        res_silent = extract_speaker_embedding(silent_audio)
        self.assertIsNone(res_silent, "Silent audio must return None")
        print(" [PASS] test_04_handle_invalid_silent_or_short_audio: Safely handled without crashing.")

    def test_05_metadata_filename_parsing(self):
        """5. Safely parse names and emails including spaces, underscores, and detect unparseable files."""
        # Standard convention
        name1, email1 = parse_filename("gowtham_gowthamsasanapuri@gmail.com.wav")
        self.assertEqual(name1, "Gowtham")
        self.assertEqual(email1, "gowthamsasanapuri@gmail.com")

        # Name with spaces/underscores
        name2, email2 = parse_filename("John_Doe_john.doe@enterprise.com.wav")
        self.assertEqual(name2, "John Doe")
        self.assertEqual(email2, "john.doe@enterprise.com")

        # Case normalization
        name3, email3 = parse_filename("navya_Pittanavya0@gmail.com.wav")
        self.assertEqual(name3, "Navya")
        self.assertEqual(email3, "pittanavya0@gmail.com")

        # Unparseable (no email symbol)
        with self.assertRaises(ValueError):
            parse_filename("unknown_audio_file.wav")

        # Unparseable (no name prefix)
        with self.assertRaises(ValueError):
            parse_filename("_justemail@domain.com.wav")

        print(" [PASS] test_05_metadata_filename_parsing: Parsed expected and rejected ambiguous filenames.")

    def test_06_and_07_deterministic_ids_and_idempotency(self):
        """6 & 7. Deterministic vector IDs support multiple samples for same participant without duplicate vectors."""
        id1 = generate_deterministic_vector_id("gowtham@example.com", "gowtham_sample1.wav")
        id2 = generate_deterministic_vector_id("gowtham@example.com", "gowtham_sample2.wav")
        id1_repeat = generate_deterministic_vector_id("gowtham@example.com", "gowtham_sample1.wav")

        # Same file gives identical deterministic ID (idempotency)
        self.assertEqual(id1, id1_repeat)
        # Different samples give distinct IDs under same participant
        self.assertNotEqual(id1, id2)
        self.assertTrue(id1.startswith("spk_gowtham_example_com_"))
        self.assertTrue(id2.startswith("spk_gowtham_example_com_"))
        print(" [PASS] test_06_and_07_deterministic_ids_and_idempotency: Deterministic IDs verified.")

    def test_08_match_recording_against_enrolled_participant(self):
        """8. Match audio segment from enrolled participant with high similarity and correct identity."""
        # Extract embedding from Navya's recording
        emb = extract_speaker_embedding(str(self.navya_sample))
        self.assertIsNotNone(emb)

        matches = query_speaker_embedding(emb.tolist(), top_k=3)
        self.assertGreater(len(matches), 0, "Query should return enrolled candidates")

        top_match = matches[0]
        self.assertEqual(top_match["metadata"]["name"], "Navya")
        self.assertGreater(top_match["score"], 0.75, "Top match score for enrolled participant should be > 0.75")
        print(f" [PASS] test_08_match_recording_against_enrolled_participant: Top match: {top_match['metadata']['name']} (score={top_match['score']:.4f}).")

    def test_09_reject_unknown_or_ambiguous_speaker(self):
        """9. Unknown or ambiguous speaker must NOT receive an arbitrary registered name."""
        # Create a synthetic orthogonal vector representing an unknown speaker
        synthetic_vector = np.random.randn(256).astype(np.float32)
        synthetic_vector = normalize_vector(synthetic_vector)

        matches = query_speaker_embedding(synthetic_vector.tolist(), top_k=3)
        sim_thresh, conf_margin = get_thresholds()

        # Check resolution logic for unknown speaker
        diar_turns = [{"start": 1.0, "end": 4.0, "speaker": "SPEAKER_99"}]
        speaker_mapping = {"SPEAKER_99": "Speaker_099"}
        
        # Audio array of random noise representing unknown speaker
        dummy_audio = np.random.randn(SAMPLE_RATE * 5).astype(np.float32) * 0.05

        results = resolve_speaker_identities(
            audio_data=dummy_audio,
            diar_turns=diar_turns,
            speaker_mapping=speaker_mapping
        )

        spk_res = results["SPEAKER_99"]
        self.assertFalse(spk_res["is_identified"], "Unknown/noise audio must not be confirmed as registered")
        self.assertEqual(spk_res["display_name"], "Unknown — Speaker_099", "Display name must retain Unknown — label")
        self.assertIsNone(spk_res["email"], "Unregistered speaker must not have an email assigned")
        print(" [PASS] test_09_reject_unknown_or_ambiguous_speaker: Unregistered speaker retained anonymous label.")

    def test_10_transcript_response_format_and_fallback(self):
        """10. Preserves transcript schema, speaker name, anonymous fallback, and display format."""
        speaker_mapping = {"SPEAKER_00": "Speaker_001"}
        dummy_audio = np.zeros(SAMPLE_RATE * 2, dtype=np.float32)
        diar_turns = [{"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}]

        # Silent audio triggers graceful fallback to anonymous label
        results = resolve_speaker_identities(
            audio_data=dummy_audio,
            diar_turns=diar_turns,
            speaker_mapping=speaker_mapping
        )

        self.assertIn("SPEAKER_00", results)
        res = results["SPEAKER_00"]
        self.assertEqual(res["display_name"], "Unknown — Speaker_001")
        self.assertFalse(res["is_identified"])
        self.assertEqual(res["anonymous_label"], "Speaker_001")
        self.assertIsNone(res["email"])
        print(" [PASS] test_10_transcript_response_format_and_fallback: Verified fallback format.")

    def test_11_automatic_identification_with_registered_name_and_email(self):
        """11. Complete pipeline identification returns registered name and email ID for enrolled participant."""
        audio = load_audio_file(str(self.bhuvan_sample))
        diar_turns = [{"start": 1.0, "end": 15.0, "speaker": "SPEAKER_00"}]
        speaker_mapping = {"SPEAKER_00": "Speaker_001"}

        results = resolve_speaker_identities(
            audio_data=audio,
            diar_turns=diar_turns,
            speaker_mapping=speaker_mapping
        )

        self.assertIn("SPEAKER_00", results)
        bhuvan_res = results["SPEAKER_00"]
        self.assertTrue(bhuvan_res["is_identified"], "Bhuvan audio must be positively identified")
        self.assertEqual(bhuvan_res["display_name"], "Bhuvan")
        self.assertEqual(bhuvan_res["email"], "23341a05p3@gmail.com")
        self.assertGreater(bhuvan_res["confidence"], 0.70)
        print(f" [PASS] test_11_automatic_identification_with_registered_name_and_email: {bhuvan_res['display_name']} ({bhuvan_res['email']}), score={bhuvan_res['confidence']:.4f}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
