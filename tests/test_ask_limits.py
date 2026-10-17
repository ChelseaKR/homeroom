"""The shared daily cap: one ceiling across every copy of the service, failing closed.

The in-memory cap bounds one process. A Lambda execution environment that is
recycled, or a second one beside it, starts that count again at zero, so the
deployed cap is a DynamoDB item per UTC day written with a conditional
``UpdateItem``. Everything here runs against a fake table that applies the same
conditions the real one does; nothing reaches the network.
"""

from __future__ import annotations

import datetime as dt
import threading
import types
from pathlib import Path
from typing import Any

import pytest

from homeroom.ask import http as ask_http
from homeroom.ask.corpus import Corpus
from homeroom.ask.limits import (
    CapUnavailable,
    DailyCap,
    DynamoDayCounter,
    SharedDailyCap,
)
from homeroom.ask.provider import ScriptedProvider
from homeroom.ask.service import AskRequest, AskService
from homeroom.i18n import text

EXAMPLE = "01100170112345"
DAY = dt.date(2026, 10, 17)


class FakeClientError(Exception):
    """Shaped like botocore's ClientError: the code is in ``response``."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code, "Message": "fake"}}


class FakeTable:
    """A DynamoDB table that understands exactly the two updates the counter sends.

    It applies the condition and the update under one lock, which is the
    atomicity DynamoDB gives a single ``UpdateItem``. An unrecognized
    expression is a test failure, so the counter cannot drift into a request
    this fake would silently accept.
    """

    def __init__(self) -> None:
        self.items: dict[str, dict[str, int]] = {}
        self.requests: list[dict[str, Any]] = []
        self.fail_with: Exception | None = None
        self._lock = threading.Lock()

    def update_item(self, **request: Any) -> dict[str, Any]:
        self.requests.append(request)
        if self.fail_with is not None:
            raise self.fail_with
        assert set(request) == {
            "TableName",
            "Key",
            "UpdateExpression",
            "ConditionExpression",
            "ExpressionAttributeNames",
            "ExpressionAttributeValues",
        }
        day = request["Key"]["day"]["S"]
        names = request["ExpressionAttributeNames"]
        values = {
            k: int(v["N"]) for k, v in request["ExpressionAttributeValues"].items()
        }
        assert names["#calls"] == "calls"
        with self._lock:
            item = self.items.get(day)
            calls = None if item is None else item["calls"]
            if (
                request["UpdateExpression"]
                == "ADD #calls :calls SET #expires = :expires"
            ):
                assert request["ConditionExpression"] == (
                    "attribute_not_exists(#calls) OR #calls <= :room"
                )
                assert names["#expires"] == "expires_at"
                if calls is not None and calls > values[":room"]:
                    raise FakeClientError("ConditionalCheckFailedException")
                self.items[day] = {
                    "calls": (calls or 0) + values[":calls"],
                    "expires_at": values[":expires"],
                }
            elif request["UpdateExpression"] == "ADD #calls :minus":
                assert request["ConditionExpression"] == "#calls >= :calls"
                if calls is None or calls < values[":calls"]:
                    raise FakeClientError("ConditionalCheckFailedException")
                assert item is not None
                item["calls"] = calls + values[":minus"]
            else:  # pragma: no cover - a failure message, not a branch
                raise AssertionError(request["UpdateExpression"])
        return {}


def shared(
    table: FakeTable, limit: int, today: list[dt.date] | None = None
) -> SharedDailyCap:
    day = today if today is not None else [DAY]
    return SharedDailyCap(
        limit=limit,
        counter=DynamoDayCounter("homeroom-ask-cap", client=table),
        today=lambda: day[0],
    )


def test_a_recycled_container_does_not_start_again_at_zero() -> None:
    """The defect this replaces: a fresh copy of the in-memory cap reads zero."""
    memory = DailyCap(limit=4, today=lambda: DAY)
    assert memory.reserve(4)
    assert DailyCap(limit=4, today=lambda: DAY).reserve(4)  # 8 spent on a cap of 4

    table = FakeTable()
    assert shared(table, 4).reserve(4)
    assert not shared(table, 4).reserve(1)  # the next container sees the same 4
    assert table.items[DAY.isoformat()]["calls"] == 4


def test_two_containers_together_never_pass_the_cap() -> None:
    table = FakeTable()
    first, second = shared(table, 5), shared(table, 5)
    assert first.reserve(2)
    assert second.reserve(2)
    assert not first.reserve(2)  # 4 + 2 > 5: refused, nothing taken
    assert table.items[DAY.isoformat()]["calls"] == 4
    assert second.reserve(1)  # exactly to the cap
    assert not first.reserve(1)
    assert table.items[DAY.isoformat()]["calls"] == 5


def test_concurrent_reservations_take_exactly_the_cap() -> None:
    table = FakeTable()
    caps = [shared(table, 40) for _ in range(8)]
    taken: list[bool] = []
    lock = threading.Lock()

    def worker(cap: SharedDailyCap) -> None:
        for _ in range(10):
            ok = cap.reserve(2)
            with lock:
                taken.append(ok)

    threads = [threading.Thread(target=worker, args=(cap,)) for cap in caps]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert taken.count(True) == 20
    assert table.items[DAY.isoformat()]["calls"] == 40


def test_each_utc_day_has_its_own_item_and_it_expires() -> None:
    table = FakeTable()
    day = [DAY]
    cap = shared(table, 2, day)
    assert cap.reserve(2)
    assert not cap.reserve(1)
    day[0] = DAY + dt.timedelta(days=1)
    assert cap.reserve(2)
    assert set(table.items) == {"2026-10-17", "2026-10-18"}
    # TTL two days after the day's own midnight, so the item outlives its day.
    expected = dt.datetime(2026, 10, 19, tzinfo=dt.UTC).timestamp()
    assert table.items["2026-10-17"]["expires_at"] == int(expected)


def test_a_counter_that_cannot_be_reached_refuses() -> None:
    """Fail closed: no model call on a budget nobody can read."""
    table = FakeTable()
    cap = shared(table, 10)
    for error in (
        FakeClientError("ProvisionedThroughputExceededException"),
        FakeClientError("AccessDeniedException"),
        FakeClientError("ResourceNotFoundException"),
        TimeoutError("read timeout"),
        OSError("no route"),
    ):
        table.fail_with = error
        with pytest.raises(CapUnavailable) as raised:
            cap.reserve(2)
        # The type only; an SDK message can carry the request it was making.
        assert str(raised.value) == type(error).__name__


def test_a_request_bigger_than_the_cap_is_refused_without_a_write() -> None:
    table = FakeTable()
    cap = shared(table, 1)
    assert not cap.reserve(2)
    assert cap.reserve(0)
    assert table.requests == []
    assert not shared(table, 0).reserve(1)
    assert table.requests == []


def test_release_gives_back_and_never_below_zero() -> None:
    table = FakeTable()
    cap = shared(table, 4)
    assert cap.reserve(2)
    cap.release(1)
    assert table.items[DAY.isoformat()]["calls"] == 1
    cap.release(5)  # more than was taken: refused by the condition, nothing changes
    assert table.items[DAY.isoformat()]["calls"] == 1
    cap.release(0)
    assert len(table.requests) == 3


def test_a_release_that_fails_leaves_the_calls_counted() -> None:
    table = FakeTable()
    cap = shared(table, 4)
    assert cap.reserve(2)
    table.fail_with = TimeoutError("read timeout")
    cap.release(2)  # does not raise: the calls stay counted, which under-spends
    table.fail_with = None
    assert table.items[DAY.isoformat()]["calls"] == 2


def test_a_release_after_midnight_does_not_lower_the_new_day() -> None:
    table = FakeTable()
    day = [DAY]
    cap = shared(table, 4, day)
    assert cap.reserve(2)
    day[0] = DAY + dt.timedelta(days=1)
    other = shared(table, 4, day)
    assert other.reserve(2)
    cap.release(2)  # reserved yesterday: today's count must not move
    assert table.items["2026-10-18"]["calls"] == 2
    assert table.items["2026-10-17"]["calls"] == 2


def test_the_counter_errors_other_than_the_condition_propagate() -> None:
    table = FakeTable()
    counter = DynamoDayCounter("t", client=table)
    table.fail_with = FakeClientError("ThrottlingException")
    with pytest.raises(FakeClientError):
        counter.add(DAY, 1, limit=2)
    with pytest.raises(FakeClientError):
        counter.subtract(DAY, 1)
    table.fail_with = ValueError("no response attribute")
    with pytest.raises(ValueError):
        counter.add(DAY, 1, limit=2)
    weird = FakeClientError("x")
    weird.response = {"Error": "not a dict"}  # type: ignore[dict-item]
    table.fail_with = weird
    with pytest.raises(FakeClientError):
        counter.add(DAY, 1, limit=2)


def test_the_counter_writes_only_a_date_a_count_and_an_expiry() -> None:
    """Nothing about a request reaches the table."""
    table = FakeTable()
    counter = DynamoDayCounter("homeroom-ask-cap", client=table)
    assert counter.add(DAY, 2, limit=10)
    request = table.requests[0]
    assert request["TableName"] == "homeroom-ask-cap"
    assert request["Key"] == {"day": {"S": "2026-10-17"}}
    assert set(request["ExpressionAttributeNames"].values()) == {
        "calls",
        "expires_at",
    }
    assert request["ExpressionAttributeValues"][":room"] == {"N": "8"}


def test_without_an_injected_client_one_is_built_lazily(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """boto3 is imported on first use, with short timeouts, and never at import."""
    built: dict[str, Any] = {}
    table = FakeTable()

    def client(service: str, config: object) -> FakeTable:
        built["service"] = service
        built["config"] = config
        return table

    class Config:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    monkeypatch.setitem(
        __import__("sys").modules, "boto3", types.SimpleNamespace(client=client)
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "botocore.config",
        types.SimpleNamespace(Config=Config),
    )
    counter = DynamoDayCounter("homeroom-ask-cap")
    assert counter.add(DAY, 1, limit=2)
    assert counter.add(DAY, 1, limit=2)
    assert built["service"] == "dynamodb"
    assert built["config"].kwargs["connect_timeout"] == 2
    assert built["config"].kwargs["read_timeout"] == 2
    assert counter.client is table
    assert len(table.requests) == 2


def test_the_environment_chooses_the_shared_cap_when_a_table_is_named(
    fixture_bundle: Path,
) -> None:
    cap = ask_http.cap_from_env(
        {"HOMEROOM_ASK_DAILY_CAP": "7", "HOMEROOM_ASK_CAP_TABLE": "homeroom-ask-cap"}
    )
    assert isinstance(cap, SharedDailyCap)
    assert cap.limit == 7
    assert isinstance(cap.counter, DynamoDayCounter)
    assert cap.counter.table == "homeroom-ask-cap"
    assert cap.counter.client is None  # nothing is contacted until a reservation
    local = ask_http.cap_from_env({"HOMEROOM_ASK_CAP_TABLE": "  "})
    assert isinstance(local, DailyCap)
    assert local.limit == 400


def structure_measures(_: str) -> dict[str, object]:
    return {
        "kind": "measures",
        "measures": ["enrollment.total"],
        "compare": False,
        "definitions": [],
        "language": "en",
    }


def test_the_service_makes_no_model_call_when_the_cap_is_unreadable(
    fixture_bundle: Path, corpus: Corpus
) -> None:
    table = FakeTable()
    table.fail_with = TimeoutError("read timeout")
    provider = ScriptedProvider({"structure_question": structure_measures})
    svc = AskService(
        bundle_root=fixture_bundle,
        corpus=corpus,
        provider=provider,
        cap=shared(table, 10),
    )
    response = svc.answer(AskRequest(cds=EXAMPLE, locale="es", question="¿Cuántos?"))
    assert response.status == "unavailable"
    assert response.refusal == text("es", "ask_refusal_unavailable")
    assert response.usage == {"model_calls": 0}
    assert provider.calls == []


def test_the_service_spends_from_the_shared_count(
    fixture_bundle: Path, corpus: Corpus
) -> None:
    table = FakeTable()
    provider = ScriptedProvider(
        {
            "structure_question": structure_measures,
            "answer_with_claims": lambda _: {
                "claims": [
                    {
                        "kind": "figure",
                        "text": "The school enrolled 100 students in 2025-26.",
                        "cites": [f"{EXAMPLE}|enrollment.total|2025-26|school"],
                    }
                ]
            },
        }
    )

    def container() -> AskService:
        return AskService(
            bundle_root=fixture_bundle,
            corpus=corpus,
            provider=provider,
            cap=shared(table, 3),
        )

    request = AskRequest(cds=EXAMPLE, locale="en", question="How many?")
    assert container().answer(request).status == "answered"
    # A fresh container, as after a recycle: one call left, an answer needs two.
    response = container().answer(request)
    assert response.status == "cap_reached"
    assert response.refusal == text("en", "ask_refusal_cap_reached")
    assert table.items[DAY.isoformat()]["calls"] == 2


def test_a_retry_is_skipped_when_the_cap_becomes_unreadable(
    fixture_bundle: Path, corpus: Corpus
) -> None:
    table = FakeTable()
    attempts = {"n": 0}

    def malformed(_: str) -> dict[str, object]:
        attempts["n"] += 1
        table.fail_with = TimeoutError("read timeout")
        return {"claims": "not json ["}

    svc = AskService(
        bundle_root=fixture_bundle,
        corpus=corpus,
        provider=ScriptedProvider(
            {"structure_question": structure_measures, "answer_with_claims": malformed}
        ),
        cap=shared(table, 10),
    )
    response = svc.answer(AskRequest(cds=EXAMPLE, locale="en", question="How many?"))
    assert response.status == "answered"
    assert response.claims == ()
    assert attempts["n"] == 1
    assert response.usage["model_calls"] == 2
