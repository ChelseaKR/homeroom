"""What can be checked about the school pages without a browser, checked.

Four things are gated here, none of them needing a renderer:

* **Structure.** Each page is parsed and the document facts a screen reader
  depends on are asserted: one ``h1``, no skipped heading level, a scope on every
  table header, a caption on every table, no repeated id, one main landmark, the
  right language on the root element, and CDE's English-only school names marked
  ``lang="en"`` when they appear on a Spanish page. ``html-validate`` and
  ``axe-core`` cover the same ground more thoroughly in ``make pages``; these run
  inside ``make verify``, so the floor holds even with no node toolchain.
* **The three unpublished states.** A withheld figure and a missing figure must
  never render a digit, and a genuine zero must render as one. This is the whole
  project in one assertion, so it is asserted from several directions.
* **Contrast.** WCAG 2.2 contrast is arithmetic over two palettes, and both
  palettes are data in :mod:`homeroom.render`. Every pair the pages put together
  is measured here, in both themes. It is the one criterion a headless check can
  settle completely and axe cannot: jsdom paints nothing.
* **Counted numbers.** Every number in a data cell must be a number the pipeline
  read out of a source file or counted as coverage. A page that can print a figure
  nothing counted is the failure this project exists to avoid.

What is deliberately not claimed: none of this looks at the pages. Layout, reflow
at small widths, focus visibility in practice, and a screen-reader walkthrough in
both languages need a person, and README.md says so.
"""

from __future__ import annotations

import re
from collections import Counter
from html.parser import HTMLParser
from itertools import pairwise
from pathlib import Path

import pytest

from homeroom.artifacts import DIRECTORY_ACCESS_DATE, ENROLLMENT_ACCESS_DATE
from homeroom.assignments import OUTCOME_NAMES
from homeroom.i18n import LOCALES, Locale, format_number, text
from homeroom.measures import MeasureStatus
from homeroom.profiles import SchoolProfile, assemble_profiles
from homeroom.render import (
    DARK,
    DIRECTORY_URL,
    ENROLLMENT_URL,
    LIGHT,
    STATE_COLOURS,
    SiteCoverage,
    page_name,
    render_school,
    site_coverage,
)
from homeroom.site import UnknownSchoolError, build_site, main, sources

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
DIRECTORY = FIXTURES / "pubschls.sample.txt"
ENROLLMENT = FIXTURES / "cdenroll.sample.txt"
ASSIGNMENTS = FIXTURES / "tamo.sample.txt"

EXAMPLE = "01100170112345"  # reported figures, a genuine zero, and withheld cells
CHARTER = "01100170154321"  # every figure withheld
ABSENT = "01100170176543"  # active school the enrollment file never mentions
SCHOOLS = (EXAMPLE, CHARTER, ABSENT)

HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


# ----------------------------------------------------------------------------------
# A parser that records the document facts these checks are about
# ----------------------------------------------------------------------------------


