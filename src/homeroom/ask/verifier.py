"""The verifier: nothing the model wrote reaches a reader until this says so.

Every claim the narration returns is checked here against the school's own
evidence and the committed corpus, and a claim that fails any check is withheld
with a reason, never repaired. The reasons are an enumeration, not prose, so
the evaluation harness can count them and the page can show the count.

What is checked, per claim:

* it has a kind the schema allows, a non-empty text, and at least one citation;
* it carries no ranking, grading, scoring, better/worse, or recommendation
  language in either language (:func:`homeroom.ask.guards.judgment_hits`);
* every citation resolves to one of this school's cells or to a corpus passage;
* every number in the text is a number one of its cited cells publishes, or a
  year, or (for a verified quote) a number in the quote. A number from nowhere
  is withheld. Coverage tallies, the build size, and the grade span are context
  about the data rather than the school's measured value, so they are licensed
  only for the `note` kind, whose subject is that context (see
  :data:`CONTEXT_CLAIM_KINDS`). A digit that belongs to a cited measure's *name*
  ("Grade 4") is licensed where it is written against that name and nowhere
  else, by :func:`homeroom.ask.guards.strip_label_references`, so it cannot be
  restated as the school's figure;
* if any cited cell is withheld or unpublished, the text says so and does not
  turn the absence into a zero, a "none", or a "no students";
* a comparison cites exactly a school cell and its own district or state cell,
  both published, and the direction it states is the direction the numbers
  have;
* a definition cites a passage and quotes it verbatim.

The verifier is the product. The model is a draft.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from homeroom.ask.corpus import Corpus
from homeroom.ask.evidence import Cell, EvidenceRecord, SchoolEvidence
from homeroom.ask.guards import (
    judgment_hits,
    number_forms,
    numbers_in,
    renders_absence_as_value,
    says_not_published,
    strip_label_references,
    year_tokens,
)
from homeroom.ask.narration import CLAIM_KINDS
from homeroom.i18n import LOCALES, Locale

MAX_CLAIM_CHARS = 700
MAX_CLAIMS = 12

REASONS: tuple[str, ...] = (
    "malformed",
    "no_citation",
    "judgment_language",
    "unresolved_citation",
    "unverifiable_number",
    "absence_unstated",
    "absence_as_value",
    "comparison_shape",
    "comparison_unpublished",
    "comparison_direction_missing",
    "comparison_direction_ambiguous",
    "comparison_direction_wrong",
    "definition_without_quote",
    "quote_not_verbatim",
)

ANCHORS: dict[str, str] = {
    "enrollment.total": "students",
    "enrollment.grade": "grades",
    "enrollment.group": "groups",
    "absenteeism.total": "absenteeism",
    "absenteeism.group": "absenteeism",
}
"""Where on the school page each measure's table sits, by key prefix."""


@dataclass(frozen=True)
class Claim:
    kind: str
    text: str
    cites: tuple[str, ...]
    quote: str | None = None


@dataclass(frozen=True)
class Citation:
    """One resolved citation, in the shape the page renders it."""

    id: str
    type: str
    label: str
    scope: str | None = None
    year: str | None = None
    anchor: str | None = None
    url: str | None = None
    title: str | None = None


@dataclass(frozen=True)
class ShownClaim:
    kind: str
    text: str
    citations: tuple[Citation, ...]
    quote: str | None = None


@dataclass(frozen=True)
class WithheldClaim:
    reason: str
    text: str
    detail: str = ""


