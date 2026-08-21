"""Teacher assignment outcomes: every rendering case, and drift refusal.

The fixture mirrors the real 2023-24 Teacher Assignment Monitoring Outcome file
acquired 2026-08-21 (``tamo2324.txt``, 234,206,408 bytes, 1,528,796 rows;
PROVENANCE.md D5): the same column names, the same seven outcomes (not the five
this module's provisional contract carried before acquisition), the same
FTE-fractional values, and the same whole-school-total-row selection this parser
was rewritten to make. The values themselves are still synthetic -- the fixture
does not reproduce a real school -- but the shape is the acquired file's, not a
guess.
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


def row(overrides: dict[str, str] | None = None) -> str:
    """One school-level whole-school-total row. ``overrides`` replaces cells by
    their real (spaced) column name, since those names are not valid keyword
    identifiers."""
    cells = {
        "Academic Year": "2023-24",
        "Aggregate Level": "S",
        "County Code": "01",
        "District Code": "10017",
        "School Code": "0112345",
        "Charter School": "No",
        "DASS": "No",
        "School Grade Span": "GRK6",
        "Teacher Experience Level": "ALL",
        "Teacher Credential Level": "ALL",
        "Subject Area": "TA",
        "Total FTE": "5.00",
    }
    for count, percent in OUTCOME_COLUMNS.values():
        cells[count] = "1.00"
        cells[percent] = "20.0"
    cells.update(overrides or {})
    return "\t".join(cells[column] for column in REQUIRED_COLUMNS) + "\n"


# --- the four rendering cases, on one real-shaped fixture ------------------


def test_fixture_parses_and_separates_aggregate_levels() -> None:
    rows = list(parse_assignments(FIXTURE))
    assert [r.level for r in rows] == ["T", "D", "S", "S", "S", "S", "S"]
    assert all(len(r.cds_code) == 14 and r.cds_code.isdigit() for r in rows)
    assert {r.academic_year for r in rows} == {"2023-24"}


def test_school_outcomes_selects_only_the_whole_school_total_row() -> None:
    """Example Elementary carries two school-level rows in the fixture: a
    distractor (Experience=EXP, Credential=FC, Subject=MATH) and the whole-school
    total (Experience=Credential=ALL, Subject=TA). Only the second is read."""
    outcomes = school_outcomes(FIXTURE)
    assert set(outcomes) == {EXAMPLE, CHARTER, CLOSED, UNJOINED}
    example = outcomes[EXAMPLE]
    assert example.subject_area == "TA"
    assert example.experience_level == "ALL"
    assert example.credential_level == "ALL"
    assert example.total.number() == 5.0


def test_normal_values_are_the_published_cells() -> None:
    example = school_outcomes(FIXTURE)[EXAMPLE]
    assert example.counts["clear"].number() == 4.0
    assert example.percents["clear"].number() == 80.0
    assert example.counts["out_of_field"].number() == 1.0
    assert example.percents["out_of_field"].number() == 20.0


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
    assert example.counts["na"].status is MeasureStatus.NOT_REPORTED
    assert example.percents["na"].status is MeasureStatus.NOT_REPORTED
    assert not example.counts["na"].is_zero


def test_a_small_school_can_be_withheld_entirely() -> None:
    charter = school_outcomes(FIXTURE)[CHARTER]
    assert charter.total.status is MeasureStatus.SUPPRESSED
    assert all(m.status is MeasureStatus.SUPPRESSED for m in charter.counts.values())
    assert all(m.status is MeasureStatus.SUPPRESSED for m in charter.percents.values())


def test_the_distractor_row_never_leaks_into_the_selected_total() -> None:
    """Example Elementary's fixture rows include a non-total row (Experience=EXP,
    Credential=FC, Subject=MATH) with its own Total FTE of 2.00 and a 100 percent
    "clear" share. If :func:`school_outcomes` ever selected that row instead of
    the whole-school total, these values would appear where the real total's
    (5.00 FTE, 80.0 percent clear) belong.
    """
    example = school_outcomes(FIXTURE)[EXAMPLE]
    assert example.total.number() == 5.0
    assert example.total.number() != 2.0
    assert example.percents["clear"].number() == 80.0
    assert example.percents["clear"].number() != 100.0


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
        "Academic Year\tAggregate Level\tTotal FTE\n2023-24\tS\t5.00\n",
        encoding="utf-8",
    )
    with pytest.raises(AssignmentDriftError, match="missing required columns"):
        list(parse_assignments(path))


def test_renamed_outcome_column_is_drift_not_a_silent_gap(tmp_path: Path) -> None:
    header = HEADER.replace("Clear FTE (count)", "Clear FTE Count")
    path = write(tmp_path, row(), header=header)
    with pytest.raises(AssignmentDriftError, match="Clear FTE"):
        list(parse_assignments(path))


def test_unknown_aggregate_level_refuses(tmp_path: Path) -> None:
    path = write(tmp_path, row({"Aggregate Level": "X"}))
    with pytest.raises(AssignmentDriftError, match="not one this parser reviewed"):
        list(parse_assignments(path))


def test_unknown_charter_value_refuses(tmp_path: Path) -> None:
    path = write(tmp_path, row({"Charter School": "Maybe"}))
    with pytest.raises(AssignmentDriftError, match="Charter School"):
        list(parse_assignments(path))


def test_unknown_dass_value_refuses(tmp_path: Path) -> None:
    path = write(tmp_path, row({"DASS": "Maybe"}))
    with pytest.raises(AssignmentDriftError, match="DASS"):
        list(parse_assignments(path))


def test_unknown_grade_span_refuses(tmp_path: Path) -> None:
    path = write(tmp_path, row({"School Grade Span": "GR13"}))
    with pytest.raises(AssignmentDriftError, match="School Grade Span"):
        list(parse_assignments(path))


def test_unknown_experience_level_refuses(tmp_path: Path) -> None:
    path = write(tmp_path, row({"Teacher Experience Level": "MID"}))
    with pytest.raises(AssignmentDriftError, match="Teacher Experience Level"):
        list(parse_assignments(path))


def test_unknown_credential_level_refuses(tmp_path: Path) -> None:
    path = write(tmp_path, row({"Teacher Credential Level": "PARTIAL"}))
    with pytest.raises(AssignmentDriftError, match="Teacher Credential Level"):
        list(parse_assignments(path))


def test_unknown_subject_area_refuses(tmp_path: Path) -> None:
    path = write(tmp_path, row({"Subject Area": "ZZZZ"}))
    with pytest.raises(AssignmentDriftError, match="Subject Area"):
        list(parse_assignments(path))


def test_malformed_cds_code_refuses_rather_than_joins(tmp_path: Path) -> None:
    path = write(tmp_path, row({"School Code": "011234X"}))
    with pytest.raises(AssignmentDriftError, match="14-digit CDS"):
        list(parse_assignments(path))


def test_overlong_cds_parts_refuse(tmp_path: Path) -> None:
    path = write(tmp_path, row({"County Code": "011"}))
    with pytest.raises(AssignmentDriftError, match="14-digit CDS"):
        list(parse_assignments(path))


def test_unknown_sentinel_refuses_rather_than_guesses(tmp_path: Path) -> None:
    path = write(tmp_path, row({"Clear FTE (count)": "N/A"}))
    with pytest.raises(UnparseableCellError, match="not reviewed"):
        list(parse_assignments(path))


def test_a_percent_sign_is_an_unreviewed_format_not_a_number(tmp_path: Path) -> None:
    """If the acquired file writes shares as "85.0%", the build stops and the
    format gets reviewed. Stripping the sign here would be a guess."""
    path = write(tmp_path, row({"Clear FTE (percent)": "85.0%"}))
    with pytest.raises(UnparseableCellError, match="not reviewed"):
        list(parse_assignments(path))


def test_two_whole_school_total_rows_is_drift(tmp_path: Path) -> None:
    path = write(tmp_path, row() + row())
    with pytest.raises(AssignmentDriftError, match="two whole-school total"):
        school_outcomes(path)


def test_a_second_row_that_is_not_a_total_row_is_not_drift(tmp_path: Path) -> None:
    """Two school-level rows for one CDS is fine as long as at most one of them
    is the whole-school total (Experience=Credential=ALL, Subject=TA)."""
    distractor = row(
        {
            "Teacher Experience Level": "EXP",
            "Teacher Credential Level": "FC",
            "Subject Area": "MATH",
        }
    )
    path = write(tmp_path, row() + distractor)
    outcomes = school_outcomes(path)
    assert set(outcomes) == {EXAMPLE}
    assert outcomes[EXAMPLE].subject_area == "TA"


# --- the column contract is the one thing to re-verify --------------------


def test_outcome_names_cover_every_outcome_and_read_as_plain_language() -> None:
    assert tuple(OUTCOME_NAMES) == OUTCOMES
    assert tuple(OUTCOME_COLUMNS) == OUTCOMES
    assert len(OUTCOMES) == 7
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


def test_the_unknown_percent_columns_own_typo_is_read_verbatim() -> None:
    """CDE's real header repeats "FTE" in this one column name. Confirmed against
    the acquired file's own header row, not the file-structure page's prose."""
    assert OUTCOME_COLUMNS["unknown"][1] == "Unknown FTE FTE (percent)"
    assert "Unknown FTE FTE (percent)" in REQUIRED_COLUMNS
