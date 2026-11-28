"""Durable background jobs.

`queue` owns persistence, leasing, retries and progress events; `handlers` holds
one function per job type. A request that needs long-running work enqueues a job
and returns immediately; the worker thread picks it up.
"""

from app.jobs.handlers import REGISTRY
from app.jobs.queue import (
    CANCELLABLE,
    JobHandle,
    JobWorker,
    cancel_job,
    drain,
    enqueue,
    get_job,
    get_worker,
    is_cancelled,
    job_events,
    job_to_dict,
    list_jobs,
    log_event,
    retry_job,
    start_worker,
    stop_worker,
    worker_status,
)

__all__ = [
    "CANCELLABLE",
    "JobHandle",
    "JobWorker",
    "REGISTRY",
    "cancel_job",
    "drain",
    "enqueue",
    "get_job",
    "get_worker",
    "is_cancelled",
    "job_events",
    "job_to_dict",
    "list_jobs",
    "log_event",
    "retry_job",
    "start_worker",
    "stop_worker",
    "worker_status",
]