class Document(HTMLParser):
    """Structural facts, gathered in one pass over the markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headings: list[tuple[str, str]] = []
        self.ids: list[str] = []
        self.landmarks: Counter[str] = Counter()
        self.tables: list[dict[str, int]] = []
        self.th_scopes: list[str | None] = []
        self.regions: list[str] = []
        self.cells: list[tuple[frozenset[str], str]] = []
        self.lang_spans: list[tuple[str, str]] = []
        self.hrefs: list[str] = []
        self.alternates: list[tuple[str, str]] = []
        self.lang: str | None = None
        self.title: str = ""
        self.metas: dict[str, str] = {}
        self.text: list[str] = []
        self._capture: list[list[str]] = []
        self._heading: str | None = None
        self._td_classes: frozenset[str] | None = None
        self._lang_span: str | None = None
        self._in_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: (value or "") for key, value in attrs}
        if tag == "style":
            self._in_style = True
        if "id" in attr:
            self.ids.append(attr["id"])
        if tag == "html":
            self.lang = attr.get("lang")
        elif tag == "meta":
            key = attr.get("name") or ("charset" if "charset" in attr else "")
            if key:
                self.metas[key] = attr.get("content", attr.get("charset", ""))
        elif tag == "link" and attr.get("rel") == "alternate":
            self.alternates.append((attr.get("hreflang", ""), attr.get("href", "")))
        elif tag == "a" and "href" in attr:
            self.hrefs.append(attr["href"])
        self._note_structure(tag, attr)

    def _note_structure(self, tag: str, attr: dict[str, str]) -> None:
        classes = frozenset(attr.get("class", "").split())
        if tag in HEADINGS:
            self._heading = tag
            self._capture.append([])
        elif tag in ("main", "header", "footer", "nav"):
            self.landmarks[tag] += 1
        elif tag == "section" and "scroll" in classes:
            self.regions.append(attr.get("aria-label", ""))
            assert attr.get("tabindex") == "0"
        elif tag == "table":
            self.tables.append({"caption": 0, "th": 0, "scoped": 0})
        elif tag == "caption" and self.tables:
            self.tables[-1]["caption"] += 1
        elif tag == "th" and self.tables:
            self.tables[-1]["th"] += 1
            scope = attr.get("scope")
            self.th_scopes.append(scope)
            if scope in ("row", "col", "rowgroup", "colgroup"):
                self.tables[-1]["scoped"] += 1
        elif tag == "td":
            self._td_classes = classes
            self._capture.append([])
        if tag == "span" and "lang" in attr:
            self._lang_span = attr["lang"]
            self._capture.append([])

    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self._in_style = False
        elif tag in HEADINGS and self._heading:
            self.headings.append((self._heading, "".join(self._capture.pop()).strip()))
            self._heading = None
        elif tag == "td" and self._td_classes is not None:
            self.cells.append((self._td_classes, "".join(self._capture.pop()).strip()))
            self._td_classes = None
        elif tag == "span" and self._lang_span is not None:
            self.lang_spans.append(
                (self._lang_span, "".join(self._capture.pop()).strip())
            )
            self._lang_span = None

    def handle_data(self, data: str) -> None:
        # The stylesheet is not something a reader reads, and it is full of
        # incidental numbers (font weights, sizes) that would otherwise look like
        # published figures to the checks below.
        if self._in_style:
            return
        self.text.append(data)
        for buffer in self._capture:
            buffer.append(data)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    @property
    def body_text(self) -> str:
        return " ".join("".join(self.text).split())


def parse_markup(source: str) -> Document:
    document = Document()
    document.feed(source)
    match = re.search(r"<title>(.*?)</title>", source, re.S)
    document.title = match.group(1) if match else ""
    return document


def parse(path: Path) -> Document:
    return parse_markup(path.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------------
# Builds
# ----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("pages")
    build_site(directory=DIRECTORY, enrollment=ENROLLMENT, out_dir=out, is_fixture=True)
    return out


def page(built: Path, cds: str, locale: Locale) -> Path:
    return built / page_name(cds, locale)


def every_page(built: Path) -> list[tuple[str, Locale, Path]]:
    return [
        (cds, locale, page(built, cds, locale)) for cds in SCHOOLS for locale in LOCALES
    ]


# ----------------------------------------------------------------------------------
# Structure
# ----------------------------------------------------------------------------------


def test_a_page_is_written_for_every_school_in_every_locale(built: Path) -> None:
    written = sorted(p.name for p in built.glob("*.html"))
    assert written == sorted(
        page_name(cds, locale) for cds in SCHOOLS for locale in LOCALES
    )


def test_every_page_has_one_h1_and_no_skipped_heading_level(built: Path) -> None:
    for _, _, path in every_page(built):
        document = parse(path)
        levels = [int(tag[1]) for tag, _ in document.headings]
        assert levels.count(1) == 1, path.name
        assert levels[0] == 1, path.name
        for previous, current in pairwise(levels):
            assert current - previous <= 1, (path.name, previous, current)


def test_every_page_has_the_landmarks_and_head_a_reader_needs(built: Path) -> None:
    for _, locale, path in every_page(built):
        document = parse(path)
        assert document.lang == locale, path.name
        assert document.landmarks["main"] == 1
        assert document.landmarks["header"] == 1
        assert document.landmarks["footer"] == 1
        assert document.landmarks["nav"] == 1
        assert document.metas["charset"] == "utf-8"
        assert document.metas["viewport"].startswith("width=device-width")
        assert document.metas["description"]
        assert document.title
        assert len(document.title) <= 110
        assert document.ids.count("main") == 1
        assert len(document.ids) == len(set(document.ids))
        assert "#main" in document.hrefs


def test_every_table_is_captioned_and_every_header_scoped(built: Path) -> None:
    for _, _, path in every_page(built):
        document = parse(path)
        assert document.tables, path.name
        for table in document.tables:
            assert table["caption"] == 1
            assert table["th"] > 0
            assert table["scoped"] == table["th"]
        assert all(scope in ("row", "col") for scope in document.th_scopes)


def test_every_scrollable_table_is_a_named_reachable_region(built: Path) -> None:
    """A box that scrolls but cannot be focused is unreachable from a keyboard."""
    for _, _, path in every_page(built):
        document = parse(path)
        assert document.regions, path.name
        assert all(label.strip() for label in document.regions)
        assert len(document.regions) == len(set(document.regions))
        assert len(document.regions) == len(document.tables)


# ----------------------------------------------------------------------------------
# The three states a number can fail to be
# ----------------------------------------------------------------------------------


def cells_with(document: Document, state: str) -> list[str]:
    return [body for classes, body in document.cells if state in classes]


def test_all_four_cell_states_appear_on_the_page_that_has_all_four(
    built: Path,
) -> None:
    for locale in LOCALES:
        document = parse(page(built, EXAMPLE, locale))
        for state in ("m-number", "m-zero", "m-withheld", "m-nothing"):
            assert cells_with(document, state), (locale, state)


def test_a_withheld_or_missing_figure_never_renders_a_digit(built: Path) -> None:
    """The founding rule, at the last place it could be broken.

    A masked cell is unreadable as a number all the way through the pipeline
    (``Measure.number()`` raises). This asserts the page keeps that promise
    visually: no digit is printed where the state published nothing readable, so
    nothing on the page can be scraped or skimmed as a zero.
    """
    for _, _, path in every_page(built):
        document = parse(path)
        for state in ("m-withheld", "m-nothing"):
            for body in cells_with(document, state):
                assert not NUMBER.search(body), (path.name, state, body)


def test_a_genuine_zero_renders_as_a_zero_and_says_it_is_one(built: Path) -> None:
    for locale in LOCALES:
        document = parse(page(built, EXAMPLE, locale))
        zeros = cells_with(document, "m-zero")
        assert zeros
        label = text(locale, "state_zero_label")
        for body in zeros:
            assert body.startswith("0")
            assert label in body


def test_the_three_states_are_worded_differently_in_both_languages(
    built: Path,
) -> None:
    """Colour is never the only signal (WCAG 2.2 SC 1.4.1), so the words carry it."""
    for locale in LOCALES:
        labels = [
            text(locale, key)
            for key in (
                "state_zero_label",
                "state_withheld_label",
                "state_nothing_label",
            )
        ]
        assert len(set(labels)) == 3
        body = parse(page(built, EXAMPLE, locale)).body_text
        for label in labels:
            assert label in body


def test_a_school_with_everything_withheld_shows_no_number_at_all(
    built: Path,
) -> None:
    for locale in LOCALES:
        document = parse(page(built, CHARTER, locale))
        assert not cells_with(document, "m-number")
        assert not cells_with(document, "m-zero")
        assert cells_with(document, "m-withheld")


def test_a_school_the_file_never_mentions_says_nothing_was_published(
    built: Path,
) -> None:
    for locale in LOCALES:
        document = parse(page(built, ABSENT, locale))
        assert not cells_with(document, "m-number")
        assert not cells_with(document, "m-zero")
        assert not cells_with(document, "m-withheld")
        assert cells_with(document, "m-nothing")


# ----------------------------------------------------------------------------------
# Every number was counted
# ----------------------------------------------------------------------------------


def reported_values(profile: SchoolProfile) -> set[str]:
    measures = [profile.total_enrollment, *profile.grades.values()]
    measures.extend(profile.subgroups.values())
    return {
        format_number(measure.number())
        for measure in measures
        if measure.status is MeasureStatus.REPORTED
    }


def coverage_numbers(cover: SiteCoverage) -> set[str]:
    groups = [cover.total_enrollment, *cover.grades.values(), *cover.subgroups.values()]
    numbers = {format_number(value) for group in groups for value in group.values()}
    return numbers | {
        format_number(cover.schools),
        format_number(cover.unjoined_school_totals),
    }


def test_every_number_in_a_data_cell_was_counted(built: Path) -> None:
    assembly = assemble_profiles(DIRECTORY, ENROLLMENT)
    counts = coverage_numbers(site_coverage(assembly))
    for profile in assembly.profiles:
        allowed = counts | reported_values(profile)
        for locale in LOCALES:
            document = parse(page(built, profile.school.cds_code, locale))
            for _, body in document.cells:
                for found in NUMBER.findall(body):
                    assert found in allowed, (profile.school.cds_code, locale, found)


def test_coverage_is_published_on_every_page(built: Path) -> None:
    """Coverage is a first-class output, which means it is on the page."""
    cover = site_coverage(assemble_profiles(DIRECTORY, ENROLLMENT))
    for _, locale, path in every_page(built):
        body = parse(path).body_text
        assert text(locale, "coverage_heading") in body
        assert text(locale, "col_publishing") in body
        assert text(locale, "col_withholding") in body
        assert text(locale, "col_nothing") in body
        assert format_number(cover.schools) in body


def test_every_page_states_that_it_refuses_to_rank(built: Path) -> None:
    for _, locale, path in every_page(built):
        assert text(locale, "no_ranking_body") in parse(path).body_text
        assert text(locale, "footer_no_ranking") in parse(path).body_text


# ----------------------------------------------------------------------------------
# D5: a parser with no file behind it publishes nothing
# ----------------------------------------------------------------------------------


def test_pages_say_the_teacher_data_is_not_yet_acquired(built: Path) -> None:
    for _, locale, path in every_page(built):
        assert text(locale, "not_yet_assignments") in parse(path).body_text


def test_no_page_shows_a_teacher_assignment_figure_even_when_one_is_loaded() -> None:
    """The page build cannot be handed the D5 file, so this reaches past it.

    The profile here carries real (fixture) assignment outcomes, joined and
    parsed: 40 teaching assignments, 34 of them on a clear credential, an 85.0
    percent share, a withheld outcome, and the 2024-25 year they report on. The
    renderer publishes none of it. Every number that reaches a data cell is an
    enrollment figure or a coverage tally, no outcome label appears anywhere, and
    the assignment year does not either. No D5 number about any school reaches a
    page until the file is acquired (PROVENANCE.md D5).
    """
    assembly = assemble_profiles(DIRECTORY, ENROLLMENT, ASSIGNMENTS)
    profile = next(p for p in assembly.profiles if p.school.cds_code == EXAMPLE)
    assert profile.teacher_assignments is not None
    cover = site_coverage(assembly)
    allowed = coverage_numbers(cover) | reported_values(profile)
    for locale in LOCALES:
        document = parse_markup(
            render_school(
                profile,
                locale=locale,
                cover=cover,
                sources=sources(
                    directory=DIRECTORY,
                    enrollment=ENROLLMENT,
                    academic_year=assembly.academic_year,
                    is_fixture=True,
                ),
                is_fixture=True,
            )
        )
        for _, body in document.cells:
            for found in NUMBER.findall(body):
                assert found in allowed, (locale, found)
        for label in OUTCOME_NAMES.values():
            assert label not in document.body_text, (locale, label)
        assert profile.teacher_assignments.academic_year not in document.body_text


# ----------------------------------------------------------------------------------
# Two languages, both real
# ----------------------------------------------------------------------------------


def test_each_page_links_to_its_counterpart_in_the_other_language(
    built: Path,
) -> None:
    for cds, locale, path in every_page(built):
        document = parse(path)
        other: Locale = "es" if locale == "en" else "en"
        assert page_name(cds, other) in document.hrefs
        assert sorted(document.alternates) == sorted(
            (loc, page_name(cds, loc)) for loc in LOCALES
        )


def test_spanish_pages_mark_cde_english_text_and_english_pages_do_not(
    built: Path,
) -> None:
    """WCAG 2.2 SC 3.1.2. CDE publishes school and district names in English only."""
    for cds, locale, path in every_page(built):
        document = parse(path)
        marked = [value for lang, value in document.lang_spans if lang == "en"]
        if locale == "es":
            assert "Davis Joint Unified" in marked, cds
        else:
            assert not document.lang_spans, cds


def test_the_two_languages_are_different_documents(built: Path) -> None:
    for cds in SCHOOLS:
        english = page(built, cds, "en").read_bytes()
        spanish = page(built, cds, "es").read_bytes()
        assert english != spanish
        assert b'lang="es"' in spanish
        assert "Cómo leer esta página".encode() in spanish
        assert b"How to read this page" in english


# ----------------------------------------------------------------------------------
# Provenance and determinism
# ----------------------------------------------------------------------------------


def test_reruns_are_byte_identical(tmp_path: Path) -> None:
    out = tmp_path / "site"
    build_site(directory=DIRECTORY, enrollment=ENROLLMENT, out_dir=out, is_fixture=True)
    first = {p.name: p.read_bytes() for p in sorted(out.glob("*.html"))}
    build_site(directory=DIRECTORY, enrollment=ENROLLMENT, out_dir=out, is_fixture=True)
    again = {p.name: p.read_bytes() for p in sorted(out.glob("*.html"))}
    assert first == again


def test_fixture_pages_stamp_no_access_date_and_say_they_are_not_real(
    built: Path,
) -> None:
    for _, locale, path in every_page(built):
        body = parse(path).body_text
        assert text(locale, "fixture_banner_title") in body
        assert text(locale, "source_fixture") in body
        assert DIRECTORY_ACCESS_DATE not in body


def test_a_real_build_stamps_the_dates_provenance_records(tmp_path: Path) -> None:
    out = tmp_path / "site"
    build_site(
        directory=DIRECTORY,
        enrollment=ENROLLMENT,
        out_dir=out,
        is_fixture=False,
        cds_codes=(EXAMPLE,),
    )
    for locale in LOCALES:
        body = parse(out / page_name(EXAMPLE, locale)).body_text
        assert DIRECTORY_ACCESS_DATE in body
        assert ENROLLMENT_ACCESS_DATE in body
        assert text(locale, "fixture_banner_title") not in body
        assert text(locale, "source_fixture") not in body


def test_every_page_names_its_source_files_and_the_states_pages(built: Path) -> None:
    for _, locale, path in every_page(built):
        document = parse(path)
        body = document.body_text
        assert ENROLLMENT.name in body
        assert DIRECTORY.name in body
        assert text(locale, "sources_heading") in body
        assert DIRECTORY_URL in document.hrefs
        assert ENROLLMENT_URL in document.hrefs


def test_source_urls_match_the_provenance_record() -> None:
    provenance = (ROOT / "PROVENANCE.md").read_text(encoding="utf-8")
    d1_row = next(line for line in provenance.splitlines() if line.startswith("| D1 |"))
    d2_row = next(line for line in provenance.splitlines() if line.startswith("| D2 |"))
    assert DIRECTORY_URL in d1_row
    assert ENROLLMENT_URL in d2_row


# ----------------------------------------------------------------------------------
# Contrast, which axe cannot measure in a DOM that paints nothing
# ----------------------------------------------------------------------------------


def luminance(colour: str) -> float:
    raw = colour.lstrip("#")
    channels = [int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground: str, background: str) -> float:
    first, second = luminance(foreground), luminance(background)
    high, low = max(first, second), min(first, second)
    return (high + 0.05) / (low + 0.05)


FOREGROUNDS = ("ink", "ink-2", "ink-3", "accent", *STATE_COLOURS)
BACKGROUNDS = ("surface", "raised", "note")


@pytest.mark.parametrize("palette", [LIGHT, DARK], ids=["light", "dark"])
def test_every_text_pair_the_pages_use_meets_wcag_aa(palette: dict[str, str]) -> None:
    for foreground in FOREGROUNDS:
        for background in BACKGROUNDS:
            ratio = contrast(palette[foreground], palette[background])
            assert ratio >= 4.5, (foreground, background, round(ratio, 2))


@pytest.mark.parametrize("palette", [LIGHT, DARK], ids=["light", "dark"])
def test_the_focus_ring_meets_non_text_contrast(palette: dict[str, str]) -> None:
    """SC 1.4.11: the focus indicator has to be visible against what it sits on."""
    for background in BACKGROUNDS:
        assert contrast(palette["accent"], palette[background]) >= 3.0


@pytest.mark.parametrize("palette", [LIGHT, DARK], ids=["light", "dark"])
def test_each_state_colour_reads_differently_from_a_plain_number(
    palette: dict[str, str],
) -> None:
    """A state cell has to look unlike an ordinary published figure.

    Colour is not the only signal, and by itself it would not be enough (SC
    1.4.1): each state also carries its own words, tested above, and its own left
    border. What this checks is that the colours are three distinct values and
    that none of them reads as the ink a plain number is printed in.
    """
    colours = [palette[token] for token in STATE_COLOURS]
    assert len(set(colours)) == len(colours)
    for colour in colours:
        assert contrast(colour, palette["ink"]) >= 1.5


def test_both_palettes_define_the_same_tokens() -> None:
    assert set(LIGHT) == set(DARK)


# ----------------------------------------------------------------------------------
# The build itself
# ----------------------------------------------------------------------------------


def test_naming_a_school_renders_only_that_school(tmp_path: Path) -> None:
    out = tmp_path / "site"
    build = build_site(
        directory=DIRECTORY,
        enrollment=ENROLLMENT,
        out_dir=out,
        is_fixture=True,
        cds_codes=(EXAMPLE,),
    )
    assert [p.school.cds_code for p in build.schools] == [EXAMPLE]
    assert sorted(p.name for p in out.glob("*.html")) == sorted(
        page_name(EXAMPLE, locale) for locale in LOCALES
    )


def test_a_cds_code_no_active_school_carries_is_refused(tmp_path: Path) -> None:
    """Rendering an empty page for it would be a claim about a real school."""
    with pytest.raises(UnknownSchoolError, match="99999999999999"):
        build_site(
            directory=DIRECTORY,
            enrollment=ENROLLMENT,
            out_dir=tmp_path / "site",
            is_fixture=True,
            cds_codes=("99999999999999",),
        )


def test_cli_builds_pages_and_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "site"
    code = main(
        [
            "--directory",
            str(DIRECTORY),
            "--enrollment",
            str(ENROLLMENT),
            "--out",
            str(out),
            "--fixture",
        ]
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert "pages: 6 (3 schools x 2 locales)" in printed
    assert "reported=1, suppressed=1, not_reported=1" in printed
    assert "no D5 file is read here" in printed
    assert "...and 2 more" in printed


def test_cli_can_name_one_school(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "--directory",
            str(DIRECTORY),
            "--enrollment",
            str(ENROLLMENT),
            "--out",
            str(tmp_path / "site"),
            "--cds",
            EXAMPLE,
            "--fixture",
        ]
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert "pages: 2 (1 schools x 2 locales)" in printed
    assert "...and" not in printed
