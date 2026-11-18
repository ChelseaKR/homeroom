"""The language switch, heard rather than seen (WCAG 2.2 SC 3.1.2).

Every page but the front door and the missing page carries one link to the
same page in the other language. Its visible text is that language's own name -- "Español" on an
English page, "English" on a Spanish one -- and a screen reader also gets a
hidden hint in the language of the page it is on: "Read this page in Spanish",
"Lea esta página en inglés".

Until 2026-11-17 the link carried ``lang`` for the *other* language and the
hint sat inside it unmarked, so the hint inherited the wrong language: an
English screen reader was told to pronounce "Read this page in Spanish" with
Spanish phonemes, and a Spanish one to pronounce "Lea esta página en inglés"
with English ones. The name was right and the instruction was garbled, on every
school, county, district and ask page.

axe-core cannot see this. The attribute is valid and it is a true statement
about one of the two phrases inside the link; only reading which words each
``lang`` covers finds it. So this reads them: the language name must be in the
language it names, and the hint must be in the language of the page.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

import pytest

from homeroom.i18n import LOCALE_NAMES, LOCALES, OTHER_LOCALE, Locale, text
from homeroom.site import build_site
from tests.test_pages import ABSENTEEISM, DIRECTORY, ENROLLMENT

VOID = {"meta", "link", "br", "img", "input", "hr"}


class SwitchLink(HTMLParser):
    """The text inside the language link, each run with the ``lang`` it inherits."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.langs: list[str | None] = []
        self.depth_in_link: int | None = None
        self.runs: list[tuple[str | None, str]] = []
        self.links = 0

    def effective(self) -> str | None:
        return next((lang for lang in reversed(self.langs) if lang), None)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in VOID:
            return
        attr = dict(attrs)
        self.langs.append(attr.get("lang"))
        if (
            tag == "a"
            and attr.get("rel") == "alternate"
            and attr.get("hreflang")
            and self.depth_in_link is None
        ):
            self.depth_in_link = len(self.langs)
            self.links += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
            return
        if self.depth_in_link is not None and len(self.langs) == self.depth_in_link:
            self.depth_in_link = None
        self.langs.pop()

    def handle_data(self, data: str) -> None:
        if self.depth_in_link is not None and data.strip():
            self.runs.append((self.effective(), data.strip()))


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("language-switch")
    build_site(
        directory=DIRECTORY,
        enrollment=ENROLLMENT,
        out_dir=out,
        is_fixture=True,
        absenteeism=ABSENTEEISM,
        ask_endpoint="https://ask.example.invalid",
        landing=True,
    )
    return out


# The two pages that are one page in both languages, so they have no twin to
# switch to: the front door and the missing page.
BILINGUAL_PAGES = {"index.html", "404.html"}


def switching_pages(built: Path) -> list[Path]:
    """Every page that has another-language twin: all but the front door and
    the missing page, which each carry both languages themselves."""
    pages = sorted(
        path for path in built.rglob("*.html") if path.name not in BILINGUAL_PAGES
    )
    kinds = {path.parent.name for path in pages}
    assert {"ask", "county", "district"} <= kinds, kinds
    assert any(path.parent == built for path in pages)
    return pages


def test_the_language_name_and_the_hint_are_each_spoken_in_their_own_language(
    built: Path,
) -> None:
    for page in switching_pages(built):
        locale: Locale = page.name.rsplit(".", 2)[1]  # type: ignore[assignment]
        assert locale in LOCALES, page
        other = OTHER_LOCALE[locale]
        parser = SwitchLink()
        parser.feed(page.read_text(encoding="utf-8"))
        where = str(page.relative_to(built))
        assert parser.links == 1, (where, parser.links)
        heard = dict((words, lang) for lang, words in parser.runs)
        assert heard == {
            LOCALE_NAMES[other]: other,
            text(locale, "switch_language_hint"): locale,
        }, (where, parser.runs)


def test_the_visible_label_still_leads_the_accessible_name(built: Path) -> None:
    """SC 2.5.3: a voice-control user says what they see, "Español" or "English"."""
    for page in switching_pages(built):
        locale: Locale = page.name.rsplit(".", 2)[1]  # type: ignore[assignment]
        parser = SwitchLink()
        parser.feed(page.read_text(encoding="utf-8"))
        assert parser.runs[0][1] == LOCALE_NAMES[OTHER_LOCALE[locale]], page.name
