"""The corpus of CDE definitions: committed, hashed, and quotable only verbatim."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from homeroom.ask.corpus import (
    CORPUS_DIR,
    Corpus,
    CorpusDriftError,
    load_corpus,
    normalise,
)

EXPECTED_SOURCES = {
    "fsabd",
    "filesabd",
    "cwa",
    "fsenrcensus",
    "filesenrcensus",
    "fspubschls",
}


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    return load_corpus()


def test_the_committed_corpus_loads_and_names_every_source(corpus: Corpus) -> None:
    assert set(corpus.sources) == EXPECTED_SOURCES
    for source in corpus.sources.values():
        assert source.url.startswith("https://www.cde.ca.gov/")
        assert source.retrieved
        assert source.passages
        assert source.measures


def test_every_source_covers_a_measure_family_the_site_publishes(
    corpus: Corpus,
) -> None:
    assert corpus.for_measure("absenteeism")
    assert corpus.for_measure("enrollment")
    assert corpus.for_measure("directory")
    assert corpus.for_measure("teacher_assignments") == []


def test_the_definitions_the_ask_layer_depends_on_are_actually_in_the_corpus(
    corpus: Corpus,
) -> None:
    """If CDE rewrites a page, these are the sentences whose loss matters."""
    fsabd = corpus.sources["fsabd"].text
    assert "suppressed (*)" in fsabd
    assert "Chronic Absenteeism Eligible Cumulative Enrollment) is 10 or less" in fsabd
    assert "absent for 10% or more of the days they were expected to attend" in fsabd
    assert "divided by the Chronic Absenteeism Enrollment" in fsabd
    cwa = corpus.sources["cwa"].text
    assert "10 percent or more of the schooldays" in cwa
    census = corpus.sources["fsenrcensus"].text
    assert "ELAS_RFEP = Reclassified Fluent English Proficient" in census
    assert "first Wednesday in October" in census


def test_a_quote_verifies_only_when_it_is_on_the_cited_page(corpus: Corpus) -> None:
    real = (
        "data are suppressed (*) on the Chronic Absenteeism downloadable files "
        "if the cell size within a selected student population"
    )
    assert corpus.quote_is_verbatim("fsabd#0", real)
    assert corpus.quote_is_verbatim("fsabd#0", real.upper())
    assert corpus.quote_is_verbatim("fsabd#0", "  data   are suppressed (*) on the ")
    # Same words, different page: not a citation of that page.
    assert not corpus.quote_is_verbatim("fspubschls#0", real)
    # A paraphrase is not a quote.
    assert not corpus.quote_is_verbatim(
        "fsabd#0", "data is hidden when fewer than ten students are in the group"
    )
    # One changed word is not a quote either.
    assert not corpus.quote_is_verbatim("fsabd#0", real.replace("cell", "sample"))


def test_a_quote_too_short_to_prove_anything_is_refused(corpus: Corpus) -> None:
    assert not corpus.quote_is_verbatim("fsabd#0", "the")
    assert not corpus.quote_is_verbatim("fsabd#0", "student privacy")


def test_a_citation_of_a_passage_that_does_not_exist_is_not_a_citation(
    corpus: Corpus,
) -> None:
    assert corpus.passage("fsabd#999999") is None
    assert corpus.passage("nope#0") is None
    assert corpus.passage("fsabd#x") is None
    assert corpus.passage("fsabd") is None
    assert not corpus.quote_is_verbatim("fsabd#999999", "data are suppressed (*) on")


def test_typographic_marks_and_whitespace_do_not_break_a_real_quote() -> None:
    assert (
        normalise("\u201ca\u201d  \u2013  \u2018b\u2019 \u2014 c\u00a0d")
        == "\"a\" - 'b' - c d"
    )


def test_a_hand_edited_corpus_file_is_refused(tmp_path: Path) -> None:
    """The manifest's hash is the claim that the text is CDE's, and it is checked."""
    manifest = json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))
    key = "filesabd"
    (tmp_path / "manifest.json").write_text(
        json.dumps({key: manifest[key]}), encoding="utf-8"
    )
    text = (CORPUS_DIR / f"{key}.txt").read_text(encoding="utf-8")
    (tmp_path / f"{key}.txt").write_text(
        text.replace("10 or less", "5 or less"), encoding="utf-8"
    )
    with pytest.raises(CorpusDriftError, match="changed after it was fetched"):
        load_corpus(tmp_path)


def test_a_passage_count_that_disagrees_with_the_manifest_is_refused(
    tmp_path: Path,
) -> None:
    manifest = json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))
    key = "filesabd"
    entry = dict(manifest[key])
    entry["passages"] = entry["passages"] + 1
    (tmp_path / "manifest.json").write_text(json.dumps({key: entry}), encoding="utf-8")
    (tmp_path / f"{key}.txt").write_text(
        (CORPUS_DIR / f"{key}.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    with pytest.raises(CorpusDriftError, match="passages"):
        load_corpus(tmp_path)


def test_the_manifest_records_provenance_for_every_text_file() -> None:
    manifest = json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))
    texts = {p.stem for p in CORPUS_DIR.glob("*.txt")}
    assert set(manifest) == texts
    for entry in manifest.values():
        for field in ("url", "title", "measures", "retrieved", "sha256_html"):
            assert entry[field], field
        assert len(entry["sha256_html"]) == 64
        assert len(entry["sha256_text"]) == 64
