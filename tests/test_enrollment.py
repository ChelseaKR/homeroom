"""Enrollment parsing: CDS assembly, suppression survival, drift refusal."""

from pathlib import Path

import pytest

from homeroom.enrollment import (
    EnrollmentDriftError,
    parse_enrollment,
    school_totals,
)
from homeroom.measures import MeasureStatus

HEADER = (
    "AcademicYear\tAggregateLevel\tCountyCode\tDistrictCode\tSchoolCode\tCountyName"
    "\tDistrictName\tSchoolName\tCharter\tReportingCategory\tTOTAL_ENR\tGR_TK\tGR_KN"
    "\tGR_01\tGR_02\tGR_03\tGR_04\tGR_05\tGR_06\tGR_07\tGR_08\tGR_09\tGR_10\tGR_11\tGR_12\n"
)


def write(tmp_path: Path, rows: str) -> Path:
    p = tmp_path / "cdenroll.txt"
    p.write_text(HEADER + rows, encoding="utf-8")
    return p


def test_school_total_row_parses_with_assembled_cds(tmp_path: Path) -> None:
    p = write(
        tmp_path,
        "2025-26\tS\t57\t72678\t6056246\tYolo\tDavis Joint Unified\tBirch Lane Elementary"
        "\tN\tTA\t441\t28\t55\t60\t58\t62\t59\t61\t58\t0\t0\t0\t0\t0\t0\n",
    )
    totals = school_totals(p)
    # Spelled out rather than compared against a dict built from `totals`
    # itself, which is an assertion that cannot fail.
    assert list(totals) == ["57726786056246"]
    assert totals["57726786056246"].number() == 441


def test_masked_cells_stay_suppressed_never_zero(tmp_path: Path) -> None:
    p = write(
        tmp_path,
        "2025-26\tS\t57\t72678\t6056246\tYolo\tDavis\tBirch\tN\tSG_HM\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\t*\n",
    )
    row = next(parse_enrollment(p))
    assert row.total.status is MeasureStatus.SUPPRESSED
    assert not row.total.is_zero
    assert all(m.status is MeasureStatus.SUPPRESSED for m in row.grades.values())


def test_a_school_code_that_will_not_make_a_cds_refuses_rather_than_joins(
    tmp_path: Path,
) -> None:
    """The join key is the only thing tying this file to the directory spine.

    A code the parser cannot assemble into 14 digits has to stop the build. Left
    to pad and truncate it would join a real school's enrollment onto whatever
    CDS the mangled key happened to land on, which is the one mistake this
    project can make that puts a wrong number under a real school's name.
    """
    p = write(
        tmp_path,
        "2025-26\tS\t5X\t72678\t6056246\tYolo\tDavis\tBirch\tN\tTA\t441\t"
        + "\t".join(["0"] * 14)
        + "\n",
    )
    with pytest.raises(EnrollmentDriftError, match="cannot assemble a 14-digit CDS"):
        list(parse_enrollment(p))


def test_unknown_aggregate_level_refuses(tmp_path: Path) -> None:
    p = write(
        tmp_path,
        "2025-26\tX\t57\t72678\t6056246\tY\tD\tS\tN\tTA\t1\t"
        + "\t".join(["0"] * 14)
        + "\n",
    )
    with pytest.raises(EnrollmentDriftError, match="not one this parser reviewed"):
        list(parse_enrollment(p))


def test_missing_grade_column_is_drift(tmp_path: Path) -> None:
    p = tmp_path / "cdenroll.txt"
    p.write_text(
        "AcademicYear\tAggregateLevel\tTOTAL_ENR\n2025-26\tS\t5\n", encoding="utf-8"
    )
    with pytest.raises(EnrollmentDriftError, match="missing required columns"):
        list(parse_enrollment(p))
