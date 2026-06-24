"""Background job helpers for long-running workspace operations."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from time import time_ns
from typing import Any


@dataclass(slots=True)
class JobRecord:
    """In-memory job state for progress reporting."""

    job_id: str
    kind: str
    status: str = 'queued'
    progress: float = 0.0
    message: str = 'Queued'
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at_ns: int = field(default_factory=time_ns)
    updated_at_ns: int = field(default_factory=time_ns)

    def to_dict(self) -> dict[str, Any]:
        return {
            'job_id': self.job_id,
            'kind': self.kind,
            'status': self.status,
            'progress': self.progress,
            'message': self.message,
            'result': self.result,
            'error': self.error,
            'created_at_ns': self.created_at_ns,
            'updated_at_ns': self.updated_at_ns,
        }


ProgressCallback = Callable[[float, str], None]


class JobManager:
    """Track background jobs and their latest progress."""

    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.RLock()
        self._jobs: dict[str, JobRecord] = {}

    def submit(self, kind: str, task: Callable[[ProgressCallback], dict[str, Any] | None]) -> str:
        job_id = uuid.uuid4().hex
        record = JobRecord(job_id=job_id, kind=kind)
        with self._lock:
            self._jobs[job_id] = record

        def report(progress: float, message: str) -> None:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                job.progress = max(0.0, min(1.0, float(progress)))
                job.message = str(message)
                job.status = 'running'
                job.updated_at_ns = time_ns()

        def runner() -> None:
            report(0.01, 'Starting')
            try:
                result = task(report)
            except Exception as exc:  # pragma: no cover - defensive
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job is not None:
                        job.status = 'failed'
                        job.error = str(exc)
                        job.message = 'Failed'
                        job.updated_at_ns = time_ns()
                return
            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    job.status = 'complete'
                    job.progress = 1.0
                    job.message = 'Complete'
                    job.result = result
                    job.updated_at_ns = time_ns()

        self._executor.submit(runner)
        return job_id

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[JobRecord]:
        with self._lock:
            return list(self._jobs.values())
