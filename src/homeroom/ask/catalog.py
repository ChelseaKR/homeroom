"""The measures the ask layer may look up: a subset of what a school page shows.

A :class:`MeasureSpec` names one figure a page renders, in the vocabulary the
structuring step hands the model and the verifier checks against. The catalog
is derived from the same constants the renderer uses (grade columns, subgroup
families, D3 categories), so a measure the catalog carries is one the page can
show, and the two cannot drift apart in that direction.

Measure keys:

* ``enrollment.total``, ``enrollment.grade.<GR_xx>``, ``enrollment.group.<code>``
  from D2 (counts of students on Census Day);
* ``absenteeism.total``, ``absenteeism.group.<code>`` from D3 (rates, percent).

Nothing here is a score, and nothing combines two keys. Teacher assignments
(D5) are deliberately absent, and the reason changed on 2026-09-05. It used to
be that no D5 number was published anywhere, so the catalog of what is published
could not carry one. ADR 0005 publishes D5 on the pages and deliberately does not
add it here: a measure in this catalog needs a corpus topic for its definitions,
verifier cases for its unit and its suppression wording, and a live evaluation
run before any sentence about it reaches a reader. That is a decision with its
own cost and it has not been made. Until it is, a question about teaching
assignments is outside what this layer can answer, and ``ask_refusal_outside``
says so by naming the figures the *answer* can draw on rather than the figures
the page carries.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeroom.enrollment import GRADE_COLUMNS
from homeroom.i18n import (
    Locale,
    absenteeism_category_name,
    category_name,
    family_name,
    grade_name,
)
from homeroom.profiles import ABSENTEEISM_SUBGROUP_FAMILIES, SUBGROUP_FAMILIES

ENROLLMENT = "enrollment"
ABSENTEEISM = "absenteeism"
FAMILIES: tuple[str, ...] = (ENROLLMENT, ABSENTEEISM)
"""The measure families, which are also the corpus topics a definition cites."""

UNITS: dict[str, str] = {ENROLLMENT: "students", ABSENTEEISM: "%"}
"""How a published number in each family reads: a count, or a percent."""


@dataclass(frozen=True)
class MeasureSpec:
    key: str
    family: str
    code: str
    """The CDE reporting-category or grade code, or ``TA`` for a total."""
    group: str | None
    """The subgroup family (``race_ethnicity``...) or ``None`` for totals/grades."""

    @property
    def unit(self) -> str:
        return UNITS[self.family]

    def label(self, locale: Locale) -> str:
        """What a family reads instead of the code, in one language."""
        if self.family == ABSENTEEISM:
            return absenteeism_category_name(locale, self.code)
        if self.key.startswith("enrollment.grade."):
            return grade_name(locale, self.code)
        return category_name(locale, self.code)

    def group_label(self, locale: Locale) -> str | None:
        return family_name(locale, self.group) if self.group else None


def _build() -> dict[str, MeasureSpec]:
    specs: list[MeasureSpec] = [
        MeasureSpec(key="enrollment.total", family=ENROLLMENT, code="TA", group=None)
    ]
    specs.extend(
        MeasureSpec(
            key=f"enrollment.grade.{grade}", family=ENROLLMENT, code=grade, group=None
        )
        for grade in GRADE_COLUMNS
    )
    specs.extend(
        MeasureSpec(
            key=f"enrollment.group.{code}", family=ENROLLMENT, code=code, group=group
        )
        for group, codes in SUBGROUP_FAMILIES.items()
        for code in codes
    )
    specs.append(
        MeasureSpec(key="absenteeism.total", family=ABSENTEEISM, code="TA", group=None)
    )
    specs.extend(
        MeasureSpec(
            key=f"absenteeism.group.{code}", family=ABSENTEEISM, code=code, group=group
        )
        for group, codes in ABSENTEEISM_SUBGROUP_FAMILIES.items()
        for code in codes
    )
    return {spec.key: spec for spec in specs}


CATALOG: dict[str, MeasureSpec] = _build()
"""Every measure the ask layer may name, keyed, in page order."""


def describe_catalog(locale: Locale) -> str:
    """The catalog as the model reads it: one line per measure, key then label.

    Deterministic, so the system prompt it lands in caches: same keys, same
    order, same words every time.
    """
    lines: list[str] = []
    for spec in CATALOG.values():
        group = spec.group_label(locale)
        where = f" [{group}]" if group else ""
        lines.append(f"{spec.key}: {spec.label(locale)}{where} ({spec.unit})")
    return "\n".join(lines)
