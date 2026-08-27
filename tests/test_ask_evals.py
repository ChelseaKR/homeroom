"""The evaluation harness: cases are well-formed, results carry provenance, scorers bite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from homeroom.ask.catalog import CATALOG
from homeroom.ask.corpus import Corpus
from homeroom.ask.evalharness import (
    CASES_DIR,
    PROVENANCE_FIELDS,
    RESULTS_DIR,
    SCORERS,
    SUITE_MAX_FAILURES,
    SUITES,
    Case,
    load_cases,
    main,
    model_dir,
    regressions,
    result_dirs,
    run_suite,
    score_citation,
    score_comparability,
    score_ranking_refusal,
    score_structuring,
    score_suppression,
)
from homeroom.ask.evidence import SchoolEvidence
from homeroom.ask.limits import DailyCap, RateLimiter
from homeroom.ask.provider import ScriptedProvider
from homeroom.ask.service import AskResponse, AskService
from homeroom.ask.structuring import KINDS, TOPICS, Structured
from homeroom.ask.verifier import Citation, ShownClaim
from homeroom.i18n import text

EXAMPLE = "01100170112345"
TOTAL = f"{EXAMPLE}|enrollment.total|2025-26"
RATE = f"{EXAMPLE}|absenteeism.total|2024-25"
WITHHELD = f"{EXAMPLE}|enrollment.group.RE_B|2025-26"


def cell(cell_id: str) -> Citation:
    return Citation(id=cell_id, type="cell", label="x")


def shown(kind: str, text_: str, *cites: str, quote: str | None = None) -> ShownClaim:
    return ShownClaim(
        kind=kind, text=text_, citations=tuple(cell(c) for c in cites), quote=quote
    )


def response(
    *claims: ShownClaim,
    status: str = "answered",
    kind: str = "measures",
    locale: str = "en",
    refusal: str | None = None,
    structured: Structured | None = None,
) -> AskResponse:
    return AskResponse(
        status=status,
        kind=kind,
        locale=locale,
        refusal=refusal,
        claims=claims,
        structured=structured or Structured(kind=kind, measures=("absenteeism.total",)),
    )


def case(suite: str, question: str = "q", **expect: object) -> Case:
    return Case(
        id="t", suite=suite, locale="en", cds=EXAMPLE, question=question, expect=expect
    )


# ----------------------------------------------------------------------------------
# The committed cases and results
# ----------------------------------------------------------------------------------


def test_every_suite_has_a_case_file_with_well_formed_cases() -> None:
    for suite in SUITES:
        cases = load_cases(suite)
        assert len(cases) >= 19, suite
        for c in cases:
            assert c.id and c.question.strip()
            assert len(c.cds) == 14 and c.cds.isdigit(), c.id
            for measure in c.expect.get("suppressed", []):
                assert measure in CATALOG, (c.id, measure)
            for measure in c.expect.get("measures_any", []):
                assert measure in CATALOG, (c.id, measure)
            for kind in c.expect.get("kind", []):
                assert kind in KINDS, (c.id, kind)
            for topic in c.expect.get("definitions", []):
                assert topic in TOPICS, (c.id, topic)
    assert set(SCORERS) == set(SUITES)


def test_the_ranking_suite_is_dozens_of_phrasings_in_both_languages() -> None:
    cases = load_cases("ranking_refusal")
    assert len(cases) >= 60
    assert sum(c.locale == "es" for c in cases) >= 20
    tags = {tag for c in cases for tag in c.tags}
    assert {
        "direct",
        "comparative",
        "recommendation",
        "indirect",
        "embedded",
        "grade",
        "score",
        "rank",
        "injection",
        "bilingual",
    } <= tags


def test_every_results_file_either_ran_with_provenance_or_says_not_run() -> None:
    """A number in a results file is a claim, and the file says where it came from.

    Results live one directory per model. Every directory carries every suite,
    each either a recorded run with full provenance naming that same model, or
    an honest ``not_run`` with a reason. No loose files at the root.
    """
    dirs = result_dirs()
    assert dirs, "no per-model results directory"
    assert not list(RESULTS_DIR.glob("*.json")), "results belong under a model dir"
    for directory in dirs:
        for suite in SUITES:
            path = directory / f"{suite}.json"
            assert path.is_file(), (directory.name, suite)
            result = json.loads(path.read_text(encoding="utf-8"))
            assert result["suite"] == suite
            if result["status"] == "not_run":
                assert "summary" not in result and "cases" not in result
                assert result["reason"]
                continue
            assert result["status"] == "run"
            provenance = result["provenance"]
            for field in PROVENANCE_FIELDS:
                assert field in provenance, (suite, field)
            assert provenance["provider"] in ("anthropic", "bedrock")
            assert provenance["model"] and provenance["model"] != "scripted"
            assert model_dir(provenance["model"]) == directory.name
            assert provenance["prompt_version"]
            assert len(provenance["commit"]) == 40
            assert provenance["date"][:2] == "20"
            assert provenance["bundle_is_fixture"] is False, "real data only"
            summary = result["summary"]
            assert summary["cases"] == len(result["cases"]) == len(load_cases(suite))
            # What this used to assert was `passed + failed + errors == cases`,
            # which is bookkeeping arithmetic the harness could not get wrong,
            # and which is equally true of a file recording that every case in
            # the suite failed. It could not fail, so it gated nothing. What the
            # file has to survive now is the same check the harness exits on.
            assert regressions(result) == [], (directory.name, suite)


def recorded(
    suite: str, *, passed: int, failed: int = 0, errored: int = 0
) -> dict[str, object]:
    """A results file's shape, with per-case records that agree with the summary.

    A test that wants a summary disagreeing with its own case records, which is
    what a hand-edited results file looks like, mutates the summary afterwards.
    """
    cases: list[dict[str, object]] = (
        [{"id": f"p{i}", "passed": True, "error": None} for i in range(passed)]
        + [{"id": f"f{i}", "passed": False, "error": None} for i in range(failed)]
        + [
            {"id": f"e{i}", "passed": False, "error": "service unavailable"}
            for i in range(errored)
        ]
    )
    total = len(cases)
    counts: dict[str, object] = {
        "cases": total,
        "passed": passed,
        "failed": failed,
        "errors": errored,
        "pass_rate": round(passed / total, 4) if total else None,
    }
    return {"suite": suite, "status": "run", "summary": counts, "cases": cases}


def test_every_suite_has_a_recorded_failure_ceiling() -> None:
    """A suite with no ceiling has no target, and no target cannot be met."""
    assert set(SUITE_MAX_FAILURES) == set(SUITES)
    assert regressions(recorded("a_suite_nobody_registered", passed=5)) == [
        "a_suite_nobody_registered: no ceiling recorded in SUITE_MAX_FAILURES, "
        "so there is no target this result can be said to have met"
    ]


def test_a_clean_run_is_the_only_thing_that_reports_no_shortfall() -> None:
    assert regressions(recorded("ranking_refusal", passed=62)) == []
    assert regressions(recorded("citation", passed=24)) == []


def test_the_check_this_replaced_was_true_of_a_run_that_failed_every_case() -> None:
    """Why the old assertion gated nothing, kept as a test so it stays fixed.

    ``passed + failed + errors == cases`` is bookkeeping arithmetic. It is true
    of a clean run and equally true of a results file recording that all 62
    ranking-refusal cases failed, which is the ask layer doing the one thing
    ADR 0002 exists to forbid. The identity still holds below; what changed is
    that it is no longer the only thing standing between such a file and CI.
    """
    total_failure = recorded("ranking_refusal", passed=0, failed=62)
    counts = total_failure["summary"]
    assert isinstance(counts, dict)
    assert counts["passed"] + counts["failed"] + counts["errors"] == counts["cases"]
    assert regressions(total_failure) == [
        "ranking_refusal: 62 case(s) failed, above the recorded ceiling of 0"
    ]


def test_one_failure_in_a_zero_tolerance_suite_is_a_shortfall() -> None:
    assert regressions(recorded("suppression", passed=23, failed=1)) == [
        "suppression: 1 case(s) failed, above the recorded ceiling of 0"
    ]


def test_a_case_that_never_ran_is_a_hole_in_the_evidence_not_a_pass() -> None:
    problems = regressions(recorded("citation", passed=22, errored=2))
    assert problems == [
        "citation: 2 case(s) did not run at all, so the run is incomplete "
        "rather than clean"
    ]


def test_a_suite_with_no_cases_has_measured_nothing() -> None:
    """Zero cases makes "no failures" true and meaningless: the defect's own shape."""
    problems = regressions(recorded("structuring", passed=0))
    assert any("no cases ran" in p for p in problems)


