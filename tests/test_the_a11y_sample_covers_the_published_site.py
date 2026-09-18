"""The accessibility gate reads 17 pages. The site serves 23,305. This is the bridge.

`make a11y` runs axe over `build/site-offline`, which `make site-offline` renders from
the committed fixtures: **17 pages, 3 schools, 1 county, 1 district**. What is served at
homeroom.chelseakr.com is `site/`, **23,305 pages** rendered from acquired CDE files CI
never has. Nothing said what made the 17 representative of the 23,305, and the two
numbers that would say it were nowhere.

They are here now, and the honest form of the claim is **not** "the sample looks like the
site". It is narrower and checkable, in two layers.

**Layer one, vocabulary.** Every accessibility-relevant markup feature the published site
uses appears somewhere in the pages the gate reads. An axe rule keys off element names,
`role`, `aria-*`, `lang`, `alt`, `type`, `scope` and the class tokens the stylesheet hangs
contrast and focus on. If the published site never uses a feature the sample lacks, then
no axe rule has an input in production that it lacks in the gate. Measured 2026-09-08 and
re-measured 2026-09-13 against `origin/main`: **containment holds, with zero exceptions.**

**Layer two, co-occurrence.** Layer one was explicit that it did not carry this, and said
so: the published site presents 8 distinct (element set, class set) shapes and the fixture
build presents 4, so a rule that fires only on a *combination* was still outside the
claim. Several axe rules are exactly that — `heading-order`, `landmark-unique`, `region`,
`landmark-one-main` — and a vocabulary check cannot see any of them.

That gap is closed here, and closing it started by re-measuring the numbers that named it.
**8 published shapes and 4 sample shapes is right; "so 4 shapes are unrepresented" is
not.** The 4 sample shapes are not a subset of the 8: exactly **1** published shape (the
ask page) is reproduced exactly, so **7** are not. What the arithmetic hid is the
direction, and the direction is the finding:

    every one of the 8 published shapes is a SUBSET of a shape the gate reads.

No published page carries an element, class token, role, aria attribute, input type,
heading transition, landmark sequence or parent/child nesting that the 17 pages lack. The
differences all run the other way — the sample renders pages *richer* than production's,
by `class:note`/`class:note-title` (the fixture banner), `class:ask` (the fixture build
gives every school an ask link; the publish target gives it to one school in 10,534) and
the measure-state tokens `class:m-zero`/`class:m-withheld` that a school's own data may
not produce. Containment of a subset is containment of every co-occurrence inside it, so
the co-occurrence claim is now measured rather than disclaimed. Re-measured
2026-09-13, every figure derived by the checks below rather than typed here:

    pages the gate examines / pages published            17 of 23,305
    published shapes contained in a shape it reads        8 of 8   (1 of them exactly)
    markup features published, present in the sample     84 of 84
    heading-level transitions published, in the sample    6 of 6
    landmark sequences published, in the sample           4 of 4
    element nestings published, in the sample            56 of 56

Nothing below asserts those numbers — a hand-kept count gated on equality is its own
failure mode — so they are a record of one run and the checks are the live claim.

**Why the sample is not extended until the 8 shapes match exactly.** It cannot be, and
should not be. Every page the gate reads carries the fixture banner and no published page
does — `tests/test_published_site.py::test_no_published_page_was_built_from_fixtures`
gates that, and it is the whole reason a fixture build is safe to publish gates over. So a
fixture page can never present a published page's shape exactly, and the only way to make
it is to stop marking the fixture build as a fixture build. That trades a measured,
one-directional gap for a build that lies about what it is. The remaining differences are
the same kind: `class:ask` is absent from 19,672 published pages because `make publish`
renders the ask layer in a second pass over one school, and reproducing that offline means
a second fixture render whose only effect is to hand axe a page it has already been handed
a superset of. It closes nothing any predicate here can measure, and doubles the gate.

**What this still does not claim.** Attribute *values* — an `aria-label`'s text, an
`alt`'s text, an `href` — are normalized away, because they are a school's name and are
the same rule input whichever school it is. Run lengths are collapsed: a school page with
eighteen measure sections and one with twenty-two are one landmark sequence here. And
nothing in a headless DOM can see layout, so contrast and target size are decided
elsewhere (`tools/a11y.mjs` names them; `tests/test_pages.py` measures contrast off the
palette). A gate that examines 17 of 23,305 pages has a ratio, and the ratio is the point:
these checks say what the 17 stand in for, and refuse to let that quietly stop being true.

The reason to gate this rather than write it down: the sample is a fixture file and
production is data acquired by hand from the state. A new school, a new district, or a
CDE column that starts arriving populated can put a markup feature into production that
the fixtures never render — silently, on a machine that is not this one — and the a11y
gate would go on printing "17 page(s) ... clean" over a page shape it has never seen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

import pytest

from homeroom import analytics
from homeroom.i18n import text
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
_HEADINGS = re.compile(r"<h([1-6])\b")
_TAGS = re.compile(r"<(/?)([a-zA-Z][\w-]*)")

#: The elements axe's landmark rules reason about, plus the two sectioning elements this
#: renderer uses to carry an accessible name.
_LANDMARKS = re.compile(r"<(main|nav|header|footer|aside|form|section)\b([^>]*)>")
_LABEL = re.compile(r'aria-label(?:ledby)?\s*=\s*"([^"]*)"')

#: HTML elements that never take a closing tag, so the nesting walk must not stack them.
_VOID = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)


def _vocabulary(markup: str) -> set[str]:
    """Every accessibility-relevant token in one document.

    Regex rather than `html.parser`: this reads 23,305 files and the parser costs six
    times as much for an answer that does not change. The tokens are deliberately
    normalized — an `aria-label`'s *value* is a school name and is the same rule input
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


