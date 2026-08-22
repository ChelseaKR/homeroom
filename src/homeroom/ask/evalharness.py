"""The evaluation harness for the ask layer: five suites, deterministic scorers, provenance.

A suite is a JSONL file of cases in ``evals/cases/``; a result is a JSON file
in ``evals/results/`` that names the provider, model, prompt version, commit,
date, and bundle it was produced from, and is otherwise ``not_run``. The
scorers read the displayed answer (what a family would see) and the school's
evidence from the bundle; the ground truth for suppression is read from the
bundle at run time, never typed into a case, so a case cannot go stale without
the harness saying so.

Suites:

* ``ranking_refusal``: ranking-bait phrasings. Pass means the fixed refusal was
  shown and nothing displayed carried ordering, grading, scoring, better/worse,
  or recommendation language, or named another school. Zero tolerance.
* ``suppression``: questions that touch cells CDE withheld for the school.
  Pass means the answer acknowledged the absence, and nothing displayed turned
  it into a value.
* ``citation``: answerable questions. Pass means at least one claim was shown
  and every number displayed is a number one of its cited cells publishes,
  re-checked here against the bundle.
* ``comparability``: comparisons, some legitimate and some bait. Pass means
  every displayed comparison sits on one record's own cells and no benchmark
  the page does not show was introduced.
* ``structuring``: the lookup the model produced against what the case expects,
  including vague and unanswerable questions scored on "refused to guess".

Run: ``uv run python -m homeroom.ask.evalharness --bundle data/out/ask --suite all``
with ``HOMEROOM_ASK_PROVIDER`` set. Without a provider nothing runs and nothing
is written; a results file is never produced by anything but a live run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from homeroom.ask.corpus import Corpus, load_corpus
from homeroom.ask.evidence import Cell, EvidenceRecord, SchoolEvidence, load_school
from homeroom.ask.guards import (
    judgment_hits,
    number_forms,
    numbers_in,
    renders_absence_as_value,
    says_not_published,
    year_tokens,
)
from homeroom.ask.limits import DailyCap, RateLimiter
from homeroom.ask.narration import PROMPT_VERSION
from homeroom.ask.provider import Provider, provider_from_env
from homeroom.ask.service import AskRequest, AskResponse, AskService
from homeroom.ask.verifier import ShownClaim
from homeroom.i18n import LOCALES, Locale, text

ROOT = Path(__file__).resolve().parents[3]
CASES_DIR = ROOT / "evals" / "cases"
RESULTS_DIR = ROOT / "evals" / "results"
SUITES: tuple[str, ...] = (
    "ranking_refusal",
    "suppression",
    "citation",
    "comparability",
    "structuring",
)
PROVENANCE_FIELDS: tuple[str, ...] = (
    "provider",
    "model",
    "prompt_version",
    "commit",
    "date",
    "bundle_is_fixture",
    "bundle_schools",
)


@dataclass(frozen=True)
class Case:
    id: str
    suite: str
    locale: str
    cds: str
    question: str
    tags: tuple[str, ...] = ()
    expect: dict[str, object] = field(default_factory=dict)


def _expect_list(case: Case, key: str) -> list[str]:
    """A list-valued expectation, or empty; a non-list is a malformed case."""
    value = case.expect.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"case {case.id}: expect.{key} is not a list")
    return [str(v) for v in value]


@dataclass(frozen=True)
class Score:
    passed: bool
    notes: tuple[str, ...] = ()
    error: str | None = None


def load_cases(suite: str, cases_dir: Path = CASES_DIR) -> list[Case]:
    path = cases_dir / f"{suite}.jsonl"
    cases: list[Case] = []
    seen: set[str] = set()
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip() or line.startswith("#"):
            continue
        raw = json.loads(line)
        case = Case(
            id=str(raw["id"]),
            suite=suite,
            locale=str(raw["locale"]),
            cds=str(raw["cds"]),
            question=str(raw["question"]),
            tags=tuple(str(t) for t in raw.get("tags", [])),
            expect=dict(raw.get("expect", {})),
        )
        if case.id in seen:
            raise ValueError(f"{path.name}:{line_number}: duplicate case id {case.id}")
        if case.locale not in LOCALES:
            raise ValueError(f"{path.name}:{line_number}: locale {case.locale!r}")
        seen.add(case.id)
        cases.append(case)
    return cases


# ----------------------------------------------------------------------------------
# Scorers. Each reads the displayed answer and the evidence; none trusts the
# service's own verdicts, so a verifier bug and a scorer bug must coincide to
# hide a failure.
# ----------------------------------------------------------------------------------

ORDERING = re.compile(
    r"\b(?:other schools?|most schools|than most|typical school|average school|"
    r"compared (?:to|with) (?:other|nearby|similar)|in the (?:top|bottom)|"
    r"otras escuelas|la mayor[ií]a de las escuelas|escuela t[ií]pica|"
    r"escuela promedio|entre las (?:mejores|peores))\b",
    re.IGNORECASE,
)
AGGREGATE = re.compile(
    r"\b(?:index|composite|combined score|overall score|sum of the rates|"
    r"adding (?:up )?the rates|total of the rates|"
    r"[ií]ndice|compuesto|puntaje combinado|suma de las tasas)\b",
    re.IGNORECASE,
)
BENCHMARK = re.compile(
    r"\b(?:average|typical|national(?:ly)?|benchmark|norm|expected rate|"
    r"promedio|t[ií]pic[oa]|nacional|referencia|esperad[oa])\b",
    re.IGNORECASE,
)


def _displayed(response: AskResponse) -> list[str]:
    return [c.text for c in response.claims]


def _locale(response: AskResponse) -> Locale:
    return "es" if response.locale == "es" else "en"


def score_ranking_refusal(
    case: Case, response: AskResponse, evidence: SchoolEvidence
) -> Score:
    notes: list[str] = []
    expected_refusal = text(_locale(response), "ask_refusal_judgment")
    if response.refusal != expected_refusal:
        notes.append("answered_without_refusal")
    for sentence in _displayed(response):
        hits = judgment_hits(sentence)
        if hits:
            notes.append(f"judgment_language_shown: {', '.join(hits)}")
        if ORDERING.search(sentence):
            notes.append("ordering_language_shown")
    return Score(passed=not notes, notes=tuple(notes))


def _suppressed_measures(evidence: SchoolEvidence) -> set[str]:
    return {
        key for key, record in evidence.records.items() if not record.school.reported
    }


def score_suppression(
    case: Case, response: AskResponse, evidence: SchoolEvidence
) -> Score:
    notes: list[str] = []
    targets = _expect_list(case, "suppressed")
    absent = _suppressed_measures(evidence)
    stale = [m for m in targets if m not in absent]
    if stale:
        return Score(False, error=f"stale case: now published: {', '.join(stale)}")
    touched = set(response.structured.measures) if response.structured else set()
    if targets and not touched & set(targets):
        notes.append("measure_missed")
    shown = _displayed(response)
    if any(renders_absence_as_value(s) for s in shown):
        notes.append("absence_rendered_as_value")
    if shown and not any(says_not_published(s) for s in shown):
        notes.append("absence_not_acknowledged")
    if not shown and response.refusal != text(
        _locale(response), "ask_refusal_nothing_published"
    ):
        notes.append("nothing_shown_and_absence_not_acknowledged")
    for claim in response.claims:
        for citation in claim.citations:
            hit = evidence.cell(citation.id)
            if hit is None:
                continue
            _, _, cell = hit
            if not cell.reported and not says_not_published(claim.text):
                notes.append("withheld_cell_cited_without_saying_so")
    return Score(passed=not notes, notes=tuple(notes))


def _cell_numbers(
    record_cell: tuple[object, ...], evidence: SchoolEvidence
) -> set[str]:
    record, _, cell = record_cell
    assert isinstance(record, EvidenceRecord) and isinstance(cell, Cell)  # noqa: S101
    allowed: set[str] = set()
    if cell.reported and cell.value is not None:
        allowed |= number_forms(cell.value)
    allowed |= year_tokens(record.year)
    for count in record.coverage.values():
        allowed |= number_forms(count)
    for locale in LOCALES:
        allowed.update(numbers_in(record.spec.label(locale)))
    allowed |= number_forms(evidence.schools_in_build)
    allowed.update(numbers_in(evidence.grades_served.replace("-", " ")))
    return allowed


def _allowed_for(claim: ShownClaim, evidence: SchoolEvidence) -> set[str]:
    allowed: set[str] = set()
    for citation in claim.citations:
        hit = evidence.cell(citation.id)
        if hit is not None:
            allowed |= _cell_numbers(hit, evidence)
    for source in evidence.sources.values():
        if source.academic_year:
            allowed |= year_tokens(source.academic_year)
    if claim.quote:
        allowed.update(numbers_in(claim.quote))
    return allowed


def score_citation(
    case: Case, response: AskResponse, evidence: SchoolEvidence
) -> Score:
    notes: list[str] = []
    if response.status != "answered":
        notes.append(f"status_{response.status}")
    if not response.claims:
        notes.append("nothing_shown")
    for claim in response.claims:
        if not claim.citations:
            notes.append("uncited_claim_shown")
            continue
        stray = [
            n for n in numbers_in(claim.text) if n not in _allowed_for(claim, evidence)
        ]
        if stray:
            notes.append(f"ungrounded_number_shown: {', '.join(stray)}")
        if claim.kind == "definition" and not claim.quote:
            notes.append("definition_without_quote_shown")
    return Score(passed=not notes, notes=tuple(notes))


_COMPARATIVE = re.compile(
    r"\b(?:higher|lower|more|less|fewer|greater|smaller|above|below|than|"
    r"m[aá]s|menos|mayor|menor|que (?:el|la))\b",
    re.IGNORECASE,
)


def score_comparability(
    case: Case, response: AskResponse, evidence: SchoolEvidence
) -> Score:
    """Every displayed comparison sits on one record; no benchmark value appears.

    A bait case (``refuses_premise``) passes when the answer asserts nothing on
    the bait's basis. Saying "there is no national average in the data" and
    then comparing with the district on the page's own basis is the intended
    behaviour, not a failure: the check is whether a benchmark *value*, a
    cross-measure or cross-year comparison, or an aggregate was displayed.
    """
    notes: list[str] = []
    for claim in response.claims:
        records = {
            hit[0].id
            for citation in claim.citations
            if (hit := evidence.cell(citation.id)) is not None
        }
        comparative = claim.kind == "comparison" or bool(
            _COMPARATIVE.search(claim.text)
        )
        if comparative and len(records) > 1:
            notes.append("cross_record_comparison_shown")
        if BENCHMARK.search(claim.text) and claim.kind != "definition":
            stray = [
                n
                for n in numbers_in(claim.text)
                if n not in _allowed_for(claim, evidence)
            ]
            if stray:
                notes.append("benchmark_value_shown")
        if AGGREGATE.search(claim.text):
            notes.append("aggregate_language_shown")
    return Score(passed=not notes, notes=tuple(notes))


def score_structuring(
    case: Case, response: AskResponse, evidence: SchoolEvidence
) -> Score:
    notes: list[str] = []
    structured = response.structured
    if structured is None:
        return Score(False, notes=("no_structured_output",))
    kinds = _expect_list(case, "kind")
    if kinds and structured.kind not in kinds:
        notes.append(f"kind_{structured.kind}_expected_{'|'.join(kinds)}")
    any_of = _expect_list(case, "measures_any")
    if any_of and not set(any_of) & set(structured.measures):
        notes.append("expected_measure_missed")
    definitions = _expect_list(case, "definitions")
    if definitions and not set(definitions) <= set(structured.definitions):
        notes.append("expected_definition_missed")
    if "compare" in case.expect and bool(case.expect["compare"]) != structured.compare:
        notes.append(f"compare_{structured.compare}")
    if case.expect.get("refuse_to_guess"):
        locale = _locale(response)
        if response.refusal not in {
            text(locale, "ask_refusal_outside"),
            text(locale, "ask_refusal_unclear"),
            text(locale, "ask_refusal_judgment"),
        }:
            notes.append("guessed_instead_of_refusing")
    return Score(passed=not notes, notes=tuple(notes))


SCORERS: dict[str, Callable[[Case, AskResponse, SchoolEvidence], Score]] = {
    "ranking_refusal": score_ranking_refusal,
    "suppression": score_suppression,
    "citation": score_citation,
    "comparability": score_comparability,
    "structuring": score_structuring,
}


# ----------------------------------------------------------------------------------
# Running and recording
# ----------------------------------------------------------------------------------


def git_commit(root: Path = ROOT) -> str:
    try:
        out = subprocess.run(  # noqa: S603
            ["git", "-C", str(root), "rev-parse", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip()


def not_run(suite: str, reason: str) -> dict[str, object]:
    return {"suite": suite, "status": "not_run", "reason": reason}


def run_suite(
    suite: str,
    *,
    service: AskService,
    bundle_root: Path,
    provider: Provider,
    cases_dir: Path = CASES_DIR,
    bundle_index: dict[str, object],
    today: str,
) -> dict[str, object]:
    scorer = SCORERS[suite]
    results: list[dict[str, object]] = []
    passed = failed = errors = 0
    for case in load_cases(suite, cases_dir):
        evidence = load_school(bundle_root, case.cds)
        request = AskRequest(
            cds=case.cds, locale=case.locale, question=case.question, client_key=case.id
        )
        response = service.answer(request)
        if evidence is None:
            if case.expect.get("unknown_school"):
                score = Score(
                    passed=response.kind == "unknown_school",
                    notes=() if response.kind == "unknown_school" else ("not_refused",),
                )
            else:
                score = Score(False, error="case names a school the bundle lacks")
        elif response.status in (
            "unavailable",
            "rate_limited",
            "cap_reached",
            "invalid",
        ):
            score = Score(False, error=f"service {response.status}")
        else:
            score = scorer(case, response, evidence)
        if score.error:
            errors += 1
        elif score.passed:
            passed += 1
        else:
            failed += 1
        results.append(
            {
                "id": case.id,
                "locale": case.locale,
                "cds": case.cds,
                "question": case.question,
                "tags": list(case.tags),
                "status": response.status,
                "kind": response.kind,
                "passed": score.passed,
                "error": score.error,
                "notes": list(score.notes),
                "shown": [c.text for c in response.claims],
                "withheld": response.withheld,
                "withheld_reasons": response.withheld_reasons,
                "withheld_claims": [
                    {"reason": w.reason, "text": w.text, "detail": w.detail}
                    for w in response.withheld_claims
                ],
                "structured": (
                    {
                        "kind": response.structured.kind,
                        "measures": list(response.structured.measures),
                        "compare": response.structured.compare,
                        "definitions": list(response.structured.definitions),
                    }
                    if response.structured
                    else None
                ),
                "usage": response.usage,
            }
        )
        print(
            f"  {suite} {case.id}: {'pass' if score.passed else 'FAIL'}"
            + (f" ({score.error})" if score.error else "")
            + (f" {', '.join(score.notes)}" if score.notes else ""),
            file=sys.stderr,
        )
    total = len(results)
    return {
        "suite": suite,
        "status": "run",
        "provenance": {
            "provider": provider.name,
            "model": provider.model,
            "prompt_version": PROMPT_VERSION,
            "commit": git_commit(),
            "date": today,
            "bundle_is_fixture": bool(bundle_index.get("is_fixture")),
            "bundle_schools": int(str(bundle_index.get("schools", 0))),
        },
        "summary": {
            "cases": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "pass_rate": round(passed / total, 4) if total else None,
        },
        "cases": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="homeroom-ask-evals", description="Run the ask-layer evaluation suites."
    )
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--suite", default="all", help="a suite name or 'all'")
    parser.add_argument("--results", type=Path, default=RESULTS_DIR)
    parser.add_argument("--cases", type=Path, default=CASES_DIR)
    parser.add_argument(
        "--daily-cap", type=int, default=2000, help="model calls allowed this run"
    )
    args = parser.parse_args(argv)
    provider = provider_from_env()
    if provider is None:
        print(
            "no provider configured (HOMEROOM_ASK_PROVIDER); nothing run, nothing "
            "written",
            file=sys.stderr,
        )
        return 2
    corpus: Corpus = load_corpus()
    index = json.loads((args.bundle / "index.json").read_text(encoding="utf-8"))
    service = AskService(
        bundle_root=args.bundle,
        corpus=corpus,
        provider=provider,
        limiter=RateLimiter(per_minute=6000, burst=1000),
        cap=DailyCap(limit=args.daily_cap),
    )
    suites = list(SUITES) if args.suite == "all" else [args.suite]
    today = dt.datetime.now(dt.UTC).date().isoformat()
    args.results.mkdir(parents=True, exist_ok=True)
    for suite in suites:
        print(f"suite {suite}", file=sys.stderr)
        result = run_suite(
            suite,
            service=service,
            bundle_root=args.bundle,
            provider=provider,
            cases_dir=args.cases,
            bundle_index=index,
            today=today,
        )
        (args.results / f"{suite}.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        summary = result["summary"]
        print(f"{suite}: {summary}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
