"""Render one school profile as a static page, in one language.

Three rules govern this module, and each is checked by a test rather than trusted.

*A cell never lies about what it is.* Four things can appear where a number would
go: a published number, a published zero, a figure the state withheld, and nothing
at all. Each gets its own words, its own colour, and its own CSS class, in both
languages. The withheld and the missing never render a digit, so no reader and no
scraper can mistake either for a zero. :class:`homeroom.measures.Measure` makes
the mistake impossible upstream; this module makes it visible downstream.

*Coverage sits beside the data.* Every measure table carries, next to this
school's cell, how many of the schools in the build publish that same figure, how
many have it withheld, and how many publish nothing. A page showing only what
exists would read as a complete picture. It is not one, and the columns say so.

*Nothing is ranked, scored, or ordered.* There is no total, no average, no
composite, and no comparison of one school against another anywhere in this file
(ADR 0000). The only arithmetic here is counting measures by status, which is what
coverage is.

The markup is written for a screen reader first: one ``h1``, sectioned headings
that never skip a level, real table headers carrying ``scope``, a caption on every
table, landmarks around every region, a skip link, and CDE's English-only school
and district names marked ``lang="en"`` when they appear on a Spanish page. The
gates that hold this true are ``tests/test_pages.py`` (structure, contrast,
counted numbers) and ``make pages`` (html-validate plus axe-core in a headless
DOM).

Determinism: no wall clock, no locale-dependent formatting, no set iteration. The
same profile renders byte-identically every time, which CI asserts by building
twice and comparing hashes.
"""

from __future__ import annotations

import html
from dataclasses import dataclass

from homeroom.enrollment import GRADE_COLUMNS, TOTAL_CATEGORY
from homeroom.i18n import (
    LOCALE_NAMES,
    OTHER_LOCALE,
    Locale,
    category_name,
    cde_text_lang,
    family_name,
    format_number,
    grade_name,
    text,
)
from homeroom.measures import Measure, MeasureStatus, coverage
from homeroom.profiles import SUBGROUP_FAMILIES, ProfileAssembly, SchoolProfile

DIRECTORY_URL = "https://www.cde.ca.gov/schooldirectory/"
"""CDE's page for D1. Mirrors PROVENANCE.md; tested for agreement with it."""

ENROLLMENT_URL = "https://www.cde.ca.gov/ds/ad/filesenrcensus.asp"
"""CDE's page for D2. Mirrors PROVENANCE.md; tested for agreement with it."""

LIGHT: dict[str, str] = {
    "surface": "#fbfbf8",
    "raised": "#ffffff",
    "note": "#f2f2ec",
    "rule": "#e0e0d6",
    "rule-strong": "#c4c4b8",
    "ink": "#191a15",
    "ink-2": "#4d4e47",
    "ink-3": "#63645c",
    "accent": "#17568f",
    "zero": "#5a3f9c",
    "withheld": "#8a4210",
    "nothing": "#55564f",
}
"""The light palette, kept as data so a test can measure it.

Contrast is arithmetic over these values, and every foreground/background pair the
pages actually put together is checked against WCAG 2.2 in ``tests/test_pages.py``.
axe-core cannot do this: jsdom paints nothing. Keeping the palette here rather than
buried in a CSS string is what makes the check possible without a browser.
"""

DARK: dict[str, str] = {
    "surface": "#16171a",
    "raised": "#1e1f22",
    "note": "#232427",
    "rule": "#35363a",
    "rule-strong": "#4c4d52",
    "ink": "#f3f3ef",
    "ink-2": "#c3c4bc",
    "ink-3": "#a3a49c",
    "accent": "#8bbcf2",
    "zero": "#c0aef5",
    "withheld": "#f0a45f",
    "nothing": "#a9aaa2",
}
"""The dark palette. Same token names, so no rule needs to know the theme."""

STATE_COLOURS: tuple[str, ...] = ("zero", "withheld", "nothing")
"""The tokens that carry a measure state. Colour is never the only signal: each
state also carries its own words, so a reader who cannot see the difference still
reads the difference (WCAG 2.2 SC 1.4.1)."""


