"""The accessibility gate reads 17 pages. The site serves 23,305. This is the bridge.

`make a11y` runs axe over `build/site-offline`, which `make site-offline` renders from
the committed fixtures: **17 pages, 3 schools, 1 county, 1 district**. What is served at
homeroom.chelseakr.com is `site/`, **23,305 pages** rendered from acquired CDE files CI
never has. Nothing said what made the 17 representative of the 23,305, and the two
numbers that would say it were nowhere.

They are here now, and the honest form of the claim is **not** "the sample looks like the
site". It is narrower and checkable: *every accessibility-relevant markup feature the
published site uses appears somewhere in the pages the gate reads.* An axe rule keys off
element names, `role`, `aria-*`, `lang`, `alt`, `type`, `scope` and the class tokens the
stylesheet hangs contrast and focus on. If the published site never uses a feature the
sample lacks, then no axe rule has an input in production that it lacks in the gate.

Measured 2026-09-08 against `origin/main`: **containment holds, with zero exceptions.**
Not one element name, class token, role, aria attribute or input type occurs in the
23,305 published pages and in none of the 17 the gate reads. That measured negative is
the entire justification for a 17-page gate over a 23,305-page site, and it had never
been taken.

**What this deliberately does not claim.** Containment is about the *vocabulary*, not
about *combinations*: the published site presents 8 distinct (element set, class set)
shapes and the fixture build presents 4, so a rule that only fires on a co-occurrence
absent from the fixtures would still be missed. That gap is real, it is smaller than the
one this closes, and the second test states it rather than leaving a reader to work it
out from a green run.

The reason to gate this rather than write it down: the sample is a fixture file and
production is data acquired by hand from the state. A new school, a new district, or a
CDE column that starts arriving populated can put a markup feature into production that
the fixtures never render — silently, on a machine that is not this one — and the a11y
gate would go on printing "17 page(s) ... clean" over a page shape it has never seen.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from homeroom.site import build_site

#: This module renders the fixture site once and reads all 23,305 published pages;
#: about a minute, and `--dist loadfile` keeps it on one worker.
pytestmark = pytest.mark.slow

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
FIXTURES = ROOT / "fixtures"

#: The attributes an axe rule keys off beyond the element name. `class` is in because the
#: palette and focus-visible rules resolve through the stylesheet; `alt`, `lang`, `type`
#: and `scope` are each the subject of at least one WCAG A rule.
_ATTRIBUTES = re.compile(r'\b(aria-[\w-]+|role|lang|alt|type|scope)\s*=\s*"([^"]*)"')
_ELEMENTS = re.compile(r"<([a-zA-Z][\w-]*)")
_CLASSES = re.compile(r'class="([^"]*)"')


def _vocabulary(markup: str) -> set[str]:
    """Every accessibility-relevant token in one document.

    Regex rather than `html.parser`: this reads 23,305 files and the parser costs six
    times as much for an answer that does not change. The tokens are deliberately
    normalised — an `aria-label`'s *value* is a school name and is the same rule input
    whichever school it is, while `alt=""` and a non-empty `alt` are different inputs.
    """
    found = {f"element:{name.lower()}" for name in _ELEMENTS.findall(markup)}
    for match in _CLASSES.finditer(markup):
        found.update(f"class:{token}" for token in match.group(1).split())
    for name, value in _ATTRIBUTES.findall(markup):
        if name.startswith("aria-"):
            found.add(f"attr:{name}")
        elif name == "alt":
            found.add("attr:alt:empty" if not value else "attr:alt:text")
        else:
            found.add(f"{name}:{value}")
    return found


@pytest.fixture(scope="module")
def sample(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    """The pages `make a11y` reads, rendered here with the Makefile's own arguments.

    Rendered rather than read off `build/site-offline`, so this cannot pass by reading a
    stale build somebody left on disk, and so it runs on a machine that has never run
    `make site-offline` — which is every CI machine, because `verify-ci` runs `test`
    before `pages`.
    """
    out = tmp_path_factory.mktemp("a11y-sample")
    build_site(
        directory=FIXTURES / "pubschls.sample.txt",
        enrollment=FIXTURES / "cdenroll.sample.txt",
        out_dir=out,
        is_fixture=True,
        absenteeism=FIXTURES / "chronicabsenteeism.sample.txt",
        assignments=FIXTURES / "tamo.sample.txt",
        ask_endpoint="https://ask.example.invalid",
        landing=True,
        site_url="https://homeroom.example",
    )
    pages = sorted(out.rglob("*.html"))
    assert pages, (
        "the fixture render produced no pages; this module would prove nothing"
    )
    return pages


@pytest.fixture(scope="module")
def published() -> list[Path]:
    assert SITE.is_dir(), (
        "site/ is missing, so this check has nothing to compare the a11y sample "
        "against. It is committed; restore it with `git checkout -- site`."
    )
    pages = sorted(SITE.rglob("*.html"))
    assert pages, "site/ exists but holds no page"
    return pages


def test_the_sample_is_the_page_set_the_makefile_names(sample: list[Path]) -> None:
    """A floor under the fixture side of the comparison.

    `make a11y` runs one invocation per directory and `tools/a11y.mjs` does not recurse,
    so a render that stopped producing one of them would shrink the sample without
    shrinking anything below it.
    """
    directories = {page.parent.name for page in sample}
    assert {"ask", "county", "district"} <= directories, directories
    assert len(sample) >= 17, len(sample)


def test_every_markup_feature_the_site_publishes_appears_in_the_pages_the_gate_reads(
    sample: list[Path], published: list[Path]
) -> None:
    """The two numbers, and the containment that is the sample's whole justification.

    An axe rule cannot fire in production on an input that never occurs in production.
    So if every element, role, aria attribute, input type and class token in `site/`
    also occurs in the 17 pages the gate reads, every rule with an input in production
    has that input in the gate. That is a weaker claim than "the gate covers the site",
    and it is the one that is true and checkable.
    """
    covered: set[str] = set()
    for page in sample:
        covered |= _vocabulary(page.read_text(encoding="utf-8", errors="replace"))
    assert covered, "the sample yielded no markup features at all"

    missing: dict[str, str] = {}
    for page in published:
        for feature in (
            _vocabulary(page.read_text(encoding="utf-8", errors="replace")) - covered
        ):
            missing.setdefault(feature, str(page.relative_to(SITE)))

    assert not missing, (
        f"{len(missing)} markup feature(s) are published but never rendered into the "
        f"{len(sample)} pages `make a11y` reads, so no axe rule keyed on them has ever "
        f"run against this site. Sample: {len(sample)} pages, {len(covered)} features. "
        f"Published: {len(published)} pages. Uncovered, with a page using each: "
        f"{dict(sorted(missing.items())[:10])}. Widen `fixtures/` until the feature is "
        "rendered; do not narrow this check."
    )


def test_the_shape_gap_the_containment_check_does_not_cover_is_stated(
    sample: list[Path], published: list[Path]
) -> None:
    """Containment is about vocabulary. This is the part of the claim it does not carry.

    Two pages can use the same elements and classes and still differ in which of them
    co-occur, and several axe rules (heading order, one main, duplicate landmark labels)
    are about co-occurrence. This does not fail on the gap — a fixture set is meant to be
    small — it fails if the gap stops being **measurable**, which is what would turn "the
    sample is representative" back into an assumption nobody has taken a number for.
    """
    published_shapes = {
        frozenset(_vocabulary(page.read_text(encoding="utf-8", errors="replace")))
        for page in published
    }
    sample_shapes = {
        frozenset(_vocabulary(page.read_text(encoding="utf-8", errors="replace")))
        for page in sample
    }
    assert sample_shapes and published_shapes
    unrendered = published_shapes - sample_shapes
    assert len(unrendered) < len(published_shapes), (
        f"not one of the {len(published_shapes)} shapes the site publishes is rendered "
        f"by the {len(sample_shapes)} the gate reads, so the sample and the site have "
        "stopped overlapping entirely"
    )


A11Y_PAGE_COUNT = re.compile(r"Pages the accessibility gate checks \| (\d+)\b")


def test_the_stated_gate_size_is_the_sample_and_not_the_site(
    sample: list[Path],
) -> None:
    """The prose half: the published figure must be the gate's, re-derived from a render.

    `docs/ROADMAP.md` states the gate's page count and `tests/test_pages.py` derives it
    from the fixture directory's arithmetic. This derives it from the render itself, so
    the two arrive at the number by different routes; and it is three orders of magnitude
    away from the site's own page count, which is what a reader must not take it for.
    """
    roadmap = (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    stated = A11Y_PAGE_COUNT.search(roadmap)
    assert stated, (
        "docs/ROADMAP.md no longer states the accessibility gate's page count"
    )
    assert int(stated.group(1)) == len(sample), (
        f"docs/ROADMAP.md says the accessibility gate checks {stated.group(1)} pages; "
        f"the fixture render this module drives produces {len(sample)}"
    )
