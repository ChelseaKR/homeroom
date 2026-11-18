"""The missing page: one bilingual ``404.html``, served for any address with no page.

A missing address has no language. A family that mistypes a school code, or
follows a link to a school that has since closed, did not say which language
they read; so this is one page carrying both, English first and Spanish under
it, each half marked with its language, the way the front door is.

Until 2026-11-17 the site had none. GitHub Pages answered a missing address with
its own stock page, in English, with no ``lang``. From that day CloudFront serves
the domain from a private bucket (ADR 0008), and what a missing address returned
was S3's own error: an XML document that begins ``<Error><Code>NoSuchKey``, with
no title, no heading, no language and no way back, shown to a parent as a tree
of tags. The status was right and the page was nothing a person can read.

Two things make that a page:

* this file, written into the published tree as ``404.html``; and
* the distribution's custom error response (``deploy/site/template.yaml``),
  which answers S3's 404 with this page **and keeps the status 404**. GitHub
  Pages, the rollback copy, serves a root ``404.html`` the same way without
  being asked, so both origins behave alike.

What is different about this page, and why:

* **Every address in it starts at the site root.** Every other page links its
  neighbours and its stylesheet relatively, which is what keeps the tree
  servable from a subpath and from ``file://``. This page is served *at* the
  address that was missing, at any depth, so a relative ``homeroom.css`` would
  be asked for beside a page that is not there. ``/homeroom.css`` and ``/`` are
  right wherever it is shown.
* **No canonical address, no social card, not in the sitemap, and
  ``noindex``.** It has no address of its own to claim, and a crawler that
  reaches ``/404.html`` directly should not list it.
* **It says nothing about any school.** It publishes no figure and names no
  school, district or county, so it needs no acquired file and renders the
  same bytes for every build.

Same rules as every other page (ADR 0001): stdlib rendering, the one shared
stylesheet, no script, nothing fetched off this origin, deterministic output.
It is written whenever the front door is (``--landing``): a site with a root has
addresses that are not there.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from homeroom.i18n import LOCALES, Locale, text
from homeroom.render import STYLESHEET_NAME, _esc

MISSING_PAGE_NAME = "404.html"
"""The file's name at the site root.

It is the name GitHub Pages looks for, which is what makes the rollback copy
serve this page with no setting anywhere; and it is the path the distribution's
custom error response names (``ResponsePagePath: /404.html``).
``tests/test_deploy_site_template.py`` holds the two to each other.
"""

FRONT_DOOR: dict[Locale, str] = {"en": "/", "es": "/#h-es"}
"""Where each half sends its reader: the front door, in their language.

The front door is one page, English first. Its Spanish half begins at the
heading ``h-es`` (`homeroom.landing`), so the Spanish link lands there and not
at the top of an English page.
"""


def _section(locale: Locale) -> str:
    """One language's half: what happened, where to go, and the two notices."""
    return (
        f'<section lang="{locale}" aria-labelledby="missing-{locale}">\n'
        f'<h2 id="missing-{locale}">{_esc(text(locale, "missing_heading"))}</h2>\n'
        f"<p>{_esc(text(locale, 'missing_body'))}</p>\n"
        f"<p>{_esc(text(locale, 'missing_where'))} "
        f'<a href="{FRONT_DOOR[locale]}">'
        f"{_esc(text(locale, 'landing_counties_heading'))}</a></p>\n"
        f"<p>{_esc(text(locale, 'footer_no_ranking'))}</p>\n"
        f"<p>{_esc(text(locale, 'footer_unaffiliated'))}</p>\n"
        "</section>"
    )


def missing_title() -> str:
    """The page's one title: both headings, then the site's name.

    The document is ``lang="en"`` with a Spanish half, like the front door. The
    front door's title is English only because it is long; this one is two
    short phrases, and the tab of a Spanish reader's browser is the first place
    the page can say it speaks Spanish.
    """
    headings = " / ".join(text(locale, "missing_heading") for locale in LOCALES)
    return f"{headings} · {text('en', 'site_name')}"


def render_missing(*, is_fixture: bool) -> str:
    """The one missing page, English first, Spanish under it.

    ``is_fixture`` adds the fixture banner in both languages, as on the front
    door, so a fixture build cannot be mistaken for the published site. Nothing
    else varies: no school, no count, no origin.
    """
    fixture = (
        '<div class="note">\n'
        f'<p><span class="note-title">{_esc(text("en", "fixture_banner_title"))}</span> '
        f"{_esc(text('en', 'fixture_banner_body'))} "
        f'<span lang="es">{_esc(text("es", "fixture_banner_body"))}</span></p>\n</div>\n'
        if is_fixture
        else ""
    )
    sections = "\n".join(_section(locale) for locale in LOCALES)
    description = " / ".join(text(locale, "missing_body") for locale in LOCALES)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(missing_title())}</title>\n"
        f'<meta name="description" content="{_esc(description)}">\n'
        '<meta name="robots" content="noindex">\n'
        f'<link rel="stylesheet" href="/{STYLESHEET_NAME}">\n'
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


def published_missing() -> str:
    """The missing page exactly as `make publish` leaves it in ``site/``.

    `make publish` renders the tree and then runs `homeroom.analytics` over it,
    so the published page is the rendered one with that step's additions. This
    is those two steps for this one page, which needs no acquired file: it is
    how ``site/404.html`` can be written, and checked byte for byte
    (`tests/test_published_site.py`), without re-rendering 10,534 schools.
    """
    # Imported here: `homeroom.analytics` reads this module's page name.
    from homeroom import analytics

    page = render_missing(is_fixture=False)
    measurement = analytics.measurement_id()
    if measurement is None:
        return page
    pinned = analytics.integrity(analytics.loader(measurement))
    return analytics.add_to_page(page, Path(MISSING_PAGE_NAME), pinned)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="homeroom-missing",
        description=(
            "Write the missing page (404.html) into a published tree, as "
            "`make publish` would. It reads no data file."
        ),
    )
    parser.add_argument("root", type=Path, help="the published tree, e.g. site")
    args = parser.parse_args(argv)
    if not (args.root / "index.html").is_file():
        parser.error(f"{args.root} holds no index.html; it is not a published tree")
    target = args.root / MISSING_PAGE_NAME
    target.write_text(published_missing(), encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
