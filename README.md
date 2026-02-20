# Clipforge ⚡

Turn any text script into a **TikTok-style vertical video** with:

- 🎙️ AI voiceover (OpenAI TTS `tts-1` / `onyx` voice, Edge TTS fallback)
- 💬 Word-by-word synchronized subtitles (bold, all-caps, centered)
- 🎮 Gameplay background video with a random start point
- 📐 9:16 portrait 1080×1920 MP4 output

No login. No database. Paste → Generate → Download.

---

## Project Structure

```
clipforge/
├── frontend/                  # Next.js 15 (App Router) — deploy to Vercel
│   ├── app/
│   │   ├── page.tsx           # Main UI (textarea, progress, preview)
│   │   ├── layout.tsx
│   │   ├── globals.css
│   │   └── api/
│   │       ├── generate/route.ts        # Proxy → POST /jobs
│   │       └── status/[jobId]/route.ts  # Proxy → GET /jobs/{id}
│   ├── package.json
│   ├── tailwind.config.ts
│   └── .env.local             # NEXT_PUBLIC_BACKEND_URL
│
└── backend/                   # FastAPI (Python) — deploy to Railway
    ├── main.py                # App entry point, routes, job runner
    ├── jobs.py                # In-memory job store (no database)
    ├── tts.py                 # TTS abstraction (OpenAI → Edge TTS fallback)
    ├── video.py               # FFmpeg rendering pipeline
    ├── cleanup.py             # Background temp-file cleanup
    ├── assets/
    │   ├── Anton.ttf          ← Download from Google Fonts (see below)
    │   └── background.mp4     ← Place your gameplay video here (git-ignored)
    ├── requirements.txt
    ├── nixpacks.toml          # Railway build config (installs FFmpeg)
    └── .env                   # Local environment variables
```

---

## Local Development Setup

### Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11+ |
| Node.js | 18+ |
| FFmpeg | any recent (must be in PATH) |

Install FFmpeg: https://ffmpeg.org/download.html

---

### Backend Setup

```bash
cd backend

# 1. Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download the Anton font
#    → https://fonts.google.com/specimen/Anton
#    → Click "Download family" → extract Anton-Regular.ttf
#    → Rename to Anton.ttf and place at:  backend/assets/Anton.ttf

# 4. Add a background video
#    Place any gameplay/looping video at:  backend/assets/background.mp4
#    (This file is git-ignored due to size)

# 5. Configure environment
cp .env .env.local              # or just edit .env directly
# Set OPENAI_API_KEY if you have one (optional — Edge TTS is the fallback)

# 6. Run the dev server
uvicorn main:app --reload --port 8000
```

The API will be available at http://localhost:8000.
Interactive docs: http://localhost:8000/docs

---

### Frontend Setup

```bash
cd frontend

# 1. Install dependencies
npm install

# 2. Configure backend URL (already set for local dev)
# Edit .env.local → NEXT_PUBLIC_BACKEND_URL=http://localhost:8000

# 3. Start dev server
npm run dev
```

Open http://localhost:3000

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | _(empty)_ | OpenAI API key. If missing or invalid, Edge TTS is used automatically. |
| `BACKGROUND_VIDEO_PATH` | `./assets/background.mp4` | Path to a video **file** or a **folder** of videos. A folder enables random selection. |
| `MAX_SCRIPT_CHARS` | `2200` | Hard character limit (~3 min of speech). Change it in one place. |
| `TEMP_DIR` | `/tmp/clipforge` | Where rendered files are stored. Auto-cleaned after 1 hour. |

### Frontend (`frontend/.env.local`)

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_BACKEND_URL` | `http://localhost:8000` | Full URL of the FastAPI backend. |

---

## Deployment

### Backend → Railway

1. Push the repo to GitHub.

2. Create a new **Railway** project → "Deploy from GitHub repo".

3. Set the **root directory** to `backend/` (if using a monorepo).

4. Railway detects `nixpacks.toml` and automatically installs:
   - `ffmpeg` (from nixpkgs)
   - Python 3.11
   - All pip dependencies

5. Set environment variables in **Railway → Variables**:
   ```
   OPENAI_API_KEY=sk-...
   BACKGROUND_VIDEO_PATH=/app/assets/background.mp4
   MAX_SCRIPT_CHARS=2200
   TEMP_DIR=/tmp/clipforge
   ```

6. **Upload assets to Railway:**
   - Option A: Use a Railway Volume and upload via CLI / Railway shell
   - Option B: Host the background video on a CDN and set `BACKGROUND_VIDEO_PATH` to an HTTPS URL *(requires small code change in `video.py`)*
   - Option C: Commit a small (< 100 MB) background video — remove it from `.gitignore` temporarily

