"""Profile assembly: copied cells only, drift refusal, join gaps as findings."""

from pathlib import Path

import pytest

from homeroom.measures import Measure, MeasureStatus
from homeroom.profiles import (
    CATEGORY_NAMES,
    SUBGROUP_CODES,
    SUBGROUP_FAMILIES,
    ProfileDriftError,
    SchoolProfile,
    assemble_profiles,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
DIRECTORY = FIXTURES / "pubschls.sample.txt"
ENROLLMENT = FIXTURES / "cdenroll.sample.txt"

EXAMPLE = "01100170112345"
CHARTER = "01100170154321"
NO_ENROLLMENT = "01100170176543"

ENROLLMENT_HEADER = (
    "AcademicYear\tAggregateLevel\tCountyCode\tDistrictCode\tSchoolCode\tCountyName"
    "\tDistrictName\tSchoolName\tCharter\tReportingCategory\tTOTAL_ENR\tGR_TK\tGR_KN"
    "\tGR_01\tGR_02\tGR_03\tGR_04\tGR_05\tGR_06\tGR_07\tGR_08\tGR_09\tGR_10\tGR_11\tGR_12\n"
)


def by_cds(cds: str) -> SchoolProfile:
    assembly = assemble_profiles(DIRECTORY, ENROLLMENT)
    return next(p for p in assembly.profiles if p.school.cds_code == cds)


def write_enrollment(tmp_path: Path, rows: str) -> Path:
    path = tmp_path / "cdenroll.txt"
    path.write_text(ENROLLMENT_HEADER + rows, encoding="utf-8")
    return path


def test_one_profile_per_active_school_in_cds_order() -> None:
    assembly = assemble_profiles(DIRECTORY, ENROLLMENT)
    codes = [p.school.cds_code for p in assembly.profiles]
    assert codes == sorted(codes)
    assert set(codes) == {EXAMPLE, CHARTER, NO_ENROLLMENT}
    assert assembly.academic_year == "2025-26"


def test_closed_school_gets_no_profile_even_with_enrollment_rows() -> None:
    assembly = assemble_profiles(DIRECTORY, ENROLLMENT)
    assert "01100170167890" not in {p.school.cds_code for p in assembly.profiles}


def test_reported_total_grades_and_subgroups_are_the_published_cells() -> None:
    profile = by_cds(EXAMPLE)
    assert profile.total_enrollment.number() == 100
    assert profile.grades["GR_TK"].number() == 12
    assert profile.subgroups["RE_H"].number() == 63
    assert profile.subgroups["ELAS_EL"].number() == 22


def test_genuine_zero_stays_zero_and_reported() -> None:
    profile = by_cds(EXAMPLE)
    assert profile.grades["GR_07"].is_zero
    assert profile.subgroups["SG_DS"].is_zero
    assert profile.subgroups["SG_DS"].status is MeasureStatus.REPORTED


def test_suppressed_cells_stay_suppressed_never_zero() -> None:
    profile = by_cds(EXAMPLE)
    for code in ("RE_B", "GN_M", "SG_HM"):
        assert profile.subgroups[code].status is MeasureStatus.SUPPRESSED
        assert not profile.subgroups[code].is_zero
    charter = by_cds(CHARTER)
    assert charter.total_enrollment.status is MeasureStatus.SUPPRESSED
    assert all(m.status is MeasureStatus.SUPPRESSED for m in charter.grades.values())


def test_not_reported_cell_differs_from_suppressed() -> None:
    profile = by_cds(EXAMPLE)
    assert profile.grades["GR_12"].status is MeasureStatus.NOT_REPORTED
    assert profile.subgroups["RE_A"].status is MeasureStatus.NOT_REPORTED


def test_school_absent_from_enrollment_is_not_reported_everywhere() -> None:
    profile = by_cds(NO_ENROLLMENT)
    measures = [profile.total_enrollment, *profile.grades.values()]
    measures.extend(profile.subgroups.values())
    assert all(m.status is MeasureStatus.NOT_REPORTED for m in measures)


def test_join_gaps_are_counted_in_both_directions() -> None:
    assembly = assemble_profiles(DIRECTORY, ENROLLMENT)
    # Birch Lane (never in the directory fixture) and Shuttered School (closed).
    assert assembly.unjoined_school_totals == 2
    # Sin Datos Middle is active but the enrollment fixture never mentions it.
    assert assembly.schools_without_enrollment == 1


def test_no_value_is_ever_derived_from_complements() -> None:
    """The pre-M3 suppression-fidelity rule (ADR 0000, audits C).

    In the fixture, Example Elementary publishes a total of 100 with RE_B masked
    beside visible 63 and 30, and GN_M masked beside visible 52. The arithmetic
    complements (7 and 48) appear nowhere in the source file, so if any measure
    reports them, assembly computed a value CDE suppressed.
    """
    assembly = assemble_profiles(DIRECTORY, ENROLLMENT)
    reported: list[float] = []
    for profile in assembly.profiles:
        for measure in (
            profile.total_enrollment,
            *profile.grades.values(),
            *profile.subgroups.values(),
        ):
            if measure.status is MeasureStatus.REPORTED:
                reported.append(measure.number())
    assert 7 not in reported
    assert 48 not in reported


def test_every_reported_value_is_verbatim_in_the_source_file() -> None:
    """Stronger form of the no-derivation rule: profiles copy cells, never compute."""
    published = set()
    for line in ENROLLMENT.read_text(encoding="utf-8").splitlines()[1:]:
        for cell in line.split("\t"):
            try:
                published.add(float(cell))
            except ValueError:
                continue
    assembly = assemble_profiles(DIRECTORY, ENROLLMENT)
    for profile in assembly.profiles:
        for measure in (
            profile.total_enrollment,
            *profile.grades.values(),
            *profile.subgroups.values(),
        ):
            if measure.status is MeasureStatus.REPORTED:
                assert measure.number() in published


def test_subgroup_families_cover_exactly_the_profiled_codes() -> None:
    assert len(SUBGROUP_CODES) == len(set(SUBGROUP_CODES))
    assert set(SUBGROUP_CODES) <= set(CATEGORY_NAMES)
    assert all(CATEGORY_NAMES[code].strip() for code in CATEGORY_NAMES)
    families = list(SUBGROUP_FAMILIES)
    assert families == [
        "race_ethnicity",
        "gender",
        "english_language_acquisition",
        "student_groups",
    ]


def test_age_categories_are_recognized_but_not_subgroups() -> None:
    assert "AR_0418" in CATEGORY_NAMES
    assert "AR_0418" not in SUBGROUP_CODES
    profile = by_cds(EXAMPLE)
    assert "AR_0418" not in profile.subgroups


def test_unreviewed_category_code_is_drift(tmp_path: Path) -> None:
    path = write_enrollment(
        tmp_path,
        "2025-26\tS\t01\t10017\t0112345\tYolo\tD\tS\tN\tRE_Q\t5\t"
        + "\t".join(["0"] * 14)
        + "\n",
    )
    with pytest.raises(ProfileDriftError, match="no reviewed display name"):
        assemble_profiles(DIRECTORY, path)


def test_duplicate_category_row_for_a_school_is_drift(tmp_path: Path) -> None:
    row = (
        "2025-26\tS\t01\t10017\t0112345\tYolo\tD\tS\tN\tTA\t5\t"
        + "\t".join(["0"] * 14)
        + "\n"
    )
    path = write_enrollment(tmp_path, row + row)
    with pytest.raises(ProfileDriftError, match="two 'TA' rows"):
        assemble_profiles(DIRECTORY, path)


def test_mixed_academic_years_are_drift(tmp_path: Path) -> None:
    grades = "\t".join(["0"] * 14)
    path = write_enrollment(
        tmp_path,
        f"2025-26\tS\t01\t10017\t0112345\tYolo\tD\tS\tN\tTA\t5\t{grades}\n"
        f"2024-25\tS\t01\t10017\t0154321\tYolo\tD\tS\tN\tTA\t5\t{grades}\n",
    )
    with pytest.raises(ProfileDriftError, match="academic years"):
        assemble_profiles(DIRECTORY, path)


def test_duplicate_active_cds_in_directory_is_drift(tmp_path: Path) -> None:
    header = "CDSCode\tStatusType\tCounty\tDistrict\tSchool\tCity\tCharter\tVirtual\tGSserved\n"
    row = "01100170112345\tActive\tYolo\tD\tTwin School\tDavis\tN\tN\tK-6\n"
    directory = tmp_path / "pubschls.txt"
    directory.write_text(header + row + row, encoding="utf-8")
    with pytest.raises(ProfileDriftError, match="appears twice"):
        assemble_profiles(directory, ENROLLMENT)


def test_profiles_carry_the_full_subgroup_roster_always() -> None:
    for profile in assemble_profiles(DIRECTORY, ENROLLMENT).profiles:
        assert tuple(profile.subgroups) == SUBGROUP_CODES
        assert all(isinstance(m, Measure) for m in profile.subgroups.values())
