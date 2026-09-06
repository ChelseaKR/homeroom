"""County and district pages: how a family reaches one school out of 10,534.

Until 2026-09-05 the site published one school and the front door listed it.
Publishing all 10,534 made that same front door a flat list of 21,069 links in
2.45MB of markup -- every school, twice, once per locale -- which is not a front
door but a wall of names. A reader looking for their own school had no way in
that was not scrolling, or their browser's find.

So the site is walked the way a family already knows where it lives: county,
then district, then school. Each step is its own page rather than a control the
reader operates, because these pages carry no script and are gated on carrying
none (ADR 0001; `test_no_school_page_carries_a_script_or_reaches_off_the_page`
covers the landing page by name). A filter box is the obvious answer and the one
thing this site cannot ship.

The hierarchy is the CDS code's own. A school's CDS is 14 digits: two of county,
five of district, seven of school, and `context.district_key` already reads the
first seven as the district a school belongs to. Nothing is invented here and no
name becomes a slug: the pages are addressed by the same digits the data joins
on, so two districts that share a name stay two districts.

Same rules as every other page: stdlib rendering, the shared inline stylesheet,
no script, no external asset, deterministic output, both locales as peers.
"""

from __future__ import annotations

from homeroom.i18n import Locale, text
from homeroom.profiles import SchoolProfile
from homeroom.render import (
    STYLESHEET,
    _cde,
    _esc,
    _social_meta,
    canonical_url,
    page_name,
    social_card_name,
)

BROWSE_STYLE = """
.browse-list { padding-left: 1.3rem; }
.browse-list li { margin: 0 0 .5rem; }
.crumb { margin: 0 0 1rem; }
"""


def county_code(cds_code: str) -> str:
    """The two digits of a CDS code that name its county."""
    return cds_code[:2]


def district_code(cds_code: str) -> str:
    """The seven digits of a CDS code that name its district, county included."""
    return cds_code[:7]


def county_page_name(code: str, locale: Locale) -> str:
    """The file one county's page lands in, for one locale."""
    return f"county/{code}.{locale}.html"


def district_page_name(code: str, locale: Locale) -> str:
    """The file one district's page lands in, for one locale."""
    return f"district/{code}.{locale}.html"


def counties(profiles: list[SchoolProfile]) -> dict[str, str]:
    """County code to county name, ordered by code, for the given schools."""
    found: dict[str, str] = {}
    for profile in sorted(profiles, key=lambda p: p.school.cds_code):
        found.setdefault(county_code(profile.school.cds_code), profile.school.county)
    return found


def districts_in(
    profiles: list[SchoolProfile], code: str | None = None
) -> dict[str, str]:
    """District code to district name, ordered by code.

    ``code`` narrows to one county; left out, every district is returned.
    """
    found: dict[str, str] = {}
    for profile in sorted(profiles, key=lambda p: p.school.cds_code):
        cds = profile.school.cds_code
        if code is not None and county_code(cds) != code:
            continue
        found.setdefault(district_code(cds), profile.school.district)
    return found


def schools_in(profiles: list[SchoolProfile], code: str) -> list[SchoolProfile]:
    """The schools of one district, ordered by name then CDS code.

    Two schools in one district can share a name, so the code breaks the tie and
    the order is total: the same input always renders the same page.
    """
    return sorted(
        (p for p in profiles if district_code(p.school.cds_code) == code),
        key=lambda p: (p.school.name, p.school.cds_code),
    )


def _fixture_note(locale: Locale, is_fixture: bool) -> str:
    if not is_fixture:
        return ""
    return (
        '<div class="note">\n'
        f'<p><span class="note-title">{_esc(text(locale, "fixture_banner_title"))}</span> '
        f"{_esc(text(locale, 'fixture_banner_body'))}</p>\n</div>\n"
    )


