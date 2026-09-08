"""``homeroom dataset``: the honesty rules have to survive the trip into a spreadsheet.

Every test here is about a way this release could say something the pages do not. A
blank cell that a consumer reads as zero. A withheld figure carrying a number. A
truncated file presenting itself as complete. A fixture shipped as California's data. A
schema that describes a column the CSV does not have, or misses one it does.

The central assertion is a **biconditional**, not an absence: a value cell is filled
exactly when its state cell says a number was published. "No empty cells" would be
satisfied by a file that wrote ``0`` into every gap, which is the defect.
"""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest

from homeroom import artifacts
from homeroom.explain import ExplainError, explain, load_artifacts, rendered_state
from homeroom.export import (
    DATASET_STATES,
    IDENTITY_COLUMNS,
    STATE_OF_RENDERED,
    STATE_SUFFIX,
    VALUE_SUFFIX,
    ExportError,
    build_table,
    dataset_name,
    main,
    measure_paths,
    table_schema,
    write_dataset,
)
from homeroom.measures import Measure, MeasureStatus, SuppressedValueError
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
def released(artifacts_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The fixture artifacts exported as a release directory."""
    out = tmp_path_factory.mktemp("release")
    write_dataset(artifacts_dir, out, allow_fixture=True)
    return out / "homeroom-dataset-fixture"


@pytest.fixture(scope="module")
def rows(released: Path) -> list[dict[str, str]]:
    with (released / "schools.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _measure_columns(row: dict[str, str]) -> list[str]:
    return [column for column in row if column.endswith(STATE_SUFFIX)]


# ----------------------------------------------------------------------------------
# The rule the whole file exists for.
# ----------------------------------------------------------------------------------


def test_every_state_cell_is_filled_with_one_of_the_four_words(
    rows: list[dict[str, str]],
) -> None:
    for row in rows:
        for column in _measure_columns(row):
            assert row[column] in DATASET_STATES, (
                f"{row['cds_code']} {column} is {row[column]!r}; a state cell that is "
                "blank or unrecognized leaves a reader to supply the meaning"
            )


def test_a_value_cell_is_filled_exactly_when_a_number_was_published(
    rows: list[dict[str, str]],
) -> None:
    """The biconditional. Both directions, because each has its own failure.

    A value present where nothing was published is a withheld figure printed as a
    number. A value absent where one was published is a real figure lost to a blank.
    """
    for row in rows:
        for state_column in _measure_columns(row):
            value_column = state_column[: -len(STATE_SUFFIX)] + VALUE_SUFFIX
            published = row[state_column] in ("reported", "zero")
            filled = row[value_column] != ""
            assert filled is published, (
                f"{row['cds_code']} {value_column}={row[value_column]!r} against "
                f"{state_column}={row[state_column]!r}"
            )


def test_the_fixture_exercises_all_four_states(rows: list[dict[str, str]]) -> None:
    """Otherwise the biconditional above is a property over a case that never occurs.

    One state in a fixture is the "fixture sits where the failure is impossible" trap:
    a rule about four states, measured over a file that only ever shows one of them,
    passes for a reason unrelated to the rule.
    """
    seen = {row[column] for row in rows for column in _measure_columns(row)}
    assert seen == set(DATASET_STATES), f"the fixture only reaches {sorted(seen)}"


def test_a_reconstructed_measure_refuses_to_yield_a_number_for_an_absence(
    rows: list[dict[str, str]],
) -> None:
    """The CSV read back through the type that enforces the rule.

    ``Measure.number()`` is the project's guarantee that a withheld cell cannot be read
    as a figure. Reconstructing each row's cells and calling it proves the CSV carries
    the same guarantee: for every non-published state there is no number to reconstruct
    from, and for every published one the number is the one in the file.
    """
    checked = 0
    for row in rows:
        for state_column in _measure_columns(row):
            value_column = state_column[: -len(STATE_SUFFIX)] + VALUE_SUFFIX
            state = row[state_column]
            if state in ("reported", "zero"):
                measure = Measure.reported(float(row[value_column]))
                assert measure.number() == float(row[value_column])
                assert measure.is_zero is (state == "zero")
            else:
                measure = (
                    Measure.suppressed()
                    if state == "suppressed"
                    else Measure.not_reported()
                )
                with pytest.raises(SuppressedValueError):
                    measure.number()
            checked += 1
    assert checked > 0, "no measure columns were examined; this proves nothing"


def test_the_dataset_states_are_the_states_the_page_renders(
    rows: list[dict[str, str]],
) -> None:
    """``STATE_OF_RENDERED`` is total over what the renderer can actually emit.

    Asserted by driving ``render._measure_cell`` with a Measure of each shape and
    reading the class it emits, rather than against a list of four strings retyped
    here, which would drift the moment the renderer gained a fifth cell.
    """
    samples = {
        "number": Measure.reported(12.0),
        "zero": Measure.reported(0.0),
        "withheld": Measure.suppressed(),
        "nothing": Measure.not_reported(),
    }
    emitted = set()
    for expected_rendered, measure in samples.items():
        cell: dict[str, Any] = {"status": measure.status.value}
        if measure.status is MeasureStatus.REPORTED:
            cell["value"] = measure.number()
        assert rendered_state(cell) == expected_rendered
        markup = _measure_cell(measure, "en")
        assert f"m-{expected_rendered}" in markup
        emitted.add(expected_rendered)
    assert set(STATE_OF_RENDERED) == emitted
    assert set(STATE_OF_RENDERED.values()) == set(DATASET_STATES)


# ----------------------------------------------------------------------------------
# The schema, the records, and the manifest.
# ----------------------------------------------------------------------------------


def test_the_schema_declares_exactly_the_columns_the_csv_has_in_order(
    released: Path, rows: list[dict[str, str]]
) -> None:
    schema = json.loads((released / "schools.schema.json").read_text(encoding="utf-8"))
    assert [field["name"] for field in schema["fields"]] == list(rows[0])
    assert schema["primaryKey"] == ["cds_code"]
    assert schema["missingValues"] == [""]


def test_every_schema_field_says_what_it_holds(released: Path) -> None:
    schema = json.loads((released / "schools.schema.json").read_text(encoding="utf-8"))
    for field in schema["fields"]:
        assert field["description"].strip(), f"{field['name']} has no description"


def test_state_fields_are_required_and_enumerated_and_value_fields_are_not(
    released: Path,
) -> None:
    """The two-sided ``missingValues`` rule, written into the schema.

    A blank in a value column is a genuine absence and must read as null. A blank in a
    state column is a broken file: the state is always written, so it is ``required``
    and constrained to the four words.
    """
    schema = json.loads((released / "schools.schema.json").read_text(encoding="utf-8"))
    states = [f for f in schema["fields"] if f["name"].endswith(STATE_SUFFIX)]
    values = [f for f in schema["fields"] if f["name"].endswith(VALUE_SUFFIX)]
    assert states and values
    for field in states:
        assert field["constraints"]["required"] is True
        assert field["constraints"]["enum"] == list(DATASET_STATES)
    for field in values:
        assert field["type"] == "number"
        assert "required" not in field.get("constraints", {})


def test_each_school_record_is_the_one_explain_prints(
    released: Path, artifacts_dir: Path
) -> None:
    """One record shape, from one function.

    Two functions producing "the school's record" would let the release and the CLI
    describe the same school differently, and nothing would say which was right.
    """
    schools, coverage = load_artifacts(artifacts_dir)
    for cds in (EXAMPLE, ALL_WITHHELD, NEVER_MENTIONED):
        written = json.loads(
            (released / "schools" / f"{cds}.json").read_text(encoding="utf-8")
        )
        assert written == explain(schools, coverage, cds)


def test_coverage_travels_byte_for_byte(released: Path, artifacts_dir: Path) -> None:
    assert (released / "coverage.json").read_bytes() == (
        artifacts_dir / "coverage.json"
    ).read_bytes()


def test_the_manifest_digests_every_file_and_does_not_list_itself(
    released: Path,
) -> None:
    import hashlib

    manifest = json.loads((released / "manifest.json").read_text(encoding="utf-8"))
    on_disk = sorted(
        str(path.relative_to(released))
        for path in released.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    )
    assert [entry["path"] for entry in manifest["files"]] == on_disk
    for entry in manifest["files"]:
        blob = (released / entry["path"]).read_bytes()
        assert entry["bytes"] == len(blob)
        assert entry["sha256"] == hashlib.sha256(blob).hexdigest()


def test_the_manifest_carries_the_acquired_files_and_their_dates(
    released: Path, artifacts_dir: Path
) -> None:
    manifest = json.loads((released / "manifest.json").read_text(encoding="utf-8"))
    coverage = json.loads((artifacts_dir / "coverage.json").read_text(encoding="utf-8"))
    assert manifest["sources"] == coverage["sources"]
    assert (
        manifest["schools"]
        == coverage["profiles"]
        == len(list(released.glob("schools/*.json")))
    )


def test_a_fixture_release_says_so_on_every_row_and_in_its_name(
    released: Path, rows: list[dict[str, str]]
) -> None:
    """A CSV opened away from its directory still has to say what it is."""
    assert released.name == "homeroom-dataset-fixture"
    assert "is_fixture" in IDENTITY_COLUMNS
    assert {row["is_fixture"] for row in rows} == {"true"}


def test_rows_are_one_per_school_sorted_by_cds_code(
    rows: list[dict[str, str]], artifacts_dir: Path
) -> None:
    _, coverage = load_artifacts(artifacts_dir)
    codes = [row["cds_code"] for row in rows]
    assert codes == sorted(codes)
    assert len(codes) == len(set(codes)) == coverage["profiles"]


# ----------------------------------------------------------------------------------
# Determinism. A citable dataset whose digest moves is not citable.
# ----------------------------------------------------------------------------------


def test_two_exports_produce_byte_identical_files_and_tarballs(
    artifacts_dir: Path, tmp_path: Path
) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    write_dataset(artifacts_dir, first, allow_fixture=True)
    write_dataset(artifacts_dir, second, allow_fixture=True)
    name = "homeroom-dataset-fixture"
    assert (first / f"{name}.tar.gz").read_bytes() == (
        second / f"{name}.tar.gz"
    ).read_bytes()
    for path in sorted((first / name).rglob("*")):
        if path.is_file():
            twin = second / name / path.relative_to(first / name)
            assert path.read_bytes() == twin.read_bytes(), path


def test_the_release_is_byte_identical_across_separate_interpreters(
    artifacts_dir: Path, tmp_path: Path
) -> None:
    """Three processes, three ``PYTHONHASHSEED`` values.

    Two runs inside one interpreter prove nothing about ordering: set iteration over
    strings is stable within a process. The fixture carries 222 measure cells across
    three schools, which is enough rows for an ordering mistake to be visible -- one
    row is always in order.
    """
    digests = set()
    for index, seed in enumerate(("0", "1", "12345")):
        out = tmp_path / f"seed-{index}"
        environment = dict(os.environ, PYTHONHASHSEED=seed)
        completed = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-m",
                "homeroom.export",
                "--artifacts",
                str(artifacts_dir),
                "--out",
                str(out),
                "--allow-fixture",
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        digests.add((out / "homeroom-dataset-fixture.tar.gz").read_bytes())
    assert len(digests) == 1


def test_the_tarball_holds_the_directory_with_no_build_machine_in_it(
    artifacts_dir: Path, tmp_path: Path
) -> None:
    write_dataset(artifacts_dir, tmp_path, allow_fixture=True)
    blob = (tmp_path / "homeroom-dataset-fixture.tar.gz").read_bytes()
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
        members = archive.getmembers()
    names = sorted(member.name for member in members)
    assert "homeroom-dataset-fixture/schools.csv" in names
    assert f"homeroom-dataset-fixture/schools/{EXAMPLE}.json" in names
    for member in members:
        assert member.mtime == 0
        assert member.uid == member.gid == 0
        assert member.uname == member.gname == ""


# ----------------------------------------------------------------------------------
# The refusals.
# ----------------------------------------------------------------------------------


def test_a_fixture_build_is_refused_unless_it_is_asked_for(
    artifacts_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--artifacts", str(artifacts_dir), "--out", str(tmp_path)])
    assert code == 2
    assert "fixture build" in capsys.readouterr().err
    assert not list(tmp_path.iterdir()), "nothing may be written before the refusal"


def _artifacts_with(
    tmp_path: Path,
    artifacts_dir: Path,
    *,
    schools: dict[str, Any] | None = None,
    coverage: dict[str, Any] | None = None,
) -> Path:
    """A copy of the fixture artifacts with one file replaced."""
    loaded_schools, loaded_coverage = load_artifacts(artifacts_dir)
    out = tmp_path / "artifacts"
    out.mkdir()
    (out / "schools.json").write_text(
        json.dumps(schools if schools is not None else loaded_schools), encoding="utf-8"
    )
    (out / "coverage.json").write_text(
        json.dumps(coverage if coverage is not None else loaded_coverage),
        encoding="utf-8",
    )
    return out


def test_artifacts_that_do_not_state_is_fixture_are_refused(
    artifacts_dir: Path, tmp_path: Path
) -> None:
    _, coverage = load_artifacts(artifacts_dir)
    del coverage["is_fixture"]
    broken = _artifacts_with(tmp_path, artifacts_dir, coverage=coverage)
    with pytest.raises(ExportError, match="is_fixture"):
        write_dataset(broken, tmp_path / "out", allow_fixture=True)


def test_a_short_release_is_refused_rather_than_published(
    artifacts_dir: Path, tmp_path: Path
) -> None:
    """A truncated dataset presenting itself as complete is the worst failure here."""
    schools, _ = load_artifacts(artifacts_dir)
    schools["schools"] = schools["schools"][:-1]
    broken = _artifacts_with(tmp_path, artifacts_dir, schools=schools)
    with pytest.raises(ExportError, match="truncated"):
        write_dataset(broken, tmp_path / "out", allow_fixture=True)


def test_a_coverage_without_an_integer_profile_count_is_refused(
    artifacts_dir: Path, tmp_path: Path
) -> None:
    _, coverage = load_artifacts(artifacts_dir)
    coverage["profiles"] = "3"
    broken = _artifacts_with(tmp_path, artifacts_dir, coverage=coverage)
    with pytest.raises(ExportError, match="profiles"):
        write_dataset(broken, tmp_path / "out", allow_fixture=True)


def test_a_school_with_no_cds_code_is_refused_rather_than_keyed_by_position(
    artifacts_dir: Path, tmp_path: Path
) -> None:
    schools, _ = load_artifacts(artifacts_dir)
    del schools["schools"][0]["cds_code"]
    broken = _artifacts_with(tmp_path, artifacts_dir, schools=schools)
    with pytest.raises(ExportError, match="cds_code"):
        write_dataset(broken, tmp_path / "out", allow_fixture=True)


def test_a_duplicated_cds_code_is_refused_rather_than_resolved(
    artifacts_dir: Path, tmp_path: Path
) -> None:
    schools, _ = load_artifacts(artifacts_dir)
    schools["schools"][1]["cds_code"] = schools["schools"][0]["cds_code"]
    broken = _artifacts_with(tmp_path, artifacts_dir, schools=schools)
    with pytest.raises(ExportError, match="twice"):
        write_dataset(broken, tmp_path / "out", allow_fixture=True)


def test_an_empty_schools_list_is_refused(artifacts_dir: Path, tmp_path: Path) -> None:
    schools, _ = load_artifacts(artifacts_dir)
    schools["schools"] = []
    broken = _artifacts_with(tmp_path, artifacts_dir, schools=schools)
    with pytest.raises(ExportError, match="no schools"):
        write_dataset(broken, tmp_path / "out", allow_fixture=True)


def test_schools_that_disagree_about_their_measures_are_refused(
    artifacts_dir: Path,
) -> None:
    """A blank column would say "no such measure for this school". It is not that."""
    schools, _ = load_artifacts(artifacts_dir)
    del schools["schools"][1]["grades"]["GR_03"]
    with pytest.raises(ExportError, match="different set of measures"):
        measure_paths(schools["schools"])


def test_schools_json_with_no_schools_list_is_refused(artifacts_dir: Path) -> None:
    with pytest.raises(ExportError, match="`schools` list"):
        build_table({}, is_fixture=True)


def test_a_row_missing_an_identity_column_is_refused(artifacts_dir: Path) -> None:
    schools, _ = load_artifacts(artifacts_dir)
    del schools["schools"][0]["city"]
    with pytest.raises(ExportError, match="has no `city`"):
        build_table(schools, is_fixture=True)


def test_a_reported_cell_with_no_value_is_refused(artifacts_dir: Path) -> None:
    """Refused by ``rendered_state``, which is why ``_value_text`` carries no second
    guard: an unreachable refusal reads as protection and can never fire."""
    schools, _ = load_artifacts(artifacts_dir)
    del schools["schools"][0]["grades"]["GR_01"]["value"]
    with pytest.raises(ExplainError, match="carries no value"):
        build_table(schools, is_fixture=True)


def test_a_null_identity_field_is_written_empty_and_is_not_required(
    artifacts_dir: Path, released: Path
) -> None:
    """CDE leaves directory fields blank, and a blank there is a genuine absence.

    Only the identity columns may be empty, and only because the Table Schema declares
    them nullable. ``cds_code`` is the exception and is ``required``: a row that cannot
    name its school is not a row.
    """
    schools, _ = load_artifacts(artifacts_dir)
    schools["schools"][0]["virtual_code"] = None
    header, table = build_table(schools, is_fixture=True)
    assert table[0][header.index("virtual_code")] == ""

    schema = json.loads((released / "schools.schema.json").read_text(encoding="utf-8"))
    by_name = {field["name"]: field for field in schema["fields"]}
    assert "required" not in by_name["virtual_code"].get("constraints", {})
    assert by_name["cds_code"]["constraints"]["required"] is True


def test_a_source_nobody_supplied_has_no_columns_at_all(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The branch that matters most, and the one the first version left untested.

    A build run without ``--assignments`` has no teacher-assignment cells. Emitting the
    columns and filling them with ``not_reported`` would say CDE published nothing about
    any school's teacher assignments, when the truth is that nobody opened the file.
    ``coverage.json`` states the absence instead, which is a different claim.
    """
    partial = tmp_path_factory.mktemp("partial-artifacts")
    code = artifacts.main(
        [
            "--fixture",
            "--directory",
            str(FIXTURES / "pubschls.sample.txt"),
            "--enrollment",
            str(FIXTURES / "cdenroll.sample.txt"),
            "--absenteeism",
            str(FIXTURES / "chronicabsenteeism.sample.txt"),
            "--out",
            str(partial),
        ]
    )
    assert code == 0

    write_dataset(partial, tmp_path, allow_fixture=True)
    release = tmp_path / "homeroom-dataset-fixture"
    with (release / "schools.csv").open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    assert not [column for column in header if column.startswith("teacher_assignments")]
    # And enrolment, which WAS supplied, is still there -- otherwise this test would
    # pass over a release that dropped every measure column.
    assert [column for column in header if column.startswith("grades.")]

    coverage = json.loads((release / "coverage.json").read_text(encoding="utf-8"))
    assert "D5_teacher_assignments" not in coverage["sources"] or (
        coverage["sources"]["D5_teacher_assignments"].get("supplied") is False
    )


# ----------------------------------------------------------------------------------
# Naming. The date is the dataset's identity, and it comes from the data.
# ----------------------------------------------------------------------------------


def test_a_fixture_release_is_never_given_a_date(artifacts_dir: Path) -> None:
    _, coverage = load_artifacts(artifacts_dir)
    assert dataset_name(coverage, is_fixture=True) == "homeroom-dataset-fixture"


def test_a_real_release_is_named_by_the_latest_access_date() -> None:
    coverage = {
        "sources": {
            "D1_directory": {"access_date": "2026-08-18"},
            "D2_enrollment": {"access_date": "2026-09-01"},
            "D3_chronic_absenteeism": {"access_date": None},
        }
    }
    assert dataset_name(coverage, is_fixture=False) == "homeroom-dataset-2026-09-01"


def test_a_real_release_with_no_access_date_is_refused(artifacts_dir: Path) -> None:
    """The fixture's own coverage has no access dates at all, which is the case."""
    _, coverage = load_artifacts(artifacts_dir)
    with pytest.raises(ExportError, match="access_date"):
        dataset_name(coverage, is_fixture=False)


def test_a_coverage_with_no_sources_object_is_refused() -> None:
    with pytest.raises(ExportError, match="`sources` object"):
        dataset_name({}, is_fixture=False)


# ----------------------------------------------------------------------------------
# The CLI.
# ----------------------------------------------------------------------------------


def test_main_writes_the_release_and_names_what_it_wrote(
    artifacts_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "--artifacts",
            str(artifacts_dir),
            "--out",
            str(tmp_path),
            "--allow-fixture",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "homeroom-dataset-fixture: 3 school(s)" in out
    assert (tmp_path / "homeroom-dataset-fixture" / "schools.csv").is_file()
    assert (tmp_path / "homeroom-dataset-fixture.tar.gz").is_file()


def test_main_reports_a_missing_artifacts_directory_rather_than_crashing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--artifacts", str(tmp_path / "nowhere"), "--out", str(tmp_path)])
    assert code == 2
    assert "does not exist" in capsys.readouterr().err


def test_re_exporting_over_an_existing_release_replaces_it(
    artifacts_dir: Path, tmp_path: Path
) -> None:
    """A stale file left behind would be listed in a manifest that no longer built it."""
    write_dataset(artifacts_dir, tmp_path, allow_fixture=True)
    stale = tmp_path / "homeroom-dataset-fixture" / "schools" / "00000000000000.json"
    stale.write_text("{}", encoding="utf-8")
    write_dataset(artifacts_dir, tmp_path, allow_fixture=True)
    assert not stale.exists()


def test_the_schema_generator_refuses_a_column_it_cannot_describe() -> None:
    with pytest.raises(ExportError, match="no schema field"):
        table_schema(["not_a_column_this_module_knows"])
