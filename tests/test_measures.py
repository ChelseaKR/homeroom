"""The three-way distinction survives every path, and guessing is impossible."""

import pytest

from homeroom.measures import (
    Measure,
    MeasureStatus,
    SuppressedValueError,
    UnparseableCellError,
    coverage,
    parse_cell,
)


def test_the_three_facts_are_distinct() -> None:
    zero = parse_cell("0", field="chronic_rate", where="test")
    masked = parse_cell("*", field="chronic_rate", where="test")
    missing = parse_cell("", field="chronic_rate", where="test")
    assert zero.status is MeasureStatus.REPORTED and zero.is_zero
    assert masked.status is MeasureStatus.SUPPRESSED and not masked.is_zero
    assert missing.status is MeasureStatus.NOT_REPORTED and not missing.is_zero


def test_a_masked_cell_has_no_readable_number() -> None:
    with pytest.raises(SuppressedValueError):
        Measure.suppressed().number()
    with pytest.raises(SuppressedValueError):
        Measure.not_reported().number()


def test_reported_numbers_read_back_including_commas() -> None:
    assert parse_cell("1,234", field="enrollment", where="test").number() == 1234.0
    assert parse_cell(" 42.5 ", field="rate", where="test").number() == 42.5


def test_none_is_not_reported() -> None:
    assert (
        parse_cell(None, field="x", where="test").status is MeasureStatus.NOT_REPORTED
    )


def test_unknown_sentinel_refuses_rather_than_guesses() -> None:
    with pytest.raises(UnparseableCellError, match="not reviewed"):
        parse_cell("N/A", field="rate", where="test")


def test_coverage_counts_every_status_even_at_zero() -> None:
    out = coverage([Measure.reported(1), Measure.suppressed(), Measure.suppressed()])
    assert out == {"reported": 1, "suppressed": 2, "not_reported": 0}