def tokens(palette: dict[str, str], *, indent: str = "  ") -> str:
    """One palette as custom-property declarations, in a fixed order."""
    return "".join(f"{indent}--{name}: {value};\n" for name, value in palette.items())


STYLESHEET = (
    f"""\
:root {{
  color-scheme: light;
{tokens(LIGHT)}}}
@media (prefers-color-scheme: dark) {{
  :root {{
    color-scheme: dark;
{tokens(DARK, indent="    ")}  }}
}}
"""
    + """
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--surface);
  color: var(--ink);
  font: 400 17px/1.6 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
.wrap { max-width: 58rem; margin: 0 auto; padding: 0 1.25rem; }
a { color: var(--accent); }
:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
.vh {
  position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0;
  overflow: hidden; clip-path: inset(50%); white-space: nowrap;
}
.skip-link {
  position: absolute; left: -9999px; top: 0; z-index: 10;
  background: var(--raised); color: var(--accent);
  padding: .6rem 1rem; border: 1px solid var(--rule-strong);
}
.skip-link:focus { left: .5rem; top: .5rem; }
.site { border-bottom: 1px solid var(--rule); background: var(--raised); }
.bar {
  display: flex; flex-wrap: wrap; gap: .75rem 1.5rem;
  align-items: baseline; justify-content: space-between;
  padding-top: .9rem; padding-bottom: .9rem;
}
.brand { margin: 0; }
.brand-name { font-weight: 700; letter-spacing: -.01em; }
.brand-tag { color: var(--ink-2); font-size: .92rem; display: block; }
.eyebrow {
  font-size: .76rem; letter-spacing: .12em; text-transform: uppercase;
  color: var(--ink-3); margin: 2rem 0 .5rem;
}
h1 { font-size: clamp(1.8rem, 1.2rem + 2.4vw, 2.6rem); line-height: 1.15; margin: 0 0 1rem; letter-spacing: -.02em; }
h2 { font-size: 1.35rem; margin: 3rem 0 .5rem; padding-top: 1.4rem; border-top: 1px solid var(--rule); letter-spacing: -.01em; }
h3 { font-size: 1.05rem; margin: 2rem 0 .4rem; color: var(--ink-2); }
p { margin: 0 0 1rem; max-width: 44rem; }
.identity { margin: 0 0 1.5rem; display: grid; grid-template-columns: max-content 1fr; gap: .3rem 1rem; max-width: 44rem; }
.identity dt { color: var(--ink-3); font-size: .9rem; }
.identity dd { margin: 0; }
.note { background: var(--note); border: 1px solid var(--rule); padding: 1rem 1.1rem; margin: 0 0 1.5rem; }
.note p:last-child { margin-bottom: 0; }
.note-title { font-weight: 700; }
.states { margin: 1rem 0 0; display: grid; grid-template-columns: max-content 1fr; gap: .55rem 1.1rem; align-items: baseline; }
.states dt { white-space: nowrap; }
.states dd { margin: 0; color: var(--ink-2); }
.scroll { overflow-x: auto; margin: 0 0 .6rem; }
table { border-collapse: collapse; width: 100%; min-width: 32rem; }
caption { text-align: left; color: var(--ink-2); font-size: .95rem; padding: 0 0 .6rem; }
th, td { text-align: left; padding: .5rem .7rem; border-bottom: 1px solid var(--rule); vertical-align: baseline; }
thead th { border-bottom: 2px solid var(--rule-strong); font-size: .85rem; color: var(--ink-2); font-weight: 600; }
tbody th { font-weight: 400; }
td.count, th.count { text-align: right; font-variant-numeric: tabular-nums; }
.num { font-variant-numeric: tabular-nums; font-weight: 600; }
.state { font-size: .86rem; }
.m-number .num { color: var(--ink); }
.m-zero { border-left: 3px solid var(--zero); }
.m-zero .num, .m-zero .state { color: var(--zero); }
.m-withheld { border-left: 3px solid var(--withheld); }
.m-withheld .state { color: var(--withheld); font-style: italic; }
.m-nothing { border-left: 3px solid var(--nothing); }
.m-nothing .state { color: var(--nothing); }
.s-number { font-weight: 600; }
.s-zero { color: var(--zero); }
.s-withheld { color: var(--withheld); font-style: italic; }
.s-nothing { color: var(--nothing); }
.coverage-note { color: var(--ink-2); font-size: .93rem; }
.sources dt { font-weight: 600; margin-top: .9rem; }
.sources dd { margin: 0; color: var(--ink-2); }
main { padding-bottom: 3rem; }
footer { border-top: 1px solid var(--rule); background: var(--raised); padding: 1.5rem 0 3rem; }
footer p { color: var(--ink-2); font-size: .92rem; }
@media (max-width: 34rem) {
  .identity, .states { grid-template-columns: 1fr; gap: .15rem; }
  .states dd { margin-bottom: .6rem; }
}
"""
)


