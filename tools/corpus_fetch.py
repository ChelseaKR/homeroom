"""Retrieve CDE's own documentation pages into ``corpus/``, with hashes and dates.

The ask layer (ADR 0003) answers "what does chronic absenteeism mean and how is
it measured?" by quoting CDE verbatim, never by paraphrasing. This tool is how
the text it quotes gets into the repository. It is run by a person, the same way
the data files are acquired (PROVENANCE.md): CI never fetches anything.

For each source it downloads the page, keeps the main content (from the page's
``<h1>`` to the "Questions:" line, which is where CDE's template puts the body),
turns block elements into passages separated by blank lines, and writes:

* ``corpus/<key>.txt``: the passages, plain text, one blank line between them;
* ``corpus/manifest.json``: for every key, the URL, the retrieval date (UTC),
  the page's own "Last Reviewed" date when it states one, the SHA-256 of the
  raw HTML as received and of the text file as written, the passage count, and
  the measures the source documents.

Re-running rewrites both; a diff in the text file is upstream drift to review,
not a reason to touch the loader. Nothing here is interpreted: a passage is a
string, and the only thing the ask layer ever does with one is quote it.

Usage (from the repository root, with network access)::

    uv run python tools/corpus_fetch.py
    uv run python tools/corpus_fetch.py --only fsabd cwa
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus"
USER_AGENT = "homeroom-corpus-fetch/1 (+https://github.com/ChelseaKR/homeroom)"


@dataclass(frozen=True)
class Source:
    key: str
    url: str
    title: str
    measures: tuple[str, ...]
    """The measure families this page documents, in the ask layer's vocabulary."""


SOURCES: tuple[Source, ...] = (
    Source(
        key="fsabd",
        url="https://www.cde.ca.gov/ds/ad/fsabd.asp",
        title="File Structure: Chronic Absenteeism Data",
        measures=("absenteeism",),
    ),
    Source(
        key="filesabd",
        url="https://www.cde.ca.gov/ds/ad/filesabd.asp",
        title="Chronic Absenteeism Data (downloadable files)",
        measures=("absenteeism",),
    ),
    Source(
        key="cwa",
        url="https://www.cde.ca.gov/ls/ai/cw/",
        title="Child Welfare & Attendance (California definition of chronic absentee)",
        measures=("absenteeism",),
    ),
    Source(
        key="fsenrcensus",
        url="https://www.cde.ca.gov/ds/ad/fsenrcensus.asp",
        title="File Structure: Census Day Enrollment Data",
        measures=("enrollment",),
    ),
    Source(
        key="filesenrcensus",
        url="https://www.cde.ca.gov/ds/ad/filesenrcensus.asp",
        title="Census Day Enrollment Data (downloadable files)",
        measures=("enrollment",),
    ),
    Source(
        key="fspubschls",
        url="https://www.cde.ca.gov/ds/si/ds/fspubschls.asp",
        title="File Structure: Public Schools and Districts",
        measures=("directory",),
    ),
)

BLOCK_TAGS = frozenset(
    {"p", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "div", "dt", "dd", "br"}
)
CELL_TAGS = frozenset({"td", "th"})
SKIP_TAGS = frozenset({"script", "style", "noscript"})
LAST_REVIEWED = re.compile(
    r"Last Reviewed:\s*([A-Za-z]+,\s*[A-Za-z]+\s+\d{1,2},\s*\d{4})"
)


class _Extractor(HTMLParser):
    """Block elements become passage breaks; table cells are joined with ' | '."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_TAGS:
            self._skip += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in CELL_TAGS:
            self.parts.append(" | ")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def main_content(page: str) -> str:
    """The body of a CDE page: from its ``<h1>`` to the "Questions:" line."""
    start = page.find("<h1")
    end = page.find('id="questionsline"')
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("page is not shaped like CDE's template; refusing to guess")
    return page[start:end]


def passages(fragment: str) -> list[str]:
    parser = _Extractor()
    parser.feed(fragment)
    text = html.unescape("".join(parser.parts))
    out: list[str] = []
    for raw in re.split(r"\n\s*\n+|\n", text):
        line = re.sub(r"[ \t\u00a0]+", " ", raw).strip(" |")
        line = re.sub(r"\s*\|\s*", " | ", line)
        if len(line) >= 12:
            out.append(line)
    return out


def fetch(url: str) -> bytes:
    if not url.startswith("https://www.cde.ca.gov/"):
        raise SystemExit(f"refusing to fetch a non-CDE URL: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return bytes(response.read())


def run(only: set[str]) -> int:
    CORPUS.mkdir(exist_ok=True)
    manifest_path = CORPUS / "manifest.json"
    manifest: dict[str, dict[str, object]] = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {}
    )
    today = dt.datetime.now(dt.UTC).date().isoformat()
    for source in SOURCES:
        if only and source.key not in only:
            continue
        raw = fetch(source.url)
        page = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
        page = page.replace("\r", "\n")
        body = passages(main_content(page))
        text = "\n\n".join(body) + "\n"
        (CORPUS / f"{source.key}.txt").write_text(text, encoding="utf-8", newline="\n")
        reviewed = LAST_REVIEWED.search(page)
        manifest[source.key] = {
            "url": source.url,
            "title": source.title,
            "measures": list(source.measures),
            "retrieved": today,
            "last_reviewed_per_page": reviewed.group(1) if reviewed else None,
            "sha256_html": hashlib.sha256(raw).hexdigest(),
            "sha256_text": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "passages": len(body),
        }
        print(f"{source.key}: {len(body)} passages, {len(raw)} bytes, {source.url}")
    manifest_path.write_text(
        json.dumps(dict(sorted(manifest.items())), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", nargs="*", default=[], help="source keys to refresh")
    raise SystemExit(run(set(parser.parse_args().only)))
