"""District and statewide figures to read a school's numbers against.

A school's enrollment count means little alone. Sixty students in a grade is
ordinary in one district and the whole grade in another, and the README's promise
is that each measure appears "beside the statewide and district context needed to
read it". This module supplies that context for both D2 (enrollment,
:class:`EnrollmentContext`) and D3 (chronic absenteeism,
:class:`AbsenteeismContext`), under one rule that decides everything else about
how each is built:

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
published nothing renders as nothing. Aggregate rows in the acquired D2 file happen
never to mask their totals, but that is a property of one file and not a promise
about the next one, so the type carries the possibility either way.

D3's aggregate rows need one more piece of care than D2's: charter status and DASS
(Dashboard Alternative School Status) are two *independent* dimensions in that file,
each an ``All``/``Yes``/``No`` value, where D2 has only the one charter dimension.
The genuine district- or state-wide rate is the row where both read ``All``;
:func:`load_absenteeism_context` accepts no other, the same way :func:`load_context`
accepts only D2's single ``ALL_CHARTER``.

D5 (teacher assignment monitoring, ADR 0005) needs the same care over six
dimensions rather than one or two: charter, DASS, school grade span, teacher
experience level, teacher credential level and subject area all have to read the
file's own aggregated value for a row to mean "this district, every school,
every subject, every teacher". :func:`load_assignment_context` accepts no other
row, and fails closed -- no statewide total, or two rows for one entity, stops
the build -- rather than publishing one slice of a district as the district.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from homeroom.absenteeism import (
    ALL_VALUE as ABSENTEEISM_ALL,
)
from homeroom.absenteeism import (
    DISTRICT_LEVEL as ABSENTEEISM_DISTRICT_LEVEL,
)
from homeroom.absenteeism import (
    STATE_LEVEL as ABSENTEEISM_STATE_LEVEL,
)
from homeroom.absenteeism import (
    TOTAL_CATEGORY as ABSENTEEISM_TOTAL_CATEGORY,
)
from homeroom.absenteeism import (
    AbsenteeismDriftError,
    parse_absenteeism,
)
from homeroom.assignments import (
    CHARTER_ALL as ASSIGNMENT_CHARTER_ALL,
)
from homeroom.assignments import (
    CREDENTIAL_ALL,
    DASS_ALL,
    EXPERIENCE_ALL,
    GRADE_SPAN_ALL,
    OUTCOMES,
    SUBJECT_TOTAL,
    AssignmentDriftError,
    AssignmentRow,
    parse_assignments,
)
from homeroom.assignments import (
    DISTRICT_LEVEL as ASSIGNMENT_DISTRICT_LEVEL,
)
from homeroom.assignments import (
    STATE_LEVEL as ASSIGNMENT_STATE_LEVEL,
)
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


class AbsenteeismContextDriftError(AbsenteeismDriftError):
    """D3's aggregate rows are not shaped the way this module was verified against."""


@dataclass(frozen=True)
class AbsenteeismAggregate:
    """One entity's published chronic-absenteeism rates, by reporting category.

    Every value is a :class:`~homeroom.measures.Measure`, so a withheld district
    rate stays withheld all the way to the page, the same as :class:`AggregateFigures`.
    """

    cds_code: str
    categories: dict[str, Measure] = field(default_factory=dict)

    def category(self, code: str) -> Measure:
        return self.categories.get(code, Measure.not_reported())


@dataclass(frozen=True)
class AbsenteeismContext:
    """Every district's chronic-absenteeism rates, plus the state's, read from
    CDE's own ``Charter School == All`` and ``DASS == All`` rows."""

    districts: dict[str, AbsenteeismAggregate]
    state: AbsenteeismAggregate
    academic_year: str

    def for_district(self, cds_code: str) -> AbsenteeismAggregate:
        key = district_key(cds_code)
        return self.districts.get(key, AbsenteeismAggregate(cds_code=key))


def load_absenteeism_context(path: Path) -> AbsenteeismContext:
    """Read district and statewide chronic-absenteeism rates from D3's own rows.

    Only rows where both ``Charter School`` and ``DASS`` read ``All`` are read, at
    district and state level: D3 crosses two independent All/Yes/No dimensions
    where D2 has one, so both have to read ``All`` for the row to mean "every
    school, regardless of charter or DASS status" rather than one slice of it. A
    duplicate ``(entity, reporting category)`` pair is drift, the same rule
    :func:`load_context` enforces for D2.
    """
    districts: dict[str, dict[str, Measure]] = {}
    state_categories: dict[str, Measure] = {}
    years: set[str] = set()
    seen: set[tuple[str, str, str]] = set()

    for row in parse_absenteeism(path):
        if row.level not in (ABSENTEEISM_DISTRICT_LEVEL, ABSENTEEISM_STATE_LEVEL):
            continue
        if row.charter != ABSENTEEISM_ALL or row.dass != ABSENTEEISM_ALL:
            continue
        key = (row.level, row.cds_code, row.category)
        if key in seen:
            raise AbsenteeismContextDriftError(
                f"{path.name}: {row.level}-level {row.cds_code} has more than one "
                f"Charter School=DASS={ABSENTEEISM_ALL!r} row for category "
                f"{row.category!r}; the file's grain is not what this module was "
                "verified against"
            )
        seen.add(key)
        years.add(row.academic_year)

        if row.level == ABSENTEEISM_STATE_LEVEL:
            state_categories[row.category] = row.rate
            continue
        districts.setdefault(row.cds_code, {})[row.category] = row.rate

    if ABSENTEEISM_TOTAL_CATEGORY not in state_categories:
        raise AbsenteeismContextDriftError(
            f"{path.name}: no statewide Charter School=DASS={ABSENTEEISM_ALL!r} row "
            f"for category {ABSENTEEISM_TOTAL_CATEGORY!r}; statewide context cannot "
            "be published without it"
        )
    if len(years) != 1:
        raise AbsenteeismContextDriftError(
            f"{path.name}: aggregate rows span academic years {sorted(years)}; "
            "context must come from one year"
        )

    return AbsenteeismContext(
        districts={
            code: AbsenteeismAggregate(cds_code=code, categories=categories)
            for code, categories in districts.items()
        },
        state=AbsenteeismAggregate(cds_code=STATE_CDS, categories=state_categories),
        academic_year=years.pop(),
    )


