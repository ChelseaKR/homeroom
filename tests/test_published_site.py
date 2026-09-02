"""The bytes actually served at homeroom.chelseakr.com.

`site/` is committed rather than built in CI, because it cannot be built in CI:
the pages are rendered from CDE files acquired by hand into `data/raw/`, which
is never in git and which CI never fetches. That is a deliberate trade, and it
has one obvious hazard -- committed output can drift from the code that made it,
or from the truth, and nothing would notice.

So these tests read the published files themselves. They cannot re-derive the
figures (that needs the acquired files), and they do not pretend to. What they
can check is every claim the published bytes make that does not require the
source data: that the site says what it is, that nothing on it is fixture data
presented as real, that every link resolves to a file that exists, that no page
reaches off-origin except the ask page's one configured endpoint, and that the
notices this project promises on every page are on every page.

`make verify` runs this on a machine with no acquired file present, which is the
whole point.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from homeroom.i18n import LOCALES, text
from tests.test_pages import FETCHING_ATTRIBUTES, SUBRESOURCE_TAGS, parse_markup

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DOMAIN = "homeroom.chelseakr.com"


def test_the_published_directory_is_here_at_all() -> None:
    """Everything below reads `site/`, so this is the floor under all of it.

    This module used to open with
    `pytestmark = pytest.mark.skipif(not SITE.is_dir(), ...)`, on the reading
    that a checkout with nothing published has nothing to check. That is not
    what this repository is: `site/` is committed, it is the bytes served at
    homeroom.chelseakr.com, and `make publish` begins with `rm -rf`. So a
    missing `site/` is a half-finished publish or a bad merge, and the skip
    turned every test in this file green for exactly the tree that most needed
    them -- fourteen checks reporting success having read nothing.
    """
    assert SITE.is_dir(), (
        "site/ is missing. It is committed, and it is what GitHub Pages "
        "serves; if `make publish` was interrupted after its `rm -rf`, restore "
        "it with `git checkout -- site` rather than publishing from here."
    )
    assert (SITE / "index.html").is_file(), "site/ exists but holds no index"


def published() -> list[Path]:
    return sorted(SITE.rglob("*.html"))


def school_pages() -> list[Path]:
    return [p for p in published() if p.parent == SITE and p.name != "index.html"]


def ask_pages() -> list[Path]:
    return [p for p in published() if p.parent.name == "ask"]


# ----------------------------------------------------------------------------------
# What the site is
# ----------------------------------------------------------------------------------


def test_the_site_names_its_own_domain_for_pages() -> None:
    """Without CNAME in the artifact, a deploy silently unsets the custom domain."""
    assert (SITE / "CNAME").read_text(encoding="utf-8").strip() == DOMAIN


def test_the_site_has_a_root_page() -> None:
    """A domain with no index answers 404 at the address people are given."""
    assert (SITE / "index.html").is_file()


def test_something_was_actually_published() -> None:
    assert school_pages(), "no school page is published"
    assert ask_pages(), "the ask link would point at nothing"


# ----------------------------------------------------------------------------------
# What it must never be
# ----------------------------------------------------------------------------------


def test_no_published_page_was_built_from_fixtures() -> None:
    """Fixture data on a public site is a synthetic school presented as a real one.

    The renderer marks a fixture build with a banner in both languages. Its
    presence here means somebody published `make site-offline`'s output.
    """
    for path in published():
        markup = path.read_text(encoding="utf-8")
        for locale in LOCALES:
            banner = text(locale, "fixture_banner_title")
            assert banner not in markup, (path.name, locale)


def test_every_published_page_carries_the_notices_this_project_promises() -> None:
    for path in published():
        markup = path.read_text(encoding="utf-8")
        assert text("en", "footer_unaffiliated") in markup or any(
            text(locale, "footer_unaffiliated") in markup for locale in LOCALES
        ), path.name
        assert any(text(locale, "footer_no_ranking") in markup for locale in LOCALES), (
            path.name
        )


def test_no_published_link_points_at_a_page_that_was_not_published() -> None:
    """A dead internal link on a school site is a claim that something is there."""
    for path in published():
        document = parse_markup(path.read_text(encoding="utf-8"))
        for href in document.hrefs:
            if href.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = (path.parent / href.split("#", 1)[0]).resolve()
            assert target.is_file(), (path.name, href)


# ----------------------------------------------------------------------------------
# What it is allowed to reach
# ----------------------------------------------------------------------------------


def test_no_school_page_carries_a_script_or_reaches_off_the_page() -> None:
    """The promise is per-page, and the published pages are where it is kept."""
    for path in [*school_pages(), SITE / "index.html"]:
        source = path.read_text(encoding="utf-8")
        document = parse_markup(source)
        for tag, attr in document.elements:
            assert tag not in SUBRESOURCE_TAGS, (path.name, tag)
            for name in attr:
                assert name not in FETCHING_ATTRIBUTES, (path.name, tag, name)
                assert not name.startswith("on"), (path.name, tag, name)
        assert "<script" not in source.lower(), path.name


def test_each_ask_page_names_exactly_one_endpoint_and_it_is_https() -> None:
    """The ask page is the only page that reaches anywhere, and only on submit.

    A published ask page pointed at an unreachable placeholder would put a form
    on a family's screen that can only ever fail, so the endpoint is checked for
    being a real https origin rather than merely present.
    """
    assert ask_pages(), "no ask page published"
    endpoints = set()
    for path in ask_pages():
        source = path.read_text(encoding="utf-8")
        blob = re.search(
            r'<script type="application/json" id="ask-strings">(.*?)</script>',
            source,
            re.S,
        )
        assert blob, path.name
        endpoint = json.loads(blob.group(1))["endpoint"]
        assert endpoint.startswith("https://"), (path.name, endpoint)
        assert endpoint.endswith("/ask"), (path.name, endpoint)
        assert ".invalid" not in endpoint, (path.name, endpoint)
        endpoints.add(endpoint)
    assert len(endpoints) == 1, endpoints


def test_every_ask_page_script_is_inline_and_nothing_else_is_fetched() -> None:
    """The ask page is allowed a script. It is not allowed to load one.

    A `src` here would mean a family's browser fetching code from somewhere
    else to read about their own child's school, which is the thing every other
    page on this site is checked for not doing.
    """
    for path in ask_pages():
        source = path.read_text(encoding="utf-8")
        document = parse_markup(source)
        scripts = [attr for tag, attr in document.elements if tag == "script"]
        assert scripts, path.name
        for attr in scripts:
            assert "src" not in attr, (path.name, attr)
        for tag, attr in document.elements:
            if tag != "script":
                assert tag not in SUBRESOURCE_TAGS, (path.name, tag)
            for name in attr:
                assert name not in FETCHING_ATTRIBUTES, (path.name, tag, name)
                assert not name.startswith("on"), (path.name, tag, name)


def test_every_school_page_is_published_in_both_languages() -> None:
    """A Spanish family arriving at an English-only site is the failure this avoids."""
    for path in school_pages():
        stem = path.name.rsplit(".", 2)[0]
        for locale in LOCALES:
            assert (SITE / f"{stem}.{locale}.html").is_file(), (stem, locale)


# ----------------------------------------------------------------------------------
# The addresses the published bytes claim
#
# `make publish` is run by hand, on a machine holding the acquired files, so the
# published bytes can fall behind the renderer with nothing noticing. These read
# the published files and check the absolute addresses in them against the
# domain the site answers on -- which, unlike the figures, is checkable with no
# acquired file and no network.
# ----------------------------------------------------------------------------------

ORIGIN = f"https://{DOMAIN}"


def indexable() -> list[Path]:
    """Every published page that is not one of the noindex ask pages."""
    return [path for path in published() if path.parent.name != "ask"]


def published_url(path: Path) -> str:
    """The address a published file answers on. The root is the bare origin."""
    return ORIGIN + ("/" if path.name == "index.html" else f"/{path.name}")


def test_every_published_page_carries_a_canonical_pointing_at_itself() -> None:
    """A canonical naming another page hands a crawler the wrong address."""
    assert indexable(), "nothing indexable is published"
    for path in indexable():
        document = parse_markup(path.read_text(encoding="utf-8"))
        assert document.canonical == published_url(path), (
            path.name,
            document.canonical,
        )


def test_every_published_page_carries_the_social_tags_a_shared_link_needs() -> None:
    """Shared anywhere, these pages have to arrive as more than a bare URL.

    `make publish` is run by hand and the output is committed, so the published
    bytes can fall behind the renderer with nothing noticing -- which is the
    hazard this whole module exists for. `tests/test_pages.py` checks that the
    renderer emits these tags; this checks that the bytes actually served carry
    them, because those are two different facts about two different trees.
    """
    assert indexable(), "nothing indexable is published"
    for path in indexable():
        document = parse_markup(path.read_text(encoding="utf-8"))
        for tag in ("og:title", "og:description", "og:image"):
            assert document.properties.get(tag), (path.name, tag)
        assert document.properties["og:url"] == published_url(path), path.name
        assert document.properties["og:type"] == "website", path.name
        assert document.metas.get("twitter:card") == "summary_large_image", path.name
        assert document.metas.get("twitter:image") == document.properties["og:image"], (
            path.name
        )


def test_every_published_card_is_a_file_that_was_actually_published() -> None:
    """`og:image` is the one address here a reader never sees fail.

    A canonical or an internal link that 404s is visible to somebody. A preview
    card that 404s renders as a bare link in a window nobody involved is
    looking at, so nothing but a check like this one would ever report it -- and
    a card type of `summary_large_image` over a missing image is worse than the
    `summary` card these pages carried before there was an image to promise.
    """
    for path in indexable():
        document = parse_markup(path.read_text(encoding="utf-8"))
        image = document.properties["og:image"]
        assert image.startswith(f"{ORIGIN}/"), (path.name, image)
        card = SITE / image.removeprefix(f"{ORIGIN}/")
        assert card.is_file(), (path.name, image)
        assert card.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", card.name


def test_each_published_language_carries_its_own_card() -> None:
    """Spanish here is a launch requirement, not a later translation phase.

    A preview is what a family sees before deciding whether to open the page, so
    an English card over the Spanish page would be the first thing a
    Spanish-reading parent is shown and the first thing telling them this site
    is not quite for them.
    """
    for path in indexable():
        if path.name == "index.html":
            continue
        locale = path.name.rsplit(".", 2)[1]
        document = parse_markup(path.read_text(encoding="utf-8"))
        assert document.properties["og:image"].endswith(f"social-card.{locale}.png"), (
            path.name,
            document.properties["og:image"],
        )
        alt = document.properties.get("og:image:alt", "")
        assert text(locale, "site_tagline") in alt, path.name


def test_no_published_address_points_at_the_old_project_path_or_plain_http() -> None:
    """The site used to answer on a github.io project path. It answers on TLS now."""
    for path in published():
        source = path.read_text(encoding="utf-8")
        assert "github.io" not in source, path.name
        assert f"http://{DOMAIN}" not in source, path.name


def test_the_published_ask_pages_are_still_noindex() -> None:
    assert ask_pages(), "no ask page published"
    for path in ask_pages():
        document = parse_markup(path.read_text(encoding="utf-8"))
        assert document.metas.get("robots") == "noindex", path.name


def test_robots_txt_is_published_and_advertises_the_sitemap() -> None:
    """Without it that address is a 404 and the sitemap is never found."""
    robots = SITE / "robots.txt"
    assert robots.is_file(), "robots.txt is not published"
    lines = [line for line in robots.read_text(encoding="utf-8").split("\n") if line]
    assert lines == [
        "User-agent: *",
        "Allow: /",
        f"Sitemap: {ORIGIN}/sitemap.xml",
    ], lines


def test_the_published_sitemap_lists_exactly_the_indexable_pages() -> None:
    sitemap = SITE / "sitemap.xml"
    assert sitemap.is_file(), "sitemap.xml is not published"
    listed = set(re.findall(r"<loc>(.*?)</loc>", sitemap.read_text(encoding="utf-8")))
    assert listed == {published_url(path) for path in indexable()}


def test_every_sitemap_url_resolves_to_a_file_that_was_published() -> None:
    """A sitemap entry for a page that is not there is a 404 handed to a crawler."""
    listed = re.findall(
        r"<loc>(.*?)</loc>", (SITE / "sitemap.xml").read_text(encoding="utf-8")
    )
    assert listed, "the sitemap lists nothing"
    for url in listed:
        assert url.startswith(f"{ORIGIN}/"), url
        assert (SITE / (url[len(ORIGIN) + 1 :] or "index.html")).is_file(), url


# ----------------------------------------------------------------------------------
# Whether a service is deployed, and whether the documents agree
#
# The ask service went live on 2026-08-22. On 2026-08-29, four documents still
# said it had not: SECURITY.md's scope ("There is no deployed service"),
# `docs/audits/threat-model.md` in three places ("no inbound network surface",
# "If deployed", "no deployment exists"), `docs/RESPONSIBLE-TECH-AUDITS.md` §F
# ("No hosted service ... no inbound network surface"), and the register's RR-07
# ("no deployment until ..."). Two of those had been edited on 2026-08-28, six
# days after the deploy, and the denials survived the edit.
#
# A security document that understates the attack surface is wrong in the
# dangerous direction: it tells a reporter there is nothing there to look at.
# So the deployment state is derived from the published bytes and the applied
# stack record, and every document that describes the surface is held to it.
# ----------------------------------------------------------------------------------

DEPLOY_RECORD = ROOT / "deploy" / "ask" / "README.md"

# Every file that tells a reader what surface this project exposes.
DOCS_DESCRIBING_THE_SURFACE = (
    "README.md",
    "SECURITY.md",
    "Makefile",
    "docs/audits/threat-model.md",
    "docs/RESPONSIBLE-TECH-AUDITS.md",
    "docs/audits/residual-risk-register.md",
)

# Ways of saying nothing is running. Each was in one of those files after the
# service was.
DENIALS = (
    "no deployed service",
    "is not deployed",
    "nothing is deployed",
    "no deployment exists",
    "no hosted service",
    "no inbound network surface",
    "before any deployment",
    "no deployment until",
    "if deployed",
    "not yet deployed",
)

QUOTED = re.compile(r'"[^"\n]*"')


def deployment_date() -> str:
    """The date the applied stack record carries, which is the deploy's own date."""
    match = re.search(r"applied (\d{4}-\d{2}-\d{2})", DEPLOY_RECORD.read_text("utf-8"))
    assert match, "deploy/ask/README.md no longer records when the stack was applied"
    return match.group(1)


