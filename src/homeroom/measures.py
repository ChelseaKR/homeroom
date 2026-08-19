"""The null-never-zero machinery: how a CDE cell becomes a value Homeroom may show.

CDE masks small cells (published as ``*``) to protect students, and leaves other cells
empty when a school did not report. Those are three different facts:

    reported        a number the state published, including a genuine zero
    suppressed      the state measured it and deliberately withheld it
    not reported    nothing was published at all

The whole project rests on never collapsing them. A :class:`Measure` makes the collapse
impossible at the type level: the numeric value of a non-reported measure cannot be read,
so a rendering layer cannot accidentally chart a masked cell as ``0``. Anything a parser
cannot classify is a hard error, never a guess.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

SUPPRESSION_MARK = "*"
"""CDE's published mask for cells withheld under its small-cell rule."""

PUBLISHED_NUMBER = re.compile(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", re.ASCII)
"""The shape of a number CDE publishes, stated rather than left to :func:`float`.

An optional sign, digits either plain or grouped in thousands with commas, and an
optional decimal fraction. Measured against the acquired 2025-26 D2 file
(2026-08-18): every one of its 2,706,792 populated numeric cells is a bare run of
ASCII digits, and the other 1,329,558 are the mask. Commas and fractions are here
because the D3 and D5 files publish rates and percents, which the existing tests
pin.

The pattern exists because :func:`float` accepts far more than a data file ever
means. ``float("nan")`` and ``float("inf")`` succeed, and NaN is the single most
common way an upstream export writes *no value*, so the string that most clearly
says "nothing was measured" would otherwise become a published figure. ``float``
also honours PEP 515 digit separators, so a garbled ``1_0`` reads as ten; it
accepts exponents CDE does not write; and ``\\d`` outside :data:`re.ASCII` matches
Arabic-Indic and fullwidth digits, so a mojibaked cell would parse as a number
nobody typed. Each of those is the project's own failure mode in miniature: a cell
that is not a published number becoming one, silently, in a statement about a real
school.

Anchoring the grouping also matters. The parser strips commas before converting,
so an ungrouped ``1,23`` used to read as one hundred and twenty-three. A malformed
group is drift; it is not a number to reinterpret.
"""


class MeasureStatus(Enum):
    REPORTED = "reported"
    SUPPRESSED = "suppressed"
    NOT_REPORTED = "not_reported"


class SuppressedValueError(ValueError):
    """A caller tried to read a number the state did not publish."""


class UnparseableCellError(ValueError):
    """A cell matched neither a number, the suppression mark, nor emptiness."""


@dataclass(frozen=True)
class Measure:
    status: MeasureStatus
    _value: float | None = None

    @classmethod
    def reported(cls, value: float) -> Measure:
        return cls(MeasureStatus.REPORTED, float(value))

    @classmethod
    def suppressed(cls) -> Measure:
        return cls(MeasureStatus.SUPPRESSED)

    @classmethod
    def not_reported(cls) -> Measure:
        return cls(MeasureStatus.NOT_REPORTED)

    def number(self) -> float:
        """The published number. Raises unless the state actually published one."""
        if self.status is not MeasureStatus.REPORTED or self._value is None:
            raise SuppressedValueError(
                f"no published number to read: measure is {self.status.value}"
            )
        return self._value

    @property
    def is_zero(self) -> bool:
        """True only for a genuine published zero, never for masked or missing cells."""
        return self.status is MeasureStatus.REPORTED and self._value == 0


def parse_cell(raw: object, *, field: str, where: str) -> Measure:
    """Classify one source cell. Refuses to guess.

    ``None`` and empty/whitespace strings are *not reported*. The suppression mark is
    *suppressed*. A cell shaped like a number CDE publishes
    (:data:`PUBLISHED_NUMBER`: counts, and the percents and rates other files carry)
    is *reported*. Everything else raises: an unrecognized sentinel upstream
    must stop the build, because every guess here becomes a statement about a real school.

    Two failures are refused rather than converted, and both are the same mistake:

    *A cell that is not a published number.* The shape is checked before conversion,
    so the strings :func:`float` happens to accept but a data file does not mean as a
    number — ``nan``, ``inf``, ``1_0``, ``1e3``, non-ASCII digits — stop the build
    instead of becoming figures. ``nan`` is the important one: it is how an export
    writes a value it does not have, and reading it as a published number is exactly
    the collapse this module exists to prevent.

    *A number too large to hold.* A digit run long enough to overflow a float
    converts to infinity without complaint. Infinity is not a figure any state
    published, and printing it beside a school's name would be a lie in the loudest
    possible register, so it raises as well.
    """
    if raw is None:
        return Measure.not_reported()
    text = str(raw).strip()
    if text == "":
        return Measure.not_reported()
    if text == SUPPRESSION_MARK:
        return Measure.suppressed()
    if not PUBLISHED_NUMBER.fullmatch(text):
        raise UnparseableCellError(
            f"{where}.{field}: cell {text!r} is neither a number, {SUPPRESSION_MARK!r}, "
            "nor empty; upstream added a sentinel this project has not reviewed"
        )
    value = float(text.replace(",", ""))
    if not math.isfinite(value):
        raise UnparseableCellError(
            f"{where}.{field}: cell {text!r} does not fit in a float and became "
            f"{value}; no state published that, so it is drift rather than a figure"
        )
    return Measure.reported(value)


def coverage(measures: Iterable[Measure]) -> dict[str, int]:
    """How many measures landed in each status. Coverage is a first-class output:
    absence is published as absence, not hidden by omission."""
    counts = Counter(m.status.value for m in measures)
    return {status.value: counts.get(status.value, 0) for status in MeasureStatus}
