"""The accessibility gate a machine cannot run, and the record that says so.

Half of this project's accessibility gate is automated and merge-blocking:
`make pages` runs html-validate and axe-core over every built page in both
languages, and `tests/test_pages.py` measures contrast off the palette and
asserts the structure a screen reader depends on. The other half -- keyboard
reach and order, focus visibility in practice, reflow at 320 CSS pixels, and a
screen-reader walkthrough in each language -- needs a person, has never been
done, and until this file existed was tracked by nothing but prose in four
documents.

Prose is what drifted last time. Four documents went on saying the ask service
was not deployed for a week after it was, and two of them were edited during
that week without the denial being noticed; the fix was to derive the fact and
hold the documents to it (`tests/test_published_site.py`, "documents describing
the surface"). This is the same shape for the accessibility gate, with one
difference: there is no published byte that proves a person did or did not use
a screen reader. Nobody can automate the walkthrough, and nobody should pretend
to.

So what is checked here is everything around it:

  * the procedure exists, and covers every page type the site actually
    publishes -- derived from `site/`, so a page type added later and not
    walked fails here rather than being quietly skipped, the way `county/` and
    `district/` were covered by no accessibility run at all until 2026-09-05;
  * the record exists, has a row per page type per language, and uses a closed
    vocabulary, so a cell cannot be edited into something meaningless;
  * a row may not claim a result without a date and a person -- a walkthrough
    with no name on it is not a walkthrough;
  * while any row is UNMET, README.md, docs/ROADMAP.md,
    docs/RESPONSIBLE-TECH-AUDITS.md and RR-05 each still say so, in their own
    words, and each still points at the procedure.

The failure this is built against is the tidy one: somebody deletes the
procedure, or flips the record, or softens the four documents, and the
repository reads as complete. Deleting the procedure fails fourteen of the
eighteen tests here and leaves four documents citing a file that is not there.
Flipping the record without a date and a name fails. Flipping it with both, and
leaving the documents claiming the gate is open, fails. What remains possible is an
outright lie -- a fabricated date beside a fabricated name, with all four
documents rewritten to match -- which no test can catch and which is now at
least a deliberate act across five files rather than a quiet edit to one.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

from homeroom.i18n import LOCALES

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
PROCEDURE = ROOT / "docs" / "accessibility-walkthrough.md"
REGISTER = ROOT / "docs" / "audits" / "residual-risk-register.md"

#: Every document that declares this gap, and the phrase each one declares it
#: with. Pinning the phrase rather than a generic "look for something negative"
#: is the point: a document that stops saying the walkthrough is outstanding
#: fails here, and it cannot pass by having said something else nearby.
DECLARING_DOCUMENTS = {
    "README.md": "not yet done",
    "docs/ROADMAP.md": "not yet done",
    "docs/RESPONSIBLE-TECH-AUDITS.md": "not yet done",
    "docs/audits/residual-risk-register.md": "have not been performed",
}

#: The path every one of those must cite, so the procedure is reachable from
#: wherever a reader meets the claim.
PROCEDURE_PATH = "docs/accessibility-walkthrough.md"

#: Ways of saying the walkthrough happened. None of them is true.
COMPLETION_CLAIMS = (
    "walkthrough is done",
    "walkthrough is complete",
    "walkthrough has been done",
    "walkthrough has been performed",
    "walkthrough has happened",
    "walkthrough was done",
    "walkthrough was performed",
    "walkthrough was completed",
    "walkthrough no longer",
)

#: What a cell in the record is allowed to say. UNMET is not a result; PASS and
#: FAIL are, and both cost a date and a name.
RESULTS = ("UNMET", "PASS", "FAIL")

UNMET = "UNMET"

#: What an unwalked row carries where its date and its walker would go.
NOTHING_RECORDED = "—"

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

QUOTED = re.compile(r'"[^"\n]*"')

CDS_PAGE = re.compile(rf"^\d{{14}}\.(?:{'|'.join(LOCALES)})\.html$")

SITE_PATH = re.compile(r"site/[A-Za-z0-9_./-]+\.html")


def unquoted(body: str) -> str:
    """A document's prose with quoted spans blanked.

    Borrowed from `tests/test_published_site.py`, and for the same reason: this
    repository corrects a wrong sentence by quoting what it used to say, so a
    claim inside quotation marks is history and a claim outside them is a
    claim.
    """
    return QUOTED.sub('""', body)


# ----------------------------------------------------------------------------------
# What the site publishes, derived rather than remembered
# ----------------------------------------------------------------------------------


def page_type(path: Path) -> str:
    """Which kind of page a published file is.

    The site's own addressing decides this. A page in a subdirectory is that
    subdirectory's kind (`ask`, `county`, `district`); at the root there are
    two, the landing page and the school pages, told apart by the one name that
    is not a CDS code.
    """
    relative = path.relative_to(SITE)
    if relative.parent != Path("."):
        return relative.parent.as_posix()
    return "landing" if relative.name == "index.html" else "school"


def page_locale(path: Path) -> str | None:
    """The locale in a published file's name, or None for the landing page."""
    parts = path.name.split(".")
    return parts[-2] if len(parts) >= 3 and parts[-2] in LOCALES else None


