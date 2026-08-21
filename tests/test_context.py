"""District and statewide context: the ALL row, never a sum, and failing closed.

The regression this file exists for is at the top. Everything after it guards the
same promise from a different side: a context figure is a number California
published for that entity, or it is one of the three non-numbers, and it is never
assembled by Homeroom out of school rows.
"""

from pathlib import Path

import pytest

from homeroom.context import (
    AbsenteeismContextDriftError,
    ContextDriftError,
    district_key,
    load_absenteeism_context,
    load_context,
)
from homeroom.enrollment import EnrollmentDriftError, parse_enrollment, school_totals
from homeroom.measures import MeasureStatus, SuppressedValueError

HEADER = (
    "AcademicYear\tAggregateLevel\tCountyCode\tDistrictCode\tSchoolCode\tCountyName"
    "\tDistrictName\tSchoolName\tCharter\tReportingCategory\tTOTAL_ENR\tGR_TK\tGR_KN"
    "\tGR_01\tGR_02\tGR_03\tGR_04\tGR_05\tGR_06\tGR_07\tGR_08\tGR_09\tGR_10\tGR_11\tGR_12\n"
)

GRADES = "\t".join(["0"] * 14)


def row(
    *,
    level: str,
    charter: str,
    category: str,
    total: str,
    county: str = "57",
    district: str = "72678",
    school: str = "",
    year: str = "2025-26",
) -> str:
    return (
        f"{year}\t{level}\t{county}\t{district}\t{school}\tYolo\tDavis Joint Unified"
        f"\tBirch Lane\t{charter}\t{category}\t{total}\t{GRADES}\n"
    )


def write(tmp_path: Path, rows: str) -> Path:
    p = tmp_path / "cdenroll.txt"
    p.write_text(HEADER + rows, encoding="utf-8")
    return p


STATE_TA = row(
    level="T", charter="ALL", category="TA", total="5731260", county="00", district=""
)


def test_district_context_is_the_all_row_not_the_first_row_that_matches(
    tmp_path: Path,
) -> None:
    """The one that would have shipped a district figure fifteen times too small.

    CDE publishes every district three times: charter, non-charter, and both. In
    the acquired 2025-26 file Davis Joint Unified reads 561 / 7,682 / 8,243 for
    the same category, and the charter row comes first. Selecting by anything
    other than ``Charter == ALL`` picks a real, plausible, wrong number that no
    downstream check would flag, because it is a number the state did publish.
    """
    p = write(
        tmp_path,
        row(level="D", charter="Y", category="TA", total="561")
        + row(level="D", charter="N", category="TA", total="7682")
        + row(level="D", charter="ALL", category="TA", total="8243")
        + STATE_TA,
    )
    district = load_context(p).for_district("57726786056246")
    assert district.total.number() == 8243
    assert district.total.number() not in (561, 7682)


def test_context_never_sums_school_rows(tmp_path: Path) -> None:
    """No arithmetic over schools, even when the schools would sum to something.

    Two schools totalling 300 sit under a district whose published ALL row says
    450. The gap is the point: the district row counts schools this file does not
    list and students whose cells are masked. Homeroom publishes 450, the state's
    own figure, and never 300.
    """
    p = write(
        tmp_path,
        row(level="S", charter="N", category="TA", total="100", school="0000001")
        + row(level="S", charter="N", category="TA", total="200", school="0000002")
        + row(level="D", charter="ALL", category="TA", total="450")
        + STATE_TA,
    )
    assert load_context(p).for_district("57726780000001").total.number() == 450


def test_masked_district_and_state_cells_stay_withheld(tmp_path: Path) -> None:
    p = write(
        tmp_path,
        row(level="D", charter="ALL", category="SG_HM", total="*")
        + row(
            level="T",
            charter="ALL",
            category="SG_HM",
            total="*",
            county="00",
            district="",
        )
        + row(level="D", charter="ALL", category="TA", total="450")
        + STATE_TA,
    )
    ctx = load_context(p)
    for measure in (
        ctx.for_district("57726786056246").subgroup("SG_HM"),
        ctx.state.subgroup("SG_HM"),
    ):
        assert measure.status is MeasureStatus.SUPPRESSED
        assert not measure.is_zero
        with pytest.raises(SuppressedValueError):
            measure.number()