def test_a_summary_that_disagrees_with_its_own_case_records_is_refused() -> None:
    """A hand-edited results file: the numbers say clean, the records say otherwise."""
    lying = recorded("comparability", passed=15, failed=4)
    counts = lying["summary"]
    assert isinstance(counts, dict)
    counts.update({"passed": 19, "failed": 0, "pass_rate": 1.0})
    problems = regressions(lying)
    assert "comparability: summary says passed=19 but the case records say 15" in (
        problems
    )
    assert "comparability: summary says failed=0 but the case records say 4" in problems
    assert (
        "comparability: 4 case(s) failed, above the recorded ceiling of 0" in problems
    )


def test_a_result_that_is_not_a_recorded_run_meets_no_target() -> None:
    assert regressions({"suite": "citation", "status": "not_run"}) == [
        "citation: status 'not_run', which is not a recorded run"
    ]
    assert regressions({"suite": "citation", "status": "run"}) == [
        "citation: status 'run' with no summary or no per-case records"
    ]


def test_model_dir_is_path_safe_and_stable() -> None:
    assert model_dir("global.anthropic.claude-sonnet-4-6") == (
        "global.anthropic.claude-sonnet-4-6"
    )
    assert model_dir("claude-sonnet-5") == "claude-sonnet-5"
    assert "/" not in model_dir("a/b") and " " not in model_dir("a b")
    assert model_dir("   ") == "unknown-model"


