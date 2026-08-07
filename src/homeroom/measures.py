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

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

SUPPRESSION_MARK = "*"
"""CDE's published mask for cells withheld under its small-cell rule."""


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
    *suppressed*. A parseable number (CDE publishes counts and percents; commas appear in
    some files) is *reported*. Everything else raises: an unrecognized sentinel upstream
    must stop the build, because every guess here becomes a statement about a real school.
    """
    if raw is None:
        return Measure.not_reported()
    text = str(raw).strip()
    if text == "":
        return Measure.not_reported()
    if text == SUPPRESSION_MARK:
        return Measure.suppressed()
    try:
        return Measure.reported(float(text.replace(",", "")))
    except ValueError:
        raise UnparseableCellError(
            f"{where}.{field}: cell {text!r} is neither a number, {SUPPRESSION_MARK!r}, "
            "nor empty; upstream added a sentinel this project has not reviewed"
        ) from None


def coverage(measures: Iterable[Measure]) -> dict[str, int]:
    """How many measures landed in each status. Coverage is a first-class output:
    absence is published as absence, not hidden by omission."""
    counts = Counter(m.status.value for m in measures)
    return {status.value: counts.get(status.value, 0) for status in MeasureStatus}