def test_absent_category_is_nothing_published_not_zero(tmp_path: Path) -> None:
    p = write(
        tmp_path, row(level="D", charter="ALL", category="TA", total="450") + STATE_TA
    )
    ctx = load_context(p)
    absent = ctx.for_district("57726786056246").subgroup("RE_W")
    assert absent.status is MeasureStatus.NOT_REPORTED
    assert not absent.is_zero
    assert ctx.state.subgroup("RE_W").status is MeasureStatus.NOT_REPORTED


def test_district_with_no_published_rows_is_absent_not_invented(
    tmp_path: Path,
) -> None:
    p = write(tmp_path, STATE_TA)
    district = load_context(p).for_district("57726786056246")
    assert district.total.status is MeasureStatus.NOT_REPORTED
    assert district.cds_code == district_key("57726786056246")


def test_duplicate_all_rows_are_drift_not_last_one_wins(tmp_path: Path) -> None:
    """Two ALL rows for one entity would make file order pick the number."""
    p = write(
        tmp_path,
        row(level="D", charter="ALL", category="TA", total="450")
        + row(level="D", charter="ALL", category="TA", total="451")
        + STATE_TA,
    )
    with pytest.raises(ContextDriftError, match="more than one"):
        load_context(p)


def test_missing_statewide_total_is_drift(tmp_path: Path) -> None:
    p = write(tmp_path, row(level="D", charter="ALL", category="TA", total="450"))
    with pytest.raises(ContextDriftError, match="no statewide"):
        load_context(p)


def test_aggregate_rows_spanning_two_years_are_drift(tmp_path: Path) -> None:
    p = write(
        tmp_path,
        STATE_TA
        + row(
            level="D",
            charter="ALL",
            category="TA",
            total="450",
            year="2024-25",
        ),
    )
    with pytest.raises(ContextDriftError, match="academic years"):
        load_context(p)


def test_unknown_charter_value_is_drift(tmp_path: Path) -> None:
    """Charter is what tells aggregate rows apart, so an unreviewed value stops."""
    p = write(tmp_path, row(level="D", charter="MAYBE", category="TA", total="450"))
    with pytest.raises(EnrollmentDriftError, match="Charter"):
        list(parse_enrollment(p))


def test_duplicate_school_total_rows_are_drift(tmp_path: Path) -> None:
    p = write(
        tmp_path,
        row(level="S", charter="N", category="TA", total="100", school="0000001")
        + row(level="S", charter="Y", category="TA", total="900", school="0000001"),
    )
    with pytest.raises(EnrollmentDriftError, match="more than one school-level"):
        school_totals(p)


def test_county_rows_are_not_mistaken_for_districts(tmp_path: Path) -> None:
    """County rows share the ALL charter value and must not become context."""
    p = write(
        tmp_path,
        row(level="C", charter="ALL", category="TA", total="99999", district="")
        + row(level="D", charter="ALL", category="TA", total="450")
        + STATE_TA,
    )
    ctx = load_context(p)
    assert ctx.for_district("57726786056246").total.number() == 450
    assert all(f.total.number() != 99999 for f in ctx.districts.values())


# --- D3 chronic absenteeism context: two independent All/Yes/No dimensions ------

ABD_HEADER = (
    "Academic Year\tAggregate Level\tCounty Code\tDistrict Code\tSchool Code"
    "\tCounty Name\tDistrict Name\tSchool Name\tCharter School\tDASS"
    "\tReporting Category\tChronicAbsenteeismEligibleCumulativeEnrollment"
    "\tChronicAbsenteeismCount\tChronicAbsenteeismRate\n"
)


def abd_row(
    *,
    level: str,
    charter: str,
    dass: str,
    category: str,
    rate: str,
    county: str = "01",
    district: str = "10017",
    school: str = "",
    year: str = "2024-25",
) -> str:
    return (
        f"{year}\t{level}\t{county}\t{district}\t{school}\tYolo\tDavis Joint Unified"
        f"\tBirch Lane\t{charter}\t{dass}\t{category}\t100\t10\t{rate}\n"
    )


def write_abd(tmp_path: Path, rows: str) -> Path:
    p = tmp_path / "chronicabsenteeism.txt"
    p.write_text(ABD_HEADER + rows, encoding="utf-8")
    return p


