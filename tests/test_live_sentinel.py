"""How much of the live site the sentinel compares, and which parts.

`tools/verify_live_site.py` fetched every published file until 2026-09-05. That
was eight files. Publishing all 10,534 schools made it 21,076, so the daily run
would have pulled 836MB from the origin every morning and taken hours doing it.

The comparison is bounded now, and bounding a sentinel is exactly the kind of
change that can quietly turn it into nothing -- the failure mode its own module
docstring calls out. So what stays exhaustive, what rotates, and the fact that
rotation reaches every page are checked here rather than assumed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "verify_live_site", ROOT / "tools" / "verify_live_site.py"
)
assert SPEC and SPEC.loader
sentinel = importlib.util.module_from_spec(SPEC)
# Registered before it is executed: the module defines a dataclass, and
# `@dataclass` resolves its own module out of `sys.modules` while running.
sys.modules[SPEC.name] = sentinel
SPEC.loader.exec_module(sentinel)

SPINE = [
    "CNAME",
    "index.html",
    "robots.txt",
    "sitemap.xml",
    "social-card.en.png",
    "social-card.es.png",
    "ask/00000000000001.en.html",
    "ask/00000000000001.es.html",
]


def corpus(schools: int) -> list[str]:
    """A published tree of `schools` school pages plus the usual spine."""
    pages = [
        f"{10000000000000 + n}.{loc}.html"
        for n in range(schools)
        for loc in ("en", "es")
    ]
    return sorted(SPINE + pages)


def schools_in(selected: list[str]) -> list[str]:
    return [r for r in selected if sentinel.is_school_page(r)]


def test_what_counts_as_a_school_page() -> None:
    """The split decides what rotates, so a miscount here silences the sentinel."""
    assert sentinel.is_school_page("57726786056246.en.html")
    assert not sentinel.is_school_page("index.html")
    assert not sentinel.is_school_page("ask/57726786056246.en.html")
    assert not sentinel.is_school_page("robots.txt")
    assert not sentinel.is_school_page("social-card.en.png")


def test_the_spine_is_compared_on_every_run() -> None:
    """A stale deploy shows up in the index and the sitemap first."""
    relatives = corpus(500)
    for offset in range(6):
        selected = sentinel.comparison_set(relatives, 20, offset)
        for path in SPINE:
            assert path in selected, (path, offset)


def test_a_run_is_bounded_by_the_sample() -> None:
    relatives = corpus(500)
    selected = sentinel.comparison_set(relatives, 20, 3)
    assert len(schools_in(selected)) == 20
    assert len(selected) == 20 + len(SPINE)


def test_consecutive_runs_do_not_repeat_the_same_school_pages() -> None:
    """Rotation is the whole reason a bounded run is still a real check."""
    relatives = corpus(500)
    first = set(schools_in(sentinel.comparison_set(relatives, 20, 7)))
    second = set(schools_in(sentinel.comparison_set(relatives, 20, 8)))
    assert first and second
    assert not (first & second)


def test_rotation_reaches_every_school_page() -> None:
    """Bounded per run, exhaustive over time; otherwise pages are never checked."""
    relatives = corpus(50)
    total = len(schools_in(relatives))
    seen: set[str] = set()
    for offset in range(total):  # more than enough windows to wrap
        seen |= set(schools_in(sentinel.comparison_set(relatives, 7, offset)))
    assert seen == set(schools_in(relatives))


def test_a_same_day_rerun_compares_the_same_window() -> None:
    """The retry loop looks again for a deploy to settle, not somewhere else."""
    relatives = corpus(500)
    assert sentinel.comparison_set(relatives, 20, 11) == sentinel.comparison_set(
        relatives, 20, 11
    )


def test_sample_zero_compares_the_whole_tree() -> None:
    """The by-hand sweep after a publish, and the old behaviour, still reachable."""
    relatives = corpus(50)
    assert sentinel.comparison_set(relatives, 0, 1) == sorted(relatives)


def test_a_sample_wider_than_the_corpus_compares_all_of_it() -> None:
    """Asking for more than exists is a full sweep, not a wrapped and doubled one."""
    relatives = corpus(10)
    selected = sentinel.comparison_set(relatives, 10_000, 4)
    assert selected == sorted(relatives)
    assert len(selected) == len(set(selected))
