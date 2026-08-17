"""Artifacts: byte-identical re-runs, null-never-zero serialization, coverage first."""

import json
from pathlib import Path
from typing import Any

import pytest

from homeroom.artifacts import (
    ASSIGNMENTS_ACCESS_DATE,
    DIRECTORY_ACCESS_DATE,
    ENROLLMENT_ACCESS_DATE,
    build_artifacts,
    main,
    measure_json,
)
from homeroom.assignments import OUTCOMES
from homeroom.measures import Measure

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
DIRECTORY = FIXTURES / "pubschls.sample.txt"
ENROLLMENT = FIXTURES / "cdenroll.sample.txt"
ASSIGNMENTS = FIXTURES / "tamo.sample.txt"


def build(
    tmp_path: Path,
    *,
    is_fixture: bool = True,
    assignments: Path | None = None,
) -> tuple[Path, Path]:
    result = build_artifacts(
        directory=DIRECTORY,
        enrollment=ENROLLMENT,
        assignments=assignments,
        out_dir=tmp_path / "out",
        is_fixture=is_fixture,
    )
    return result.schools_path, result.coverage_path


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def all_measure_dicts(school: dict[str, Any]) -> list[dict[str, Any]]:
    measures = [school["total_enrollment"], *school["grades"].values()]
    for family in school["subgroups"].values():
        measures.extend(family.values())
    return measures


def test_reruns_are_byte_identical(tmp_path: Path) -> None:
    schools_path, coverage_path = build(tmp_path)
    first = (schools_path.read_bytes(), coverage_path.read_bytes())
    build(tmp_path)
    again = (schools_path.read_bytes(), coverage_path.read_bytes())
    assert first == again


def test_measure_serialization_has_value_only_when_reported() -> None:
    assert measure_json(Measure.reported(441)) == {"status": "reported", "value": 441}
    assert measure_json(Measure.reported(42.5)) == {"status": "reported", "value": 42.5}
    assert measure_json(Measure.reported(0)) == {"status": "reported", "value": 0}
    assert measure_json(Measure.suppressed()) == {"status": "suppressed"}
    assert measure_json(Measure.not_reported()) == {"status": "not_reported"}


def test_no_serialized_measure_smuggles_a_number_for_unpublished_cells(
    tmp_path: Path,
) -> None:
    schools_path, _ = build(tmp_path)
    for school in load(schools_path)["schools"]:
        for measure in all_measure_dicts(school):
            if measure["status"] == "reported":
                assert isinstance(measure["value"], int | float)
            else:
                assert "value" not in measure


def test_schools_artifact_shape_and_order(tmp_path: Path) -> None:
    schools_path, _ = build(tmp_path)
    payload = load(schools_path)
    assert payload["academic_year"] == "2025-26"
    codes = [s["cds_code"] for s in payload["schools"]]
    assert codes == sorted(codes)
    assert payload["reporting_categories"]["TA"] == "All students"
    assert payload["reporting_categories"]["RE_H"] == "Hispanic or Latino"
    example = next(s for s in payload["schools"] if s["name"] == "Example Elementary")
    assert example["total_enrollment"] == {"status": "reported", "value": 100}
    assert example["subgroups"]["gender"]["GN_M"] == {"status": "suppressed"}
    assert example["grades"]["GR_12"] == {"status": "not_reported"}
    assert example["subgroups"]["student_groups"]["SG_DS"] == {
        "status": "reported",
        "value": 0,
    }


def test_artifact_exposes_no_complement_of_a_masked_cell(tmp_path: Path) -> None:
    """Suppression fidelity at the artifact boundary: the masked RE_B and GN_M
    complements (7 and 48; see the fixture) must not appear as any value."""
    schools_path, _ = build(tmp_path)
    values = [
        measure["value"]
        for school in load(schools_path)["schools"]
        for measure in all_measure_dicts(school)
        if "value" in measure
    ]
    assert 7 not in values
    assert 48 not in values


def test_coverage_is_first_class(tmp_path: Path) -> None:
    _, coverage_path = build(tmp_path)
    payload = load(coverage_path)
    assert payload["is_fixture"] is True
    assert payload["profiles"] == 3
    assert payload["join_gaps"] == {
        "school_totals_without_directory_match": 2,
        "active_schools_without_enrollment_rows": 1,
        "assignment_rows_without_directory_match": None,
        "active_schools_without_assignment_rows": None,
    }
    assert payload["measures"]["total_enrollment"] == {
        "reported": 1,
        "suppressed": 1,
        "not_reported": 1,
    }
    for counts in (
        payload["measures"]["total_enrollment"],
        *payload["measures"]["grades"].values(),
        *payload["measures"]["subgroups"].values(),
    ):
        assert sum(counts.values()) == payload["profiles"]
    assert payload["measures"]["subgroups"]["SG_HM"]["suppressed"] == 1
    assert payload["measures"]["grades"]["GR_12"]["not_reported"] == 2


