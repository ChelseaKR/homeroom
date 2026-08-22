"""The service end to end, with a scripted model: every stop, every branch, no network."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from homeroom.ask.corpus import Corpus
from homeroom.ask.limits import DailyCap, RateLimiter
from homeroom.ask.narration import PROMPT_VERSION, SYSTEM_PROMPT
from homeroom.ask.provider import ProviderError, ProviderRateLimited, ScriptedProvider
from homeroom.ask.service import STATUSES, AskRequest, AskService
from homeroom.i18n import text

EXAMPLE = "01100170112345"
NEVER_MENTIONED = "01100170176543"
TOTAL = f"{EXAMPLE}|enrollment.total|2025-26"
RATE = f"{EXAMPLE}|absenteeism.total|2024-25"
WITHHELD = f"{EXAMPLE}|enrollment.group.RE_B|2025-26"

Reply = Callable[[str], dict[str, object]]


def structure(kind: str, measures: list[str], **extra: object) -> Reply:
    def reply(_: str) -> dict[str, object]:
        out: dict[str, object] = {
            "kind": kind,
            "measures": measures,
            "compare": False,
            "definitions": [],
            "language": "en",
        }
        out.update(extra)
        return out

    return reply


def claims(*items: dict[str, object]) -> Reply:
    return lambda _: {"claims": list(items)}


GOOD_CLAIMS = claims(
    {
        "kind": "figure",
        "text": "In 2024-25 the chronic absenteeism rate was 12.5%.",
        "cites": [f"{RATE}|school"],
    },
    {
        "kind": "comparison",
        "text": "That is higher than the district figure of 11%.",
        "cites": [f"{RATE}|school", f"{RATE}|district"],
    },
    {
        "kind": "figure",
        "text": "This is a great school with 100 students.",
        "cites": [f"{TOTAL}|school"],
    },
    {
        "kind": "figure",
        "text": "Roughly 110 students attend.",
        "cites": [f"{TOTAL}|school"],
    },
)


def service(
    fixture_bundle: Path,
    corpus: Corpus,
    provider: ScriptedProvider | None,
    **kwargs: object,
) -> AskService:
    return AskService(
        bundle_root=fixture_bundle,
        corpus=corpus,
        provider=provider,
        **kwargs,  # type: ignore[arg-type]
    )


def ask(
    svc: AskService, question: str, cds: str = EXAMPLE, locale: str = "en"
) -> object:
    return svc.answer(AskRequest(cds=cds, locale=locale, question=question))


def test_an_answerable_question_is_answered_and_verified(
    fixture_bundle: Path, corpus: Corpus
) -> None:
    provider = ScriptedProvider(
        {
            "structure_question": structure("measures", ["absenteeism.total"]),
            "answer_with_claims": GOOD_CLAIMS,
        }
    )
    svc = service(fixture_bundle, corpus, provider)
    response = svc.answer(
        AskRequest(cds=EXAMPLE, locale="en", question="Is absenteeism a problem here?")
    )
    assert response.status == "answered"
    assert response.kind == "measures"
    assert response.refusal is None
    assert response.intro == text("en", "ask_intro_measures")
    assert [c.text for c in response.claims] == [
        "In 2024-25 the chronic absenteeism rate was 12.5%.",
        "That is higher than the district figure of 11%.",
    ]
    assert response.withheld == 2
    assert response.withheld_reasons == {
        "judgment_language": 1,
        "unverifiable_number": 1,
    }
    assert response.labels["ai"] == text("en", "ask_label_ai")
    assert response.labels["unaffiliated"] == text("en", "footer_unaffiliated")
    assert response.provenance == {
        "provider": "scripted",
        "model": "scripted",
        "prompt_version": PROMPT_VERSION,
        "is_fixture": True,
    }
    assert response.usage["model_calls"] == 2
    assert response.structured is not None
    assert response.structured.measures == ("absenteeism.total",)
    # The model was shown the rules, the catalog, and only the requested record.
    names = [call[0] for call in provider.calls]
    assert names == ["structure_question", "answer_with_claims"]
    assert all(call[1] == SYSTEM_PROMPT for call in provider.calls)
    narration_user = provider.calls[1][2]
    assert f"record {RATE}" in narration_user
    assert f"record {TOTAL}" not in narration_user
    assert "<question>" in narration_user
    # The JSON shape the page reads.
    data = json.loads(json.dumps(response.to_json()))
    assert data["status"] == "answered"
    assert data["claims"][0]["citations"][0]["anchor"] == "absenteeism"
    assert data["structured"]["kind"] == "measures"


def test_a_judgment_question_gets_the_fixed_refusal_and_figures_on_their_own_terms(
    fixture_bundle: Path, corpus: Corpus
) -> None:
    # The model itself says "measures"; the lexical guard overrides it.
    provider = ScriptedProvider(
        {
            "structure_question": structure("measures", ["absenteeism.total"]),
            "answer_with_claims": GOOD_CLAIMS,
        }
    )
    svc = service(fixture_bundle, corpus, provider)
    response = svc.answer(
        AskRequest(cds=EXAMPLE, locale="es", question="¿Es una buena escuela?")
    )
    assert response.status == "answered"
    assert response.kind == "judgment"
    assert response.refusal == text("es", "ask_refusal_judgment")
    assert len(response.claims) == 2
    assert "fixed refusal" in provider.calls[1][2]
    assert response.structured is not None
    assert response.structured.kind == "judgment"


def test_a_judgment_question_the_model_classifies_is_refused_without_figures(
    fixture_bundle: Path, corpus: Corpus
) -> None:
    provider = ScriptedProvider({"structure_question": structure("judgment", [])})
    svc = service(fixture_bundle, corpus, provider)
    response = svc.answer(
        AskRequest(cds=EXAMPLE, locale="en", question="Thoughts on this place?")
    )
    assert response.status == "refused"
    assert response.kind == "judgment"
    assert response.refusal == text("en", "ask_refusal_judgment")
    assert response.claims == ()
    assert response.usage["model_calls"] == 1


def test_outside_and_unclear_questions_get_their_fixed_notes(
    fixture_bundle: Path, corpus: Corpus
) -> None:
    for kind, key in (
        ("outside", "ask_refusal_outside"),
        ("unclear", "ask_refusal_unclear"),
    ):
        provider = ScriptedProvider({"structure_question": structure(kind, [])})
        response = service(fixture_bundle, corpus, provider).answer(
            AskRequest(cds=EXAMPLE, locale="en", question="Is the principal nice?")
        )
        assert response.status == "refused"
        assert response.kind == kind
        assert response.refusal == text("en", key)


def test_an_outside_question_with_nearby_measures_shows_them_under_the_note(
    fixture_bundle: Path, corpus: Corpus
) -> None:
    provider = ScriptedProvider(
        {
            "structure_question": structure("outside", ["enrollment.total"]),
            "answer_with_claims": claims(
                {
                    "kind": "figure",
                    "text": "The school enrolled 100 students in 2025-26.",
                    "cites": [f"{TOTAL}|school"],
                }
            ),
        }
    )
    response = service(fixture_bundle, corpus, provider).answer(
        AskRequest(cds=EXAMPLE, locale="en", question="How big are the classrooms?")
    )
    assert response.status == "answered"
    assert response.kind == "outside"
    assert response.refusal == text("en", "ask_refusal_outside")
    assert len(response.claims) == 1
    assert "fixed note" in provider.calls[1][2]


def test_a_definition_question_is_narrated_from_the_corpus(
    fixture_bundle: Path, corpus: Corpus
) -> None:
    quote = (
        "Students are determined to be chronically absent if they were eligible "
        "to be considered chronically absent at the selected level during the "
        "academic year and they were absent for 10% or more of the days they "
        "were expected to attend."
    )
    provider = ScriptedProvider(
        {
            "structure_question": structure(
                "definition", [], definitions=["absenteeism", "suppression"]
            ),
            "answer_with_claims": claims(
                {
                    "kind": "definition",
                    "text": "A student counts as chronically absent after missing a tenth of expected days.",
                    "cites": ["fsabd#61"],
                    "quote": quote,
                }
            ),
        }
    )
    response = service(fixture_bundle, corpus, provider).answer(
        AskRequest(
            cds=EXAMPLE, locale="en", question="What does chronic absenteeism mean?"
        )
    )
    assert response.status == "answered"
    assert response.kind == "definition"
    assert response.intro == text("en", "ask_intro_definition")
    assert len(response.claims) == 1
    assert response.claims[0].quote == quote
    assert response.claims[0].citations[0].type == "passage"
    narration_user = provider.calls[1][2]
    assert "CDE passages" in narration_user
    assert "fsabd#" in narration_user and "cwa#" in narration_user


def test_when_every_requested_figure_is_absent_the_answer_says_so(
    fixture_bundle: Path, corpus: Corpus
) -> None:
    provider = ScriptedProvider(
        {
            "structure_question": structure("measures", ["enrollment.group.RE_B"]),
            "answer_with_claims": claims(
                {
                    "kind": "figure",
                    "text": "The count of African American students was withheld to protect privacy.",
                    "cites": [f"{WITHHELD}|school"],
                }
            ),
        }
    )
    response = service(fixture_bundle, corpus, provider).answer(
        AskRequest(cds=EXAMPLE, locale="en", question="How many Black students?")
    )
    assert response.status == "answered"
    assert response.refusal == text("en", "ask_refusal_nothing_published")
    assert len(response.claims) == 1


def test_an_answer_with_nothing_verifiable_is_an_honest_empty_answer(
    fixture_bundle: Path, corpus: Corpus
) -> None:
    provider = ScriptedProvider(
        {
            "structure_question": structure("measures", ["enrollment.total"]),
            "answer_with_claims": claims(
                {
                    "kind": "figure",
                    "text": "About 105 students.",
                    "cites": [f"{TOTAL}|school"],
                }
            ),
        }
    )
    response = service(fixture_bundle, corpus, provider).answer(
        AskRequest(cds=EXAMPLE, locale="en", question="How many students?")
    )
    assert response.status == "answered"
    assert response.claims == ()
    assert response.withheld == 1
    assert response.intro == text("en", "ask_empty_answer")


def test_an_unknown_school_is_refused_before_any_model_call(
    fixture_bundle: Path, corpus: Corpus
) -> None:
    provider = ScriptedProvider({})
    response = service(fixture_bundle, corpus, provider).answer(
        AskRequest(cds="99999999999999", locale="en", question="How many students?")
    )
    assert response.status == "refused"
    assert response.kind == "unknown_school"
    assert response.refusal == text("en", "ask_refusal_unknown_school")
    assert response.school is None
    assert provider.calls == []


def test_a_school_no_file_mentions_still_gets_answered_honestly(
    fixture_bundle: Path, corpus: Corpus
) -> None:
    cell = f"{NEVER_MENTIONED}|enrollment.total|2025-26|school"
    provider = ScriptedProvider(
        {
            "structure_question": structure("measures", ["enrollment.total"]),
            "answer_with_claims": claims(
                {
                    "kind": "figure",
                    "text": "No enrollment figure was published for this school for 2025-26.",
                    "cites": [cell],
                }
            ),
        }
    )
    response = service(fixture_bundle, corpus, provider).answer(
        AskRequest(cds=NEVER_MENTIONED, locale="en", question="How many students?")
    )
    assert response.status == "answered"
    assert response.refusal == text("en", "ask_refusal_nothing_published")
    assert len(response.claims) == 1


@pytest.mark.parametrize(
    ("cds", "locale", "question"),
    [
        (EXAMPLE, "fr", "How many students?"),
        (EXAMPLE, "en", "   "),
        (EXAMPLE, "en", "x" * 601),
        ("0110017011234", "en", "How many students?"),
        ("../../etc/passwd", "en", "How many students?"),
    ],
)
def test_malformed_requests_are_invalid_and_cost_nothing(
    fixture_bundle: Path, corpus: Corpus, cds: str, locale: str, question: str
) -> None:
    provider = ScriptedProvider({})
    cap = DailyCap(limit=2)
    response = service(fixture_bundle, corpus, provider, cap=cap).answer(
        AskRequest(cds=cds, locale=locale, question=question)
    )
    assert response.status == "invalid"
    assert response.locale in ("en", "es")
    assert provider.calls == []
    assert cap.remaining() == 2


def test_without_a_provider_the_service_says_so_and_the_page_stands(
    fixture_bundle: Path, corpus: Corpus
) -> None:
    response = service(fixture_bundle, corpus, None).answer(
        AskRequest(cds=EXAMPLE, locale="es", question="¿Cuántos estudiantes hay?")
    )
    assert response.status == "unavailable"
    assert response.refusal == text("es", "ask_refusal_unavailable")
    assert response.school == {"cds": EXAMPLE, "name": "Example Elementary"}
    assert response.provenance["provider"] is None


def test_provider_failures_fail_closed_and_give_the_cap_back(
    fixture_bundle: Path, corpus: Corpus
) -> None:
    def boom(_: str) -> dict[str, object]:
        raise ProviderError("503")

    def limited(_: str) -> dict[str, object]:
        raise ProviderRateLimited("429")

    cap = DailyCap(limit=10)
    svc = service(
        fixture_bundle,
        corpus,
        ScriptedProvider({"structure_question": boom}),
        cap=cap,
    )
    response = svc.answer(AskRequest(cds=EXAMPLE, locale="en", question="How many?"))
    assert response.status == "unavailable"
    assert response.refusal == text("en", "ask_refusal_unavailable")
    assert cap.remaining() == 10

    svc = service(
        fixture_bundle,
        corpus,
        ScriptedProvider(
            {
                "structure_question": structure("measures", ["enrollment.total"]),
                "answer_with_claims": limited,
            }
        ),
        cap=cap,
    )
    response = svc.answer(AskRequest(cds=EXAMPLE, locale="en", question="How many?"))
    assert response.status == "rate_limited"
    assert response.refusal == text("en", "ask_refusal_rate_limited")
    assert response.usage["model_calls"] == 1
    assert cap.remaining() == 9

    # A structuring reply off the schema is the same as no reply.
    svc = service(
        fixture_bundle,
        corpus,
        ScriptedProvider({"structure_question": lambda _: {"kind": "verdict"}}),
        cap=cap,
    )
    response = svc.answer(AskRequest(cds=EXAMPLE, locale="en", question="How many?"))
    assert response.status == "unavailable"
    assert cap.remaining() == 8  # the structuring call was made and is counted

    # A provider with no reply for the tool at all.
    svc = service(fixture_bundle, corpus, ScriptedProvider({}), cap=cap)
    response = svc.answer(AskRequest(cds=EXAMPLE, locale="en", question="How many?"))
    assert response.status == "unavailable"


def test_the_rate_limit_and_the_daily_cap_refuse_with_fixed_strings(
    fixture_bundle: Path, corpus: Corpus
) -> None:
    provider = ScriptedProvider({"structure_question": structure("judgment", [])})
    clock = [0.0]
    limiter = RateLimiter(per_minute=60, burst=2, clock=lambda: clock[0])
    day = [dt.date(2026, 8, 21)]
    cap = DailyCap(limit=3, today=lambda: day[0])
    svc = service(fixture_bundle, corpus, provider, limiter=limiter, cap=cap)
    request = AskRequest(
        cds=EXAMPLE, locale="en", question="Is it good?", client_key="a"
    )
    assert svc.answer(request).status == "refused"  # burst 1, one call used
    assert svc.answer(request).status == "refused"  # burst 2, two calls used
    assert svc.answer(request).status == "rate_limited"
    assert svc.answer(request).refusal == text("en", "ask_refusal_rate_limited")
    other = AskRequest(cds=EXAMPLE, locale="en", question="Is it good?", client_key="b")
    assert svc.answer(other).status == "cap_reached"  # needs 2, only 1 left
    assert svc.answer(other).refusal == text("en", "ask_refusal_cap_reached")
    day[0] = dt.date(2026, 8, 22)
    clock[0] = 120.0
    assert svc.answer(request).status == "refused"
    assert cap.remaining() == 2


def test_every_status_the_service_can_return_is_named() -> None:
    assert set(STATUSES) == {
        "answered",
        "refused",
        "unavailable",
        "rate_limited",
        "cap_reached",
        "invalid",
    }


def test_a_malformed_narration_is_retried_once_and_paid_for(
    fixture_bundle: Path, corpus: Corpus
) -> None:
    attempts = {"n": 0}

    def narrate(_: str) -> dict[str, object]:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return {"claims": "not json ["}
        return {
            "claims": [
                {
                    "kind": "figure",
                    "text": "The school enrolled 100 students in 2025-26.",
                    "cites": [f"{TOTAL}|school"],
                }
            ]
        }

    cap = DailyCap(limit=10)
    svc = service(
        fixture_bundle,
        corpus,
        ScriptedProvider(
            {
                "structure_question": structure("measures", ["enrollment.total"]),
                "answer_with_claims": narrate,
            }
        ),
        cap=cap,
    )
    response = svc.answer(AskRequest(cds=EXAMPLE, locale="en", question="How many?"))
    assert response.status == "answered"
    assert len(response.claims) == 1
    assert response.usage["model_calls"] == 3
    assert cap.remaining() == 7
    # With no budget for a retry, the malformed reply stands as an empty answer.
    attempts["n"] = 0
    cap = DailyCap(limit=2)
    svc = service(
        fixture_bundle,
        corpus,
        ScriptedProvider(
            {
                "structure_question": structure("measures", ["enrollment.total"]),
                "answer_with_claims": narrate,
            }
        ),
        cap=cap,
    )
    response = svc.answer(AskRequest(cds=EXAMPLE, locale="en", question="How many?"))
    assert response.status == "answered"
    assert response.claims == ()
    assert response.withheld_reasons == {"malformed": 1}
    assert response.usage["model_calls"] == 2
