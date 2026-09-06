#!/usr/bin/env python3
"""Report when CDE lists a newer file than the one Homeroom acquired.

Every published number here is copied out of a file a person downloaded from
CDE in a browser and recorded in `PROVENANCE.md`. The site says "as acquired
2026-08-21" and means it. What nothing said, until this file existed, was when
CDE published a newer one: the 2025-26 absenteeism file could land and every
gate in this repository would stay green while the pages carried last year's.

    python3 tools/sources_check.py

For each acquired source in `PROVENANCE.md`'s machine-readable register it
reads CDE's **HTML download page** -- never a data file -- and compares the
filename and the posting note the page currently shows against the ones
recorded when the file was acquired. The principle the whole pipeline is built
on holds here: what never crosses the network is the data. This reads an index
page and downloads nothing.

Three outcomes per source, and the third is why this is worth writing:

    unchanged     the page still lists the acquired file, with the same note
    newer         the page lists a different newest file, or the same file
                  with a moved posting note; both values are printed
    unreadable    the page could not be read, or nothing that looks like a
                  file listing parsed out of it

An unreadable page is never reported as unchanged and never exits 0. Silence
reading as "no change" is the failure every gate in this repository is written
against, and a freshness check is the shape most exposed to it: the quiet
answer and the good answer look identical.

Three things are refused outright rather than reported as a pass, following
`tools/verify_live_site.py`:

  * a register with no checkable source in it, because a check that checks
    nothing and prints OK is worse than no check;
  * a page that returns anything but HTTP 200, an unreachable host included;
  * a page that returns 200 and yields zero file listings, which is what a
    redirect to a firewall notice or a rebuilt page looks like.

Exit codes:

    0   every checkable source still lists the file that was acquired
    1   at least one source lists something newer
    4   the check could not run: no page could be read, or the register is
        empty or malformed

Sources the register marks `not_checkable` are printed with the reason and
never counted as passing. `D1`'s download page is a query form that generates
a report on request, so there is no listed filename to compare; that is a fact
about CDE's page, and it is stated rather than skipped.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROVENANCE = ROOT / "PROVENANCE.md"

REGISTER_SCHEMA = "homeroom/source-register/v1"

#: Identifies this tool to CDE rather than impersonating a browser. The
#: `www3.cde.ca.gov` host answers a non-browser client with a firewall
#: redirect (PROVENANCE.md, "Surveyed"), which is one reason this check reads
#: only the `www.cde.ca.gov` index pages: those serve an honest client, and a
#: check that has to lie about who it is has no business running unattended.
USER_AGENT = "homeroom-sources-check/1.0 (+https://github.com/ChelseaKR/homeroom)"

UNCHANGED = "unchanged"
NEWER = "newer"
UNREADABLE = "unreadable"
NOT_CHECKABLE = "not checkable"

EXIT_OK = 0
EXIT_NEWER = 1
EXIT_CANNOT_RUN = 4


class PageUnreadable(Exception):
    """The index page could not be read. Never "unchanged"."""


# --------------------------------------------------------------------------
# The register
# --------------------------------------------------------------------------

#: The fenced JSON block under "## Source register (machine readable)".
_REGISTER_RE = re.compile(
    r"^## Source register \(machine readable\)\s*$.*?^```json\s*$(?P<body>.*?)^```\s*$",
    re.M | re.S,
)


@dataclass(frozen=True)
class Source:
    id: str
    index_url: str
    saved_as: str
    acquired: str
    listed_file: str | None = None
    listed_note: str | None = None
    listed_read: str | None = None
    not_checkable: str | None = None

    @property
    def checkable(self) -> bool:
        return self.not_checkable is None


class RegisterError(ValueError):
    """The register is missing, malformed, or self-contradictory."""


def read_register(path: Path = PROVENANCE) -> list[Source]:
    text = path.read_text(encoding="utf-8")
    found = _REGISTER_RE.search(text)
    if not found:
        raise RegisterError(
            f"{path.name} carries no fenced json block under "
            '"## Source register (machine readable)"'
        )
    try:
        payload = json.loads(found.group("body"))
    except json.JSONDecodeError as error:
        raise RegisterError(
            f"the source register is not valid JSON: {error}"
        ) from error
    if payload.get("schema") != REGISTER_SCHEMA:
        raise RegisterError(
            f"the source register declares schema {payload.get('schema')!r}, "
            f"not {REGISTER_SCHEMA!r}"
        )
    sources = []
    for raw in payload.get("sources") or ():
        try:
            source = Source(**raw)
        except TypeError as error:
            raise RegisterError(
                f"source entry {raw!r} is not the register's shape: {error}"
            ) from error
        if source.checkable and not source.listed_file:
            raise RegisterError(
                f"{source.id} states neither a listed_file to compare nor a "
                "not_checkable reason, so nothing would check it and nothing "
                "would say so"
            )
        sources.append(source)
    if not sources:
        raise RegisterError("the source register lists no sources")
    return sources


# --------------------------------------------------------------------------
# Reading a CDE download page
# --------------------------------------------------------------------------

#: A data-file link on a CDE download page, with the label that follows it.
#: CDE puts the posting date in a `LinkNotation` span inside the anchor:
#:     <a href=".../tamo2324.txt">tamo2324<span class="LinkNotation">
#:     (TXT; 229MB; Posted 24-Sep-2025)</span></a>
#: The href is matched on an explicit extension set rather than on "anything
#: up to the closing quote", and the anchor body is bounded by `</a>` rather
#: than by a punctuation class: a class such as `[^.;]*?` stops at the dot in
#: `tamo2324.txt` and would silently match nothing at all.
_LINK_RE = re.compile(
    r'<a\s[^>]*href="(?P<href>https?://[^"]+?\.(?:txt|csv|xlsx|zip))"[^>]*>(?P<label>.*?)</a>',
    re.I | re.S,
)
_NOTATION_RE = re.compile(
    r'<span class="LinkNotation">\s*\((?P<note>[^)]*)\)', re.I | re.S
)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Listing:
    """One data file as the download page currently lists it."""

    filename: str
    note: str | None

    def describe(self) -> str:
        return f"{self.filename} ({self.note})" if self.note else self.filename


def listings(page: str) -> list[Listing]:
    """Every data file the page links, in page order (newest first at CDE)."""
    out: list[Listing] = []
    for match in _LINK_RE.finditer(page):
        label = match.group("label")
        notation = _NOTATION_RE.search(label)
        out.append(
            Listing(
                filename=match.group("href").rsplit("/", 1)[-1],
                note=" ".join(html.unescape(notation.group("note")).split())
                if notation
                else None,
            )
        )
    return out


def urllib_fetch(url: str, timeout: float) -> str:
    # Only the register's own https URLs reach here, and the register is
    # committed; there is no caller-supplied scheme to audit.
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=timeout) as handle:  # noqa: S310
        if handle.status != 200:
            raise PageUnreadable(f"HTTP {handle.status}")
        return handle.read(8_000_000).decode("utf-8", errors="replace")


def fetch_with_retries(
    url: str, *, timeout: float, attempts: int, fetch, sleep=time.sleep
) -> str:
    """`fetch`, retried on a transport failure. A non-200 is not retried.

    A bounded retry keeps one dropped connection from reading as a finding.
    An HTTP error is the page's own answer and is reported as it stands.
    """
    last = ""
    for attempt in range(1, attempts + 1):
        try:
            return fetch(url, timeout)
        except PageUnreadable:
            raise
        except urllib.error.HTTPError as error:
            raise PageUnreadable(f"HTTP {error.code}") from error
        except Exception as error:
            last = f"{type(error).__name__}: {error}"
            if attempt < attempts:
                sleep(min(2**attempt, 8))
    raise PageUnreadable(last or "unreachable")


# --------------------------------------------------------------------------
# The comparison
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    source: Source
    state: str
    detail: str


def check_source(
    source: Source, *, timeout: float, attempts: int, fetch, sleep=time.sleep
) -> Finding:
    if not source.checkable:
        return Finding(source, NOT_CHECKABLE, source.not_checkable or "")
    try:
        page = fetch_with_retries(
            source.index_url,
            timeout=timeout,
            attempts=attempts,
            fetch=fetch,
            sleep=sleep,
        )
    except PageUnreadable as error:
        return Finding(source, UNREADABLE, f"{source.index_url}: {error}")

    found = listings(page)
    if not found:
        return Finding(
            source,
            UNREADABLE,
            f"{source.index_url} answered, but no data-file listing parsed out "
            "of it. That is what a firewall notice or a rebuilt page looks "
            "like; it is not evidence that nothing has changed.",
        )

    newest = found[0]
    if newest.filename != source.listed_file:
        return Finding(
            source,
            NEWER,
            f"the page now lists {newest.describe()} first; "
            f"{source.saved_as} was acquired {source.acquired} from "
            f"{source.listed_file}",
        )

    same = [item for item in found if item.filename == source.listed_file]
    if source.listed_note and all(item.note != source.listed_note for item in same):
        current = same[0].note if same else None
        return Finding(
            source,
            NEWER,
            f"{source.listed_file} is still listed first, but its note moved "
            f"from {source.listed_note!r} (read {source.listed_read}) to "
            f"{current!r}: CDE republished the same filename",
        )
    return Finding(
        source,
        UNCHANGED,
        f"{newest.describe()} is still the newest listed, as when "
        f"{source.saved_as} was acquired {source.acquired}",
    )


def run(
    sources: list[Source], *, timeout: float, attempts: int, fetch, sleep=time.sleep
) -> list[Finding]:
    return [
        check_source(
            source, timeout=timeout, attempts=attempts, fetch=fetch, sleep=sleep
        )
        for source in sources
    ]


def exit_code(findings: list[Finding]) -> int:
    states = {f.state for f in findings}
    if not any(f.state in (UNCHANGED, NEWER) for f in findings):
        # Nothing was actually compared. Never 0.
        return EXIT_CANNOT_RUN
    if NEWER in states:
        return EXIT_NEWER
    if UNREADABLE in states:
        return EXIT_CANNOT_RUN
    return EXIT_OK


_ORDER = {NEWER: 0, UNREADABLE: 1, NOT_CHECKABLE: 2, UNCHANGED: 3}


def report(findings: list[Finding]) -> str:
    lines = ["# Source freshness", ""]
    counts = {state: sum(f.state == state for f in findings) for state in _ORDER}
    lines.append(
        f"**{counts[UNCHANGED]} unchanged, {counts[NEWER]} newer file listed, "
        f"{counts[UNREADABLE]} unreadable, {counts[NOT_CHECKABLE]} not checkable.** "
        "Only the HTML download page is read; no data file is fetched, and "
        "nothing is acquired by this check."
    )
    lines.append("")
    lines.append("| source | state | detail |")
    lines.append("|---|---|---|")
    for finding in sorted(findings, key=lambda f: (_ORDER[f.state], f.source.id)):
        detail = finding.detail.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {finding.source.id} | **{finding.state}** | {detail} |")
    lines.append("")
    if counts[NEWER]:
        lines.append(
            "A newer listing is not an instruction to download anything. "
            "Acquiring a source is a browser step a person takes, and the "
            "acquisition is recorded in `PROVENANCE.md` in the same commit "
            "that parses it (see the *Surveyed* rule there)."
        )
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sources_check",
        description=(
            "Report when CDE's download page lists a newer file than the one "
            "PROVENANCE.md records as acquired. Reads only the HTML index."
        ),
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="seconds per request"
    )
    parser.add_argument(
        "--attempts", type=int, default=3, help="tries per page before it is unreadable"
    )
    parser.add_argument(
        "--out", type=Path, help="write the Markdown report here as well"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        sources = read_register()
    except (OSError, RegisterError) as error:
        sys.stderr.write(f"the source register could not be read: {error}\n")
        return EXIT_CANNOT_RUN
    if not any(source.checkable for source in sources):
        sys.stderr.write(
            "no source in the register is checkable, so this run would compare "
            "nothing and print a pass\n"
        )
        return EXIT_CANNOT_RUN

    findings = run(
        sources, timeout=args.timeout, attempts=args.attempts, fetch=urllib_fetch
    )
    text = report(findings)
    sys.stdout.write(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    return exit_code(findings)


if __name__ == "__main__":
    raise SystemExit(main())