@dataclass(frozen=True)
class Verification:
    shown: tuple[ShownClaim, ...]
    withheld: tuple[WithheldClaim, ...]

    @property
    def withheld_reasons(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for claim in self.withheld:
            counts[claim.reason] = counts.get(claim.reason, 0) + 1
        return dict(sorted(counts.items()))


def _claims_list(raw: object) -> object:
    """The ``claims`` value, parsed if the model sent the array as a JSON string.

    Some replies carry the array serialised inside a string. Strict
    ``json.loads`` is the only repair attempted; anything it rejects is
    malformed, because guessing at a claim is the one thing this module must
    never do.
    """
    if not isinstance(raw, dict):
        return None
    claims = raw.get("claims")
    if isinstance(claims, str):
        try:
            return json.loads(claims)
        except ValueError:
            return None
    return claims


def parse_claims(raw: object) -> list[Claim | WithheldClaim]:
    """Read the model's tool input. A malformed entry is withheld, not dropped."""
    claims = _claims_list(raw)
    if not isinstance(raw, dict) or not isinstance(claims, list):
        shape = f"keys {sorted(raw)}" if isinstance(raw, dict) else type(raw).__name__
        return [WithheldClaim("malformed", "", f"claims is not a list ({shape})")]
    out: list[Claim | WithheldClaim] = []
    for entry in claims[:MAX_CLAIMS]:
        if not isinstance(entry, dict):
            out.append(WithheldClaim("malformed", "", "claim is not an object"))
            continue
        kind = entry.get("kind")
        text = entry.get("text")
        cites = entry.get("cites")
        quote = entry.get("quote")
        if (
            not isinstance(kind, str)
            or kind not in CLAIM_KINDS
            or not isinstance(text, str)
            or not text.strip()
            or len(text) > MAX_CLAIM_CHARS
            or not isinstance(cites, list)
        ):
            out.append(
                WithheldClaim(
                    "malformed", str(text or ""), "kind, text, or cites off-schema"
                )
            )
            continue
        out.append(
            Claim(
                kind=kind,
                text=text.strip(),
                cites=tuple(dict.fromkeys(str(c).strip() for c in cites)),
                quote=quote.strip()
                if isinstance(quote, str) and quote.strip()
                else None,
            )
        )
    return out


@dataclass
class _Resolved:
    cells: list[tuple[str, EvidenceRecord, str, Cell]] = field(default_factory=list)
    passages: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)


def _resolve(claim: Claim, evidence: SchoolEvidence, corpus: Corpus) -> _Resolved:
    """Each cite is a cell of this school, a corpus passage, or a source file key.

    A source key (``d2``, ``d3``) lets a note say which file and year a figure
    comes from without inventing a cell to hang it on; it allows no number but
    that source's academic year.
    """
    resolved = _Resolved()
    for cite in claim.cites:
        hit = evidence.cell(cite)
        if hit is not None:
            record, scope, cell = hit
            resolved.cells.append((cite, record, scope, cell))
        elif corpus.passage(cite) is not None:
            resolved.passages.append(cite)
        elif cite in evidence.sources:
            resolved.sources.append(cite)
        else:
            resolved.unresolved.append(cite)
    return resolved


CONTEXT_CLAIM_KINDS: frozenset[str] = frozenset({"note"})
"""Kinds whose subject may be a fact *about* the data rather than a cell's value.

A record carries two very different sorts of number. One is the school's own
published figure. The other is context attached to the same record: how many
schools in this build published that measure, how many withheld it, how many
never appeared, the size of the build, the grade span in the school's identity.

Those context numbers are real and a reader is entitled to them, but they are
not the school's measured value, and licensing them for every claim that cites
the record lets a sentence assert one of them *as* the value. The fixture makes
the collision concrete: Example Elementary's absenteeism rate is 12.5% and its
coverage tally is ``{"reported": 1, "suppressed": 1, "not_reported": 1}``, so
"the rate was 1%" once verified clean (issue #34).

So context numbers are licensed only for the kind whose whole job is context.
``note`` is documented to the model as "context about the data (which year, why
a figure is withheld)"; ``figure`` and ``comparison`` state cells' values and
get only the values their own cited cells publish.

A measure's *label* carries the third sort of number, and narrowing by kind
cannot reach it: "Grade 4" has to be sayable in a figure claim, because naming
the row is half the sentence. That one is narrowed by position instead --
:func:`homeroom.ask.guards.strip_label_references` -- so the digit is licensed
where it is written against the label's own word and nowhere else. Until
2026-09-02 it was licensed as a bare token, and "Example Elementary enrolled 4
students in Grade 4" verified clean against a cell whose value is 9.
"""


def _cited_labels(resolved: _Resolved) -> list[str]:
    """Every cited measure's label, in both languages.

    Both, not the answer's own, because the label is the measure's name and a
    sentence may carry it in either: a Spanish answer names CDE's categories,
    and the fixtures' school and district names are English inside one. Which
    language a label is written in does not change that its digits are part of
    the name (issue #34, :func:`strip_label_references`).
    """
    return [
        record.spec.label(locale)
        for _, record, _, _ in resolved.cells
        for locale in LOCALES
    ]


