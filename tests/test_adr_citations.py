"""ADR citations are the provenance trail for this project's strongest claims.

`docs/adr/0002-refuse-to-rank-schools.md` is the founding commitment, and
AGENTS.md requires a PR touching that guardrail to link an ADR. A citation is
only worth as much as the document it points at, so these check the trail
itself: that every ADR a source file or a document cites exists, that no ADR
carries a generator placeholder where its date should be, and that nothing
cites the process meta-ADR as if it were a decision about behaviour.

That last one is issue #35. Seven sites in code and docs cited "ADR 0000" for
the anti-ranking and suppression-fidelity rule. ADR 0000 is
`0000-record-architecture-decisions.md`, the MADR process ADR; it says nothing
about ranking or suppression. Anyone auditing the project's most important
claim by following its own citations landed on a boilerplate template.

Issue #107 is about the universe these checks read. It was a hand-typed tuple,
`("src", "tests", "docs", "evals", "tools")`, and the repository root was not in
it -- so the ten citations in `README.md`, the four in `PROVENANCE.md` and the
rest of the 52 outside those five directories were reported as a pass having
been examined by nothing. `SKIP_FILES` named `CHANGELOG.md`, which the walk
could never have reached, which is the tell that somebody expected otherwise.

The universe is now derived from `git ls-files` instead of typed, so a directory
added to the repository is in scope on the day it is added rather than on the
day somebody remembers this tuple. Everything the walk drops is declared below
and is held to two rules: the exclusion must name something the derivation would
otherwise have reached, and it must be load-bearing -- a skipped file whose
removal from the skip list would change no verdict is a skip nobody needs.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = ROOT / "docs" / "adr"

CITATION = re.compile(r"\bADR (\d{4})\b")

# A citation can only live in a file somebody writes by hand. Binary and data
# formats are out; these six are what this repository authors.
SCANNED_SUFFIXES = frozenset({".py", ".md", ".mjs", ".yml", ".yaml", ".json"})

# The rule below is about a citation used as the *authority for a behaviour*, so
# it applies to code and to the normative documents. Retrospective writing has to
# be able to name the defect it narrates, or the record of a fix cannot describe
# what was fixed. Two kinds of file are therefore out of scope, by a stated
# principle rather than one exemption at a time:
#
#   - append-only history (`CHANGELOG.md`), whose entries are *about* the old
#     numbering -- one narrates the negative control that proved this gate can
#     fail, by quoting the two faults it planted -- and rewriting them would
#     falsify the record;
#   - `docs/plans/`, which is where audits and improvement plans describe what
#     was wrong before it was fixed.
#
# This file is the third, and is named individually: it quotes "ADR 0000" in its
# own prose to say what it prevents.
#
# Paths are repository-relative, not bare names: a skip that matches on the file
# name alone silences every file of that name anywhere in the tree.
SKIP_FILES = frozenset({"CHANGELOG.md", "tests/test_adr_citations.py"})
SKIP_DIRS = (Path("docs") / "plans",)

# The process ADR. It records that this project keeps ADRs; it decides nothing
# about schools, ranking, suppression, or the ask layer, so citing it as the
# authority for a behaviour points a reader at the wrong document.
PROCESS_ADR = "0000"


def tracked_files() -> tuple[Path, ...]:
    """Every file git is tracking, repository-relative.

    Tracking is the derivation: `__pycache__` and `node_modules` needed naming
    when the walk was `rglob`, and do not now, because git has never heard of
    them.
    """
    listed = subprocess.run(  # noqa: S603
        ["git", "-C", str(ROOT), "ls-files", "-z"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    names = [name for name in listed.stdout.split("\0") if name]
    assert names, "git ls-files reported no tracked files; the walk read nothing"
    return tuple(Path(name) for name in sorted(names))


def published_output_dir() -> Path:
    """The directory `make publish` writes, read from the Makefile that writes it.

    Its bytes are generated from `src/`, so a citation there is a citation in
    `src/` counted twice. Reading the name out of the Makefile rather than
    typing it means renaming the publish target moves this exclusion with it,
    and a Makefile that stops declaring one fails here instead of silently
    scanning 23,000 rendered pages.
    """
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    declared = re.search(r"^PUBLISH_DIR \?= (\S+)$", makefile, re.M)
    assert declared, "the Makefile no longer declares PUBLISH_DIR"
    return Path(declared.group(1))


def candidate_files() -> tuple[Path, ...]:
    """Tracked files in a format that can carry a citation, before exclusions."""
    return tuple(p for p in tracked_files() if p.suffix in SCANNED_SUFFIXES)


def excluded_files() -> dict[Path, str]:
    """Every candidate the walk drops, mapped to the reason it is dropped."""
    published = published_output_dir()
    dropped: dict[Path, str] = {}
    for relative in candidate_files():
        if relative.is_relative_to(published):
            dropped[relative] = f"generated: under {published.as_posix()}/"
        elif relative.as_posix() in SKIP_FILES:
            dropped[relative] = "skipped: retrospective writing (SKIP_FILES)"
        elif any(relative.is_relative_to(d) for d in SKIP_DIRS):
            dropped[relative] = "skipped: plans and audits (SKIP_DIRS)"
    return dropped


def cited_files() -> list[Path]:
    dropped = excluded_files()
    return [ROOT / p for p in candidate_files() if p not in dropped]


def files_carrying_a_citation() -> list[Path]:
    return [p for p in cited_files() if CITATION.search(p.read_text(encoding="utf-8"))]


def census() -> str:
    """The two numbers, in one line, so a narrowing is legible where it happens."""
    return (
        f"ADR citation gate: walked {len(cited_files())} of "
        f"{len(candidate_files())} tracked files that could carry a citation "
        f"({len(excluded_files())} declared exclusions); "
        f"{len(files_carrying_a_citation())} of them carry one."
    )


def adr_numbers() -> set[str]:
    return {p.name[:4] for p in ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")}


def test_there_is_an_adr_series_to_cite() -> None:
    """A zero-file corpus would make every check below vacuously true."""
    numbers = adr_numbers()
    assert len(numbers) >= 5, numbers
    assert "0002" in numbers, "the refuse-to-rank ADR is the one that must exist"
    assert cited_files(), f"nothing was scanned. {census()}"
    assert files_carrying_a_citation(), (
        f"the walk found no ADR citation anywhere. A pattern that has stopped "
        f"matching and a repository that has stopped citing look the same from "
        f"here, and only one of them is plausible. {census()}"
    )


def test_the_walk_universe_is_derived_and_every_hole_is_declared() -> None:
    """Issue #107. The universe is derived, and every hole in it is named.

    A gate whose scope is typed can be narrowed by editing a tuple, and the
    output of a narrowed run is identical to the output of a clean one. So the
    scope is a subtraction from `git ls-files` and the subtrahend is spelled
    out: anything missing from the walk has to appear in `excluded_files()`
    with a reason, or this fails and names it.
    """
    print(census())
    walked = {p.relative_to(ROOT) for p in cited_files()}
    dropped = excluded_files()
    unexplained = set(candidate_files()) - walked - set(dropped)
    assert not unexplained, sorted(p.as_posix() for p in unexplained)
    assert not (walked & set(dropped)), "a file is both walked and excluded"

    # The regression #107 records, named individually because it is the one an
    # auditor meets first: ten of the fifty-two out-of-scope citations were in
    # the README.
    assert Path("README.md") in walked, (
        f"the repository README is out of the walk again. {census()}"
    )
    assert Path("PROVENANCE.md") in walked, census()


def test_every_declared_exclusion_names_a_file_and_earns_its_place() -> None:
    """An exemption list needs the same self-test as the thing it exempts.

    Two refusals. An entry that names nothing in the tree is dead code -- which
    is precisely what `SKIP_FILES` was before #107, since `CHANGELOG.md` sat at
    a root the walk never visited. And an entry that would change no verdict is
    an exemption nobody needs: each skipped file is re-read here, and has to
    contain a citation that one of the checks below would refuse.
    """
    candidates = {p.as_posix() for p in candidate_files()}
    for name in sorted(SKIP_FILES):
        assert name in candidates, (
            f"SKIP_FILES names {name}, which is not a tracked file the walk "
            f"would otherwise reach. It exempts nothing."
        )

    numbers = adr_numbers()
    for name in sorted(SKIP_FILES):
        body = (ROOT / name).read_text(encoding="utf-8")
        refusable = [
            number
            for number in CITATION.findall(body)
            if number not in numbers or number == PROCESS_ADR
        ]
        assert refusable, (
            f"SKIP_FILES exempts {name}, but nothing in it would be refused if "
            f"it were scanned. Delete the entry rather than carrying a skip "
            f"that hides nothing."
        )

    skipped_by_dir = [p for p, why in excluded_files().items() if "SKIP_DIRS" in why]
    assert skipped_by_dir, (
        f"SKIP_DIRS {[d.as_posix() for d in SKIP_DIRS]} excludes no tracked "
        f"file. {census()}"
    )


def test_the_generated_publish_directory_is_the_one_the_makefile_writes() -> None:
    """The one exclusion that is about bytes rather than about prose.

    It is declared ahead of need: the publish directory holds 23,305 rendered
    pages and no file in a format this gate reads, so today it excludes nothing.
    That is the honest state to print rather than to fail on -- the entry
    anticipates the dataset release, which puts JSON under the same directory.
    """
    published = published_output_dir()
    assert (ROOT / published).is_dir(), f"{published} is not a directory"
    assert any(p.is_relative_to(published) for p in tracked_files()), (
        f"{published} holds no tracked file; the Makefile and the tree disagree"
    )
    generated = [
        p for p, why in excluded_files().items() if why.startswith("generated")
    ]
    print(
        f"published output {published.as_posix()}/: "
        f"{len(generated)} tracked files excluded from the ADR citation walk "
        f"(declared ahead of need; 0 is the expected count today)"
    )


def test_every_cited_adr_exists() -> None:
    numbers = adr_numbers()
    missing: list[str] = []
    for path in cited_files():
        for number in CITATION.findall(path.read_text(encoding="utf-8")):
            if number not in numbers:
                missing.append(f"{path.relative_to(ROOT)} cites ADR {number}")
    assert not missing, f"{missing} -- {census()}"


def test_no_adr_carries_an_unfilled_generator_placeholder() -> None:
    """`Date: TODO -- set to today's date at generation time` shipped in ADR 0000."""
    bad: list[str] = []
    for path in sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("Date:"):
                if not re.fullmatch(r"Date: \d{4}-\d{2}-\d{2}", line.strip()):
                    bad.append(f"{path.name}: {line.strip()}")
                break
        else:
            bad.append(f"{path.name}: no Date line")
    assert not bad, bad


def test_the_process_adr_is_never_cited_as_the_reason_for_a_behaviour() -> None:
    """Issue #35. The anti-ranking rule is ADR 0002, not ADR 0000."""
    offenders: list[str] = []
    for path in cited_files():
        if path.is_relative_to(ADR_DIR):
            continue
        for number, line in _citations_with_lines(path):
            if number == PROCESS_ADR:
                offenders.append(f"{path.relative_to(ROOT)}: {line.strip()}")
    assert not offenders, (
        "ADR 0000 records the ADR process and decides nothing about behaviour; "
        "the anti-ranking and suppression rule is ADR 0002: "
        + "; ".join(offenders)
        + f" -- {census()}"
    )


def _citations_with_lines(path: Path) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        for number in CITATION.findall(line):
            found.append((number, line))
    return found


@pytest.mark.parametrize("number", ["0002", "0003", "0004"])
def test_the_decision_adrs_are_accepted(number: str) -> None:
    """A citation of a Proposed or Superseded ADR is a citation of a non-decision."""
    (path,) = ADR_DIR.glob(f"{number}-*.md")
    body = path.read_text(encoding="utf-8")
    assert re.search(r"^Status: Accepted", body, re.M), path.name
