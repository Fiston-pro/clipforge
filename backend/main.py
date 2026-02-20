"""
Clipforge FastAPI backend.

Endpoints:
  POST /jobs               — submit a script, get back a jobId immediately
  GET  /jobs/{job_id}      — poll status: pending | processing | done | error
  GET  /videos/{filename}  — download the rendered MP4
"""

import asyncio
import os
import sys

# Windows requires ProactorEventLoop for asyncio subprocess support
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

# Load .env file in development (no-op when vars are already set by Railway)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from cleanup import cleanup_old_files
from jobs import create_job, get_job, update_job
from tts import generate_speech
from video import (
    FONT_PATH,
    get_audio_duration,
    get_word_timestamps,
    render_video,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TEMP_DIR: str = os.getenv("TEMP_DIR", "/tmp/clipforge")
MAX_SCRIPT_CHARS: int = int(os.getenv("MAX_SCRIPT_CHARS", "2200"))


# ---------------------------------------------------------------------------
# App lifespan: create temp dir + start cleanup background task
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)

    # Download background video from URL if env var is set and file is missing
    bg_url: str = os.getenv("BACKGROUND_VIDEO_URL", "")
    bg_path = Path(os.getenv("BACKGROUND_VIDEO_PATH", "./assets/background.mp4"))
    if bg_url and not bg_path.exists():
        print(f"[Startup] Downloading background video from {bg_url} ...")
        import urllib.request
        bg_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(urllib.request.urlretrieve, bg_url, str(bg_path))
        print(f"[Startup] Background video saved to {bg_path}")

    if not Path(FONT_PATH).exists():
        print(
            f"[WARNING] Font not found at {FONT_PATH}\n"
            "  Download Anton from https://fonts.google.com/specimen/Anton\n"
            "  and place the .ttf at backend/assets/Anton.ttf"
        )

    cleanup_task = asyncio.create_task(cleanup_old_files())

    yield  # application runs

    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Clipforge API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class JobRequest(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Script cannot be empty")
        if len(v) > MAX_SCRIPT_CHARS:
            raise ValueError(
                f"Script is {len(v)} characters — exceeds the {MAX_SCRIPT_CHARS} character limit"
            )
        return v


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/jobs", status_code=202)
async def create_video_job(request: JobRequest, background_tasks: BackgroundTasks):
    """Enqueue a video generation job and return its ID immediately."""
    job_id = create_job()
    background_tasks.add_task(process_job, job_id, request.text)
    return {"jobId": job_id}


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Poll the status of a job."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/videos/{filename}")
async def serve_video(filename: str):
    """Serve a rendered video file from the temp directory."""
    # Prevent path traversal attacks
    safe_name = Path(filename).name
    file_path = Path(TEMP_DIR) / safe_name

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Video not found")

    return FileResponse(
        str(file_path),
        media_type="video/mp4",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


# ---------------------------------------------------------------------------
# Background job pipeline
# ---------------------------------------------------------------------------

async def process_job(job_id: str, text: str) -> None:
    """
    Full pipeline executed in the background:
      1. Generate voiceover (OpenAI → Edge TTS fallback)
      2. Measure audio duration via FFprobe
      3. Calculate word timestamps (even distribution)
      4. Render portrait video with FFmpeg
      5. Mark job done with video URL
    """
    try:
        update_job(job_id, status="processing", progress=5, message="Starting...")

        audio_path = str(Path(TEMP_DIR) / f"{job_id}.mp3")

        # ---- 1. TTS --------------------------------------------------------
        update_job(job_id, progress=10, message="Generating voiceover...")
        await generate_speech(text, audio_path)
        update_job(job_id, progress=30)

        # ---- 2. Audio duration ---------------------------------------------
        update_job(job_id, progress=35, message="Analyzing audio...")
        duration = await get_audio_duration(audio_path)
        update_job(job_id, progress=40)

        # ---- 3. Word timestamps (Whisper → char-weighted fallback) ---------
        update_job(job_id, progress=45, message="Syncing subtitles with Whisper...")
        word_timestamps = await get_word_timestamps(text, audio_path, duration)
        update_job(job_id, progress=52)

        # ---- 4. Video render (two FFmpeg passes) ---------------------------
        update_job(job_id, progress=55, message="Rendering video...")
        output_filename = f"{job_id}_output.mp4"
        output_path = str(Path(TEMP_DIR) / output_filename)
        await render_video(job_id, audio_path, word_timestamps, duration, output_path)
        update_job(job_id, progress=90)

        # ---- 5. Cleanup intermediate audio --------------------------------
        update_job(job_id, progress=95, message="Finalizing...")
        try:
            Path(audio_path).unlink(missing_ok=True)
        except Exception:
            pass

        # ---- Done ----------------------------------------------------------
        update_job(
            job_id,
            status="done",
            progress=100,
            message="Done!",
            url=f"/videos/{output_filename}",
        )

    except Exception as exc:
        import traceback
        print(f"[Job {job_id}] Failed: {exc!r}")
        traceback.print_exc()
        update_job(
            job_id,
            status="error",
            progress=0,
            message="An error occurred",
            error=str(exc),
        )