@dataclass(frozen=True)
class SourceRef:
    """One acquired file, as the page names it.

    ``access_date`` is ``None`` for a fixture build and for any source nobody has
    downloaded. The page then says so in words rather than printing a date, which
    is the same rule ``coverage.json`` follows.
    """

    key: str
    file_name: str
    url: str
    access_date: str | None
    academic_year: str | None = None


@dataclass(frozen=True)
class SiteCoverage:
    """How many schools in this build publish each figure.

    Counted from the same assembly the pages render, with
    :func:`homeroom.measures.coverage`. Nothing here is an average or a rate; it
    is a tally of statuses, which is the only arithmetic the project permits over
    measures.
    """

    schools: int
    total_enrollment: dict[str, int]
    grades: dict[str, dict[str, int]]
    subgroups: dict[str, dict[str, int]]
    unjoined_school_totals: int


def site_coverage(assembly: ProfileAssembly) -> SiteCoverage:
    profiles = assembly.profiles
    return SiteCoverage(
        schools=len(profiles),
        total_enrollment=coverage(p.total_enrollment for p in profiles),
        grades={
            grade: coverage(p.grades[grade] for p in profiles)
            for grade in GRADE_COLUMNS
        },
        subgroups={
            code: coverage(p.subgroups[code] for p in profiles)
            for family in SUBGROUP_FAMILIES.values()
            for code in family
        },
        unjoined_school_totals=assembly.unjoined_school_totals,
    )


@dataclass(frozen=True)
class Row:
    """One measure as a table row: its name, this school's cell, and coverage."""

    label: str
    measure: Measure
    counts: dict[str, int]


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def _cde(value: str, locale: Locale) -> str:
    """CDE-published text, marked with the language CDE published it in.

    School, district, county, and city names exist in English only in the source
    files. Marking them keeps a Spanish screen reader from reading English words
    with Spanish phonemes (WCAG 2.2 SC 3.1.2). On an English page the attribute
    would be redundant, so it is not emitted.
    """
    lang = cde_text_lang(locale)
    if lang is None:
        return _esc(value)
    return f'<span lang="{lang}">{_esc(value)}</span>'


def _measure_cell(measure: Measure, locale: Locale) -> str:
    """One school's value, in whichever of the four states it is actually in."""
    if measure.status is MeasureStatus.REPORTED:
        number = f'<span class="num">{_esc(format_number(measure.number()))}</span>'
        if measure.is_zero:
            label = _esc(text(locale, "state_zero_label"))
            return (
                f'<td class="m m-zero">{number} <span class="state">{label}</span></td>'
            )
        return f'<td class="m m-number">{number}</td>'
    if measure.status is MeasureStatus.SUPPRESSED:
        label = _esc(text(locale, "state_withheld_label"))
        return f'<td class="m m-withheld"><span class="state">{label}</span></td>'
    label = _esc(text(locale, "state_nothing_label"))
    return f'<td class="m m-nothing"><span class="state">{label}</span></td>'


