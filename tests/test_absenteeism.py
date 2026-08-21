"""Chronic absenteeism parsing: CDS assembly, suppression survival, drift refusal.

The fixture mirrors the real 2024-25 Chronic Absenteeism file acquired 2026-08-21
(``chronicabsenteeism25.txt``, 33,781,100 bytes, 341,490 rows; PROVENANCE.md D3):
the same spaced identity columns, the same concatenated
``ChronicAbsenteeismEligibleCumulativeEnrollment`` / ``ChronicAbsenteeismCount`` /
``ChronicAbsenteeismRate`` measure columns, and the same independent
``Charter School`` / ``DASS`` dimensions, each ``All``/``Yes``/``No``.
"""

from pathlib import Path

import pytest

from homeroom.absenteeism import (
    REQUIRED_COLUMNS,
    AbsenteeismDriftError,
    parse_absenteeism,
)
from homeroom.measures import MeasureStatus, UnparseableCellError

HEADER = "\t".join(REQUIRED_COLUMNS) + "\n"


def write(tmp_path: Path, rows: str, *, header: str = HEADER) -> Path:
    path = tmp_path / "chronicabsenteeism.txt"
    path.write_text(header + rows, encoding="utf-8")
    return path


def row(overrides: dict[str, str] | None = None) -> str:
    cells = {
        "Academic Year": "2024-25",
        "Aggregate Level": "S",
        "County Code": "57",
        "District Code": "72678",
        "School Code": "6056246",
        "Charter School": "No",
        "DASS": "No",
        "Reporting Category": "TA",
        "ChronicAbsenteeismEligibleCumulativeEnrollment": "96",
        "ChronicAbsenteeismCount": "12",
        "ChronicAbsenteeismRate": "12.5",
    }
    cells.update(overrides or {})
    return "\t".join(cells[column] for column in REQUIRED_COLUMNS) + "\n"


def test_school_row_parses_with_assembled_cds(tmp_path: Path) -> None:
    p = write(tmp_path, row())
    parsed = list(parse_absenteeism(p))
    assert len(parsed) == 1
    assert parsed[0].cds_code == "57726786056246"
    assert parsed[0].rate.number() == 12.5
    assert parsed[0].count.number() == 12
    assert parsed[0].eligible_enrollment.number() == 96


def test_masked_row_masks_all_three_cells_never_zero(tmp_path: Path) -> None:
    p = write(
        tmp_path,
        row(
            {
                "ChronicAbsenteeismEligibleCumulativeEnrollment": "*",
                "ChronicAbsenteeismCount": "*",
                "ChronicAbsenteeismRate": "*",
            }
        ),
    )
    parsed = next(parse_absenteeism(p))
    assert parsed.rate.status is MeasureStatus.SUPPRESSED
    assert not parsed.rate.is_zero
    assert parsed.count.status is MeasureStatus.SUPPRESSED
    assert parsed.eligible_enrollment.status is MeasureStatus.SUPPRESSED


def test_a_genuine_zero_rate_stays_zero_and_reported(tmp_path: Path) -> None:
    p = write(
        tmp_path,
        row(
            {
                "ChronicAbsenteeismCount": "0",
                "ChronicAbsenteeismRate": "0.0",
            }
        ),
    )
    parsed = next(parse_absenteeism(p))
    assert parsed.rate.is_zero
    assert parsed.rate.status is MeasureStatus.REPORTED


def test_a_no_value_marker_in_the_rate_stops_the_file(tmp_path: Path) -> None:
    """``nan`` in a rate is not a rate, the same rule D2's TOTAL_ENR enforces."""
    p = write(tmp_path, row({"ChronicAbsenteeismRate": "nan"}))
    with pytest.raises(UnparseableCellError, match="ChronicAbsenteeismRate"):
        list(parse_absenteeism(p))


def test_a_school_code_that_will_not_make_a_cds_refuses_rather_than_joins(
    tmp_path: Path,
) -> None:
    p = write(tmp_path, row({"School Code": "605624X"}))
    with pytest.raises(AbsenteeismDriftError, match="cannot assemble a 14-digit CDS"):
        list(parse_absenteeism(p))


def test_unknown_aggregate_level_refuses(tmp_path: Path) -> None:
    p = write(tmp_path, row({"Aggregate Level": "X"}))
    with pytest.raises(AbsenteeismDriftError, match="not one this parser reviewed"):
        list(parse_absenteeism(p))


def test_unknown_charter_value_refuses(tmp_path: Path) -> None:
    p = write(tmp_path, row({"Charter School": "Maybe"}))
    with pytest.raises(AbsenteeismDriftError, match="Charter School"):
        list(parse_absenteeism(p))


def test_unknown_dass_value_refuses(tmp_path: Path) -> None:
    p = write(tmp_path, row({"DASS": "Maybe"}))
    with pytest.raises(AbsenteeismDriftError, match="DASS"):
        list(parse_absenteeism(p))


def test_missing_required_column_is_drift(tmp_path: Path) -> None:
    p = tmp_path / "chronicabsenteeism.txt"
    p.write_text(
        "Academic Year\tAggregate Level\tChronicAbsenteeismRate\n2024-25\tS\t12.5\n",
        encoding="utf-8",
    )
    with pytest.raises(AbsenteeismDriftError, match="missing required columns"):
        list(parse_absenteeism(p))


def test_a_percent_sign_is_an_unreviewed_format_not_a_rate(tmp_path: Path) -> None:
    p = write(tmp_path, row({"ChronicAbsenteeismRate": "12.5%"}))
    with pytest.raises(UnparseableCellError, match="not reviewed"):
        list(parse_absenteeism(p))


def test_district_and_state_rows_carry_their_own_level(tmp_path: Path) -> None:
    p = write(
        tmp_path,
        row(
            {
                "Aggregate Level": "D",
                "School Code": "",
                "Charter School": "All",
                "DASS": "All",
            }
        )
        + row(
            {
                "Aggregate Level": "T",
                "County Code": "00",
                "District Code": "",
                "School Code": "",
                "Charter School": "All",
                "DASS": "All",
            }
        ),
    )
    levels = [r.level for r in parse_absenteeism(p)]
    assert levels == ["D", "T"]
