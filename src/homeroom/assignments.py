"""Parse CDE Teacher Assignment Monitoring Outcome files (PROVENANCE.md D5).

CDE publishes these files from the Commission on Teacher Credentialing's CalSAAS
system: for each school, how many teaching assignments (in full-time-equivalent
units, FTE) sat in each authorization outcome the state tracks. Homeroom carries
that record so a family can read it beside enrollment, on the same school page, in
their language. It restates CDE's and the Commission's published outcomes; it does
not re-score them and it does not evaluate teachers.

**Verified against an acquired file.** The 2023-24 file (``tamo2324.txt``, 234,206,408
bytes, 1,528,796 data rows) was downloaded from
https://www3.cde.ca.gov/demo-downloads/tamo/tamo2324.txt on 2026-08-21 and its
header read directly; nothing below is carried over from documentation prose. The
provisional contract this module carried before that (five outcomes, one row per
school, column names in the style ``ClearCount``/``ClearPercent``) did not survive
contact with the file. What follows replaces it, and PROVENANCE.md D5 records the
full list of what changed.

**The file's grain is not one row per school.** Every row is one intersection of
school, ``Charter School``, ``DASS``, ``School Grade Span``, ``Teacher Experience
Level``, ``Teacher Credential Level``, and ``Subject Area``: a school-level CDS code
appears in up to 150 rows in the acquired file (10,064 distinct schools, up to 150
rows each). :data:`GRADE_SPAN`, :data:`EXPERIENCE_LEVEL`, :data:`CREDENTIAL_LEVEL`
and :data:`SUBJECT_AREA` each carry an ``ALL``/``TA`` value meaning "aggregated
without regard to this dimension", the same convention D2's ``ReportingCategory ==
TA`` and D2/D3's ``Charter == ALL`` already use. Verified empirically: every one of
the 10,064 schools in the acquired file publishes exactly one row where experience
level, credential level, and subject area are all ``ALL``/``ALL``/``TA`` at that
school's own (single, not "ALL") grade span -- the genuine whole-school total CDE
itself computed, not a value this project would sum out of the other 149. Only that
row is read as "this school's outcomes"; see :func:`school_outcomes`.

**This file does not mask, in the vintage acquired.** D2 and D3 both withhold small
cells behind CDE's ``*``. Scanning every numeric cell in the acquired 2023-24 file
(1,528,796 rows x 15 numeric columns) found zero instances of ``*``, an empty cell,
or any sentinel other than a plain FTE number -- not "no masked cell happened to
appear here", the way M4's enrollment page had zero withheld cells on one school,
but zero anywhere in the whole file, and CDE's file-structure page
(https://www.cde.ca.gov/ds/ad/fstamo.asp) carries no small-cell suppression rule for
this file the way https://www.cde.ca.gov/ds/ad/fsabd.asp does for D3. The
:data:`homeroom.measures.SUPPRESSION_MARK` path stays load-bearing here anyway --
this project has already been wrong once about what this file does, and a future
year's file suppressing cells is exactly the kind of drift this module exists to
catch rather than assume away. The committed fixture keeps a masked school so the
path is exercised by a test, not just left dead code.

Two rules ride on top of the shared :class:`homeroom.measures.Measure` machinery and
matter more here than anywhere else in the project so far:

*Never derive.* Every value is a cell CDE published, including the whole-school
total row itself, which is CDE's own aggregate and not a sum this project performs
over the other rows for that school.

*Masked stays unreadable.* A masked outcome is suppressed, a published zero is
zero, and an absent cell is not reported, all the way to the artifact.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from homeroom.measures import Measure, parse_cell

OUTCOMES: tuple[str, ...] = (
    "clear",
    "out_of_field",
    "intern",
    "ineffective",
    "incomplete",
    "unknown",
    "na",
)
"""The seven authorization outcomes this file publishes, in the order pages would
read them. Five were in this module's provisional contract; ``incomplete`` and
``na`` did not appear in it and were found only by reading the acquired file."""

OUTCOME_NAMES: dict[str, str] = {
    "clear": "Clear credential, appropriately assigned",
    "out_of_field": "Credentialed, assigned outside that authorization",
    "intern": "Teaching on an intern credential",
    "ineffective": "Teaching on a permit, waiver, or other non-credentialed basis",
    "incomplete": "Assignment data incomplete",
    "unknown": "Authorization not established in the state's records",
    "na": "Assignment monitoring outcome not applicable",
}
"""EN display names. The underlying fact, which credential the assignment sat on,
is what gets shown, for the same reason D2 expands CDE's "Not Reported" label
rather than repeating a term of art a family would meet cold."""

IDENTITY_COLUMNS = (
    "Academic Year",
    "Aggregate Level",
    "County Code",
    "District Code",
    "School Code",
)
"""Columns this parser reads by name. CDE's real header also carries County Name,
District Name and School Name; this project takes names from D1 and never reads
them here, the same choice D1 and D2 already made about their own identity columns.
"""

CHARTER_COLUMN = "Charter School"
"""Values observed: ``All``, ``Yes``, ``No`` (note: CDE pads ``No`` with a trailing
space in the acquired file; this parser strips it). Unlike D2's single-letter
``Y``/``N``/``ALL``, this file spells the same three states as words."""

DASS_COLUMN = "DASS"
"""Dashboard Alternative School Status: ``All``, ``Yes``, ``No``, the same three
values as :data:`CHARTER_COLUMN`. Not a dimension D1's spine carries; Homeroom
records what the school actually is (never ``All``, verified: every one of the
10,064 schools in the acquired file carries exactly one Charter/DASS combination)
but does not join on it."""

GRADE_SPAN_COLUMN = "School Grade Span"
GRADE_SPAN_ALL = "ALL"
KNOWN_GRADE_SPANS = frozenset({"ALL", "GRK12", "GR912", "GR69", "GRK6"})
"""Observed in the acquired file. At school level this is never ``ALL``: it is the
one grade span that school actually serves (verified: every school carries exactly
one)."""

EXPERIENCE_COLUMN = "Teacher Experience Level"
EXPERIENCE_ALL = "ALL"
KNOWN_EXPERIENCE_LEVELS = frozenset({"ALL", "EXP", "INEXP"})

CREDENTIAL_COLUMN = "Teacher Credential Level"
CREDENTIAL_ALL = "ALL"
KNOWN_CREDENTIAL_LEVELS = frozenset({"ALL", "FC", "NFC"})

SUBJECT_COLUMN = "Subject Area"
SUBJECT_TOTAL = "TA"
KNOWN_SUBJECT_AREAS = frozenset(
    {
        "AGRI",
        "ARTS",
        "BUSN",
        "CPTE",
        "CTED",
        "DNCE",
        "DRMT",
        "ENLA",
        "FRLG",
        "GADM",
        "HISS",
        "HLTH",
        "MATH",
        "MDAR",
        "MUSC",
        "OTHR",
        "PHYS",
        "SCCL",
        "SCIE",
        "SDSU",
        "TA",
    }
)
"""The 21 subject-area codes observed in the acquired 2023-24 file. ``TA`` is the
all-subjects total, the same convention D2's ``TA`` reporting category uses."""