def _allowed_numbers(
    resolved: _Resolved,
    evidence: SchoolEvidence,
    verified_quote: str | None,
    kind: str,
) -> set[str]:
    context = kind in CONTEXT_CLAIM_KINDS
    allowed: set[str] = set()
    for _, record, _, cell in resolved.cells:
        if cell.reported and cell.value is not None:
            allowed |= number_forms(cell.value)
        allowed |= year_tokens(record.year)
        if context:
            for count in record.coverage.values():
                allowed |= number_forms(count)
    if resolved.cells and context:
        allowed |= number_forms(evidence.schools_in_build)
        allowed.update(numbers_in(evidence.grades_served.replace("-", " ")))
    for source in evidence.sources.values():
        if source.academic_year:
            allowed |= year_tokens(source.academic_year)
    if verified_quote:
        allowed.update(numbers_in(verified_quote))
    return allowed


_HIGHER = re.compile(
    r"\b(?:higher|above|more|greater|larger|bigger|exceeds?|"
    r"m[aá]s alt[ao]s?|mayor(?:es)?|por encima|supera|m[aá]s grandes?|m[aá]s que)\b",
    re.IGNORECASE,
)
_LOWER = re.compile(
    r"\b(?:lower|below|less|fewer|smaller|under|"
    r"m[aá]s baj[ao]s?|menor(?:es)?|por debajo|menos|m[aá]s peque[nñ][ao]s?)\b",
    re.IGNORECASE,
)
_SAME = re.compile(
    r"\b(?:the same as|same as|equal to|equals|identical to|matches|"
    r"igual (?:a|que)|la misma que|el mismo que|coincide con)\b",
    re.IGNORECASE,
)
_COMPARATIVE = re.compile(
    r"\b(?:than|compared|versus|que (?:el|la|los|las)|comparad[ao]|respecto|frente a)\b",
    re.IGNORECASE,
)


def _is_comparative(text: str) -> bool:
    return bool(_COMPARATIVE.search(text)) and bool(
        _HIGHER.search(text) or _LOWER.search(text) or _SAME.search(text)
    )


def _directions(text: str) -> set[str]:
    found: set[str] = set()
    if _HIGHER.search(text):
        found.add("higher")
    if _LOWER.search(text):
        found.add("lower")
    if _SAME.search(text):
        found.add("same")
    return found


def _spoken_from_the_other_side(text: str, other: float) -> bool:
    """True if the sentence names the district or state figure before it compares.

    "The district's 609 is higher than the school's 58" speaks from the
    district's side; "the school's 58 is lower than the district's 609" and
    "that is lower than the district's 609" speak from the school's. The tell
    is whether the other figure is written before the first comparative word.
    """
    stripped = text.replace(",", "")
    positions = [
        m.start()
        for pattern in (_COMPARATIVE, _HIGHER, _LOWER, _SAME)
        for m in pattern.finditer(stripped)
    ]
    if not positions:
        return False
    first_marker = min(positions)
    found = [stripped.find(form) for form in number_forms(other) if form in stripped]
    return bool(found) and min(found) < first_marker


def _check_comparison(claim: Claim, resolved: _Resolved) -> WithheldClaim | None:
    """A comparison is exactly two published cells of one record, school first."""
    if (
        len(resolved.cells) != 2
        or resolved.passages
        or resolved.sources
        or resolved.unresolved
    ):
        return WithheldClaim(
            "comparison_shape",
            claim.text,
            "a comparison cites exactly the school cell and one district or state "
            "cell of the same record",
        )
    (_, rec_a, scope_a, cell_a), (_, rec_b, scope_b, cell_b) = resolved.cells
    if rec_a.id != rec_b.id or "school" not in (scope_a, scope_b) or scope_a == scope_b:
        return WithheldClaim(
            "comparison_shape",
            claim.text,
            "cells are not school + context of one record",
        )
    school = cell_a if scope_a == "school" else cell_b
    other = cell_b if scope_a == "school" else cell_a
    if (
        not school.reported
        or not other.reported
        or school.value is None
        or other.value is None
    ):
        return WithheldClaim(
            "comparison_unpublished",
            claim.text,
            "one side of the comparison is not a published figure",
        )
    directions = _directions(claim.text)
    if not directions:
        return WithheldClaim("comparison_direction_missing", claim.text)
    if len(directions) > 1:
        return WithheldClaim(
            "comparison_direction_ambiguous", claim.text, ", ".join(sorted(directions))
        )
    stated = directions.pop()
    subject, object_ = school.value, other.value
    if _spoken_from_the_other_side(claim.text, other.value):
        # "The district's 609 is higher than the school's 58": the sentence is
        # from the district's side, and the direction is read that way.
        subject, object_ = other.value, school.value
    actual = "higher" if subject > object_ else "lower" if subject < object_ else "same"
    if stated != actual:
        return WithheldClaim(
            "comparison_direction_wrong",
            claim.text,
            f"text says {stated}, figures say {actual}",
        )
    return None


