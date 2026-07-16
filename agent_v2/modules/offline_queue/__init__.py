"""Module 12: Offline Queue.

On-disk rolling queue for telemetry frames that can't be delivered live.
Bounded (max 5000 files) with oldest-wins eviction.

Public API:
    enqueue(frame), drain() -> iterator, depth() -> int
"""
from .queue import enqueue, drain, depth  # noqa: F401

__all__ = ["enqueue", "drain", "depth"]
