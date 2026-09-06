"""The landing page: one bilingual ``index.html`` naming what is published so far.

A domain needs a front door. This one is honest about the state of the site:
Homeroom is in development, these are the schools published so far, nothing is
ranked, and the site is unofficial. Both languages sit on the one page, each
section marked with its language.

It listed every published school until 2026-09-05. That was right at one school
and absurd at 10,534: 21,069 links, 2.45MB, and no way for a reader to find
their own school but to scroll. It lists the 58 counties now, and `browse.py`
carries the two steps below them. What the page says has not changed -- these
are the schools published so far -- only how many names it puts in front of
somebody to say it.

Same rules as every other page (ADR 0001): stdlib rendering, the shared inline
stylesheet, no script, no external asset, deterministic output. It is written
only when the build is asked for it (``--landing``), so the fixture gates cover
it and a build without it is unchanged.
"""

from __future__ import annotations

from homeroom.browse import counties, county_page_name
from homeroom.i18n import LOCALES, Locale, text
from homeroom.profiles import SchoolProfile
from homeroom.render import (
    STYLESHEET,
    _cde,
    _esc,
    _social_meta,
    canonical_url,
    social_card_name,
)

LANDING_STYLE = """
.langs { display: grid; gap: 2.5rem; margin: 2rem 0; }
.county-list { columns: 12rem; column-gap: 2rem; padding-left: 1.3rem; }
.county-list li { margin: 0 0 .5rem; break-inside: avoid; }
"""


def _section(profiles: list[SchoolProfile], locale: Locale) -> str:
    """One language's half of the front door: what this is, then the counties.

    The county is the widest step a family already knows the answer to, so it is
    the one the front door asks. Districts and schools are a page each below it
    (`browse.py`), which is what keeps this page a door rather than a directory.
    """
    items = "\n".join(
        f'<li><a href="{_esc(county_page_name(code, locale))}">'
        f"{_cde(name, locale)}</a></li>"
        for code, name in counties(profiles).items()
    )
    return (
        f'<section lang="{locale}" aria-labelledby="h-{locale}">\n'
        f'<h2 id="h-{locale}">{_esc(text(locale, "site_tagline"))}</h2>\n'
        f"<p>{_esc(text(locale, 'landing_status'))}</p>\n"
        f"<h3>{_esc(text(locale, 'landing_counties_heading'))}</h3>\n"
        f'<ul class="county-list">\n{items}\n</ul>\n'
        f"<p>{_esc(text(locale, 'footer_no_ranking'))}</p>\n"
        f"<p>{_esc(text(locale, 'footer_unaffiliated'))}</p>\n"
        "</section>"
    )


def render_landing(
    profiles: list[SchoolProfile], *, is_fixture: bool, site_url: str | None = None
) -> str:
    """The one index page, English first, Spanish beside it, schools linked in both.

    ``site_url`` is the origin the build will be served from. Given, the page
    gains a canonical address and the social tags derived from it; left out, the
    page is byte-identical to one rendered before there was an origin to name.
    """
    fixture = (
        '<div class="note">\n'
        f'<p><span class="note-title">{_esc(text("en", "fixture_banner_title"))}</span> '
        f"{_esc(text('en', 'fixture_banner_body'))} "
        f'<span lang="es">{_esc(text("es", "fixture_banner_body"))}</span></p>\n</div>'
        if is_fixture
        else ""
    )
    sections = "\n".join(_section(profiles, locale) for locale in LOCALES)
    title = text("en", "site_name")
    description = f"{text('en', 'site_tagline')} / {text('es', 'site_tagline')}"
    if site_url is None:
        addressed = ""
    else:
        url = canonical_url(site_url, "index.html")
        addressed = (
            f'<link rel="canonical" href="{_esc(url)}">\n'
            + _social_meta(
                title=title,
                description=description,
                url=url,
                locale="en",
                image=canonical_url(site_url, social_card_name("en")),
            )
            + "\n"
        )
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(title)}</title>\n"
        f'<meta name="description" content="{_esc(description)}">\n'
        f"{addressed}"
        f"<style>\n{STYLESHEET}{LANDING_STYLE}</style>\n"
        "</head>\n"
        "<body>\n"
        f'<a class="skip-link" href="#main">{_esc(text("en", "skip_to_content"))}</a>\n'
        '<header class="site">\n<div class="wrap bar">\n'
        '<p class="brand">'
        f'<span class="brand-name">{_esc(text("en", "site_name"))}</span>'
        f'<span class="brand-tag">{_esc(text("en", "site_tagline"))} '
        f'<span lang="es">{_esc(text("es", "site_tagline"))}</span></span>'
        "</p>\n</div>\n</header>\n"
        '<main id="main" class="wrap">\n'
        f"<h1>{_esc(text('en', 'site_name'))}</h1>\n"
        f"{fixture}"
        f'<div class="langs">\n{sections}\n</div>\n'
        "</main>\n"
        "</body>\n"
        "</html>\n"
    )