ABD_STATE_TA = abd_row(
    level="T",
    charter="All",
    dass="All",
    category="TA",
    rate="19.0",
    county="00",
    district="",
)


def test_absenteeism_context_requires_both_charter_and_dass_all(
    tmp_path: Path,
) -> None:
    """D3 crosses two independent dimensions; only Charter=All AND DASS=All is
    the genuine district-wide rate, the same failure mode D2's own Charter=ALL
    test guards from the other direction."""
    p = write_abd(
        tmp_path,
        abd_row(level="D", charter="Yes", dass="All", category="TA", rate="5.0")
        + abd_row(level="D", charter="No", dass="All", category="TA", rate="12.0")
        + abd_row(level="D", charter="All", dass="Yes", category="TA", rate="30.0")
        + abd_row(level="D", charter="All", dass="All", category="TA", rate="11.0")
        + ABD_STATE_TA,
    )
    district = load_absenteeism_context(p).for_district("01100170112345")
    assert district.category("TA").number() == 11.0
    assert district.category("TA").number() not in (5.0, 12.0, 30.0)


def test_absenteeism_context_never_sums_school_rows(tmp_path: Path) -> None:
    p = write_abd(
        tmp_path,
        abd_row(
            level="S",
            charter="No",
            dass="No",
            category="TA",
            rate="10.0",
            school="0000001",
        )
        + abd_row(
            level="S",
            charter="No",
            dass="No",
            category="TA",
            rate="20.0",
            school="0000002",
        )
        + abd_row(level="D", charter="All", dass="All", category="TA", rate="11.0")
        + ABD_STATE_TA,
    )
    assert (
        load_absenteeism_context(p)
        .for_district("01100170000001")
        .category("TA")
        .number()
        == 11.0
    )


def test_absenteeism_masked_district_and_state_rates_stay_withheld(
    tmp_path: Path,
) -> None:
    p = write_abd(
        tmp_path,
        abd_row(level="D", charter="All", dass="All", category="RB", rate="*")
        + abd_row(
            level="T",
            charter="All",
            dass="All",
            category="RB",
            rate="*",
            county="00",
            district="",
        )
        + abd_row(level="D", charter="All", dass="All", category="TA", rate="11.0")
        + ABD_STATE_TA,
    )
    ctx = load_absenteeism_context(p)
    for measure in (
        ctx.for_district("01100170112345").category("RB"),
        ctx.state.category("RB"),
    ):
        assert measure.status is MeasureStatus.SUPPRESSED
        assert not measure.is_zero
        with pytest.raises(SuppressedValueError):
            measure.number()


def test_absenteeism_absent_category_is_nothing_published_not_zero(
    tmp_path: Path,
) -> None:
    p = write_abd(
        tmp_path,
        abd_row(level="D", charter="All", dass="All", category="TA", rate="11.0")
        + ABD_STATE_TA,
    )
    ctx = load_absenteeism_context(p)
    absent = ctx.for_district("01100170112345").category("RW")
    assert absent.status is MeasureStatus.NOT_REPORTED
    assert not absent.is_zero


def test_absenteeism_duplicate_all_rows_are_drift(tmp_path: Path) -> None:
    p = write_abd(
        tmp_path,
        abd_row(level="D", charter="All", dass="All", category="TA", rate="11.0")
        + abd_row(level="D", charter="All", dass="All", category="TA", rate="12.0")
        + ABD_STATE_TA,
    )
    with pytest.raises(AbsenteeismContextDriftError, match="more than one"):
        load_absenteeism_context(p)


def test_absenteeism_missing_statewide_total_is_drift(tmp_path: Path) -> None:
    p = write_abd(
        tmp_path,
        abd_row(level="D", charter="All", dass="All", category="TA", rate="11.0"),
    )
    with pytest.raises(AbsenteeismContextDriftError, match="no statewide"):
        load_absenteeism_context(p)


def test_absenteeism_aggregate_rows_spanning_two_years_are_drift(
    tmp_path: Path,
) -> None:
    p = write_abd(
        tmp_path,
        ABD_STATE_TA
        + abd_row(
            level="D",
            charter="All",
            dass="All",
            category="TA",
            rate="11.0",
            year="2023-24",
        ),
    )
    with pytest.raises(AbsenteeismContextDriftError, match="academic years"):
        load_absenteeism_context(p)
