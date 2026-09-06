"""The freshness check says what it could not read, and never "unchanged".

`tools/sources_check.py` answers one question -- has CDE published a newer
file than the one Homeroom acquired -- and the dangerous answer is the quiet
one. "No newer file listed" and "I could not read the page" look identical to
a reader and identical in an exit code, unless something forces them apart.
That is what most of this module is about.

The index fixtures under `fixtures/cde-index/` are CDE's own markup, read
2026-09-06 and committed as served, so the parser is held to the page rather
than to a hand-written idea of it. One of them is the HTTP 200 firewall notice
`www3.cde.ca.gov` returns to a non-browser client, which is the exact shape of
a page that answers successfully and says nothing.

The register in `PROVENANCE.md` is also held to the prose table above it here,
so the two cannot drift: an acquired source with no register entry, or an
entry naming a page the table does not, fails.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures" / "cde-index"
PROVENANCE = ROOT / "PROVENANCE.md"

_SPEC = importlib.util.spec_from_file_location(
    "sources_check", ROOT / "tools" / "sources_check.py"
)
assert _SPEC and _SPEC.loader
sources_check = importlib.util.module_from_spec(_SPEC)
# Registered before it executes: the module defines dataclasses, and
# `@dataclass` resolves its own module out of `sys.modules` while running.
sys.modules[_SPEC.name] = sources_check
_SPEC.loader.exec_module(sources_check)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def source(**overrides):
    base = {
        "id": "D3",
        "index_url": "https://www.cde.ca.gov/ds/ad/filesabd.asp",
        "saved_as": "chronicabsenteeism25.txt",
        "acquired": "2026-08-21",
        "listed_file": "chronicabsenteeism25-v2.txt",
        "listed_note": "TXT; 33MB; Updated 13-Mar-2026",
        "listed_read": "2026-09-06",
    }
    base.update(overrides)
    return sources_check.Source(**base)


class Fetcher:
    """Answers with one page, or raises. Records every call."""

    def __init__(self, page: str | None = None, error: Exception | None = None):
        self.page = page
        self.error = error
        self.calls: list[str] = []

    def __call__(self, url: str, timeout: float) -> str:
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        assert self.page is not None
        return self.page


def check(src, fetcher, attempts=1):
    # `sleep` is a no-op: the backoff is real in production and pure latency
    # here, and a suite that waits for it fails first under machine load.
    return sources_check.check_source(
        src, timeout=1.0, attempts=attempts, fetch=fetcher, sleep=lambda _s: None
    )


# --------------------------------------------------------------------------
# The three outcomes
# --------------------------------------------------------------------------


def test_the_acquired_file_still_listed_first_is_unchanged() -> None:
    finding = check(source(), Fetcher(fixture("filesabd-unchanged.html")))
    assert finding.state == sources_check.UNCHANGED
    assert "chronicabsenteeism25-v2.txt" in finding.detail


def test_a_newer_vintage_reports_newer_and_names_both_files() -> None:
    finding = check(source(), Fetcher(fixture("filesabd-newer.html")))
    assert finding.state == sources_check.NEWER
    assert "chronicabsenteeism26.txt" in finding.detail
    assert "chronicabsenteeism25-v2.txt" in finding.detail
    assert "2026-08-21" in finding.detail


def test_the_same_filename_republished_is_newer_not_unchanged() -> None:
    """CDE reissues a vintage under the same name; only the note moves."""
    finding = check(source(), Fetcher(fixture("filesabd-republished.html")))
    assert finding.state == sources_check.NEWER
    assert "13-Mar-2026" in finding.detail
    assert "04-Oct-2026" in finding.detail


def test_an_http_error_is_unreadable_not_unchanged() -> None:
    finding = check(source(), Fetcher(error=sources_check.PageUnreadable("HTTP 503")))
    assert finding.state == sources_check.UNREADABLE
    assert "503" in finding.detail


def test_an_unreachable_host_is_unreadable_not_unchanged() -> None:
    finding = check(source(), Fetcher(error=OSError("nodename nor servname provided")))
    assert finding.state == sources_check.UNREADABLE


def test_a_200_carrying_a_firewall_notice_is_unreadable() -> None:
    """The failure this whole file exists for: a successful, empty answer."""
    finding = check(source(), Fetcher(fixture("firewall-notice.html")))
    assert finding.state == sources_check.UNREADABLE
    assert "no data-file listing parsed out of it" in finding.detail
    assert "not evidence that nothing has changed" in finding.detail


def test_a_source_that_cannot_be_checked_says_so_and_is_never_fetched() -> None:
    fetcher = Fetcher(fixture("filesabd-unchanged.html"))
    finding = check(
        source(
            id="D1", listed_file=None, listed_note=None, not_checkable="a query form"
        ),
        fetcher,
    )
    assert finding.state == sources_check.NOT_CHECKABLE
    assert finding.detail == "a query form"
    assert fetcher.calls == []


# --------------------------------------------------------------------------
# Exit codes
# --------------------------------------------------------------------------


def findings_for(*pages):
    return [check(source(), Fetcher(fixture(page))) for page in pages]


def test_all_unchanged_exits_zero() -> None:
    assert sources_check.exit_code(findings_for("filesabd-unchanged.html")) == 0


def test_a_newer_file_exits_one() -> None:
    assert sources_check.exit_code(findings_for("filesabd-newer.html")) == 1


def test_an_unreadable_page_exits_non_zero() -> None:
    findings = [
        check(source(), Fetcher(error=sources_check.PageUnreadable("HTTP 500")))
    ]
    assert sources_check.exit_code(findings) == sources_check.EXIT_CANNOT_RUN


def test_a_run_that_compared_nothing_never_exits_zero() -> None:
    """Every source unreadable or not checkable is not a clean bill of health."""
    findings = [
        check(source(), Fetcher(error=sources_check.PageUnreadable("HTTP 500"))),
        check(
            source(
                id="D1",
                listed_file=None,
                listed_note=None,
                not_checkable="a query form",
            ),
            Fetcher(),
        ),
    ]
    assert sources_check.exit_code(findings) == sources_check.EXIT_CANNOT_RUN


def test_a_newer_finding_survives_an_unreadable_sibling() -> None:
    findings = [
        check(source(), Fetcher(fixture("filesabd-newer.html"))),
        check(source(id="D5"), Fetcher(error=sources_check.PageUnreadable("HTTP 500"))),
    ]
    assert sources_check.exit_code(findings) == sources_check.EXIT_NEWER


# --------------------------------------------------------------------------
# Retries
# --------------------------------------------------------------------------


def test_a_transport_failure_is_retried_and_an_http_error_is_not() -> None:
    calls: list[str] = []

    def flaky(url, timeout):
        calls.append(url)
        if len(calls) < 3:
            raise OSError("connection reset")
        return fixture("filesabd-unchanged.html")

    waits: list[float] = []
    finding = sources_check.check_source(
        source(), timeout=1.0, attempts=3, fetch=flaky, sleep=waits.append
    )
    assert finding.state == sources_check.UNCHANGED
    assert len(calls) == 3
    assert waits == [2, 4], "the backoff between attempts is not bounded as documented"

    refused: list[str] = []

    def denied(url, timeout):
        refused.append(url)
        raise sources_check.PageUnreadable("HTTP 403")

    finding = sources_check.check_source(
        source(), timeout=1.0, attempts=3, fetch=denied, sleep=lambda _s: None
    )
    assert finding.state == sources_check.UNREADABLE
    assert len(refused) == 1, (
        "an HTTP status is the page's answer; retrying it is noise"
    )


def test_retries_run_out_and_report_unreadable() -> None:
    def always_fails(url, timeout):
        raise OSError("connection reset")

    finding = sources_check.check_source(
        source(), timeout=1.0, attempts=2, fetch=always_fails, sleep=lambda _s: None
    )
    assert finding.state == sources_check.UNREADABLE
    assert "connection reset" in finding.detail


# --------------------------------------------------------------------------
# The parser, held to CDE's own markup
# --------------------------------------------------------------------------


def test_the_newest_listing_is_read_off_the_committed_page() -> None:
    found = sources_check.listings(fixture("filesabd-unchanged.html"))
    assert found[0].filename == "chronicabsenteeism25-v2.txt"
    assert found[0].note == "TXT; 33MB; Updated 13-Mar-2026"
    assert len(found) >= 6, "CDE lists every vintage; the parser saw almost none"


def test_a_dot_in_a_filename_does_not_truncate_the_link_label() -> None:
    """The regex flaw this portfolio has already shipped once.

    A label bounded by a punctuation class stops at the dot inside
    `chronicabsenteeism25-v2.txt` and reads no posting note at all, which
    turns every republication into "unchanged".
    """
    found = sources_check.listings(fixture("filesabd-unchanged.html"))
    assert all(item.filename.endswith(".txt") for item in found)
    assert found[0].note is not None
    assert "Updated" in found[0].note


def test_a_page_with_no_file_links_yields_nothing_rather_than_guessing() -> None:
    assert sources_check.listings(fixture("firewall-notice.html")) == []


def test_the_file_structure_links_are_not_mistaken_for_data_files() -> None:
    names = {
        item.filename
        for item in sources_check.listings(fixture("filesabd-unchanged.html"))
    }
    assert not any(name.endswith(".asp") for name in names)


# --------------------------------------------------------------------------
# The register, held to the prose
# --------------------------------------------------------------------------

#: A row of PROVENANCE.md's source table: `| D3 | ... | ... | ... | ... |`.
PROSE_ROW = re.compile(r"^\|\s*(D\d+)\s*\|(?P<rest>.*)\|\s*$", re.M)


def prose_rows() -> dict[str, str]:
    text = PROVENANCE.read_text(encoding="utf-8")
    table = text.split("## Source register", 1)[0]
    return {m.group(1): m.group("rest") for m in PROSE_ROW.finditer(table)}


def test_the_register_parses_and_lists_every_acquired_source() -> None:
    register = {s.id: s for s in sources_check.read_register()}
    rows = prose_rows()
    assert rows, "the prose source table did not parse; this check would pass vacuously"

    acquired = {
        source_id
        for source_id, rest in rows.items()
        if re.search(r"\bAcquired\b", rest)
    }
    assert acquired, "no row in the table says Acquired; the parity check sees nothing"
    missing = sorted(acquired - set(register))
    assert not missing, (
        f"these sources are recorded as acquired but carry no register entry, "
        f"so nothing would check them for a newer file: {missing}"
    )


def test_every_register_entry_matches_its_row_in_the_prose() -> None:
    rows = prose_rows()
    for entry in sources_check.read_register():
        assert entry.id in rows, (
            f"{entry.id} is registered but is not a row in the table"
        )
        row = rows[entry.id]
        assert entry.index_url in row, (
            f"{entry.id} registers download page {entry.index_url}, which its "
            "row in the table above does not name"
        )
        assert entry.saved_as in row, (
            f"{entry.id} registers the acquired file as {entry.saved_as}, which "
            "its row in the table above does not name"
        )


def test_a_checkable_entry_without_a_listed_file_is_refused() -> None:
    text = PROVENANCE.read_text(encoding="utf-8")
    block = sources_check._REGISTER_RE.search(text).group("body")
    payload = json.loads(block)
    for entry in payload["sources"]:
        if "listed_file" not in entry:
            continue
        del entry["listed_file"]
        entry.pop("not_checkable", None)
        break
    else:  # pragma: no cover - the register always has a checkable entry
        pytest.fail("no register entry carries a listed_file to remove")
    broken = text.replace(block, "\n" + json.dumps(payload, indent=2) + "\n", 1)
    path = ROOT / "build" / "provenance-under-test.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(broken, encoding="utf-8")
    try:
        with pytest.raises(sources_check.RegisterError, match="neither a listed_file"):
            sources_check.read_register(path)
    finally:
        path.unlink(missing_ok=True)


def test_a_register_that_is_not_the_declared_schema_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "PROVENANCE.md"
    path.write_text(
        "## Source register (machine readable)\n\n```json\n"
        '{"schema": "something/else", "sources": []}\n```\n',
        encoding="utf-8",
    )
    with pytest.raises(sources_check.RegisterError, match="schema"):
        sources_check.read_register(path)


def test_a_missing_register_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "PROVENANCE.md"
    path.write_text("# Provenance\n\nNo register here.\n", encoding="utf-8")
    with pytest.raises(sources_check.RegisterError, match="no fenced json block"):
        sources_check.read_register(path)


# --------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------


def test_the_report_counts_match_its_rows() -> None:
    findings = [
        check(source(), Fetcher(fixture("filesabd-newer.html"))),
        check(source(id="D5"), Fetcher(error=sources_check.PageUnreadable("HTTP 500"))),
        check(
            source(
                id="D1",
                listed_file=None,
                listed_note=None,
                not_checkable="a query form",
            ),
            Fetcher(),
        ),
    ]
    text = sources_check.report(findings)
    assert "0 unchanged, 1 newer file listed, 1 unreadable, 1 not checkable" in text
    assert len([line for line in text.splitlines() if line.startswith("| D")]) == 3
    assert "not an instruction to download anything" in text


def test_the_report_never_ticks_a_source_it_could_not_read() -> None:
    findings = [check(source(), Fetcher(fixture("firewall-notice.html")))]
    text = sources_check.report(findings)
    assert "**unreadable**" in text
    assert "**unchanged**" not in text


def test_the_tool_identifies_itself_rather_than_a_browser() -> None:
    agent = sources_check.USER_AGENT
    assert "homeroom" in agent
    assert "github.com/ChelseaKR/homeroom" in agent
    for impersonation in ("Mozilla", "Chrome", "Safari", "AppleWebKit"):
        assert impersonation not in agent, (
            "a check that has to claim to be a browser has no business running "
            "unattended against a public agency's site"
        )
