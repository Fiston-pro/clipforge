"""
Video rendering pipeline.

Key public functions:
  get_audio_duration(path)              — FFprobe: audio length in seconds
  get_word_timestamps(text, path, dur)  — Whisper API (perfect sync) with char-weighted fallback
  calculate_word_timestamps(text, dur)  — char-weighted fallback (no API needed)
  get_background_video()                — pick a random background video
  render_video(...)                     — full FFmpeg pipeline → MP4
"""

import asyncio
import json
import os
import random
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Configuration — all configurable via environment variables
# ---------------------------------------------------------------------------
BACKGROUND_VIDEO_PATH: str = os.getenv("BACKGROUND_VIDEO_PATH", "./assets/background.mp4")
TEMP_DIR: str = os.getenv("TEMP_DIR", "/tmp/clipforge")
FONT_SIZE: int = int(os.getenv("FONT_SIZE", "90"))

# Absolute path to the Anton.ttf font shipped in the assets folder
FONT_PATH: str = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "assets", "Anton.ttf")
)


# ---------------------------------------------------------------------------
# Low-level subprocess helper
# ---------------------------------------------------------------------------

def _run_sync(*args: str) -> Tuple[str, str]:
    """Run an external command synchronously. Raises RuntimeError on non-zero exit."""
    result = subprocess.run(
        list(args),
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed (exit {result.returncode}): {' '.join(args)}\n"
            f"stderr: {result.stderr.decode(errors='replace')}"
        )
    return result.stdout.decode(errors="replace"), result.stderr.decode(errors="replace")


async def _run(*args: str) -> Tuple[str, str]:
    """Run an external command in a thread pool (non-blocking, cross-platform)."""
    return await asyncio.to_thread(_run_sync, *args)


# ---------------------------------------------------------------------------
# FFprobe helpers
# ---------------------------------------------------------------------------

async def get_audio_duration(audio_path: str) -> float:
    """Return the duration of an audio file in seconds."""
    stdout, _ = await _run(
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        audio_path,
    )
    data = json.loads(stdout)
    for stream in data.get("streams", []):
        if "duration" in stream:
            return float(stream["duration"])
    raise RuntimeError(f"Could not determine audio duration for: {audio_path}")


async def _get_video_duration(video_path: str) -> float:
    """Return the duration of a video file in seconds."""
    stdout, _ = await _run(
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "v:0",
        video_path,
    )
    data = json.loads(stdout)
    for stream in data.get("streams", []):
        if "duration" in stream:
            return float(stream["duration"])
    raise RuntimeError(f"Could not determine video duration for: {video_path}")


# ---------------------------------------------------------------------------
# Word timing (replaceable with Whisper later)
# ---------------------------------------------------------------------------

def calculate_word_timestamps(
    text: str, duration: float
) -> List[Tuple[str, float, float]]:
    """
    Distribute words across *duration* seconds, weighted by character count.

    Longer words naturally take more time to say, so allocating proportional
    time to each word produces much better sync than equal slices.

    Returns a list of (word, start_sec, end_sec) tuples.

    This function is intentionally isolated so it can be swapped for a
    Whisper-based implementation (perfect accuracy) without touching anything else.
    """
    words = text.split()
    if not words:
        return []

    # Weight each word by its character length (minimum 1 to avoid zero-width)
    char_counts = [max(1, len(w)) for w in words]
    total_chars = sum(char_counts)

    timestamps: List[Tuple[str, float, float]] = []
    current = 0.0
    for word, chars in zip(words, char_counts):
        word_duration = duration * chars / total_chars
        timestamps.append((word, current, current + word_duration))
        current += word_duration

    return timestamps


async def get_word_timestamps(
    text: str,
    audio_path: str,
    duration: float,
) -> List[Tuple[str, float, float]]:
    """
    Return word-level timestamps for subtitle sync.

    Strategy:
      1. If OPENAI_API_KEY is set → call Whisper-1 with word timestamps (frame-perfect).
      2. If Whisper fails or key is absent → fall back to char-weighted distribution.

    The fallback guarantees the pipeline never breaks even without an API key.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key:
        try:
            timestamps = await _whisper_timestamps(audio_path, api_key)
            print(f"[Whisper] Got {len(timestamps)} word timestamps — using exact sync")
            return timestamps
        except Exception as exc:
            print(f"[Whisper] Failed: {exc!r} — falling back to char-weighted timing")

    return calculate_word_timestamps(text, duration)


async def _whisper_timestamps(
    audio_path: str,
    api_key: str,
) -> List[Tuple[str, float, float]]:
    """
    Call OpenAI Whisper-1 with timestamp_granularities=['word'].
    Returns [(word, start_sec, end_sec), ...] matching actual speech timing.
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)

    # Read file bytes in a thread so we don't block the event loop
    audio_bytes = await asyncio.to_thread(Path(audio_path).read_bytes)

    import io
    response = await client.audio.transcriptions.create(
        model="whisper-1",
        file=("audio.mp3", io.BytesIO(audio_bytes), "audio/mpeg"),
        response_format="verbose_json",
        timestamp_granularities=["word"],
    )

    words = getattr(response, "words", None)
    if not words:
        raise RuntimeError("Whisper returned no word timestamps")

    # Strip surrounding whitespace; skip empty tokens
    return [
        (w.word.strip(), float(w.start), float(w.end))
        for w in words
        if w.word.strip()
    ]


