# Accessibility walkthrough: the half no gate can run

**Status: not done.** Every cell in [the record](#the-record) below reads UNMET.
Nobody has walked any page of this site with a keyboard or a screen reader, in
either language. This document exists so that the walkthrough can be performed
by a person who was not there when the pages were written, and so that the gap
stops living only in prose.

- Accountable owner: Chelsea Kelly-Reif
- Tracked as [issue #6](https://github.com/ChelseaKR/homeroom/issues/6) and as
  RR-05 in `docs/audits/residual-risk-register.md`
- The commitment it discharges: `docs/RESPONSIBLE-TECH-AUDITS.md` §E, the
  REVIEW item, plus the portfolio controls A11Y-11 (screen-reader walkthrough
  of every primary task, dated committed artifact) and A11Y-12 (keyboard-only
  walkthrough beyond the automated path)
- Adding this document walks nothing. It is the procedure and the empty record,
  not the result.

## Why this is a document rather than a gate

The automated half of this project's accessibility gate is real, wired, and
merge-blocking, and it is not what this document is about. `make pages` builds
every page type from committed fixtures and runs `html-validate` and `axe-core`
over the WCAG 2.0/2.1/2.2 A and AA rule sets plus best-practice, in both
languages, on every built page; `tests/test_pages.py` measures colour contrast
for every pair the pages use in both themes, asserts the document structure a
screen reader depends on, and asserts each cell state carries its own words so
colour is never the only signal. That gate has been at zero violations since
M4.

What it cannot do is look at, or listen to, a page. `tools/a11y.mjs` runs in
jsdom, which does no layout and paints no pixels: it says so in its own header,
and it excludes `color-contrast` and `target-size` by name rather than letting
an unrunnable rule report as a pass. No headless DOM decides whether a
seven-column table inside a horizontally scrolling region is usable on a phone,
whether a focus ring is visible against the surface it lands on, whether a
Spanish page is announced with Spanish phonemes, or whether "withheld to protect
privacy" and a published number are distinguishable by voice alone. The last of
those is the whole design: this site's argument is that a family can read this
data, and a page that passes axe and cannot be heard fails the argument while
passing the gate.

So this is a procedure for a person, and the record of it is a committed
artifact, the way `docs/audits/threat-model.md` and the residual-risk register
are. A walkthrough that finds problems is a better artifact than one that does
not happen.

## What the site publishes

The walkthrough covers 5 page types in 2 languages: 10 rows, every one of them
unwalked. The page types are derived from the published tree rather than
remembered, and `tests/test_accessibility_review.py` re-derives them, so a page
type added later and not walked fails the suite instead of being quietly
skipped.

| Page type | What it is | Walk these files |
|---|---|---|
| Landing page | The front door. One document holding both languages side by side: `<html lang="en">` with a `lang="es"` section under it, and 58 county links in each | `site/index.html` |
| County page | The 116 pages naming the districts in one county | `site/county/01.en.html`, `site/county/01.es.html` |
| District page | The 2,118 pages naming the schools in one district | `site/district/0110017.en.html`, `site/district/0110017.es.html` |
| School page | The product: identity, ten data tables in scrolling regions, coverage, sources | `site/57726786056246.en.html`, `site/57726786056246.es.html` |
| Ask page | The only page on the site that carries a script (ADR 0003): a form, a polite live region, and citations | `site/ask/57726786056246.en.html`, `site/ask/57726786056246.es.html` |

The county and district pages were added on 2026-09-05 with the browse
hierarchy and have never been in front of a person either.

Walk the deployed pages at <https://homeroom.chelseakr.com>, not a local build:
the paths above are the committed bytes that GitHub Pages serves, so
`site/57726786056246.en.html` is `https://homeroom.chelseakr.com/57726786056246.en.html`.
Birch Lane Elementary (CDS 57726786056246) is named here for a reason rather
than at random: it is the one school that carries all four cell states on one
page in both languages -- a published number, a published zero, a withheld
figure and a figure the state never published -- and it is the one school the
ask layer covers, so a single school walks both.

## Before you start

**Assistive technology.** Two screen readers, on their paired browser, is the
minimum; three is better, and the pairing matters more than the count, because
a screen reader and a browser fail as a pair.

| Screen reader | Browser | Platform | Why it is on the list |
|---|---|---|---|
| VoiceOver | Safari | macOS 14 or later | The pairing Apple tests; the only screen reader most Mac readers have |
| NVDA (2024.1 or later) | Firefox, then Chrome | Windows 11 | Free, the most-used screen reader in the WebAIM survey, and the one most likely to find a table-semantics problem |
| VoiceOver | Safari | iOS 17 or later, real phone | Reflow and touch on the device families actually read this on |
| JAWS | Chrome | Windows 11 | Optional; run it if a licence is available |
| TalkBack | Chrome | Android | Optional; the second half of the phone story |

**Make the screen reader able to switch languages.** This is not optional here,
and a walkthrough run without it cannot answer the Spanish half of any row. A
screen reader announces `lang="es"` content with Spanish phonemes only if a
Spanish voice is installed and automatic language switching is on.

- VoiceOver: VoiceOver Utility → Speech → Voices, add a Spanish voice; the
  language-detection setting must be on so the voice follows the document.
- NVDA: install a Spanish voice for your synthesiser (eSpeak NG ships one;
  Windows OneCore needs the Spanish language pack), then NVDA menu →
  Preferences → Settings → Speech → "Automatic language switching (when
  supported)".
- Confirm it works before walking anything: open `site/57726786056246.es.html`
  and listen to the first heading. If the Spanish page is read to you in an
  English voice, fix the setting first; every Spanish row below would otherwise
  record a finding about your configuration rather than about the page.

**Reflow rig.** Either a 1280 CSS pixel wide window at 400% browser zoom, or a
responsive-design viewport set to 320 x 256 CSS pixels. Both give the 320 CSS
pixels WCAG 2.2 SC 1.4.10 asks for. Do the phone pass on a real phone as well:
a desktop browser at 320 pixels is not a touch target.

**A note on what 1.4.10 actually requires.** The data tables are the reason
this project has a reflow question at all, and SC 1.4.10 explicitly excepts
"parts of the content which require two-dimensional layout for usage or
meaning" -- a data table is such a part. So a table that scrolls sideways
inside its region is not automatically a failure of 1.4.10. The question this
walkthrough answers is the harder one: whether everything *around* the table
reflows to one column, whether the scrolling region can be reached and operated
without a mouse, whether a screen reader says it is there, and whether reading
a seven-column row on a phone is something a person can actually do. Record
what you observe, not what the rule text permits.

**Do not fix as you go.** File what you find, keep the row's cell honest, and
walk the rest. A walkthrough that turns into a refactor stops being a
walkthrough.

## How to record what you find

For each row of [the record](#the-record):

1. Replace UNMET with PASS or FAIL for that check.
2. Fill in the date (ISO, `YYYY-MM-DD`) and the name of the person who walked
   it. A row that claims a result without both is rejected by
   `tests/test_accessibility_review.py`: the record cannot say a walk happened
   without saying who did it and when.
3. Put every finding in the Findings cell as a link to an issue, one per
   finding. FAIL with no issue is a note nobody will act on.
4. Leave every row you did not walk at UNMET. A partial walkthrough recorded as
   a partial walkthrough is the point.
5. While any cell reads UNMET, README.md, `docs/ROADMAP.md`,
   `docs/RESPONSIBLE-TECH-AUDITS.md` §E and RR-05 must keep saying so. The test
   holds all four to it, so the record and the prose cannot drift apart the way
   the deployment claim did in 2026-08 (`tests/test_published_site.py`,
   "documents describing the surface").

Every check below is written as a step, then what a pass looks like, then what a
failure looks like. Where a step names a success criterion, that is the
criterion the finding should cite.

## Every page: the four checks that repeat

Run these on every page type. The page-type sections that follow add what is
particular to that page, and do not repeat these.

1. **Reach the skip link (SC 2.4.1).** Load the page, put focus in the address
   bar, press Tab once.
   - Pass: the first stop is a visible link reading "Skip to the main content"
     ("Saltar al contenido principal" on a Spanish page), which was off-screen a
     moment ago and is now on it. Enter moves focus into `<main id="main">`, and
     the next Tab continues from inside the main content rather than from the
     top of the page.
   - Failure: nothing appears (the link is `left: -9999px` and its `:focus`
     rule did not fire), or it appears under the header, or Enter scrolls the
     page but leaves focus behind so the next Tab returns to the header.

2. **Walk the whole page with Tab (SC 2.1.1, 2.1.2, 2.4.3).** Tab from the top
   to the footer, then Shift+Tab back up.
   - Pass: every link and control is reachable, the order follows the reading
     order, and Shift+Tab retraces the same stops in reverse.
   - Failure: a stop you cannot leave with Tab or Shift+Tab (a trap), a stop
     that never arrives, or an order that jumps between columns or sections.

3. **Watch the focus ring (SC 2.4.7, 2.4.11).** Same pass, watching rather than
   listening. The site sets one rule, `:focus-visible { outline: 3px solid
   var(--accent); outline-offset: 2px; }`, over the light and dark palettes.
   - Pass: every stop shows the ring, the ring is against a surface you can see
     it on in both themes, and no sticky header or footer covers the focused
     element.
   - Failure: a stop with no visible ring, a ring that vanishes into its
     background in dark mode, or a focused element scrolled under something.
     Check both themes; the OS setting decides which palette the page paints.

4. **Reflow (SC 1.4.4, 1.4.10).** Take the page to 320 CSS pixels, then to 400%
   zoom on a 1280 pixel window, then open it on a real phone.
   - Pass: text reflows to one column, nothing is clipped, nothing needs
     horizontal scrolling except inside a table's own region, and text at 200%
     is still readable without loss of function.
   - Failure: two-dimensional scrolling of the page itself, overlapping text,
     content cut off at the viewport edge, or a control that has moved off
     screen and cannot be reached.

## Landing page

`site/index.html`. One document, both languages, no language switcher: the
English half and the Spanish half sit in the same page as two sections, with
`<html lang="en">` at the root and `lang="es"` on the Spanish section.

1. **The language of the parts (SC 3.1.1, 3.1.2).** With the screen reader on,
   read from the top through the English county list and into the Spanish
   section.
   - Pass: the Spanish section is announced with a Spanish voice from its
     heading onward, and returns to English if you continue past it.
   - Failure: the Spanish half is read with English phonemes -- the failure
     this whole gate is most likely to find, and the one automation cannot see,
     since the markup is correct either way.

2. **Finding the Spanish half at all.** Read the page as a Spanish speaker
   would: from the top, with no sight of the layout.
   - Pass: a Spanish reader learns within the first screen or the first few
     headings that a Spanish version of this list exists below, and can jump to
     it by heading navigation.
   - Failure: the Spanish reader has to hear the entire English list of 58
     counties before reaching anything in Spanish. Record this even though no
     success criterion is failed by it: this is now the only page type on the
     site with no language link -- the school, ask, county and district pages
     all carry one -- and whether holding both languages in one document
     instead is usable is a judgment this walkthrough is here to make.

3. **The county lists by heading and by link (SC 1.3.1, 2.4.6).** Pull up the
   screen reader's heading list, then its links list.
   - Pass: two headings, one per language, each naming its language's list; the
     links list reads as county names a person can pick from.
   - Failure: headings that do not say which language they open, or a links
     list of 116 entries in which the two languages are indistinguishable.

## County page

`site/county/01.en.html` and `site/county/01.es.html`.

1. **The breadcrumb and the list (SC 1.3.1, 2.4.3).** Tab through: breadcrumb
   ("All counties" / "Todos los condados"), then the district links.
   - Pass: the breadcrumb is the first stop in the main content, and the
     district list reads as a list with a count.
   - Failure: the breadcrumb reads as an unlabelled link, or the list is
     announced as loose links with no list semantics.

2. **The proper name inside the Spanish heading (SC 3.1.2).** On the Spanish
   page the `<h1>` is `Condado de <span lang="en">Alameda</span>`, and the
   breadcrumb on a district page is `En el condado de
   <span lang="en">Alameda</span>`: the `lang="en"` marking covers the
   CDE-published proper name and nothing around it. It was wrapped around the
   whole Spanish phrase until 2026-09-05, which is a fault this walkthrough was
   what found -- by reading the committed markup -- and which was fixed before
   the walkthrough itself was run. What no reading of the markup settles is how
   the corrected version sounds, which is the check here.
   - Pass: the article and the preposition are announced in Spanish and only
     the name is handed to the English voice, without a jarring break where the
     voice changes.
   - Failure: "Condado de Alameda" announced entirely with English phonemes
     (the marking has grown back), or a voice switch mid-phrase so abrupt that
     the name is harder to make out than it would have been unmarked.

3. **Getting to the other language (SC 3.1.2).** Reach `01.es.html` from
   `01.en.html`. As committed there is one visible switcher link plus the
   `hreflang` alternates in the head; the browse pages carried neither until
   2026-09-05.
   - Pass: the link is reachable by keyboard, its accessible name says which
     language it goes to, and it is marked in the language it goes to, so a
     Spanish reader hears "Espanol" in a Spanish voice.
   - Failure: the link is announced in the page's own language rather than the
     one it leads to, or its name is a bare language code, or it cannot be
     found without sight of the layout.

## District page

`site/district/0110017.en.html` and `site/district/0110017.es.html`. The same
shape as a county page, with schools instead of districts, and one difference
that matters: the longest of these lists 994 schools.

1. **A long list by keyboard (SC 2.1.1, 2.4.3).** Walk the largest district
   (`site/district/1964733.en.html`, Los Angeles Unified, 994 schools on the
   page as committed) with Tab alone.
   - Pass: you can leave the list without Tabbing through every school -- by
     heading navigation, by the browser's find, or by the skip link.
   - Failure: the only way past the list is 994 Tab presses.

2. **The list read aloud (SC 1.3.1).** Listen to the start of the school list.
   - Pass: the screen reader states the list and its item count before the
     first school, so a reader knows how long it is.
   - Failure: schools arrive one after another with no idea how many are
     coming.

3. **The same proper-name check as the county page.** The `<h1>` is the
   district's CDE-published English name, and the Spanish breadcrumb marks only
   the county name inside it as English.
   - Pass: the Spanish breadcrumb is read in Spanish; the district and school
     names, which really are English, are read as English.
   - Failure: either one read in the other's phonemes.

## School page

`site/57726786056246.en.html` and `site/57726786056246.es.html`. Ten data
tables, each seven columns wide, each inside `<section class="scroll"
tabindex="0" aria-label="...">`. This is the page the product is, and the
hardest thing on the site to get right.

1. **The four cell states by voice alone (SC 1.4.1, 1.3.1).** Read the
   "Students by group" and "Chronic absenteeism" tables cell by cell with the
   screen reader's table navigation. Birch Lane carries all four states.
   - Pass: a published number, a published zero ("reported as zero" /
     "informado como cero"), a withheld figure ("withheld to protect privacy" /
     "retenido para proteger la privacidad") and an unpublished figure ("no
     figure published" / "sin dato publicado") are four distinguishable
     announcements, each with its row and column header attached.
   - Failure: any two of them sound the same, or a withheld cell is announced
     as a bare number, or a state word arrives with no header so the listener
     cannot tell which figure it belongs to. This is the single most important
     line in this document: the entire suppression design rests on those four
     being distinguishable, and a screen reader that blurs them republishes a
     withheld cell as a zero in the reader's ear.

2. **The scrolling region by keyboard (SC 2.1.1, 1.4.10).** Tab to a table's
   region -- it is focusable on purpose -- and try the arrow keys.
   - Pass: the region takes focus, shows the focus ring, and Left/Right scroll
     it so the district, state and coverage columns can be reached without a
     mouse or a trackpad gesture.
   - Failure: the region takes focus and arrow keys do nothing, or the region
     scrolls but the ring is invisible, or you cannot tell you are inside a
     scrollable thing at all.

3. **The region's own label (SC 1.3.1, 4.1.2).** Listen as focus enters the
   region.
   - Pass: the region is announced with a label that tells you what table you
     have arrived at, once.
   - Failure: the label and the table's `<caption>` are the same sentence and
     you hear it twice in a row -- they are byte-identical in the committed
     markup, which is a plausible double-announcement no automated rule
     objects to. On the Spanish page also listen to the school name inside
     that label: an `aria-label` is a flat string and cannot carry `lang="en"`,
     so "Birch Lane Elementary" is announced there with whatever voice the
     surrounding Spanish sets, while the same name in the body is marked.

4. **Table semantics (SC 1.3.1).** Move by column and by row inside a table.
   - Pass: every data cell announces its row header (the grade, the group) and
     its column header ("At this school", "In this district", "In California",
     and the three coverage counts); `scope` is on every header and
     `html-validate` requires it, but only listening proves it lands.
   - Failure: a cell read as a naked number, or the coverage columns read as
     though they were about this school. Those last three columns count all
     10,534 schools, and the page says so in a note after the table -- listen
     for whether the note arrives before a reader could misread the row.

5. **Reading a seven-column row at 320 CSS pixels.** With the reflow rig and
   then on a phone, find one school figure and its state comparison in the same
   row.
   - Pass: possible, and it does not require remembering the header while
     scrolling sideways past four columns.
   - Failure: it does. Say so plainly; this is the finding the design has been
     waiting on since M4, and the tables have deliberately not been widened
     past seven columns while it is open.

6. **The "How to read this page" legend (SC 1.3.1).** Read it before the
   tables, as a first-time reader would.
   - Pass: the four cell states are explained by voice before the first table
     arrives, and the words match what the cells announce.
   - Failure: the legend's wording and the cells' wording differ, so hearing a
     state in a table does not connect to the explanation.

## Ask page

`site/ask/57726786056246.en.html` and `site/ask/57726786056246.es.html`. The
only page on the site with a script (ADR 0003), so it is the only one with a
control that changes the page after load. A headless measurement recorded in
issue #6 walked the live English page in Chromium and found five keyboard stops
in document order, a computed focus ring on each, focus moving to the answer
heading when an answer landed, and axe clean over the answered DOM. That was a
machine reading a DOM; not one of the steps below is answered by it, and the
comment recording it says so itself.

1. **The form by keyboard (SC 2.1.1, 3.3.2, 2.4.3).** Tab from the top: skip
   link, language link, back-to-school link, textarea, Ask button. Type a
   question and submit with Enter from the button.
   - Pass: the textarea is announced with its label ("Your question" / "Su
     pregunta"), the button's name is its visible text, and submitting needs no
     mouse.
   - Failure: an unlabelled textarea, a control you can reach only by pointer,
     or a submit that requires a click.

2. **The answer's arrival (SC 4.1.3).** Submit a real question and listen
   without touching the keyboard. The answer region is `aria-live="polite"`.
   - Pass: the answer is announced once, after the sentence in progress, and
     the reader is told an answer arrived before hearing it.
   - Failure: silence (the live region did not fire), a double announcement, or
     an unbroken run-on of the whole answer with its labels and citations that
     cannot be paused or re-read.

3. **Where focus goes (SC 2.4.3, 2.4.7).** Same submission, watching focus.
   - Pass: focus lands on the "Answer" heading, so a keyboard reader continues
     from the result rather than from the button, and the heading shows a
     focus ring.
   - Failure: focus stays on the button, or moves somewhere with no visible
     ring, or moves before the answer is there.

4. **The labels before the answer (SC 1.3.1).** In reading order, the "What
   this is" note says the answer is written by an AI model, is unofficial, is
   not a ranking, and is not reviewed by a person.
   - Pass: a screen-reader reader hears all four of those before the first
     model sentence.
   - Failure: the answer is announced first and the labels are somewhere a
     reader may never reach. The labels exist to be read first; if the live
     region jumps the queue, that is a finding.

5. **The citations as a links list (SC 2.4.4, 2.4.9).** After an answer, open
   the screen reader's links list.
   - Pass: each "Checked against ..." link says which figure it checked, and
     the six of them are told apart by voice.
   - Failure: six near-identical link texts in a row, or links whose text does
     not say where they go.

6. **The refusal (SC 4.1.3).** Ask something the service must refuse -- a
   ranking question ("Is this a good school?") or a question about a withheld
   figure.
   - Pass: the refusal is announced as an answer, in the reader's language, and
     does not sound like an error or a failure of the page.
   - Failure: it reads as a browser or network error, or arrives in the wrong
     language.

7. **The form at 320 CSS pixels.** Reflow rig, then a real phone.
   - Pass: label, textarea and button stay in one column, the button is a
     comfortable touch target, and the answer is readable without horizontal
     scrolling.
   - Failure: any of those is not true.

## The record

Nothing below has been walked. Every cell is UNMET, no row carries a date, and
no row carries a name, because no walkthrough has taken place. That is the
honest state of this gate as of the day this document was committed, and it is
what `tests/test_accessibility_review.py` holds the rest of the repository to.

Keyboard covers SC 2.1.1, 2.1.2, 2.4.1, 2.4.3, 2.4.7 and 2.4.11. Screen reader
covers SC 1.3.1, 1.4.1, 3.1.1, 3.1.2, 4.1.2 and 4.1.3. Reflow covers SC 1.4.4
and 1.4.10 at 320 CSS pixels and 400% zoom.

| Page type | Language | Keyboard | Screen reader | Reflow | Date walked | Walked by | Findings |
|---|---|---|---|---|---|---|---|
| Landing page | English (`en`) | UNMET | UNMET | UNMET | — | — | — |
| Landing page | Spanish (`es`) | UNMET | UNMET | UNMET | — | — | — |
| County page | English (`en`) | UNMET | UNMET | UNMET | — | — | — |
| County page | Spanish (`es`) | UNMET | UNMET | UNMET | — | — | — |
| District page | English (`en`) | UNMET | UNMET | UNMET | — | — | — |
| District page | Spanish (`es`) | UNMET | UNMET | UNMET | — | — | — |
| School page | English (`en`) | UNMET | UNMET | UNMET | — | — | — |
| School page | Spanish (`es`) | UNMET | UNMET | UNMET | — | — | — |
| Ask page | English (`en`) | UNMET | UNMET | UNMET | — | — | — |
| Ask page | Spanish (`es`) | UNMET | UNMET | UNMET | — | — | — |

## When the record is full

A completed walkthrough is a dated artifact, and it changes three things beyond
this table.

1. RR-05 in `docs/audits/residual-risk-register.md` moves from Track to Closed
   only if every row passed. A row that failed is a finding with an issue, and
   RR-05 stays open, pointing at it.
2. `docs/RESPONSIBLE-TECH-AUDITS.md` §E records the date, the assistive
   technologies used, and what was found -- including nothing, if nothing was.
3. README.md's Standards Conformance row stops saying the review half is open.

Re-walk on any change to the page shell, the table markup, the focus styles, or
the ask page's script, and on each release: A11Y-11 and A11Y-12 are per-release
controls, and a record dated once is a record about one version of the pages.
