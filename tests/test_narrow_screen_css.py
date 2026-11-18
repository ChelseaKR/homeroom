"""What the stylesheet does on a narrow screen, where no headless DOM can look.

`tools/a11y.mjs` runs axe-core in jsdom, which does no layout, so it cannot say
whether a page scrolls sideways at 320 CSS pixels (WCAG 2.2 SC 1.4.10) or when a
reader widens the spacing of text (SC 1.4.12). The 2026-11-17 accessibility
sweep measured both in Chromium and WebKit, on the published pages, and found
the rules below. A browser is not part of `make verify`, so what is held here is
the rule that fixes each one, read out of the stylesheet the build writes, plus
a control showing the check notices when the rule is gone.

1. The legend of cell states ("What each cell can say"). Its four terms were
   `white-space: nowrap`, which is right beside their definitions on a wide
   screen and wrong once the list stacks to one column: with the text-spacing
   overrides SC 1.4.12 names (letter spacing 0.12em, word spacing 0.16em),
   "retenido para proteger la privacidad" is wider than a 320 pixel screen, and
   every Spanish school page scrolled sideways by 57 pixels. In the stacked
   layout the terms may wrap.
"""

from __future__ import annotations

import re

import pytest

from homeroom.render import STYLESHEET_NAME
from homeroom.site import build_site
from tests.test_pages import DIRECTORY, ENROLLMENT

NARROW = "@media (max-width: 34rem) {"


@pytest.fixture(scope="module")
def css(tmp_path_factory: pytest.TempPathFactory) -> str:
    out = tmp_path_factory.mktemp("narrow")
    build_site(directory=DIRECTORY, enrollment=ENROLLMENT, out_dir=out, is_fixture=True)
    return (out / STYLESHEET_NAME).read_text(encoding="utf-8")


def narrow_block(css: str) -> str:
    """The body of the one narrow-screen media query, braces balanced."""
    assert css.count(NARROW) == 1
    start = css.index(NARROW) + len(NARROW)
    depth, index = 1, start
    while depth:
        depth += {"{": 1, "}": -1}.get(css[index], 0)
        index += 1
    return css[start : index - 1]


def declarations(block: str, selector: str) -> str:
    """Every declaration a block gives one exact selector, as one string."""
    found = [
        body
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", block)
        if selector in [part.strip() for part in selectors.split(",")]
    ]
    return " ".join(" ".join(found).split())


def legend_terms_may_wrap_when_stacked(css: str) -> bool:
    return "white-space: normal;" in declarations(narrow_block(css), ".states dt")


def test_the_legend_stacks_and_its_terms_may_wrap_on_a_narrow_screen(css: str) -> None:
    # The premise: wide, the terms hold one line beside their definitions...
    assert "white-space: nowrap;" in declarations(css.split(NARROW)[0], ".states dt")
    # ...and narrow, the list is one column, where a term that cannot wrap is
    # the widest thing on the page.
    assert "grid-template-columns: 1fr;" in declarations(
        narrow_block(css), ".identity, .states"
    ) or "grid-template-columns: 1fr;" in declarations(narrow_block(css), ".states")
    assert legend_terms_may_wrap_when_stacked(css)


def test_control_the_check_notices_a_legend_that_cannot_wrap(css: str) -> None:
    sabotaged = css.replace(".states dt { white-space: normal; }", "")
    assert sabotaged != css
    assert not legend_terms_may_wrap_when_stacked(sabotaged)


def test_control_the_rule_has_to_be_inside_the_narrow_query(css: str) -> None:
    moved = css.replace(".states dt { white-space: normal; }", "") + (
        "\n.states dt { white-space: normal; }\n"
    )
    assert moved != css
    assert not legend_terms_may_wrap_when_stacked(moved)
