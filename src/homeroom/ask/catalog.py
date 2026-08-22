"""The measures the ask layer may look up: exactly the ones a school page shows.

A :class:`MeasureSpec` names one figure a page renders, in the vocabulary the
structuring step hands the model and the verifier checks against. The catalog
is derived from the same constants the renderer uses (grade columns, subgroup
families, D3 categories), so a measure the page cannot show is a measure the
model cannot ask for, and the two cannot drift apart.

Measure keys:

* ``enrollment.total``, ``enrollment.grade.<GR_xx>``, ``enrollment.group.<code>``
  from D2 (counts of students on Census Day);
* ``absenteeism.total``, ``absenteeism.group.<code>`` from D3 (rates, percent).

Nothing here is a score, and nothing combines two keys. Teacher assignments
(D5) are deliberately absent: no D5 number is published on any page, and the
catalog is the list of what is published.
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
