"""The release this project's metadata claimed, and the one it has.

`CITATION.cff` carried `version: 0.1.0` and `date-released: "2026-08-18"`, and
`CHANGELOG.md` opened a section `## [0.1.0] - 2026-08-18 / First tagged release`.
There is no tag in this repository and no release has been published, so both
described something that never happened -- a citation someone follows, and a
changelog someone reads, agreeing with each other about a release that does not
exist. The sibling project olive-bark-logger hit the same thing and fixed it the
same way: omit `date-released` until a tag exists, and say in the file why it is
absent.

`git tag` cannot settle this from a test. CI checks out at depth 1 and fetches
no tags, so a git-based check would report "no tags" on every run and be a false
green the day a release is cut. What is checkable everywhere is that the three
places a version is claimed agree, and that none of them dates a release while
the others say there is not one.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CITATION = ROOT / "CITATION.cff"
CHANGELOG = ROOT / "CHANGELOG.md"
PYPROJECT = ROOT / "pyproject.toml"

# `## [0.1.0] - 2026-08-18`, and `## [Unreleased]`, which carries no version.
RELEASE_HEADING = re.compile(r"^## \[(\d+\.\d+\.\d+)\](.*)$", re.M)
A_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# A correction here quotes the sentence it corrects, the same convention
# `tests/test_published_site.py` reads around. Quoted text is history.
QUOTED = re.compile(r'"[^"\n]*"')


def cff_keys() -> dict[str, str]:
    """The top-level keys of CITATION.cff, with comments dropped.

    A comment quoting the line that was removed is how this repository records a
    correction, and it must not read back as the key it is quoting.
    """
    keys: dict[str, str] = {}
    for line in CITATION.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip() or line.startswith(" "):
            continue
        key, _, value = line.partition(":")
        keys[key.strip()] = value.split("#")[0].strip().strip('"')
    return keys


def declared_version() -> str:
    return str(
        tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]
    )


def test_the_citation_states_the_version_pyproject_declares() -> None:
    """One version, in one place, mirrored where a citation needs it."""
    assert cff_keys()["version"] == declared_version()


def test_the_citation_claims_no_release_date_while_none_has_happened() -> None:
    """The absence is the point, so the absence is what is checked.

    Adding `date-released` back is correct once a tag exists; doing it while the
    changelog still says nothing has been released is the drift that produced
    the 2026-08-18 date this replaced.
    """
    assert "date-released" not in cff_keys(), (
        "CITATION.cff dates a release. If a version has actually been tagged, "
        "give the CHANGELOG heading the same date; if not, remove this key."
    )


def test_no_changelog_heading_dates_a_release_the_citation_does_not() -> None:
    headings = RELEASE_HEADING.findall(CHANGELOG.read_text(encoding="utf-8"))
    assert headings, "CHANGELOG.md no longer carries a versioned section"
    dated = sorted(version for version, rest in headings if A_DATE.search(rest))
    if "date-released" in cff_keys():
        assert dated, "CITATION.cff dates a release and no CHANGELOG heading does"
    else:
        assert not dated, (
            "these CHANGELOG headings date a release while CITATION.cff says none "
            f"has been made: {dated}"
        )


def test_no_changelog_section_calls_itself_a_tagged_release() -> None:
    """`git tag` lists nothing here; a heading saying otherwise is a claim, not prose."""
    body = QUOTED.sub('""', CHANGELOG.read_text(encoding="utf-8"))
    if "date-released" in cff_keys():
        return
    for line in body.splitlines():
        assert "First tagged release" not in line, line


def test_the_versioned_changelog_sections_are_versions_this_project_has() -> None:
    headings = {
        version
        for version, _ in RELEASE_HEADING.findall(CHANGELOG.read_text(encoding="utf-8"))
    }
    assert headings == {declared_version()}, (sorted(headings), declared_version())