TOTAL_COLUMN = "Total FTE"
"""Total teaching assignment FTE the outcomes describe. Fractional: this file
reports full-time-equivalent units, not integer assignment counts."""

OUTCOME_COLUMNS: dict[str, tuple[str, str]] = {
    "clear": ("Clear FTE (count)", "Clear FTE (percent)"),
    "out_of_field": ("Out-of-Field FTE (count)", "Out-of-Field FTE (percent)"),
    "intern": ("Intern FTE (count)", "Intern FTE (percent)"),
    "ineffective": ("Ineffective FTE (count)", "Ineffective FTE (percent)"),
    "incomplete": ("Incomplete FTE (count)", "Incomplete FTE (percent)"),
    "unknown": ("Unknown FTE (count)", "Unknown FTE FTE (percent)"),
    "na": ("N/A FTE (count)", "N/A FTE (percent)"),
}
"""outcome -> (count column, percent column), read verbatim from the acquired
header. ``"Unknown FTE FTE (percent)"`` repeats "FTE" -- that is CDE's own column
header, byte for byte, not a typo introduced here; "fixing" it would silently stop
reading the column CDE actually writes to."""

REQUIRED_COLUMNS = (
    *IDENTITY_COLUMNS,
    CHARTER_COLUMN,
    DASS_COLUMN,
    GRADE_SPAN_COLUMN,
    EXPERIENCE_COLUMN,
    CREDENTIAL_COLUMN,
    SUBJECT_COLUMN,
    TOTAL_COLUMN,
    *(column for pair in OUTCOME_COLUMNS.values() for column in pair),
)
"""Every column this parser reads. Absence of any is drift and fails the build."""

SCHOOL_LEVEL = "S"
KNOWN_LEVELS = frozenset({"T", "C", "D", "S"})
"""Aggregate levels: state, county, district, school. Anything else is drift."""

KNOWN_CHARTER_VALUES = frozenset({"All", "Yes", "No"})
KNOWN_DASS_VALUES = frozenset({"All", "Yes", "No"})


class AssignmentDriftError(ValueError):
    """The upstream file does not match the layout this parser was built against."""


@dataclass(frozen=True)
class AssignmentRow:
    """One row of published outcomes. Every value is a copied cell."""

    academic_year: str
    level: str
    cds_code: str
    charter: str
    dass: str
    grade_span: str
    experience_level: str
    credential_level: str
    subject_area: str
    total: Measure
    counts: dict[str, Measure]
    percents: dict[str, Measure]


def _cds(county: str, district: str, school: str, *, where: str) -> str:
    """Assemble the 14-digit join key. The only key Homeroom joins on.

    Mirrors :func:`homeroom.enrollment._cds`: a blank school code (aggregate rows)
    zero-fills rather than raising, and a school-level row must resolve to exactly
    14 digits or the row is drift.
    """
    county, district, school = county.strip(), district.strip(), school.strip()
    code = (
        f"{county:0>2}{district:0>5}{school:0>7}"
        if school
        else f"{county:0>2}{district:0>5}0000000"
    )
    if len(code) != 14 or not code.isdigit():
        raise AssignmentDriftError(
            f"{where}: cannot assemble a 14-digit CDS from "
            f"county={county!r} district={district!r} school={school!r}"
        )
    return code


