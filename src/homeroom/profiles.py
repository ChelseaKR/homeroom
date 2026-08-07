"""Assemble one profile per active school from the spine and Census Day enrollment.

A :class:`SchoolProfile` is the unit the future pages render: directory identity,
the academic year, total enrollment, per-grade enrollment, and subgroup enrollment,
every value a :class:`homeroom.measures.Measure` so suppression survives assembly.

Suppression fidelity (ADR 0000, and the pre-M3 privacy commitment in
docs/RESPONSIBLE-TECH-AUDITS.md): every published value in a profile is exactly a
cell CDE published. Nothing here subtracts visible subgroups from a total, sums
grades into a total, or otherwise derives a value a masked cell was protecting.
A profile copies cells; it never computes them.

Reporting categories: the acquired 2025-26 file carries exactly the 33 codes named
in :data:`CATEGORY_NAMES`, reviewed against CDE's file structure page
(https://www.cde.ca.gov/ds/ad/fsenrcensus.asp, checked 2026-08-07). Display names
follow CDE's labels, sentence-cased, with ambiguous labels ("Not Reported",
"Missing") expanded so they cannot be confused with a measure status. Profiles
carry the four subgroup families (race/ethnicity ``RE_``, gender ``GN_``, English
language acquisition ``ELAS_``, student groups ``SG_``); the age-range ``AR_``
codes and the ``TA`` total are recognized but are not subgroup measures. A code
outside :data:`CATEGORY_NAMES` in source data is upstream drift and fails the
build; it is never silently passed through or guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from homeroom.directory import School, active_schools
from homeroom.enrollment import (
    GRADE_COLUMNS,
    SCHOOL_LEVEL,
    TOTAL_CATEGORY,
    EnrollmentRow,
    parse_enrollment,
)
from homeroom.measures import Measure

CATEGORY_NAMES: dict[str, str] = {
    "TA": "All students",
    # Race/ethnicity. CDE's label for RE_D is "Not Reported"; expanded here so it
    # cannot be read as the not_reported measure status.
    "RE_A": "Asian",
    "RE_B": "African American",
    "RE_D": "Race or ethnicity not reported",
    "RE_F": "Filipino",
    "RE_H": "Hispanic or Latino",
    "RE_I": "American Indian or Alaska Native",
    "RE_P": "Pacific Islander",
    "RE_T": "Two or more races",
    "RE_W": "White",
    # Gender.
    "GN_F": "Female",
    "GN_M": "Male",
    "GN_X": "Non-binary",
    # English language acquisition status. CDE's label for ELAS_MISS is "Missing";
    # expanded for the same reason as RE_D.
    "ELAS_ADEL": "Adult English learner",
    "ELAS_EL": "English learner",
    "ELAS_EO": "English only",
    "ELAS_IFEP": "Initial fluent English proficient",
    "ELAS_MISS": "English language acquisition status missing",
    "ELAS_RFEP": "Reclassified fluent English proficient",
    "ELAS_TBD": "To be determined",
    # Student groups.
    "SG_DS": "Students with disabilities",
    "SG_EL": "English learners",
    "SG_FS": "Foster youth",
    "SG_HM": "Homeless youth",
    "SG_MG": "Migrant youth",
    "SG_SD": "Socioeconomically disadvantaged",
    # Age ranges: recognized so real data parses, not carried as profile subgroups.
    "AR_03": "Ages 0 to 3",
    "AR_0418": "Ages 4 to 18",
    "AR_1922": "Ages 19 to 22",
    "AR_2329": "Ages 23 to 29",
    "AR_3039": "Ages 30 to 39",
    "AR_4049": "Ages 40 to 49",
    "AR_50P": "Ages 50 and over",
}
"""EN display name for every ReportingCategory code observed in the acquired file."""

SUBGROUP_FAMILIES: dict[str, tuple[str, ...]] = {
    "race_ethnicity": (
        "RE_A",
        "RE_B",
        "RE_D",
        "RE_F",
        "RE_H",
        "RE_I",
        "RE_P",
        "RE_T",
        "RE_W",
    ),
    "gender": ("GN_F", "GN_M", "GN_X"),
    "english_language_acquisition": (
        "ELAS_ADEL",
        "ELAS_EL",
        "ELAS_EO",
        "ELAS_IFEP",
        "ELAS_MISS",
        "ELAS_RFEP",
        "ELAS_TBD",
    ),
    "student_groups": ("SG_DS", "SG_EL", "SG_FS", "SG_HM", "SG_MG", "SG_SD"),
}
"""The subgroup families a profile carries, keyed by artifact family name."""

SUBGROUP_CODES: tuple[str, ...] = tuple(
    code for family in SUBGROUP_FAMILIES.values() for code in family
)


class ProfileDriftError(ValueError):
    """Source data no longer matches what profile assembly was verified against."""


@dataclass(frozen=True)
class SchoolProfile:
    """Everything M3a knows about one active school. Every value is a Measure."""

    school: School
    academic_year: str
    total_enrollment: Measure
    grades: dict[str, Measure]
    subgroups: dict[str, Measure]


@dataclass(frozen=True)
class ProfileAssembly:
    """The profiles plus the join gaps, which are findings to publish, not noise."""

    academic_year: str
    profiles: list[SchoolProfile]
    unjoined_school_totals: int
    schools_without_enrollment: int


def _spine(directory_path: Path) -> dict[str, School]:
    spine: dict[str, School] = {}
    for school in active_schools(directory_path):
        if school.cds_code in spine:
            raise ProfileDriftError(
                f"{directory_path.name}: CDS code {school.cds_code} appears twice "
                "among active schools; refusing to build profiles on an ambiguous spine"
            )
        spine[school.cds_code] = school
    return spine


def _school_rows(
    enrollment_path: Path,
) -> tuple[str, dict[str, dict[str, EnrollmentRow]]]:
    """School-level rows keyed by CDS code then category, plus the academic year."""
    years: set[str] = set()
    by_school: dict[str, dict[str, EnrollmentRow]] = {}
    for row in parse_enrollment(enrollment_path):
        if row.category not in CATEGORY_NAMES:
            raise ProfileDriftError(
                f"{enrollment_path.name}: ReportingCategory {row.category!r} has no "
                "reviewed display name; upstream added a code this project has not "
                "reviewed, so the build stops rather than guessing"
            )
        years.add(row.academic_year)
        if row.level != SCHOOL_LEVEL:
            continue
        rows = by_school.setdefault(row.cds_code, {})
        if row.category in rows:
            raise ProfileDriftError(
                f"{enrollment_path.name}: CDS {row.cds_code} carries two "
                f"{row.category!r} rows; the one-row-per-category layout changed"
            )
        rows[row.category] = row
    if len(years) != 1:
        raise ProfileDriftError(
            f"{enrollment_path.name} carries academic years {sorted(years)}; "
            "profile assembly was verified against exactly one"
        )
    return years.pop(), by_school


def _profile(
    school: School, rows: dict[str, EnrollmentRow], academic_year: str
) -> SchoolProfile:
    """Copy published cells onto a profile. Absent rows are not reported, because
    the state published nothing; they are never filled in from arithmetic."""
    total_row = rows.get(TOTAL_CATEGORY)
    return SchoolProfile(
        school=school,
        academic_year=academic_year,
        total_enrollment=(total_row.total if total_row else Measure.not_reported()),
        grades=(
            dict(total_row.grades)
            if total_row
            else {grade: Measure.not_reported() for grade in GRADE_COLUMNS}
        ),
        subgroups={
            code: rows[code].total if code in rows else Measure.not_reported()
            for code in SUBGROUP_CODES
        },
    )


def assemble_profiles(directory_path: Path, enrollment_path: Path) -> ProfileAssembly:
    """One profile per active school, in CDS order, with join gaps counted.

    The gap runs both ways and both directions are published: school-level
    enrollment totals whose CDS matches no active school (closed schools still
    reporting, or spine lag), and active schools the enrollment file never
    mentions.
    """
    spine = _spine(directory_path)
    academic_year, by_school = _school_rows(enrollment_path)
    profiles = [
        _profile(spine[cds], by_school.get(cds, {}), academic_year)
        for cds in sorted(spine)
    ]
    unjoined = sum(
        1
        for cds, rows in by_school.items()
        if TOTAL_CATEGORY in rows and cds not in spine
    )
    without = sum(1 for cds in spine if cds not in by_school)
    return ProfileAssembly(
        academic_year=academic_year,
        profiles=profiles,
        unjoined_school_totals=unjoined,
        schools_without_enrollment=without,
    )
