"""Parse CDE Census Day Enrollment files (PROVENANCE.md D2).

Layout verified against the acquired 2025-26 file (269,090 rows, header read
2026-08-07), not remembered: one row per (aggregate level, entity, reporting
category), grade columns TK through 12 plus a total, with CDE's ``*`` masking
in force (117,946 rows in the 2025-26 file carry at least one masked cell,
re-measured 2026-08-07; every one is a school-level row masked in grade
columns, and TOTAL_ENR is never masked in this file).
Every cell passes through :func:`homeroom.measures.parse_cell`, so a masked
count can never surface as a zero.

The CDS join key is assembled from the file's split county/district/school
codes, zero-padded to the directory's 14-digit form. Aggregate rows (state,
county, district) carry partial codes and are exposed separately rather than
being disguised as schools.

ReportingCategory values observed in the acquired 2025-26 file (33 codes, counted
2026-08-07): ``TA``; race/ethnicity ``RE_A RE_B RE_D RE_F RE_H RE_I RE_P RE_T
RE_W``; gender ``GN_F GN_M GN_X``; English language acquisition ``ELAS_ADEL
ELAS_EL ELAS_EO ELAS_IFEP ELAS_MISS ELAS_RFEP ELAS_TBD``; student groups ``SG_DS
SG_EL SG_FS SG_HM SG_MG SG_SD``; age ranges ``AR_03 AR_0418 AR_1922 AR_2329
AR_3039 AR_4049 AR_50P``. Their reviewed display names live in
:data:`homeroom.profiles.CATEGORY_NAMES`; a code outside that set is drift.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from homeroom.measures import Measure, parse_cell

GRADE_COLUMNS = (
    "GR_TK",
    "GR_KN",
    "GR_01",
    "GR_02",
    "GR_03",
    "GR_04",
    "GR_05",
    "GR_06",
    "GR_07",
    "GR_08",
    "GR_09",
    "GR_10",
    "GR_11",
    "GR_12",
)

REQUIRED_COLUMNS = (
    "AcademicYear",
    "AggregateLevel",
    "Charter",
    "CountyCode",
    "DistrictCode",
    "SchoolCode",
    "ReportingCategory",
    "TOTAL_ENR",
    *GRADE_COLUMNS,
)

TOTAL_CATEGORY = "TA"
"""The all-students reporting category, per the acquired file's own rows."""

SCHOOL_LEVEL = "S"
DISTRICT_LEVEL = "D"
STATE_LEVEL = "T"
KNOWN_LEVELS = {"T", "C", "D", "S"}

ALL_CHARTER = "ALL"
"""The charter value meaning "every school at this level, charter or not".

This distinction is load-bearing, not bookkeeping. Each aggregate entity is
published three times over: once for its charter schools, once for its
non-charter schools, and once for both together. In the acquired 2025-26 file
Davis Joint Unified's three district rows read 561, 7,682 and 8,243 students for
the same reporting category, so a reader that takes whichever row it meets first
can publish a district figure fifteen times too small and never notice. Only
``ALL`` answers "how big is the district".

School-level rows carry ``Y`` or ``N`` and never ``ALL``, because a school either
is a charter or is not.
"""

KNOWN_CHARTERS = {"Y", "N", ALL_CHARTER}


class EnrollmentDriftError(ValueError):
    """The upstream file no longer matches the layout this parser was verified against."""


@dataclass(frozen=True)
class EnrollmentRow:
    academic_year: str
    level: str
    charter: str
    cds_code: str
    category: str
    total: Measure
    grades: dict[str, Measure]


def _cds(county: str, district: str, school: str, *, where: str) -> str:
    county, district, school = county.strip(), district.strip(), school.strip()
    code = (
        f"{county:0>2}{district:0>5}{school:0>7}"
        if school
        else f"{county:0>2}{district:0>5}0000000"
    )
    if len(code) != 14 or not code.isdigit():
        raise EnrollmentDriftError(
            f"{where}: cannot assemble a 14-digit CDS from "
            f"county={county!r} district={district!r} school={school!r}"
        )
    return code


def parse_enrollment(path: Path) -> Iterator[EnrollmentRow]:
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        header = reader.fieldnames or []
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
        if missing:
            raise EnrollmentDriftError(
                f"{path.name} is missing required columns {missing}; re-verify the layout"
            )
        for n, row in enumerate(reader, start=2):
            level = (row.get("AggregateLevel") or "").strip()
            if level not in KNOWN_LEVELS:
                raise EnrollmentDriftError(
                    f"{path.name}:{n}: AggregateLevel {level!r} is not one this parser reviewed"
                )
            charter = (row.get("Charter") or "").strip()
            if charter not in KNOWN_CHARTERS:
                raise EnrollmentDriftError(
                    f"{path.name}:{n}: Charter {charter!r} is not one this parser "
                    f"reviewed; aggregate rows cannot be told apart without it"
                )
            where = f"{path.name}:{n}"
            district = (row.get("DistrictCode") or "").strip()
            county = (row.get("CountyCode") or "").strip()
            school = (row.get("SchoolCode") or "").strip()
            cds = (
                _cds(county, district, school, where=where)
                if level == SCHOOL_LEVEL
                else f"{county:0>2}{district:0>5}{school:0>7}".ljust(14, "0")[:14]
                if (county or district)
                else "0" * 14
            )
            yield EnrollmentRow(
                academic_year=(row.get("AcademicYear") or "").strip(),
                level=level,
                charter=charter,
                cds_code=cds,
                category=(row.get("ReportingCategory") or "").strip(),
                total=parse_cell(row.get("TOTAL_ENR"), field="TOTAL_ENR", where=where),
                grades={
                    g: parse_cell(row.get(g), field=g, where=where)
                    for g in GRADE_COLUMNS
                },
            )


def school_totals(path: Path) -> dict[str, Measure]:
    """CDS code -> all-students total enrollment, school-level rows only.

    One school publishes one all-students total. A second row for the same CDS
    code would mean the file no longer says what this parser was verified
    against, and silently keeping the last one would pick a number by file order,
    so it is drift and it stops the build.
    """
    totals: dict[str, Measure] = {}
    for row in parse_enrollment(path):
        if row.level == SCHOOL_LEVEL and row.category == TOTAL_CATEGORY:
            if row.cds_code in totals:
                raise EnrollmentDriftError(
                    f"{path.name}: CDS {row.cds_code} has more than one school-level "
                    f"{TOTAL_CATEGORY} row; the file's grain is not what was verified"
                )
            totals[row.cds_code] = row.total
    return totals