def _checked(value: str, known: frozenset[str], *, field: str, where: str) -> str:
    if value not in known:
        raise AssignmentDriftError(
            f"{where}: {field} {value!r} is not one this parser reviewed"
        )
    return value


def parse_assignments(path: Path) -> Iterator[AssignmentRow]:
    """Yield every row, school-level and aggregate alike.

    Aggregate rows (state, county, district) are yielded with the level that
    produced them rather than being dropped or disguised as schools.
    """
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        header = reader.fieldnames or []
        missing = [column for column in REQUIRED_COLUMNS if column not in header]
        if missing:
            raise AssignmentDriftError(
                f"{path.name} is missing required columns {missing}; the layout "
                "must be re-verified against CDE's file structure before parsing"
            )
        for line_number, row in enumerate(reader, start=2):
            where = f"{path.name}:{line_number}"
            level = _checked(
                (row.get("Aggregate Level") or "").strip(),
                KNOWN_LEVELS,
                field="Aggregate Level",
                where=where,
            )
            charter = _checked(
                (row.get(CHARTER_COLUMN) or "").strip(),
                KNOWN_CHARTER_VALUES,
                field=CHARTER_COLUMN,
                where=where,
            )
            dass = _checked(
                (row.get(DASS_COLUMN) or "").strip(),
                KNOWN_DASS_VALUES,
                field=DASS_COLUMN,
                where=where,
            )
            grade_span = _checked(
                (row.get(GRADE_SPAN_COLUMN) or "").strip(),
                KNOWN_GRADE_SPANS,
                field=GRADE_SPAN_COLUMN,
                where=where,
            )
            experience = _checked(
                (row.get(EXPERIENCE_COLUMN) or "").strip(),
                KNOWN_EXPERIENCE_LEVELS,
                field=EXPERIENCE_COLUMN,
                where=where,
            )
            credential = _checked(
                (row.get(CREDENTIAL_COLUMN) or "").strip(),
                KNOWN_CREDENTIAL_LEVELS,
                field=CREDENTIAL_COLUMN,
                where=where,
            )
            subject = _checked(
                (row.get(SUBJECT_COLUMN) or "").strip(),
                KNOWN_SUBJECT_AREAS,
                field=SUBJECT_COLUMN,
                where=where,
            )
            county = (row.get("County Code") or "").strip()
            district = (row.get("District Code") or "").strip()
            school = (row.get("School Code") or "").strip()
            cds = _cds(county, district, school, where=where)
            yield AssignmentRow(
                academic_year=(row.get("Academic Year") or "").strip(),
                level=level,
                cds_code=cds,
                charter=charter,
                dass=dass,
                grade_span=grade_span,
                experience_level=experience,
                credential_level=credential,
                subject_area=subject,
                total=parse_cell(
                    row.get(TOTAL_COLUMN), field=TOTAL_COLUMN, where=where
                ),
                counts={
                    outcome: parse_cell(row.get(count), field=count, where=where)
                    for outcome, (count, _) in OUTCOME_COLUMNS.items()
                },
                percents={
                    outcome: parse_cell(row.get(percent), field=percent, where=where)
                    for outcome, (_, percent) in OUTCOME_COLUMNS.items()
                },
            )


def _is_school_total(row: AssignmentRow) -> bool:
    """True for the one row per school that is CDE's own whole-school aggregate.

    Experience level, credential level, and subject area all ``ALL``/``TA``:
    verified empirically against the acquired file that exactly one such row
    exists for every one of its 10,064 schools (docstring above). Grade span is
    not part of the filter because a school-level row is never ``ALL`` there; it
    already carries the one grade span the school serves.
    """
    return (
        row.experience_level == EXPERIENCE_ALL
        and row.credential_level == CREDENTIAL_ALL
        and row.subject_area == SUBJECT_TOTAL
    )


def school_outcomes(path: Path) -> dict[str, AssignmentRow]:
    """CDS code -> this school's whole-school outcomes, school-level rows only.

    Selects CDE's own already-aggregated row per school (see :func:`_is_school_total`)
    rather than summing the file's ~150 rows per school over subject, experience, and
    credential -- doing that arithmetic here, even correctly, would be exactly the
    derivation PROVENANCE.md and this module's own docstring rule out. A CDS with
    more than one qualifying row is drift, not a row to overwrite: it would mean the
    one-total-row-per-school shape this parser was verified against no longer holds.
    """
    outcomes: dict[str, AssignmentRow] = {}
    for row in parse_assignments(path):
        if row.level != SCHOOL_LEVEL or not _is_school_total(row):
            continue
        if row.cds_code in outcomes:
            raise AssignmentDriftError(
                f"{path.name}: CDS {row.cds_code} carries two whole-school total "
                "rows (Teacher Experience Level=Teacher Credential Level=ALL, "
                "Subject Area=TA); the shape this parser was verified against "
                "no longer holds"
            )
        outcomes[row.cds_code] = row
    return outcomes