@cache
def published_page_types() -> tuple[str, ...]:
    """Every kind of page the published site holds, in a stable order."""
    return tuple(sorted({page_type(path) for path in SITE.rglob("*.html")}))


@cache
def procedure() -> str:
    return PROCEDURE.read_text(encoding="utf-8")


@cache
def sections() -> dict[str, str]:
    """The procedure's `##` sections, heading text to body."""
    found: dict[str, str] = {}
    heading = ""
    for line in procedure().splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
            found[heading] = ""
        elif heading:
            found[heading] += line + "\n"
    return found


def test_the_site_still_has_the_shape_this_derivation_reads() -> None:
    """The floor under every derivation below.

    `page_type` reads a root-level page as a school unless it is the index. If
    a page type ever lands at the root with a name of some other shape, that
    reading silently absorbs it into the school pages and the procedure would
    not have to cover it. So the root is held to exactly what it holds today:
    one index and CDS-coded school pages in the site's own locales.
    """
    assert SITE.is_dir(), "site/ is missing; see tests/test_published_site.py"
    unexpected = sorted(
        path.name
        for path in SITE.glob("*.html")
        if path.name != "index.html" and not CDS_PAGE.match(path.name)
    )
    assert not unexpected, (
        "a root-level page that is neither the index nor a CDS school page is a "
        f"page type this file reads as a school page: {unexpected[:5]}"
    )
    nested = sorted(
        str(path.relative_to(SITE))
        for path in SITE.rglob("*.html")
        if len(path.relative_to(SITE).parts) > 2
    )
    assert not nested, f"a published page below the first directory level: {nested[:5]}"


def test_every_page_type_the_site_publishes_is_here_in_both_languages() -> None:
    """A page type published in one language only would need saying so."""
    by_type: dict[str, set[str | None]] = {}
    for path in SITE.rglob("*.html"):
        by_type.setdefault(page_type(path), set()).add(page_locale(path))
    assert by_type.pop("landing") == {None}, "the landing page gained a locale suffix"
    for kind, locales in sorted(by_type.items()):
        assert locales == set(LOCALES), (kind, sorted(str(x) for x in locales))


# ----------------------------------------------------------------------------------
# The procedure
# ----------------------------------------------------------------------------------


def test_the_procedure_is_committed_and_says_it_has_not_been_run() -> None:
    """The document is the deliverable; the walkthrough is not done."""
    assert PROCEDURE.is_file(), (
        f"{PROCEDURE_PATH} is missing, and four documents cite it as where this "
        "gate's procedure lives"
    )
    assert "**Status: not done.**" in procedure(), (
        "the procedure no longer opens by saying the walkthrough has not been run"
    )


def test_the_procedure_covers_every_page_type_the_site_publishes() -> None:
    """Derived, so a sixth page type is a failure rather than an omission.

    `county/` and `district/` were published on 2026-09-05 and were read by no
    accessibility run at all until the same day, because `tools/a11y.mjs` does
    not recurse and nothing counted the directories. A walkthrough procedure
    with a hand-written list of page types would go the same way.
    """
    kinds = published_page_types()
    headings = [heading.lower() for heading in sections()]
    for kind in kinds:
        assert any(kind in heading for heading in headings), (
            f"the site publishes {kind} pages and the procedure has no section "
            f"for them; headings are {headings}"
        )
    assert f"{len(kinds)} page types" in procedure(), (
        f"the procedure no longer states that the site has {len(kinds)} page types"
    )
    assert f"{len(LOCALES)} languages" in procedure()
    assert f"{len(kinds) * len(LOCALES)} rows" in procedure()