def _measure_table(
    *,
    locale: Locale,
    caption: str,
    row_header: str,
    rows: list[Row],
) -> str:
    """A measure table: one row per figure, this school beside the coverage tally.

    Wrapped in a named, focusable ``section`` because the table can overflow a
    narrow screen, and a scrollable box that cannot be reached from the keyboard is
    a WCAG 2.2 SC 2.1.1 failure. A ``section`` with an accessible name is a region
    landmark natively, so the wrapper needs no ARIA role of its own.
    """
    head = "".join(
        f'<th scope="col" class="count">{_esc(text(locale, key))}</th>'
        for key in ("col_publishing", "col_withholding", "col_nothing")
    )
    body: list[str] = []
    for row in rows:
        counts = "".join(
            f'<td class="count">{_esc(format_number(row.counts[status]))}</td>'
            for status in ("reported", "suppressed", "not_reported")
        )
        body.append(
            f'<tr><th scope="row">{row.label}</th>'
            f"{_measure_cell(row.measure, locale)}{counts}</tr>"
        )
    rows_html = "\n".join(body)
    return (
        f'<section class="scroll" tabindex="0" aria-label="{_esc(caption)}">\n'
        "<table>\n"
        f"<caption>{_esc(caption)}</caption>\n"
        "<thead><tr>"
        f'<th scope="col">{_esc(row_header)}</th>'
        f'<th scope="col">{_esc(text(locale, "col_this_school"))}</th>'
        f"{head}</tr></thead>\n"
        f"<tbody>\n{rows_html}\n</tbody>\n"
        "</table>\n"
        "</section>"
    )


def _section(anchor: str, heading: str, body: str) -> str:
    return (
        f'<section aria-labelledby="{anchor}">\n'
        f'<h2 id="{anchor}">{_esc(heading)}</h2>\n'
        f"{body}\n"
        "</section>"
    )


def _identity(profile: SchoolProfile, locale: Locale) -> str:
    school = profile.school
    type_key = "identity_type_charter" if school.charter else "identity_type_district"
    pairs: list[tuple[str, str]] = [
        ("identity_district", _cde(school.district, locale)),
        ("identity_city", _cde(school.city, locale)),
        ("identity_county", _cde(school.county, locale)),
        ("identity_grades", _esc(school.grades_served)),
        ("identity_type", _esc(text(locale, type_key))),
        ("identity_cds", _esc(school.cds_code)),
    ]
    items = "\n".join(
        f"<dt>{_esc(text(locale, key))}</dt><dd>{value}</dd>"
        for key, value in pairs
        if value
    )
    return f'<dl class="identity">\n{items}\n</dl>'


def _states_legend(locale: Locale) -> str:
    entries = (
        ("s-number", "state_number_label", "state_number_body"),
        ("s-zero", "state_zero_label", "state_zero_body"),
        ("s-withheld", "state_withheld_label", "state_withheld_body"),
        ("s-nothing", "state_nothing_label", "state_nothing_body"),
    )
    items = "\n".join(
        f'<dt class="{css}">{_esc(text(locale, label))}</dt>'
        f"<dd>{_esc(text(locale, body))}</dd>"
        for css, label, body in entries
    )
    return f'<dl class="states">\n{items}\n</dl>'


def _how_to_read(locale: Locale) -> str:
    return _section(
        "how-to-read",
        text(locale, "how_to_read_heading"),
        f"<p>{_esc(text(locale, 'no_ranking_body'))}</p>\n"
        f"<p>{_esc(text(locale, 'states_intro'))}</p>\n"
        f"<h3>{_esc(text(locale, 'states_heading'))}</h3>\n"
        f"{_states_legend(locale)}",
    )


def _coverage_note(locale: Locale, cover: SiteCoverage) -> str:
    note = text(locale, "coverage_note").format(
        schools=format_number(cover.schools),
    )
    return f'<p class="coverage-note">{_esc(note)}</p>'


