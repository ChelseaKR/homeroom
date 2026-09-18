"""Google Analytics 4, added to rendered pages by `homeroom.analytics`.

What the loader does in a browser is `tools/analytics.mjs`'s to prove (it runs in
`make pages`). This file holds the step that puts it on the page: where each
piece goes, that it goes there once, that it refuses a page it does not
recognize, that an empty ID adds nothing, and that `make publish` runs it before
the tree is weighed.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

import pytest

from homeroom import analytics
from homeroom.i18n import LOCALES, text

ROOT = Path(__file__).resolve().parent.parent

SCHOOL = """<!doctype html>
<html lang="{lang}">
<head>
<title>School</title>
</head>
<body>
<main id="main" class="wrap"><h1>School</h1></main>
<footer>
<div class="wrap">
<p>notice</p>
</div>
</footer>
</body>
</html>
"""

BROWSE = """<!doctype html>
<html lang="{lang}">
<head>
<title>County</title>
</head>
<body>
<main id="main" class="wrap"><h1>County</h1>
<p>notice</p>
</main>
</body>
</html>
"""

LANDING = """<!doctype html>
<html lang="en">
<head>
<title>Homeroom</title>
</head>
<body>
<main id="main" class="wrap">
<h1>Homeroom</h1>
<div class="langs">
<section lang="en" aria-labelledby="h-en">
<h2 id="h-en">English</h2>
</section>
<section lang="es" aria-labelledby="h-es">
<h2 id="h-es">Español</h2>
</section>
</div>
</main>
</body>
</html>
"""


def tree(tmp_path: Path) -> Path:
    site = tmp_path / "site"
    (site / "county").mkdir(parents=True)
    (site / "ask").mkdir()
    (site / "index.html").write_text(LANDING, encoding="utf-8")
    for lang in LOCALES:
        (site / f"01100170112345.{lang}.html").write_text(
            SCHOOL.format(lang=lang), encoding="utf-8"
        )
        (site / "ask" / f"01100170112345.{lang}.html").write_text(
            SCHOOL.format(lang=lang), encoding="utf-8"
        )
        (site / "county" / f"01.{lang}.html").write_text(
            BROWSE.format(lang=lang), encoding="utf-8"
        )
    (site / "CNAME").write_text("homeroom.chelseakr.com\n", encoding="utf-8")
    return site


def snapshot(site: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(site)): p.read_bytes() for p in site.rglob("*") if p.is_file()
    }


def test_the_configured_id_is_the_production_stream() -> None:
    assert analytics.GA4_MEASUREMENT_ID == "G-PMC113MW2C"
    assert analytics.measurement_id() == "G-PMC113MW2C"
    assert analytics.PRODUCTION_HOST == "homeroom.chelseakr.com"


@pytest.mark.parametrize("raw", ["", "   "])
def test_an_empty_id_adds_nothing_and_writes_nothing(tmp_path: Path, raw: str) -> None:
    site = tree(tmp_path)
    before = snapshot(site)
    assert analytics.add_to_tree(site, raw) == 0
    assert snapshot(site) == before
    assert not (site / analytics.SCRIPT_NAME).exists()


@pytest.mark.parametrize("raw", ["UA-12345-1", "G-", "g-pmc113mw2c", 'G-PMC"><x>'])
def test_a_malformed_id_is_refused_before_anything_is_written(
    tmp_path: Path, raw: str
) -> None:
    site = tree(tmp_path)
    before = snapshot(site)
    with pytest.raises(ValueError, match="not a GA4 measurement ID"):
        analytics.add_to_tree(site, raw)
    assert snapshot(site) == before


def test_every_page_gets_one_pinned_script_with_a_relative_path(tmp_path: Path) -> None:
    site = tree(tmp_path)
    assert analytics.add_to_tree(site) == 7
    loader = (site / "analytics.js").read_bytes()
    pinned = "sha384-" + base64.b64encode(hashlib.sha384(loader).digest()).decode()
    for page in site.rglob("*.html"):
        source = page.read_text(encoding="utf-8")
        depth = len(page.relative_to(site).parts) - 1
        tags = re.findall(r"<script[^>]*></script>", source)
        assert tags == [
            f'<script src="{"../" * depth}analytics.js" defer integrity="{pinned}" '
            f"{analytics.MARKER}></script>"
        ], page
        assert source.index("<script") < source.index("</head>"), page


def test_the_loader_carries_the_id_the_host_the_key_and_both_languages(
    tmp_path: Path,
) -> None:
    site = tree(tmp_path)
    analytics.add_to_tree(site)
    script = (site / "analytics.js").read_text(encoding="utf-8")
    assert 'var ID = "G-PMC113MW2C";' in script
    assert 'var HOST = "homeroom.chelseakr.com";' in script
    assert 'var KEY = "homeroom.chelseakr.com:analytics-opt-out";' in script
    assert "allow_google_signals: false" in script
    assert "allow_ad_personalization_signals: false" in script
    labels = json.loads(re.search(r"var LABELS = (\{.*\});", script).group(1))  # type: ignore[union-attr]
    for locale in LOCALES:
        assert labels[locale]["optOut"] == text(locale, "analytics_opt_out")
        assert labels[locale]["optIn"] == text(locale, "analytics_opt_in")
    assert "__" not in script.replace("__proto__", ""), "a template token was left"


def test_school_and_ask_pages_get_the_note_at_the_end_of_the_footer(
    tmp_path: Path,
) -> None:
    site = tree(tmp_path)
    analytics.add_to_tree(site)
    for lang in LOCALES:
        for page, prefix in (
            (site / f"01100170112345.{lang}.html", ""),
            (site / "ask" / f"01100170112345.{lang}.html", "../"),
        ):
            source = page.read_text(encoding="utf-8")
            note = source[source.index("<footer>") :]
            assert note.count(text(lang, "analytics_note")) == 1, page
            assert f'href="{prefix}index.html#privacy-{lang}"' in note, page
            assert note.count('class="analytics-opt-out"') == 1, page
            assert note.index("analytics-note") < note.index("</footer>"), page


def test_browse_pages_get_the_note_at_the_end_of_main(tmp_path: Path) -> None:
    site = tree(tmp_path)
    analytics.add_to_tree(site)
    for lang in LOCALES:
        source = (site / "county" / f"01.{lang}.html").read_text(encoding="utf-8")
        assert source.count(text(lang, "analytics_note")) == 1
        assert source.index("analytics-note") < source.index("</main>")
        assert f'href="../index.html#privacy-{lang}"' in source


def test_the_landing_page_carries_the_whole_disclosure_in_each_language(
    tmp_path: Path,
) -> None:
    site = tree(tmp_path)
    analytics.add_to_tree(site)
    source = (site / "index.html").read_text(encoding="utf-8")
    for lang in LOCALES:
        section = source[source.index(f'<section lang="{lang}"') :]
        section = section[: section.index("</section>")]
        assert f'id="privacy-{lang}"' in section
        for key in ("privacy_body", "privacy_cookies", "privacy_opt_out"):
            assert text(lang, key).replace("&", "&amp;") in section, (lang, key)
        assert section.count('class="analytics-opt-out"') == 1
    assert "analytics-note" not in source


def test_a_second_run_is_refused_rather_than_doubling_the_script(
    tmp_path: Path,
) -> None:
    site = tree(tmp_path)
    analytics.add_to_tree(site)
    with pytest.raises(ValueError, match="already carries Google Analytics"):
        analytics.add_to_tree(site)


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        ('<html lang="en"><body><main></main></body></html>', "</head>"),
        (SCHOOL.format(lang="fr"), "<html lang>"),
        ('<html lang="en"><head></head><body><p>x</p></body></html>', "</main>"),
    ],
)
def test_a_page_of_an_unknown_shape_is_refused(source: str, reason: str) -> None:
    with pytest.raises(ValueError, match=re.escape(reason)):
        analytics.add_to_page(source, Path("x.en.html"), "sha384-x")


def test_the_disclosure_describes_what_the_loader_does() -> None:
    """The copy is a claim about the code; these are the parts that could drift."""
    script = analytics.loader("G-PMC113MW2C")
    for locale in LOCALES:
        body = text(locale, "privacy_body")
        cookies = text(locale, "privacy_cookies")
        opt_out = text(locale, "privacy_opt_out")
        assert "Google LLC" in body
        assert "utm_source" in body
        assert "_ga" in cookies and "14" in cookies
        assert "Global Privacy Control" in opt_out and "Do Not Track" in opt_out
        assert text(locale, "analytics_opt_out") in opt_out
        assert text(locale, "analytics_opt_in") in opt_out
    for region in ("DE", "FR", "GB", "CH", "NO", "IS", "LI"):
        assert f'"{region}"' in script
    assert '"US"' not in script


def test_publish_adds_ga_to_the_staged_tree_before_weighing_it() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    recipe = makefile[
        makefile.index("\npublish:") : makefile.index("\npublish-limits:")
    ]
    step = "uv run python -m homeroom.analytics $(PUBLISH_STAGE)"
    assert step in recipe
    assert recipe.index("CNAME") < recipe.index(step) < recipe.index("publish-limits")


def test_the_page_gates_run_the_analytics_harness() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    pages = next(line for line in makefile.splitlines() if line.startswith("pages:"))
    assert "analytics-gate" in pages.split()
    assert "node tools/analytics.mjs build/site-offline-analytics" in makefile