# ---------------------------------------------------------------------------
# Background video selection
# ---------------------------------------------------------------------------

def get_background_video() -> str:
    """
    Return an absolute path to a background video file.

    If BACKGROUND_VIDEO_PATH is a directory, a random .mp4/.mov file inside
    it is chosen — making it trivial to add more backgrounds later.
    If it's a file, that file is used directly.
    """
    bg = Path(BACKGROUND_VIDEO_PATH)

    if bg.is_dir():
        candidates = list(bg.glob("*.mp4")) + list(bg.glob("*.mov"))
        if not candidates:
            raise RuntimeError(
                f"No .mp4/.mov files found in background directory: {bg}"
            )
        return str(random.choice(candidates))

    if not bg.exists():
        raise RuntimeError(
            f"Background video not found: {bg}\n"
            "Place a video file there or set BACKGROUND_VIDEO_PATH in your .env"
        )

    return str(bg.resolve())


# ---------------------------------------------------------------------------
# FFmpeg text escaping
# ---------------------------------------------------------------------------

def _escape_drawtext(text: str) -> str:
    """
    Escape a string for safe use as a FFmpeg drawtext `text=` value.

    FFmpeg filter-level escape rules (applied in order):
      1. Backslash → double backslash
      2. Single quote → backslash + single quote  (inside single-quoted value)
      3. Colon → backslash + colon  (option separator)
      4. Percent → double percent  (ffmpeg format expansion)
    """
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\\'")
    text = text.replace(":", "\\:")
    text = text.replace("%", "%%")
    text = text.replace("\n", " ").replace("\r", "")
    return text


# ---------------------------------------------------------------------------
# Subtitle filter builder
# ---------------------------------------------------------------------------

def _build_subtitle_filter(
    word_timestamps: List[Tuple[str, float, float]],
    font_path: Optional[str] = None,
) -> str:
    """
    Build a chained FFmpeg drawtext filter that shows one word at a time.

    Each word is displayed in bold all-caps white text with a black stroke,
    centered on screen, visible only during its time slice.
    """
    # Normalize font path to forward slashes; escape colon for FFmpeg
    escaped_font = ""
    if font_path and os.path.exists(font_path):
        escaped_font = font_path.replace("\\", "/").replace(":", "\\:")

    filters: List[str] = []
    for word, start, end in word_timestamps:
        escaped_word = _escape_drawtext(word.upper())

        font_part = f"fontfile='{escaped_font}':" if escaped_font else ""

        segment = (
            f"drawtext="
            f"{font_part}"
            f"text='{escaped_word}':"
            f"fontsize={FONT_SIZE}:"
            f"fontcolor=white:"
            f"bordercolor=black:"
            f"borderw=3:"
            f"x=(w-text_w)/2:"
            f"y=(h-text_h)/2:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
        )
        filters.append(segment)

    return ",".join(filters)


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

async def render_video(
    job_id: str,
    audio_path: str,
    word_timestamps: List[Tuple[str, float, float]],
    audio_duration: float,
    output_path: str,
) -> None:
    """
    Full FFmpeg pipeline:
      1. Trim/loop background video to audio duration, scale to 1080×1920
      2. Overlay voiceover audio + word-by-word subtitle drawtext filters
      3. Write final MP4 to output_path
    """
    bg_video = get_background_video()
    temp_dir = Path(TEMP_DIR)
    temp_bg = str(temp_dir / f"{job_id}_bg.mp4")

    try:
        # ----------------------------------------------------------------
        # Step 1: Prepare portrait background segment
        # ----------------------------------------------------------------
        bg_duration = await _get_video_duration(bg_video)

        if bg_duration >= audio_duration:
            # Seek to a random start point so every video uses a fresh section
            max_start = bg_duration - audio_duration
            start_time = random.uniform(0, max_start)
            input_args = ["-ss", str(start_time), "-i", bg_video]
        else:
            # Background is shorter than the script — loop it seamlessly
            input_args = ["-stream_loop", "-1", "-i", bg_video]

        await _run(
            "ffmpeg", "-y",
            *input_args,
            "-t", str(audio_duration),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-c:v", "libx264", "-preset", "fast",
            "-an",           # strip original audio
            temp_bg,
        )

        # ----------------------------------------------------------------
        # Step 2: Combine background + voiceover + subtitles
        # ----------------------------------------------------------------
        subtitle_filter = _build_subtitle_filter(word_timestamps, FONT_PATH)

        ffmpeg_args = [
            "ffmpeg", "-y",
            "-i", temp_bg,
            "-i", audio_path,
        ]

        if subtitle_filter:
            ffmpeg_args += ["-vf", subtitle_filter]

        ffmpeg_args += [
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-shortest",
            output_path,
        ]

        await _run(*ffmpeg_args)

    finally:
        # Always clean up the intermediate background clip
        try:
            if Path(temp_bg).exists():
                Path(temp_bg).unlink()
        except Exception:
            pass
