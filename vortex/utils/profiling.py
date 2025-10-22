"""Runtime profiling helpers for Vortex."""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from typing import Dict, Iterator

from .logging import get_logger

logger = get_logger(__name__)


@dataclass
class ProfileEvent:
    """Data structure representing a profiling measurement."""

    name: str
    duration: float


@contextlib.contextmanager
def profile(name: str) -> Iterator[None]:
    """Context manager that records execution time.

    Profiling information is emitted as structured logs. The approach avoids
    hard dependencies on heavyweight profilers while still providing high-level
    telemetry operators can aggregate. Using a context manager keeps the API
    unobtrusive and easy to adopt throughout the codebase.
    """

    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        logger.debug("profile", extra={"event": name, "duration": duration})


__all__ = ["profile", "ProfileEvent"]
