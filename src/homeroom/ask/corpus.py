"""CDE's own words about the measures, loaded from ``corpus/`` and quoted verbatim.

The ask layer (ADR 0003) explains a measure by quoting the California Department
of Education's published file-structure and program pages, never by paraphrasing
them. ``tools/corpus_fetch.py`` is how those pages get into ``corpus/`` (a person
runs it; CI never fetches); this module is how the service reads them back and
how the verifier decides whether a quote is real.

A :class:`Passage` is one block of one page, addressed as ``<source>#<index>``.
A quote verifies against the *whole page* it cites, not only the passage, after
normalising whitespace and the typographic quotes and dashes CDE's pages use:
CDE's template sometimes splits one sentence across two blocks around a link,
and a sentence that is on the page is on the page. What a quote may not do is
differ from the page in any word, and that is the check.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CORPUS_DIR = ROOT / "corpus"

_QUOTE_MARKS = str.maketrans(
    {
        "\u2018": "'",  # left single quotation mark
        "\u2019": "'",  # right single quotation mark
        "\u201c": '"',  # left double quotation mark
        "\u201d": '"',  # right double quotation mark
        "\u2013": "-",  # en dash
        "\u2014": "-",  # em dash
        "\u00a0": " ",  # no-break space
    }
)


class CorpusDriftError(ValueError):
    """A corpus file no longer matches what the manifest recorded for it."""


@dataclass(frozen=True)
class Passage:
    id: str
    source: str
    index: int
    text: str


@dataclass(frozen=True)
class CorpusSource:
    key: str
    url: str
    title: str
    measures: tuple[str, ...]
    retrieved: str
    last_reviewed_per_page: str | None
    sha256_text: str
    passages: tuple[Passage, ...]

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.passages)


def normalise(text: str) -> str:
    """The form quotes are compared in: one space between words, ASCII marks."""
    return re.sub(r"\s+", " ", text.translate(_QUOTE_MARKS)).strip().casefold()


@dataclass(frozen=True)
class Corpus:
    sources: dict[str, CorpusSource]

    def passage(self, passage_id: str) -> Passage | None:
        source_key, _, index = passage_id.partition("#")
        source = self.sources.get(source_key)
        if source is None or not index.isdigit():
            return None
        i = int(index)
        if i < 0 or i >= len(source.passages):
            return None
        return source.passages[i]

    def for_measure(self, measure: str) -> list[CorpusSource]:
        return [s for s in self.sources.values() if measure in s.measures]

    def quote_is_verbatim(self, passage_id: str, quote: str) -> bool:
        """True only if ``quote`` appears, word for word, on the cited page.

        A quote shorter than a few words is refused: "the" is on every page, and
        a citation that proves nothing is not a citation.
        """
        passage = self.passage(passage_id)
        if passage is None:
            return False
        wanted = normalise(quote)
        if len(wanted.split()) < 4:
            return False
        return wanted in normalise(self.sources[passage.source].text)


def load_corpus(root: Path = CORPUS_DIR) -> Corpus:
    """Read ``manifest.json`` and every text it names, refusing drift.

    The manifest records the SHA-256 of each text file as written by the fetch
    tool. A file that no longer hashes to that is a file somebody edited by
    hand, and a corpus the service quotes as CDE's words must be CDE's words,
    so the mismatch is an error rather than a warning.
    """
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    sources: dict[str, CorpusSource] = {}
    for key, entry in sorted(manifest.items()):
        path = root / f"{key}.txt"
        text = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest != entry["sha256_text"]:
            raise CorpusDriftError(
                f"{path.name} hashes to {digest[:12]}..., manifest says "
                f"{entry['sha256_text'][:12]}...; the file was changed after it "
                "was fetched, so it can no longer be quoted as CDE's own text"
            )
        blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
        passages = tuple(
            Passage(id=f"{key}#{i}", source=key, index=i, text=block)
            for i, block in enumerate(blocks)
        )
        if len(passages) != entry["passages"]:
            raise CorpusDriftError(
                f"{path.name} has {len(passages)} passages, manifest says "
                f"{entry['passages']}"
            )
        sources[key] = CorpusSource(
            key=key,
            url=entry["url"],
            title=entry["title"],
            measures=tuple(entry["measures"]),
            retrieved=entry["retrieved"],
            last_reviewed_per_page=entry.get("last_reviewed_per_page"),
            sha256_text=entry["sha256_text"],
            passages=passages,
        )
    return Corpus(sources=sources)