def _heading_transitions(markup: str) -> frozenset[tuple[str | int, int | None]]:
    """What `heading-order` actually reads: the level a page starts on and each step.

    A sequence, not a set: `h1 h2 h3 h2` and `h1 h3 h2` use the same three elements and
    only one of them skips a level. Reduced to consecutive pairs plus the opening level,
    which is the granularity the rule decides on, so two pages differing only in how many
    times they repeat a legal step are one input here.
    """
    levels = [int(found) for found in _HEADINGS.findall(markup)]
    start: tuple[str | int, int | None] = ("start", levels[0] if levels else None)
    return frozenset(pairwise(levels)) | {start}


def _landmark_sequence(markup: str) -> tuple[str, ...]:
    """The landmarks in document order, with label values normalized and runs collapsed.

    `landmark-unique`, `landmark-one-main` and `region` reason about which landmarks a
    page has, whether each carries an accessible name, and where they sit relative to one
    another — not about the name's text, and not about how many measure sections a
    particular school happens to publish. So a labeled `<section>` repeated eighteen
    times and one repeated twenty-two times are the same sequence here, while a page that
    gains an unlabeled one, or loses its `<footer>`, is not.
    """
    ordered = [
        f"{name}[{'labeled' if _LABEL.search(attributes) else 'bare'}]"
        for name, attributes in _LANDMARKS.findall(markup)
    ]
    collapsed: list[str] = []
    for landmark in ordered:
        if not collapsed or collapsed[-1] != landmark:
            collapsed.append(landmark)
    return tuple(collapsed)


def _repeated_landmark_names(markup: str) -> frozenset[str]:
    """Landmarks sharing an element and an accessible name — `landmark-unique`'s input.

    The one property a set of features cannot carry is *how many*, and this rule needs
    exactly that. Kept separate from the shape rather than folded into it, so that a
    published page growing a duplicate is a named failure and not a shape that merely
    stopped matching.
    """
    seen: dict[tuple[str, str | None], int] = {}
    for name, attributes in _LANDMARKS.findall(markup):
        label = _LABEL.search(attributes)
        key = (name, label.group(1) if label else None)
        seen[key] = seen.get(key, 0) + 1
    return frozenset(f"{name}[{label}]" for (name, label), n in seen.items() if n > 1)


