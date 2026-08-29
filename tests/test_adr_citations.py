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
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = ROOT / "docs" / "adr"

CITATION = re.compile(r"\bADR (\d{4})\b")

SEARCH_ROOTS = ("src", "tests", "docs", "evals", "tools")

# The rule below is about a citation used as the *authority for a behaviour*, so
# it applies to code and to the normative documents. Retrospective writing has to
# be able to name the defect it narrates, or the record of a fix cannot describe
# what was fixed. Two kinds of file are therefore out of scope, by a stated
# principle rather than one exemption at a time:
#
#   - append-only history (`CHANGELOG.md`), two of whose entries are *about* the
#     old numbering, and rewriting them would falsify the record;
#   - `docs/plans/`, which is where audits and improvement plans describe what
#     was wrong before it was fixed.
#
# This file is the third, and is named individually: it quotes "ADR 0000" in its
# own prose to say what it prevents.
SKIP_FILES = {"CHANGELOG.md", "test_adr_citations.py"}
SKIP_DIRS = (Path("docs") / "plans",)

# The process ADR. It records that this project keeps ADRs; it decides nothing
# about schools, ranking, suppression, or the ask layer, so citing it as the
# authority for a behaviour points a reader at the wrong document.
PROCESS_ADR = "0000"


def cited_files() -> list[Path]:
    paths: list[Path] = []
    for root in SEARCH_ROOTS:
        for path in sorted((ROOT / root).rglob("*")):
            if not path.is_file() or path.name in SKIP_FILES:
                continue
            relative = path.relative_to(ROOT)
            if any(relative.is_relative_to(d) for d in SKIP_DIRS):
                continue
            if path.suffix not in {".py", ".md", ".mjs", ".yml", ".yaml", ".json"}:
                continue
            if "__pycache__" in path.parts or "node_modules" in path.parts:
                continue
            paths.append(path)
    return paths


def adr_numbers() -> set[str]:
    return {p.name[:4] for p in ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md")}


def test_there_is_an_adr_series_to_cite() -> None:
    """A zero-file corpus would make every check below vacuously true."""
    numbers = adr_numbers()
    assert len(numbers) >= 5, numbers
    assert "0002" in numbers, "the refuse-to-rank ADR is the one that must exist"
    assert cited_files(), "nothing was scanned"


def test_every_cited_adr_exists() -> None:
    numbers = adr_numbers()
    missing: list[str] = []
    for path in cited_files():
        for number in CITATION.findall(path.read_text(encoding="utf-8")):
            if number not in numbers:
                missing.append(f"{path.relative_to(ROOT)} cites ADR {number}")
    assert not missing, missing


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
        "the anti-ranking and suppression rule is ADR 0002: " + "; ".join(offenders)
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
