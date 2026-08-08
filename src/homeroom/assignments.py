"""Parse CDE Teacher Assignment Monitoring Outcome files (PROVENANCE.md D5).

CDE publishes these files from the Commission on Teacher Credentialing's CalSAAS
system: for each school, how many teaching assignments were held by a teacher with
a clear credential appropriately matched to the assignment, and how many sat in one
of the other authorization states the state tracks. Homeroom carries that record so
a family can read it beside enrollment, on the same school page, in their language.
It restates CDE's and the Commission's published outcomes; it does not re-score
them and it does not evaluate teachers.

**Layout status: provisional, not yet verified against an acquired file.** The D1
and D2 parsers were written against files in hand, and their docstrings say so.
This one was not. The column names below were not read off CDE's file structure
page; they follow the conventions the D2 file did turn out to use. So the contract
is the single thing to check at acquisition, and it is deliberately the only place
in this module where a column name appears.

That is safe rather than sloppy only because the parser fails closed in every
direction: a missing required column, an aggregate level this parser has not
reviewed, a CDS code that is not 14 digits, or a cell that is neither a number,
the mask, nor empty all raise. If the real file disagrees with the contract, the
build stops. It never guesses, and it never half-reads a file into numbers about
real schools.

Two rules ride on top of the shared :class:`homeroom.measures.Measure` machinery
and matter more here than anywhere else in the project so far:

*Never derive.* Every value is a cell CDE published. A share is copied from a
published percent column, never computed from counts; a count is never computed
from a percent and a total; an outcome missing from the file is never recovered as
the total minus its visible siblings. Assignment counts are small, so complements
are exactly how a masked cell gets undone, and undoing it would put a handful of
identifiable teachers back on the page.

*Masked stays unreadable.* Small-cell masking bites harder here than in
enrollment: a school with four teachers can have most of this table withheld. A
masked outcome is suppressed, a published zero is zero, and an absent cell is not
reported, all the way to the artifact.
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
    "unknown",
)
"""The authorization outcomes this parser carries, in the order pages read them."""

OUTCOME_NAMES: dict[str, str] = {
    "clear": "Clear credential, appropriately assigned",
    "out_of_field": "Credentialed, assigned outside that authorization",
    "intern": "Teaching on an intern credential",
    "ineffective": "Teaching on a permit or waiver",
    "unknown": "Authorization not established in the state's records",
}
"""EN display names, to be confirmed against CDE's own labels at acquisition.

The keys mirror the reporting terms these files use. The display strings describe
the authorization rather than repeating a term of art, for the same reason D2
expands CDE's "Not Reported" and "Missing" labels: a family reading a school page
should not meet a reporting category and take it for a judgment about the teacher
in their child's classroom. The underlying fact, which credential the assignment
sat on, is what gets shown.
"""

TOTAL_COLUMN = "TotalAssignments"
"""Total teaching assignments the outcomes describe."""

OUTCOME_COLUMNS: dict[str, tuple[str, str]] = {
    "clear": ("ClearCount", "ClearPercent"),
    "out_of_field": ("OutOfFieldCount", "OutOfFieldPercent"),
    "intern": ("InternCount", "InternPercent"),
    "ineffective": ("IneffectiveCount", "IneffectivePercent"),
    "unknown": ("UnknownCount", "UnknownPercent"),
}
"""outcome -> (count column, percent column). Provisional; re-verify at acquisition.

Both members are read and neither is computed from the other. If CDE publishes only
one of the pair, the missing side is dropped from this mapping at acquisition and
the pages show what exists; it is not back-filled with arithmetic.
"""

IDENTITY_COLUMNS = (
    "AcademicYear",
    "AggregateLevel",
    "CountyCode",
    "DistrictCode",
    "SchoolCode",
)

REQUIRED_COLUMNS = (
    *IDENTITY_COLUMNS,
    TOTAL_COLUMN,
    *(column for pair in OUTCOME_COLUMNS.values() for column in pair),
)
"""Every column this parser reads. Absence of any is drift and fails the build."""

SCHOOL_LEVEL = "S"
KNOWN_LEVELS = {"T", "C", "D", "S"}
"""Aggregate levels: state, county, district, school. Anything else is drift."""


class AssignmentDriftError(ValueError):
    """The upstream file does not match the layout this parser was built against."""


@dataclass(frozen=True)
class AssignmentRow:
    """One row of published outcomes. Every value is a copied cell."""

    academic_year: str
    level: str
    cds_code: str
    total: Measure
    counts: dict[str, Measure]
    percents: dict[str, Measure]


def _cds(county: str, district: str, school: str, *, where: str) -> str:
    """Assemble the 14-digit join key. The only key Homeroom joins on."""
    county, district, school = county.strip(), district.strip(), school.strip()
    code = f"{county:0>2}{district:0>5}{school:0>7}"
    if len(code) != 14 or not code.isdigit():
        raise AssignmentDriftError(
            f"{where}: cannot assemble a 14-digit CDS from "
            f"county={county!r} district={district!r} school={school!r}"
        )
    return code


def parse_assignments(path: Path) -> Iterator[AssignmentRow]:
    """Yield every row, school-level and aggregate alike.

    Aggregate rows (state, county, district) are yielded with the level that
    produced them rather than being dropped or disguised as schools, because the
    statewide and district figures are the context a school figure needs to be
    readable at all.
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
            level = (row.get("AggregateLevel") or "").strip()
            if level not in KNOWN_LEVELS:
                raise AssignmentDriftError(
                    f"{where}: AggregateLevel {level!r} is not one this parser reviewed"
                )
            county = (row.get("CountyCode") or "").strip()
            district = (row.get("DistrictCode") or "").strip()
            school = (row.get("SchoolCode") or "").strip()
            cds = (
                _cds(county, district, school, where=where)
                if level == SCHOOL_LEVEL
                else f"{county:0>2}{district:0>5}{school:0>7}".ljust(14, "0")[:14]
            )
            yield AssignmentRow(
                academic_year=(row.get("AcademicYear") or "").strip(),
                level=level,
                cds_code=cds,
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


def school_outcomes(path: Path) -> dict[str, AssignmentRow]:
    """CDS code -> outcomes, school-level rows only.

    A CDS appearing twice is drift, not a row to overwrite: two school rows mean
    the one-row-per-school layout changed, and silently keeping the last one would
    publish half a school's teachers as all of them.
    """
    outcomes: dict[str, AssignmentRow] = {}
    for row in parse_assignments(path):
        if row.level != SCHOOL_LEVEL:
            continue
        if row.cds_code in outcomes:
            raise AssignmentDriftError(
                f"{path.name}: CDS {row.cds_code} carries two school-level rows; "
                "the one-row-per-school layout changed and must be re-verified"
            )
        outcomes[row.cds_code] = row
    return outcomes
