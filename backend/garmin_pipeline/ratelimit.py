"""Rate limiting and HTTP 429 retry."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional


def compute_backoff(
    attempt: int,
    base_seconds: float,
    *,
    multiplier: float = 2.0,
    cap_seconds: float = 1800.0,
) -> float:
    """Exponential backoff for retry `attempt` (1-based), capped.

    attempt=1 -> base, attempt=2 -> base*multiplier, ... clamped to cap_seconds.
    """
    if attempt < 1:
        attempt = 1
    wait = base_seconds * (multiplier ** (attempt - 1))
    return min(wait, cap_seconds)


@dataclass
class RateLimitPolicy:
    min_call_interval_seconds: float = 5.0
    backoff_seconds: float = 1800.0
    backoff_multiplier: float = 2.0
    backoff_cap_seconds: float = 1800.0
    max_retries: int = 4


class TooManyRequests(Exception):
    """Raised/recognized when the upstream signals HTTP 429."""


class RateLimiter:
    """Enforces a minimum gap between calls and computes 429 backoff waits.

    `sleep_fn` and `clock_fn` are injectable for deterministic tests.
    """

    def __init__(
        self,
        policy: RateLimitPolicy,
        *,
        sleep_fn: Callable[[float], None] = time.sleep,
        clock_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.policy = policy
        self._sleep = sleep_fn
        self._clock = clock_fn
        self._last_call_at: Optional[float] = None

    def throttle(self) -> float:
        """Sleep just enough to honor the minimum inter-call gap. Returns seconds slept."""
        now = self._clock()
        slept = 0.0
        if self._last_call_at is not None:
            elapsed = now - self._last_call_at
            remaining = self.policy.min_call_interval_seconds - elapsed
            if remaining > 0:
                self._sleep(remaining)
                slept = remaining
        self._last_call_at = self._clock()
        return slept

    def backoff(self, attempt: int) -> float:
        """Sleep for the 429 backoff of this attempt. Returns seconds slept."""
        wait = compute_backoff(
            attempt,
            self.policy.backoff_seconds,
            multiplier=self.policy.backoff_multiplier,
            cap_seconds=self.policy.backoff_cap_seconds,
        )
        self._sleep(wait)
        return wait
