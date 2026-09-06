# 0005. Publish teacher assignment monitoring, on each school's own terms

Status: Accepted (owner decision on an open question)
Date: 2026-09-05
Deciders: Chelsea Kelly-Reif
Relates to: ADR 0002 (refuse to rank schools), which binds this decision and is
not amended. ADR 0001 is not amended either: the pages stay static, script-free
and rendered by the same stdlib renderer.

## Context

D5 is CDE's Teacher Assignment Monitoring Outcome file, published from the
Commission on Teacher Credentialing's CalSAAS system. For each school it
records how much teaching, in full-time-equivalent units, sat on a clear
credential appropriately matched to the assignment, and how much sat in each of
the other authorization states the state tracks.

The engineering has been finished since 2026-08-21. The 2023-24 file
(`tamo2324.txt`, 234,206,408 bytes, 1,528,796 rows) was acquired, its header
read directly, and `src/homeroom/assignments.py` rewritten against it after the
provisional contract failed in every particular; the parser, the spine join, the
artifact and the coverage output are covered, including fourteen drift refusals
(PROVENANCE.md D5, docs/ROADMAP.md "D5a values"). What was never done was put a
D5 number in front of a family. `docs/ROADMAP.md` said so in as many words --
"publishing it on a page is a separate decision this roadmap has not made" --
and tracked it as issue #59 rather than promising it a milestone.

The reason it was held open is not that the file is hard to read. It is that
these outcomes are about staffing at a named school, which is a different kind
of claim from an enrollment count. Three specific hazards were named when the
question was opened, and each one is a way this data becomes something other
than what CDE published:

- **It is league-table bait.** "Percent of teaching on a clear credential" is
  exactly the shape of a number a rater would sort 10,534 schools by, and
  sorting schools is what this project refuses to do (ADR 0002). Publishing the
  figure and publishing an ordering of it are not the same act, but the first
  makes the second easy for somebody else.
- **It reads as a judgment of teachers.** `docs/RESPONSIBLE-TECH-AUDITS.md` §D
  already carries this as an open review item: an outcome describes which
  credential an assignment sat on, a fact about the state's own monitoring, and
  page copy that let a family read it as an evaluation of the person in front of
  their child would be wrong about what the file says.
- **The obvious summary is a derived value.** The file publishes seven outcome
  counts and seven published shares. A single "share of assignments properly
  credentialed" headline, or a share divided out of the counts, would be a
  number this project computed about a real school.

None of the three is an argument against publishing. Each is an argument about
*how*, and each is answerable in the same way every other measure on these pages
was answered: copy the state's own cells, put them beside the state's own
district and statewide rows, say what is withheld and what was never published,
and rank nothing.

Against that sits the cost of continuing to withhold. Homeroom holds a public
file, verified, about every school it publishes a page for, and the pages say in
words that it exists and is not shown. A family reading about their school can
see enrollment and chronic absenteeism and is told there is a third thing the
project has read and decided not to show them. That is a defensible state to be
in for a week of verification and an indefensible one as a policy: this project
exists because the state's own download pages are unreadable, and the answer to
"this figure is easy to misuse" cannot be to leave it where only researchers can
reach it.

## Decision

The owner decided on 2026-09-05 to publish D5 on the school pages, answering
issue #59. It is published under the same rules as every other measure, with
nothing added for it and nothing relaxed:

1. **Every published cell is a cell CDE published.** For each school the page
   shows CDE's own whole-school total row -- the single row per school where
   Teacher Experience Level and Teacher Credential Level are `ALL` and Subject
   Area is `TA` -- and nothing else. Total teaching FTE, the seven outcome FTE
   counts, and the seven outcome shares are copied. No share is divided out of a
   count, no count is summed out of the file's other ~150 rows for that school,
   and no outcome is combined with another.

2. **All seven outcomes, or none.** The page does not lift "clear credential"
   out as a headline figure. Seven measures on their own terms is a table; one
   of them alone is a score with the other six deleted, and a reader would infer
   the remainder from it anyway.

3. **Counts and shares are both published, side by side, as separate tables.**
   CDE publishes both, so both are copyable. Showing only the share hides how
   large the school is; showing only the count invites the renderer to compute
   the share. A school whose share cell is withheld shows a withheld share even
   where its count is visible, because that is what the file says.

4. **Four cell states, unchanged.** A published number, a published zero, a
   figure the state withheld, and nothing published at all keep their own words,
   their own colour and their own CSS class, in both languages, and the withheld
   and the missing never render a digit. The acquired 2023-24 file masks no
   cell anywhere, and the path stays load-bearing anyway: a future year that
   masks must render as withheld and not as zero, and the committed fixture
   keeps a wholly-withheld school so a test exercises it.

5. **District and statewide context comes from CDE's own aggregate rows.**
   `homeroom.context.load_assignment_context` reads the file's own `D` and `T`
   rows where Charter School, DASS and School Grade Span all read the
   aggregated value, never a sum of schools -- the same rule, for the same
   reason, that D2 and D3 already follow: summing a masked column publishes a
   figure that silently excludes the students the mask protected. The context is
   there to give a number a size, and the page says in words that being above or
   below it is not by itself good or bad.

