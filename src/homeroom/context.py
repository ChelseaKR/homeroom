"""District and statewide figures to read a school's numbers against.

A school's enrollment count means little alone. Sixty students in a grade is
ordinary in one district and the whole grade in another, and the README's promise
is that each measure appears "beside the statewide and district context needed to
read it". This module supplies that context, under one rule that decides
everything else about how it is built:

**Homeroom never adds school rows together to make a district or a state figure.**

That rule is not fastidiousness. CDE masks small cells, and a masked cell is a
number the state measured and deliberately withheld. Summing a column that
contains masks gives an answer that is wrong; skipping the masked cells and
summing the rest gives an answer that is wrong *and* looks clean, because the
total silently excludes exactly the students the mask was protecting. Either way
the page would publish a figure the state never published, and the reader would
have no way to tell. So Homeroom reads CDE's own district and state rows, which
are in the same file, computed by the people who hold the unmasked data.

Selecting those rows takes one piece of care. Every aggregate entity is published
three times: charter schools, non-charter schools, and both together, keyed by
:data:`homeroom.enrollment.ALL_CHARTER`. In the acquired 2025-26 file Davis Joint
Unified's three district rows read 561, 7,682 and 8,243 students for the same
reporting category. A reader that takes the first matching row can publish a
district figure fifteen times too small. Only the ``ALL`` row answers "how big is
the district", and this module accepts no other, failing closed if it finds none
or finds two.

The context figures are :class:`~homeroom.measures.Measure` values like any
other, so a masked district cell renders as withheld and a district that
published nothing renders as nothing. Aggregate rows in the acquired file happen
never to mask their totals, but that is a property of one file and not a promise
about the next one, so the type carries the possibility either way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from homeroom.enrollment import (
    ALL_CHARTER,
    DISTRICT_LEVEL,
    STATE_LEVEL,
    TOTAL_CATEGORY,
    EnrollmentDriftError,
    parse_enrollment,
)
from homeroom.measures import Measure

STATE_CDS = "0" * 14
"""The CDS code the parser assigns to statewide rows, which carry no entity code."""


class ContextDriftError(EnrollmentDriftError):
    """The aggregate rows are not shaped the way this module was verified against."""


@dataclass(frozen=True)
class AggregateFigures:
    """One entity's published figures, in the same shape as a school's.

    ``total`` and every value in ``grades`` and ``subgroups`` is a Measure, so a
    withheld district cell stays withheld all the way to the page.
    """

    cds_code: str
    total: Measure = field(default_factory=Measure.not_reported)
    grades: dict[str, Measure] = field(default_factory=dict)
    subgroups: dict[str, Measure] = field(default_factory=dict)

    def grade(self, column: str) -> Measure:
        return self.grades.get(column, Measure.not_reported())

    def subgroup(self, category: str) -> Measure:
        return self.subgroups.get(category, Measure.not_reported())


@dataclass(frozen=True)
class EnrollmentContext:
    """Every district's figures, plus the state's, read from CDE's own rows."""

    districts: dict[str, AggregateFigures]
    state: AggregateFigures
    academic_year: str

    def for_district(self, cds_code: str) -> AggregateFigures:
        """The district context for a school's CDS code.

        A school's district is the first seven digits of its CDS code with the
        school part zeroed, which is exactly the key the parser builds for
        district rows. A district with no published rows is absent rather than
        invented, and renders as nothing published.
        """
        return self.districts.get(
            district_key(cds_code), AggregateFigures(cds_code=district_key(cds_code))
        )


def district_key(cds_code: str) -> str:
    """The district-level CDS key for a school-level CDS code."""
    return f"{cds_code[:7]:0<7}".ljust(14, "0")[:14]


def load_context(path: Path) -> EnrollmentContext:
    """Read district and statewide figures from the enrollment file's own rows.

    Only ``ALL`` charter rows are read, at district and state level. A duplicate
    ``(entity, reporting category)`` pair is drift and stops the build, because
    keeping the last row seen would pick a published number by file order.
    """
    districts: dict[str, dict[str, Measure]] = {}
    district_grades: dict[str, dict[str, Measure]] = {}
    district_totals: dict[str, Measure] = {}
    state_subgroups: dict[str, Measure] = {}
    state_grades: dict[str, Measure] = {}
    state_total: Measure | None = None
    years: set[str] = set()
    seen: set[tuple[str, str, str]] = set()

    for row in parse_enrollment(path):
        if row.level not in (DISTRICT_LEVEL, STATE_LEVEL):
            continue
        if row.charter != ALL_CHARTER:
            continue
        key = (row.level, row.cds_code, row.category)
        if key in seen:
            raise ContextDriftError(
                f"{path.name}: {row.level}-level {row.cds_code} has more than one "
                f"{ALL_CHARTER} row for category {row.category!r}; the file's grain "
                f"is not what this module was verified against"
            )
        seen.add(key)
        years.add(row.academic_year)

        if row.level == STATE_LEVEL:
            if row.category == TOTAL_CATEGORY:
                state_total = row.total
                state_grades = dict(row.grades)
            state_subgroups[row.category] = row.total
            continue

        if row.category == TOTAL_CATEGORY:
            district_totals[row.cds_code] = row.total
            district_grades[row.cds_code] = dict(row.grades)
        districts.setdefault(row.cds_code, {})[row.category] = row.total

    if state_total is None:
        raise ContextDriftError(
            f"{path.name}: no statewide {ALL_CHARTER} row for category "
            f"{TOTAL_CATEGORY!r}; statewide context cannot be published without it"
        )
    if len(years) != 1:
        raise ContextDriftError(
            f"{path.name}: aggregate rows span academic years {sorted(years)}; "
            f"context must come from one year"
        )

    return EnrollmentContext(
        districts={
            code: AggregateFigures(
                cds_code=code,
                total=district_totals.get(code, Measure.not_reported()),
                grades=district_grades.get(code, {}),
                subgroups=subgroups,
            )
            for code, subgroups in districts.items()
        },
        state=AggregateFigures(
            cds_code=STATE_CDS,
            total=state_total,
            grades=state_grades,
            subgroups=state_subgroups,
        ),
        academic_year=years.pop(),
    )
