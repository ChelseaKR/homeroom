"""Shared fixtures for the ask-layer tests: the fixture evidence bundle and the corpus."""

from __future__ import annotations

from pathlib import Path

import pytest

from homeroom.ask.corpus import Corpus, load_corpus
from homeroom.ask.evidence import SchoolEvidence, build_bundle, load_school

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"

EXAMPLE = "01100170112345"
"""Example Elementary: published figures, a genuine zero, and withheld cells."""
ALL_WITHHELD = "01100170154321"
"""Ejemplo Charter Academy: every enrollment figure the file mentions is withheld."""
NEVER_MENTIONED = "01100170176543"
"""Sin Datos Middle: no source file mentions it at all."""


@pytest.fixture(scope="session")
def fixture_bundle(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("bundle")
    build_bundle(
        directory=FIXTURES / "pubschls.sample.txt",
        enrollment=FIXTURES / "cdenroll.sample.txt",
        absenteeism=FIXTURES / "chronicabsenteeism.sample.txt",
        out_dir=out,
        is_fixture=True,
    )
    return out


@pytest.fixture(scope="session")
def corpus() -> Corpus:
    return load_corpus()


@pytest.fixture(scope="session")
def example(fixture_bundle: Path) -> SchoolEvidence:
    evidence = load_school(fixture_bundle, EXAMPLE)
    assert evidence is not None
    return evidence