def _students_section(
    profile: SchoolProfile, locale: Locale, cover: SiteCoverage
) -> str:
    caption = text(locale, "caption_total").format(
        school=profile.school.name, year=profile.academic_year
    )
    table = _measure_table(
        locale=locale,
        caption=caption,
        row_header=text(locale, "col_figure"),
        rows=[
            Row(
                label=_esc(category_name(locale, TOTAL_CATEGORY)),
                measure=profile.total_enrollment,
                counts=cover.total_enrollment,
            )
        ],
    )
    return _section(
        "students",
        text(locale, "students_heading"),
        f"{table}\n{_coverage_note(locale, cover)}",
    )


def _grades_section(profile: SchoolProfile, locale: Locale, cover: SiteCoverage) -> str:
    caption = text(locale, "caption_grades").format(
        school=profile.school.name, year=profile.academic_year
    )
    table = _measure_table(
        locale=locale,
        caption=caption,
        row_header=text(locale, "col_grade"),
        rows=[
            Row(
                label=_esc(grade_name(locale, grade)),
                measure=profile.grades[grade],
                counts=cover.grades[grade],
            )
            for grade in GRADE_COLUMNS
        ],
    )
    return _section("grades", text(locale, "grades_heading"), table)


def _groups_section(profile: SchoolProfile, locale: Locale, cover: SiteCoverage) -> str:
    blocks: list[str] = [f"<p>{_esc(text(locale, 'groups_intro'))}</p>"]
    for family, codes in SUBGROUP_FAMILIES.items():
        caption = text(locale, "caption_groups").format(
            family=family_name(locale, family),
            school=profile.school.name,
            year=profile.academic_year,
        )
        table = _measure_table(
            locale=locale,
            caption=caption,
            row_header=text(locale, "col_group"),
            rows=[
                Row(
                    label=_esc(category_name(locale, code)),
                    measure=profile.subgroups[code],
                    counts=cover.subgroups[code],
                )
                for code in codes
            ],
        )
        blocks.append(f"<h3>{_esc(family_name(locale, family))}</h3>\n{table}")
    return _section("groups", text(locale, "groups_heading"), "\n".join(blocks))


def _coverage_section(locale: Locale, cover: SiteCoverage) -> str:
    pairs = (
        ("coverage_schools", cover.schools),
        ("coverage_total_published", cover.total_enrollment["reported"]),
        ("coverage_total_withheld", cover.total_enrollment["suppressed"]),
        ("coverage_total_nothing", cover.total_enrollment["not_reported"]),
        ("coverage_unjoined", cover.unjoined_school_totals),
    )
    items = "\n".join(
        f"<dt>{_esc(text(locale, key))}</dt>"
        f'<dd class="count">{_esc(format_number(value))}</dd>'
        for key, value in pairs
    )
    return _section(
        "coverage",
        text(locale, "coverage_heading"),
        f"<p>{_esc(text(locale, 'coverage_body'))}</p>\n"
        f'<dl class="identity">\n{items}\n</dl>',
    )


def _not_yet_section(locale: Locale) -> str:
    body = "\n".join(
        f"<p>{_esc(text(locale, key))}</p>"
        for key in ("not_yet_assignments", "not_yet_context", "not_yet_measures")
    )
    return _section("not-yet", text(locale, "not_yet_heading"), body)


def _source_entry(source: SourceRef, locale: Locale) -> str:
    name = text(locale, f"source_{source.key}_name")
    title = text(locale, f"source_{source.key}_title")
    parts = [f"{_esc(text(locale, 'source_file'))}: {_esc(source.file_name)}"]
    if source.academic_year:
        parts.append(
            f"{_esc(text(locale, 'source_year'))}: {_esc(source.academic_year)}"
        )
    if source.access_date is None:
        parts.append(_esc(text(locale, "source_fixture")))
    else:
        parts.append(
            f"{_esc(text(locale, 'source_downloaded'))}: {_esc(source.access_date)}"
        )
    link = f'<a href="{_esc(source.url)}">{_esc(text(locale, "source_page"))}</a>'
    return f"<dt>{_esc(name)}</dt>\n<dd>{_esc(title)}. {'. '.join(parts)}. {link}</dd>"