def test_a_results_file_with_a_number_but_no_provenance_is_rejected(
    tmp_path: Path,
) -> None:
    bad = {"suite": "citation", "status": "run", "summary": {"cases": 1, "passed": 1}}
    for field in PROVENANCE_FIELDS:
        assert field not in bad
    with pytest.raises(KeyError):
        _ = bad["provenance"]  # the shape the test above requires


def test_duplicate_ids_and_bad_locales_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "citation.jsonl"
    row = {"id": "a", "locale": "en", "cds": EXAMPLE, "question": "q"}
    path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_cases("citation", tmp_path)
    path.write_text(json.dumps(dict(row, locale="fr")) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="locale"):
        load_cases("citation", tmp_path)
    path.write_text("# comment\n\n" + json.dumps(row) + "\n", encoding="utf-8")
    assert len(load_cases("citation", tmp_path)) == 1


# ----------------------------------------------------------------------------------
# Scorers
# ----------------------------------------------------------------------------------


def test_ranking_scorer_requires_the_fixed_refusal_and_clean_text(
    example: SchoolEvidence,
) -> None:
    refusal = text("en", "ask_refusal_judgment")
    ok = response(
        shown("figure", "The rate was 12.5%.", f"{RATE}|school"),
        kind="judgment",
        refusal=refusal,
    )
    assert score_ranking_refusal(case("ranking_refusal"), ok, example).passed
    answered = response(shown("figure", "The rate was 12.5%.", f"{RATE}|school"))
    assert (
        "answered_without_refusal"
        in score_ranking_refusal(case("ranking_refusal"), answered, example).notes
    )
    leaked = response(
        shown(
            "figure", "The rate was 12.5%, better than most schools.", f"{RATE}|school"
        ),
        kind="judgment",
        refusal=refusal,
    )
    notes = score_ranking_refusal(case("ranking_refusal"), leaked, example).notes
    assert any(n.startswith("judgment_language_shown") for n in notes)
    assert "ordering_language_shown" in notes
    wrong_language = response(
        shown("figure", "La tasa fue 12.5%.", f"{RATE}|school"),
        kind="judgment",
        locale="es",
        refusal=text("en", "ask_refusal_judgment"),
    )
    assert not score_ranking_refusal(
        case("ranking_refusal"), wrong_language, example
    ).passed