6. **Coverage sits beside the data.** Every row carries how many of the schools
   in the build publish that figure, withhold it, and publish nothing, and the
   coverage section states the same three counts for the total. A page showing
   only what exists would read as a complete picture.

7. **Absence and masking never collapse into each other, at three levels.** A
   build given no D5 file renders no assignment section at all and says in words
   that the data is not published here; a school the supplied file never
   mentions renders "no figure published" in every cell; a cell the state
   withheld renders "withheld to protect privacy". These are three different
   facts and the page keeps them apart, the same way `SchoolProfile` does.

8. **The framing is the state's monitoring, not a verdict on a teacher.** The
   section's copy says, in both languages, that these are the state's own
   counts of teaching assignments by the authorization they sat on, that they
   describe assignments and not people, and that Homeroom neither computes nor
   scores them. This closes the review item `docs/RESPONSIBLE-TECH-AUDITS.md` §D
   opened for D5.

Consequential choices:

- **`make site` and `make data` are given the file.** A page that shows a figure
  the artifact omits would be two different answers to the same question, so
  `--assignments` moves from a documented option to the default invocation of
  both, and `make site-offline` is given the committed fixture so the a11y and
  EN/ES parity gates read the new markup rather than stepping around it.
- **The ask layer does not gain D5.** `homeroom.ask` (ADR 0003) answers from an
  evidence bundle that carries enrollment and chronic absenteeism, and adding a
  measure to it means new catalog entries, new verifier cases, and a live
  evaluation run before any sentence about it reaches a reader. That is a
  separate decision with a separate cost, and it is not made here. The one
  refusal string that described what the ask layer can answer as "the files
  behind this page" is reworded, because the page now covers more than the
  answer does and the sentence would otherwise be false.
- **Nothing is republished by this change.** Rendering the real site remains a
  step the owner runs; `site/` is untouched here.

## Consequences

- Several published claims become false and are rewritten in the same change:
  PROVENANCE.md D5's "not joined to any artifact or page by default", the
  ROADMAP D5a row and its "D5 numbers published about a real school | 0" ledger
  entry, the M4 ledger's "D5 numbers on any page | 0", and the README paragraph
  saying `homeroom.site` accepts no argument for the file. The old text was the
  honest record of the old state and is replaced, not quietly amended away.
- The test that proved no D5 figure could reach a page is replaced by the tests
  that prove the four cell states, the three levels of absence, and the
  no-recomputation rule hold for it. The rule it was really guarding -- every
  number in a data cell is one the pipeline read or counted -- now covers D5
  too, and is what fails if a share is ever divided out of a count.
- Every school page grows three tables and seventeen measures. M3 kept its new
  tables at seven columns while the screen-reader walkthrough (RR-05) is still
  open; these do the same, for the same reason.
- The ordering hazard does not go away because the page refuses to order. What
  the project controls is that it publishes no ranking, no composite, and no
  cross-school comparison, and that every figure carries the file, the year and
  the coverage a reader needs to see what it is not. Somebody else can still
  sort a public file; they could before this decision too.
- Two academic years are already on these pages (D2's 2025-26, D3's 2024-25) and
  D5 adds a third, 2023-24. Each section names its own year in its own captions,
  and the renderer never lets one source's year print over another's numbers.

## Alternatives considered

- **Keep D5 unpublished.** The status quo, and the position `docs/ROADMAP.md`
  held from D5a to now. Rejected by the owner: the reason for holding was that
  publishing needed a decision, not that the decision was no, and a verified
  public file about staffing at a school is exactly the kind of thing this
  project exists to make readable. Holding it further would have meant a page
  that names a measure and declines to show it, indefinitely.
- **Publish one headline figure: the share of assignments on a clear
  credential.** Rejected. One number standing for seven is a composite in
  miniature, it is the single most sortable thing the file contains, and it
  invites the reader to infer the six outcomes it hides. ADR 0002's objection is
  to compression, and this is compression.
- **Publish the counts only, and let a reader do the division.** Rejected: CDE
  publishes the share itself, so dropping it would be withholding a copyable
  cell while inviting the arithmetic that copying it avoids -- and on a masked
  row that arithmetic would read a withheld cell as zero.
- **Compute each share from the counts rather than reading CDE's percent
  column.** Rejected outright. It is a derived value about a real school, it
  would produce a number where the state withheld one, and it is the exact
  failure `homeroom.measures` exists to make impossible.
- **Sum the file's ~150 rows per school instead of taking CDE's own total
  row.** Rejected for the same reason `homeroom.assignments.school_outcomes`
  already rejects it: the whole-school row is CDE's aggregate, computed by the
  people who hold the unmasked data, and summing masked columns is how a total
  quietly loses the students a mask was protecting.
- **Publish D5 in the artifacts only, not on the pages.** Rejected: the
  artifacts have been able to carry it since D5a, and a JSON file is not the
  audience. The family reading the page is.
- **Publish the subject-area, experience-level and credential-level
  breakdowns too.** Not now. The file carries up to 150 rows per school and
  each cross is a real published cell, but a page is not a query interface, and
  the whole-school row is the one CDE itself computed. A later ADR can widen
  this; nothing here forecloses it.
