# Help wanted: the half of this project a person has to do

Homeroom publishes California's public school data as plain-language, bilingual
school pages: 10,534 active schools, 21,069 pages, English and Spanish, live at
<https://homeroom.chelseakr.com>. It refuses to rank schools. Each measure is
shown on its own terms with its suppression and coverage stated, and a number
that cannot be shown honestly is not shown at all.

That last rule is the whole project, and it is the rule this document is about.

## What is not done, and why no amount of code closes it

**Nobody has ever listened to this site.**

The automated half of the accessibility gate is real and merge-blocking. `make
pages` builds every page type from committed fixtures and runs `html-validate`
and `axe-core` over WCAG 2.0/2.1/2.2 A and AA plus best-practice, in both
languages, on every built page. `tests/test_pages.py` measures colour contrast
for every pair the pages use in both themes and asserts that each cell state
carries its own words, so colour is never the only signal. That gate has been at
zero violations since M4.

It cannot look at, or listen to, a page. `tools/a11y.mjs` runs in jsdom, which
does no layout and paints no pixels; it excludes `color-contrast` and
`target-size` by name rather than letting an unrunnable rule report as a pass.
No headless DOM decides whether a seven-column table inside a horizontally
scrolling region is usable on a phone, whether a focus ring is visible against
the surface it lands on, whether a Spanish page is announced with Spanish
phonemes, or whether "withheld to protect privacy" and a published number are
distinguishable by voice alone.

That last one is not a detail. This site's argument is that a family can read
this data. If a screen reader announces a withheld cell as a bare number, then
a figure the state deliberately did not publish has just been read aloud as a
fact, and the suppression design has failed in the reader's ear while passing
every check in CI. **No test can find that. A person listening can find it in
about a minute.**

The procedure and the empty record are committed at
[`docs/accessibility-walkthrough.md`](accessibility-walkthrough.md). Ten rows:
five page types in two languages. Every cell reads UNMET. The gap is tracked at
[issue #6](https://github.com/ChelseaKR/homeroom/issues/6) and as RR-05 in the
residual-risk register, and `tests/test_accessibility_review.py` holds the
README, the roadmap and the audit document to saying it is open for as long as
any cell is UNMET. The gap cannot quietly close, and it also cannot open itself.

## What one hour would unblock

**One row.** One page type, one language, one screen reader, one sitting.

The procedure says it in terms: *"Leave every row you did not walk at UNMET. A
partial walkthrough recorded as a partial walkthrough is the point."* You are
not signing up for ten rows, and nobody will ask you for the other nine.

Honest costs, so you can pick one that fits the time you actually have:

| Row | Roughly | Why |
|---|---|---|
| Landing page | 20 to 40 min | One document holding both languages; 58 county links each |
| County page | 20 to 30 min | A breadcrumb and a district list |
| District page | 30 to 40 min | Same shape, but the largest one lists 994 schools |
| School page | about an hour | Ten seven-column tables in scrolling regions. The hard one. |
| Ask page | 20 to 30 min | The only page with a script: a form and a live region |

Add setup time the first time, and add real setup time for Spanish: a screen
reader announces `lang="es"` content with Spanish phonemes only if a Spanish
voice is installed and automatic language switching is on. The procedure has
the steps. If you skip that, every Spanish row you walk records a finding about
your own configuration instead of about the page, which helps nobody.

**This is not a five-minute task and this page will not pretend it is.** There
is no workbench here that reduces it, the way trans-docs-navigator's verifier
workbench reduces checking a legal record. What there is, is a written
procedure that tells you exactly what to press and what a pass and a failure
each look like, so you are not inventing a method.

Two answers are worth as much as a clean run:

- **"I could not tell."** Recorded as itself. The one thing that must never
  happen is a check nobody could make being written down as a check that
  passed.
- **"I got two screens in and stopped."** Say where. A partial row is a real
  contribution and the record has a place for it.

File it with the [screen-reader session
template](https://github.com/ChelseaKR/homeroom/issues/new?template=screen-reader-session.md).

### The other thing that needs a person

If you work at a California school or district, or you are a parent at one, you
know things about a school that no dataset check can see. The [school page
looks wrong
template](https://github.com/ChelseaKR/homeroom/issues/new?template=school-page-looks-wrong.md)
takes five minutes and needs nothing but the page in front of you. The most
valuable version of it is: *the page showed a number where the state withheld
one, or the label made me read the number as something it is not.*

## What you get

- **Your name and the date in the record**, in
  `docs/accessibility-walkthrough.md`, against the row you walked. This is not
  decoration: `tests/test_accessibility_review.py` rejects a row that claims a
  result without both a name and a date, so the record cannot say a walk
  happened without saying who did it.
- **A dated, committed, citable artifact.** The record is a file in a public
  repository with a `CITATION.cff`, at a commit, in history. "I performed the
  accessibility walkthrough of the school page, English and Spanish, on this
  date" is a thing you can link to and put on a CV. Manual accessibility
  testing is skilled work that mostly disappears into private audit PDFs; this
  one does not.
- **Findings filed as issues with your report linked**, so what you found has
  a life after the sitting.

## A question this project has not answered

Being credited means being named in a public file, and for some people that is
not free. This repository has no policy on whether a pseudonym, a handle, or an
organisation name is acceptable in the walker column, and it is not this
document's place to invent one.

The session template therefore offers three options - name, handle or
organisation, or anonymous - and is honest about the consequence of the third:
an unnamed row cannot move off UNMET, because the record's own rule is that a
result needs a name and a date. Your findings are still filed and still fixed.

Whether that rule should have a pseudonym path is an open question for the
maintainer. Sibling projects in this portfolio have answered it differently:
contextsafe's hazard register accepts pseudonymity and publishes no roster
without individual written consent; trans-docs-navigator requires a named
verifier on a public roster and serves an audience for whom being named
carries real risk. Those two cannot both be right for every project, and
nobody should resolve that in an issue thread.

If you want to help but not be named, say so. That is a supported answer, not a
lesser one.

## Reusing one session across several projects

This is not the only project in this portfolio blocked on exactly this. A
single sitting with one screen reader answers the same question for several,
and the session report is portable:

- homeroom, [#6](https://github.com/ChelseaKR/homeroom/issues/6)
- tods-validate, [#74](https://github.com/ChelseaKR/tods-validate/issues/74)
  and [#184](https://github.com/ChelseaKR/tods-validate/issues/184)
- ctdl-validate, [#54](https://github.com/ChelseaKR/ctdl-validate/issues/54)
- fare-policy-assistant,
  [#201](https://github.com/ChelseaKR/fare-policy-assistant/issues/201)
- gauntlet, [#35](https://github.com/ChelseaKR/gauntlet/issues/35)
- permit-bearings, the manual rows in `docs/MANUAL-VALIDATION.md`

File the detail wherever you did the most work and link that issue from the
others. Nobody should have to type a session report twice.