def _nesting(markup: str) -> tuple[frozenset[tuple[str, str]], bool]:
    """Every (parent, child) element pairing, and whether the document's tags balance.

    `region`, `landmark-banner-is-top-level`, `list`, `definition-list` and `td-headers-attr`
    are all about what sits inside what. Pairs rather than full paths: a path signature is
    unique per page and would measure nothing, while a pair is the relation each of those
    rules reads. The balance flag is the floor under it — an unbalanced document would
    make the walk produce pairs that are not in the tree, and a signature nobody can trust
    is worse than no signature.
    """
    stack: list[str] = []
    pairs: set[tuple[str, str]] = set()
    balanced = True
    for closing, raw in _TAGS.findall(markup):
        name = raw.lower()
        if closing:
            if name in stack:
                while stack and stack.pop() != name:
                    balanced = False
            else:
                balanced = False
            continue
        if stack:
            pairs.add((stack[-1], name))
        if name not in _VOID:
            stack.append(name)
    return frozenset(pairs), balanced and not stack


@dataclass
class Signature:
    """What a set of pages offers an axe rule, accumulated one page at a time.

    Deliberately not a list of per-page objects. `site/` is 856 MB across 23,305 files
    and the published side has only nine distinct signatures of any kind in it, so the
    summary is three orders of magnitude smaller than the corpus it describes and fits
    on a two-core runner. Each mapping keeps one example path per distinct value, which
    is what a failure message needs: the thing that is uncovered, and a page that has it.
    """

    pages: int = 0
    feature_union: set[str] = field(default_factory=set)
    shapes: dict[frozenset[str], str] = field(default_factory=dict)
    heading_steps: dict[tuple[str | int, int | None], str] = field(default_factory=dict)
    landmark_runs: dict[tuple[str, ...], str] = field(default_factory=dict)
    nestings: dict[tuple[str, str], str] = field(default_factory=dict)
    repeated_landmarks: dict[str, str] = field(default_factory=dict)
    unbalanced: list[str] = field(default_factory=list)

    def read(self, path: Path, root: Path) -> None:
        markup = path.read_text(encoding="utf-8", errors="replace")
        where = str(path.relative_to(root))
        self.pages += 1

        features = frozenset(_vocabulary(markup))
        self.feature_union |= features
        self.shapes.setdefault(features, where)

        for step in _heading_transitions(markup):
            self.heading_steps.setdefault(step, where)

        self.landmark_runs.setdefault(_landmark_sequence(markup), where)

        for repeated in _repeated_landmark_names(markup):
            self.repeated_landmarks.setdefault(repeated, where)

        pairs, balanced = _nesting(markup)
        for pair in pairs:
            self.nestings.setdefault(pair, where)
        if not balanced:
            self.unbalanced.append(where)


def _signature(pages: list[Path], root: Path) -> Signature:
    signature = Signature()
    for page in pages:
        signature.read(page, root)
    return signature


@pytest.fixture(scope="module")
def fixture_build(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The tree `make site-offline` writes, rendered here with the Makefile's arguments.

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
    # Since 2026-09-17 the published pages carry what `homeroom.analytics` adds
    # after rendering (the Google Analytics loader's script tag, the note, the
    # landing page's disclosure), and `make analytics-gate` runs html-validate and
    # the same axe pass as `make a11y` over the fixture build with exactly that
    # added. So the sample is the fixture build with it added too: the comparison
    # below is between what is served and what those gates read.
    analytics.add_to_tree(out)
    return out


@pytest.fixture(scope="module")
def sample(fixture_build: Path) -> list[Path]:
    """The pages `make a11y` reads."""
    pages = sorted(fixture_build.rglob("*.html"))
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


@pytest.fixture(scope="module")
def gate(fixture_build: Path, sample: list[Path]) -> Signature:
    """What the 17 pages `make a11y` reads offer a rule."""
    return _signature(sample, fixture_build)


@pytest.fixture(scope="module")
def site(published: list[Path]) -> Signature:
    """What the 23,305 pages homeroom.chelseakr.com serves offer a rule."""
    return _signature(published, SITE)


def _ratio(covered: int, total: int, what: str) -> str:
    """Both numbers, never one. A coverage figure with a denominator missing is the
    defect every check in this module exists to answer."""
    return f"{covered} of {total} {what}"


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
    gate: Signature, site: Signature
) -> None:
    """Layer one: the vocabulary, and the sample's original justification.

    An axe rule cannot fire in production on an input that never occurs in production.
    So if every element, role, aria attribute, input type and class token in `site/`
    also occurs in the 17 pages the gate reads, every rule with an input in production
    has that input in the gate. That is a weaker claim than "the gate covers the site",
    and it is the one that is true and checkable.
    """
    assert gate.feature_union, "the sample yielded no markup features at all"

    missing: dict[str, str] = {}
    for shape, example in site.shapes.items():
        for feature in shape - gate.feature_union:
            missing.setdefault(feature, example)

    assert not missing, (
        f"{len(missing)} markup feature(s) are published but never rendered into the "
        f"{gate.pages} pages `make a11y` reads, so no axe rule keyed on them has ever "
        f"run against this site. Sample: {gate.pages} pages, "
        f"{len(gate.feature_union)} features. Published: {site.pages} pages. "
        f"Uncovered, with a page using each: {dict(sorted(missing.items())[:10])}. "
        "Widen `fixtures/` until the feature is rendered; do not narrow this check."
    )


