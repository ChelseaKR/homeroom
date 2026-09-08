"""``homeroom diff``: the event this project must never ship unnoticed.

A state flip on a real school's page -- a figure that was published and is now
withheld, or the reverse -- is the thing a 23,310-file git diff of markup buries.
Every test here is about a way a diff of that kind normally misleads: by calling a
withheld cell a changed value, by reporting a file nobody opened as a dataset CDE
withdrew, by diffing a school against one that is not there, or by comparing a
fixture run to an acquired one.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from homeroom import artifacts
from homeroom.diff import TRANSITIONS, DiffError, diff, main, render_markdown
from homeroom.explain import load_artifacts

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"

EXAMPLE = "01100170112345"
"""Example Elementary: published figures, genuine zeros, and withheld cells."""


def _build(out: Path, *, assignments: bool = True, absenteeism: bool = True) -> Path:
    argv = [
        "--fixture",
        "--directory",
        str(FIXTURES / "pubschls.sample.txt"),
        "--enrollment",
        str(FIXTURES / "cdenroll.sample.txt"),
        "--out",
        str(out),
    ]
    if assignments:
        argv += ["--assignments", str(FIXTURES / "tamo.sample.txt")]
    if absenteeism:
        argv += ["--absenteeism", str(FIXTURES / "chronicabsenteeism.sample.txt")]
    assert artifacts.main(argv) == 0
    return out


@pytest.fixture(scope="module")
def base(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return load_artifacts(_build(tmp_path_factory.mktemp("base")))


@pytest.fixture(scope="module")
def enrollment_only(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return load_artifacts(
        _build(tmp_path_factory.mktemp("enrol"), assignments=False, absenteeism=False)
    )


def _school(
    side: tuple[dict[str, Any], dict[str, Any]], cds: str = EXAMPLE
) -> dict[str, Any]:
    return next(s for s in side[0]["schools"] if s["cds_code"] == cds)


def _mutated(
    side: tuple[dict[str, Any], dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    return (copy.deepcopy(side[0]), copy.deepcopy(side[1]))


# ----------------------------------------------------------------------------------
# The issue's three acceptance criteria.
# ----------------------------------------------------------------------------------


def test_identical_artifacts_produce_an_empty_diff(
    base: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    record = diff(base, base)
    assert record["events"] == []
    assert record["counts"] == {}


def test_masking_one_cell_yields_exactly_one_published_to_withheld_and_nothing_else(
    base: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """The criterion the whole verb exists for."""
    after = _mutated(base)
    cell = _school(after)["grades"]["GR_01"]
    assert cell["status"] == "reported"
    cell.clear()
    cell["status"] = "suppressed"

    record = diff(base, after)
    assert record["counts"] == {"published_to_withheld": 1}
    (event,) = record["events"]
    assert event["cds_code"] == EXAMPLE
    assert event["measure"] == "grades.GR_01"
    assert event["from_state"] == "number"
    assert event["to_state"] == "withheld"
    # The number that was published is carried; the withheld side carries nothing.
    assert "from" in event
    assert "to" not in event


def test_a_removed_school_is_reported_as_removed_and_not_as_lost_cells(
    base: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    after = _mutated(base)
    after[0]["schools"] = [s for s in after[0]["schools"] if s["cds_code"] != EXAMPLE]

    record = diff(base, after)
    assert record["counts"] == {"school_removed": 1}
    (event,) = record["events"]
    assert event["cds_code"] == EXAMPLE
    assert event["name"] == "Example Elementary"


def test_an_added_school_is_reported_as_added(
    base: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    before = _mutated(base)
    before[0]["schools"] = [s for s in before[0]["schools"] if s["cds_code"] != EXAMPLE]
    record = diff(before, base)
    assert record["counts"] == {"school_added": 1}


# ----------------------------------------------------------------------------------
# "Value changed to nothing" is not a change of value.
# ----------------------------------------------------------------------------------


def test_a_withheld_cell_becoming_published_is_its_own_event(
    base: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    after = _mutated(base)
    cell = _school(after)["subgroups"]["gender"]["GN_M"]
    assert cell["status"] == "suppressed"
    cell["status"] = "reported"
    cell["value"] = 41

    record = diff(base, after)
    assert record["counts"] == {"withheld_to_published": 1}
    (event,) = record["events"]
    assert "from" not in event
    assert event["to"] == 41


def test_a_withheld_cell_becoming_unreported_is_neither_a_number_nor_a_publication(
    base: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    after = _mutated(base)
    cell = _school(after)["subgroups"]["gender"]["GN_M"]
    cell["status"] = "not_reported"

    record = diff(base, after)
    assert record["counts"] == {"withheld_to_nothing": 1}
    (event,) = record["events"]
    assert "from" not in event and "to" not in event


def test_a_published_number_becoming_a_genuine_zero_is_not_just_a_number_change(
    base: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """A zero is labelled in words on the page, so it is its own event here too."""
    after = _mutated(base)
    _school(after)["grades"]["GR_01"]["value"] = 0

    record = diff(base, after)
    assert record["counts"] == {"number_to_zero": 1}
    (event,) = record["events"]
    assert event["to"] == 0


def test_a_changed_number_is_reported_with_both_numbers(
    base: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    after = _mutated(base)
    before_value = _school(base)["grades"]["GR_01"]["value"]
    _school(after)["grades"]["GR_01"]["value"] = before_value + 3

    record = diff(base, after)
    assert record["counts"] == {"number_changed": 1}
    (event,) = record["events"]
    assert event["from"] == before_value
    assert event["to"] == before_value + 3


def test_every_state_pair_that_can_occur_has_a_name() -> None:
    """A transition with no name would fall through as an untyped 'changed'.

    Sixteen ordered pairs over four states; the four identity pairs are not events,
    and `number -> number` is, because the number can move.
    """
    states = ("number", "zero", "withheld", "nothing")
    for was in states:
        for now in states:
            if was == now and was not in ("number", "zero"):
                continue
            if was == now == "zero":
                continue  # two zeros are the same cell
            assert (was, now) in TRANSITIONS, (was, now)


# ----------------------------------------------------------------------------------
# A source nobody supplied is one event, not thousands.
# ----------------------------------------------------------------------------------


def test_a_source_that_was_not_supplied_is_one_event_per_block(
    base: tuple[dict[str, Any], dict[str, Any]],
    enrollment_only: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Otherwise this reads as CDE withdrawing two whole datasets.

    Cell by cell it would be every absenteeism and assignment cell of every school
    flipping to nothing. Nobody opened the file; that is a fact about the build, not
    about the state's publishing.
    """
    record = diff(base, enrollment_only)
    assert record["counts"] == {"source_unsupplied": 2}
    blocks = {e["measure_block"] for e in record["events"]}
    assert blocks == {"chronic_absenteeism", "teacher_assignments"}
    for event in record["events"]:
        # The suppression is stated, with its size, rather than being silent.
        assert event["cell_events_suppressed"] > 0
        assert "did not open the file" in event["why"]