def _citation(
    cite: str,
    record: EvidenceRecord,
    scope: str,
    evidence: SchoolEvidence,
    locale: Locale,
) -> Citation:
    prefix = ".".join(record.measure.split(".")[:2])
    source = evidence.sources.get(record.source)
    return Citation(
        id=cite,
        type="cell",
        label=record.spec.label(locale),
        scope=scope,
        year=record.year,
        anchor=ANCHORS[prefix],
        url=source.url if source else None,
        title=source.file_name if source else None,
    )


def _source_citation(cite: str, evidence: SchoolEvidence) -> Citation:
    source = evidence.sources[cite]
    return Citation(
        id=cite,
        type="source",
        label=source.file_name,
        year=source.academic_year,
        anchor="sources",
        url=source.url,
        title=source.file_name,
    )


def _passage_citation(cite: str, corpus: Corpus) -> Citation:
    passage = corpus.passage(cite)
    source = corpus.sources[passage.source] if passage else None
    return Citation(
        id=cite,
        type="passage",
        label=source.title if source else cite,
        url=source.url if source else None,
        title=source.title if source else None,
    )


def _check_quote(
    claim: Claim, resolved: _Resolved, corpus: Corpus
) -> str | WithheldClaim | None:
    """The verified quote, a withheld claim, or ``None`` when there is no quote."""
    if claim.quote is None:
        if claim.kind == "definition":
            return WithheldClaim("definition_without_quote", claim.text)
        return None
    if not any(corpus.quote_is_verbatim(p, claim.quote) for p in resolved.passages):
        return WithheldClaim("quote_not_verbatim", claim.text, claim.quote[:120])
    return claim.quote


def _check_absence(claim: Claim, resolved: _Resolved) -> WithheldClaim | None:
    if not any(not cell.reported for _, _, _, cell in resolved.cells):
        return None
    if renders_absence_as_value(claim.text):
        return WithheldClaim("absence_as_value", claim.text)
    if not says_not_published(claim.text):
        return WithheldClaim("absence_unstated", claim.text)
    return None


def _verify_one(
    claim: Claim, evidence: SchoolEvidence, corpus: Corpus, locale: Locale
) -> ShownClaim | WithheldClaim:
    if not claim.cites:
        return WithheldClaim("no_citation", claim.text)
    hits = judgment_hits(claim.text)
    if hits:
        return WithheldClaim("judgment_language", claim.text, ", ".join(hits))
    resolved = _resolve(claim, evidence, corpus)
    if resolved.unresolved:
        return WithheldClaim(
            "unresolved_citation", claim.text, ", ".join(resolved.unresolved)
        )
    quote = _check_quote(claim, resolved, corpus)
    if isinstance(quote, WithheldClaim):
        return quote
    allowed = _allowed_numbers(resolved, evidence, quote, claim.kind)
    stated = strip_label_references(claim.text, _cited_labels(resolved))
    stray = [n for n in numbers_in(stated) if n not in allowed]
    if stray:
        return WithheldClaim("unverifiable_number", claim.text, ", ".join(stray))
    absence = _check_absence(claim, resolved)
    if absence is not None:
        return absence
    if claim.kind == "comparison" or (resolved.cells and _is_comparative(claim.text)):
        problem = _check_comparison(claim, resolved)
        if problem is not None:
            return problem
    citations = (
        tuple(
            _citation(cite, record, scope, evidence, locale)
            for cite, record, scope, _ in resolved.cells
        )
        + tuple(_passage_citation(cite, corpus) for cite in resolved.passages)
        + tuple(_source_citation(cite, evidence) for cite in resolved.sources)
    )
    return ShownClaim(
        kind=claim.kind, text=claim.text, citations=citations, quote=quote
    )


def verify(
    claims: list[Claim | WithheldClaim],
    evidence: SchoolEvidence,
    corpus: Corpus,
    locale: Locale,
) -> Verification:
    shown: list[ShownClaim] = []
    withheld: list[WithheldClaim] = []
    for claim in claims:
        if isinstance(claim, WithheldClaim):
            withheld.append(claim)
            continue
        result = _verify_one(claim, evidence, corpus, locale)
        if isinstance(result, ShownClaim):
            shown.append(result)
        else:
            withheld.append(result)
    return Verification(shown=tuple(shown), withheld=tuple(withheld))
