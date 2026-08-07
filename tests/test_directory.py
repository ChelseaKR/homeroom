"""The directory parser fails closed on drift and never guesses a column."""

from pathlib import Path

import pytest

from homeroom.directory import (
    DirectoryDriftError,
    active_schools,
    parse_directory,
)

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "pubschls.sample.txt"


def test_fixture_parses_and_joins_on_cds() -> None:
    schools = list(parse_directory(FIXTURE))
    assert len(schools) == 4
    assert all(len(s.cds_code) == 14 for s in schools)


def test_active_schools_excludes_closed_and_offices() -> None:
    active = active_schools(FIXTURE)
    names = {s.name for s in active}
    assert names == {"Example Elementary", "Ejemplo Charter Academy"}
    charter = next(s for s in active if s.name == "Ejemplo Charter Academy")
    assert charter.charter is True


def test_no_data_placeholder_becomes_empty_not_a_value() -> None:
    office = next(s for s in parse_directory(FIXTURE) if not s.name)
    assert office.grades_served == ""


def test_missing_required_column_is_a_hard_failure(tmp_path: Path) -> None:
    broken = tmp_path / "pubschls.txt"
    broken.write_text("CDSCode\tSchool\n01100170000000\tX\n", encoding="utf-8")
    with pytest.raises(DirectoryDriftError, match="missing required columns"):
        list(parse_directory(broken))


def test_malformed_cds_code_refuses_rather_than_joins(tmp_path: Path) -> None:
    header = (
        "CDSCode\tStatusType\tCounty\tDistrict\tSchool\tCity\tCharter\tVirtual\tGSserved\n"
    )
    bad = tmp_path / "pubschls.txt"
    bad.write_text(header + "12345\tActive\tYolo\tD\tS\tDavis\tN\tN\tK-6\n", encoding="utf-8")
    with pytest.raises(DirectoryDriftError, match="not 14 digits"):
        list(parse_directory(bad))