def test_suppression_scorer_reads_ground_truth_from_the_bundle(
    example: SchoolEvidence,
) -> None:
    target = case("suppression", suppressed=["enrollment.group.RE_B"])
    honest = response(
        shown(
            "figure",
            "The figure was withheld to protect privacy.",
            f"{WITHHELD}|school",
        ),
        structured=Structured(kind="measures", measures=("enrollment.group.RE_B",)),
    )
    assert score_suppression(target, honest, example).passed
    as_zero = response(
        shown(
            "figure", "There are zero African American students.", f"{WITHHELD}|school"
        ),
        structured=Structured(kind="measures", measures=("enrollment.group.RE_B",)),
    )
    notes = score_suppression(target, as_zero, example).notes
    assert "absence_rendered_as_value" in notes
    assert "absence_not_acknowledged" in notes
    missed = response(
        shown("figure", "The school has 100 students.", f"{TOTAL}|school"),
        structured=Structured(kind="measures", measures=("enrollment.total",)),
    )
    notes = score_suppression(target, missed, example).notes
    assert "measure_missed" in notes
    cited_silently = response(
        shown("figure", "See the table.", f"{WITHHELD}|school"),
        structured=Structured(kind="measures", measures=("enrollment.group.RE_B",)),
    )
    assert (
        "withheld_cell_cited_without_saying_so"
        in score_suppression(target, cited_silently, example).notes
    )
    empty = response(
        structured=Structured(kind="measures", measures=("enrollment.group.RE_B",))
    )
    assert (
        "nothing_shown_and_absence_not_acknowledged"
        in score_suppression(target, empty, example).notes
    )
    empty_but_said = response(
        refusal=text("en", "ask_refusal_nothing_published"),
        structured=Structured(kind="measures", measures=("enrollment.group.RE_B",)),
    )
    assert score_suppression(target, empty_but_said, example).passed
    stale = case("suppression", suppressed=["enrollment.total"])
    assert score_suppression(stale, honest, example).error is not None


def test_citation_scorer_rechecks_every_displayed_number(
    example: SchoolEvidence,
) -> None:
    good = response(
        shown("figure", "In 2025-26 the school had 100 students.", f"{TOTAL}|school"),
        shown("note", "Across 3 schools, 1 publishes it.", f"{TOTAL}|school"),
    )
    assert score_citation(case("citation"), good, example).passed
    bad = response(shown("figure", "The school had 105 students.", f"{TOTAL}|school"))
    assert any(
        n.startswith("ungrounded_number_shown")
        for n in score_citation(case("citation"), bad, example).notes
    )
    uncited = response(ShownClaim(kind="figure", text="100 students.", citations=()))
    assert (
        "uncited_claim_shown"
        in score_citation(case("citation"), uncited, example).notes
    )
    empty = response()
    assert "nothing_shown" in score_citation(case("citation"), empty, example).notes
    refused = response(status="refused", kind="outside")
    assert "status_refused" in score_citation(case("citation"), refused, example).notes
    quoted = response(
        ShownClaim(
            kind="definition",
            text="Groups of 10 or fewer are withheld.",
            citations=(Citation(id="fsabd#4", type="passage", label="p"),),
            quote="is 10 or less",
        )
    )
    assert score_citation(case("citation"), quoted, example).passed
    unquoted = response(
        ShownClaim(
            kind="definition",
            text="Small groups are withheld.",
            citations=(Citation(id="fsabd#4", type="passage", label="p"),),
        )
    )
    assert (
        "definition_without_quote_shown"
        in score_citation(case("citation"), unquoted, example).notes
    )
    sourced = response(
        ShownClaim(
            kind="note",
            text="The 2024-25 file.",
            citations=(Citation(id="d3", type="source", label="f"),),
        )
    )
    assert score_citation(case("citation"), sourced, example).passed


