"""Durable background jobs.

`queue` owns persistence, leasing, retries and progress events; `handlers` holds
one function per job type. A request that needs long-running work enqueues a job
and returns immediately; the worker thread picks it up.
"""

from app.jobs import handlers, queue

__all__ = ["handlers", "queue"]
