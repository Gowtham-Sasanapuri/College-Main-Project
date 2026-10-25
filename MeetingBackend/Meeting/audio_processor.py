import os
import shutil
import logging
import wave
import subprocess
from pathlib import Path
import numpy as np
import torch
import whisper

try:
    import dotenv
    _base_dir = Path(__file__).resolve().parent.parent
    dotenv.load_dotenv(_base_dir / '.env')
    dotenv.load_dotenv(_base_dir.parent / '.env')
except ImportError:
    pass

logger = logging.getLogger(__name__)

_whisper_model = None
_resolved_ffmpeg_path = None


def get_ffmpeg_path():
    global _resolved_ffmpeg_path
    if _resolved_ffmpeg_path is not None:
        return _resolved_ffmpeg_path

    ffmpeg_path = os.getenv("FFMPEG_PATH")
    if ffmpeg_path:
        ffmpeg_path = ffmpeg_path.strip('\'"')
        # Check if FFMPEG_PATH points to a directory
        if os.path.isdir(ffmpeg_path):
            found = False
            for filename in ["ffmpeg.exe", "ffmpeg"]:
                p = os.path.join(ffmpeg_path, filename)
                if os.path.isfile(p):
                    ffmpeg_path = p
                    found = True
                    break
            if not found:
                raise FileNotFoundError(
                    f"FFMPEG_PATH directory '{ffmpeg_path}' does not contain a valid ffmpeg executable."
                )
        elif not os.path.isfile(ffmpeg_path):
            raise FileNotFoundError(
                f"FFmpeg executable specified in FFMPEG_PATH was not found: {ffmpeg_path}"
            )
    else:
        ffmpeg_path = shutil.which("ffmpeg")
        # Fallback check on Windows for WinGet-installed FFmpeg
        if not ffmpeg_path and os.name == "nt":
            local_appdata = os.getenv("LOCALAPPDATA")
            if not local_appdata:
                user_profile = os.getenv("USERPROFILE") or os.path.expanduser("~")
                if user_profile:
                    local_appdata = os.path.join(user_profile, "AppData", "Local")
            
            if local_appdata:
                winget_packages_dir = os.path.join(local_appdata, "Microsoft", "WinGet", "Packages")
                if os.path.isdir(winget_packages_dir):
                    for entry in os.listdir(winget_packages_dir):
                        if "ffmpeg" in entry.lower():
                            entry_path = os.path.join(winget_packages_dir, entry)
                            for root, _, files in os.walk(entry_path):
                                if "ffmpeg.exe" in files:
                                    ffmpeg_path = os.path.join(root, "ffmpeg.exe")
                                    break
                            if ffmpeg_path:
                                break

    if ffmpeg_path:
        # Verify that the file exists and is a file
        if not os.path.isfile(ffmpeg_path):
            raise FileNotFoundError(
                f"Resolved FFmpeg path is not a valid file: {ffmpeg_path}"
            )
        # Validate that the executable actually runs
        try:
            res = subprocess.run(
                [ffmpeg_path, "-version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            if res.returncode != 0:
                raise RuntimeError(f"FFmpeg command returned non-zero exit code: {res.returncode}")
        except Exception as exc:
            raise RuntimeError(
                f"FFmpeg executable at '{ffmpeg_path}' is not executable or failed to run: {exc}"
            ) from exc
    else:
        raise FileNotFoundError(
            "FFmpeg executable was not found on system PATH and FFMPEG_PATH is not set."
        )

    # Prepend the directory of the resolved ffmpeg to PATH so that library calls (like whisper) find it
    ffmpeg_dir = os.path.dirname(os.path.abspath(ffmpeg_path))
    path_env = os.environ.get("PATH", "")
    if ffmpeg_dir not in path_env.split(os.pathsep):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + path_env

    _resolved_ffmpeg_path = ffmpeg_path
    logger.info(f"[FFMPEG] Using: {_resolved_ffmpeg_path}")
    return _resolved_ffmpeg_path


def init_ffmpeg_shared_dlls():
    """
    On Windows, registers the FFmpeg shared library directory with os.add_dll_directory
    so native libraries like torchcodec can load FFmpeg DLLs (avcodec, avformat, etc.).
    """
    if os.name != "nt":
        return
    local_appdata = os.getenv("LOCALAPPDATA") or os.path.join(
        os.getenv("USERPROFILE") or os.path.expanduser("~"), "AppData", "Local"
    )
    winget_packages_dir = os.path.join(local_appdata, "Microsoft", "WinGet", "Packages")
    if os.path.isdir(winget_packages_dir):
        for entry in os.listdir(winget_packages_dir):
            if "ffmpeg" in entry.lower() and "shared" in entry.lower():
                entry_path = os.path.join(winget_packages_dir, entry)
                for root, _, files in os.walk(entry_path):
                    if any(f.startswith("avcodec") and f.endswith(".dll") for f in files):
                        try:
                            os.add_dll_directory(root)
                            logger.info(f"[FFMPEG] Registered DLL directory for TorchCodec: {root}")
                        except Exception as e:
                            logger.warning(f"[FFMPEG] Failed to register DLL directory {root}: {e}")
                        return


# Safe startup checks
try:
    get_ffmpeg_path()
except Exception as exc:
    logger.warning(f"[FFMPEG] Safe startup check failed: {exc}")

try:
    init_ffmpeg_shared_dlls()
except Exception as exc:
    logger.warning(f"[FFMPEG] Shared DLL startup check failed: {exc}")


def get_whisper_model(model_size="base"):
    global _whisper_model
    if _whisper_model is None:
        logger.info(f"Loading Whisper ASR model ({model_size})...")
        _whisper_model = whisper.load_model(model_size)
    return _whisper_model


def normalize_speaker_label(raw_speaker, speaker_mapping):
    """
    Normalizes any speaker label (e.g. SPEAKER_00, speaker_1, Speaker 0)
    to standard 'Speaker_001', 'Speaker_002', etc.
    """
    if raw_speaker not in speaker_mapping:
        idx = len(speaker_mapping) + 1
        speaker_mapping[raw_speaker] = f"Speaker_{idx:03d}"
    return speaker_mapping[raw_speaker]


def load_audio_file(audio_path):
    """
    Loads audio file as float32 NumPy array sampled at 16,000 Hz for Whisper.
    First attempts using whisper.load_audio (which uses FFmpeg).
    If FFmpeg is not installed on system PATH, falls back to native Python wave / scipy WAV decoding.
    """
    try:
        get_ffmpeg_path()
        has_ffmpeg = True
    except Exception as exc:
        logger.warning(f"FFmpeg check failed: {exc}")
        has_ffmpeg = False

    if has_ffmpeg:
        try:
            logger.info("FFmpeg found. Decoding audio using Whisper load_audio...")
            return whisper.load_audio(audio_path)
        except Exception as exc:
            logger.warning(f"Whisper load_audio failed: {exc}. Trying native decoding fallback...")

    # Fallback: Native Python WAV decoding for PCM WAV files
    try:
        logger.info("Attempting native Python WAV decoding fallback...")
        with wave.open(audio_path, 'rb') as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            
            raw_bytes = wf.readframes(n_frames)
            
            if sampwidth == 2:
                audio_data = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            elif sampwidth == 4:
                audio_data = np.frombuffer(raw_bytes, dtype=np.int32).astype(np.float32) / 2147483648.0
            else:
                audio_data = np.frombuffer(raw_bytes, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0

            # Convert stereo to mono if needed
            if n_channels > 1:
                audio_data = audio_data.reshape(-1, n_channels).mean(axis=1)

            # Resample to 16,000 Hz if necessary
            if framerate != 16000:
                duration = len(audio_data) / framerate
                new_length = int(duration * 16000)
                audio_data = np.interp(
                    np.linspace(0, len(audio_data), new_length, endpoint=False),
                    np.arange(len(audio_data)),
                    audio_data
                ).astype(np.float32)

            return audio_data
    except Exception as exc:
        logger.error(f"Native WAV decoding fallback failed: {exc}")
        if not has_ffmpeg:
            raise FileNotFoundError(
                "FFmpeg executable was not found on system PATH or FFMPEG_PATH. "
                "Please install FFmpeg and add it to system PATH or set FFMPEG_PATH to decode webm/mp4 audio files."
            ) from exc
        raise exc


def run_diarization(audio_path, hf_token=None, audio_data=None):
    """
    Runs pyannote.audio speaker diarization pipeline (pyannote/speaker-diarization-community-1).
    Returns list of dicts: [{'start': float, 'end': float, 'speaker': str}]
    Raises RuntimeError if diarization cannot be performed.
    """
    token = hf_token or os.environ.get("HF_TOKEN")
    if not token:
        raise ValueError(
            "HF_TOKEN is not configured. Please set HF_TOKEN in your environment/.env to enable speaker diarization."
        )

    init_ffmpeg_shared_dlls()

    try:
        from pyannote.audio import Pipeline
        logger.info("Attempting pyannote speaker diarization with community-1 model...")
        
        pipeline = None
        last_error = None
        for model_name in ["pyannote/speaker-diarization-community-1", "pyannote/speaker-diarization-3.1"]:
            try:
                pipeline = Pipeline.from_pretrained(model_name, token=token)
                if pipeline:
                    logger.info(f"Loaded pyannote diarization model: {model_name}")
                    break
            except Exception as e:
                last_error = e
                logger.warning(f"Failed to load pyannote model {model_name}: {e}")

        if pipeline is None:
            raise RuntimeError(
                f"Failed to load pyannote diarization model. Error: {last_error}. "
                "Verify your Hugging Face token permissions (ensure 'Read access to contents of all public gated repos' is enabled) "
                "and accept conditions on https://huggingface.co/pyannote/speaker-diarization-community-1"
            )

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        pipeline.to(device)

        # Prepare audio input: use in-memory waveform tensor if audio_data is available
        if audio_data is not None:
            waveform_tensor = torch.from_numpy(audio_data).unsqueeze(0)
            audio_input = {"waveform": waveform_tensor, "sample_rate": 16000}
        else:
            audio_input = audio_path

        diarization_output = pipeline(audio_input)

        # In pyannote.audio 4.x, pipeline returns DiarizeOutput.
        # Prefer exclusive_speaker_diarization for clean reconciliation with transcription timestamps.
        if hasattr(diarization_output, "exclusive_speaker_diarization") and diarization_output.exclusive_speaker_diarization is not None:
            annotation = diarization_output.exclusive_speaker_diarization
        elif hasattr(diarization_output, "speaker_diarization") and diarization_output.speaker_diarization is not None:
            annotation = diarization_output.speaker_diarization
        else:
            annotation = diarization_output

        diar_turns = []
        for turn, _, speaker in annotation.itertracks(yield_label=True):
            diar_turns.append({
                "start": turn.start,
                "end": turn.end,
                "speaker": str(speaker)
            })
        
        logger.info(f"Pyannote diarization completed with {len(diar_turns)} turns.")
        return diar_turns
    except Exception as exc:
        logger.error(f"Pyannote diarization failed: {exc}")
        raise RuntimeError(f"Speaker diarization failed: {exc}") from exc


def process_audio_file(audio_path, hf_token=None):
    """
    Processes full meeting audio file:
    1. Loads audio & runs Whisper ASR to extract speech segments with timestamps.
    2. Runs pyannote diarization.
    3. Aligns timing information to assign speaker labels.
    4. Normalizes speaker labels to 'Speaker_001', 'Speaker_002', etc.
    5. Returns structured list: [{'speaker': 'Speaker_001', 'text': '...'}]
    """
    logger.info(f"Processing complete audio file: {audio_path}")

    # 1. Load audio with FFmpeg / native WAV fallback
    audio_data = load_audio_file(audio_path)

    # 2. Speech Recognition (Whisper)
    model = get_whisper_model("base")
    asr_result = model.transcribe(audio_data, fp16=False)
    raw_segments = asr_result.get("segments", [])

    if not raw_segments:
        logger.warning("No speech detected in audio file.")
        return []

    # 3. Speaker Diarization
    diar_turns = run_diarization(audio_path, hf_token=hf_token, audio_data=audio_data)

    if not diar_turns:
        raise RuntimeError(
            "Speaker diarization produced no speaker segments. Please ensure the audio contains audible speech."
        )

    # Pre-populate anonymous speaker mapping for all diarization turns
    speaker_mapping = {}
    for turn in diar_turns:
        normalize_speaker_label(turn["speaker"], speaker_mapping)

    # 4. Speaker Identification via Pinecone and Pretrained Voice Embeddings
    resolved_identities = {}
    try:
        from .speaker_identifier import resolve_speaker_identities
        resolved_identities = resolve_speaker_identities(
            audio_data=audio_data,
            diar_turns=diar_turns,
            speaker_mapping=speaker_mapping,
            hf_token=hf_token
        )
    except Exception as id_exc:
        logger.warning(
            f"Speaker identification step encountered an error: {id_exc}. "
            "Gracefully falling back to anonymous speaker labels."
        )

    structured_entries = []

    for seg in raw_segments:
        seg_start = seg["start"]
        seg_end = seg["end"]
        text = seg["text"].strip()
        if not text:
            continue

        best_speaker = None
        max_overlap = 0.0

        for turn in diar_turns:
            overlap_start = max(seg_start, turn["start"])
            overlap_end = min(seg_end, turn["end"])
            overlap = max(0.0, overlap_end - overlap_start)
            if overlap > max_overlap:
                max_overlap = overlap
                best_speaker = turn["speaker"]

        if not best_speaker:
            best_speaker = "SPEAKER_00"

        anon_label = normalize_speaker_label(best_speaker, speaker_mapping)
        spk_info = resolved_identities.get(best_speaker, {})
        display_name = spk_info.get("display_name") or anon_label
        participant_email = spk_info.get("email") or spk_info.get("participant_id")
        confidence = spk_info.get("confidence", 0.0)
        is_identified = spk_info.get("is_identified", False)

        structured_entries.append({
            "speaker": display_name,
            "speaker_id": participant_email or anon_label,
            "email": participant_email if is_identified else None,
            "anonymous_speaker": anon_label,
            "is_identified": is_identified,
            "confidence": confidence,
            "text": text
        })

    # 5. Merge consecutive entries by the same speaker
    merged_entries = []
    for entry in structured_entries:
        if merged_entries and merged_entries[-1]["speaker"] == entry["speaker"]:
            merged_entries[-1]["text"] += " " + entry["text"]
        else:
            merged_entries.append(dict(entry))

    logger.info(f"Audio processing complete. Produced {len(merged_entries)} speaker entries.")
    return merged_entries