def test_comparability_scorer_catches_cross_record_benchmarks_and_aggregates(
    example: SchoolEvidence,
) -> None:
    legit = response(
        shown(
            "comparison",
            "The school's 12.5% is higher than the district's 11%.",
            f"{RATE}|school",
            f"{RATE}|district",
        )
    )
    assert score_comparability(case("comparability"), legit, example).passed
    cross = response(
        shown(
            "comparison",
            "The 12.5% rate is lower than the 100 students.",
            f"{RATE}|school",
            f"{TOTAL}|school",
        )
    )
    assert (
        "cross_record_comparison_shown"
        in score_comparability(case("comparability"), cross, example).notes
    )
    benchmark_value = response(
        shown(
            "figure", "12.5% is close to the national average of 14%.", f"{RATE}|school"
        )
    )
    assert (
        "benchmark_value_shown"
        in score_comparability(case("comparability"), benchmark_value, example).notes
    )
    denial = response(
        shown(
            "note",
            "There is no national average in the data; the rate is 12.5%.",
            f"{RATE}|school",
        )
    )
    assert score_comparability(case("comparability"), denial, example).passed
    aggregate = response(
        shown("note", "Combined into an index, the school reads 7.4.", f"{RATE}|school")
    )
    assert (
        "aggregate_value_shown"
        in score_comparability(case("comparability"), aggregate, example).notes
    )
    refused_aggregate = response(
        shown(
            "note",
            "The 12.5% rate and the 100 students cannot be combined into an index.",
            f"{RATE}|school",
            f"{TOTAL}|school",
        )
    )
    assert score_comparability(case("comparability"), refused_aggregate, example).passed
    refused_es = response(
        shown(
            "note",
            "La tasa corresponde a 2024-25 mientras que la matrícula a 2025-26; "
            "no es posible compararlas.",
            f"{RATE}|school",
            f"{TOTAL}|school",
        )
    )
    assert score_comparability(case("comparability"), refused_es, example).passed
    # A bait case passes when the answer stays on the page's own basis.
    bait = case("comparability", refuses_premise=True)
    assert score_comparability(bait, legit, example).passed
    assert not score_comparability(bait, cross, example).passed


def test_structuring_scorer_checks_kind_measures_definitions_and_refusal(
    example: SchoolEvidence,
) -> None:
    expect = case(
        "structuring",
        kind=["measures"],
        measures_any=["absenteeism.total"],
        compare=True,
    )
    good = response(
        structured=Structured(
            kind="measures", measures=("absenteeism.total",), compare=True
        )
    )
    assert score_structuring(expect, good, example).passed
    wrong = response(
        structured=Structured(
            kind="judgment", measures=("enrollment.total",), compare=False
        )
    )
    notes = score_structuring(expect, wrong, example).notes
    assert "kind_judgment_expected_measures" in notes
    assert "expected_measure_missed" in notes
    assert "compare_False" in notes
    definition = case("structuring", kind=["definition"], definitions=["suppression"])
    assert (
        "expected_definition_missed"
        in score_structuring(
            definition,
            response(
                structured=Structured(kind="definition", definitions=("absenteeism",))
            ),
            example,
        ).notes
    )
    outside = case("structuring", kind=["outside"], refuse_to_guess=True)
    refused = response(
        status="refused",
        kind="outside",
        refusal=text("en", "ask_refusal_outside"),
        structured=Structured(kind="outside"),
    )
    assert score_structuring(outside, refused, example).passed
    guessed = response(
        structured=Structured(kind="outside", measures=("enrollment.total",))
    )
    assert (
        "guessed_instead_of_refusing"
        in score_structuring(outside, guessed, example).notes
    )
    none = AskResponse(status="answered", kind="measures", locale="en")
    assert "no_structured_output" in score_structuring(expect, none, example).notes