def test_fixture_builds_stamp_no_acquisition_dates(tmp_path: Path) -> None:
    _, coverage_path = build(tmp_path)
    sources = load(coverage_path)["sources"]
    assert sources["D1_directory"]["access_date"] is None
    assert sources["D2_enrollment"]["access_date"] is None
    assert sources["D2_enrollment"]["academic_year"] == "2025-26"


def test_real_builds_stamp_provenance_access_dates(tmp_path: Path) -> None:
    _, coverage_path = build(tmp_path, is_fixture=False)
    payload = load(coverage_path)
    assert payload["is_fixture"] is False
    assert payload["sources"]["D1_directory"]["access_date"] == DIRECTORY_ACCESS_DATE
    assert payload["sources"]["D2_enrollment"]["access_date"] == ENROLLMENT_ACCESS_DATE


def test_access_date_constants_match_provenance_record() -> None:
    provenance = (ROOT / "PROVENANCE.md").read_text(encoding="utf-8")
    d1_row = next(line for line in provenance.splitlines() if line.startswith("| D1 |"))
    d2_row = next(line for line in provenance.splitlines() if line.startswith("| D2 |"))
    assert DIRECTORY_ACCESS_DATE in d1_row
    assert ENROLLMENT_ACCESS_DATE in d2_row


