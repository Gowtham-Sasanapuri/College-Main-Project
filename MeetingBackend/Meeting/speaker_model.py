"""
Speaker Embedding Model Module.
Provides shared pretrained embedding extraction for enrollment and inference
using the pyannote community speaker embedding extractor (WeSpeaker ResNet34, 256-dim).
"""

import os
import logging
from pathlib import Path
from typing import Union, Optional
import numpy as np
import torch

try:
    import dotenv
    _base_dir = Path(__file__).resolve().parent.parent
    dotenv.load_dotenv(_base_dir / '.env')
    dotenv.load_dotenv(_base_dir.parent / '.env')
except ImportError:
    pass

from .audio_processor import load_audio_file, init_ffmpeg_shared_dlls

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSION = 256
SAMPLE_RATE = 16000
MIN_AUDIO_DURATION_SEC = 0.5  # Minimum speech duration to extract a meaningful embedding

_embedding_model = None


def get_speaker_embedding_model(hf_token: Optional[str] = None):
    """
    Loads and caches the PyannoteAudioPretrainedSpeakerEmbedding model.
    Uses 'pyannote/speaker-diarization-community-1' (subfolder='embedding').
    """
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    token = hf_token or os.environ.get("HF_TOKEN")
    if not token:
        raise ValueError(
            "HF_TOKEN is not configured. Please set HF_TOKEN in your environment/.env file."
        )

    init_ffmpeg_shared_dlls()

    logger.info("Loading pretrained speaker embedding model from pyannote community checkpoint...")
    try:
        from pyannote.audio.pipelines.speaker_verification import PyannoteAudioPretrainedSpeakerEmbedding
        model_spec = {
            "checkpoint": "pyannote/speaker-diarization-community-1",
            "subfolder": "embedding",
        }
        _embedding_model = PyannoteAudioPretrainedSpeakerEmbedding(model_spec, token=token)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        _embedding_model.to(device)
        logger.info(
            f"Pretrained speaker embedding model loaded successfully (dimension={_embedding_model.dimension}, device={device})."
        )
        return _embedding_model
    except Exception as exc:
        logger.error(f"Failed to load speaker embedding model: {exc}")
        raise RuntimeError(f"Could not load speaker embedding model: {exc}") from exc


def normalize_vector(vec: np.ndarray) -> np.ndarray:
    """L2-normalizes a numerical embedding vector."""
    norm = np.linalg.norm(vec)
    if norm == 0 or not np.isfinite(norm):
        return vec
    return vec / norm


def extract_speaker_embedding(
    audio_input: Union[str, np.ndarray, torch.Tensor],
    sample_rate: int = SAMPLE_RATE,
    hf_token: Optional[str] = None
) -> Optional[np.ndarray]:
    """
    Extracts a normalized 256-dimensional fixed-length speaker embedding vector.

    Args:
        audio_input: File path (str), 1D numpy array, or torch.Tensor sampled at 16000 Hz.
        sample_rate: Sample rate (must be 16000).
        hf_token: Optional Hugging Face token.

    Returns:
        np.ndarray of shape (256,), or None if audio is too short or silent.
    """
    # 1. Load audio array if path provided
    if isinstance(audio_input, (str, Path)):
        audio_arr = load_audio_file(str(audio_input))
    elif isinstance(audio_input, torch.Tensor):
        audio_arr = audio_input.detach().cpu().numpy().flatten().astype(np.float32)
    elif isinstance(audio_input, np.ndarray):
        audio_arr = audio_input.flatten().astype(np.float32)
    else:
        raise TypeError(f"Unsupported audio_input type: {type(audio_input)}")

    # 2. Check duration
    if len(audio_arr) == 0:
        logger.warning("Empty audio passed to extract_speaker_embedding.")
        return None

    duration = len(audio_arr) / sample_rate
    if duration < MIN_AUDIO_DURATION_SEC:
        logger.warning(
            f"Audio duration {duration:.2f}s is below minimum threshold {MIN_AUDIO_DURATION_SEC}s."
        )
        return None

    # Check for silence (energy threshold)
    rms = np.sqrt(np.mean(audio_arr ** 2))
    if rms < 1e-4:
        logger.warning(f"Audio is nearly silent (RMS={rms:.6f}). Skipping embedding extraction.")
        return None

    # 3. Format as 3D tensor: (batch=1, channels=1, time)
    tensor = torch.from_numpy(audio_arr).unsqueeze(0).unsqueeze(0)

    # 4. Run model inference
    model = get_speaker_embedding_model(hf_token=hf_token)
    raw_emb = model(tensor)  # returns np.ndarray of shape (1, 256)

    emb = raw_emb[0]
    if not np.isfinite(emb).all():
        logger.error("Generated speaker embedding contains NaN or Inf values.")
        return None

    if len(emb) != EMBEDDING_DIMENSION:
        logger.error(
            f"Extracted embedding dimension {len(emb)} != expected {EMBEDDING_DIMENSION}."
        )
        return None

    # 5. Unit normalize for cosine similarity
    normalized = normalize_vector(emb)
    return normalized