def _sources_section(sources: tuple[SourceRef, ...], locale: Locale) -> str:
    entries = "\n".join(_source_entry(source, locale) for source in sources)
    return _section(
        "sources",
        text(locale, "sources_heading"),
        f"<p>{_esc(text(locale, 'sources_body'))}</p>\n"
        f'<dl class="sources">\n{entries}\n</dl>',
    )


def _fixture_banner(locale: Locale) -> str:
    return (
        '<div class="note">\n'
        f'<p><span class="note-title">{_esc(text(locale, "fixture_banner_title"))}</span> '
        f"{_esc(text(locale, 'fixture_banner_body'))}</p>\n"
        "</div>"
    )


def page_name(cds_code: str, locale: Locale) -> str:
    """The file one school's page lands in, for one locale."""
    return f"{cds_code}.{locale}.html"


def _head(profile: SchoolProfile, locale: Locale, title: str) -> str:
    school = profile.school
    description = text(locale, "meta_description").format(
        school=school.name, district=school.district
    )
    alternates = "\n".join(
        f'<link rel="alternate" hreflang="{other}" '
        f'href="{page_name(school.cds_code, other)}">'
        for other in (locale, OTHER_LOCALE[locale])
    )
    return (
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(title)}</title>\n"
        f'<meta name="description" content="{_esc(description)}">\n'
        f"{alternates}\n"
        f"<style>\n{STYLESHEET}</style>\n"
        "</head>"
    )


def _header(profile: SchoolProfile, locale: Locale) -> str:
    other = OTHER_LOCALE[locale]
    href = page_name(profile.school.cds_code, other)
    return (
        '<header class="site">\n'
        '<div class="wrap bar">\n'
        '<p class="brand">'
        f'<span class="brand-name">{_esc(text(locale, "site_name"))}</span>'
        f'<span class="brand-tag">{_esc(text(locale, "site_tagline"))}</span>'
        "</p>\n"
        f'<nav aria-label="{_esc(text(locale, "language_nav"))}">\n'
        f'<a lang="{other}" hreflang="{other}" rel="alternate" href="{_esc(href)}">'
        f"{_esc(LOCALE_NAMES[other])}"
        f'<span class="vh"> {_esc(text(locale, "switch_language_hint"))}</span></a>\n'
        "</nav>\n"
        "</div>\n"
        "</header>"
    )


def render_school(
    profile: SchoolProfile,
    *,
    locale: Locale,
    cover: SiteCoverage,
    sources: tuple[SourceRef, ...],
    is_fixture: bool,
) -> str:
    """One school, one language, as a complete standalone HTML document."""
    school = profile.school
    title = (
        text(locale, "page_title").format(
            school=school.name, year=profile.academic_year
        )
        + " · "
        + text(locale, "site_name")
    )
    body_parts = [
        f'<a class="skip-link" href="#main">{_esc(text(locale, "skip_to_content"))}</a>',
        _header(profile, locale),
        '<main id="main" class="wrap">',
        f'<p class="eyebrow">{_esc(text(locale, "eyebrow"))}</p>',
        f"<h1>{_cde(school.name, locale)}</h1>",
        *([_fixture_banner(locale)] if is_fixture else []),
        _identity(profile, locale),
        _how_to_read(locale),
        _students_section(profile, locale, cover),
        _grades_section(profile, locale, cover),
        _groups_section(profile, locale, cover),
        _coverage_section(locale, cover),
        _not_yet_section(locale),
        _sources_section(sources, locale),
        "</main>",
        '<footer>\n<div class="wrap">\n'
        f"<p>{_esc(text(locale, 'footer_no_ranking'))}</p>\n"
        f"<p>{_esc(text(locale, 'footer_unaffiliated'))}</p>\n"
        "</div>\n</footer>",
    ]
    body = "\n".join(body_parts)
    return (
        "<!doctype html>\n"
        f'<html lang="{locale}">\n'
        f"{_head(profile, locale, title)}\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )
