"""Cost controls: a per-client rate limit and a hard daily cap, from the first commit.

Both are in-memory and process-local, which is honest about what they are: a
bound on what one running copy of the service will spend, not a global ledger.
A deployment with more than one copy needs a shared counter, and the prepared
deployment shape (``deploy/ask/``) says so; until then the cap here and the
reserved concurrency there are the envelope.

A refused request is refused before any model call and costs nothing. The
page it came from is complete without the answer, and the fixed strings the
service returns say so.
"""

from __future__ import annotations

import datetime as dt
import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    """A token bucket per client key.

    ``burst`` requests may arrive at once; after that one more is allowed
    every ``60 / per_minute`` seconds. Keys are whatever the caller hashes the
    client to; the service never stores the raw address.
    """

    per_minute: float = 6.0
    burst: int = 3
    clock: Callable[[], float] = time.monotonic
    _buckets: dict[str, tuple[float, float]] = field(default_factory=dict)

    def allow(self, key: str) -> bool:
        now = self.clock()
        tokens, last = self._buckets.get(key, (float(self.burst), now))
        tokens = min(float(self.burst), tokens + (now - last) * self.per_minute / 60.0)
        if tokens < 1.0:
            self._buckets[key] = (tokens, now)
            return False
        self._buckets[key] = (tokens - 1.0, now)
        if len(self._buckets) > 10_000:
            self._buckets = {
                k: v for k, v in self._buckets.items() if now - v[1] < 600.0
            }
        return True


@dataclass
class DailyCap:
    """A hard ceiling on model calls per UTC day.

    ``limit`` is model calls, not requests: an answered question costs two
    (structure, narrate), a refusal before the model costs none.
    """

    limit: int = 400
    today: Callable[[], dt.date] = lambda: dt.datetime.now(dt.UTC).date()
    _day: dt.date | None = None
    _used: int = 0

    def _roll(self) -> None:
        day = self.today()
        if day != self._day:
            self._day = day
            self._used = 0

    def remaining(self) -> int:
        self._roll()
        return max(0, self.limit - self._used)

    def reserve(self, calls: int) -> bool:
        """Take ``calls`` from today's budget, or refuse without taking any."""
        self._roll()
        if self._used + calls > self.limit:
            return False
        self._used += calls
        return True

    def release(self, calls: int) -> None:
        """Give back calls that were reserved but never made."""
        self._roll()
        self._used = max(0, self._used - calls)
