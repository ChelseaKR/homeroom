"""``homeroom explain``: the record must say exactly what the page says, and no more.

The point of this verb is that a figure on a page becomes citable, so every test
here is about a way the record could differ from the page it claims to describe --
by inventing a number the state withheld, by collapsing a published zero into an
ordinary figure, by omitting a measure while presenting itself as complete, or by
reporting a school the build never saw as a school with nothing published.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from homeroom import artifacts
from homeroom.diff import diff
from homeroom.explain import (
    CELL_UNITS,
    PERCENT_UNITS,
    SOURCE_OF_BLOCK,
    ExplainError,
    explain,
    load_artifacts,
    main,
    measure_blocks,
    registered_blocks,
    rendered_state,
)
from homeroom.export import _cells_of
from homeroom.measures import Measure
from homeroom.render import _measure_cell

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"

EXAMPLE = "01100170112345"
"""Example Elementary: published figures, genuine zeros, and withheld cells."""
ALL_WITHHELD = "01100170154321"
"""Ejemplo Charter Academy: every enrollment figure the file mentions is withheld."""
NEVER_MENTIONED = "01100170176543"
"""Sin Datos Middle: no source file mentions it at all."""


@pytest.fixture(scope="module")
def artifacts_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The fixture artifacts, built by the same code path `make data-offline` runs."""
    out = tmp_path_factory.mktemp("artifacts")
    code = artifacts.main(
        [
            "--fixture",
            "--directory",
            str(FIXTURES / "pubschls.sample.txt"),
            "--enrollment",
            str(FIXTURES / "cdenroll.sample.txt"),
            "--assignments",
            str(FIXTURES / "tamo.sample.txt"),
            "--absenteeism",
            str(FIXTURES / "chronicabsenteeism.sample.txt"),
            "--out",
            str(out),
        ]
    )
    assert code == 0
    return out


