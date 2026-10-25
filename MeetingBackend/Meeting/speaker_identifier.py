"""
Speaker Identifier Module.
Resolves anonymous diarization speaker clusters (e.g. SPEAKER_00, SPEAKER_01)
to registered participant identities by extracting voice embeddings, querying Pinecone,
and applying confidence and margin thresholds.
"""

import os
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
import numpy as np

try:
    import dotenv
    _base_dir = Path(__file__).resolve().parent.parent
    dotenv.load_dotenv(_base_dir / '.env')
    dotenv.load_dotenv(_base_dir.parent / '.env')
except ImportError:
    pass

from .speaker_index import query_speaker_embedding, get_pinecone_config
from .speaker_model import extract_speaker_embedding, normalize_vector, SAMPLE_RATE

logger = logging.getLogger(__name__)

# Default confidence thresholds (can be overridden via environment variables)
DEFAULT_SIMILARITY_THRESHOLD = 0.50
DEFAULT_CONFIDENCE_MARGIN = 0.05
MIN_SEGMENT_DURATION_SEC = 0.6  # Minimum turn duration to include for embedding


def get_thresholds():
    """Retrieves calibrated similarity threshold and confidence margin from environment."""
    try:
        sim_thresh = float(os.getenv("SPEAKER_SIMILARITY_THRESHOLD", DEFAULT_SIMILARITY_THRESHOLD))
    except (ValueError, TypeError):
        sim_thresh = DEFAULT_SIMILARITY_THRESHOLD

    try:
        conf_margin = float(os.getenv("SPEAKER_CONFIDENCE_MARGIN", DEFAULT_CONFIDENCE_MARGIN))
    except (ValueError, TypeError):
        conf_margin = DEFAULT_CONFIDENCE_MARGIN

    return sim_thresh, conf_margin


def aggregate_speaker_audio(
    audio_data: np.ndarray,
    turns: List[Dict[str, Any]],
    sample_rate: int = SAMPLE_RATE
) -> np.ndarray:
    """
    Concatenates usable speech segments belonging to a single speaker turn cluster.
    Filters out turns that are too short to avoid silence/noise artifacts.
    """
    slices = []
    total_samples = len(audio_data)

    # Sort turns chronologically
    sorted_turns = sorted(turns, key=lambda t: t["start"])

    for turn in sorted_turns:
        start_sec = turn["start"]
        end_sec = turn["end"]
        dur = end_sec - start_sec

        if dur < MIN_SEGMENT_DURATION_SEC:
            continue

        start_idx = max(0, int(start_sec * sample_rate))
        end_idx = min(total_samples, int(end_sec * sample_rate))

        if end_idx > start_idx:
            segment = audio_data[start_idx:end_idx]
            # Check for non-silence
            rms = np.sqrt(np.mean(segment ** 2)) if len(segment) > 0 else 0
            if rms > 1e-4:
                slices.append(segment)

    if not slices:
        # Fallback: if all turns were short, take the longest available turn
        longest_turn = max(sorted_turns, key=lambda t: t["end"] - t["start"]) if sorted_turns else None
        if longest_turn:
            start_idx = max(0, int(longest_turn["start"] * sample_rate))
            end_idx = min(total_samples, int(longest_turn["end"] * sample_rate))
            if end_idx > start_idx:
                slices.append(audio_data[start_idx:end_idx])

    if not slices:
        return np.array([], dtype=np.float32)

    return np.concatenate(slices).astype(np.float32)


