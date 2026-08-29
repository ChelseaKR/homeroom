"""Parse CDE Chronic Absenteeism files (PROVENANCE.md D3).

Chronic absenteeism is CDE's own measure of how many students missed 10% or more
of the days they were expected to attend, out of the students eligible to be
considered ("Chronic Absenteeism Eligible Cumulative Enrollment" removes students
who attended too briefly to be counted, or who were exempt). It is the first
measure this project publishes that CDE masks at meaningful scale (M3,
docs/ROADMAP.md), and the measure the project's own honesty rules exist for most
directly: a school's rate is not a score, not a ranking signal, and not shown as
zero when the state withheld it (ADR 0002).

**Verified against an acquired file.** The 2024-25 file (``chronicabsenteeism25.txt``,
33,781,100 bytes, 341,490 data rows) was downloaded from
https://www3.cde.ca.gov/demo-downloads/attendance/chronicabsenteeism25-v2.txt on
2026-08-21 and its header read directly. Column names are spaced
(``"Chronic Absenteeism Rate"`` would be the natural guess; the real header instead
concatenates as ``ChronicAbsenteeismRate``, which this module reads verbatim), and
``Charter School``/``DASS`` are independent dimensions, each an ``All``/``Yes``/``No``
value -- not the single ``ALL``/``Y``/``N`` dimension D2 uses. Scanning the acquired
file found 104,469 of 341,490 rows (30.6%) carrying a mask on at least one of its
three numeric cells, and every masked row masks all three together (eligible
enrollment, count, and rate), never a subset. 25 reporting-category codes appear,
none of them the ones D2 uses for the same underlying groups (D2's ``RE_A`` is this
file's ``RA``; see :data:`homeroom.profiles.ABSENTEEISM_CATEGORY_NAMES` for CDE's
own labels for all 25).

**Small-cell masking, per CDE's own file-structure page**
(https://www.cde.ca.gov/ds/ad/fsabd.asp): "data are suppressed (*) ... if the cell
size within a selected student population (Chronic Absenteeism Eligible Cumulative
Enrollment) is 10 or less. Additionally, for Race/Ethnicity, 'Not Reported' is
suppressed, regardless of actual cell size, if the student population for one or
more other race/ethnicity groups is suppressed." Homeroom does not reproduce that
rule; it reads whichever cells CDE actually masked, the same as every other source.

Two rules ride on top of the shared :class:`homeroom.measures.Measure` machinery:

*Never derive.* The rate is a cell CDE published, never divided out of the count
and the eligible-enrollment cells, even when both of those happen to be visible.

*Masked stays unreadable.* A masked rate is suppressed, a published zero (a school
where nobody eligible was chronically absent) is a genuine zero, and a school this
file never mentions is not reported, all the way to the artifact and the page.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from homeroom.measures import Measure, parse_cell

IDENTITY_COLUMNS = (
    "Academic Year",
    "Aggregate Level",
    "County Code",
    "District Code",
    "School Code",
)
"""Columns this parser reads by name. The real header also carries County Name,
District Name and School Name; this project takes names from D1 and never reads
them here, the same choice D1, D2 and D5 already made about their own identity
columns."""

CHARTER_COLUMN = "Charter School"
DASS_COLUMN = "DASS"
ALL_VALUE = "All"
"""The value meaning "aggregated without regard to this dimension", for both
:data:`CHARTER_COLUMN` and :data:`DASS_COLUMN`. Verified: at school level neither
column is ever ``All`` (CDE's file-structure page: "beginning in 2021-22, only data
rows for the applicable Y or N value of the school are included in the file"); a
school-level row always carries the school's own actual Yes/No for both."""

KNOWN_CHARTER_VALUES = frozenset({"All", "Yes", "No"})
KNOWN_DASS_VALUES = frozenset({"All", "Yes", "No"})

REPORTING_CATEGORY_COLUMN = "Reporting Category"

TOTAL_CATEGORY = "TA"
"""The all-students reporting category, matching D2's own convention for the same
concept under a different code."""

ELIGIBLE_ENROLLMENT_COLUMN = "ChronicAbsenteeismEligibleCumulativeEnrollment"
COUNT_COLUMN = "ChronicAbsenteeismCount"
RATE_COLUMN = "ChronicAbsenteeismRate"

REQUIRED_COLUMNS = (
    *IDENTITY_COLUMNS,
    CHARTER_COLUMN,
    DASS_COLUMN,
    REPORTING_CATEGORY_COLUMN,
    ELIGIBLE_ENROLLMENT_COLUMN,
    COUNT_COLUMN,
    RATE_COLUMN,
)
"""Every column this parser reads. Absence of any is drift and fails the build."""

SCHOOL_LEVEL = "S"
DISTRICT_LEVEL = "D"
STATE_LEVEL = "T"
KNOWN_LEVELS = frozenset({"T", "C", "D", "S"})
"""Aggregate levels: state, county, district, school. Anything else is drift."""


class AbsenteeismDriftError(ValueError):
    """The upstream file does not match the layout this parser was built against."""


@dataclass(frozen=True)
class AbsenteeismRow:
    """One row of published chronic-absenteeism figures. Every value is a copied
    cell; the rate is never computed here from the count and the enrollment."""

    academic_year: str
    level: str
    charter: str
    dass: str
    cds_code: str
    category: str
    eligible_enrollment: Measure
    count: Measure
    rate: Measure


def _cds(county: str, district: str, school: str, *, where: str) -> str:
    """Assemble the 14-digit join key, the same convention D1, D2 and D5 use: a
    blank school code (aggregate rows) zero-fills rather than raising."""
    county, district, school = county.strip(), district.strip(), school.strip()
    code = (
        f"{county:0>2}{district:0>5}{school:0>7}"
        if school
        else f"{county:0>2}{district:0>5}0000000"
    )
    if len(code) != 14 or not code.isdigit():
        raise AbsenteeismDriftError(
            f"{where}: cannot assemble a 14-digit CDS from "
            f"county={county!r} district={district!r} school={school!r}"
        )
    return code


def parse_absenteeism(path: Path) -> Iterator[AbsenteeismRow]:
    """Yield every row, school-level and aggregate alike.

    Aggregate rows (state, county, district) are yielded with the level that
    produced them, because the statewide and district rate a school's own rate is
    read against comes from these same rows (see
    :func:`homeroom.context.load_absenteeism_context`).
    """
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        header = reader.fieldnames or []
        missing = [column for column in REQUIRED_COLUMNS if column not in header]
        if missing:
            raise AbsenteeismDriftError(
                f"{path.name} is missing required columns {missing}; the layout "
                "must be re-verified against CDE's file structure before parsing"
            )
        for line_number, row in enumerate(reader, start=2):
            where = f"{path.name}:{line_number}"
            level = (row.get("Aggregate Level") or "").strip()
            if level not in KNOWN_LEVELS:
                raise AbsenteeismDriftError(
                    f"{where}: Aggregate Level {level!r} is not one this parser "
                    "reviewed"
                )
            charter = (row.get(CHARTER_COLUMN) or "").strip()
            if charter not in KNOWN_CHARTER_VALUES:
                raise AbsenteeismDriftError(
                    f"{where}: {CHARTER_COLUMN} {charter!r} is not one this parser "
                    "reviewed"
                )
            dass = (row.get(DASS_COLUMN) or "").strip()
            if dass not in KNOWN_DASS_VALUES:
                raise AbsenteeismDriftError(
                    f"{where}: {DASS_COLUMN} {dass!r} is not one this parser reviewed"
                )
            county = (row.get("County Code") or "").strip()
            district = (row.get("District Code") or "").strip()
            school = (row.get("School Code") or "").strip()
            cds = _cds(county, district, school, where=where)
            yield AbsenteeismRow(
                academic_year=(row.get("Academic Year") or "").strip(),
                level=level,
                charter=charter,
                dass=dass,
                cds_code=cds,
                category=(row.get(REPORTING_CATEGORY_COLUMN) or "").strip(),
                eligible_enrollment=parse_cell(
                    row.get(ELIGIBLE_ENROLLMENT_COLUMN),
                    field=ELIGIBLE_ENROLLMENT_COLUMN,
                    where=where,
                ),
                count=parse_cell(
                    row.get(COUNT_COLUMN), field=COUNT_COLUMN, where=where
                ),
                rate=parse_cell(row.get(RATE_COLUMN), field=RATE_COLUMN, where=where),
            )