7. Railway auto-deploys on every push to `main`.

---

### Frontend → Vercel

1. Push the `frontend/` directory (or the whole monorepo) to GitHub.

2. Create a new **Vercel** project → import the repo.

3. If using a monorepo, set the **Root Directory** to `frontend/`.

4. Add environment variables in **Vercel → Settings → Environment Variables**:
   ```
   NEXT_PUBLIC_BACKEND_URL=https://your-railway-app.railway.app
   ```

5. Vercel auto-deploys on every push. Done.

---

## How the Video Pipeline Works

```
Script text
    │
    ▼
[1] TTS (OpenAI tts-1 / onyx, or Edge TTS fallback)
    → job_id.mp3
    │
    ▼
[2] FFprobe → audio duration (seconds)
    │
    ▼
[3] calculate_word_timestamps()
    → [(word, start_sec, end_sec), ...]
    Evenly distributes each word across the audio timeline.
    (Swap this function for Whisper-based timing later — nothing else changes.)
    │
    ▼
[4] FFmpeg pass 1 — background prep
    → Trim / loop background video to audio duration
    → Scale + crop to 1080×1920 (portrait 9:16)
    → job_id_bg.mp4
    │
    ▼
[5] FFmpeg pass 2 — final render
    → Overlay voiceover audio
    → Add drawtext filter chain (one filter per word, enable='between(t,...)')
       Font: Anton.ttf, 90px, all-caps white with 3px black stroke, centered
    → job_id_output.mp4
    │
    ▼
[6] Serve via GET /videos/{filename}
    Job status → done, url = /videos/job_id_output.mp4
    Frontend polls, shows preview player + download button
```

**Cleanup:** A background asyncio task runs every 30 minutes and deletes any
files in `TEMP_DIR` that are older than 1 hour.

---

## Adding More Background Videos

Set `BACKGROUND_VIDEO_PATH` to a **directory**:

```env
BACKGROUND_VIDEO_PATH=./assets/backgrounds/
```

Drop any `.mp4` or `.mov` files in that folder. One is chosen randomly for
each generated video. No code changes needed.

---

## Swapping TTS or Subtitle Timing

| What | Where | How |
|------|-------|-----|
| TTS provider | `backend/tts.py` | Replace `_openai_tts()` or `_edge_tts()` — only `generate_speech(text, path)` is called externally |
| Word timing | `backend/video.py` | Replace `calculate_word_timestamps(text, duration)` — return the same `List[Tuple[str, float, float]]` format |

---

## API Reference

### `POST /jobs`

Submit a script for processing.

**Request body:**
```json
{ "text": "Your script here..." }
```

**Response `202`:**
```json
{ "jobId": "uuid-string" }
```

---

### `GET /jobs/{jobId}`

Poll job status.

**Response:**
```json
{
  "status": "pending | processing | done | error",
  "progress": 0,
  "message": "Generating voiceover...",
  "url": "/videos/abc_output.mp4",
  "error": null
}
```

---

### `GET /videos/{filename}`

Download the rendered MP4. Returns `Content-Disposition: attachment`.

---

## Configurable Constants

All tuneable values live at the top of their respective files or in `.env`:

| Constant | File | Description |
|----------|------|-------------|
| `MAX_CHARS` | `frontend/app/page.tsx` (line 9) | UI character limit display |
| `MAX_SCRIPT_CHARS` | `backend/.env` | Server-side character limit |
| `FONT_SIZE` | `backend/.env` → `video.py` | Subtitle font size (default 90px) |
| `CLEANUP_INTERVAL` | `backend/cleanup.py` | How often cleanup runs (default 30 min) |
| `MAX_FILE_AGE` | `backend/cleanup.py` | File TTL (default 1 hour) |
| `TTS_VOICE` | `backend/tts.py` | OpenAI voice (default `onyx`) |
| `EDGE_TTS_VOICE` | `backend/tts.py` | Edge TTS voice (default `en-US-GuyNeural`) |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15 (App Router), Tailwind CSS |
| Backend | FastAPI, Python 3.11, asyncio |
| Video processing | FFmpeg, FFprobe |
| TTS (primary) | OpenAI TTS API (`tts-1`, `onyx`) |
| TTS (fallback) | Edge TTS (`edge-tts` library, free) |
| Hosting (frontend) | Vercel |
| Hosting (backend) | Railway |
| Temp storage | Railway ephemeral filesystem (`/tmp`) |
| Job queue | Python in-memory dict (no Redis) |
