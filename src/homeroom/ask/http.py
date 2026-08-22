"""The HTTP edge of the ask service: one POST, a health check, and a Lambda handler.

Two entry points share one request shape and one response shape:

* :func:`serve` runs a stdlib ``ThreadingHTTPServer`` for local use, with
  ``POST /ask``, ``GET /health``, and the CORS preflight the ask page needs.
* :func:`lambda_handler` is the AWS Lambda Function URL handler (payload
  format 2.0) the prepared deployment shape in ``deploy/ask/`` points at.

Both are thin. Every decision about a question is :class:`AskService`'s; this
module parses JSON, maps the service status to an HTTP status, strips the
fields a reader must not see (the withheld sentences and the raw structured
lookup), and sets the headers. It never logs a question and never stores one:
the only thing derived from the request that outlives it is a salted hash of
the client address, used as the rate-limit key and never written anywhere.

Configuration is from the environment only:

``HOMEROOM_ASK_BUNDLE``       path to the evidence bundle (``index.json`` and ``schools/``)
``HOMEROOM_ASK_PROVIDER``     ``anthropic`` | ``bedrock`` | unset (service answers "unavailable")
``HOMEROOM_ASK_MODEL``        model id (default ``claude-sonnet-5``; required for bedrock)
``HOMEROOM_ASK_ORIGIN``       the site origin allowed to call (CORS and an Origin check)
``HOMEROOM_ASK_DAILY_CAP``    model calls per UTC day (default 400)
``HOMEROOM_ASK_PER_MINUTE``   requests per client per minute (default 6)
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from homeroom.ask.corpus import load_corpus
from homeroom.ask.limits import DailyCap, RateLimiter
from homeroom.ask.provider import Provider, provider_from_env
from homeroom.ask.service import AskRequest, AskService

STATUS_CODES: dict[str, int] = {
    "answered": 200,
    "refused": 200,
    "invalid": 400,
    "rate_limited": 429,
    "cap_reached": 429,
    "unavailable": 503,
}
MAX_BODY_BYTES = 4096
_SALT = secrets.token_bytes(16)
"""Per-process salt for the client key. A restart forgets every key."""


def client_key(address: str) -> str:
    """An opaque, per-process key for one client address. Never reversible here."""
    return hashlib.sha256(_SALT + address.encode("utf-8")).hexdigest()[:32]


def service_from_env(
    environ: dict[str, str] | None = None, provider: Provider | None = None
) -> AskService:
    env = dict(os.environ) if environ is None else environ
    bundle = Path(env.get("HOMEROOM_ASK_BUNDLE", "data/out/ask"))
    return AskService(
        bundle_root=bundle,
        corpus=load_corpus(),
        provider=provider if provider is not None else provider_from_env(env),
        limiter=RateLimiter(per_minute=float(env.get("HOMEROOM_ASK_PER_MINUTE", "6"))),
        cap=DailyCap(limit=int(env.get("HOMEROOM_ASK_DAILY_CAP", "400"))),
    )


def parse_body(raw: bytes) -> dict[str, Any] | None:
    if len(raw) > MAX_BODY_BYTES:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def handle_ask(
    service: AskService, body: dict[str, Any] | None, key: str
) -> tuple[int, dict[str, object]]:
    """Run one question through the service. Returns (HTTP status, public JSON)."""
    if body is None:
        return 400, {"status": "invalid", "error": "body must be a JSON object"}
    request = AskRequest(
        cds=str(body.get("cds", "")),
        locale=str(body.get("locale", "")),
        question=str(body.get("question", "")),
        client_key=key,
    )
    response = service.answer(request)
    return STATUS_CODES[response.status], response.to_json(public=True)


def health(service: AskService) -> dict[str, object]:
    return {"ok": True, **service.provenance}


def cors_headers(origin: str | None, allowed: str | None) -> dict[str, str]:
    """CORS for exactly the configured site origin, or nothing."""
    if not allowed or origin != allowed:
        return {}
    return {
        "access-control-allow-origin": allowed,
        "access-control-allow-methods": "POST, OPTIONS",
        "access-control-allow-headers": "content-type",
        "access-control-max-age": "600",
        "vary": "origin",
    }


def origin_allowed(origin: str | None, allowed: str | None) -> bool:
    """With an origin configured, only that origin may ask; without one, anyone
    may (local development). A browser always sends Origin on a cross-site
    POST; a missing Origin is treated as not allowed when one is configured."""
    return not allowed or origin == allowed


_BASE_HEADERS = {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
}


# ----------------------------------------------------------------------------------
# AWS Lambda Function URL (payload format 2.0)
# ----------------------------------------------------------------------------------

_SERVICE: AskService | None = None


def _service() -> AskService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = service_from_env()
    return _SERVICE


def _lambda_reply(
    status: int, body: dict[str, object], extra: dict[str, str]
) -> dict[str, object]:
    return {
        "statusCode": status,
        "headers": {**_BASE_HEADERS, **extra},
        "body": json.dumps(body, ensure_ascii=False),
    }


def lambda_handler(event: dict[str, Any], context: object = None) -> dict[str, object]:
    allowed = os.environ.get("HOMEROOM_ASK_ORIGIN") or None
    headers = {str(k).lower(): str(v) for k, v in (event.get("headers") or {}).items()}
    origin = headers.get("origin")
    cors = cors_headers(origin, allowed)
    http_info = (event.get("requestContext") or {}).get("http") or {}
    method = str(http_info.get("method", "GET")).upper()
    path = str(event.get("rawPath") or http_info.get("path") or "/")
    if method == "OPTIONS":
        return (
            _lambda_reply(204, {}, cors)
            if cors or not allowed
            else _lambda_reply(403, {}, {})
        )
    if method == "GET" and path.rstrip("/").endswith("health"):
        return _lambda_reply(200, health(_service()), cors)
    if method != "POST" or not path.rstrip("/").endswith("ask"):
        return _lambda_reply(404, {"status": "invalid", "error": "not found"}, cors)
    if not origin_allowed(origin, allowed):
        return _lambda_reply(
            403, {"status": "invalid", "error": "origin not allowed"}, {}
        )
    raw = event.get("body") or ""
    data = base64.b64decode(raw) if event.get("isBase64Encoded") else str(raw).encode()
    key = client_key(str(http_info.get("sourceIp", "")))
    status, body = handle_ask(_service(), parse_body(data), key)
    return _lambda_reply(status, body, cors)


# ----------------------------------------------------------------------------------
# Local server
# ----------------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    service: AskService
    allowed_origin: str | None

    def log_message(self, format: str, *args: object) -> None:
        """Silence the default access log: it would write the request line, and
        the only request line this server sees carries a family's question."""

    def _send(
        self, status: int, body: dict[str, object], extra: dict[str, str]
    ) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        for name, value in {**_BASE_HEADERS, **extra}.items():
            self.send_header(name, value)
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        cors = cors_headers(self.headers.get("origin"), self.allowed_origin)
        if self.allowed_origin and not cors:
            self._send(403, {}, {})
            return
        self.send_response(204)
        for name, value in cors.items():
            self.send_header(name, value)
        self.end_headers()

    def do_GET(self) -> None:
        cors = cors_headers(self.headers.get("origin"), self.allowed_origin)
        if self.path.rstrip("/").endswith("health"):
            self._send(200, health(self.service), cors)
        else:
            self._send(404, {"status": "invalid", "error": "not found"}, cors)

    def do_POST(self) -> None:
        origin = self.headers.get("origin")
        cors = cors_headers(origin, self.allowed_origin)
        if not self.path.rstrip("/").endswith("ask"):
            self._send(404, {"status": "invalid", "error": "not found"}, cors)
            return
        if not origin_allowed(origin, self.allowed_origin):
            self._send(403, {"status": "invalid", "error": "origin not allowed"}, {})
            return
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(min(length, MAX_BODY_BYTES + 1)) if length > 0 else b""
        key = client_key(self.client_address[0])
        status, body = handle_ask(self.service, parse_body(raw), key)
        self._send(status, body, cors)


def make_server(
    service: AskService, *, host: str = "127.0.0.1", port: int = 8765
) -> ThreadingHTTPServer:
    allowed = os.environ.get("HOMEROOM_ASK_ORIGIN") or None
    handler = type(
        "AskHandler", (_Handler,), {"service": service, "allowed_origin": allowed}
    )
    return ThreadingHTTPServer((host, port), handler)


def serve(host: str = "127.0.0.1", port: int = 8765) -> int:  # pragma: no cover
    server = make_server(service_from_env(), host=host, port=port)
    print(f"ask service on http://{host}:{port}/ask ({service_from_env().provenance})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="Serve the ask service locally.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    raise SystemExit(serve(args.host, args.port))