def unquoted(body: str) -> str:
    """A document's prose, with quoted spans blanked.

    This repository corrects a wrong sentence by quoting it and saying what it
    said, which is the right convention and would otherwise make every
    correction look like the error it describes. So a denial inside quotation
    marks is history, and a denial outside them is a claim.
    """
    return QUOTED.sub('""', body)


def test_the_published_bytes_show_a_deployed_service() -> None:
    """The premise under the two checks below, derived rather than asserted.

    An ask page is only published with an endpoint, the endpoint is only a real
    host if a stack is answering on it, and `deploy/ask/README.md` records which
    stack. If this project is ever rolled back the way that file describes, the
    ask pages stop existing and this test says so first.
    """
    assert ask_pages(), "no ask page is published, so there is nothing to be deployed"
    record = DEPLOY_RECORD.read_text(encoding="utf-8")
    host = re.search(r"https://([a-z0-9]+\.lambda-url\.[a-z0-9-]+\.on\.aws)", record)
    assert host, "deploy/ask/README.md no longer records a Function URL"
    for path in ask_pages():
        assert host.group(1) in path.read_text(encoding="utf-8"), path.name


def test_no_document_describing_the_surface_denies_the_deployment() -> None:
    """The check that was missing while four documents denied a running service."""
    for name in DOCS_DESCRIBING_THE_SURFACE:
        body = unquoted((ROOT / name).read_text(encoding="utf-8")).lower()
        found = sorted(phrase for phrase in DENIALS if phrase in body)
        assert not found, (
            f"{name} says the service is not deployed, and the published bytes "
            f"say it is (see deploy/ask/README.md): {found}"
        )