class AssignmentContextDriftError(AssignmentDriftError):
    """D5's aggregate rows are not shaped the way this module was verified against."""


@dataclass(frozen=True)
class AssignmentAggregate:
    """One entity's published teacher assignment outcomes, as CDE published them.

    ``total`` is the entity's total teaching FTE; ``counts`` and ``percents`` are
    the seven outcome cells, each a :class:`~homeroom.measures.Measure`, so a
    withheld district cell stays withheld all the way to the page. Nothing here
    is summed from schools and no percent is divided out of a count.
    """

    cds_code: str
    total: Measure = field(default_factory=Measure.not_reported)
    counts: dict[str, Measure] = field(default_factory=dict)
    percents: dict[str, Measure] = field(default_factory=dict)

    def count(self, outcome: str) -> Measure:
        return self.counts.get(outcome, Measure.not_reported())

    def percent(self, outcome: str) -> Measure:
        return self.percents.get(outcome, Measure.not_reported())


@dataclass(frozen=True)
class AssignmentContext:
    """Every district's assignment outcomes, plus the state's, from CDE's own rows."""

    districts: dict[str, AssignmentAggregate]
    state: AssignmentAggregate
    academic_year: str

    def for_district(self, cds_code: str) -> AssignmentAggregate:
        key = district_key(cds_code)
        return self.districts.get(key, AssignmentAggregate(cds_code=key))


def _is_whole_entity_row(row: AssignmentRow) -> bool:
    """True for the one row per aggregate entity that describes all of it.

    Six dimensions have to read their aggregated value at once. Charter School
    and DASS are the words ``All``; School Grade Span, Teacher Experience Level
    and Teacher Credential Level are ``ALL``; Subject Area is ``TA``. A row
    missing any one of them is a slice -- one grade span, or one subject, or the
    charter schools only -- and publishing it as the district would be the same
    error D2's three charter rows invite, where taking the first match makes a
    district fifteen times too small.

    Grade span is part of the filter here and deliberately is not part of
    :func:`homeroom.assignments._is_school_total`: a school-level row is never
    ``ALL`` there, because it already carries the one span that school serves,
    while an aggregate entity spans several and publishes a row for each.
    """
    return (
        row.charter == ASSIGNMENT_CHARTER_ALL
        and row.dass == DASS_ALL
        and row.grade_span == GRADE_SPAN_ALL
        and row.experience_level == EXPERIENCE_ALL
        and row.credential_level == CREDENTIAL_ALL
        and row.subject_area == SUBJECT_TOTAL
    )


def load_assignment_context(path: Path) -> AssignmentContext:
    """Read district and statewide assignment outcomes from D5's own rows.

    Only the whole-entity rows described in :func:`_is_whole_entity_row` are
    read, at district and state level, and a second such row for one entity is
    drift rather than a row to overwrite: keeping the last one seen would pick a
    published number by file order. A file with no statewide row stops the build,
    because a page cannot claim statewide context it does not have and must not
    quietly show nothing where the state published something.
    """
    districts: dict[str, AssignmentAggregate] = {}
    state: AssignmentAggregate | None = None
    years: set[str] = set()
    seen: set[tuple[str, str]] = set()

    for row in parse_assignments(path):
        if row.level not in (ASSIGNMENT_DISTRICT_LEVEL, ASSIGNMENT_STATE_LEVEL):
            continue
        if not _is_whole_entity_row(row):
            continue
        key = (row.level, row.cds_code)
        if key in seen:
            raise AssignmentContextDriftError(
                f"{path.name}: {row.level}-level {row.cds_code} has more than one "
                "whole-entity row (Charter School and DASS 'All', grade span, "
                "experience and credential 'ALL', subject area 'TA'); the file's "
                "grain is not what this module was verified against"
            )
        seen.add(key)
        years.add(row.academic_year)
        figures = AssignmentAggregate(
            cds_code=row.cds_code,
            total=row.total,
            counts={outcome: row.counts[outcome] for outcome in OUTCOMES},
            percents={outcome: row.percents[outcome] for outcome in OUTCOMES},
        )
        if row.level == ASSIGNMENT_STATE_LEVEL:
            state = figures
            continue
        districts[row.cds_code] = figures

    if state is None:
        raise AssignmentContextDriftError(
            f"{path.name}: no statewide whole-entity row; statewide context "
            "cannot be published without it"
        )
    if len(years) != 1:
        raise AssignmentContextDriftError(
            f"{path.name}: aggregate rows span academic years {sorted(years)}; "
            "context must come from one year"
        )

    return AssignmentContext(
        districts=districts, state=state, academic_year=years.pop()
    )
