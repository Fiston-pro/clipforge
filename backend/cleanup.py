"""
Background cleanup task.

Runs every CLEANUP_INTERVAL seconds and deletes any files in TEMP_DIR
that are older than MAX_FILE_AGE seconds. This keeps the Railway
ephemeral filesystem from filling up.
"""

import asyncio
import os
import time
from pathlib import Path

TEMP_DIR: str = os.getenv("TEMP_DIR", "/tmp/clipforge")
CLEANUP_INTERVAL: int = 30 * 60   # run every 30 minutes
MAX_FILE_AGE: int = 60 * 60       # delete files older than 1 hour


async def cleanup_old_files() -> None:
    """Infinite loop: sleep, then delete stale temp files."""
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL)
            _delete_stale_files()
        except asyncio.CancelledError:
            # Graceful shutdown — stop the loop
            break
        except Exception as exc:
            # Log but never crash the background task
            print(f"[Cleanup] Unexpected error: {exc!r}")


def _delete_stale_files() -> None:
    temp_path = Path(TEMP_DIR)
    if not temp_path.exists():
        return

    now = time.time()
    deleted = 0

    for file in temp_path.iterdir():
        if not file.is_file():
            continue
        age = now - file.stat().st_mtime
        if age > MAX_FILE_AGE:
            try:
                file.unlink()
                deleted += 1
            except Exception as exc:
                print(f"[Cleanup] Could not delete {file.name}: {exc!r}")

    if deleted:
        print(f"[Cleanup] Deleted {deleted} stale file(s) from {TEMP_DIR}")