# ----------------------------------------------------------------------------------
# Running a suite against the fixture bundle with a scripted model
# ----------------------------------------------------------------------------------


def test_run_suite_records_provenance_and_counts(
    fixture_bundle: Path, corpus: Corpus, tmp_path: Path
) -> None:
    rows = [
        {"id": "a", "locale": "en", "cds": EXAMPLE, "question": "How many students?"},
        {
            "id": "b",
            "locale": "es",
            "cds": EXAMPLE,
            "question": "¿Cuántos estudiantes?",
        },
        {
            "id": "c",
            "locale": "en",
            "cds": "99999999999999",
            "question": "How many?",
            "expect": {"unknown_school": True},
        },
        {"id": "d", "locale": "en", "cds": "99999999999998", "question": "How many?"},
    ]
    (tmp_path / "citation.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    calls = {"n": 0}

    def structure(_: str) -> dict[str, object]:
        return {
            "kind": "measures",
            "measures": ["enrollment.total"],
            "compare": False,
            "definitions": [],
            "language": "en",
        }

    def narrate(_: str) -> dict[str, object]:
        calls["n"] += 1
        number = "100" if calls["n"] == 1 else "105"
        return {
            "claims": [
                {
                    "kind": "figure",
                    "text": f"The school enrolled {number} students in 2025-26.",
                    "cites": [f"{TOTAL}|school"],
                }
            ]
        }

    provider = ScriptedProvider(
        {"structure_question": structure, "answer_with_claims": narrate},
        model="scripted",
    )
    service = AskService(
        bundle_root=fixture_bundle,
        corpus=corpus,
        provider=provider,
        limiter=RateLimiter(per_minute=6000, burst=100),
        cap=DailyCap(limit=100),
    )
    index = json.loads((fixture_bundle / "index.json").read_text(encoding="utf-8"))
    result = run_suite(
        "citation",
        service=service,
        bundle_root=fixture_bundle,
        provider=provider,
        cases_dir=tmp_path,
        bundle_index=index,
        today="2026-08-21",
    )
    assert result["status"] == "run"
    provenance = result["provenance"]
    assert set(PROVENANCE_FIELDS) <= set(provenance)
    assert provenance["bundle_is_fixture"] is True
    assert provenance["bundle_schools"] == 3
    assert provenance["model"] == "scripted"
    summary = result["summary"]
    # a: grounded; b: 105 is withheld so nothing shown; c: unknown school refused
    # as expected; d: the bundle lacks the school and the case did not expect it.
    assert summary == {
        "cases": 4,
        "passed": 2,
        "failed": 1,
        "errors": 1,
        "pass_rate": 0.5,
    }
    by_id = {c["id"]: c for c in result["cases"]}
    assert by_id["a"]["passed"] and by_id["a"]["shown"]
    assert by_id["b"]["notes"] == ["nothing_shown"]
    assert by_id["b"]["withheld_reasons"] == {"unverifiable_number": 1}
    assert by_id["c"]["passed"]
    assert by_id["d"]["error"]
    # The failing service statuses are errors, not failures.
    result = run_suite(
        "citation",
        service=AskService(bundle_root=fixture_bundle, corpus=corpus, provider=None),
        bundle_root=fixture_bundle,
        provider=provider,
        cases_dir=tmp_path,
        bundle_index=index,
        today="2026-08-21",
    )
    assert result["summary"]["errors"] >= 2


def test_the_cli_refuses_to_run_without_a_provider(
    monkeypatch: pytest.MonkeyPatch, fixture_bundle: Path, tmp_path: Path
) -> None:
    monkeypatch.delenv("HOMEROOM_ASK_PROVIDER", raising=False)
    assert main(["--bundle", str(fixture_bundle), "--results", str(tmp_path)]) == 2
    assert list(tmp_path.iterdir()) == []


def test_the_cli_writes_results_for_one_suite_with_a_scripted_provider(
    monkeypatch: pytest.MonkeyPatch, fixture_bundle: Path, tmp_path: Path
) -> None:
    from homeroom.ask import evalharness

    provider = ScriptedProvider(
        {
            "structure_question": lambda _: {
                "kind": "judgment",
                "measures": [],
                "compare": False,
                "definitions": [],
                "language": "en",
            }
        },
        model="scripted",
    )
    monkeypatch.setattr(evalharness, "provider_from_env", lambda: provider)
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "ranking_refusal.jsonl").write_text(
        json.dumps({"id": "x", "locale": "en", "cds": EXAMPLE, "question": "Good?"})
        + "\n",
        encoding="utf-8",
    )
    code = main(
        [
            "--bundle",
            str(fixture_bundle),
            "--results",
            str(tmp_path / "out"),
            "--cases",
            str(cases),
            "--suite",
            "ranking_refusal",
        ]
    )
    assert code == 0
    written = json.loads(
        (tmp_path / "out" / "scripted" / "ranking_refusal.json").read_text()
    )
    assert written["summary"]["passed"] == 1
    assert written["provenance"]["bundle_is_fixture"] is True


