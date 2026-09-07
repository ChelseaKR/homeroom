---
name: Report a screen-reader or keyboard session
about: You walked one page with a screen reader, a keyboard, or at 320px, and can say what happened
title: "[a11y session] <page type> · <language> · <your screen reader + browser>"
labels: ["accessibility", "help wanted"]
---

<!--
This is the contribution this project is most stuck on, and it is the one no
amount of code closes.

docs/accessibility-walkthrough.md holds the procedure and an empty record: ten
rows, five page types in two languages, every cell reading UNMET. Nobody has
walked any page of this site with a keyboard or a screen reader, in either
language. tests/test_accessibility_review.py holds the README, the roadmap and
the residual-risk register to saying so, so the gap cannot quietly close.

You do not need to be an accessibility expert. You need a screen reader you
already use, or a keyboard and the patience to press Tab a lot.

ONE ROW IS A WHOLE CONTRIBUTION. One page type, one language, one screen
reader, one sitting. The procedure says it in terms: "Leave every row you did
not walk at UNMET. A partial walkthrough recorded as a partial walkthrough is
the point." You are not signing up for ten rows.

Roughly what a row costs, honestly: the landing, county and district pages are
20 to 40 minutes each. The school page is the hard one and is more like an
hour on its own, because it has ten seven-column tables inside scrolling
regions. The ask page is 20 to 30 minutes. Add setup time the first time,
especially for the Spanish voice (see below). If that is more than you have,
walk part of a row and say where you stopped.
-->

## What you walked

- **Page (paste the URL):** <!-- e.g. https://homeroom.chelseakr.com/57726786056246.es.html -->
- **Page type:** <!-- landing / county / district / school / ask -->
- **Language:** <!-- en / es -->
- **How long it took you:** <!-- honestly. If it took three times what the note above says, that is itself a finding. -->

## Your setup

Versions matter more than they look like they do: a screen reader and a browser
fail as a pair, not separately.

- **Screen reader + version:** <!-- e.g. VoiceOver on macOS 15.3, NVDA 2024.4, TalkBack 15 -->
- **Browser + version:**
- **Operating system + version:**
- **Keyboard only, or screen reader, or both:**
- **If you tested reflow:** viewport or zoom level you used
- **Spanish voice installed and automatic language switching on?** <!-- Only if you walked a Spanish page. If a Spanish page was read to you in an English voice, that is very likely your settings and not the page - docs/accessibility-walkthrough.md has the setup steps. Say so either way rather than filing it as a page finding. -->

## What happened

<!--
Describe what you did and what you heard or saw, in order. Quote what was
announced where you can, including the bits that were wrong.

Please do NOT tell us whether the page conforms to anything. That judgement is
not what this report is for, and a report that leads with "looks fine" is a
report that gets nodded through. Say what happened; the conformance question is
settled somewhere else, against the record, by someone who has to sign it.
-->

## Where it stopped, or got hard

- [ ] I completed the task
- [ ] I completed it, but it was harder than it should have been
- [ ] I could not complete it
- [ ] I could not tell whether it worked

<!--
"I could not tell" is a real answer and this project wants it recorded as
itself. The one thing that must never happen here is a check nobody could
actually make being written down as a check that passed.
-->

## If you walked the school page

These two are the reason this gate exists. Answer them if you got to them, and
skip them without apology if you did not.

1. **The four cell states by voice.** A published number, a published zero
   ("reported as zero" / "informado como cero"), a withheld figure ("withheld
   to protect privacy" / "retenido para proteger la privacidad") and a figure
   the state never published ("no figure published" / "sin dato publicado")
   are meant to be four distinguishable announcements, each carrying its row
   and column header. Did any two of them sound the same to you?

2. **A seven-column row at 320 CSS pixels.** Find one school's figure and the
   California comparison in the same row, on a phone or at 400% zoom. Could
   you? This is the finding the table design has been waiting on.

<!--
Both of those are about a real thing: if a withheld cell is announced as a bare
number, a screen-reader reader is told a number the state deliberately did not
publish. That is the whole suppression design failing in the ear while passing
every automated check.
-->

## How you want to be credited

The record in `docs/accessibility-walkthrough.md` names who walked each row and
when. A row that claims a result without both is rejected by the test suite, so
this is not decoration.

- **Name or handle to record:**
- [ ] Record my name
- [ ] Record a handle or an organisation instead
- [ ] Do not record me; treat this as an anonymous report and leave the row's
      "walked by" cell empty

<!--
If you leave the walker unnamed the row cannot move off UNMET, because the
record's own rule is that a result needs a name and a date. Your findings are
still useful and still get filed and fixed. Say what you prefer; nobody will
push you to be named.
-->

## Did you walk another project in the same sitting?

A session report is portable. The same setup answers the same question for
several projects in this portfolio that are each blocked on a manual
screen-reader and keyboard pass and have never had one:

- homeroom (this repo), issue #6
- tods-validate #74 and #184
- ctdl-validate #54
- fare-policy-assistant #201
- gauntlet #35
- permit-bearings, the manual rows in `docs/MANUAL-VALIDATION.md`

If you walked more than one, file the detail wherever you did the most, and
link that issue from the others rather than retyping it. Link it here:

- **Other session reports:**