def test_every_document_describing_the_surface_states_the_deployment() -> None:
    """A document going quiet about it fails here, rather than passing on silence."""
    date = deployment_date()
    for name in DOCS_DESCRIBING_THE_SURFACE:
        body = (ROOT / name).read_text(encoding="utf-8")
        assert date in body, f"{name} no longer states the deployment date {date}"
        assert "deployed" in body.lower(), f"{name} no longer says it is deployed"


def test_the_unmet_precondition_for_deploying_is_still_written_down() -> None:
    """RR-07 required a person to read real answers in each language first.

    Nobody had, and the service was deployed anyway. Recording that is the
    point; deleting the precondition to make the register consistent would be
    the failure this test exists to prevent. Both halves stay named: the
    evaluation half that was met, and the reading half that was not.
    """
    register = (ROOT / "docs" / "audits" / "residual-risk-register.md").read_text(
        "utf-8"
    )
    row = next(line for line in register.splitlines() if line.startswith("| RR-07 "))
    assert "read a sample of real answers in each language" in row, (
        "RR-07 no longer carries the reading commitment it was deployed without"
    )
    assert "not met" in row, "RR-07 no longer says the commitment is unmet"
    audits = (ROOT / "docs" / "RESPONSIBLE-TECH-AUDITS.md").read_text("utf-8")
    assert "Nobody has." in audits, (
        "the AI-EVAL REVIEW item no longer admits nobody has read a sample"
    )