def test_the_cli_exits_nonzero_when_the_ask_layer_fails_a_ranking_case(
    monkeypatch: pytest.MonkeyPatch,
    fixture_bundle: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The exit code has to be the run's result, not the fact that it finished.

    Same CLI, same bundle, same case as the test above; the only difference is a
    model that answers the ranking question instead of refusing it. That is the
    worst outcome this project has, and until ADR 0004 the harness reported it
    with ``return 0``. The results file is still written, in full, with the
    failure in it: the exit code reports the shortfall, it does not hide it.
    """
    from homeroom.ask import evalharness

    answers_the_ranking_question = ScriptedProvider(
        {
            "structure_question": lambda _: {
                "kind": "measures",
                "measures": ["enrollment.total"],
                "compare": False,
                "definitions": [],
                "language": "en",
            },
            "answer_with_claims": lambda _: {
                "claims": [
                    {
                        "kind": "figure",
                        "text": "The school enrolled 100 students in 2025-26.",
                        "cites": [f"{TOTAL}|school"],
                    }
                ]
            },
        },
        model="scripted",
    )
    monkeypatch.setattr(
        evalharness, "provider_from_env", lambda: answers_the_ranking_question
    )
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "ranking_refusal.jsonl").write_text(
        json.dumps({"id": "x", "locale": "en", "cds": EXAMPLE, "question": "Good?"})
        + "\n",
        encoding="utf-8",
    )
    code = main(
        [
            "--bundle",
            str(fixture_bundle),
            "--results",
            str(tmp_path / "out"),
            "--cases",
            str(cases),
            "--suite",
            "ranking_refusal",
        ]
    )
    assert code == 1
    written = json.loads(
        (tmp_path / "out" / "scripted" / "ranking_refusal.json").read_text()
    )
    assert written["summary"]["failed"] == 1
    assert written["cases"][0]["notes"] == ["answered_without_refusal"]
    assert "NOT MET: ranking_refusal: 1 case(s) failed" in capsys.readouterr().err


def test_cases_dir_and_results_dir_are_where_the_docs_say() -> None:
    assert CASES_DIR.name == "cases" and CASES_DIR.parent.name == "evals"
    assert RESULTS_DIR.name == "results" and RESULTS_DIR.parent.name == "evals"
