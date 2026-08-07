# 0000. Refuse to rank schools

Status: Accepted
Date: 2026-08-07
Deciders: Chelsea Kelly-Reif

## Context

Most families meet California school data through commercial raters that compress
every measure into one composite score. The equity harms of that compression are
well documented: composite scores track demographics and property wealth more than
anything a school controls, they steer enrollment and housing decisions toward
already-advantaged schools, and they punish the schools serving the students with
the greatest needs. The weights inside a composite are opinions wearing the costume
of measurement.

Homeroom joins the state's own public data into family-readable pages. The founding
question is whether it ever computes a summary judgment of a school. This is an
architectural decision, not an editorial preference, because aggregation is where
the harm enters and because the data itself resists it: CDE masks small cells
(published as `*`) to protect students, and any pipeline casual about those masks
converts protected students into fake zeros that then flow into averages and ranks.

This is also the repo's first ADR. Decisions here are recorded as sequential
MADR-style ADRs in `docs/adr/`, immutable once Accepted; a change of course adds a
new ADR with `Status: Superseded by NNNN` rather than editing an old one.

## Decision

Homeroom refuses to rank schools, and the refusal is enforced in the data model,
not in a style guide:

- No composite score, no letter grade, no ordering of one school above another.
  No code path combines measures across domains into a single number, and no such
  code path will be accepted.
- Each measure renders on its own terms, beside the statewide and district context
  needed to read it, with its suppression and coverage stated.
- The `Measure` type (`src/homeroom/measures.py`) makes the dangerous shortcut
  impossible: `reported`, `suppressed`, and `not_reported` are distinct statuses,
  and `Measure.number()` raises `SuppressedValueError` unless the state actually
  published a number. A masked cell is unreadable, so downstream code cannot
  average it, rank on it, or chart it as zero.
- `parse_cell` refuses to guess. A cell that is neither a number, the `*` mask,
  nor empty is a hard build failure, because every guess becomes a statement about
  a real school.
- Any PR touching this guardrail (the `Measure` type, suppression handling, or
  anything that scores or orders schools) must link an ADR. Adding a ranking would
  require a superseding ADR, which is to say a recorded reversal of the project's
  founding commitment.

## Consequences

- Homeroom cannot answer "which school is best." That is the point, and it is a
  permanent product constraint, not a missing feature.
- Rendering code carries the cost of three statuses everywhere a number could
  appear. The type system makes forgetting impossible; the cost is accepted.
- Comparison stays possible measure by measure, in context. The harm addressed is
  aggregation, not information.
- Suppressed data renders as not published, never as zero, in every artifact.
- An unrecognized upstream sentinel stops the build instead of shipping a wrong
  page, so upstream drift costs build time rather than credibility.
