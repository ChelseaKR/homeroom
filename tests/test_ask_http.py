"""The HTTP edge: status mapping, CORS, origin check, no question ever logged."""

from __future__ import annotations

import base64
import http.client
import json
import threading
from pathlib import Path

import pytest

from homeroom.ask import http as ask_http
from homeroom.ask.corpus import Corpus
from homeroom.ask.provider import ScriptedProvider
from homeroom.ask.service import AskService

EXAMPLE = "01100170112345"
TOTAL = f"{EXAMPLE}|enrollment.total|2025-26"


def judgment_provider() -> ScriptedProvider:
    return ScriptedProvider(
        {
            "structure_question": lambda _: {
                "kind": "judgment",
                "measures": [],
                "compare": False,
                "definitions": [],
                "language": "en",
            }
        }
    )


@pytest.fixture
def service(fixture_bundle: Path, corpus: Corpus) -> AskService:
    return AskService(
        bundle_root=fixture_bundle, corpus=corpus, provider=judgment_provider()
    )


def test_handle_ask_maps_statuses_and_strips_private_fields(
    service: AskService,
) -> None:
    status, body = ask_http.handle_ask(
        service, {"cds": EXAMPLE, "locale": "en", "question": "Good?"}, "k"
    )
    assert status == 200
    assert body["status"] == "refused"
    assert "withheld_claims" not in body and "structured" not in body
    assert body["labels"]["ai"]
    status, body = ask_http.handle_ask(
        service, {"cds": "x", "locale": "en", "question": "?"}, "k"
    )
    assert status == 400
    status, body = ask_http.handle_ask(service, None, "k")
    assert status == 400
    status, body = ask_http.handle_ask(
        service, {"cds": "99999999999999", "locale": "en", "question": "Good?"}, "k"
    )
    assert (status, body["kind"]) == (200, "unknown_school")


def test_unavailable_and_rate_limited_map_to_503_and_429(
    fixture_bundle: Path, corpus: Corpus
) -> None:
    no_provider = AskService(bundle_root=fixture_bundle, corpus=corpus, provider=None)
    status, body = ask_http.handle_ask(
        no_provider, {"cds": EXAMPLE, "locale": "es", "question": "¿Bien?"}, "k"
    )
    assert (status, body["status"]) == (503, "unavailable")
    limited = AskService(
        bundle_root=fixture_bundle,
        corpus=corpus,
        provider=judgment_provider(),
        limiter=ask_http.RateLimiter(per_minute=1, burst=1),
    )
    first = ask_http.handle_ask(
        limited, {"cds": EXAMPLE, "locale": "en", "question": "?"}, "k"
    )
    second = ask_http.handle_ask(
        limited, {"cds": EXAMPLE, "locale": "en", "question": "?"}, "k"
    )
    assert first[0] == 200 and second[0] == 429


def test_body_parsing_refuses_oversize_and_non_objects() -> None:
    assert ask_http.parse_body(b"[]") is None
    assert ask_http.parse_body(b"not json") is None
    assert ask_http.parse_body(b"\xff") is None
    assert ask_http.parse_body(b"{" + b" " * ask_http.MAX_BODY_BYTES + b"}") is None
    assert ask_http.parse_body(b'{"a": 1}') == {"a": 1}


def test_cors_is_for_exactly_the_configured_origin() -> None:
    assert (
        ask_http.cors_headers("https://a.example", "https://a.example")[
            "access-control-allow-origin"
        ]
        == "https://a.example"
    )
    assert ask_http.cors_headers("https://evil.example", "https://a.example") == {}
    assert ask_http.cors_headers(None, "https://a.example") == {}
    assert ask_http.cors_headers("https://a.example", None) == {}
    assert ask_http.origin_allowed("https://a.example", "https://a.example")
    assert not ask_http.origin_allowed("https://evil.example", "https://a.example")
    assert not ask_http.origin_allowed(None, "https://a.example")
    assert ask_http.origin_allowed(None, None)


def test_the_client_key_is_a_salted_hash_not_an_address() -> None:
    key = ask_http.client_key("203.0.113.9")
    assert "203.0.113.9" not in key and len(key) == 32
    assert key == ask_http.client_key("203.0.113.9")
    assert key != ask_http.client_key("203.0.113.10")


