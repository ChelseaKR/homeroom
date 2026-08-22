"""Model providers: the public ``anthropic`` SDK, configured from the environment.

The service asks the model for exactly one thing per call: a tool call against
a fixed schema. :class:`Provider` is that one operation. Two real providers
exist, the Anthropic API (default model ``claude-sonnet-5``) and Amazon Bedrock
through the same SDK, plus a :class:`ScriptedProvider` that tests and the
offline evaluation path use, which never touches the network.

Credentials come from the environment only (``ANTHROPIC_API_KEY``, or the AWS
credential chain for Bedrock). Nothing here reads, writes, or logs a key, and
nothing here logs a question: the SDK is constructed with its defaults and the
request body is never retained.

The SDK is imported lazily inside the real providers, so importing this module
(and therefore the service, the verifier, and the tests) needs no ``anthropic``
installed and the core package stays stdlib-only.

Thinking is disabled explicitly on every call. Both calls are forced tool
calls against a schema, which is the shape that works identically across the
models this project might run on, and the reasoning the product depends on
happens in the verifier, not in the model.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

DEFAULT_MODEL = "claude-sonnet-5"
ENV_PROVIDER = "HOMEROOM_ASK_PROVIDER"
ENV_MODEL = "HOMEROOM_ASK_MODEL"
ENV_REGION = "AWS_REGION"


class ProviderError(Exception):
    """The model could not be reached or did not return a usable tool call."""


class ProviderRateLimited(ProviderError):
    """The provider itself said 429."""


@dataclass(frozen=True)
class ToolReply:
    input: dict[str, object]
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class Provider(Protocol):
    name: str
    model: str

    def call_tool(
        self, *, system: str, user: str, tool: dict[str, object], max_tokens: int
    ) -> ToolReply: ...


def _extract_tool_input(message: Any, tool_name: str) -> dict[str, object]:
    for block in message.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            payload = block.input
            if isinstance(payload, dict):
                return dict(payload)
    raise ProviderError(
        f"the model did not call {tool_name}; stop_reason={message.stop_reason!r}"
    )


def _usage(message: Any) -> dict[str, int]:
    usage = getattr(message, "usage", None)
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "cache_read_tokens": int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        "cache_write_tokens": int(
            getattr(usage, "cache_creation_input_tokens", 0) or 0
        ),
    }


class _SdkProvider:
    """Shared request shape for the two real providers."""

    name = "anthropic"

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self.model = model

    def call_tool(
        self, *, system: str, user: str, tool: dict[str, object], max_tokens: int
    ) -> ToolReply:
        import anthropic

        try:
            message = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user}],
                tools=[tool],
                tool_choice={"type": "tool", "name": str(tool["name"])},
                thinking={"type": "disabled"},
            )
        except anthropic.RateLimitError as error:
            raise ProviderRateLimited(str(error)) from error
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as error:
            raise ProviderError(type(error).__name__) from error
        return ToolReply(
            input=_extract_tool_input(message, str(tool["name"])),
            model=str(getattr(message, "model", self.model)),
            **_usage(message),
        )


class AnthropicProvider(_SdkProvider):
    """The Anthropic API. ``ANTHROPIC_API_KEY`` (or an ``ant auth`` profile) from env."""

    name = "anthropic"

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        import anthropic

        super().__init__(anthropic.Anthropic(), model)


class BedrockProvider(_SdkProvider):
    """Amazon Bedrock through the same SDK. AWS credentials from the usual chain.

    The model id is Bedrock's (an inference-profile id such as
    ``global.anthropic.claude-sonnet-4-6``), given by ``HOMEROOM_ASK_MODEL``;
    there is no default, because the id that works depends on the account.
    """

    name = "bedrock"

    def __init__(self, model: str, region: str | None = None) -> None:
        import anthropic

        kwargs: dict[str, Any] = {}
        if region:
            kwargs["aws_region"] = region
        super().__init__(anthropic.AnthropicBedrock(**kwargs), model)


@dataclass
class ScriptedProvider:
    """Replies from a script, for tests and the offline evaluation path.

    ``replies`` maps a tool name to a callable that takes the user turn and
    returns the tool input. Calls are recorded so a test can assert what the
    model was shown.
    """

    replies: dict[str, Callable[[str], dict[str, object]]]
    model: str = "scripted"
    name: str = "scripted"
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    def call_tool(
        self, *, system: str, user: str, tool: dict[str, object], max_tokens: int
    ) -> ToolReply:
        tool_name = str(tool["name"])
        self.calls.append((tool_name, system, user))
        reply = self.replies.get(tool_name)
        if reply is None:
            raise ProviderError(f"scripted provider has no reply for {tool_name}")
        return ToolReply(input=reply(user), model=self.model)


def provider_from_env(environ: dict[str, str] | None = None) -> Provider | None:
    """The configured provider, or ``None`` when the service should run without one.

    ``HOMEROOM_ASK_PROVIDER`` is ``anthropic``, ``bedrock``, or unset/``none``.
    ``HOMEROOM_ASK_MODEL`` overrides the model (required for Bedrock). No value
    of any credential is read here; the SDK reads its own.
    """
    env = os.environ if environ is None else environ
    which = env.get(ENV_PROVIDER, "none").strip().lower()
    model = env.get(ENV_MODEL, "").strip()
    if which in ("", "none"):
        return None
    if which == "anthropic":
        return AnthropicProvider(model or DEFAULT_MODEL)
    if which == "bedrock":
        if not model:
            raise ProviderError(f"{ENV_MODEL} is required for the bedrock provider")
        return BedrockProvider(model, env.get(ENV_REGION))
    raise ProviderError(
        f"{ENV_PROVIDER}={which!r} is not a provider this service knows"
    )
