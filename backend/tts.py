"""
TTS abstraction layer.

Primary:  OpenAI TTS (tts-1, nova voice)
Fallback: Edge TTS (en-US-JennyNeural) — used when OPENAI_API_KEY is absent or the call fails.

To swap TTS providers, only this file needs to change.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration — pull from environment so nothing is hardcoded
# ---------------------------------------------------------------------------
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
TTS_MODEL: str = "tts-1"
TTS_VOICE: str = os.getenv("TTS_VOICE", "nova")   # nova | alloy | echo | fable | onyx | shimmer

# Edge TTS voice map: ISO 639-1 language code → regional neural voice
# OpenAI TTS handles language automatically; this map is only used by the fallback path.
_EDGE_TTS_VOICES: dict[str, str] = {
    "en": "en-US-JennyNeural",
    "fr": "fr-FR-DeniseNeural",
    "es": "es-ES-ElviraNeural",
    "de": "de-DE-KatjaNeural",
    "it": "it-IT-ElsaNeural",
    "pt": "pt-BR-FranciscaNeural",
    "nl": "nl-NL-ColetteNeural",
    "pl": "pl-PL-ZofiaNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "tr": "tr-TR-EmelNeural",
    "ar": "ar-SA-ZariyahNeural",
    "hi": "hi-IN-SwaraNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
}
_EDGE_TTS_DEFAULT: str = "en-US-JennyNeural"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_speech(text: str, output_path: str) -> None:
    """
    Generate speech audio from *text* and write it to *output_path* (MP3).

    Tries OpenAI TTS first; automatically falls back to Edge TTS if:
    - OPENAI_API_KEY is not set, or
    - the OpenAI call raises any exception.
    """
    if OPENAI_API_KEY:
        try:
            await _openai_tts(text, output_path)
            return
        except Exception as exc:
            print(f"[TTS] OpenAI TTS failed: {exc!r} — falling back to Edge TTS")

    await _edge_tts(text, output_path)


# ---------------------------------------------------------------------------
# Private implementations
# ---------------------------------------------------------------------------

async def _openai_tts(text: str, output_path: str) -> None:
    """Generate audio via OpenAI TTS API and write to disk."""
    import asyncio
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    response = await client.audio.speech.create(
        model=TTS_MODEL,
        voice=TTS_VOICE,  # type: ignore[arg-type]
        input=text,
    )
    # write_to_file is synchronous; run in thread to avoid blocking the event loop
    await asyncio.to_thread(response.write_to_file, output_path)


async def _edge_tts(text: str, output_path: str) -> None:
    """
    Generate audio via Microsoft Edge TTS (free, no API key required).
    Auto-detects the script language and picks an appropriate regional voice.
    """
    import edge_tts

    voice = _pick_edge_voice(text)
    print(f"[EdgeTTS] Using voice: {voice}")
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def _pick_edge_voice(text: str) -> str:
    """
    Detect the language of *text* and return the best matching Edge TTS voice.
    Falls back to English if detection fails or the language isn't in the map.
    """
    try:
        from langdetect import detect, LangDetectException
        lang = detect(text)           # returns ISO 639-1 code e.g. "fr", "en", "ar"
        voice = _EDGE_TTS_VOICES.get(lang, _EDGE_TTS_DEFAULT)
        if lang not in _EDGE_TTS_VOICES:
            print(f"[EdgeTTS] Language '{lang}' not in voice map — using default")
        return voice
    except Exception as exc:
        print(f"[EdgeTTS] Language detection failed: {exc!r} — using default voice")
        return _EDGE_TTS_DEFAULT
