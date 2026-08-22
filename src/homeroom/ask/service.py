"""The ask service: one question about one school, answered from its page and verified.

The pipeline, in order, with where each request can stop:

1. Validate the request (locale, CDS shape, question length). Malformed stops.
2. Rate limit per client and reserve two model calls from the daily cap.
   Refused stops, with a fixed string; the page is complete without it.
3. Load the school's evidence. An unknown CDS stops with a fixed refusal and
   no model call.
4. Ask the model to structure the question (call one). Run the lexical
   judgment guard over the question too. Either saying "judgment" wins.
5. Decide the fixed text: the ranking refusal, the outside-the-data note, the
   unclear note, or nothing. A question with no measures and no definitions
   stops here, with that text and no second call.
6. Ask the model to narrate the measures and definitions (call two).
7. Verify every claim. Withhold and count the failures. Return the rest.

Nothing here writes a question anywhere: no log, no file, no cache. The only
thing that persists between requests is the rate-limit bucket and the cap.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from homeroom.ask.corpus import Corpus
from homeroom.ask.evidence import SchoolEvidence, load_school
from homeroom.ask.limits import DailyCap, RateLimiter
from homeroom.ask.narration import (
    NARRATE_TOOL,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    narration_prompt,
)
from homeroom.ask.provider import Provider, ProviderError, ProviderRateLimited
from homeroom.ask.structuring import (
    MAX_QUESTION_CHARS,
    STRUCTURE_TOOL,
    Structured,
    StructuringError,
    parse_structured,
    pre_classify,
    structure_prompt,
)
from homeroom.ask.verifier import ShownClaim, WithheldClaim, parse_claims, verify
from homeroom.i18n import LOCALES, Locale, text

STRUCTURE_MAX_TOKENS = 600
NARRATE_MAX_TOKENS = 2500

STATUSES: tuple[str, ...] = (
    "answered",
    "refused",
    "unavailable",
    "rate_limited",
    "cap_reached",
    "invalid",
)


@dataclass(frozen=True)
class AskRequest:
    cds: str
    locale: str
    question: str
    client_key: str = "anonymous"
    """An opaque key for rate limiting. The service never sees an address."""


@dataclass(frozen=True)
class AskResponse:
    status: str
    kind: str
    locale: str
    school: dict[str, str] | None = None
    refusal: str | None = None
    intro: str | None = None
    claims: tuple[ShownClaim, ...] = ()
    withheld: int = 0
    withheld_reasons: dict[str, int] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    provenance: dict[str, object] = field(default_factory=dict)
    usage: dict[str, int] = field(default_factory=dict)
    structured: Structured | None = None
    """What the model said the question asked for; kept for the evaluation
    harness and the tests, not shown to a reader."""
    withheld_claims: tuple[WithheldClaim, ...] = ()
    """The withheld sentences and why. For the harness and the tests; the HTTP
    layer strips them, because an unverified sentence is exactly what a reader
    must not see."""

    def to_json(self, *, public: bool = False) -> dict[str, object]:
        data = asdict(self)
        data["claims"] = [asdict(c) for c in self.claims]
        data["structured"] = asdict(self.structured) if self.structured else None
        data["withheld_claims"] = [asdict(c) for c in self.withheld_claims]
        if public:
            del data["withheld_claims"]
            del data["structured"]
        return data


def _locale(value: str) -> Locale:
    """The page locale, or English for anything that is not a locale the site has.

    The invalid-request check that follows refuses the request; this only decides
    which language that refusal is written in.
    """
    return "es" if value == "es" else "en"


def _labels(locale: Locale) -> dict[str, str]:
    return {
        "ai": text(locale, "ask_label_ai"),
        "language": text(locale, "ask_label_language"),
        "no_ranking": text(locale, "footer_no_ranking"),
        "unaffiliated": text(locale, "footer_unaffiliated"),
    }


class AskService:
    def __init__(
        self,
        *,
        bundle_root: Path,
        corpus: Corpus,
        provider: Provider | None,
        limiter: RateLimiter | None = None,
        cap: DailyCap | None = None,
    ) -> None:
        self._root = bundle_root
        self._corpus = corpus
        self._provider = provider
        self._limiter = limiter or RateLimiter()
        self._cap = cap or DailyCap()

    @property
    def provenance(self) -> dict[str, object]:
        return {
            "provider": self._provider.name if self._provider else None,
            "model": self._provider.model if self._provider else None,
            "prompt_version": PROMPT_VERSION,
        }

    def _stop(
        self,
        status: str,
        kind: str,
        locale: Locale,
        *,
        refusal_key: str | None,
        evidence: SchoolEvidence | None = None,
        usage: dict[str, int] | None = None,
    ) -> AskResponse:
        provenance = dict(self.provenance)
        provenance["is_fixture"] = evidence.is_fixture if evidence else None
        return AskResponse(
            status=status,
            kind=kind,
            locale=locale,
            school={"cds": evidence.cds, "name": evidence.name} if evidence else None,
            refusal=text(locale, refusal_key) if refusal_key else None,
            labels=_labels(locale),
            provenance=provenance,
            usage=usage or {"model_calls": 0},
        )

    def answer(self, request: AskRequest) -> AskResponse:
        locale = _locale(request.locale)
        question = request.question.strip()
        if (
            request.locale not in LOCALES
            or not question
            or len(question) > MAX_QUESTION_CHARS
            or len(request.cds) != 14
            or not request.cds.isdigit()
        ):
            return self._stop("invalid", "invalid", locale, refusal_key=None)
        if not self._limiter.allow(request.client_key):
            return self._stop(
                "rate_limited",
                "rate_limited",
                locale,
                refusal_key="ask_refusal_rate_limited",
            )
        evidence = load_school(self._root, request.cds)
        if evidence is None:
            return self._stop(
                "refused",
                "unknown_school",
                locale,
                refusal_key="ask_refusal_unknown_school",
            )
        if self._provider is None:
            return self._stop(
                "unavailable",
                "unavailable",
                locale,
                refusal_key="ask_refusal_unavailable",
                evidence=evidence,
            )
        if not self._cap.reserve(2):
            return self._stop(
                "cap_reached",
                "cap_reached",
                locale,
                refusal_key="ask_refusal_cap_reached",
                evidence=evidence,
            )
        usage = {"model_calls": 0, "input_tokens": 0, "output_tokens": 0}
        try:
            return self._answer(request, question, locale, evidence, usage)
        except ProviderRateLimited:
            self._cap.release(2 - usage["model_calls"])
            return self._stop(
                "rate_limited",
                "rate_limited",
                locale,
                refusal_key="ask_refusal_rate_limited",
                evidence=evidence,
                usage=usage,
            )
        except (ProviderError, StructuringError):
            self._cap.release(2 - usage["model_calls"])
            return self._stop(
                "unavailable",
                "unavailable",
                locale,
                refusal_key="ask_refusal_unavailable",
                evidence=evidence,
                usage=usage,
            )

    def _call(
        self, user: str, tool: dict[str, object], max_tokens: int, usage: dict[str, int]
    ) -> tuple[dict[str, object], str]:
        if self._provider is None:  # pragma: no cover - guarded by answer()
            raise ProviderError("no provider")
        reply = self._provider.call_tool(
            system=SYSTEM_PROMPT, user=user, tool=tool, max_tokens=max_tokens
        )
        usage["model_calls"] += 1
        usage["input_tokens"] += reply.input_tokens
        usage["output_tokens"] += reply.output_tokens
        usage["cache_read_tokens"] = (
            usage.get("cache_read_tokens", 0) + reply.cache_read_tokens
        )
        return reply.input, reply.model

    def _answer(
        self,
        request: AskRequest,
        question: str,
        locale: Locale,
        evidence: SchoolEvidence,
        usage: dict[str, int],
    ) -> AskResponse:
        raw, model = self._call(
            structure_prompt(question, evidence, locale),
            STRUCTURE_TOOL,
            STRUCTURE_MAX_TOKENS,
            usage,
        )
        structured = parse_structured(raw, evidence)
        if pre_classify(question) == "judgment" and structured.kind != "judgment":
            structured = Structured(
                kind="judgment",
                measures=structured.measures,
                compare=structured.compare,
                definitions=structured.definitions,
                language=structured.language,
                dropped=structured.dropped,
            )
        refusal_key = {
            "judgment": "ask_refusal_judgment",
            "outside": "ask_refusal_outside",
            "unclear": "ask_refusal_unclear",
        }.get(structured.kind)
        provenance = dict(self.provenance)
        provenance["model"] = model
        provenance["is_fixture"] = evidence.is_fixture
        school = {"cds": evidence.cds, "name": evidence.name}

        if not structured.measures and not structured.definitions:
            self._cap.release(1)
            return AskResponse(
                status="refused",
                kind=structured.kind,
                locale=locale,
                school=school,
                refusal=text(locale, refusal_key or "ask_refusal_unclear"),
                labels=_labels(locale),
                provenance=provenance,
                usage=usage,
                structured=structured,
            )

        raw_claims, model = self._call(
            narration_prompt(
                question=question,
                structured=structured,
                evidence=evidence,
                corpus=self._corpus,
                locale=locale,
            ),
            NARRATE_TOOL,
            NARRATE_MAX_TOKENS,
            usage,
        )
        provenance["model"] = model
        verification = verify(parse_claims(raw_claims), evidence, self._corpus, locale)

        intro_key = (
            "ask_intro_definition"
            if structured.kind == "definition"
            else "ask_intro_measures"
        )
        all_absent = structured.measures and all(
            not evidence.records[m].school.reported for m in structured.measures
        )
        if all_absent and structured.kind == "measures":
            refusal_key = "ask_refusal_nothing_published"
        return AskResponse(
            status="answered",
            kind=structured.kind,
            locale=locale,
            school=school,
            refusal=text(locale, refusal_key) if refusal_key else None,
            intro=(
                text(locale, intro_key)
                if verification.shown
                else text(locale, "ask_empty_answer")
            ),
            claims=verification.shown,
            withheld=len(verification.withheld),
            withheld_reasons=verification.withheld_reasons,
            labels=_labels(locale),
            provenance=provenance,
            usage=usage,
            structured=structured,
            withheld_claims=verification.withheld,
        )
