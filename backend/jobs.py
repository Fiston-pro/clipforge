"""
In-memory job store. No database — all state lives in this dict.
A server restart will clear all jobs. Acceptable for MVP.
"""

import uuid
from typing import Any, Dict, Optional

# In-memory job store: { job_id: { status, progress, message, url, error } }
_jobs: Dict[str, Dict[str, Any]] = {}


def create_job() -> str:
    """Create a new job entry and return its ID."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "pending",
        "progress": 0,
        "message": "Waiting to start...",
        "url": None,
        "error": None,
    }
    return job_id


def update_job(job_id: str, **kwargs: Any) -> None:
    """Update one or more fields of an existing job."""
    if job_id in _jobs:
        _jobs[job_id].update(kwargs)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Return a job dict or None if not found."""
    return _jobs.get(job_id)
