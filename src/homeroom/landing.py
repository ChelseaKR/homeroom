"""The landing page: one bilingual ``index.html`` naming what is published.

A domain needs a front door. This one is honest about the state of the site:
every active school is published, it says how many, nothing is ranked, and the
site is unofficial. Both languages sit on the one page, each section marked with
its language. A build of fewer schools than the directory holds (``--cds``) says
"published so far" instead, because "every" would then be false (ADR 0007).

It listed every published school until 2026-09-05. That was right at one school
and absurd at 10,534: 21,069 links, 2.45MB, and no way for a reader to find
their own school but to scroll. It lists the 58 counties now, and `browse.py`
carries the two steps below them. Until ADR 0007 its status line still said
"in development ... published so far" months after every active school was
published; it now says every school, with the count the build rendered.

Same rules as every other page (ADR 0001): stdlib rendering, the one shared
stylesheet, no script, nothing fetched off this origin, deterministic output. It
is written only when the build is asked for it (``--landing``), so the fixture
gates cover it and a build without it is unchanged.

This page saves nothing by linking the stylesheet rather than inlining it --
there is one of it, so the file it links costs what the block it dropped cost.
It links anyway, because it is the first page a family lands on and the walk
from here to a county, a district and a school is four pages: linking means one
stylesheet fetched once rather than a copy of it in each of the four.
"""

from __future__ import annotations

from homeroom.browse import counties, county_page_name
from homeroom.i18n import LOCALES, Locale, format_number, text
from homeroom.profiles import SchoolProfile
from homeroom.render import (
    REPOSITORY_URL,
    _cde,
    _esc,
    _social_meta,
    canonical_url,
    social_card_name,
    stylesheet_link,
)

LANDING_STYLE = """
.langs { display: grid; gap: 2.5rem; margin: 2rem 0; }
.county-list { columns: 12rem; column-gap: 2rem; padding-left: 1.3rem; }
.county-list li { margin: 0 0 .5rem; break-inside: avoid; }
"""


def _source_link(locale: Locale) -> str:
    """One sentence, in this language, and the link out to the repository.

    Every page on this site names the CDE download page each figure came from,
    so a reader can check a number against the state's own file. Until this
    line, nothing named the code that turned those files into a sentence about
    a real school -- the one thing a reader who distrusts this site cannot get
    to from anywhere on it. It sits on the front door rather than on all 21,069
    school pages: the pages are committed bytes republished by hand, the
    published tree is already at 86.8% of the ceiling it deploys under
    (`homeroom.publish_limits`, issue #82), and a link every page carries is a
    link the front door already carries 23,310 times over.

    The link text is a sentence in its own language rather than a bare URL: a
    screen reader announces link text out of context, and "https://github.com/
    ChelseaKR/homeroom" read character by character is not what was meant.
    """
    return (
        f"<p>{_esc(text(locale, 'landing_source_body'))} "
        f'<a href="{_esc(REPOSITORY_URL)}">'
        f"{_esc(text(locale, 'landing_source_link'))}</a></p>"
    )


def _status(profiles: list[SchoolProfile], locale: Locale, *, complete: bool) -> str:
    """What is published, counted from what this build rendered (ADR 0007)."""
    if not complete:
        return text(locale, "landing_status_partial")
    return text(locale, "landing_status").format(count=format_number(len(profiles)))


def _section(profiles: list[SchoolProfile], locale: Locale, *, complete: bool) -> str:
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
        f"<p>{_esc(_status(profiles, locale, complete=complete))}</p>\n"
        f"<h3>{_esc(text(locale, 'landing_counties_heading'))}</h3>\n"
        f'<ul class="county-list">\n{items}\n</ul>\n'
        f"<p>{_esc(text(locale, 'footer_no_ranking'))}</p>\n"
        f"<p>{_esc(text(locale, 'footer_unaffiliated'))}</p>\n"
        f"{_source_link(locale)}\n"
        "</section>"
    )


def render_landing(
    profiles: list[SchoolProfile],
    *,
    is_fixture: bool,
    site_url: str | None = None,
    complete: bool = True,
) -> str:
    """The one index page, English first, Spanish beside it, schools linked in both.

    ``site_url`` is the origin the build will be served from. Given, the page
    gains a canonical address and the social tags derived from it; left out, the
    page is byte-identical to one rendered before there was an origin to name.

    ``complete`` says the build rendered every active school in the directory; a
    ``--cds`` build passes False and keeps the "published so far" wording.
    """
    fixture = (
        '<div class="note">\n'
        f'<p><span class="note-title">{_esc(text("en", "fixture_banner_title"))}</span> '
        f"{_esc(text('en', 'fixture_banner_body'))} "
        f'<span lang="es">{_esc(text("es", "fixture_banner_body"))}</span></p>\n</div>'
        if is_fixture
        else ""
    )
    sections = "\n".join(
        _section(profiles, locale, complete=complete) for locale in LOCALES
    )
    # The page is bilingual under lang="en", so its one title is the English one.
    title = text("en", "landing_title")
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
        f"{stylesheet_link()}\n"
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
