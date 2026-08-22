"""The ask page and the opt-in: one link, one script, nothing reached until submit.

``tools/ask-optin.mjs`` runs the script in a DOM and proves the request
timing; these tests hold the static half: the school pages change by exactly
one link and only when an endpoint is given, the ask page carries exactly one
inline script and no subresource, every fixed string is in the page's
language, and the build is deterministic.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from homeroom.askpage import ask_page_name, render_ask_page
from homeroom.i18n import LOCALES, UI, Locale, text
from homeroom.render import page_name
from homeroom.site import build_site

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
SCHOOLS = ("01100170112345", "01100170154321", "01100170176543")
ENDPOINT = "https://ask.example.invalid"


def build(out: Path, endpoint: str | None) -> None:
    build_site(
        directory=FIXTURES / "pubschls.sample.txt",
        enrollment=FIXTURES / "cdenroll.sample.txt",
        absenteeism=FIXTURES / "chronicabsenteeism.sample.txt",
        out_dir=out,
        is_fixture=True,
        ask_endpoint=endpoint,
    )


@pytest.fixture(scope="module")
def with_ask(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("with-ask")
    build(out, ENDPOINT)
    return out


@pytest.fixture(scope="module")
def without_ask(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("without-ask")
    build(out, None)
    return out


class Tags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.scripts: list[tuple[dict[str, str | None], str]] = []
        self._in_script: dict[str, str | None] | None = None
        self._script_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        self.elements.append((tag, attributes))
        if tag == "script":
            self._in_script = attributes
            self._script_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_script is not None:
            self.scripts.append((self._in_script, "".join(self._script_text)))
            self._in_script = None

    def handle_data(self, data: str) -> None:
        if self._in_script is not None:
            self._script_text.append(data)


def parse(path: Path) -> Tags:
    tags = Tags()
    tags.feed(path.read_text(encoding="utf-8"))
    return tags


SUBRESOURCE_TAGS = frozenset(
    {"applet", "audio", "canvas", "embed", "frame", "iframe", "img", "object", "video"}
)
FETCHING_ATTRIBUTES = frozenset({"src", "srcset", "background", "poster", "ping"})


def test_without_an_endpoint_there_is_no_ask_page_and_no_link(
    without_ask: Path,
) -> None:
    assert not (without_ask / "ask").exists()
    for cds in SCHOOLS:
        for locale in LOCALES:
            source = (without_ask / page_name(cds, locale)).read_text(encoding="utf-8")
            assert 'class="ask"' not in source
            assert "ask/" not in source
            assert text(locale, "ask_link") not in source


def test_with_an_endpoint_each_school_page_gains_exactly_one_link_and_nothing_else(
    with_ask: Path, without_ask: Path
) -> None:
    for cds in SCHOOLS:
        for locale in LOCALES:
            name = page_name(cds, locale)
            with_ = (with_ask / name).read_text(encoding="utf-8")
            without = (without_ask / name).read_text(encoding="utf-8")
            link = (
                f'<p class="ask"><a href="{ask_page_name(cds, locale)}">'
                f"{text(locale, 'ask_link')}</a></p>\n"
            )
            assert with_.count(link) == 1, name
            assert with_.replace(link, "") == without, name
            assert "<script" not in with_.lower()


def test_the_ask_page_carries_one_inline_script_and_reaches_nowhere(
    with_ask: Path,
) -> None:
    for cds in SCHOOLS:
        for locale in LOCALES:
            path = with_ask / ask_page_name(cds, locale)
            source = path.read_text(encoding="utf-8")
            document = parse(path)
            kinds = [attrs.get("type") for attrs, _ in document.scripts]
            assert kinds == ["application/json", None], path.name
            for attrs, _ in document.scripts:
                assert "src" not in attrs
            for tag, attrs in document.elements:
                assert tag not in SUBRESOURCE_TAGS, (path.name, tag)
                for name in attrs:
                    assert name not in FETCHING_ATTRIBUTES, (path.name, tag, name)
                    assert not name.startswith("on"), (path.name, tag, name)
                if tag == "link":
                    assert attrs.get("rel") == "alternate"
                if tag == "a":
                    href = attrs.get("href") or ""
                    assert href.startswith(("#", "../", "0")) or href.startswith(
                        "https://www.cde.ca.gov/"
                    ), (path.name, href)
            # The endpoint lives only in the data block the script reads.
            data_block, code = document.scripts[0][1], document.scripts[1][1]
            assert ENDPOINT in data_block
            assert ENDPOINT not in code
            assert source.count(ENDPOINT) == 1
            assert "fetch(" in code and 'addEventListener("submit"' in code
            assert "innerHTML" not in code and "eval(" not in code
            assert "<" not in data_block
            for smell in ("@import", "url(", "javascript:"):
                assert smell not in source.lower(), (path.name, smell)


def test_the_ask_page_says_what_it_is_in_its_own_language(with_ask: Path) -> None:
    for cds in SCHOOLS:
        for locale in LOCALES:
            source = (with_ask / ask_page_name(cds, locale)).read_text(encoding="utf-8")
            assert f'<html lang="{locale}">' in source
            for key in (
                "ask_label_ai",
                "footer_no_ranking",
                "footer_unaffiliated",
                "ask_page_examples",
                "ask_page_intro",
                "ask_page_noscript",
                "ask_page_label_question",
                "ask_page_button",
                "ask_page_back",
            ):
                assert (
                    text(locale, key).replace("'", "&#x27;") in source
                    or text(locale, key) in source
                ), (locale, key)
            other: Locale = "es" if locale == "en" else "en"
            assert text(other, "ask_page_intro") not in source
            assert f'href="../{page_name(cds, locale)}"' in source
            assert (
                f'hreflang="{other}" rel="alternate" href="{page_name(cds, other)}"'
                in source
            )
            assert '<meta name="robots" content="noindex">' in source
            assert source.count("<h1>") == 1
            assert '<label for="ask-question">' in source
            assert 'id="ask-question"' in source and 'maxlength="600"' in source
            assert "<noscript>" in source
            assert 'aria-live="polite"' in source


def test_the_fixture_banner_is_on_the_ask_page_too(with_ask: Path) -> None:
    for locale in LOCALES:
        source = (with_ask / ask_page_name(SCHOOLS[0], locale)).read_text(
            encoding="utf-8"
        )
        assert text(locale, "fixture_banner_title") in source


def test_the_ask_pages_are_deterministic(tmp_path: Path) -> None:
    outs = []
    for name in ("a", "b"):
        out = tmp_path / name
        build(out, ENDPOINT)
        outs.append(
            {p.relative_to(out): p.read_bytes() for p in sorted(out.rglob("*.html"))}
        )
    assert outs[0] == outs[1]
    assert len(outs[0]) == 12


def test_render_ask_page_without_fixture_banner(with_ask: Path) -> None:
    from homeroom.profiles import assemble_profiles

    assembly = assemble_profiles(
        FIXTURES / "pubschls.sample.txt", FIXTURES / "cdenroll.sample.txt"
    )
    profile = assembly.profiles[0]
    page = render_ask_page(
        profile, locale="en", endpoint=ENDPOINT + "/", is_fixture=False
    )
    assert text("en", "fixture_banner_title") not in page
    assert '"endpoint": "https://ask.example.invalid/ask"' in page
    assert ask_page_name(profile.school.cds_code, "es") == (
        f"ask/{profile.school.cds_code}.es.html"
    )


def test_the_ask_page_says_nothing_untrue_before_a_question_is_asked() -> None:
    """Standing help must not be a refusal, because a refusal answers something.

    The page used to print `ask_refusal_unclear` as its help text, so every
    reader was told "It is not clear which published figure the question is
    about" before they had typed one. It is a fine sentence in reply to a
    question nobody could interpret and a false one addressed to a person who
    has not spoken yet -- and this project's whole claim is that it does not
    put untrue sentences in front of families.
    """
    from homeroom.profiles import assemble_profiles

    assembly = assemble_profiles(
        FIXTURES / "pubschls.sample.txt", FIXTURES / "cdenroll.sample.txt"
    )
    profile = assembly.profiles[0]
    for locale in LOCALES:
        markup = render_ask_page(
            profile, locale=locale, endpoint=ENDPOINT, is_fixture=False
        )
        # The refusals do ship on the page, inside the JSON the script reads,
        # because the script is what renders them when one is actually earned.
        # What must not happen is one being *displayed* before that. So this
        # reads the document with every script element removed.
        body = re.sub(r"<script\b.*?</script>", "", markup, flags=re.S)
        assert text(locale, "ask_page_examples") in body, locale
        for key, value in UI[locale].items():
            if key.startswith("ask_refusal_"):
                assert value not in body, (locale, key)
