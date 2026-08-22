"""Providers: the request shape, the error mapping, the env config, and the lazy import."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from homeroom.ask import provider as provider_module
from homeroom.ask.provider import (
    DEFAULT_MODEL,
    ENV_MODEL,
    ENV_PROVIDER,
    ProviderError,
    ProviderRateLimited,
    ScriptedProvider,
    ToolReply,
    provider_from_env,
)

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class _Block:
    type: str
    name: str = ""
    input: Any = None


@dataclass
class _Usage:
    input_tokens: int = 10
    output_tokens: int = 5
    cache_read_input_tokens: int = 7
    cache_creation_input_tokens: int = 0


@dataclass
class _Message:
    content: list[_Block]
    stop_reason: str = "tool_use"
    model: str = "claude-test"
    usage: _Usage = field(default_factory=_Usage)


class _Messages:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class _Client:
    def __init__(self, outcome: Any) -> None:
        self.messages = _Messages(outcome)


TOOL: dict[str, object] = {"name": "t", "input_schema": {"type": "object"}}


def test_the_request_is_a_forced_tool_call_with_a_cached_system_prompt() -> None:
    client = _Client(_Message([_Block("tool_use", "t", {"kind": "measures"})]))
    provider = provider_module._SdkProvider(client, "claude-test")
    reply = provider.call_tool(system="SYS", user="USER", tool=TOOL, max_tokens=99)
    assert reply == ToolReply(
        input={"kind": "measures"},
        model="claude-test",
        input_tokens=10,
        output_tokens=5,
        cache_read_tokens=7,
        cache_write_tokens=0,
    )
    sent = client.messages.kwargs
    assert sent["model"] == "claude-test"
    assert sent["max_tokens"] == 99
    assert sent["system"] == [
        {"type": "text", "text": "SYS", "cache_control": {"type": "ephemeral"}}
    ]
    assert sent["messages"] == [{"role": "user", "content": "USER"}]
    assert sent["tools"] == [TOOL]
    assert sent["tool_choice"] == {"type": "tool", "name": "t"}
    assert sent["thinking"] == {"type": "disabled"}


def test_a_reply_without_the_tool_call_is_a_provider_error() -> None:
    client = _Client(_Message([_Block("text")], stop_reason="end_turn"))
    provider = provider_module._SdkProvider(client, "m")
    with pytest.raises(ProviderError, match="did not call t"):
        provider.call_tool(system="s", user="u", tool=TOOL, max_tokens=1)
    client = _Client(_Message([_Block("tool_use", "t", "not a dict")]))
    with pytest.raises(ProviderError):
        provider_module._SdkProvider(client, "m").call_tool(
            system="s", user="u", tool=TOOL, max_tokens=1
        )


def test_sdk_errors_map_to_the_two_failure_kinds() -> None:
    anthropic = pytest.importorskip("anthropic")
    import httpx2 as httpx

    request = httpx.Request("POST", "https://example.invalid/")

    def status(code: int) -> Exception:
        response = httpx.Response(code, request=request)
        return anthropic.APIStatusError("x", response=response, body=None)

    with pytest.raises(ProviderRateLimited):
        provider_module._SdkProvider(
            _Client(
                anthropic.RateLimitError(
                    "x", response=httpx.Response(429, request=request), body=None
                )
            ),
            "m",
        ).call_tool(system="s", user="u", tool=TOOL, max_tokens=1)
    with pytest.raises(ProviderError, match="APIStatusError"):
        provider_module._SdkProvider(_Client(status(503)), "m").call_tool(
            system="s", user="u", tool=TOOL, max_tokens=1
        )
    with pytest.raises(ProviderError, match="APIConnectionError"):
        provider_module._SdkProvider(
            _Client(anthropic.APIConnectionError(request=request)), "m"
        ).call_tool(system="s", user="u", tool=TOOL, max_tokens=1)


def test_provider_from_env_reads_only_the_switches_never_a_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert provider_from_env({}) is None
    assert provider_from_env({ENV_PROVIDER: "none"}) is None
    assert provider_from_env({ENV_PROVIDER: ""}) is None
    with pytest.raises(ProviderError, match="not a provider"):
        provider_from_env({ENV_PROVIDER: "openai"})
    with pytest.raises(ProviderError, match=ENV_MODEL):
        provider_from_env({ENV_PROVIDER: "bedrock"})

    built: list[tuple[str, object]] = []

    class FakeAnthropic:
        name = "anthropic"

        def __init__(self, model: str = DEFAULT_MODEL) -> None:
            built.append(("anthropic", model))
            self.model = model

    class FakeBedrock:
        name = "bedrock"

        def __init__(self, model: str, region: str | None = None) -> None:
            built.append(("bedrock", (model, region)))
            self.model = model

    monkeypatch.setattr(provider_module, "AnthropicProvider", FakeAnthropic)
    monkeypatch.setattr(provider_module, "BedrockProvider", FakeBedrock)
    provider_from_env({ENV_PROVIDER: "anthropic"})
    provider_from_env({ENV_PROVIDER: "Anthropic", ENV_MODEL: "claude-opus-5"})
    provider_from_env(
        {
            ENV_PROVIDER: "bedrock",
            ENV_MODEL: "global.anthropic.x",
            "AWS_REGION": "us-west-2",
        }
    )
    assert built == [
        ("anthropic", DEFAULT_MODEL),
        ("anthropic", "claude-opus-5"),
        ("bedrock", ("global.anthropic.x", "us-west-2")),
    ]
    assert DEFAULT_MODEL == "claude-sonnet-5"


def test_the_scripted_provider_records_calls_and_refuses_unknown_tools() -> None:
    provider = ScriptedProvider({"t": lambda user: {"echo": user}})
    reply = provider.call_tool(system="s", user="hello", tool=TOOL, max_tokens=1)
    assert reply.input == {"echo": "hello"}
    assert provider.calls == [("t", "s", "hello")]
    with pytest.raises(ProviderError):
        provider.call_tool(system="s", user="u", tool={"name": "other"}, max_tokens=1)


def test_importing_the_service_does_not_import_the_sdk() -> None:
    """The core stays stdlib-only; the SDK loads only when a real provider is built."""
    code = (
        "import sys; import homeroom.ask.service, homeroom.ask.provider; "
        "assert 'anthropic' not in sys.modules, 'anthropic imported eagerly'"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": ""},
        check=False,
    )
    assert result.returncode == 0, result.stderr