def test_a_source_appearing_is_the_mirror_event(
    base: tuple[dict[str, Any], dict[str, Any]],
    enrollment_only: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    record = diff(enrollment_only, base)
    assert record["counts"] == {"source_supplied": 2}


def test_the_suppressed_count_equals_the_cells_that_would_have_been_reported(
    base: tuple[dict[str, Any], dict[str, Any]],
    enrollment_only: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Counted from the artifact, so the stated size cannot drift from the truth."""

    def count(node: Any) -> int:
        if isinstance(node, dict):
            return 1 if "status" in node else sum(count(v) for v in node.values())
        return 0

    record = diff(base, enrollment_only)
    stated = {e["measure_block"]: e["cell_events_suppressed"] for e in record["events"]}
    for block, said in stated.items():
        actual = sum(count(s.get(block)) for s in base[0]["schools"])
        assert said == actual, block


def test_a_cell_appearing_inside_a_supplied_block_is_still_reported(
    base: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Block-level suppression must not swallow a real per-school shape change."""
    after = _mutated(base)
    del _school(after)["grades"]["GR_01"]

    record = diff(base, after)
    assert record["counts"] == {"cell_removed": 1}
    (event,) = record["events"]
    assert event["measure"] == "grades.GR_01"


# ----------------------------------------------------------------------------------
# Refusals.
# ----------------------------------------------------------------------------------


def test_a_fixture_run_and_an_acquired_run_are_refused(
    base: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    acquired = _mutated(base)
    acquired[1]["is_fixture"] = False
    with pytest.raises(DiffError, match="fixture build and the other is not"):
        diff(base, acquired)


def test_an_artifact_that_does_not_say_what_it_is_gets_refused(
    base: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    unstated = _mutated(base)
    del unstated[1]["is_fixture"]
    with pytest.raises(DiffError, match="does not state `is_fixture`"):
        diff(base, unstated)
    with pytest.raises(DiffError, match=r"the old coverage\.json"):
        diff(unstated, base)


def test_a_school_with_no_cds_code_is_refused_rather_than_matched_by_position(
    base: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Position is not identity. Two files' nth entries are not the same school."""
    broken = _mutated(base)
    del broken[0]["schools"][0]["cds_code"]
    with pytest.raises(DiffError, match="refusing to diff by position"):
        diff(base, broken)


def test_a_duplicated_cds_code_is_refused(
    base: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    broken = _mutated(base)
    broken[0]["schools"].append(copy.deepcopy(broken[0]["schools"][0]))
    with pytest.raises(DiffError, match="appears twice"):
        diff(base, broken)


def test_schools_json_without_a_schools_list_is_refused(
    base: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    with pytest.raises(DiffError, match="no `schools` list"):
        diff(base, ({}, base[1]))


# ----------------------------------------------------------------------------------
# Output.
# ----------------------------------------------------------------------------------


def test_the_markdown_for_an_empty_diff_says_nothing_changed(
    base: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    text = render_markdown(diff(base, base))
    assert "Nothing changed" in text
    assert "|" not in text


def test_the_markdown_never_prints_a_bare_blank_where_a_number_is_absent(
    base: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """A blank cell in a table of numbers reads as a zero. It must read as a state."""
    after = _mutated(base)
    cell = _school(after)["grades"]["GR_01"]
    cell.clear()
    cell["status"] = "suppressed"
    text = render_markdown(diff(base, after))
    row = next(line for line in text.splitlines() if "published_to_withheld" in line)
    assert "withheld" in row
    assert "|  |" not in row


def test_the_markdown_says_when_both_sides_are_fixtures(
    base: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    assert "fixture builds" in render_markdown(diff(base, base))


def test_main_prints_json_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = _build(tmp_path / "old")
    new = _build(tmp_path / "new")
    capsys.readouterr()  # the artifact builder prints its own report
    assert main(["--old", str(old), "--new", str(new)]) == 0
    assert json.loads(capsys.readouterr().out)["events"] == []


def test_main_renders_markdown_on_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = _build(tmp_path / "old")
    new = _build(tmp_path / "new")
    capsys.readouterr()
    assert main(["--old", str(old), "--new", str(new), "--format", "markdown"]) == 0
    assert "Nothing changed" in capsys.readouterr().out


def test_main_exits_two_and_says_why_when_the_sides_are_not_comparable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = _build(tmp_path / "old")
    new = _build(tmp_path / "new", assignments=True, absenteeism=True)
    coverage = json.loads((new / "coverage.json").read_text())
    coverage["is_fixture"] = False
    (new / "coverage.json").write_text(json.dumps(coverage))

    capsys.readouterr()
    assert main(["--old", str(old), "--new", str(new)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "fixture build and the other is not" in captured.err


def test_main_exits_two_when_an_artifacts_directory_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = _build(tmp_path / "old")
    capsys.readouterr()
    assert main(["--old", str(old), "--new", str(tmp_path / "nope")]) == 2
    assert "does not exist" in capsys.readouterr().err


def test_the_diff_is_byte_identical_across_separate_interpreters(
    tmp_path: Path,
) -> None:
    """Across processes with varied PYTHONHASHSEED, over a diff with enough events.

    Two runs in one interpreter prove nothing about ordering. Eleven schools' worth
    of one event each is enough items for an ordering mistake to be observable; one
    event is always in order.
    """
    old = _build(tmp_path / "old")
    new = _build(tmp_path / "new")
    schools = json.loads((new / "schools.json").read_text())
    # EVERY reported cell, not one per block. The first version of this test changed
    # one cell per block and produced five events, which is few enough that an
    # ordering mistake could hide; the assertion below caught it rather than the
    # test passing over a fixture too narrow to observe order in.
    changed = 0
    for school in schools["schools"]:
        for cell in sorted(school.get("grades", {}).values(), key=lambda c: sorted(c)):
            if cell.get("status") == "reported":
                cell.clear()
                cell["status"] = "suppressed"
                changed += 1
        for family in school.get("subgroups", {}).values():
            for cell in family.values():
                if cell.get("status") == "reported":
                    cell["value"] = float(cell["value"]) + 1
                    changed += 1
    (new / "schools.json").write_text(json.dumps(schools))
    assert changed >= 8, (
        f"only {changed} events; widen the fixture before trusting this"
    )

    outputs = []
    for seed in ("0", "1", "42"):
        completed = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-m",
                "homeroom.diff",
                "--old",
                str(old),
                "--new",
                str(new),
            ],
            capture_output=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        outputs.append(completed.stdout)
    assert len(json.loads(outputs[0])["events"]) >= 8
    assert outputs[0] == outputs[1] == outputs[2]


def test_a_diff_of_two_acquired_runs_carries_no_fixture_warning(
    base: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """The warning must appear only when it is true.

    A standing "these are fixtures" banner on a report about real schools would be
    read as boilerplate and stop being read at all -- and the run where it matters is
    the one where it is absent from a report that should carry it.
    """
    acquired = _mutated(base)
    acquired[1]["is_fixture"] = False
    other = _mutated(acquired)
    text = render_markdown(diff(acquired, other))
    assert "fixture builds" not in text
    assert "Nothing changed" in text