def test_the_procedure_names_a_published_page_for_every_type_and_language() -> None:
    """A procedure is only followable if the pages it names are really there."""
    named = {ROOT / match for match in SITE_PATH.findall(procedure())}
    assert named, "the procedure names no page to walk"
    missing = sorted(
        str(path.relative_to(ROOT)) for path in named if not path.is_file()
    )
    assert not missing, f"the procedure names pages that are not published: {missing}"

    covered = {(page_type(path), page_locale(path)) for path in named}
    for kind in published_page_types():
        wanted = [(kind, None)] if kind == "landing" else [(kind, x) for x in LOCALES]
        for pair in wanted:
            assert pair in covered, (
                f"the procedure names no {pair[1] or 'published'} page to walk for "
                f"the {pair[0]} page type"
            )


def test_every_page_type_section_says_what_a_pass_and_a_failure_look_like() -> None:
    """A step a walker cannot judge is a step that records nothing.

    Both halves are counted rather than merely present: a section that grows a
    check with no failure beside it, or loses the failure from one it had, is
    a step whose result is whatever the walker felt like recording.
    """
    kinds = published_page_types()
    checked = 0
    for heading, body in sections().items():
        if not any(kind in heading.lower() for kind in kinds):
            continue
        checked += 1
        passes = body.count("- Pass:")
        failures = body.count("- Failure:")
        assert passes == failures, (heading, passes, failures)
        assert passes >= 3, (
            f"the {heading} section has {passes} checks; a page type walked in "
            "fewer than three respects is not walked"
        )
    assert checked >= len(kinds), (checked, kinds)


def test_the_procedure_names_the_assistive_technologies_and_the_reflow_rig() -> None:
    """Which screen reader, which browser, which width. Otherwise it is a wish."""
    body = procedure().lower()
    for name in ("voiceover", "nvda", "jaws", "talkback", "safari", "firefox"):
        assert name in body, f"the procedure no longer names {name}"
    for check in (
        "320 css pixels",
        "400% ",
        "skip link",
        "focus ring",
        "shift+tab",
        "automatic language switching",
        "spanish phonemes",
        "withheld to protect privacy",
    ):
        assert check in body, f"the procedure no longer covers {check!r}"


def test_the_procedure_does_not_offer_the_automated_gate_as_the_walkthrough() -> None:
    """The one substitution that would make this document worthless.

    axe-core in jsdom is the thing this walkthrough exists beside, not a
    weaker version of it. The procedure has to keep saying which of the two it
    is, or a reader can close the gate by running `make pages`.
    """
    body = procedure().lower()
    assert "jsdom" in body and "no headless" in body


def test_the_gap_is_still_linked_to_the_issue_that_tracks_it() -> None:
    """A declared conformance gap links an open issue (DOC-13)."""
    issue = "https://github.com/ChelseaKR/homeroom/issues/6"
    assert issue in procedure(), "the procedure no longer links issue #6"
    assert issue in (ROOT / "README.md").read_text(encoding="utf-8"), (
        "README.md's accessibility row no longer links the issue tracking it"
    )


# ----------------------------------------------------------------------------------
# The record
# ----------------------------------------------------------------------------------


@cache
def record() -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    """The results table: its header cells and its rows."""
    lines = procedure().splitlines()
    start = next(
        (
            i
            for i, line in enumerate(lines)
            if line.startswith("| Page type | Language")
        ),
        None,
    )
    assert start is not None, "the procedure no longer holds a results table"
    header = tuple(cell.strip() for cell in lines[start].strip().strip("|").split("|"))
    rows = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        rows.append(tuple(cell.strip() for cell in line.strip().strip("|").split("|")))
    return header, tuple(rows)


def columns() -> dict[str, int]:
    header, _ = record()
    return {name.lower(): index for index, name in enumerate(header)}


def check_columns() -> tuple[int, ...]:
    """The three columns that hold a result rather than a note."""
    index = columns()
    return tuple(index[name] for name in ("keyboard", "screen reader", "reflow"))


def test_the_record_has_a_row_for_every_page_type_in_every_language() -> None:
    """Ten rows, derived. Five page types, two languages, none of them optional.

    Spanish is a launch requirement in this project rather than a later phase,
    so a record that walked the English pages and left the Spanish ones out
    would be a record of half a site.
    """
    _, rows = record()
    index = columns()
    found = set()
    for row in rows:
        kind = next(
            (k for k in published_page_types() if k in row[index["page type"]].lower()),
            None,
        )
        assert kind, f"the record has a row for no page type this site has: {row}"
        locale = next((x for x in LOCALES if f"`{x}`" in row[index["language"]]), None)
        assert locale, f"the record has a row in no language this site has: {row}"
        found.add((kind, locale))
    expected = {(k, x) for k in published_page_types() for x in LOCALES}
    assert found == expected, sorted(expected - found)
    assert len(rows) == len(expected), (len(rows), len(expected))


