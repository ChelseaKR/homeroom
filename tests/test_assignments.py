"""Teacher assignment outcomes: every rendering case, and drift refusal.

The fixture is synthetic. D5 has not been acquired, so these tests pin the parser's
behaviour against the documented file structure rather than against a file in hand,
and they are written to fail loudly if the real file turns out to disagree.
"""

from pathlib import Path

import pytest

from homeroom.assignments import (
    OUTCOME_COLUMNS,
    OUTCOME_NAMES,
    OUTCOMES,
    REQUIRED_COLUMNS,
    AssignmentDriftError,
    parse_assignments,
    school_outcomes,
)
from homeroom.measures import (
    MeasureStatus,
    SuppressedValueError,
    UnparseableCellError,
)

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "tamo.sample.txt"

EXAMPLE = "01100170112345"
CHARTER = "01100170154321"
CLOSED = "01100170167890"
UNJOINED = "57726786056246"

HEADER = "\t".join(REQUIRED_COLUMNS) + "\n"


def write(tmp_path: Path, rows: str, *, header: str = HEADER) -> Path:
    path = tmp_path / "tamo.txt"
    path.write_text(header + rows, encoding="utf-8")
    return path


def row(**overrides: str) -> str:
    cells = {
        "AcademicYear": "2024-25",
        "AggregateLevel": "S",
        "CountyCode": "01",
        "DistrictCode": "10017",
        "SchoolCode": "0112345",
        "TotalAssignments": "40",
    }
    for count, percent in OUTCOME_COLUMNS.values():
        cells[count] = "0"
        cells[percent] = "0.0"
    cells.update(overrides)
    return "\t".join(cells[column] for column in REQUIRED_COLUMNS) + "\n"


# --- the four rendering cases, on one real-shaped fixture ------------------


def test_fixture_parses_and_separates_aggregate_levels() -> None:
    rows = list(parse_assignments(FIXTURE))
    assert [r.level for r in rows] == ["T", "D", "S", "S", "S", "S"]
    assert all(len(r.cds_code) == 14 and r.cds_code.isdigit() for r in rows)
    assert {r.academic_year for r in rows} == {"2024-25"}


def test_school_outcomes_keys_on_the_fourteen_digit_cds_only() -> None:
    assert set(school_outcomes(FIXTURE)) == {EXAMPLE, CHARTER, CLOSED, UNJOINED}


def test_normal_values_are_the_published_cells() -> None:
    example = school_outcomes(FIXTURE)[EXAMPLE]
    assert example.total.number() == 40
    assert example.counts["clear"].number() == 34
    assert example.percents["clear"].number() == 85.0
    assert example.counts["out_of_field"].number() == 4
    assert example.percents["out_of_field"].number() == 10.0


def test_a_published_zero_stays_a_zero() -> None:
    example = school_outcomes(FIXTURE)[EXAMPLE]
    assert example.counts["intern"].is_zero
    assert example.percents["intern"].is_zero
    assert example.counts["intern"].status is MeasureStatus.REPORTED


def test_a_masked_outcome_stays_unreadable_never_zero() -> None:
    example = school_outcomes(FIXTURE)[EXAMPLE]
    assert example.counts["ineffective"].status is MeasureStatus.SUPPRESSED
    assert example.percents["ineffective"].status is MeasureStatus.SUPPRESSED
    assert not example.counts["ineffective"].is_zero
    with pytest.raises(SuppressedValueError, match="no published number"):
        example.counts["ineffective"].number()


def test_a_missing_outcome_differs_from_a_masked_one() -> None:
    example = school_outcomes(FIXTURE)[EXAMPLE]
    assert example.counts["unknown"].status is MeasureStatus.NOT_REPORTED
    assert example.percents["unknown"].status is MeasureStatus.NOT_REPORTED
    assert not example.counts["unknown"].is_zero


def test_a_small_school_can_be_withheld_entirely() -> None:
    charter = school_outcomes(FIXTURE)[CHARTER]
    assert charter.total.status is MeasureStatus.SUPPRESSED
    assert all(m.status is MeasureStatus.SUPPRESSED for m in charter.counts.values())
    assert all(m.status is MeasureStatus.SUPPRESSED for m in charter.percents.values())