def test_the_lambda_handler_speaks_function_url_payload_v2(
    monkeypatch: pytest.MonkeyPatch, service: AskService
) -> None:
    monkeypatch.setattr(ask_http, "_SERVICE", service)
    monkeypatch.setenv("HOMEROOM_ASK_ORIGIN", "https://homeroom.example")

    def event(
        method: str,
        path: str,
        body: object = None,
        origin: str | None = None,
        b64: bool = False,
    ) -> dict[str, object]:
        raw = json.dumps(body) if body is not None else ""
        return {
            "rawPath": path,
            "headers": {"Origin": origin} if origin else {},
            "requestContext": {
                "http": {"method": method, "path": path, "sourceIp": "198.51.100.7"}
            },
            "body": base64.b64encode(raw.encode()).decode() if b64 else raw,
            "isBase64Encoded": b64,
        }

    ok = ask_http.lambda_handler(
        event(
            "POST",
            "/ask",
            {"cds": EXAMPLE, "locale": "en", "question": "Good?"},
            "https://homeroom.example",
            b64=True,
        )
    )
    assert ok["statusCode"] == 200
    headers = ok["headers"]
    assert isinstance(headers, dict)
    assert headers["access-control-allow-origin"] == "https://homeroom.example"
    assert headers["cache-control"] == "no-store"
    assert json.loads(str(ok["body"]))["kind"] == "judgment"

    forbidden = ask_http.lambda_handler(
        event(
            "POST",
            "/ask",
            {"cds": EXAMPLE, "locale": "en", "question": "Good?"},
            "https://evil.example",
        )
    )
    assert forbidden["statusCode"] == 403
    assert (
        ask_http.lambda_handler(
            event("POST", "/ask", {"cds": EXAMPLE, "locale": "en", "question": "Good?"})
        )["statusCode"]
        == 403
    )
    assert (
        ask_http.lambda_handler(
            event("OPTIONS", "/ask", origin="https://homeroom.example")
        )["statusCode"]
        == 204
    )
    assert (
        ask_http.lambda_handler(
            event("OPTIONS", "/ask", origin="https://evil.example")
        )["statusCode"]
        == 403
    )
    health = ask_http.lambda_handler(
        event("GET", "/health", origin="https://homeroom.example")
    )
    assert health["statusCode"] == 200
    assert json.loads(str(health["body"]))["ok"] is True
    assert ask_http.lambda_handler(event("GET", "/nope"))["statusCode"] == 404
    bad = ask_http.lambda_handler(
        event("POST", "/ask", "not an object", "https://homeroom.example")
    )
    assert bad["statusCode"] == 400

    monkeypatch.delenv("HOMEROOM_ASK_ORIGIN")
    open_options = ask_http.lambda_handler(event("OPTIONS", "/ask"))
    assert open_options["statusCode"] == 204


def test_the_lambda_handler_builds_its_service_from_env_once(
    monkeypatch: pytest.MonkeyPatch, fixture_bundle: Path
) -> None:
    monkeypatch.setattr(ask_http, "_SERVICE", None)
    monkeypatch.setenv("HOMEROOM_ASK_BUNDLE", str(fixture_bundle))
    monkeypatch.delenv("HOMEROOM_ASK_PROVIDER", raising=False)
    monkeypatch.delenv("HOMEROOM_ASK_ORIGIN", raising=False)
    reply = ask_http.lambda_handler(
        {
            "rawPath": "/ask",
            "headers": {},
            "requestContext": {"http": {"method": "POST", "sourceIp": "1.2.3.4"}},
            "body": json.dumps(
                {"cds": EXAMPLE, "locale": "en", "question": "How many?"}
            ),
        }
    )
    assert reply["statusCode"] == 503
    assert ask_http._service() is ask_http._service()


def test_the_local_server_answers_over_real_http_without_logging(
    service: AskService,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("HOMEROOM_ASK_ORIGIN", "https://homeroom.example")
    server = ask_http.make_server(service, port=0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def call(
        method: str, path: str, body: bytes | None = None, origin: str | None = None
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        headers = {"content-type": "application/json"}
        if origin:
            headers["origin"] = origin
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read()
        connection.close()
        return (
            response.status,
            {k.lower(): v for k, v in response.getheaders()},
            payload,
        )

    try:
        body = json.dumps(
            {"cds": EXAMPLE, "locale": "en", "question": "Is it good? SECRET"}
        ).encode()
        status, headers, payload = call(
            "POST", "/ask", body, "https://homeroom.example"
        )
        assert status == 200
        assert headers["access-control-allow-origin"] == "https://homeroom.example"
        assert json.loads(payload)["kind"] == "judgment"
        assert call("OPTIONS", "/ask", None, "https://homeroom.example")[0] == 204
        status, _, payload = call("GET", "/health")
        assert status == 200 and json.loads(payload)["ok"] is True
        assert call("POST", "/ask", body)[0] == 403  # no origin
        assert call("GET", "/nope")[0] == 404
        assert call("POST", "/nope", body)[0] == 404
        assert call("OPTIONS", "/ask", None, "https://evil.example")[0] == 403
    finally:
        server.shutdown()
        server.server_close()
    captured = capsys.readouterr()
    assert "SECRET" not in captured.out + captured.err


def test_service_from_env_reads_the_switches(fixture_bundle: Path) -> None:
    svc = ask_http.service_from_env(
        {"HOMEROOM_ASK_BUNDLE": str(fixture_bundle), "HOMEROOM_ASK_DAILY_CAP": "3"},
        provider=judgment_provider(),
    )
    assert svc.provenance["provider"] == "scripted"
    assert svc._cap.remaining() == 3
