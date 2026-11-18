"""The ask page and the opt-in: one link, one script, nothing reached until submit.

``tools/ask-optin.mjs`` runs the script in a DOM and proves the request
timing; these tests hold the static half: the school pages change by exactly
one link and only when an endpoint is given, the ask page carries exactly one
inline script and no subresource, every fixed string is in the page's
language, and the build is deterministic.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from homeroom.askpage import ASK_STYLE, ask_page_name, render_ask_page
from homeroom.i18n import LOCALES, UI, Locale, text
from homeroom.render import DARK, LIGHT, page_name
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


def test_the_ask_page_is_the_one_page_that_still_carries_its_stylesheet_inline(
    with_ask: Path,
) -> None:
    """Every other page links `homeroom.css` since 2026-09-07. This one may not.

    `tools/ask-optin.mjs` asserts that opening an ask page issues no request
    until a question is submitted, and a linked stylesheet is a request -- one
    the browser makes before the reader has done anything. So the 6,074 bytes
    that could come off each of these pages stay on them, which is what README's
    "the one large saving is not available" is about and is the whole of what it
    is about. There are two ask pages published today, so the cost of the
    exception is 12,148 bytes; the same exception across all 10,534 schools is
    the 216 MB the README bounds the ask layer with.

    Asserted rather than left to the ADR, because the failure is silent: an ask
    page that quietly gained a `<link>` would look right, render right, and
    break a promise in `tools/ask-optin.mjs`'s language rather than in HTML.
    """
    for cds in SCHOOLS:
        for locale in LOCALES:
            path = with_ask / ask_page_name(cds, locale)
            source = path.read_text(encoding="utf-8")
            document = parse(path)
            styles = [tag for tag, _ in document.elements if tag == "style"]
            assert styles == ["style"], path.name
            assert "--surface" in source, path.name
            sheets = [
                attrs
                for tag, attrs in document.elements
                if tag == "link" and attrs.get("rel") == "stylesheet"
            ]
            assert not sheets, (path.name, sheets)


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


def _token(selector: str, declaration: str) -> str:
    """The palette token one declaration of one ask-page rule paints with."""
    rule = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", ASK_STYLE)
    assert rule, selector
    found = re.search(
        re.escape(declaration) + r":[^;]*var\(--([a-z0-9-]+)\)", rule.group(1)
    )
    assert found, (selector, declaration, rule.group(1))
    return found.group(1)


@pytest.mark.parametrize("palette", [LIGHT, DARK], ids=["light", "dark"])
def test_the_question_box_has_an_edge_a_reader_can_see(
    palette: dict[str, str],
) -> None:
    """SC 1.4.11: the box a question is typed in must be findable by its edge.

    The textarea is filled with `raised` and sits on `surface`, and those two
    are 1.03:1 apart in the light palette and 1.09:1 in the dark one -- by
    design, they are two whites and two near-blacks. So the border is the only
    thing that says where the box is, and until 2026-11-17 it was drawn in
    `rule-strong`, a hairline color: 1.69:1 on the light page and 2.10:1 on the
    dark one, under the 3:1 a control's boundary needs. A reader with low
    vision met a label and a button with nothing visible between them.

    axe-core has no rule for this; `color-contrast` reads text. It is
    arithmetic over the palette, the same arithmetic `tests/test_pages.py`
    does for text and for the focus ring, so it is done here the same way.
    """
    from tests.test_pages import contrast

    edge = palette[_token(".ask-form textarea", "border")]
    fill = palette[_token(".ask-form textarea", "background")]
    assert contrast(edge, palette["surface"]) >= 3.0, round(
        contrast(edge, palette["surface"]), 2
    )
    assert contrast(edge, fill) >= 3.0, round(contrast(edge, fill), 2)


def test_the_script_is_told_which_language_the_states_own_words_are_in(
    with_ask: Path,
) -> None:
    """SC 3.1.2: a quoted CDE passage on a Spanish page is still English.

    The answer can carry two things that are CDE's words and not Homeroom's: a
    definition quoted verbatim from a CDE page, and that page's title in the
    citation under it. Both exist in English only. The static pages mark such
    text with `lang="en"` on a Spanish page (`render._cde`); the script that
    builds the answer did not, so a Spanish screen reader read a paragraph of
    English with Spanish phonemes. The script cannot know the page's language
    from the service, so the page tells it, in the same block as its strings:
    `cde_lang` on a Spanish page, and no key at all on an English one, where
    the attribute would be redundant. `tools/ask-optin.mjs` renders an answer
    and checks the attribute lands on the quote and the title.
    """
    for cds in SCHOOLS:
        english = (with_ask / ask_page_name(cds, "en")).read_text(encoding="utf-8")
        spanish = (with_ask / ask_page_name(cds, "es")).read_text(encoding="utf-8")
        assert '"cde_lang": "en"' in spanish, cds
        assert '"cde_lang"' not in english, cds


APPROVED_FORM_MESSAGES = {
    "ask_page_hint_length": ("Up to 600 characters.", "Hasta 600 caracteres."),
    "ask_page_error_empty": ("Type a question first.", "Escriba primero una pregunta."),
}
"""The two form messages, word for word as the owner approved them on 2026-11-17."""


def test_the_form_messages_are_the_approved_words() -> None:
    for key, (english, spanish) in APPROVED_FORM_MESSAGES.items():
        assert text("en", key) == english, key
        assert text("es", key) == spanish, key


def test_the_box_the_hint_and_the_service_agree_on_the_limit() -> None:
    """One number in three places: the box, the words, and what the service accepts."""
    from homeroom.ask.structuring import MAX_QUESTION_CHARS
    from homeroom.askpage import QUESTION_MAX_LENGTH

    assert QUESTION_MAX_LENGTH == MAX_QUESTION_CHARS == 600
    for locale in LOCALES:
        assert f" {QUESTION_MAX_LENGTH} " in text(locale, "ask_page_hint_length")


def _element(source: str, element_id: str) -> tuple[str, dict[str, str | None], str]:
    """One element of a page by its id: its tag, its attributes and its text."""
    found = re.findall(
        rf'<(\w+)\b([^>]*\bid="{re.escape(element_id)}"[^>]*)>(.*?)</\1>',
        source,
        re.S,
    )
    assert len(found) == 1, (element_id, len(found))
    tag, raw, inner = found[0]
    parser = Tags()
    parser.feed(f"<{tag}{raw}>")
    return tag, parser.elements[0][1], inner


def test_the_question_box_says_how_long_a_question_may_be(with_ask: Path) -> None:
    """SC 3.3.2: the box stops at 600 characters, so the page says so first.

    `maxlength="600"` was on the textarea from the start and nothing on the
    page mentioned it: a reader typing a long question found the keys stop
    working mid-sentence. The hint sits between the label and the box, always
    visible, and the box names it in `aria-describedby`, so a screen reader
    reads it with the box and not only when the cursor happens to pass it.
    The number in the words and the number on the box are held to each other.
    """
    for cds in SCHOOLS:
        for locale in LOCALES:
            source = (with_ask / ask_page_name(cds, locale)).read_text(encoding="utf-8")
            tag, _, inner = _element(source, "ask-hint")
            assert tag == "p"
            assert inner == text(locale, "ask_page_hint_length"), (locale, inner)
            _, box, _ = _element(source, "ask-question")
            assert box["maxlength"] == "600"
            assert f"{box['maxlength']} " in inner
            assert "ask-hint" in (box.get("aria-describedby") or "").split()
            form = source[source.index('<form id="ask-form"') :].split("</form>")[0]
            assert (
                form.index("<label")
                < form.index('id="ask-hint"')
                < form.index("<textarea")
            )


def test_an_empty_question_has_somewhere_to_be_told_so(with_ask: Path) -> None:
    """SC 3.3.1: an error is identified in text, beside the box, in the page's language.

    Until 2026-11-17 a question of only spaces was dropped without a word, and
    a truly empty box got the browser's own bubble, in the browser's language
    and not the page's. The form now checks for itself (`novalidate`) and the
    page carries the place the message goes: an empty paragraph after the box,
    which the box names in `aria-describedby` so the message is read with it,
    and which is an alert so it can be announced when focus is already in the
    box. The message itself reaches the script with the other fixed strings;
    `tools/ask-optin.mjs` presses the button and reads what happens.
    """
    for cds in SCHOOLS:
        for locale in LOCALES:
            source = (with_ask / ask_page_name(cds, locale)).read_text(encoding="utf-8")
            tag, attrs, inner = _element(source, "ask-error")
            assert tag == "p" and inner == "", (tag, inner)
            assert attrs.get("role") == "alert"
            _, box, _ = _element(source, "ask-question")
            described = (box.get("aria-describedby") or "").split()
            assert described == ["ask-hint", "ask-error"], described
            assert "required" in box
            form = source[source.index('<form id="ask-form"') :].split("</form>")[0]
            assert "novalidate" in form.split(">", 1)[0]
            assert form.index("</textarea>") < form.index('id="ask-error"')
            assert form.index('id="ask-error"') < form.index("<button")
            blob = re.search(
                r'<script type="application/json" id="ask-strings">(.*?)</script>',
                source,
                re.S,
            )
            assert blob
            strings = json.loads(blob.group(1))
            assert strings["empty"] == text(locale, "ask_page_error_empty")