def test_no_outcome_is_the_complement_of_a_masked_one() -> None:
    """Example Elementary publishes 40 assignments with 34 + 4 + 0 visible.

    The two withheld outcomes hold 2 assignments and 5.0 percent between them.
    Neither number appears anywhere in the fixture, so if the parser ever reports
    one it computed a value the state withheld.
    """
    reported = [
        measure.number()
        for outcomes in school_outcomes(FIXTURE).values()
        for measure in (
            outcomes.total,
            *outcomes.counts.values(),
            *outcomes.percents.values(),
        )
        if measure.status is MeasureStatus.REPORTED
    ]
    assert 2 not in reported
    assert 5.0 not in reported


def test_every_reported_value_is_verbatim_in_the_source_file() -> None:
    published = set()
    for line in FIXTURE.read_text(encoding="utf-8").splitlines()[1:]:
        for cell in line.split("\t"):
            try:
                published.add(float(cell))
            except ValueError:
                continue
    for outcomes in school_outcomes(FIXTURE).values():
        for measure in (
            outcomes.total,
            *outcomes.counts.values(),
            *outcomes.percents.values(),
        ):
            if measure.status is MeasureStatus.REPORTED:
                assert measure.number() in published


# --- drift refusal --------------------------------------------------------


def test_missing_required_column_is_a_hard_failure(tmp_path: Path) -> None:
    path = tmp_path / "tamo.txt"
    path.write_text(
        "AcademicYear\tAggregateLevel\tTotalAssignments\n2024-25\tS\t40\n",
        encoding="utf-8",
    )
    with pytest.raises(AssignmentDriftError, match="missing required columns"):
        list(parse_assignments(path))


def test_renamed_outcome_column_is_drift_not_a_silent_gap(tmp_path: Path) -> None:
    header = HEADER.replace("ClearCount", "ClearlyAssignedCount")
    path = write(tmp_path, row(), header=header)
    with pytest.raises(AssignmentDriftError, match="ClearCount"):
        list(parse_assignments(path))


def test_unknown_aggregate_level_refuses(tmp_path: Path) -> None:
    path = write(tmp_path, row(AggregateLevel="X"))
    with pytest.raises(AssignmentDriftError, match="not one this parser reviewed"):
        list(parse_assignments(path))


def test_malformed_cds_code_refuses_rather_than_joins(tmp_path: Path) -> None:
    path = write(tmp_path, row(SchoolCode="011234X"))
    with pytest.raises(AssignmentDriftError, match="14-digit CDS"):
        list(parse_assignments(path))


def test_overlong_cds_parts_refuse(tmp_path: Path) -> None:
    path = write(tmp_path, row(CountyCode="011"))
    with pytest.raises(AssignmentDriftError, match="14-digit CDS"):
        list(parse_assignments(path))


def test_unknown_sentinel_refuses_rather_than_guesses(tmp_path: Path) -> None:
    path = write(tmp_path, row(ClearCount="N/A"))
    with pytest.raises(UnparseableCellError, match="not reviewed"):
        list(parse_assignments(path))


def test_a_percent_sign_is_an_unreviewed_format_not_a_number(tmp_path: Path) -> None:
    """If the acquired file writes shares as "85.0%", the build stops and the
    format gets reviewed. Stripping the sign here would be a guess."""
    path = write(tmp_path, row(ClearPercent="85.0%"))
    with pytest.raises(UnparseableCellError, match="not reviewed"):
        list(parse_assignments(path))


def test_two_rows_for_one_school_is_drift(tmp_path: Path) -> None:
    path = write(tmp_path, row() + row())
    with pytest.raises(AssignmentDriftError, match="two school-level rows"):
        school_outcomes(path)


# --- the column contract is the one thing to re-verify --------------------


def test_outcome_names_cover_every_outcome_and_read_as_plain_language() -> None:
    assert tuple(OUTCOME_NAMES) == OUTCOMES
    assert tuple(OUTCOME_COLUMNS) == OUTCOMES
    assert all(name.strip() and name[0].isupper() for name in OUTCOME_NAMES.values())


def test_required_columns_are_exactly_the_contract(tmp_path: Path) -> None:
    """Every column the parser reads is declared, and none is read undeclared."""
    assert len(REQUIRED_COLUMNS) == len(set(REQUIRED_COLUMNS))
    for count, percent in OUTCOME_COLUMNS.values():
        assert count in REQUIRED_COLUMNS
        assert percent in REQUIRED_COLUMNS
    path = write(tmp_path, row())
    parsed = next(parse_assignments(path))
    assert set(parsed.counts) == set(OUTCOMES)
    assert set(parsed.percents) == set(OUTCOMES)
