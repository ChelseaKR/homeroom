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


@pytest.mark.parametrize(
    "cell", ["nan", "NaN", "-nan", "inf", "-inf", "Infinity", "infinity"]
)
def test_the_words_for_no_value_are_not_read_as_values(cell: str) -> None:
    """``float`` accepts every one of these. They are the opposite of a figure.

    NaN is how an export writes a value it does not have, which makes it the single
    worst thing to classify as *reported*: the cell that most clearly says nothing
    was measured would render styled as a number the state published, and land in
    ``schools.json`` as the literal ``NaN``, which is not valid JSON.
    """
    with pytest.raises(UnparseableCellError, match="not reviewed"):
        parse_cell(cell, field="TOTAL_ENR", where="test")


@pytest.mark.parametrize(
    ("cell", "would_have_read_as"),
    [
        ("1_0", "ten, via PEP 515 digit separators"),
        ("1_000", "one thousand, same"),
        ("1e3", "one thousand, an exponent CDE does not write"),
        ("1,23", "one hundred and twenty-three, from a malformed thousands group"),
        (".5", "a half, from a cell with no integer part"),
        # Written as escapes rather than pasted: a reviewer should be able to see
        # which characters these are, and they are indistinguishable from ASCII
        # digits in most fonts, which is the whole reason they are dangerous.
        ("\uff11\uff12", "twelve, from fullwidth digits"),
        ("\u0665", "five, from an Arabic-Indic digit"),
        ("12%", "twelve, with the unit silently dropped"),
    ],
)
def test_text_that_is_not_a_published_number_refuses(
    cell: str, would_have_read_as: str
) -> None:
    """Each of these converts cleanly and means something else, or nothing.

    The parser is not entitled to reinterpret them: every one becomes a statement
    about a real school. ``would_have_read_as`` records what each used to produce,
    so this list reads as the inventory of near-misses it is.
    """
    with pytest.raises(UnparseableCellError, match="not reviewed"):
        parse_cell(cell, field="TOTAL_ENR", where="test")


def test_a_figure_too_large_to_hold_refuses_rather_than_becoming_infinity() -> None:
    """A digit run this long overflows a float, and the overflow is silent."""
    with pytest.raises(UnparseableCellError, match="does not fit"):
        parse_cell("9" * 400, field="TOTAL_ENR", where="test")


@pytest.mark.parametrize("cell", ["0", "17", "441", "1,234", "42.5", "0.0"])
def test_the_shapes_cde_actually_publishes_still_parse(cell: str) -> None:
    """Measured against the acquired D2 file: bare digit runs, plus the commas and
    fractions the rate and percent files carry."""
    assert parse_cell(cell, field="TOTAL_ENR", where="test").status is (
        MeasureStatus.REPORTED
    )


@pytest.mark.parametrize("cell", ["+5", "-1"])
def test_a_signed_cell_still_parses_and_is_not_read_as_a_sentinel(cell: str) -> None:
    """A sign is kept deliberately, and this test is where that decision lives.

    Sibling projects meet ``-1`` as a suppression sentinel, and it is tempting to
    treat a negative count the same way here. That would be a guess, which is the
    one thing this module may not do. A rule that an enrollment count cannot be
    negative is a fact about enrollment, so it belongs to the dataset parser that
    knows the column, not to a cell reader shared with percent and rate columns
    where a negative is meaningful.
    """
    assert parse_cell(cell, field="rate", where="test").status is (
        MeasureStatus.REPORTED
    )


def test_coverage_counts_every_status_even_at_zero() -> None:
    out = coverage([Measure.reported(1), Measure.suppressed(), Measure.suppressed()])
    assert out == {"reported": 1, "suppressed": 2, "not_reported": 0}