def _shell(
    *,
    locale: Locale,
    title: str,
    heading: str,
    description: str,
    depth: str,
    crumb: str,
    listing: str,
    path: str,
    is_fixture: bool,
    site_url: str | None,
) -> str:
    """One browse page. ``depth`` is the relative prefix back to the site root."""
    if site_url is None:
        addressed = ""
    else:
        url = canonical_url(site_url, path)
        addressed = (
            f'<link rel="canonical" href="{_esc(url)}">\n'
            + _social_meta(
                title=title,
                description=description,
                url=url,
                locale=locale,
                image=canonical_url(site_url, social_card_name(locale)),
            )
            + "\n"
        )
    return (
        "<!doctype html>\n"
        f'<html lang="{locale}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(title)}</title>\n"
        f'<meta name="description" content="{_esc(description)}">\n'
        f"{addressed}"
        f"<style>\n{STYLESHEET}{BROWSE_STYLE}</style>\n"
        "</head>\n"
        "<body>\n"
        f'<a class="skip-link" href="#main">{_esc(text(locale, "skip_to_content"))}</a>\n'
        '<header class="site">\n<div class="wrap bar">\n'
        '<p class="brand">'
        f'<span class="brand-name">{_esc(text(locale, "site_name"))}</span>'
        f'<span class="brand-tag">{_esc(text(locale, "site_tagline"))}</span>'
        "</p>\n</div>\n</header>\n"
        '<main id="main" class="wrap">\n'
        f"{_fixture_note(locale, is_fixture)}"
        f'<p class="crumb">{crumb}</p>\n'
        f"<h1>{heading}</h1>\n"
        f"{listing}"
        f"<p>{_esc(text(locale, 'footer_no_ranking'))}</p>\n"
        f"<p>{_esc(text(locale, 'footer_unaffiliated'))}</p>\n"
        "</main>\n"
        "</body>\n"
        "</html>\n"
    )


def render_county(
    profiles: list[SchoolProfile],
    code: str,
    name: str,
    *,
    locale: Locale,
    is_fixture: bool,
    site_url: str | None = None,
) -> str:
    """One county's page: the districts in it that have a published school."""
    found = districts_in(profiles, code)
    items = "\n".join(
        f'<li><a href="../{_esc(district_page_name(dcode, locale))}">'
        f"{_cde(dname, locale)}</a></li>"
        for dcode, dname in found.items()
    )
    heading = _cde(text(locale, "browse_county_heading").format(county=name), locale)
    plain = text(locale, "browse_county_heading").format(county=name)
    return _shell(
        locale=locale,
        title=f"{plain} · {text(locale, 'site_name')}",
        heading=heading,
        description=f"{plain}. {text(locale, 'site_tagline')}",
        depth="../",
        crumb=f'<a href="../index.html">{_esc(text(locale, "browse_all_counties"))}</a>',
        listing=(
            f"<h2>{_esc(text(locale, 'browse_districts_label'))}</h2>\n"
            f'<ul class="browse-list">\n{items}\n</ul>\n'
        ),
        path=county_page_name(code, locale),
        is_fixture=is_fixture,
        site_url=site_url,
    )


def render_district(
    profiles: list[SchoolProfile],
    code: str,
    name: str,
    county_name: str,
    *,
    locale: Locale,
    is_fixture: bool,
    site_url: str | None = None,
) -> str:
    """One district's page: its published schools, each linked in this locale."""
    items = "\n".join(
        f'<li><a href="../{_esc(page_name(p.school.cds_code, locale))}">'
        f"{_cde(p.school.name, locale)}</a></li>"
        for p in schools_in(profiles, code)
    )
    back = text(locale, "browse_in_county").format(county=county_name)
    return _shell(
        locale=locale,
        title=f"{name} · {text(locale, 'site_name')}",
        heading=_cde(name, locale),
        description=f"{name}. {text(locale, 'site_tagline')}",
        depth="../",
        crumb=(
            f'<a href="../{_esc(county_page_name(county_code(code), locale))}">'
            f"{_cde(back, locale)}</a>"
        ),
        listing=(
            f"<h2>{_esc(text(locale, 'browse_schools_label'))}</h2>\n"
            f'<ul class="browse-list">\n{items}\n</ul>\n'
        ),
        path=district_page_name(code, locale),
        is_fixture=is_fixture,
        site_url=site_url,
    )
