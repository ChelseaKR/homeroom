"""Assemble one profile per active school from the spine and the measure files.

A :class:`SchoolProfile` is the unit the future pages render: directory identity,
the academic year, total enrollment, per-grade enrollment, subgroup enrollment,
and, when the D5 file is supplied, that school's published teacher assignment
outcomes, every value a :class:`homeroom.measures.Measure` so suppression survives
assembly.

Each source keeps its own academic year. Teacher assignment monitoring reports on
a different cycle than Census Day enrollment, so a profile carries both years
rather than one label over data from two calendars.

Suppression fidelity (ADR 0002, and the pre-M3 privacy commitment in
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

from homeroom.absenteeism import SCHOOL_LEVEL as ABSENTEEISM_SCHOOL_LEVEL
from homeroom.absenteeism import TOTAL_CATEGORY as ABSENTEEISM_TOTAL_CATEGORY
from homeroom.absenteeism import AbsenteeismRow, parse_absenteeism
from homeroom.assignments import AssignmentRow, school_outcomes
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

ABSENTEEISM_CATEGORY_NAMES: dict[str, str] = {
    "TA": "All students",
    # Race/ethnicity. CDE's own file structure page (fsabd.asp) labels RD
    # "Did not Report"; expanded here for the same reason D2's RE_D is, so it
    # cannot be read as the not_reported measure status.
    "RA": "Asian",
    "RB": "African American",
    "RD": "Race or ethnicity not reported",
    "RF": "Filipino",
    "RH": "Hispanic or Latino",
    "RI": "American Indian or Alaska Native",
    "RP": "Pacific Islander",
    "RT": "Two or more races",
    "RW": "White",
    # Gender. GZ ("Missing Gender" in CDE's documentation) is not in this set:
    # it never appeared in the acquired 2024-25 file (25 categories observed,
    # none of them GZ), and this project adds a code only once it has been seen
    # in an acquired file, the same rule D2's CATEGORY_NAMES follows. A future
    # year publishing GZ is drift, correctly: it stops the build for review
    # rather than silently carrying an unreviewed code through.
    "GF": "Female",
    "GM": "Male",
    "GX": "Non-binary",
    # Student groups.
    "SD": "Students with disabilities",
    "SE": "English learners",
    "SF": "Foster youth",
    "SH": "Homeless youth",
    "SM": "Migrant youth",
    "SS": "Socioeconomically disadvantaged",
    # Grade spans: recognized so real data parses without drift, but not
    # rendered as a subgroup measure (see ABSENTEEISM_SUBGROUP_FAMILIES below),
    # the same treatment D2's age-range AR_* codes get.
    "GRTKKN": "Grades TK-K",
    "GR13": "Grades 1-3",
    "GR46": "Grades 4-6",
    "GR78": "Grades 7-8",
    "GRTK8": "Grades TK/K-8",
    "GR912": "Grades 9-12",
}
"""EN display name for every D3 reporting-category code observed in the acquired
2024-25 chronic absenteeism file (25 codes, counted 2026-08-21; PROVENANCE.md D3).
These are CDE's own codes for this file, distinct from D2's ``RE_*``/``GN_*``/``SG_*``
codes for the same underlying groups (D2's ``RE_A`` is this file's ``RA``): the two
files were built by different parts of CDE and never share a code."""

ABSENTEEISM_SUBGROUP_FAMILIES: dict[str, tuple[str, ...]] = {
    "race_ethnicity": ("RA", "RB", "RD", "RF", "RH", "RI", "RP", "RT", "RW"),
    "gender": ("GF", "GM", "GX"),
    "student_groups": ("SD", "SE", "SF", "SH", "SM", "SS"),
}
"""The D3 subgroup families a profile renders, keyed by artifact family name. Grade
spans (``GRTKKN``...``GR912``) are recognized in :data:`ABSENTEEISM_CATEGORY_NAMES`
but not rendered as a subgroup here, the same treatment D2 gives ``AR_*``."""

ABSENTEEISM_SUBGROUP_CODES: tuple[str, ...] = tuple(
    code for family in ABSENTEEISM_SUBGROUP_FAMILIES.values() for code in family
)


class ProfileDriftError(ValueError):
    """Source data no longer matches what profile assembly was verified against."""


@dataclass(frozen=True)
class SchoolProfile:
    """Everything Homeroom knows about one active school. Every value is a Measure.

    ``teacher_assignments`` is ``None`` when the D5 file was not supplied to this
    build. That is a different fact from a school the file covers with everything
    withheld, and the two never collapse: the first says Homeroom has no source,
    the second says the state published a mask. There is a third fact between
    them -- the file was supplied and never mentions this school -- which is also
    ``None`` here, because whether a D5 source was supplied at all is recorded
    once, on ``ProfileAssembly.assignments_academic_year``, rather than repeated
    on every profile. All three reach a page as different words (ADR 0005): no
    source renders no section and says so, no row renders "no figure published",
    and a mask renders "withheld to protect privacy". None of the three ever
    renders a digit it does not have.

    ``chronic_absenteeism_rate`` and ``chronic_absenteeism_subgroups`` are always
    ``Measure`` values, never ``None``: unlike D5, whether a D3 source was
    supplied to this build at all is recorded once, at the assembly level
    (``ProfileAssembly.absenteeism_academic_year``), not per school, the same
    choice D2's own ``total_enrollment``/``subgroups`` already make. A school this
    build's D3 source never mentions and a build given no D3 source at all both
    read ``not_reported`` here; the assembly-level field is what tells them apart.
    """

    school: School
    academic_year: str
    total_enrollment: Measure
    grades: dict[str, Measure]
    subgroups: dict[str, Measure]
    teacher_assignments: AssignmentRow | None
    chronic_absenteeism_rate: Measure
    chronic_absenteeism_subgroups: dict[str, Measure]


@dataclass(frozen=True)
class ProfileAssembly:
    """The profiles plus the join gaps, which are findings to publish, not noise."""

    academic_year: str
    profiles: list[SchoolProfile]
    unjoined_school_totals: int
    schools_without_enrollment: int
    assignments_academic_year: str | None
    unjoined_assignment_rows: int | None
    schools_without_assignments: int | None
    absenteeism_academic_year: str | None
    unjoined_absenteeism_rows: int | None
    schools_without_absenteeism: int | None


def assignment_measure(
    profile: SchoolProfile, outcome: str, *, percent: bool
) -> Measure:
    """One school's published D5 cell for one outcome, or nothing published.

    ``teacher_assignments`` is ``None`` both for a school the supplied file never
    mentions and for a build given no D5 file at all, and this returns
    ``not_reported`` for either, because at the level of one school there is no
    number and no mask in either case. What tells the two apart is
    :attr:`ProfileAssembly.assignments_academic_year`, which is where that fact
    is recorded once instead of on every profile.

    Every consumer reads the cell through here -- the artifact, the coverage
    tallies, the page -- so the rule is stated in one place rather than copied
    into three, which is how two of them would eventually disagree about what a
    missing row means.
    """
    row = profile.teacher_assignments
    if row is None:
        return Measure.not_reported()
    return row.percents[outcome] if percent else row.counts[outcome]


def assignment_total(profile: SchoolProfile) -> Measure:
    """This school's total teaching FTE, or nothing published. Same rule."""
    row = profile.teacher_assignments
    return row.total if row is not None else Measure.not_reported()


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


def _assignment_rows(
    assignments_path: Path,
) -> tuple[str, dict[str, AssignmentRow]]:
    """School-level D5 rows keyed by CDS code, plus the academic year they report."""
    by_school = school_outcomes(assignments_path)
    years = {row.academic_year for row in by_school.values()}
    if len(years) != 1:
        raise ProfileDriftError(
            f"{assignments_path.name} carries academic years {sorted(years)}; "
            "profile assembly was built against exactly one"
        )
    return years.pop(), by_school


def _absenteeism_rows(
    absenteeism_path: Path,
) -> tuple[str, dict[str, dict[str, AbsenteeismRow]]]:
    """School-level D3 rows keyed by CDS code then category, plus the academic
    year. Mirrors :func:`_school_rows`, D2's own version of the same join."""
    years: set[str] = set()
    by_school: dict[str, dict[str, AbsenteeismRow]] = {}
    for row in parse_absenteeism(absenteeism_path):
        if row.category not in ABSENTEEISM_CATEGORY_NAMES:
            raise ProfileDriftError(
                f"{absenteeism_path.name}: Reporting Category {row.category!r} has "
                "no reviewed display name; upstream added a code this project has "
                "not reviewed, so the build stops rather than guessing"
            )
        years.add(row.academic_year)
        if row.level != ABSENTEEISM_SCHOOL_LEVEL:
            continue
        rows = by_school.setdefault(row.cds_code, {})
        if row.category in rows:
            raise ProfileDriftError(
                f"{absenteeism_path.name}: CDS {row.cds_code} carries two "
                f"{row.category!r} rows; the one-row-per-category layout changed"
            )
        rows[row.category] = row
    if len(years) != 1:
        raise ProfileDriftError(
            f"{absenteeism_path.name} carries academic years {sorted(years)}; "
            "profile assembly was verified against exactly one"
        )
    return years.pop(), by_school


def _profile(
    school: School,
    rows: dict[str, EnrollmentRow],
    academic_year: str,
    assignments: AssignmentRow | None,
    absenteeism_rows: dict[str, AbsenteeismRow],
) -> SchoolProfile:
    """Copy published cells onto a profile. Absent rows are not reported, because
    the state published nothing; they are never filled in from arithmetic."""
    total_row = rows.get(TOTAL_CATEGORY)
    absenteeism_total = absenteeism_rows.get(ABSENTEEISM_TOTAL_CATEGORY)
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
        teacher_assignments=assignments,
        chronic_absenteeism_rate=(
            absenteeism_total.rate if absenteeism_total else Measure.not_reported()
        ),
        chronic_absenteeism_subgroups={
            code: (
                absenteeism_rows[code].rate
                if code in absenteeism_rows
                else Measure.not_reported()
            )
            for code in ABSENTEEISM_SUBGROUP_CODES
        },
    )


def assemble_profiles(
    directory_path: Path,
    enrollment_path: Path,
    assignments_path: Path | None = None,
    *,
    absenteeism_path: Path | None = None,
) -> ProfileAssembly:
    """One profile per active school, in CDS order, with join gaps counted.

    The gap runs both ways for every source and both directions are published:
    rows whose CDS matches no active school (closed schools still reporting, or
    spine lag), and active schools the file never mentions.

    ``assignments_path`` and ``absenteeism_path`` are both optional, so a caller
    that only has the directory and enrollment files can still build profiles.
    Left out, the corresponding counts come back ``None`` rather than zero: no
    source is not the same claim as a source that covers nothing.
    """
    spine = _spine(directory_path)
    academic_year, by_school = _school_rows(enrollment_path)
    assignment_year, assignments = (
        _assignment_rows(assignments_path)
        if assignments_path is not None
        else (None, {})
    )
    absenteeism_year, absenteeism_by_school = (
        _absenteeism_rows(absenteeism_path)
        if absenteeism_path is not None
        else (None, {})
    )
    profiles = [
        _profile(
            spine[cds],
            by_school.get(cds, {}),
            academic_year,
            assignments.get(cds) if assignments_path is not None else None,
            absenteeism_by_school.get(cds, {}),
        )
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
        assignments_academic_year=assignment_year,
        unjoined_assignment_rows=(
            sum(1 for cds in assignments if cds not in spine)
            if assignments_path is not None
            else None
        ),
        schools_without_assignments=(
            sum(1 for cds in spine if cds not in assignments)
            if assignments_path is not None
            else None
        ),
        absenteeism_academic_year=absenteeism_year,
        unjoined_absenteeism_rows=(
            sum(
                1
                for cds, rows in absenteeism_by_school.items()
                if ABSENTEEISM_TOTAL_CATEGORY in rows and cds not in spine
            )
            if absenteeism_path is not None
            else None
        ),
        schools_without_absenteeism=(
            sum(
                1
                for cds in spine
                if ABSENTEEISM_TOTAL_CATEGORY not in absenteeism_by_school.get(cds, {})
            )
            if absenteeism_path is not None
            else None
        ),
    )