def test_unacquired_source_carries_no_access_date_in_either_place() -> None:
    """D5 is parser-built and unacquired. The code constant and the provenance
    record have to say so together, or one of them is lying."""
    d5_row = next(
        line
        for line in (ROOT / "PROVENANCE.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("| D5 |")
    )
    if ASSIGNMENTS_ACCESS_DATE is None:
        assert "awaiting acquisition" in d5_row
    else:
        assert ASSIGNMENTS_ACCESS_DATE in d5_row


# --- D5 teacher assignment outcomes ---------------------------------------


def test_without_the_d5_file_absence_is_stated_not_faked(tmp_path: Path) -> None:
    schools_path, coverage_path = build(tmp_path)
    assert all(
        "teacher_assignments" not in school for school in load(schools_path)["schools"]
    )
    assert "teacher_assignment_outcomes" not in load(schools_path)
    payload = load(coverage_path)
    assert payload["sources"]["D5_teacher_assignments"] == {
        "supplied": False,
        "file": None,
        "access_date": None,
        "academic_year": None,
    }
    assert payload["measures"]["teacher_assignments"] is None


def test_assignment_outcomes_render_every_case(tmp_path: Path) -> None:
    schools_path, _ = build(tmp_path, assignments=ASSIGNMENTS)
    payload = load(schools_path)
    assert payload["teacher_assignment_academic_year"] == "2024-25"
    assert set(payload["teacher_assignment_outcomes"]) == set(OUTCOMES)

    example = next(s for s in payload["schools"] if s["name"] == "Example Elementary")
    block = example["teacher_assignments"]
    assert block["academic_year"] == "2024-25"
    assert block["total_assignments"] == {"status": "reported", "value": 40}
    outcomes = block["outcomes"]
    assert outcomes["clear"] == {
        "count": {"status": "reported", "value": 34},
        "percent": {"status": "reported", "value": 85.0},
    }
    assert outcomes["intern"] == {
        "count": {"status": "reported", "value": 0},
        "percent": {"status": "reported", "value": 0},
    }
    assert outcomes["ineffective"] == {
        "count": {"status": "suppressed"},
        "percent": {"status": "suppressed"},
    }
    assert outcomes["unknown"] == {
        "count": {"status": "not_reported"},
        "percent": {"status": "not_reported"},
    }


def test_a_school_the_file_never_mentions_reads_as_not_reported(
    tmp_path: Path,
) -> None:
    schools_path, _ = build(tmp_path, assignments=ASSIGNMENTS)
    absent = next(
        s for s in load(schools_path)["schools"] if s["name"] == "Sin Datos Middle"
    )
    block = absent["teacher_assignments"]
    assert block["academic_year"] is None
    assert block["total_assignments"] == {"status": "not_reported"}
    for outcome in block["outcomes"].values():
        assert outcome["count"] == {"status": "not_reported"}
        assert outcome["percent"] == {"status": "not_reported"}


def test_assignment_artifact_exposes_no_complement_of_a_masked_cell(
    tmp_path: Path,
) -> None:
    """The withheld outcomes at Example Elementary hold 2 assignments and 5.0
    percent between them. Neither may appear as a published value."""
    schools_path, _ = build(tmp_path, assignments=ASSIGNMENTS)
    values = []
    for school in load(schools_path)["schools"]:
        block = school["teacher_assignments"]
        for measure in (
            block["total_assignments"],
            *(m for o in block["outcomes"].values() for m in o.values()),
        ):
            if "value" in measure:
                values.append(measure["value"])
    assert 2 not in values
    assert 5.0 not in values


def test_assignment_coverage_is_first_class(tmp_path: Path) -> None:
    _, coverage_path = build(tmp_path, assignments=ASSIGNMENTS)
    payload = load(coverage_path)
    assert payload["sources"]["D5_teacher_assignments"] == {
        "supplied": True,
        "file": "tamo.sample.txt",
        "access_date": None,
        "academic_year": "2024-25",
    }
    assert payload["join_gaps"]["assignment_rows_without_directory_match"] == 2
    assert payload["join_gaps"]["active_schools_without_assignment_rows"] == 1

    measures = payload["measures"]["teacher_assignments"]
    # Example reported, charter masked, Sin Datos never mentioned.
    assert measures["total_assignments"] == {
        "reported": 1,
        "suppressed": 1,
        "not_reported": 1,
    }
    for outcome in measures["outcomes"].values():
        for counts in outcome.values():
            assert sum(counts.values()) == payload["profiles"]
    assert measures["outcomes"]["ineffective"]["count"]["suppressed"] == 2
    assert measures["outcomes"]["unknown"]["count"]["not_reported"] == 2


def test_assignment_reruns_are_byte_identical(tmp_path: Path) -> None:
    schools_path, coverage_path = build(tmp_path, assignments=ASSIGNMENTS)
    first = (schools_path.read_bytes(), coverage_path.read_bytes())
    build(tmp_path, assignments=ASSIGNMENTS)
    assert first == (schools_path.read_bytes(), coverage_path.read_bytes())


def test_a_real_build_cannot_stamp_an_unrecorded_acquisition_date(
    tmp_path: Path,
) -> None:
    """The emitted D5 date has to match the record, not the constant.

    Comparing the field to :data:`ASSIGNMENTS_ACCESS_DATE` would be circular:
    that constant is what writes the field, so the assertion could not fail
    whatever either one said. The independent fact is PROVENANCE.md, which is
    where a person records an acquisition, so the expectation is read from
    there. Setting the constant without recording the acquisition fails here.
    """
    d5_row = next(
        line
        for line in (ROOT / "PROVENANCE.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("| D5 |")
    )
    _, coverage_path = build(tmp_path, assignments=ASSIGNMENTS, is_fixture=False)
    source = load(coverage_path)["sources"]["D5_teacher_assignments"]
    if "awaiting acquisition" in d5_row:
        assert source["access_date"] is None
    else:
        assert source["access_date"] is not None
        assert source["access_date"] in d5_row


def test_cli_builds_artifacts_and_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_dir = tmp_path / "out"
    code = main(
        [
            "--directory",
            str(DIRECTORY),
            "--enrollment",
            str(ENROLLMENT),
            "--out",
            str(out_dir),
            "--fixture",
        ]
    )
    assert code == 0
    assert (out_dir / "schools.json").exists()
    assert (out_dir / "coverage.json").exists()
    printed = capsys.readouterr().out
    assert "profiles: 3 (2025-26)" in printed
    assert "join gaps: 2 school totals" in printed
    assert "no D5 file supplied" in printed


def test_cli_reports_assignment_coverage_when_the_file_is_given(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "--directory",
            str(DIRECTORY),
            "--enrollment",
            str(ENROLLMENT),
            "--assignments",
            str(ASSIGNMENTS),
            "--out",
            str(tmp_path / "out"),
            "--fixture",
        ]
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert "teacher assignments: 2024-25" in printed
    assert "reported=1, suppressed=1, not_reported=1" in printed
    assert "1 active schools without rows" in printed