def test_every_shape_the_site_publishes_is_contained_in_a_shape_the_gate_reads(
    gate: Signature, site: Signature
) -> None:
    """Layer two: the co-occurrence claim the vocabulary check used to disclaim.

    A rule that fires on a *combination* — two features on the same page — is invisible
    to a check that unions the site's vocabulary and unions the sample's. This is the
    combination form of the same argument, and it is the one that carries it: if a
    published page's whole feature set is contained in one sample page's feature set,
    then every co-occurrence that page exhibits is exhibited on a page axe has read.

    Containment, not equality. A fixture page carries the fixture banner and a published
    page never may, so the sets cannot be equal — see the module docstring. The number
    to watch is how many published shapes are contained, and it must be all of them.
    """
    uncontained = {
        example: sorted(
            shape
            - max(
                gate.shapes, key=lambda known: len(shape & known), default=frozenset()
            )
        )[:12]
        for shape, example in site.shapes.items()
        if not any(shape <= known for known in gate.shapes)
    }
    assert not uncontained, (
        f"{_ratio(len(site.shapes) - len(uncontained), len(site.shapes), 'published page shapes')} "
        f"are contained in one of the {len(gate.shapes)} shapes `make a11y` reads. A "
        "shape that is not contained carries a combination of markup features that no "
        "page axe has read carries together, so a rule keyed on that combination has "
        f"never run against this site. Uncontained, with what each adds: {uncontained}. "
        "Widen `fixtures/` until the combination is rendered; do not narrow this check."
    )


def test_every_heading_level_transition_the_site_publishes_occurs_in_the_sample(
    gate: Signature, site: Signature
) -> None:
    """`heading-order` is a co-occurrence rule about order, which a set cannot hold.

    It fires on a *step* — an `h1` followed by an `h3` — so the input is the pair, and a
    page that only ever steps by one can never produce it. Every step the published site
    takes, and every level it opens on, has to be a step the gate has read.
    """
    missing = {
        step: example
        for step, example in site.heading_steps.items()
        if step not in gate.heading_steps
    }
    assert not missing, (
        f"{_ratio(len(site.heading_steps) - len(missing), len(site.heading_steps), 'heading-level transitions')} "
        f"the site publishes also occur in the {gate.pages} pages the gate reads. "
        f"Missing, with a page taking each: {missing}"
    )


def test_every_landmark_sequence_the_site_publishes_occurs_in_the_sample(
    gate: Signature, site: Signature
) -> None:
    """`landmark-one-main`, `landmark-banner-is-top-level` and `region` read this.

    Not the shape of one landmark but the run of them: which landmarks a page carries,
    in what order, each labeled or bare. Runs are collapsed, so the number of measure
    sections a school publishes is not a difference; gaining an unlabeled landmark, or
    losing the footer, is.
    """
    missing = {
        run: example
        for run, example in site.landmark_runs.items()
        if run not in gate.landmark_runs
    }
    assert not missing, (
        f"{_ratio(len(site.landmark_runs) - len(missing), len(site.landmark_runs), 'landmark sequences')} "
        f"the site publishes also occur in the {gate.pages} pages the gate reads. "
        f"Missing, with a page carrying each: {missing}"
    )


