"""Cost controls: a per-client rate limit and a hard daily cap, from the first commit.

The rate limit is in-memory and process-local: a bound on how fast one client
can ask one running copy of the service, not a global ledger.

The daily cap comes in two shapes behind one interface, :class:`Cap`:

* :class:`DailyCap` counts in memory. It is what tests, the evaluation harness
  and a local server use, and it is honest only about one process: a Lambda
  execution environment that is recycled, or a second one started beside it,
  begins again at zero, so N copies is not N times the cap -- it is no ceiling.
* :class:`SharedDailyCap` counts in one shared item per UTC day, through an
  injectable :class:`DayCounter`. :class:`DynamoDayCounter` is the deployed one:
  an atomic, conditional ``UpdateItem`` that adds the calls only if the total
  would stay within the cap. If the counter cannot be reached the cap refuses
  (:class:`CapUnavailable`): no model call is made on a budget nobody can read.

A refused request is refused before any model call and costs nothing. The
page it came from is complete without the answer, and the fixed strings the
service returns say so.

Nothing here sees a question. The shared counter's item holds a date, a count
and an expiry time, and nothing else.
"""

from __future__ import annotations

import datetime as dt
import importlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


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


def utc_today() -> dt.date:
    return dt.datetime.now(dt.UTC).date()


class Cap(Protocol):
    """A daily budget of model calls.

    ``reserve`` takes calls or refuses without taking any; it raises
    :class:`CapUnavailable` when it cannot tell, and the caller treats that as
    a refusal. ``release`` gives back calls reserved and never made, and never
    raises: a release that fails leaves the calls counted, which only ever
    errs toward spending less.
    """

    def reserve(self, calls: int) -> bool: ...

    def release(self, calls: int) -> None: ...


class CapUnavailable(Exception):
    """The shared counter could not be read or written. The caller refuses."""


@dataclass
class DailyCap:
    """A hard ceiling on model calls per UTC day.

    ``limit`` is model calls, not requests: an answered question costs two
    (structure, narrate), a refusal before the model costs none.
    """

    limit: int = 400
    today: Callable[[], dt.date] = utc_today
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


class DayCounter(Protocol):
    """One shared count of model calls per UTC day."""

    def add(self, day: dt.date, calls: int, *, limit: int) -> bool:
        """Atomically add ``calls`` to ``day``'s count if the total stays within
        ``limit``. True if added; False, with nothing added, if it would not.
        Raises on anything else (unreachable, throttled, misconfigured)."""
        ...

    def subtract(self, day: dt.date, calls: int) -> None:
        """Give back up to ``calls`` from ``day``'s count, never below zero."""
        ...


@dataclass
class SharedDailyCap:
    """A hard ceiling on model calls per UTC day, across every running copy.

    The count lives in a :class:`DayCounter`, so a fresh execution environment
    reads the same total as the one before it. Fail closed: if the counter
    raises, :meth:`reserve` raises :class:`CapUnavailable` and the service
    makes no model call.
    """

    limit: int
    counter: DayCounter
    today: Callable[[], dt.date] = utc_today
    _reserved_day: dt.date | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def reserve(self, calls: int) -> bool:
        if calls <= 0:
            return True
        if calls > self.limit:
            return False
        day = self.today()
        try:
            taken = self.counter.add(day, calls, limit=self.limit)
        except Exception as error:
            # The type only, never the message: an SDK error can carry the
            # request it was making, and nothing about a request is logged.
            raise CapUnavailable(type(error).__name__) from error
        if taken:
            with self._lock:
                self._reserved_day = day
        return taken

    def release(self, calls: int) -> None:
        if calls <= 0:
            return
        day = self.today()
        with self._lock:
            reserved = self._reserved_day
        if day != reserved:
            # The reservation was made on a day that has ended. Its calls stay
            # on that day's count; taking them off today's would let today
            # spend past its cap.
            return
        try:
            self.counter.subtract(day, calls)
        except Exception:
            # See Cap: a release that fails leaves the calls counted, which
            # only ever errs toward spending less.
            return


def _error_code(error: Exception) -> str | None:
    """The AWS error code of a botocore ``ClientError``, read without importing botocore."""
    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return None
    detail = response.get("Error")
    if not isinstance(detail, dict):
        return None
    code = detail.get("Code")
    return code if isinstance(code, str) else None


_CONDITION_FAILED = "ConditionalCheckFailedException"


@dataclass
class DynamoDayCounter:
    """The shared day counter, one DynamoDB item per UTC day.

    The item is ``{"day": "YYYY-MM-DD", "calls": N, "expires_at": epoch}``.
    Every write is a single ``UpdateItem`` with a condition, which DynamoDB
    applies atomically, so two copies reserving at once cannot both take the
    last calls. ``UpdateItem`` is also the only action the function's role is
    granted on the table: it creates the item on the day's first call, and no
    read is needed, because the condition is the read.

    ``expires_at`` lets DynamoDB's TTL delete a day's item two days after it
    ends; the key is the date, so a late deletion changes nothing.

    ``client`` is injectable so tests use a fake and make no network call.
    Without one, a boto3 client is built on first use with short timeouts:
    boto3 is in the deployment package already (``anthropic[bedrock]`` brings
    it, and the Lambda runtime carries one), and is imported by name so the
    core package and the type check need neither.
    """

    table: str
    client: Any = None
    keep_days: int = 2

    def _client(self) -> Any:
        if self.client is None:
            boto3 = importlib.import_module("boto3")
            config = importlib.import_module("botocore.config")
            self.client = boto3.client(
                "dynamodb",
                config=config.Config(
                    connect_timeout=2,
                    read_timeout=2,
                    retries={"max_attempts": 2, "mode": "standard"},
                ),
            )
        return self.client

    def _expires(self, day: dt.date) -> int:
        end = dt.datetime.combine(
            day + dt.timedelta(days=self.keep_days), dt.time(), tzinfo=dt.UTC
        )
        return int(end.timestamp())

    def add(self, day: dt.date, calls: int, *, limit: int) -> bool:
        try:
            self._client().update_item(
                TableName=self.table,
                Key={"day": {"S": day.isoformat()}},
                UpdateExpression="ADD #calls :calls SET #expires = :expires",
                ConditionExpression="attribute_not_exists(#calls) OR #calls <= :room",
                ExpressionAttributeNames={
                    "#calls": "calls",
                    "#expires": "expires_at",
                },
                ExpressionAttributeValues={
                    ":calls": {"N": str(calls)},
                    ":room": {"N": str(limit - calls)},
                    ":expires": {"N": str(self._expires(day))},
                },
            )
        except Exception as error:
            if _error_code(error) == _CONDITION_FAILED:
                return False
            raise
        return True

    def subtract(self, day: dt.date, calls: int) -> None:
        try:
            self._client().update_item(
                TableName=self.table,
                Key={"day": {"S": day.isoformat()}},
                UpdateExpression="ADD #calls :minus",
                ConditionExpression="#calls >= :calls",
                ExpressionAttributeNames={"#calls": "calls"},
                ExpressionAttributeValues={
                    ":minus": {"N": str(-calls)},
                    ":calls": {"N": str(calls)},
                },
            )
        except Exception as error:
            if _error_code(error) == _CONDITION_FAILED:
                return
            raise