def test_every_cell_in_the_record_says_one_of_three_things() -> None:
    """A closed vocabulary, so a cell cannot be edited into a shrug."""
    _, rows = record()
    for row in rows:
        for column in check_columns():
            assert row[column] in RESULTS, (row, row[column])


def test_the_walkthrough_is_still_unmet_everywhere() -> None:
    """Today's honest state: nothing has been walked.

    This is the assertion that will one day fail, and the failure is the
    prompt: when a real result is recorded, the two tests below become the
    ones that hold it honest, and the four documents and RR-05 have to be
    updated in the same change. Until then, a record that quietly stops saying
    UNMET without any of that happening fails here first.
    """
    _, rows = record()
    results = {row[column] for row in rows for column in check_columns()}
    assert results == {UNMET}, sorted(results)


def test_a_recorded_result_costs_a_date_and_a_person() -> None:
    """No anonymous pass. A walkthrough is somebody's, or it is not one."""
    _, rows = record()
    index = columns()
    for row in rows:
        walked = [row[column] for column in check_columns() if row[column] != UNMET]
        if not walked:
            continue
        date = row[index["date walked"]]
        walker = row[index["walked by"]]
        assert ISO_DATE.match(date), (
            f"a row records {walked} with no date: {row}. A result without a "
            "date is a claim about no particular version of the pages"
        )
        assert walker and walker != NOTHING_RECORDED, (
            f"a row records {walked} with nobody's name on it: {row}"
        )


def test_an_unwalked_row_carries_no_date_and_no_name() -> None:
    """The other direction: a date beside UNMET would read as a walk that failed."""
    _, rows = record()
    index = columns()
    for row in rows:
        if any(row[column] != UNMET for column in check_columns()):
            continue
        assert row[index["date walked"]] == NOTHING_RECORDED, row
        assert row[index["walked by"]] == NOTHING_RECORDED, row


# ----------------------------------------------------------------------------------
# The documents that declare the gap
# ----------------------------------------------------------------------------------


def test_every_document_declaring_this_gap_points_at_the_procedure() -> None:
    """The prose stops being the only place this lives, and stays that way."""
    for name in DECLARING_DOCUMENTS:
        body = (ROOT / name).read_text(encoding="utf-8")
        assert PROCEDURE_PATH in body, (
            f"{name} declares this gap and no longer points at {PROCEDURE_PATH}"
        )


def test_the_documents_still_say_the_walkthrough_is_outstanding() -> None:
    """While any row is UNMET, all four say so, each in its own words."""
    _, rows = record()
    if not any(row[column] == UNMET for row in rows for column in check_columns()):
        return
    for name, phrase in DECLARING_DOCUMENTS.items():
        body = (ROOT / name).read_text(encoding="utf-8").lower()
        assert phrase in body, (
            f"{name} no longer says the walkthrough is outstanding, and the "
            f"record in {PROCEDURE_PATH} still says it is: expected {phrase!r}"
        )


def test_no_document_claims_the_walkthrough_has_been_done() -> None:
    """The tidy edit this file exists to catch."""
    for name in (*DECLARING_DOCUMENTS, PROCEDURE_PATH):
        body = unquoted((ROOT / name).read_text(encoding="utf-8")).lower()
        found = sorted(claim for claim in COMPLETION_CLAIMS if claim in body)
        assert not found, (
            f"{name} says the walkthrough happened; nobody has run it, and the "
            f"record in {PROCEDURE_PATH} is empty: {found}"
        )


def test_rr_05_still_carries_the_open_commitment() -> None:
    """The register row is the commitment; the procedure is how it gets met.

    RR-07 needed this same test after a precondition was deleted rather than
    met (`tests/test_published_site.py`). RR-05 is the one row in this register
    that no gate can close, which makes deleting it the cheapest way to make
    the repository look finished.
    """
    row = next(
        line
        for line in REGISTER.read_text(encoding="utf-8").splitlines()
        if line.startswith("| RR-05 ")
    )
    assert "have not been performed" in row, (
        "RR-05 no longer says the walkthrough has not been performed"
    )
    assert "No gate can close this one" in row, (
        "RR-05 no longer says that no automated gate can close it"
    )
    assert PROCEDURE_PATH in row, f"RR-05 no longer points at {PROCEDURE_PATH}"
    assert "| Track" in row, f"RR-05 is no longer being tracked: {row[:200]}"