def test_every_element_nesting_the_site_publishes_occurs_in_the_sample(
    gate: Signature, site: Signature
) -> None:
    """The third co-occurrence granularity: what sits inside what.

    `region` asks whether content sits inside a landmark, `list` whether a `<li>`'s
    parent is a list, `landmark-banner-is-top-level` whether a `<header>` is nested in
    one. Each reads a parent/child pairing, and a pairing production makes that the
    fixtures never make is a pairing axe has never decided here.
    """
    missing = {
        pair: example
        for pair, example in site.nestings.items()
        if pair not in gate.nestings
    }
    assert not missing, (
        f"{_ratio(len(site.nestings) - len(missing), len(site.nestings), 'element nestings')} "
        f"the site publishes also occur in the {gate.pages} pages the gate reads. "
        f"Missing, with a page nesting each: {missing}"
    )


def test_every_page_on_both_sides_closes_the_tags_it_opens(
    gate: Signature, site: Signature
) -> None:
    """The floor under the nesting signature, and a real check in its own right.

    An unbalanced document would make the tag walk above emit parent/child pairs that
    are nowhere in the tree, so the comparison would be between two fictions. It is also
    a defect on its own terms: `make htmlvalidate` holds the fixture build to HTML
    conformance and nothing held the 23,305 published pages to closing what they open.
    """
    assert not site.unbalanced[:10], (
        f"{len(site.unbalanced)} of {site.pages} published pages do not close the tags "
        f"they open, e.g. {site.unbalanced[:10]}. The nesting comparison above reads a "
        "tag stack, and an unbalanced document makes it report pairings the document "
        "does not contain."
    )
    assert not gate.unbalanced, gate.unbalanced


def test_no_published_page_repeats_a_landmark_the_sample_never_repeats(
    gate: Signature, site: Signature
) -> None:
    """`landmark-unique` needs two landmarks with one name, and a set cannot count.

    Every other check here reduces a page to sets, and a set holds "there is a labeled
    section" identically whether there is one or five. This is the property that falls
    through: two landmarks sharing an element and an accessible name are a violation, and
    a page with one of each is not. Measured 2026-09-13: no page on either side repeats
    one, so the rule has no firing input in production — which is a reason it cannot fire
    here, not a reason it was checked.
    """
    offending = {
        repeated: example
        for repeated, example in site.repeated_landmarks.items()
        if repeated not in gate.repeated_landmarks
    }
    assert not offending, (
        f"{len(offending)} landmark name(s) are repeated on a published page and on no "
        "page the gate reads, so `landmark-unique` has an input in production it has "
        f"never had here: {offending}"
    )


def test_the_gate_reads_a_fixture_build_which_is_why_no_shape_can_match_exactly(
    sample: list[Path],
) -> None:
    """Why 8 shapes and 4 shapes will never be 8 and 8, and why that is the right trade.

    Every page the gate reads carries the fixture banner, in its own locale, because the
    build that renders them is told it is a fixture build. No published page may carry it
    — `tests/test_published_site.py::test_no_published_page_was_built_from_fixtures`
    fails if one ever does. So the sample's shapes are strictly richer than the site's by
    at least the banner's own markup, and "make the sample present all 8 published
    shapes" resolves to "stop marking the fixture build as a fixture build".

    This asserts the asymmetry rather than describing it, so that a future change which
    quietly drops the banner to close the shape gap fails here, next to the reason.
    """
    banners = [text(locale, "fixture_banner_title") for locale in ("en", "es")]
    unmarked = [
        page.name
        for page in sample
        if not any(
            banner in page.read_text(encoding="utf-8", errors="replace")
            for banner in banners
        )
    ]
    assert not unmarked, (
        "pages the a11y gate reads that do not say they came from a fixture build: "
        f"{unmarked}. The gate's sample is a fixture build, the published site is not, "
        "and that difference is what makes the comparisons above containments rather "
        "than equalities. Removing the banner would close the shape gap by making the "
        "fixture build claim to be the published site."
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