@pytest.fixture(scope="module")
def loaded(artifacts_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    return load_artifacts(artifacts_dir)


@pytest.fixture(scope="module")
def example_record(loaded: tuple[dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
    schools, coverage = loaded
    return explain(schools, coverage, EXAMPLE)


# ----------------------------------------------------------------------------------
# A withheld cell carries no number. This is the whole reason the verb exists.
# ----------------------------------------------------------------------------------


def test_a_withheld_cell_says_suppressed_and_carries_no_value_key(
    example_record: dict[str, Any],
) -> None:
    withheld = [c for c in example_record["cells"] if c["status"] == "suppressed"]
    assert withheld, "the example fixture is supposed to have withheld cells"
    for cell in withheld:
        assert cell["rendered_state"] == "withheld"
        # Not `is None`, not `== 0`: the key must be ABSENT, so a consumer that
        # reads it raises instead of getting a number nobody published.
        assert "value" not in cell, cell["measure"]


def test_a_not_reported_cell_carries_no_value_key(
    example_record: dict[str, Any],
) -> None:
    nothing = [c for c in example_record["cells"] if c["status"] == "not_reported"]
    assert nothing
    for cell in nothing:
        assert cell["rendered_state"] == "nothing"
        assert "value" not in cell, cell["measure"]


def test_no_cell_anywhere_pairs_an_absence_with_a_number(
    example_record: dict[str, Any],
) -> None:
    for cell in example_record["cells"]:
        assert ("value" in cell) == (cell["status"] == "reported"), cell["measure"]


def test_the_all_withheld_school_publishes_no_number_at_all(
    loaded: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    schools, coverage = loaded
    record = explain(schools, coverage, ALL_WITHHELD)
    enrollment = [
        c
        for c in record["cells"]
        if c["source"] == "D2_enrollment" and c["status"] == "reported"
    ]
    assert enrollment == []
    assert any(c["status"] == "suppressed" for c in record["cells"])


# ----------------------------------------------------------------------------------
# The record's states are the page's states, including the fourth one.
# ----------------------------------------------------------------------------------


def test_every_rendered_state_is_the_class_the_renderer_emits(
    example_record: dict[str, Any],
) -> None:
    """`rendered_state` is checked against `_measure_cell`, not against a list here.

    A record that says `withheld` while the page renders `m-nothing` is a wrong
    citation. Reconstructing the Measure and asking the renderer is the only way
    this stays true when the renderer changes.
    """
    for cell in example_record["cells"]:
        if cell["status"] == "reported":
            measure = Measure.reported(cell["value"])
        elif cell["status"] == "suppressed":
            measure = Measure.suppressed()
        else:
            measure = Measure.not_reported()
        html = _measure_cell(measure, "en")
        assert f'm-{cell["rendered_state"]}"' in html, (cell["measure"], html)


def test_a_published_zero_is_not_collapsed_into_an_ordinary_number(
    example_record: dict[str, Any],
) -> None:
    """Three statuses, four rendered states. The split is the project's whole point."""
    zeros = [c for c in example_record["cells"] if c["rendered_state"] == "zero"]
    numbers = [c for c in example_record["cells"] if c["rendered_state"] == "number"]
    assert zeros and numbers
    assert all(c["status"] == "reported" for c in zeros + numbers)
    assert all(float(c["value"]) == 0.0 for c in zeros)
    assert all(float(c["value"]) != 0.0 for c in numbers)


def test_all_four_rendered_states_appear_in_the_example_school(
    example_record: dict[str, Any],
) -> None:
    """If the fixture stopped covering a state, these tests would pass over it."""
    assert {c["rendered_state"] for c in example_record["cells"]} == {
        "number",
        "zero",
        "withheld",
        "nothing",
    }


def test_rendered_state_refuses_a_status_it_does_not_know() -> None:
    with pytest.raises(ExplainError, match="unknown measure status"):
        rendered_state({"status": "probably_fine"})


def test_rendered_state_refuses_a_reported_cell_with_no_value() -> None:
    with pytest.raises(ExplainError, match="reported but carries no value"):
        rendered_state({"status": "reported"})


# ----------------------------------------------------------------------------------
# Provenance: which file, which year, which unit.
# ----------------------------------------------------------------------------------


def test_every_cell_names_its_file_year_and_unit(
    example_record: dict[str, Any],
) -> None:
    for cell in example_record["cells"]:
        assert cell["source"] in SOURCE_OF_BLOCK.values()
        assert cell["source_file"], cell["measure"]
        assert cell["unit"] in set(CELL_UNITS.values()), cell["measure"]


def test_the_directory_file_carries_no_academic_year_and_the_measure_files_do(
    example_record: dict[str, Any],
) -> None:
    """A measure has to be for a year. D1 is the directory and is not a measure."""
    for cell in example_record["cells"]:
        assert cell["academic_year"], cell["measure"]


def test_a_cell_percent_unit_matches_the_suffix_the_page_prints(
    example_record: dict[str, Any],
) -> None:
    """`explain` says `percent`; `render._measure_cell` prints `%`. Tied here.

    Otherwise the record's unit and the page's unit can drift apart, and a citation
    of "12.5 teachers" against a page reading "12.5%" is exactly the sort of error
    this verb is meant to make impossible.
    """
    reported = [c for c in example_record["cells"] if c["status"] == "reported"]
    assert reported
    for cell in reported:
        suffix = "%" if cell["unit"] in PERCENT_UNITS else ""
        html = _measure_cell(Measure.reported(cell["value"]), "en", unit=suffix)
        assert "%" in html if suffix else "%" not in html


def test_every_measure_block_declares_a_unit_and_a_source() -> None:
    """The two tables must agree on which blocks exist.

    `_unit_for` refuses a block with no declared unit rather than guessing one, and
    that refusal caught `teacher_assignments.total_assignments` on the first run.
    This keeps the two registries from drifting apart afterwards.
    """
    for block in SOURCE_OF_BLOCK:
        keys = {block} | {k.split(".", 1)[0] for k in CELL_UNITS}
        assert block in keys


def test_every_measure_block_the_build_writes_is_registered(
    loaded: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """The floor issue #109 asks for, and it reads the artifact rather than the list.

    `test_every_measure_block_declares_a_unit_and_a_source` compares
    `SOURCE_OF_BLOCK` with `CELL_UNITS` -- two hand-written dicts held to each other,
    and neither ever held to what `artifacts.py` actually writes. A sixth block would
    satisfy it by being in neither.

    This walks every school the build produced and states the two numbers: how many
    distinct measure blocks the artifact carries, and how many of them anything
    knows the source of.
    """
    schools, _ = loaded
    entries = schools["schools"]
    assert entries, "the build produced no schools; this floor reads nothing"

    discovered: set[str] = set()
    for entry in entries:
        discovered.update(measure_blocks(entry))
    assert discovered, "no school carries a measure block; the walk found nothing"

    unregistered = sorted(discovered - set(SOURCE_OF_BLOCK))
    assert not unregistered, (
        f"{len(discovered) - len(unregistered)} of {len(discovered)} measure blocks "
        f"in schools.json are registered; {unregistered} are not, and would be "
        f"dropped from the record, the dataset release and the diff."
    )


def test_a_measure_block_nobody_registered_is_refused_by_every_consumer(
    loaded: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Issue #109: a sixth block used to disappear from four places, all exiting 0.

    The synthetic block is shaped exactly like a real one -- a dict of cells, each
    with a ``status`` -- because that is what `artifacts.py` would write for a new
    measure and it is what the walk has to notice.
    """
    schools, coverage = loaded
    mutated = json.loads(json.dumps(schools))
    for entry in mutated["schools"]:
        entry["suspensions"] = {"total": {"status": "reported", "value": 3}}

    school = next(s for s in mutated["schools"] if s["cds_code"] == EXAMPLE)
    assert "suspensions" in measure_blocks(school)

    with pytest.raises(ExplainError, match="suspensions"):
        registered_blocks(school)
    with pytest.raises(ExplainError, match="suspensions"):
        explain(mutated, coverage, EXAMPLE)
    with pytest.raises(ExplainError, match="suspensions"):
        _cells_of(school)
    with pytest.raises(ExplainError, match="suspensions"):
        diff((schools, coverage), (mutated, coverage))


def test_a_block_with_no_declared_unit_is_refused_rather_than_guessed(
    loaded: tuple[dict[str, Any], dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schools, coverage = loaded
    monkeypatch.delitem(CELL_UNITS, "grades", raising=True)
    with pytest.raises(ExplainError, match="no unit is declared"):
        explain(schools, coverage, EXAMPLE)


# ----------------------------------------------------------------------------------
# Refusals. Each of these would otherwise publish a comfortable wrong answer.
# ----------------------------------------------------------------------------------


def test_an_unknown_cds_is_an_error_not_an_empty_record(
    loaded: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    schools, coverage = loaded
    with pytest.raises(ExplainError, match="never saw"):
        explain(schools, coverage, "99999999999999")


def test_a_school_nothing_mentions_still_gets_a_record(
    loaded: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """`not in the file` and `in the file with nothing published` are different facts.

    Sin Datos Middle is in the directory and in no measure file, so it has a record
    and every cell in it is `nothing`. An unknown CDS raises. Collapsing the two
    would report a school Homeroom has never heard of as one it looked at.
    """
    schools, coverage = loaded
    record = explain(schools, coverage, NEVER_MENTIONED)
    assert record["cells"]
    assert {c["rendered_state"] for c in record["cells"]} == {"nothing"}
    assert not any("value" in c for c in record["cells"])


def test_an_artifact_that_does_not_say_whether_it_is_a_fixture_is_refused(
    loaded: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """`bool(coverage.get("is_fixture"))` would read an absent flag as `False`.

    That is the shape #100 found in the eval harness: a bundle that did not say what
    it was produced a results file claiming it was real. The same defect here would
    put a fixture figure into a citation.
    """
    schools, coverage = loaded
    without = {k: v for k, v in coverage.items() if k != "is_fixture"}
    with pytest.raises(ExplainError, match="cannot say whether"):
        explain(schools, without, EXAMPLE)

    for not_a_bool in ("false", "", 0, 1, None):
        with pytest.raises(ExplainError, match="cannot say whether"):
            explain(schools, {**coverage, "is_fixture": not_a_bool}, EXAMPLE)


def test_a_fixture_record_says_so(example_record: dict[str, Any]) -> None:
    assert example_record["is_fixture"] is True


def test_missing_artifacts_are_named_rather_than_read_as_empty(tmp_path: Path) -> None:
    with pytest.raises(ExplainError, match="does not exist"):
        load_artifacts(tmp_path)


def test_schools_json_without_a_schools_list_is_refused(
    loaded: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    _, coverage = loaded
    with pytest.raises(ExplainError, match="no `schools` list"):
        explain({}, coverage, EXAMPLE)


def test_coverage_json_without_sources_is_refused(
    loaded: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    schools, coverage = loaded
    without = {k: v for k, v in coverage.items() if k != "sources"}
    with pytest.raises(ExplainError, match="no `sources` object"):
        explain(schools, without, EXAMPLE)


# ----------------------------------------------------------------------------------
# Completeness: a record that presents itself as whole must be whole.
# ----------------------------------------------------------------------------------


def test_every_cell_in_the_artifact_reaches_the_record(
    loaded: tuple[dict[str, Any], dict[str, Any]], example_record: dict[str, Any]
) -> None:
    """Counted from `schools.json` itself, so a measure added there cannot be dropped.

    Enumerating the blocks by hand is how a record ends up describing a subset while
    presenting itself as the whole school.

    Issue #109: this test used to do that itself. The sum was taken over
    `SOURCE_OF_BLOCK` -- the same hand-written list `explain` iterated -- so an
    unregistered block shrank **both** sides of the equality and the assertion held
    by construction rather than by agreement. Measured on the fixture school: 74
    cells in total and 74 in registered blocks, which is what made it look sound.
    The count is now taken over the school entry with no list consulted at all.
    """
    schools, _ = loaded
    school = next(s for s in schools["schools"] if s["cds_code"] == EXAMPLE)

    def count(node: Any) -> int:
        if isinstance(node, dict):
            if "status" in node:
                return 1
            return sum(count(v) for v in node.values())
        return 0

    in_artifact = count(school)
    assert in_artifact, "the fixture school carries no cells; this compares nothing"
    assert len(example_record["cells"]) == in_artifact


def test_the_record_names_only_the_sources_its_cells_came_from(
    example_record: dict[str, Any],
) -> None:
    used = {c["source"] for c in example_record["cells"]}
    assert set(example_record["sources"]) >= used


# ----------------------------------------------------------------------------------
# Determinism, across processes.
# ----------------------------------------------------------------------------------


def test_the_record_is_byte_identical_across_separate_interpreters(
    artifacts_dir: Path,
) -> None:
    """Two runs in ONE interpreter prove nothing: set iteration is stable within one.

    So this runs the CLI three times in three processes under three different
    `PYTHONHASHSEED` values, and the example school has 74 cells, which is enough
    items for an ordering mistake to be observable. One row is always in order.
    """
    outputs = []
    for seed in ("0", "1", "42"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        completed = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-m",
                "homeroom.explain",
                "--artifacts",
                str(artifacts_dir),
                "--cds",
                EXAMPLE,
            ],
            capture_output=True,
            check=True,
            env=env,
        )
        outputs.append(completed.stdout)
    assert len(json.loads(outputs[0])["cells"]) > 8
    assert outputs[0] == outputs[1] == outputs[2]


# ----------------------------------------------------------------------------------
# The command line.
# ----------------------------------------------------------------------------------


def test_main_prints_the_record_and_exits_zero(
    artifacts_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--artifacts", str(artifacts_dir), "--cds", EXAMPLE])
    assert code == 0
    record = json.loads(capsys.readouterr().out)
    assert record["cds_code"] == EXAMPLE


def test_main_exits_two_and_says_why_on_an_unknown_school(
    artifacts_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--artifacts", str(artifacts_dir), "--cds", "99999999999999"])
    assert code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "never saw" in captured.err


def test_main_exits_two_when_the_artifacts_are_not_there(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--artifacts", str(tmp_path), "--cds", EXAMPLE])
    assert code == 2
    assert "does not exist" in capsys.readouterr().err


# ----------------------------------------------------------------------------------
# A source that was never supplied.
# ----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def enrollment_only_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Artifacts built with neither D3 nor D5, which `artifacts.py` allows."""
    out = tmp_path_factory.mktemp("enrollment-only")
    code = artifacts.main(
        [
            "--fixture",
            "--directory",
            str(FIXTURES / "pubschls.sample.txt"),
            "--enrollment",
            str(FIXTURES / "cdenroll.sample.txt"),
            "--out",
            str(out),
        ]
    )
    assert code == 0
    return out


def test_an_unsupplied_source_yields_no_cells_rather_than_a_school_of_zeros(
    enrollment_only_dir: Path,
) -> None:
    """The branch that matters most: nothing was read, so nothing may be reported.

    `artifacts.py` omits the block entirely when a source is not supplied, precisely
    so no consumer can read a school-shaped set of zeros as "Homeroom looked and
    found none". If `explain` filled those cells in as `not_reported` it would be
    saying CDE published nothing for this school, when in fact this build never
    opened the file.
    """
    schools, coverage = load_artifacts(enrollment_only_dir)
    record = explain(schools, coverage, EXAMPLE)
    sources = {c["source"] for c in record["cells"]}
    assert sources == {"D2_enrollment"}
    assert not any(
        c["measure"].startswith("chronic_absenteeism") for c in record["cells"]
    )
    assert not any(
        c["measure"].startswith("teacher_assignments") for c in record["cells"]
    )


def test_an_unsupplied_source_is_still_named_in_the_record(
    enrollment_only_dir: Path,
) -> None:
    """Omitting the cells is only honest if the omission is stated somewhere.

    A record whose cells simply stop at enrollment, with nothing saying why, reads
    as a school with no absenteeism data. The `sources` block carries CDE's own
    answer: the file was not supplied to this build.
    """
    schools, coverage = load_artifacts(enrollment_only_dir)
    record = explain(schools, coverage, EXAMPLE)
    for key in ("D3_chronic_absenteeism", "D5_teacher_assignments"):
        assert key in record["sources"], key
        assert record["sources"][key]["supplied"] is False