def resolve_speaker_identities(
    audio_data: np.ndarray,
    diar_turns: List[Dict[str, Any]],
    speaker_mapping: Dict[str, str],
    sample_rate: int = SAMPLE_RATE,
    hf_token: Optional[str] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Identifies the registered participant for each diarized speaker cluster.

    Args:
        audio_data: 1D numpy array of meeting audio (16,000 Hz).
        diar_turns: List of turn dicts from pyannote [{'start': float, 'end': float, 'speaker': str}].
        speaker_mapping: Map from raw diarization label to anonymous label (e.g. {'SPEAKER_00': 'Speaker_001'}).
        sample_rate: Audio sample rate (default 16000).
        hf_token: Optional Hugging Face token.

    Returns:
        Dict mapping raw_speaker (e.g. 'SPEAKER_00') to identity resolution dictionary:
        {
            "display_name": "Gowtham" or "Speaker_001",
            "is_identified": bool,
            "confidence": float,
            "participant_id": str or None,
            "anonymous_label": "Speaker_001",
            "match_details": [...]
        }
    """
    results = {}
    sim_threshold, conf_margin = get_thresholds()

    # Group turns by raw speaker label
    turns_by_speaker: Dict[str, List[Dict[str, Any]]] = {}
    for turn in diar_turns:
        spk = turn["speaker"]
        turns_by_speaker.setdefault(spk, []).append(turn)

    logger.info(
        f"[SPEAKER_ID] Resolving identities for {len(turns_by_speaker)} diarized speaker(s). "
        f"Threshold: {sim_threshold:.2f}, Margin: {conf_margin:.2f}"
    )

    for raw_spk, turns in turns_by_speaker.items():
        anon_label = speaker_mapping.get(raw_spk, f"Speaker_{len(results)+1:03d}")

        # Default fallback
        resolved_info = {
            "display_name": f"Unknown — {anon_label}",
            "email": None,
            "is_identified": False,
            "confidence": 0.0,
            "participant_id": None,
            "anonymous_label": anon_label,
            "match_details": [],
        }

        # 1. Aggregate audio segments for this speaker
        speaker_audio = aggregate_speaker_audio(audio_data, turns, sample_rate=sample_rate)
        if len(speaker_audio) == 0:
            logger.warning(f"[SPEAKER_ID] No usable audio for '{raw_spk}'. Retaining {anon_label}.")
            results[raw_spk] = resolved_info
            continue

        # 2. Extract speaker embedding
        try:
            embedding = extract_speaker_embedding(speaker_audio, sample_rate=sample_rate, hf_token=hf_token)
            if embedding is None:
                logger.warning(f"[SPEAKER_ID] Could not extract embedding for '{raw_spk}'. Retaining {anon_label}.")
                results[raw_spk] = resolved_info
                continue
        except Exception as emb_exc:
            logger.error(f"[SPEAKER_ID] Embedding extraction failed for '{raw_spk}': {emb_exc}")
            results[raw_spk] = resolved_info
            continue

        # 3. Query Pinecone for enrolled profiles
        try:
            matches = query_speaker_embedding(embedding.tolist(), top_k=5)
        except Exception as query_exc:
            logger.warning(
                f"[SPEAKER_ID] Pinecone query failed for '{raw_spk}': {query_exc}. "
                f"Gracefully falling back to anonymous label {anon_label}."
            )
            results[raw_spk] = resolved_info
            continue

        if not matches:
            logger.info(f"[SPEAKER_ID] No enrolled candidates matched for '{raw_spk}'. Retaining {anon_label}.")
            results[raw_spk] = resolved_info
            continue

        # 4. Group matches by participant name (to support multiple samples per participant)
        participant_scores: Dict[str, Dict[str, Any]] = {}
        for m in matches:
            meta = m.get("metadata", {})
            name = meta.get("name") or "Unknown"
            email = meta.get("email") or meta.get("participant_id")
            score = float(m.get("score", 0.0))

            if name not in participant_scores:
                participant_scores[name] = {
                    "max_score": score,
                    "email": email,
                    "scores": [score],
                    "sample_ids": [meta.get("sample_id")]
                }
            else:
                participant_scores[name]["scores"].append(score)
                if score > participant_scores[name]["max_score"]:
                    participant_scores[name]["max_score"] = score
                    participant_scores[name]["email"] = email

        # Sort candidate participants by highest similarity score
        ranked_candidates = sorted(
            participant_scores.items(),
            key=lambda item: item[1]["max_score"],
            reverse=True
        )

        top_name, top_data = ranked_candidates[0]
        top_score = top_data["max_score"]
        second_score = ranked_candidates[1][1]["max_score"] if len(ranked_candidates) > 1 else 0.0

        margin = top_score - second_score
        logger.info(
            f"[SPEAKER_ID] Candidate evaluation for '{raw_spk}': "
            f"Top='{top_name}' (score={top_score:.4f}), Second='{ranked_candidates[1][0] if len(ranked_candidates) > 1 else 'None'}' "
            f"(score={second_score:.4f}), Margin={margin:.4f}"
        )

        # 5. Apply similarity threshold and confidence margin
        if top_score >= sim_threshold and (len(ranked_candidates) == 1 or margin >= conf_margin):
            logger.info(
                f"[SPEAKER_ID] MATCH CONFIRMED: '{raw_spk}' ({anon_label}) -> '{top_name}' "
                f"(score={top_score:.4f}, margin={margin:.4f})"
            )
            resolved_info["display_name"] = top_name
            resolved_info["email"] = top_data["email"]
            resolved_info["is_identified"] = True
            resolved_info["confidence"] = round(top_score, 4)
            resolved_info["participant_id"] = top_data["email"]
            resolved_info["match_details"] = ranked_candidates
        else:
            logger.info(
                f"[SPEAKER_ID] Match inconclusive for '{raw_spk}': top_score={top_score:.4f} "
                f"(thresh={sim_threshold:.2f}), margin={margin:.4f} (req={conf_margin:.2f}). "
                f"Retaining anonymous label '{anon_label}'."
            )
            resolved_info["display_name"] = f"Unknown — {anon_label}"
            resolved_info["email"] = None
            resolved_info["is_identified"] = False
            resolved_info["confidence"] = round(top_score, 4)
            resolved_info["match_details"] = ranked_candidates

        results[raw_spk] = resolved_info

    return results
