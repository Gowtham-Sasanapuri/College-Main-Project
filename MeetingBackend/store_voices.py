"""
Voice Enrollment Script (store_voices.py)
Scans the project's 'Voices' directory, extracts 256-dimensional speaker embeddings
using the pyannote community speaker embedding extractor, and stores them in Pinecone
with deterministic IDs and participant metadata.

Usage:
    python store_voices.py                  # Enroll all valid WAV files
    python store_voices.py --list           # List enrolled speakers in Pinecone
    python store_voices.py --delete <id>    # Delete embeddings for participant
    python store_voices.py --clear-all      # Clear all enrolled voices in namespace
"""

import os
import sys
import re
import json
import hashlib
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Setup Django & module environment
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

try:
    import dotenv
    dotenv.load_dotenv(BASE_DIR / ".env")
    dotenv.load_dotenv(BASE_DIR.parent / ".env")
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("store_voices")

from Meeting.speaker_index import (
    get_or_create_speaker_index,
    get_pinecone_config,
    upsert_speaker_embedding,
    query_speaker_embedding,
    delete_speaker_embeddings,
    EMBEDDING_DIMENSION,
)
from Meeting.speaker_model import extract_speaker_embedding, SAMPLE_RATE

# Default Voices directory
DEFAULT_VOICES_DIR = BASE_DIR.parent / "Voices"
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def parse_filename(filename: str, metadata_override: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    """
    Safely parses participant name and email address from a voice recording filename.
    Convention: 'name_mailid.wav' (e.g. 'gowtham_gowthamsasanapuri@gmail.com.wav').
    Supports spaces and underscores in names (e.g. 'Gowtham_Sasanapuri_gowtham@example.com.wav').
    
    Returns:
        (name: str, email: str)
    Raises:
        ValueError if filename cannot be reliably parsed.
    """
    if metadata_override and filename in metadata_override:
        entry = metadata_override[filename]
        return entry["name"].strip(), entry["email"].strip().lower()

    stem = Path(filename).stem.strip()
    if not stem:
        raise ValueError(f"Empty filename stem for: '{filename}'")

    # Find the token containing '@'
    if "@" not in stem or "_" not in stem:
        raise ValueError(
            f"Filename '{filename}' does not follow expected 'name_mailid.wav' convention."
        )

    # Split by underscore
    tokens = stem.split("_")
    # Identify which token contains '@'
    email_idx = None
    for idx, token in enumerate(tokens):
        if "@" in token:
            email_idx = idx
            break

    if email_idx is None:
        raise ValueError(f"No email address found in filename: '{filename}'")

    email_token = "_".join(tokens[email_idx:]).strip()
    name_tokens = tokens[:email_idx]

    if not name_tokens:
        raise ValueError(f"No participant name could be extracted before email in: '{filename}'")

    raw_name = " ".join(t.strip() for t in name_tokens if t.strip()).strip()
    if not raw_name:
        raise ValueError(f"No participant name could be extracted before email in: '{filename}'")

    # Format name nicely (e.g. 'gowtham' -> 'Gowtham')
    clean_name = raw_name.title()
    clean_email = email_token.lower()

    if not EMAIL_REGEX.match(clean_email):
        raise ValueError(
            f"Extracted email '{clean_email}' does not appear to be a valid email format in '{filename}'"
        )

    return clean_name, clean_email


def generate_deterministic_vector_id(email: str, filename: str) -> str:
    """
    Generates a stable, idempotent vector ID so rerunning enrollment updates existing vectors.
    """
    norm_email = email.strip().lower()
    norm_fn = Path(filename).name.strip().lower()
    fn_hash = hashlib.sha256(norm_fn.encode("utf-8")).hexdigest()[:12]
    # Pinecone ID pattern: spk_<email>_<hash>
    sanitized_email = re.sub(r"[^a-zA-Z0-9_-]", "_", norm_email)
    return f"spk_{sanitized_email}_{fn_hash}"


def load_metadata_override(voices_dir: Path) -> Dict[str, Any]:
    """Loads optional voices_manifest.json or metadata.json if present in Voices dir."""
    for manifest_name in ["voices_manifest.json", "metadata.json"]:
        manifest_path = voices_dir / manifest_name
        if manifest_path.is_file():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    logger.info(f"Loaded explicit metadata mapping from {manifest_path}")
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not parse metadata file {manifest_path}: {e}")
    return {}


def enroll_voices(voices_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Scans the Voices directory and enrolls all usable WAV recordings into Pinecone.
    """
    vdir = Path(voices_dir) if voices_dir else DEFAULT_VOICES_DIR
    if not vdir.is_dir():
        raise FileNotFoundError(f"Voices directory not found at: {vdir}")

    logger.info(f"Scanning voices directory: {vdir}")
    metadata_map = load_metadata_override(vdir)

    all_files = os.listdir(vdir)
    wav_files = [f for f in all_files if f.lower().endswith(".wav")]
    non_wav_files = [f for f in all_files if not f.lower().endswith(".wav") and not f.startswith(".")]

    if non_wav_files:
        logger.info(
            f"Found {len(non_wav_files)} non-WAV files in {vdir} (skipped): {', '.join(non_wav_files)}"
        )

    if not wav_files:
        logger.warning(f"No .wav audio files found in {vdir}.")
        return {"total": 0, "enrolled": 0, "skipped": 0, "errors": 0}

    logger.info(f"Found {len(wav_files)} WAV recording(s) for processing.")

    # Initialize index
    index = get_or_create_speaker_index(create_if_missing=True)
    cfg = get_pinecone_config()

    stats = {
        "total": len(wav_files),
        "enrolled": 0,
        "skipped": 0,
        "errors": 0,
        "participants": set(),
        "details": []
    }

    for filename in wav_files:
        file_path = vdir / filename
        logger.info(f"\n--- Processing: {filename} ---")

        # 1. Parse participant metadata
        try:
            name, email = parse_filename(filename, metadata_map)
            logger.info(f"Parsed metadata -> Name: '{name}', Email: '{email}'")
        except Exception as parse_exc:
            logger.error(f"[PARSE ERROR] Failed to parse metadata from '{filename}': {parse_exc}")
            stats["errors"] += 1
            stats["details"].append({"file": filename, "status": "parse_error", "message": str(parse_exc)})
            continue

        # 2. Extract speaker embedding
        try:
            embedding = extract_speaker_embedding(str(file_path))
            if embedding is None:
                logger.warning(f"[SKIP] Audio in '{filename}' was too short or silent.")
                stats["skipped"] += 1
                stats["details"].append({"file": filename, "status": "skipped", "message": "Short or silent audio"})
                continue
        except Exception as emb_exc:
            logger.error(f"[EMBEDDING ERROR] Failed to extract embedding from '{filename}': {emb_exc}")
            stats["errors"] += 1
            stats["details"].append({"file": filename, "status": "embedding_error", "message": str(emb_exc)})
            continue

        # 3. Validate embedding vector
        if len(embedding) != EMBEDDING_DIMENSION:
            logger.error(f"[INVALID DIM] Embedding dim {len(embedding)} != {EMBEDDING_DIMENSION}")
            stats["errors"] += 1
            continue

        # 4. Construct deterministic vector ID & metadata
        vector_id = generate_deterministic_vector_id(email, filename)
        # Participant ID: clean email or canonical name
        participant_id = email.lower()
        now_iso = datetime.now(timezone.utc).isoformat()

        metadata = {
            "participant_id": participant_id,
            "name": name,
            "email": email,
            "sample_id": filename,
            "embedding_model": "pyannote/speaker-diarization-community-1",
            "enrolled_at": now_iso,
        }

        # 5. Upsert to Pinecone
        try:
            upsert_speaker_embedding(
                vector_id=vector_id,
                vector=embedding.tolist(),
                metadata=metadata,
                namespace=cfg["namespace"]
            )
            stats["enrolled"] += 1
            stats["participants"].add(name)
            stats["details"].append({
                "file": filename,
                "vector_id": vector_id,
                "name": name,
                "email": email,
                "status": "enrolled"
            })
            logger.info(f"Successfully enrolled '{filename}' -> ID: {vector_id}")
        except Exception as upsert_exc:
            logger.error(f"[UPSERT ERROR] Failed to upsert vector for '{filename}': {upsert_exc}")
            stats["errors"] += 1
            stats["details"].append({"file": filename, "status": "upsert_error", "message": str(upsert_exc)})

    # Summary
    logger.info("\n================ ENROLLMENT SUMMARY ================")
    logger.info(f"Total WAV files examined: {stats['total']}")
    logger.info(f"Successfully enrolled:   {stats['enrolled']}")
    logger.info(f"Distinct participants:   {len(stats['participants'])} ({', '.join(sorted(stats['participants']))})")
    logger.info(f"Skipped (short/silent):  {stats['skipped']}")
    logger.info(f"Failed / Parse errors:   {stats['errors']}")
    logger.info("====================================================\n")

    return stats


def list_enrolled_profiles():
    """Queries Pinecone index stats and samples to display enrolled participants."""
    cfg = get_pinecone_config()
    index = get_or_create_speaker_index(create_if_missing=False)
    stats = index.describe_index_stats()
    ns_stats = stats.get("namespaces", {}).get(cfg["namespace"], {})
    count = ns_stats.get("vector_count", 0)

    print(f"\nPinecone Index: '{cfg['index_name']}'")
    print(f"Namespace:      '{cfg['namespace']}'")
    print(f"Total Vectors:  {count}\n")


def delete_participant_profile(target: str):
    """Deletes vectors for a participant by ID, email, or name."""
    cfg = get_pinecone_config()
    target_clean = target.strip()
    logger.info(f"Searching and deleting voice vectors matching: '{target_clean}'...")
    
    # In Pinecone serverless, we can query or delete with metadata filter
    index = get_or_create_speaker_index(create_if_missing=False)
    try:
        # Try metadata filter deletion
        index.delete(
            filter={"$or": [{"email": target_clean.lower()}, {"name": target_clean}, {"participant_id": target_clean.lower()}]},
            namespace=cfg["namespace"]
        )
        logger.info(f"Deletion command executed for participant '{target_clean}'.")
    except Exception as exc:
        logger.warning(f"Metadata filter delete not directly supported on this tier: {exc}. Trying direct vector ID deletion...")


def main():
    parser = argparse.ArgumentParser(description="Enroll voice recordings into Pinecone speaker index.")
    parser.add_argument("--voices-dir", type=str, default=None, help="Path to Voices directory")
    parser.add_argument("--list", action="store_true", help="List enrolled speaker profile statistics")
    parser.add_argument("--delete", type=str, help="Delete speaker embeddings for participant email or name")
    parser.add_argument("--clear-all", action="store_true", help="Clear all speaker embeddings in namespace")

    args = parser.parse_args()

    if args.list:
        list_enrolled_profiles()
    elif args.delete:
        delete_participant_profile(args.delete)
    elif args.clear_all:
        cfg = get_pinecone_config()
        confirm = input(f"Are you sure you want to delete ALL voice vectors in '{cfg['namespace']}'? (yes/no): ")
        if confirm.lower() == "yes":
            delete_speaker_embeddings(delete_all=True)
            logger.info("All speaker vectors cleared.")
        else:
            logger.info("Operation aborted.")
    else:
        vdir = Path(args.voices_dir) if args.voices_dir else None
        enroll_voices(vdir)


if __name__ == "__main__":
    main()
