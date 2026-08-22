"""The evidence bundle: exactly what the page shows, addressable, deterministic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from homeroom.ask.catalog import CATALOG, describe_catalog
from homeroom.ask.evidence import (
    SCOPES,
    SchoolEvidence,
    build_bundle,
    load_school,
    main,
)
from homeroom.i18n import LOCALES

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
EXAMPLE = "01100170112345"
ALL_WITHHELD = "01100170154321"
NEVER_MENTIONED = "01100170176543"


def test_every_catalog_measure_has_a_record_for_every_school(
    fixture_bundle: Path,
) -> None:
    for cds in (EXAMPLE, ALL_WITHHELD, NEVER_MENTIONED):
        evidence = load_school(fixture_bundle, cds)
        assert evidence is not None
        assert list(evidence.records) == list(CATALOG)
        for record in evidence.records.values():
            assert record.id == f"{cds}|{record.measure}|{record.year}"
            assert record.source in ("d2", "d3")
            assert set(record.coverage) == {"reported", "suppressed", "not_reported"}


def test_the_catalog_is_every_figure_the_page_renders_and_nothing_else() -> None:
    keys = list(CATALOG)
    assert keys[0] == "enrollment.total"
    assert sum(k.startswith("enrollment.grade.") for k in keys) == 14
    assert sum(k.startswith("enrollment.group.") for k in keys) == 25
    assert "absenteeism.total" in keys
    assert sum(k.startswith("absenteeism.group.") for k in keys) == 18
    assert not any("assignment" in k or "teacher" in k for k in keys)
    for locale in LOCALES:
        listing = describe_catalog(locale)
        assert listing.count("\n") + 1 == len(keys)
        assert listing == describe_catalog(locale)


def test_a_withheld_cell_carries_no_value_and_a_zero_carries_one(
    example: SchoolEvidence,
) -> None:
    withheld = example.records["enrollment.group.RE_B"]
    assert withheld.school.status == "suppressed"
    assert withheld.school.value is None
    assert not withheld.school.reported
    zero = example.records["absenteeism.group.RA"]
    assert zero.school.reported
    assert zero.school.value == 0.0


def test_the_school_never_mentioned_by_any_file_has_only_absences(
    fixture_bundle: Path,
) -> None:
    evidence = load_school(fixture_bundle, NEVER_MENTIONED)
    assert evidence is not None
    assert {r.school.status for r in evidence.records.values()} == {"not_reported"}
    # The district and state rows still publish, and they are not this school's.
    assert evidence.records["enrollment.total"].state.reported


def test_cell_ids_resolve_only_for_this_school(example: SchoolEvidence) -> None:
    record = example.records["absenteeism.total"]
    for scope in SCOPES:
        hit = example.cell(record.cell_id(scope))
        assert hit is not None
        assert hit[1] == scope
    assert example.cell(record.cell_id("school").replace(EXAMPLE, ALL_WITHHELD)) is None
    assert example.cell(f"{EXAMPLE}|absenteeism.total|2099-00|school") is None
    assert example.cell(f"{EXAMPLE}|absenteeism.total|{record.year}|county") is None
    assert example.cell(f"{EXAMPLE}|not.a.measure|{record.year}|school") is None
    assert example.cell("garbage") is None
    with pytest.raises(KeyError):
        record.cell("county")
    with pytest.raises(KeyError):
        record.cell_id("county")


def test_loading_refuses_codes_that_are_not_cds_codes(fixture_bundle: Path) -> None:
    assert load_school(fixture_bundle, "../index") is None
    assert load_school(fixture_bundle, "0110017011234") is None
    assert load_school(fixture_bundle, "0110017011234x") is None
    assert load_school(fixture_bundle, "99999999999999") is None


def test_the_bundle_is_byte_identical_across_builds(tmp_path: Path) -> None:
    outs = []
    for name in ("a", "b"):
        out = tmp_path / name
        build_bundle(
            directory=FIXTURES / "pubschls.sample.txt",
            enrollment=FIXTURES / "cdenroll.sample.txt",
            absenteeism=FIXTURES / "chronicabsenteeism.sample.txt",
            out_dir=out,
            is_fixture=True,
        )
        outs.append({p.name: p.read_bytes() for p in sorted(out.rglob("*.json"))})
    assert outs[0] == outs[1]
    assert len(outs[0]) == 4


def test_round_trip_through_json_is_lossless(example: SchoolEvidence) -> None:
    again = SchoolEvidence.from_json(json.loads(json.dumps(example.to_json())))
    assert again == example


def test_a_bundle_from_another_catalog_version_is_refused(
    example: SchoolEvidence,
) -> None:
    data = example.to_json()
    records = data["records"]
    assert isinstance(records, list)
    records[0] = dict(records[0], measure="spending.per_pupil")
    with pytest.raises(ValueError, match="catalog does not carry"):
        SchoolEvidence.from_json(data)
    with pytest.raises(ValueError, match="not shaped"):
        SchoolEvidence.from_json(dict(data, records={}))


def test_a_build_without_d3_carries_no_absenteeism_record(tmp_path: Path) -> None:
    build_bundle(
        directory=FIXTURES / "pubschls.sample.txt",
        enrollment=FIXTURES / "cdenroll.sample.txt",
        out_dir=tmp_path,
        is_fixture=True,
    )
    evidence = load_school(tmp_path, EXAMPLE)
    assert evidence is not None
    assert not any(k.startswith("absenteeism") for k in evidence.records)
    assert "d3" not in evidence.sources


def test_the_cli_writes_the_bundle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "--fixture",
            "--directory",
            str(FIXTURES / "pubschls.sample.txt"),
            "--enrollment",
            str(FIXTURES / "cdenroll.sample.txt"),
            "--absenteeism",
            str(FIXTURES / "chronicabsenteeism.sample.txt"),
            "--out",
            str(tmp_path),
        ]
    )
    assert code == 0
    assert "3 schools" in capsys.readouterr().out
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert index["is_fixture"] is True
    assert index["schools"] == 3
    assert index["measures"] == list(CATALOG)
    assert index["sources"]["d2"]["access_date"] is None
