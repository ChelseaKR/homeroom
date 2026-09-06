# Changelog

All notable changes to homeroom are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **`make publish` deleted the site being served before it knew whether the
  replacement could be deployed** (2026-09-06). The recipe opened with
  `rm -rf site` and then spent about a quarter of an hour rendering into the
  hole it had just made, so the one irreversible step ran first and nothing
  between it and the closing "commit it to deploy" weighed the result. A publish
  over the 1 GB GitHub Pages ceiling therefore destroyed the working copy of a
  live site, reported success, and left the size to be discovered by a later
  `make verify` -- or, if nobody ran one, by GitHub refusing the artifact while
  every check in this repository stayed green and families kept receiving the
  tree that was last accepted.

  That is not hypothetical here. Issue #82 measured the next publish at
  ~1,051 MB: D5 on the school pages (ADR 0005) is 8,723 bytes across 21,068
  pages, 184 MB, and there is no reading of the sample under which it fits.
  Which of the three answers to that is taken -- move to the S3 origin prepared
  in #80, republish without `--assignments`, or take an existing section off the
  page -- is the owner's, and nothing here takes it.

  `publish` now renders into `build/publish-site/`, weighs that tree with
  `homeroom.publish_limits`, and moves it over `site/` only if it passes; a
  refusal names the ceiling, the budget, the measurement and where the bytes
  are, points at #82, and leaves `site/` untouched. The ceilings themselves
  moved into `src/homeroom/publish_limits.py` and
  `tests/test_published_limits.py` now imports them, so the number that refuses
  a publish and the number that fails the suite cannot drift apart. Weighing
  nothing is a refusal rather than a pass: an empty or missing staging tree
  raises rather than clearing a budget it never measured, which is the same
  floor `MINIMUM_FILES` and the `determinism` target's `-s` test already put
  under two other checks here. `tests/test_publish_budget.py` holds the recipe
  to the order -- the check before the `rm -rf`, and nothing writing into
  `site/` before the check -- because prose in a Makefile comment is not what
  stops this coming back.

- **The browse pages told a Spanish screen reader to read Spanish as English,
  and offered no way to the other language** (2026-09-05). Both shipped with the
  county and district pages earlier the same day and both land on Spanish-reading
  families first. The heading marked the whole phrase as CDE's English --
  `<span lang="en">Condado de Alameda</span>` -- when only `Alameda` is CDE's, so
  a screen reader was told to pronounce the article and the preposition with
  English phonemes. That is worse than not marking at all: the reader hears their
  own language read badly rather than a foreign name read plainly, and it is the
  exact WCAG 2.2 SC 3.1.2 failure the marking exists to prevent. `_named` now
  escapes the translated template and puts the marked name inside it, so the
  span covers the name and nothing else. Separately, every school page carries a
  link to itself in the other language and the browse pages carried none, so a
  reader who arrived at a county in the wrong language had no way across but the
  URL bar; they carry the same `hreflang` links and the same visible switcher
  now.

  Neither was visible to any automated gate. axe-core and html-validate both
  pass on the old markup: it is valid, the contrast is fine, and `lang` on the
  wrong span is a true statement about the wrong words. They were found by
  reading the committed markup while writing `docs/accessibility-walkthrough.md`,
  which is the argument for that document. `tests/test_browse.py` holds the
  marked spans to the names the directory file actually publishes, so a span one
  word too wide fails rather than shipping: reverting the fix reports
  `'Condado de Yolo' in {..., 'Yolo'}`.

### Added

- **A stdlib XLSX reader, written on its own before anything needs it**
  (2026-09-05). The M5 source survey found that D6, ESSA Per-Pupil Expenditure,
  publishes XLSX only -- no TXT, no CSV -- so the `csv.DictReader` every other
  parser in this project opens with has nothing to point at, and it named the
  consequence rather than absorbing it: reading that source needs `zipfile` plus
  `xml.etree` over the shared string table, which is inside ADR 0001's
  stdlib-only rule but is new surface, "worth naming before it is written rather
  than after". `src/homeroom/xlsx.py` is that surface, written by itself, so the
  file format is settled before any argument about per-pupil spending starts
  borrowing from it.

  **It reads a format and nothing else.** Bytes of an .xlsx in, rows of cells
  out. It does not know what `DNR` means, which columns hold dollars, that a
  header might sit on row 7, or that CDS codes exist. It converts nothing
  either: a numeric cell comes back as the digits the workbook holds, as text,
  because what a number *is* -- reported, suppressed, not reported -- is
  `parse_cell`'s decision about a data source, not a decision about a container
  format. A date comes back as the serial number Excel stored, unconverted, for
  the same reason. **D6 is still unacquired**: it is not in `data/raw/`, no
  access date exists for it, no number from it is published, nothing here
  fetches anything, and both M5 decisions -- whether a Dashboard band may be
  shown, and what number "per-pupil spending" would even be -- are still open.

  The hazard the module is built around is that XLSX omits what is empty. A row
  with values in the first and eleventh columns writes two `<c>` elements, not
  eleven, and a sheet whose data starts on row 7 writes no rows 1-6. A reader
  that takes a value's column from its position among the cells present rather
  than from its own `r` attribute shifts every value left, raises nothing while
  doing it, and produces a complete, plausible table of numbers filed under the
  wrong headings -- which for this project is the worst available failure. So
  the reader refuses to count: a `<row>` or `<c>` with no `r` attribute is an
  error, not an assumption, and `Row.values(width)` places cells by index and
  raises on one that falls outside the width the caller says it verified rather
  than dropping it to fit.

  Everything it will not do is a named error, following `DirectoryDriftError`
  and `parse_cell` rather than inventing a new posture: a missing sheet (naming
  the sheets the workbook does carry), a shared-string index that resolves to
  nothing, an unparseable cell reference, a cell whose reference names a
  different row than the one it sits in, two cells in one column, rows out of
  order, a workbook in the strict-OOXML namespace, and a cell type this reader
  has not been verified against. That last one includes `b`, `e` and `d`, which
  are real parts of the format: `#DIV/0!` read as the text `#DIV/0!` would be a
  spreadsheet error rendered as data, and a boolean read as `1` would be a
  number nobody published, so both stop rather than resolve.

  A zip is attacker-shaped input even when a state agency published it. The
  archive's declared uncompressed size and member count are checked before a
  byte is read, and then each part is streamed under a hard cap that does not
  consult what the zip header declared -- the shape `tools/verify_live_site.py`
  already uses for HTTP bodies. Rows and columns are bounded by the format's own
  limits, 1,048,576 and 16,384, so those bounds are not a number somebody chose.
  Parts are parsed incrementally and released as they go rather than read into
  one tree. And a part carrying a DTD is refused, because `xml.etree` expands
  internal general entities -- measured on this interpreter, not assumed -- and
  a spreadsheet part has no use for one, so closing that vector costs nothing
  and is what keeps the stdlib parser an honest choice rather than an accepted
  risk.

  `tests/test_xlsx.py` builds every fixture in the test with `zipfile` and
  hand-written XML instead of committing binary blobs, so each one states which
  hazard it encodes and a reader can check the claim without opening a
  spreadsheet. 59 tests over the shared string table (including a string split
  into runs by one bolded word, and a phonetic guide that is text *about* a
  string rather than part of it), inline strings, cells with no value, skipped
  cells and skipped rows, numbers held as text and as numbers, formula results,
  determinism, and every refusal above. The suite is 680 tests at 98.83% branch
  coverage, both re-measured rather than edited to fit; the module itself is at
  100%.

- **Teacher assignment monitoring is on the pages** (2026-09-05, ADR 0005). The
  owner decided issue #59: D5 is published. It had been acquired, schema-verified
  against the real 234MB 2023-24 file, joined to the spine and covered by tests
  since 2026-08-21, and deliberately shown to nobody, because publishing a figure
  about staffing at a named school is a different act from parsing one and the
  roadmap said so in as many words. `docs/adr/0005-publish-teacher-assignment-monitoring.md`
  records the decision, what is published, and the three hazards it was held open
  for: that "percent on a clear credential" is exactly the number a rater would
  sort 10,534 schools by, that a family could read a credential outcome as a
  verdict on the person teaching their child, and that the obvious one-line
  summary would be a value this project computed rather than copied.

  Each school page now carries CDE's own whole-school row in three tables: the
  total teaching FTE, the seven outcome FTE counts, and the seven outcome shares
  -- 15 measures, each beside its district and statewide figure read from the
  file's own aggregate rows, each with the coverage tally in the next three
  columns. All seven outcomes or none: there is no headline figure, because one
  number standing for seven is the compression ADR 0002 refuses. Counts and
  shares are both copied and neither is derived from the other, so a school whose
  share cell is withheld shows a withheld share even where its count is visible.
  `tests/test_pages.py` compares all fifteen cells, in order, against the
  measures the pipeline holds, which is what would fail if a share were ever
  divided out of a count.

  Three kinds of absence stay three different sentences. A build given no D5 file
  renders no section at all and says in words that the data is not here; a school
  the supplied file never mentions renders "no figure published" in every cell; a
  cell the state withheld renders "withheld to protect privacy". The first two
  are both `teacher_assignments is None` on the profile, and the assembly-level
  academic year is what tells them apart -- the same shape D3 already used, now
  written down in `SchoolProfile`'s docstring.

  District and statewide context needed a new loader, and this file crosses more
  dimensions than either of the two before it: charter status, DASS, grade span,
  experience level, credential level and subject area all have to read their
  aggregated value for a row to be the district's own. Five of the six are decoy
  slices that a reader filtering on aggregate level alone would publish as the
  district, which is the same defect D2's three charter rows once caused, and
  `load_assignment_context` fails closed on all of them -- no statewide row, or
  two rows for one entity, stops the build rather than publishing a slice.

  `make site-offline` is given the committed fixture, so the a11y and EN/ES gates
  read the new markup rather than stepping around it: 0 axe-core violations
  across 6 rule sets and 17 pages, 0 html-validate errors, byte-identical across
  two builds. `make data`, `make site` and `make publish` are given the acquired
  file, because an artifact that omitted a figure the pages carry would be two
  answers to one question. 19 new bilingual strings (217 keys per locale).

  What did not change: the ask layer. `homeroom.ask` answers from an evidence
  bundle that carries enrollment and chronic absenteeism, and widening it means
  new catalog entries, new verifier cases and a live evaluation run before any
  sentence about D5 reaches a reader. Its one refusal that described what it can
  answer as "the files behind this page" is reworded, because the page now covers
  more than the answer does and the sentence would otherwise have been false.

  Nothing under `site/` is republished here; that is a step the owner runs.

- **The one open accessibility gate now has a procedure and an empty record**
  (2026-09-05). **The walkthrough itself is still not done.** Nobody has used a
  keyboard or a screen reader on any page of this site, in either language, and
  nothing here changes that. What changes is that the gap stops living only in
  prose.

  Three documents said the same true thing and nothing else tracked it: README
  ("that walkthrough has not happened yet"), `docs/ROADMAP.md` §Scoping, and
  `docs/RESPONSIBLE-TECH-AUDITS.md` §E, which records it as REVIEW (not yet
  done) with an accountable owner and registers it as RR-05. A declaration with
  an owner, a risk-register row, and no procedure to follow is a commitment
  nobody can act on and nobody would notice going missing.

  `docs/accessibility-walkthrough.md` is what a person sits down with: which
  screen readers on which browsers (VoiceOver/Safari, NVDA/Firefox, VoiceOver
  on a real iPhone, JAWS and TalkBack if available), how to make the screen
  reader switch languages before starting -- without a Spanish voice and
  automatic language switching, the Spanish half of every row is a finding
  about the walker's configuration rather than about the page -- how to build
  the 320 CSS pixel and 400% zoom rig, and then, for each of the five page
  types this site publishes, the steps with what a pass looks like and what a
  failure looks like beside each one. All five: the landing page, the county
  and district pages added on 2026-09-05, the school page, and the ask page,
  which is the only page carrying a script. Both languages throughout, because
  Spanish is a launch requirement here and a screen reader announcing Spanish
  content with English phonemes is precisely the failure no headless gate can
  see.

  Reading the committed markup while writing it turned up three things. Two of
  them were faults and are already fixed, in the entry above this one: the
  `lang="en"` marking on the Spanish browse pages wrapped the Spanish words
  around a CDE-published proper name, and the browse pages carried no language
  link. Finding them by reading the markup is the argument for writing the
  procedure down, and the walkthrough now checks how the corrected markup
  *sounds*, which no reading of it settles. The third stands: each data table's
  scroll region carries an `aria-label` byte-identical to the table's own
  `<caption>`, a plausible double-announcement that is not a finding yet, and
  the landing page is now the only page type with no language link, which is a
  judgment the walk is there to make rather than a defect. They are markup
  facts with unknown audible consequences, which is what a walkthrough is for.

  The record is a results table, one row per page type per language: 5 x 2 = 10
  rows, every keyboard, screen-reader and reflow cell reading **UNMET**, no
  date and no name anywhere in it. It is meant to be obvious at a glance that
  nothing has been walked.

  `tests/test_accessibility_review.py` is what keeps it honest, in this repo's
  usual shape -- a claim in a document is checked by code. It derives the page
  types from the published tree rather than a list somebody has to remember to
  extend, so a sixth page type published without a walkthrough section fails
  the suite the way `county/` and `district/` were covered by no accessibility
  run at all until the day they were caught. It holds the record to a closed
  vocabulary, refuses a recorded result that carries no date and no name (a
  walkthrough is somebody's or it is not one), refuses a date beside an unwalked
  row, and, while any cell reads UNMET, requires README.md, `docs/ROADMAP.md`,
  `docs/RESPONSIBLE-TECH-AUDITS.md` §E and RR-05 each to keep saying so in
  their own words and each to point at the procedure. Deleting the procedure to
  make the repository look complete fails fourteen of its eighteen tests and
  leaves four documents citing a file that is not there.

  What it cannot check is whether somebody sat down and did it. No published
  byte proves a person used a screen reader, and a test that pretended
  otherwise would be worse than none. What is left possible is an outright lie
  across five files, which is a deliberate act rather than a quiet edit.

- **The two ceilings the published site sits under are measured by a build now**
  (2026-09-05). `site/` is committed and uploaded as it stands, so what GitHub
  Pages and the sitemap protocol will accept are limits on bytes in this
  repository rather than on anything a later build could adjust -- and nothing
  here measured either of them. Both were close enough to matter on the day they
  were first measured. `site/` is **867,639,523 bytes across 23,310 files, 86.8%
  of the 1 GB** GitHub allows a published site; `sitemap.xml` is **23,303 URLs
  and 1,821,378 bytes, 46.6%** of the protocol's 50,000-URL cap and 3.5% of its
  50 MB one. Neither figure existed a day earlier: the tree went 212 KB, then
  836 MB, then this, inside 2026-09-05, as all 10,534 schools were published and
  2,234 county and district pages went on top of them. (`du -sh site` says 856M
  for the same tree. That is allocated blocks, 23,310 files each rounded up to a
  4 KiB boundary; what the deploy uploads and what GitHub measures is the
  apparent size, and these gates read that.)

  Failure is silent in both cases, which is the argument for a gate rather than
  a sentence in the README. An artifact over the Pages limit is refused at
  deploy time: `make publish` succeeds, the diff reviews clean, every existing
  check stays green, and families keep receiving whatever was last served, or
  nothing. A sitemap over its caps is one a crawler may stop reading part-way
  down, and the symptom -- schools quietly absent from search results -- arrives
  months later attached to no error anywhere.

  `tests/test_published_limits.py` fails at 90% of each limit rather than at it,
  because a gate that fires only on a tree that is already undeployable reports
  what the deploy would have reported anyway. 10% of the Pages ceiling is about
  100 MB, or roughly 2,500 school pages at what they weigh now: room to notice,
  decide and republish while the site is still being served. Measured against
  today's tree that budget leaves **32 MB**, which is less than one new
  per-page section across 21,068 school pages -- and that is the finding rather
  than a badly chosen threshold. It is measured rather than supposed: rendering
  240 real pages with and without D5 puts that one section at 8,723 bytes a
  page, so the section ADR 0005 decided to publish costs 184 MB and carries the
  tree past the 1 GB ceiling itself, not merely past this budget (issue #82). The headroom was already load-bearing (ask
  pages for all 10,534 schools rather than two would be about 1.1 GB and do not
  fit), and it was written down only in README prose, where no build can read
  it.

  A third gate bounds a single published file at 8 MiB, which is half the 16 MiB
  `tools/verify_live_site.py` will read from the origin, and takes that number
  out of the tool rather than retyping it. Past the tool's bound the daily
  deployment check does not skip the file: it raises, and the run exits 4,
  "could not run". So one oversized file takes the whole live-site sentinel
  offline, and `sitemap.xml` -- the file here nearest to growing without a bound
  -- is in the spine that sentinel compares every morning rather than in the
  sample it rotates through. That also makes 16 MiB, not the protocol's 50 MB,
  the sitemap's effective byte ceiling in this repository. At the measured 78
  bytes an entry the URL cap still arrives first by a wide margin; both are
  checked because which one binds is a property of the addresses, which are CDS
  digits today and could be something longer tomorrow.

  Every failure names the limit, its source, the budget and the current
  measurement, and the size failure prints where the bytes are by area -- "(root)
  21,074 files, 848.1 MB; district/ 2,118 files, 17.8 MB; county/ 116 files,
  1.1 MB; ask/ 2 files, 0.0 MB" -- because "site/ is too big" is not something a
  reader can act on and "the district pages are 17.8 MB" is. A fifth check is
  the floor under the other four: a size budget over an empty directory passes
  having weighed nothing, which is the same vacuity `MINIMUM_FILES` refuses in
  `tools/verify_live_site.py` and the `-s` test refuses in the `determinism`
  target. `docs/ROADMAP.md`'s metrics ledger carries all of it as rows, beside
  this project's other automated gates.

- **Every published school page is walked to from the front door, in the tree
  that was actually published** (2026-09-05). `tests/test_landing.py` walks
  index to county to district to school, and has since the browse hierarchy
  landed this morning -- over a fixture build of three schools. Nothing walked
  the 23,310 files that were published. Between those two facts sits a whole
  class of failure with no check in it: a county or district page generated from
  the wrong slice of schools orphans thousands of pages at once, and every gate
  in `tests/test_published_site.py` passes on the result. The pages are all
  there, each one is valid, each carries its notices and its canonical, and no
  link is dead -- because being linked from *somewhere* was the property being
  checked, and being reachable from the *root* was not. A school that is
  published and unreachable is not published for a family.

  `test_every_published_school_page_is_reachable_from_the_front_door` walks the
  real tree in both languages: 58 counties, 1,059 districts and all 10,534
  schools per locale, with the reached set and the published set compared in
  both directions, so an orphaned page and a hierarchy naming a page that was
  never published are separate failures with separate messages. It costs 2.2s
  on a module that already parses the corpus once, because `pages()` carries
  each page's `hrefs` for the dead-link check and this walk is dictionary
  lookups over facts that are already in memory; nothing is read or parsed
  twice. Verified against a mutation rather than only against a green run:
  blanking one district page's links reports "16 of 10534 published en school
  pages cannot be reached from index.html by county and district", and blanking
  one county page's reports "county/01.en.html reaches no district page".

- **A hosting path that is not bounded by a 1 GB cap, prepared and not applied**
  (2026-09-05). `site/` is **857 MB** across **23,310 files** against the 1 GB
  GitHub Pages documents for a published site -- 84% of the cap, reached in one
  day from 212 KB that morning. The cap stopped being a background number and
  started deciding what this project may publish, which is the wrong thing to
  be deciding it.

  What it was deciding, measured rather than estimated. **D5 alone no longer
  fits.** ADR 0005 decided to publish teacher-assignment monitoring on the
  school pages; rendering 240 real pages with and without `--assignments` puts
  that section at 8,723 bytes each, so it is **+184 MB** over 21,068 school
  pages and takes the tree past 1 GB on its own, before anything else is added
  (issue #82). The ask layer for every school is 21,068 pages and the two
  published ask pages average 14,392 bytes, so it is a further **+303 MB**;
  857 MB plus 303 MB is 1.09 GiB and does not fit either. D4 and
  D6, when their two decisions are made, add measures to all 23,310 pages. And
  the one large saving on offer is not available: the ask page's inline CSS and
  script are **10,993 of its 14,206 bytes**, about 216 MB across the projected
  layer, and lifting them into shared files is two requests on load, which is
  precisely the thing `tools/ask-optin.mjs` loads each ask page in a DOM to
  prove does not happen. A saving that costs the guarantee is not a saving. So
  the host moves rather than the pages shrinking.

  `deploy/site/template.yaml` is the shape, in the form `deploy/ask/` already
  uses: a CloudFormation stack, parameterised, with the domain nowhere in it,
  and a README beside it recording what was applied, how to verify, and how to
  go back. A private S3 bucket -- all four public-access blocks,
  `BucketOwnerEnforced` so there are no ACLs to get wrong, encrypted, versioned
  with a 30-day expiry on superseded versions, `DeletionPolicy: Retain` so a
  `delete-stack` in the wrong terminal cannot take the bytes families are
  reading -- behind CloudFront with **Origin Access Control**, not the legacy
  OAI, whose grant cannot be narrowed to a single distribution ARN. HTTPS only,
  HTTP redirected, TLS 1.2 (2021) floor, compression on, `DefaultRootObject:
  index.html`, and a cache key of the path alone.

  It is two-phase for the same reason the ask stack is, and the phases are
  chosen so the origin can be built and proved before anything a family uses
  moves: `AttachDomain=false` builds it on CloudFront's own `*.cloudfront.net`
  name, which `tools/verify_live_site.py --url ... --sample 0` can then compare
  against all 23,310 published files while DNS still points at GitHub Pages;
  `AttachDomain=true` attaches the alias and the certificate. **The certificate
  must be in `us-east-1`** whatever region the rest of the stack is in --
  CloudFront reads ACM from nowhere else, and a certificate issued beside the
  bucket is a valid certificate CloudFront cannot see, failing at deploy time
  with a message about the ARN and nothing about regions. `CertificateArn`'s
  `AllowedPattern` refuses every other region, so that is checked rather than
  remembered, and the template and the README both say it in words for whoever
  the pattern refuses.

  Two details are load-bearing and would not survive being tidied away.

  A missing page stays missing: both `CustomErrorResponses` entries set only
  `ErrorCachingMinTTL: 10` and neither carries `ResponseCode` or
  `ResponsePagePath`, so a request for a school that is not published gets the
  origin's own 404 rather than a 200 carrying some other page's bytes. And the
  bucket policy grants `s3:ListBucket` alongside `s3:GetObject`, which looks
  redundant and is not: without it S3 answers a GET for a key that does not
  exist with **403 AccessDenied** rather than 404 -- it will not confirm
  absence to a caller who may not list -- CloudFront passes the 403 through,
  every real page is correct, and `tools/verify_live_site.py` exits 4 because
  `prove_the_origin_discriminates` refuses any origin that answers a
  guaranteed-missing path with anything but 404. CloudFront never issues a
  ListBucket request; the grant changes which of two error codes S3 returns.
  Both are pinned by tests that name the symptom.

  The publish path is `.github/workflows/site-publish.yml`, and it is a
  workflow rather than a `make` target for two reasons. `pages.yml` publishes
  only after ci concludes `success` on main, which is what makes "a commit that
  fails the accessibility, parity or published-site gates is never the one that
  reaches families" true; a command run by hand from a laptop cannot carry
  that. And a local target needs AWS credentials on a developer's machine,
  where a workflow needs a short-lived OIDC token minted per run -- the same
  keyless exchange `release.yml` already signs with. `workflow_dispatch` covers
  the one thing a target was wanted for, seeding the bucket before DNS moves,
  by running the same code rather than a second copy of it.

  What that path has to preserve is the property the whole project rests on:
  the bytes committed are the bytes served. Deletions propagate -- every sync
  pass carries `--delete`, whose filters apply to the bucket listing as well as
  the local tree, and a sixth pass excludes all five published kinds so it has
  nothing to upload and everything else to delete. Content-Type is stated
  rather than guessed, per kind, because the CLI's guess is right for `.html`,
  `.png`, `.xml` and `.txt` and gives the extensionless `CNAME`
  `binary/octet-stream`, which a browser offers to download. Neither is trusted
  afterwards: the workflow diffs the bucket's key listing against
  `find site -type f` and fails on a difference in either direction, and reads
  one object of each kind back with `head-object` to check its type. The six
  passes are written out rather than looped, because a shell `for` loop exits
  with only its last iteration's status -- the same reason `make secret-scan`
  runs its two scans as two commands.

  A republish invalidates `/*` and waits. `/*` is **one** invalidation path,
  and AWS gives 1,000 a month free; naming the 23,310 changed pages
  individually would be about **$111 per publish**. The wait is there because
  the next thing to read the origin is the live sentinel, and a comparison
  against an edge that has not turned over reports a difference that is not
  there.

  **Nothing is applied, and the workflow is inert as committed.** Its job is
  gated on four repository variables, none of which is set, so merging it
  creates nothing, publishes nothing, and cannot fail. `homeroom.chelseakr.com`
  is still a CNAME to `chelseakr.github.io` (`dig`, 2026-09-05) and
  `.github/workflows/pages.yml` is byte-for-byte unchanged and still the deploy
  families receive. Setting the four variables is step 3 of the cutover and
  moving DNS is step 7, and between them both origins receive every commit ci
  passes -- which is what makes the rollback a single DNS record rather than a
  redeployment.

  The rollback is written at the same length as the cutover, because the part
  that can go wrong is in it. GitHub renews the Pages certificate for the
  custom domain by checking that the domain points at GitHub; while it points
  at CloudFront that check fails and the certificate eventually lapses, and
  rolling back after that means HTTPS is down until re-provisioning finishes
  while `Strict-Transport-Security` denies any HTTP fallback. That is why
  `HstsMaxAgeSeconds` is a parameter, why the README says to deploy it at 300
  for the first weeks, and why `site/CNAME` -- inert on the new origin, since
  CloudFront reads its alias from the stack -- is kept rather than removed: it
  is what holds the custom domain configured in the Pages settings.

  `tools/verify_live_site.py` needs no change, and that was checked rather than
  assumed. It grades a domain and the domain does not move; the three things it
  requires of an origin are each provided deliberately (the 404 above,
  `DefaultRootObject` for the root comparison, and an identity-encoded response
  because CloudFront compresses only when the viewer asks for it, over objects
  stored uncompressed). One behaviour genuinely changes and is harmless: the
  `?live-integrity=<nonce>` it appends stops busting the cache, because the
  cache key is the path alone, and freshness after a publish comes from the
  invalidation the publish waits for.

  Cost, at this size and these rates: **about two cents a month** (0.808 GiB at
  $0.023/GB-month) plus about twelve cents per full republish (23,310 PUTs at
  $0.005/1,000), with serving inside CloudFront's always-free 1 TB and
  10,000,000 requests a month -- the daily sentinel is 9.37 MB and 210 requests.
  Reader traffic is not stated because it cannot be: GitHub Pages gives the
  owner no access log and this stack turns CloudFront logging off on purpose,
  since a viewer IP beside a school page's path is a record of which family
  looked at which named school. What is stated instead is headroom: a school
  page averages 40,163 bytes and carries no external asset, so the request cap
  binds first, at roughly 10 million page views a month.

  And the new ceiling, which is the thing the next person needs: there isn't
  one of the old kind. An S3 bucket has no limit on total size or object count.
  What is left is 5 TiB per object and 30 GB per CloudFront GET, against a
  largest published file of 1,821,378 bytes. **Cloudflare Pages was not an
  option** and not marginally: it caps a deployment at 20,000 files and the
  site is 23,310, exceeded by 3,310 before the question was asked, and no
  amount of shrinking pages changes a file count.

  34 tests in `tests/test_deploy_site_template.py`, in the shape
  `tests/test_deploy_template.py` holds the ask stack: each names the symptom
  it would catch. Three of them hold documents to reality rather than to
  intent, which is the habit the comment above `DOCS_DESCRIBING_THE_SURFACE`
  records the cost of learning -- the record may not carry a distribution id, a
  stack ARN, a certificate ARN, a role ARN, a `*.cloudfront.net` host or a
  named bucket while it says nothing is applied; it may only call GitHub Pages
  the live deploy while `pages.yml` still uploads `site/`; and its three
  headline measurements are re-derived from the published tree, so a republish
  that changes the tree and not the document fails rather than leaving three
  stale numbers that still read as measurements. The content-type check derives
  the kinds it demands from `site/` itself, so a page type arriving with a new
  extension fails here rather than being served as `binary/octet-stream`. All
  three of the sabotages tried -- dropping the `ListBucket` grant, dropping
  `CNAME`'s `--content-type`, and adding a distribution id to the record --
  fail the suite.

- **A front door you can find your school through** (2026-09-05). Publishing all
  10,534 schools left the landing page listing every one of them, twice, once
  per locale: 21,069 links in 2.45MB. That is not a front door, it is a wall of
  names, and a family looking for their own school had no way in but scrolling
  or their browser's find. The site is walked now the way a family already knows
  where it lives -- county, then district, then school -- and each step is its
  own page: `index.html` names the 58 counties, 116 county pages name the 1,059
  districts, and 2,118 district pages name the schools. The landing page is
  **15,936 bytes**, down from 2,451,038, and the longest list on the site is
  LAUSD's 995 schools, which is one real district rather than an arbitrary dump.
  A filter box would have been the obvious answer and is the one thing this site
  cannot ship: these pages carry no script and are gated on carrying none
  (ADR 0001), so the hierarchy is pages rather than a control.

  The addresses are the CDS code's own digits -- two of county, seven of
  district, which is already how `context.district_key` finds a school's
  district -- so no name becomes a slug and two districts sharing a name stay
  two districts. `site/` grew 836MB to 855MB, still inside the 1GB GitHub Pages
  allows.

  Three gates covered the new pages with nothing, each found by building them:
  `tools/a11y.mjs` reads one directory and does not recurse, so `county/` and
  `district/` needed their own runs in `make a11y` (the ledger's page count goes
  13 to 17); `published_url` in `tests/test_published_site.py` built an address
  from a file's name alone, which for a county page is `/01.en.html` and is not
  an address anything serves; and the live sentinel's spine/rotate split keys on
  a name with no directory in it, so all 2,234 browse pages would have sat in
  the spine and been fetched every morning -- passing, slowly, at the origin's
  expense. `test_no_school_page_carries_a_script_or_reaches_off_the_page` now
  reads every indexable page rather than a list of page types somebody has to
  remember to extend.

  The landing test that asserted every school was linked is a walk now:
  index to county to district to school, in both languages, because a school
  that is published and unreachable is not published for a family.

- **Every active school is published; the ask layer stays where it was**
  (2026-09-05).
  The site served one school from 2026-08-22 to now: Birch Lane Elementary, the
  M4 school, out of the 10,534 the pipeline has profiled since M3a. Publishing
  the rest was never a technical step -- `--cds` has always accepted "omit to
  render every school" -- it was the decision about which schools to put in
  front of families, and it has now been made the same way the first one was, by
  a person. `site/` holds 21,069 school pages, English and Spanish for all 10,534
  active schools, plus the landing page, sitemap, robots.txt and both cards.
  `make publish` renders them in 42s.

  The ask layer did not widen with them, and `make publish` is two passes so that
  it did not have to. Pass 1 renders every school in `SCHOOLS` (empty, meaning
  all) with no endpoint, so no page carries an ask link. Pass 2 renders
  `ASK_SCHOOLS` again with the endpoint and contributes exactly two things: the
  ask pages, and those schools' school pages, which are pass 1's bytes plus the
  one link line. Pass 2's own index, sitemap, robots and cards describe a site of
  `ASK_SCHOOLS` alone and are discarded with the stage directory. Keeping the ask
  layer at two pages is a decision about an approved spend envelope -- the service
  calls a paid model per question and a CloudWatch alarm watches daily
  invocations against it -- rather than a consequence of how many schools
  California has. A school page carrying an ask link with nothing behind it fails
  `test_no_published_link_points_at_a_page_that_was_not_published`, so the two
  halves cannot drift apart quietly.

  Two limits were measured rather than assumed, because both bound what can be
  published next. `site/` is 836 MB, against the 1 GB GitHub Pages allows a
  published site; ask pages for all 10,534 schools instead of two would be about
  1.1 GB, which does not fit. And 836 MB of near-identical HTML packs to about
  46 MB in git, so the repository grew by tens of megabytes rather than by the
  figure the working tree shows. README's Status section carried the old shape --
  "one school out of the 10,534 the pipeline profiles" -- and now carries this
  one, with the ratio it used to state recorded as what it said until 2026-09-05.

- **M5's two sources were surveyed against the real published files, and one of
  them was not where this repository said it was** (2026-09-05). D4 and D6 were
  the last two rows in PROVENANCE.md reading "Planned", which is a status that
  can hide either "not started" or "not possible", and nothing here had checked
  which. Both exist. D4 is nine files, not one: eight state-indicator files plus
  a Growth Model file, 153,581,873 bytes and 1,104,219 rows, sharing 22 columns
  and not a schema (17 to 109 columns each), one of which spells `changeLevel`
  where the other seven spell `changelevel`. It masks nothing with `*`;
  suppression is a blank cell, and `0` in `color`, `statuslevel`, `changelevel`
  and `box` is CDE's "No Color", not a value -- 55,651 of 114,225 chronic rows
  read `color` = 0, which a parser reading it as an integer would publish as a
  band. D6's recorded pointer, "SACS/LCFF public files", was aimed at
  district-level data: Current Expense of Education says on its own page that it
  is calculated at district level, SACS ships as Windows `.exe` archives for
  Microsoft Access, and the SARC file that is school-grained carries one distinct
  value in its per-pupil column -- 11146.18, the statewide figure, on all 10,274
  rows. The school-level source is CDE's ESSA Per-Pupil Expenditure workbook,
  10,065 school rows, whose sentinel is `DNR` rather than `*` and which publishes
  four per-pupil components and no total. Neither source is acquired: the files
  are not in `data/raw/`, no access date is recorded, and no number from either
  reaches an artifact or a page. PROVENANCE.md D4 and D6 carry the measurements,
  docs/ROADMAP.md gains an "M5 source survey" section, and PROVENANCE.md's rules
  now define *surveyed* as the weaker word it is.

- **Every figure the documents quote off `evals/results/` is now re-derived from
  it** (2026-08-29). `test_every_results_file_either_ran_with_provenance_or_says_not_run`
  holds each results file to the harness's own exit condition, which is the right
  check on the artifact. Nothing held the *documents* to it. README.md and
  docs/ROADMAP.md between them retype eleven numbers off that directory: the case
  total, five per-suite scores, the sentences shown, the sentences withheld, their
  sum, and the five-way account of why they were withheld. Not one was read back.
  The results cannot be regenerated by a gate -- the harness calls a hosted model
  over a bundle built from acquired files that are never in git -- but the results
  are committed and CI can read them, so every figure quoted *from* them costs
  nothing to check. That is the whole gap: a live run is not reproducible and a
  transcription of one is. Shape borrowed from
  `tests/test_i18n.py::test_the_key_count_the_documents_state_is_the_count_that_exists`:
  derive the figure, hold every document that states it to that figure, and fail
  if a document stops making the claim, so a number can never be quietly deleted
  instead of corrected. Nothing had drifted; all eleven re-derive exactly.

- **The showcase's second table is gated too** (2026-08-29). `SHOWCASE_ROW` needs
  four numeric columns and a percentage, so it never matched a row of the
  two-column "scale this matters at" table: 10,534, 9,718, 83 and 733 were parsed
  by nothing and checked by nothing, in a document every other figure in which is
  checked three ways. They are not free numbers. The same file's `TA` row publishes
  9,718 and 83, and 9,718 + 83 + 733 is the 10,534 the prose states, so the two
  tables state one set of counts twice and can only be right together. That is now
  asserted, along with a floor test so an unparsed table cannot pass as an
  agreeing one.

### Changed

- **The live sentinel compares a spine every run and rotates through the school
  pages** (2026-09-05). `tools/verify_live_site.py` fetched every published file,
  which was eight of them. Publishing all 10,534 schools made it 21,076, so the
  daily scheduled run would have pulled 836MB from the origin every morning,
  three times over on its retry loop, and taken hours to do it. Bounding a
  sentinel is the change most likely to turn it into nothing, so the split is by
  what the two halves can go wrong. Everything that is not a school page --
  index, sitemap, robots, CNAME, both cards, every ask page -- is compared on
  every run, and that is where a stale or failed deploy shows up first, because
  the index and the sitemap change whenever the site does. The school pages
  rotate: each run takes a window of 200 chosen by the UTC date, so consecutive
  days walk the corpus and every page is reached in about fifteen weeks. A run is
  210 requests instead of 21,078. `--sample 0` still compares all of them, which
  is the right thing to do by hand after a publish. `tests/test_live_sentinel.py`
  holds the part that could silently under-check: that the spine is always in,
  that consecutive windows do not overlap, that rotation reaches every page, that
  a same-day re-run repeats its window rather than wandering, and that a sample
  wider than the corpus is a full sweep rather than a wrapped and doubled one.

- **Every gate stage runs `uv run --locked`, never a bare `uv run`** (2026-08-29).
  A bare `uv run` performs an implicit sync: when `uv.lock` no longer agrees with
  `pyproject.toml` it rewrites the tracked lockfile in place and carries on.
  Measured here on 2026-08-29, with one dependency added to `pyproject.toml` and
  the lockfile left alone: `uv run ruff check .` printed "All checks passed!",
  exited 0, and moved `uv.lock` from sha256 `1c47f06e` to `4666a2e7`. The same
  command with `--locked` exits 2, names the drift, and leaves the lockfile at
  `1c47f06e`. The property that the gate did not silently repair its own
  precondition held only because `sync` happens to be listed first in
  `verify-ci`; `make lint` on its own did not have it.

### Fixed
- **The withheld-count check on the ask page was passing on the citation year**
  (2026-09-05). ADR 0003 promises that "the count of withheld claims is shown
  beside the answer" and the README's standards table repeats it. No test renders
  an answer, so `tools/ask-optin.mjs` was the only thing holding that promise, and
  what it held was `text.includes("2")` over the whole answer's text. The canned
  response's first citation carries `year: "2025-26"`, which the script renders
  into every answer, so the assertion was satisfied by the citation year on every
  render. Deleting the withheld paragraph from `askpage.py` outright left all six
  ask pages reporting `ok`.

  The count is now matched as the whole paragraph the script appends, against the
  page's own `ask_withheld_count` string with the response's count substituted --
  the same string the script builds, read out of the page's JSON block, so the
  assertion reads in Spanish as well as English with no English hardcoded in the
  checker. A digit elsewhere in the answer cannot satisfy it.

  Each page now renders three answers instead of one. The second carries a
  different count, so a number fixed in the script or baked into the locale string
  fails rather than passing on a coincidence; the third withheld nothing, and must
  render no count at all, which is the one case the paragraph is deliberately
  absent. All three sabotages were run: deleting the block, hardcoding the count,
  and dropping the `> 0` guard each fail all six pages, in both languages, with a
  message naming the count. Nothing else in the file was relaxed.
- **`docs/RESPONSIBLE-TECH-AUDITS.md` said it was regenerated, and it has no
  generator** (2026-08-29). The header read "Last regenerated: 2026-08-21" on a
  hand-authored file: a repository-wide search finds only readers, never a
  producer. The document's own third paragraph promises that "nothing below claims
  an audit that did not happen", and its header was claiming a regeneration that
  did not happen. It now reads "Last reviewed", which is what occurred.
- **The published site can say where it lives** (2026-08-28). Nothing rendered
  by `homeroom.site` had ever named an address, so
  `homeroom.chelseakr.com/robots.txt` and `/sitemap.xml` were both 404 and no
  page carried a canonical link or an OpenGraph tag. Nothing said which of the
  two addresses for the root page was the one to keep.
  - `--site-url` on `homeroom.site` takes the https origin the build will be
    served from and, given one, writes a self-referencing `<link rel="canonical">`
    and the OpenGraph and Twitter tags on every indexable page, plus
    `robots.txt` and `sitemap.xml`. Omitted, the output is byte-identical to a
    build before this existed, on the same reasoning as `--landing` and
    `--ask-endpoint`: a page cannot honestly claim a canonical address on a
    build nobody has said where to host.
  - The social tags repeat the page's own title and description rather than a
    second set written for a card, and there is deliberately no `og:image`:
    the site ships no image asset, and an `og:image` naming a file that is not
    there is worse than none at all.
  - The ask pages stay `noindex` and stay out of the sitemap. `robots.txt`
    disallows nothing, because a `Disallow` on those pages would stop a
    crawler fetching them and so stop it ever reading the `noindex`.
  - The origin is validated. `--site-url` refuses anything that is not a bare
    `https` origin, including plain `http` and a leftover project path; a
    mistyped origin does not fail loudly, it publishes a wrong address.
  - `make site-offline` now passes a reserved-TLD origin, so the fixture gates
    read the markup a hosted build ships without a fixture page claiming the
    real domain's addresses. `tests/test_published_site.py` checks the
    committed bytes: a canonical per page, robots and sitemap present, every
    sitemap URL resolving to a file that was published, and no `github.io` or
    plain `http` address anywhere. Each was demonstrated failing, by deleting
    the published file, by stripping the canonical from a page, and by removing
    the social tags from the renderer.

### Fixed
- **The committed tag ruleset was a lockout, and its own guard required it**
  (2026-08-29). `.github/rulesets/tags.json` is a tag ruleset with `update` and
  `deletion` over `refs/tags/v*`, and it carried `"bypass_actors": []`. Applied
  as committed, nobody -- the repository owner included -- could delete or
  re-point a release tag, including a bad one, and no break-glass path would
  remain to undo it with. GitHub answers 201 to such an apply, so nothing warns
  you; the same mistake elsewhere in this portfolio took a sweep across eighteen
  repositories to unwind.
  - Nothing live contradicted the file. As of 2026-08-29
    `gh api repos/ChelseaKR/homeroom/rulesets` returns `[]` and
    `repos/ChelseaKR/homeroom/branches/main/protection` returns 404 "Branch not
    protected", so the profile has been wrong unopposed: committed, never
    applied, and read by exactly one thing.
  - That one thing mandated the defect. `automation/check_release_ruleset.py`
    listed `("bypass_actors", [])` among the fields it required to be exact, and
    the signed release-tag message asserted `Tag-Ruleset-Bypass-Actors: empty`.
    Correcting the profile alone would have turned the build red, and correcting
    the guard alone would have left the profile wrong, so both moved together.
  - The profile now carries exactly
    `{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}`:
    the owner's standing bypass, admin, and `always` rather than
    `pull_request`. The guard expects that same one-element list, still by exact
    equality and not membership, so an empty list, an absent key, a non-list, a
    foreign actor, a second actor alongside the owner, and
    `bypass_mode: "pull_request"` all fail. This is a correction of what the
    guard points at, not a loosening of how hard it points. The signed tag
    message names the bypass it vouches for, derived from the same constant so
    the signature and the profile cannot drift apart.
  - `tests/test_release_ruleset.py` runs the shipped validator, not a copy of
    it, against each of those five losing shapes and against a correct profile
    as a positive control, so the check cannot pass by refusing everything. A
    missing file and a malformed file are both held to failure, through
    `load_ruleset` -- which returns errors rather than raising, and would
    otherwise hand a caller `None` to read as "nothing wrong" -- and again
    through `main`, so neither can be reported as valid anywhere in the chain.
  - Demonstrated failing five ways, each confirmed landed by a JSON parse rather
    than a grep: the empty list, a deleted file, a malformed file that still
    contains the literal string `bypass_actors` and the owner's actor id (a
    grep-based check passes exactly that shape; `grep -c` finds it and the parse
    refuses it), `bypass_mode: "pull_request"`, and reverting the guard's own
    constant to `[]` with the profile left correct, which fails seven tests.
  - CICD-15 and CI-CD-STANDARD §5.1 prescribe "empty bypass actors" and, where a
    bypass exists, `bypass_mode: "pull_request"`. That standard is not vendored
    here, so nothing upstream is rewritten; the divergence is declined on the
    record in the guard's docstring, in the test module, and as RR-11 in
    `docs/audits/residual-risk-register.md`. A bypass that works only inside a
    pull request is no use when the pull request is what is wedged, and a tag is
    neither updated nor deleted through one.
- **The most-suppressed group was the one the suppression story left out**
  (2026-08-29). This project's argument is that CDE's masking falls hardest on
  the smallest groups. The single most-withheld category in the acquired 2024-25
  file is `GX`, Non-binary: 55 published and 1,990 withheld of the 2,045 schools
  that report it at all, 97.3%. No document in the repository named it. README.md,
  docs/ROADMAP.md, CHANGELOG.md and `docs/SUPPRESSION-SHOWCASE.md` all called `RI`
  (American Indian or Alaska Native, 95.4%) the maximum, and RR-05 in the risk
  register said two categories exceed 94% when three do (`GX`, `RI`, `RP`).
  `GX` is a rendered subgroup, in `ABSENTEEISM_SUBGROUP_FAMILIES`' `gender` family
  and on Birch Lane's published page in both languages, so nothing about it was
  hidden from the pipeline; only from the prose.
  - The sentences now carry both figures and the difference between them. `GX`'s
    97.3% is over 2,045 schools, with 8,489 more carrying no Non-binary row at
    all; `RI`'s 95.4% is over 9,801, which is nearly every active school. Neither
    is the whole picture alone, and rounding one away would have been the easier
    edit.
  - The showcase table said "Among the 9,801 schools that publish any row for a
    given category", which was true of every row it happened to list and false of
    the file. Each row now carries its own denominator, and `SF` (Foster youth,
    7,312) is in the table as a second category the single denominator would have
    misdescribed.
  - `RD` read "79.7%" where 7,806 of 9,801 is 79.6449. Every other row rounded
    correctly.
  - `tests/test_suppression_claims.py` gates all of it, on the shape
    `tests/test_i18n.py` uses for the i18n key count: the showcase table is the
    committed record, its own arithmetic is checked, the maximum must be a code
    the pages actually render, every document stating the claim must name the
    same category and share, and a document that stops making the claim fails
    too. On a machine holding the acquired files it also checks the table against
    `data/out/coverage.json`. Demonstrated failing by restoring the 79.7%, by
    putting `RI`'s share back in the README, by deleting the `GX` row, and by
    setting the register back to two categories.
- **Four documents said no service was deployed, and one was** (2026-08-29). The
  ask service has been live since 2026-08-22: `deploy/ask/README.md` records the
  stack and Function URL, and the published pages under `site/ask/` carry the
  endpoint. `SECURITY.md`'s scope section said "There is no deployed service";
  `docs/audits/threat-model.md` said "no inbound network surface", "If deployed",
  and "no deployment exists"; `docs/RESPONSIBLE-TECH-AUDITS.md` §F said "No hosted
  service ... no inbound network surface"; the Makefile's `ASK_ENDPOINT` comment
  said nothing was deployed. The threat model and the audit file were edited on
  2026-08-28, six days after the deploy, and the denials survived the edit. A
  security document that understates the attack surface tells a reporter there is
  nothing there to look at.
  - Every one of them now describes the deployed service, and each says what it
    used to say rather than being quietly rewritten.
  - RR-07's precondition was "no deployment until the ranking-refusal and
    suppression suites have a live run recorded at zero on the model that would be
    deployed, and a person has read a sample of real answers in each language".
    The first half was met: `evals/results/global.anthropic.claude-sonnet-4-6/`
    records ranking_refusal 62 of 62 and suppression 24 of 24, dated 2026-08-22,
    on the model the stack invokes. The second was not, and still is not. That is
    recorded in RR-07 and in the audit file's REVIEW item rather than removed: the
    reading commitment is now an open obligation against a running service instead
    of a gate in front of one, which is a worse position and is why it is written
    down.
  - `tests/test_published_site.py` derives the deployment state from the published
    ask pages and the applied stack record, fails if any of those documents denies
    it, fails if one stops stating it, and fails if RR-07's reading commitment or
    the "Nobody has." admission is deleted. Quoted text is exempt, because
    correcting a sentence here means quoting it. Demonstrated failing by putting
    the SECURITY.md denial back, by deleting the RR-07 commitment, and by softening
    "Nobody has." to "This is planned."
- **CONTRIBUTING.md still promised a gate identical to CI** (2026-08-29). It said
  `make verify` "is byte-for-byte identical to the `verify` job in
  `.github/workflows/ci.yml`". The Makefile retracted exactly that on 2026-08-28
  and AGENTS.md now says "a strict superset ... never the reverse"; this file was
  missed in that pass. `make verify` is `verify-ci` plus the working-tree secret
  scan, and CI runs `verify-ci`.
- **The CI parity gate could not see two thirds of the workflow** (2026-08-29).
  README.md said "Every step in `.github/workflows/ci.yml` is a `make` target",
  and `tests/test_ci_parity.py` checked it by matching `run:` lines. Eight of
  ci.yml's eleven steps are `uses:` steps, and the whole `secret-scan` job is one
  of them: it runs no command, so the gate saw an empty job and passed. The gate
  is widened rather than the sentence narrowed. Every `uses:` step must now be
  either a setup or reporting action named in `SETUP_AND_REPORTING` or a gating
  action registered in `GATING_ACTIONS` against the make target that reproduces
  it, and every job must reach at least one target `verify` reaches. Demonstrated
  failing by adding an unregistered scanner action, and again by adding a job whose
  only step is a checkout.
- **`0.1.0` was dated as a release that was never cut** (2026-08-29).
  `CITATION.cff` carried `date-released: "2026-08-18"` and CHANGELOG.md opened a
  section dated 2026-08-18 and headed "First tagged release". This repository has
  no tag and
  has published no release. Following olive-bark-logger, `date-released` is
  omitted with the reason written in the file, the heading says what it is, and
  `tests/test_release_metadata.py` holds `CITATION.cff`'s version to
  `pyproject.toml`'s and refuses a dated heading while no release date is claimed.
  Demonstrated failing by restoring each of the two.
- **"CI never touches the network" was an absolute the gate does not keep**
  (2026-08-29). README.md (twice), PROVENANCE.md, docs/ROADMAP.md and the Makefile
  all stated it. `make verify-ci` reaches a package index or an advisory database
  at `uv sync`, `npm ci`, `pip-audit`, `npm audit`, and the pinned `uvx` runs of
  semgrep and zizmor. The intent was already stated correctly in the README's Data
  Governance row: what never crosses the network is the data. Every instance now
  says that instead.
- **Smaller claims that were not true** (2026-08-29).
  - `docs/ROADMAP.md` said the accessibility gate checks 6 pages. `make a11y` runs
    `tools/a11y.mjs` over two directories and the checker does not recurse, so it
    reads 13: six school pages and the landing page, plus six ask pages. Gated in
    `tests/test_pages.py`, which derives the count from the fixture schools, the
    locales, and the Makefile's own recipe.
  - `docs/ROADMAP.md` said counting districts by name loses eleven because "ten
    names cover two districts each, and 'Jefferson Elementary' covers three",
    which is twelve. Ten names cover more than one district, nine of them two and
    Jefferson three. README.md already had this right.
  - `docs/ROADMAP.md` said all four cell states are present in Birch Lane's
    chronic-absenteeism section. Three are; the fourth, a published zero, is on
    the same page in the grade-span table.
  - README.md said the landing page states that one school of 10,534 is published.
    It does not print that ratio; it says Homeroom is in development and that the
    listed schools are the ones published so far.
  - README.md listed "a daily cap of 400 model calls" among the applied envelope
    without the qualifier `deploy/ask/template.yaml` carries: the cap is per warm
    container, which RR-09 already recorded as open.
  - README.md said semgrep runs "over the whole tree". `.semgrepignore` excludes
    vendored, generated and built output, including `site/`, which is the
    directory actually served; `tests/test_published_site.py` is what gates those
    bytes.
- **`make verify` was green on trees CI rejects** (2026-08-28). `AGENTS.md` said
  "`make verify` is the gate, byte-for-byte identical to CI" and the Makefile
  said the two "MUST stay byte-for-byte identical". CI ran three jobs and
  `make verify` covered one. `secret-scan`, `sast`, and the twice-build
  determinism check existed only as steps inside
  `.github/workflows/ci.yml`, with no target to run them by, so nobody could
  run the gate the documentation described.
  - Every CI stage is now a `make` target, `verify` reaches all of them, and
    every step in `ci.yml` that runs a command invokes one. CI calls
    `make verify-ci`; `make verify`
    is that plus the working-tree secret pass, so the local gate is a strict
    superset and green locally implies green in CI. The one asymmetry is
    deliberate: `gitleaks` is not on the runner image, putting it there means a
    pinned download or a container to keep verifying, and the pass it adds finds
    uncommitted files, of which CI has none. `tests/test_ci_parity.py` checks those
    three facts by reading the workflow, so a stage added to CI as inline
    script fails the build that adds it. Demonstrated failing by adding a
    CI-only `run: echo` step, and again by removing `sast` from `verify`'s
    prerequisites.
  - **The determinism check could pass having hashed nothing.** It wrote two
    `find | xargs shasum` files and diffed them; over an empty directory that
    is two empty files and a successful diff. Confirmed by running the old
    command pair against an empty tree: exit 0. The target now fails if the
    first hash file is empty, and prints how many files it compared.
  - **The secret scan could not see an uncommitted key.** `gitleaks` in history
    mode reads commits, not the working tree. Confirmed on this repository with
    a high-entropy GitHub token in an untracked file: history mode reported
    "68 commits scanned, no leaks found" and exited 0. `make secret-scan` keeps
    that pass and adds a working-tree pass, which exits 1 on the same file. The
    working-tree pass is scoped to what `git ls-files -co --exclude-standard`
    lists, which is where an uncommitted key lives and which keeps the scan off
    `node_modules/` and `.venv/`: 1.3 MB in 0.3 s rather than 577 MB in 72 s.
    The two passes are two commands with two exit statuses, not a `for` loop,
    which would report only its last iteration's.
  - **Semgrep silently skipped every test.** Its built-in ignore list drops
    `tests/`, so a job whose stated scope was the whole repository read 30 of
    55 tracked Python files and said so only as "Files matching .semgrepignore
    patterns: 25". A repository-root `.semgrepignore` replaces that list;
    scope is now 55 of 55, still 0 findings. This project's tests are gates,
    not scratch code.
  - **zizmor was cited as a control in three documents and existed nowhere.**
    `docs/audits/threat-model.md` named it twice, once for `uses:` pinning and
    once as the "gate on permissions creep", and `docs/ROADMAP.md`'s metrics
    ledger named it as the measurement for 100% SHA-pinned actions. It was not
    in the Makefile, the workflows, or the dependencies. It runs now, pinned,
    in `make workflow-audit`.
    - Its default configuration could not have backed the claim it was cited
      for: `unpinned-uses` accepts a tag by default, so `actions/setup-node@v7`
      passes it. Verified by unpinning that action and watching the default
      configuration report clean. `.github/zizmor.yml` sets the `hash-pin`
      policy; with it, the same unpinned action is a High finding and the gate
      exits 14.
    - One finding is ignored: `dangerous-triggers` on `pages.yml`'s
      `workflow_run`. The reasoning is written at the line it applies to, and
      it is the only suppression.

- **The gate over the bytes served at homeroom.chelseakr.com could vanish
  silently.** `tests/test_published_site.py` opened with
  `pytestmark = pytest.mark.skipif(not SITE.is_dir(), ...)`, on the reading that
  a checkout with nothing published has nothing to check. That is not what this
  repository is: `site/` is committed, it is what GitHub Pages serves, and
  `make publish` begins with `rm -rf $(PUBLISH_DIR)`. So a missing `site/` means
  an interrupted publish or a bad merge -- exactly the tree whose published
  bytes most need checking -- and the whole module went green over it.
  Confirmed by hiding `site/` and running the old file: **10 skipped, exit 0**.
  The same tree now fails 6 of 11, starting with a floor that says what is
  missing and how to restore it.

### Changed
- `RR-02`'s mitigation text said dependencies are installed `--frozen`; the
  Makefile has run `--locked` since 2026-08-26. `docs/audits/threat-model.md`
  carried the same stale word and is corrected too.
- The README's Accessibility conformance row named only the automated half of
  the gate. It now names the open review half -- the keyboard and screen-reader
  walkthrough and the 320px reflow check -- and links issue #6 and RR-05, which
  is what `DOC-13` asks of a declared conformance gap. The row previously read
  as fully satisfied. The Security & Supply-Chain row now says what actually
  runs.
- **The project's most important claim cited the wrong document** (2026-08-28,
  issue #35). The anti-ranking and suppression-fidelity rule was cited as
  "ADR 0000" in eight places across code, docs and tests. ADR 0000 is
  `0000-record-architecture-decisions.md`, the MADR process ADR: it says
  nothing about ranking or suppression. The decision is
  `0002-refuse-to-rank-schools.md`, `Status: Accepted`, dated 2026-08-07. The
  numbering is a leftover from the release that split the two ADRs that were
  both numbered 0000; the file moved and these citations did not.
  - Fixed at all eight sites: `src/homeroom/render.py`,
    `src/homeroom/absenteeism.py`, `src/homeroom/profiles.py`,
    `docs/ROADMAP.md` (two), `docs/RESPONSIBLE-TECH-AUDITS.md` (three). The
    issue listed seven; `tests/test_profiles.py` was the eighth and is fixed
    too. `src/homeroom/ask/guards.py` and `src/homeroom/ask/evalharness.py`
    already cited 0002 correctly, which is what confirms 0002 is the target.
  - CHANGELOG entries that mention the old number are left alone. Two of them
    are *about* the renumbering, and rewriting history to look tidy would
    falsify the record this project keeps citations for.
  - **ADR 0000 shipped with `Date: TODO - set to today's date at generation
    time`**, an unfilled generator placeholder, for three weeks. Set to
    2026-08-07, the date the file was added (commit `4cd542b`), which is the
    date the other day-one ADRs carry.
  - `tests/test_adr_citations.py` (new) keeps the trail honest, because fixing
    eight strings by hand is not a control. It checks that every ADR cited
    anywhere in `src/`, `tests/`, `docs/`, `evals/` and `tools/` resolves to a
    file that exists; that no ADR carries a placeholder where its date should
    be; that the Accepted decision ADRs are still Accepted; and that the
    process meta-ADR is never cited as the reason for a behaviour. Each of the
    three was run against a deliberately reintroduced fault (an `ADR 0000`
    citation, an `ADR 0099` citation, the restored `TODO` date) and observed
    failing before being observed passing. A first test asserts the ADR series
    and the scanned file list are both non-empty, so a renamed directory
    reports zero files instead of passing over nothing.
- **The verifier licensed a number by proximity, not by the fact it came from**
  (2026-08-28, issue #34, ADR 0003 point 4). `_allowed_numbers` in
  `src/homeroom/ask/verifier.py` built one flat set of "numbers seen anywhere
  near this record" and then asked only whether each number in a claim appeared
  somewhere in it. Into that set went the record's statewide coverage tally
  (`{"reported": N, "suppressed": M, "not_reported": K}`, a count of how many
  *other* schools' cells landed in each status), the size of the build, and the
  digits of the school's grade span. None of those is the school's own
  published figure, and ADR 0003 promises that "every number in the sentence is
  a number one of its cited records actually publishes".
  - The collision is not hypothetical. In the committed fixture, Example
    Elementary's chronic absenteeism rate is 12.5% and its coverage tally is
    `{"not_reported": 1, "reported": 1, "suppressed": 1}`, so the sentence
    "the rate for all students was 1%" verified clean and was shown to the
    reader as a cited figure about that school. The repro in issue #34 was
    executed against the fixture bundle and reproduced exactly; it now returns
    the claim withheld with reason `unverifiable_number`.
  - The suppression invariant was never at risk: `_check_absence` is a separate
    check and a withheld cell is still never narrated as a value. What could be
    swapped was a *reported* cell's own number.
  - Numbers are now licensed by the kind of claim making them.
    `CONTEXT_CLAIM_KINDS` holds the one kind whose subject is context about the
    data rather than a cell's value: `note`, already described to the model as
    "context about the data (which year, why a figure is withheld)". A `note`
    may still state a coverage tally, the build size, and the grade span. A
    `figure` or a `comparison` gets only what its own cited cells publish, plus
    years, measure-label digits, and the numbers inside a verified quote.
  - The same construction was duplicated in the independent eval scorer,
    `_cell_numbers` in `src/homeroom/ask/evalharness.py`, so the `citation` and
    `comparability` suites shared the blind spot and could not have caught it.
    That scorer exists to disagree with the service; it is narrowed the same
    way and by its own code path.
  - Both guards are demonstrated failing before they are demonstrated passing.
    `test_a_figure_may_not_state_the_coverage_tally_as_the_school_own_value`
    and `test_a_figure_may_not_borrow_the_build_size_as_the_school_own_value`
    fail against the old flat set; `test_a_note_may_still_state_the_coverage_tally_it_cites`
    and `test_a_figure_still_shows_the_value_its_own_cell_publishes` prove the
    narrowing did not withhold the sentences it exists to protect.
  - The committed results files still pass the gate `make verify` holds them
    to. They could not be re-scored under the narrowed rule, and this says so
    rather than implying they were: a results file records each shown claim's
    *text* but not its kind or its citations, and re-running the suites needs
    the acquired files in `data/raw/`, which are never in git. So the recorded
    157-case run is evidence about the old rule only. Recording kind and
    citations per shown claim, so a scorer change can be replayed against
    recorded evidence, is filed as RR-10.
- **The evaluation gate could not fail** (2026-08-26, ADR 0004). Two things
  were reporting on the ask layer and neither could report bad news.
  `main()` in `src/homeroom/ask/evalharness.py` ended in an unconditional
  `return 0`, so a run in which all 62 ranking-refusal cases were answered
  instead of refused, which is the ask layer doing the one thing ADR 0002
  exists to forbid, exited 0 and looked at the shell exactly like a clean run.
  The per-case verdicts went to stderr and the counts went into the results
  file, and then the process said success. The only automated reader of those
  counts, in `tests/test_ask_evals.py`, asserted
  `passed + failed + errors == cases`, which is bookkeeping arithmetic the
  harness computes in a single loop and cannot get wrong, and which is equally
  true of `{"cases": 62, "passed": 0, "failed": 62}`. Every provenance
  assertion in that test bit; the one assertion about whether the ask layer
  had behaved did not.
  - Nothing was masked. The recorded run is 5 suites and 157 of 157 cases
    passing, and it still is with the gate on, which is why this landed now
    rather than after a regression made it urgent.
  - One function, `regressions()`, now decides whether a suite met its target,
    and both readers call it: the harness exit code (`0` met, `1` fell short
    with each shortfall named on stderr, `2` no provider, unchanged) and the
    test over every committed results file. A results file recording a
    regression cannot pass CI. The results are still written before the check
    and written whatever they say.
  - `SUITE_MAX_FAILURES` holds the ceiling per suite in one place: the targets
    `evals/README.md` already published for ranking refusal, suppression and
    comparability, and a ratchet at the recorded level for citation and
    structuring, which have no published target. Lowering the bar is a diff
    with a reason, not a quieter results file. A suite with no entry has no
    target, which counts as a shortfall rather than as consent.
  - Two shapes that report clean without meaning anything are refused too: a
    summary whose counts disagree with the per-case records in the same file
    (what a hand-edited results file looks like), and a suite with zero cases.
    An errored case counts as a shortfall, because an error means the case
    never ran and a hole in the evidence is not a pass.
  - Both gates are demonstrated failing before they are demonstrated passing.
    `test_the_cli_exits_nonzero_when_the_ask_layer_fails_a_ranking_case` drives
    the real CLI with a model that answers the ranking question, and
    `test_the_check_this_replaced_was_true_of_a_run_that_failed_every_case`
    keeps the old identity in the suite as a record of why it gated nothing.
  - The suites still do not run in CI and this does not wire them in: they need
    a provider, a credential and the acquired CDE files, and CI has none of the
    three by design. The CI-side gate is the test over the committed results,
    and it now reads the same verdict the harness exits on.

### Added
- **The site is live at <https://homeroom.chelseakr.com>, and the ask service
  behind it is deployed** (2026-08-22, by the owner's decision). Nothing in this
  project had ever been hosted; every document said so, and now none of them do.
  What is published is one school -- Birch Lane Elementary in Davis Joint
  Unified, in English and Spanish -- with an ask page for each language wired to
  a running service, and a landing page that says it is one school out of the
  10,534 the pipeline profiles rather than implying the state is covered.
  - **Static hosting on GitHub Pages**, custom domain with HTTPS enforced, and a
    Route 53 CNAME. Zero AWS cost for the site itself.
  - **The rendered pages are committed to `site/` and the workflow builds
    nothing.** It cannot: `data/raw/` is never in git and CI never touches the
    network. That trade is what `tests/test_published_site.py` exists to make
    safe -- it reads the published bytes on a runner with no acquired file and
    checks the claims that do not need the source data: the domain is named, no
    page carries the fixture banner, every internal link resolves to a file that
    exists, no page reaches off-origin except the ask page's one https endpoint,
    every ask-page script is inline, both languages are present for every
    school, and the no-ranking and non-affiliation notices are on every page.
  - `make publish` renders and stamps `CNAME`; `.github/workflows/pages.yml`
    publishes after ci succeeds on main, or on demand, and refuses to publish a
    tree with no `index.html` or no `CNAME` (a missing CNAME silently unsets the
    custom domain).
  - **The ask service** runs as CloudFormation stack `homeroom-ask` in
    `us-west-2` on Bedrock `global.anthropic.claude-sonnet-4-6`, the model the
    recorded evaluations name: reserved concurrency 2, a daily cap of 400 model
    calls, six requests per client per minute, a CloudWatch alarm at 400 daily
    invocations to an SNS topic in the same stack, 14-day logs, and no request
    body ever logged. Verified live rather than by reading configuration: a real
    question returns cited figures; a ranking-bait question returns the fixed
    refusal and no ordering; a POST from a foreign origin is refused 403 by the
    handler, not only by CORS.
  - Recorded as applied in `deploy/ask/README.md` (stack, region, ARN, Function
    URL, parameters, rollback) and in the ADR, the ROADMAP, the risk register
    and the README. What is still open is written down too: nobody is subscribed
    to the alarm topic, there is no account budget by design, the daily cap is
    per warm container rather than a shared ledger, and no person has read the
    Spanish narration as a Spanish speaker.

### Changed
- **Direction: a grounded AI question-answering layer, by the owner's
  direction (ADR 0003, 2026-08-21).** Until now this project had no prompt,
  retrieval, or model surface, and every document said so. It is gaining one:
  an optional, opt-in service that lets a family ask what a school's page says,
  in English or Spanish, with the published CDE-derived records as the only
  evidence and a verifier between the model and the reader. The founding rule
  holds: one school per request, a fixed bilingual refusal for every form of
  ranking or judgment question, an independent guard over every model sentence,
  withheld cells narrated as not published, comparisons only on the page's own
  basis, definitions quoted verbatim from a committed corpus of CDE's pages.
  This entry records the decision and the document rewrites (README standards
  table, `docs/ROADMAP.md`, `docs/RESPONSIBLE-TECH-AUDITS.md` AI-EVAL and
  Governance, the threat model's fifth trust boundary, RR-07 to RR-09,
  `SECURITY.md`, `CONTRIBUTING.md`, and a new `AGENTS.md`); the code lands in
  the PRs that follow and is listed here as it does.

### Fixed
- **The live ask page told every reader their question was unclear before they
  had typed one.** It used the refusal string `ask_refusal_unclear` as its
  standing help text, so the page opened with "It is not clear which published
  figure the question is about" addressed to somebody who had not spoken yet.
  The useful half of that string is the list of things you can ask about, so
  the list is now its own key (`ask_page_examples`, both locales) and the
  refusal stays a refusal. A test renders the page with every `<script>`
  removed -- the refusals legitimately ship inside the JSON the script reads,
  and the question is only ever whether one is *displayed* unearned -- and
  asserts no refusal appears in what a reader sees. Found by looking at a
  screenshot of the live page. One more bilingual string (217 keys per locale).
- **The deployed ask page could not reach its service from a browser, and said
  so in the one string that hides why.** Both the Lambda Function URL's `Cors`
  configuration and the handler set `access-control-allow-origin`, so the
  response carried it twice (`https://homeroom.chelseakr.com,
  https://homeroom.chelseakr.com`) and every browser refused it: *"contains
  multiple values, but only one is allowed"*. The page then fell back to its
  fixed "the answering service is not available right now" refusal -- correct
  behaviour, and a complete disguise. `curl` cannot see this at all; it prints
  the header and does not enforce it, and had reported the same endpoint
  healthy and answering minutes earlier. Found by loading the live page in a
  real browser. The template no longer declares CORS on the URL: the handler is
  the single source, and it is the same code that enforces the origin
  server-side, which is the check that actually refuses anybody. Preflight now
  reaches the function, which already handled `OPTIONS`.
  `tests/test_deploy_template.py` gates that and ten other things a green
  `cloudformation deploy` does not prove.
- **Three things the ask service's deployment shape got wrong, each found by
  deploying it rather than by reading it** (2026-08-22, the day the owner
  authorized hosting). (1) `homeroom.ask.corpus` locates the corpus by walking
  up from its own file to the repository root, which is right in a checkout and
  one directory too high in a deployment package, where there is no `src`
  level: the first live request died on `/var/corpus/manifest.json` while the
  corpus sat at `/var/task/corpus`. `HOMEROOM_ASK_CORPUS` now names it, the way
  `HOMEROOM_ASK_BUNDLE` already named the evidence bundle, and the template
  sets it. (2) `build.sh` installed the bare `anthropic` SDK, but
  `AnthropicBedrock` signs with botocore; the package would have run on
  whatever boto3 the Lambda runtime happened to carry. It now installs the
  `bedrock` extra, and it measures and prints the unzipped package against
  Lambda's 250 MB limit (231.7 MB, 92.7%) instead of reporting `du`'s
  block-rounded overstatement. (3) The Function URL returned 403 to every
  request while its CORS preflight returned 200: this account requires a
  `lambda:InvokeFunction` grant as well as `lambda:InvokeFunctionUrl` before an
  unauthenticated caller can run the function. The template carries both, with
  a note on why the second cannot be narrowed by `FunctionUrlAuthType` and what
  that does and does not widen.

### Added
- The landing page (`homeroom.landing`, `--landing`): one bilingual
  `index.html` naming what is published so far. A hosted site needs a root,
  and the risk a root page carries is a claim rather than a rendering bug, so
  this one says Homeroom is in development, lists only the schools the build
  actually wrote (a link to a page that was not built is a 404 with a real
  school's name on it), repeats the no-ranking and non-affiliation notices,
  marks each language section with its own `lang`, and carries no figure at
  all: every number on this site sits beside its suppression state, year and
  source, and none of that fits in a list of links. Same rules as every other
  page (ADR 0001) — stdlib rendering, the shared inline stylesheet, no script,
  no external asset, deterministic output — and it is written only when asked
  for, so a build without `--landing` is byte-identical to one from before it
  existed, which `tests/test_landing.py` asserts by diffing the two builds.
  html-validate and axe-core cover it in `make pages` (zero violations). Two
  more bilingual strings (217 keys per locale).
- `homeroom.ask.http`: the HTTP edge of the ask service, a stdlib
  `ThreadingHTTPServer` for local use (`make ask-serve`) and an AWS Lambda
  Function URL handler, both thin over `AskService`: JSON in, the public JSON
  out (withheld sentences and the raw lookup stripped), service status mapped
  to 200/400/429/503, CORS for exactly the configured origin, a 4 KB body
  limit, `cache-control: no-store`, the access log silenced, and a salted
  per-process hash of the client address as the only thing derived from a
  request that outlives it. `deploy/ask/`: the prepared and NOT APPLIED
  deployment shape (CloudFormation: one arm64 Lambda, Function URL with CORS
  locked to the site origin, reserved concurrency, 14-day logs, a daily
  invocation alarm, Bedrock via the role or the Anthropic API via a `NoEcho`
  parameter), a build script that refuses to package a fixture bundle, and a
  runbook naming the decisions that precede any deployment.
- The ask page, the opt-in front end of the ask layer (ADR 0003). `make site
  ASK_ENDPOINT=<url>` (or `--ask-endpoint`) adds exactly one link to each
  school page and writes `ask/<cds>.<locale>.html` beside them; without it the
  build is byte-identical to one before ADR 0003, which `tests/test_askpage.py`
  asserts by diffing the two builds. The ask page is the only page that
  carries a script: one inline script, no subresource, no `on*` attribute, a
  form with a labelled textarea and a button, a `noscript` note, the
  AI/unofficial/not-a-ranking labels, the non-affiliation notice, and a link
  back to the school page, which is complete without it. The script registers
  a submit handler and nothing else; the answer is built with `textContent`
  only, citations link to the school page's own table anchors or to CDE's
  page, and focus moves to the answer heading. `tools/ask-optin.mjs` loads
  every ask page in a DOM with every network path stubbed and proves zero
  requests on load and exactly one POST on submit, rendered as text; it runs
  in `make pages` beside html-validate and axe-core, which now cover the ask
  pages too (zero violations, both languages). Seventeen more fixed
  bilingual strings (217 keys per locale).
- `evals/`: the evaluation harness (`homeroom.ask.evalharness`) and five
  suites over real schools from the acquired files, with deterministic
  scorers that read the displayed answer and the bundle rather than the
  service's own verdicts, and results files, one directory per model under
  `evals/results/`, that carry provider, model, prompt version, commit,
  date, and bundle provenance (a test rejects one without them, or one from
  fixture data; two models' runs sit side by side and neither overwrites
  the other). Recorded run 2026-08-22 on Amazon
  Bedrock `global.anthropic.claude-sonnet-4-6` against the 10,534-school
  bundle: ranking refusal 62/62, suppression 24/24, citation 24/24,
  comparability 19/19, structuring 28/28; 511 sentences shown, 23 withheld
  by the verifier before display. Earlier runs found and fixed: a claims
  array serialised as a string, 'has not been published' missing from the
  absence lexicon, and honest denials of the zero reading ('not because the
  number is zero') being withheld as zeros.
- `homeroom.ask`, the service core of the grounded question-answering layer
  (ADR 0003). `catalog` names every measure a page renders and nothing else
  (58 keys, derived from the renderer's own constants; no D5). `evidence`
  writes one small JSON file per school from the page build's own assembly,
  context, and coverage code, every cell addressable as
  `CDS|measure|year|scope` and in the same three states as the page; 10,534
  files from the acquired data, byte-identical across builds. `structuring`
  turns a question into a validated lookup against the catalog and runs a
  lexical judgment guard over the question in both languages, so either the
  model or the guard saying "judgment" wins. `narration` holds the one cached
  system prompt (rules, catalog in both languages, citation format;
  `PROMPT_VERSION` stamped on every result) and the claims schema. `verifier`
  checks every claim before display: citation resolution, every number
  against the cited cells (years, coverage counts, label digits, and verified
  quotes allowed; nothing else), withheld cells stated as not published and
  never as a zero or a "none", comparisons limited to a school cell and its
  own district or state cell with the stated direction checked against the
  arithmetic (read from whichever side the sentence speaks from), definitions
  requiring a verbatim corpus quote, and a judgment-language guard over every
  sentence; fourteen enumerated withhold reasons. `provider` wraps the public
  `anthropic` SDK (Anthropic API, default `claude-sonnet-5`; Amazon Bedrock
  through the same SDK), forced tool calls with the system prompt cached and
  thinking disabled, credentials from the environment only, imported lazily
  so the core package stays stdlib-only. `limits` is a per-client token bucket
  and a hard daily cap on model calls. `service` is the pipeline: validate,
  limit, load one school, structure, fixed refusal where owed, narrate,
  verify, count what was withheld; it stores no question anywhere and fails
  closed to the static page on any provider error. Sixteen fixed bilingual
  strings in `i18n.py` (labels and every refusal) that the model never writes.
  Tests cover every verifier failure class against the fixture school, every
  service stop, and the request shape; the SDK is never imported by the test
  suite's import of the service (asserted in a subprocess).
- `corpus/`: the text of six CDE pages (chronic absenteeism file structure and
  download page, the Child Welfare & Attendance page with the statutory
  definition of a chronic absentee, the Census Day enrollment file structure
  and download page, the public-schools directory file structure), retrieved
  by the new `tools/corpus_fetch.py` with URL, retrieval date, the page's own
  "Last Reviewed" date, and SHA-256 of both the HTML received and the text
  committed, in `corpus/manifest.json`. `homeroom.ask.corpus` loads them,
  refuses a file whose hash no longer matches the manifest, and decides
  whether a quote is verbatim (whitespace and typographic marks normalised,
  every word checked, quotes under four words refused). This is the only
  evidence the ask layer may cite for a definition (ADR 0003).

### Fixed
- A cell that is not a published number could become one. `parse_cell` handed
  anything that was not `*` or empty straight to `float`, and `float` accepts a
  great deal a data file never means as a number. `nan` is the one that matters:
  it is how an export writes a value it does not have, and it was classified as
  *reported*, so it rendered on a school page inside `<span class="num">`, in a
  cell whose own legend says "the state published this figure", styled and
  captioned exactly like a real count. The page-level gate that checks every
  number in a data cell was counted did not catch it, because `nan` has no digits
  in it. `1_0` read as ten through PEP 515 digit separators, `1e3` as a thousand,
  `1,23` as one hundred and twenty-three once the commas were stripped, and
  fullwidth or Arabic-Indic digits as numbers nobody typed. `parse_cell` now
  checks the cell against `PUBLISHED_NUMBER`, an explicit statement of the shape
  CDE publishes, before converting, and refuses everything else as the drift it
  is. Measured against the acquired 2025-26 D2 file: no change to any real figure
  (10,534 profiles, 182,362 / 0 / 80,988 subgroup measures, join gaps 698 and 674,
  all unchanged).
- A figure too large to hold became infinity in silence. A digit run long enough
  to overflow a float converted without complaint, and `inf` reached the page the
  same way `nan` did. `parse_cell` now refuses a value that is not finite.
- `schools.json` could stop being JSON. A `nan` or overflowed cell serialized as
  the bare literal `NaN` or `Infinity`, which RFC 8259 does not have: Python
  writes and reads both without complaint, so the project's own round trip could
  not see it, while a browser's `JSON.parse` and a Go or Rust decoder reject the
  whole document over one of them, taking all 10,534 schools down with one bad
  cell. `tests/test_artifacts.py` now reads the artifacts back through
  `parse_constant`, which fires on exactly those tokens, so the gate holds for any
  future path into the artifact and not only for this one.
- Two measured figures in the docs were wrong, and are corrected in place in the
  `docs/ROADMAP.md` ledger the way its earlier corrections are. Districts were
  recorded as 1,048, which is the count of distinct district *names*: ten names
  cover two districts each and "Jefferson Elementary" covers three, so counting by
  name loses eleven, and the count by CDS code, the only key this project joins
  on, is 1,059. And Birch Lane's page was recorded as "30 numbers, 6 of them
  genuine published zeros" when the 6 are beside the 30 rather than among them:
  the page publishes 36 of its 40 figures. The second is this project's own rule
  read backwards, since a published zero is a figure the state published and is
  the reason the four cell states exist.
- **The lockfile gate did not gate.** `make sync`, the first stage of `make verify`
  and therefore of CI, ran `uv sync --frozen`. That flag installs from `uv.lock`
  without reading `pyproject.toml`, so by construction it cannot notice the two
  disagree, and it exits 0 on a drifted lock: a dependency added or bumped in
  `pyproject.toml` without relocking would have passed the full gate. Now
  `uv sync --locked`, which re-resolves and exits 1 on drift, with the reasoning
  in a comment beside the line. The release job in `.github/workflows/release.yml`
  gets the same substitution.
- **Two ADRs were both numbered 0000**, making a citation to "ADR 0000" ambiguous.
  `0000-record-architecture-decisions.md` keeps the seed number by convention;
  refuse-to-rank-schools moves to `0002-refuse-to-rank-schools.md` with its
  heading updated. No accepted ADR was renumbered out from under an existing
  citation, and nothing referenced the moved file by number.

### Added
- **M3: chronic absenteeism (D3), the first masked-heavy measure, end to end**
  (`src/homeroom/absenteeism.py`, new). The 2024-25 file (`chronicabsenteeism25.txt`,
  33,781,100 bytes, 341,490 rows) was acquired 2026-08-21 and its header read
  directly: identity columns are spaced (`Academic Year`, `Charter School`, ...)
  while the three measure columns are concatenated
  (`ChronicAbsenteeismEligibleCumulativeEnrollment`, `ChronicAbsenteeismCount`,
  `ChronicAbsenteeismRate`), and `Charter School`/`DASS` are two independent
  `All`/`Yes`/`No` dimensions rather than D2's one. Joins the D1 spine and D2's
  academic year stays separate from D3's own (`homeroom.profiles`); district and
  statewide context reads CDE's own `Charter School = All, DASS = All` rows,
  never a sum over schools (`homeroom.context.load_absenteeism_context`, mirroring
  `load_context`'s existing rule for D2). Renders on every school page as a total
  rate plus race/ethnicity, gender, and student-group tables, each in the same
  four states and the same seven-column shape as every other measure table
  (`homeroom.render._absenteeism_section`); wired into `make data` and
  `make site`'s default invocation. Measured against the acquired files: total
  rate reported for 9,718 of 10,534 active schools, withheld for 83, not
  published for 733; the most-withheld subgroup is Non-binary (`GX`), withheld
  for 1,990 of the 2,045 schools that have any row for it (97.3%), with the
  other 8,489 carrying no such row at all. American Indian or Alaska Native
  (`RI`) is withheld for 9,350 of 9,801 (95.4%), over a denominator that is
  nearly every active school. This entry named `RI` as the maximum until
  2026-08-29.
  `docs/SUPPRESSION-SHOWCASE.md` is the committed artifact walking four real rows,
  one of each cell state, from the source file to the rendered markup.
- **D5's provisional column contract, checked against the real file and rewritten
  to match it** (issue #5). The 2023-24 Teacher Assignment Monitoring Outcome
  file (`tamo2324.txt`, 234,206,408 bytes, 1,528,796 rows) was acquired
  2026-08-21. Every part of the provisional contract disagreed with it: real
  column names are spaced and some carry CDE's own typo (`Unknown FTE FTE
  (percent)`, read verbatim); there are seven outcomes, not five (`incomplete`
  and `na` were missing); values are fractional FTE, not integer counts; and the
  file's grain is one row per (school, charter, DASS, grade span, teacher
  experience level, teacher credential level, subject area) -- up to 150 rows per
  school, not one -- of which exactly one row per school (experience = credential
  = `ALL`, subject = `TA`) is CDE's own already-aggregated whole-school total,
  verified present for all 10,064 schools in the file. Scanning every numeric
  cell in the file found zero masked cells anywhere, unlike D2 and D3.
  `src/homeroom/assignments.py` and `fixtures/tamo.sample.txt` are rewritten to
  match; acquired is still not published, and `make data`/`make site`'s default
  invocation are unchanged.
- `.github/dependabot.yml`: weekly `uv`, `npm` and `github-actions` updates,
  keeping the pinned Python set, the Node page-gate toolchain, and the
  SHA-pinned action set current at a weekly PR volume one maintainer can
  review. The CodeQL action set is grouped into one PR because init, analyze,
  autobuild and upload-sarif must run the same version.
- Four standards missing from the README conformance table (Performance, AI
  Development Measurement, Incident Response, Data Governance) are now
  declared **Applies**, each naming what exists and what does not.

## [0.1.0] - not released

Not a release. This heading read "[0.1.0] - 2026-08-18 / First tagged release"
until 2026-08-29; `git tag` lists nothing in this repository and no release has
ever been published, so both the date and the word "tagged" described something
that never happened. `0.1.0` is the in-development version in `pyproject.toml`
and `CITATION.cff`, and the section is kept as the boundary of the work it
describes, not as a release. `.github/workflows/release.yml` still requires a
signed tag, so cutting one is a deliberate act that has not been performed.

The work: the CDS-code directory spine, Census Day enrollment, the
teacher-assignment parser (no D5 file acquired), one school profile per active
school as deterministic JSON artifacts, and static bilingual school pages built
from those profiles. Nothing was deployed or hosted at that point; pages
rendered locally from files a person downloaded from CDE's public data pages.
The ask service was deployed later, on 2026-08-22 (ADR 0003, `deploy/ask/`).

### Added
- `.github/dependabot.yml`: weekly `uv`, `npm` and `github-actions` updates.
  `pip-audit` in `make verify` catches a dependency that is already
  known-vulnerable; this covers the other half, keeping the pinned set current.
  The CodeQL action set is grouped into one PR because init, analyze, autobuild
  and upload-sarif must always run the same version.
- Four standards that the README conformance table had left undeclared are now
  declared with their current state: Performance, AI Development Measurement,
  Incident Response, and Data Governance. Each row says what exists and what
  does not, rather than asserting a posture the repo has not built.
- First bilingual school pages (M4): `src/homeroom/render.py` renders one static
  HTML page per school per language from the existing profiles, and `make site` /
  `make site-offline` build them. Birch Lane Elementary in Davis Joint Unified
  renders from the acquired files in English and Spanish; the fixture build
  renders every committed school in both languages and says on the page that the
  data is not real. Pages carry no script, no external asset, no account, and no
  tracking, and nothing is deployed or hosted.
- Four cell states that never collapse into each other: a published figure prints
  as published, a published zero prints as `0` and says it is one, a figure CDE
  withheld prints the words "withheld to protect privacy" with no digit anywhere,
  and a figure the state never published prints "no figure published". Withheld
  and missing cells are tested to contain no digit at all, so nothing on a page
  can be skimmed or scraped as a zero.
- Coverage published beside the data, row by row: every measure table carries how
  many active schools publish that figure, withhold it, and publish nothing,
  counted across all 10,534 active schools on the acquired build (9,860 publish a
  total enrollment figure, 674 publish none).
- English and Spanish as peers (`src/homeroom/i18n.py`): 217 keys per locale, 434
  strings total (122 keys at M4, before D3 added its own 25-code category catalog
  and 10 interface strings at M3, and before the ask layer added 33 fixed
  interface strings under ADR 0003), covering every reporting category, grade span,
  and subgroup family name. A missing key raises rather than falling back to
  English, and CDE's English-only school and district names are marked
  `lang="en"` on Spanish pages (WCAG 2.2 SC 3.1.2).
- The accessibility gate the README promised from the first page, inside
  `make verify` and merge-blocking in CI: `html-validate` (conformance, document,
  and a11y presets, with `scope` required on every table header) and `axe-core` in
  a headless jsdom DOM over the WCAG 2.0/2.1/2.2 A and AA rule sets plus
  best-practice, on every built page in both languages. Zero violations.
- The EN/ES parity gate the roadmap wired at M4 (`tests/test_i18n.py`): fails on a
  key present in one language and absent in the other, on a Spanish string left
  identical to its English original outside a short reviewed list, and on a
  translated template that lost a `{placeholder}`.
- Page checks that need no browser (`tests/test_pages.py`): one `h1`, no skipped
  heading level, a caption and scoped headers on every table, landmarks, unique
  ids, a focusable named region around every scrollable table, WCAG 2.2 contrast
  measured off both palettes in light and dark, and every number in a data cell
  checked against the values the pipeline actually counted.
- Every page states, in both languages, that teacher assignment data has not been
  acquired and that no figure about this school's teachers is shown. The page
  build takes only the D1 and D2 files, so it has no argument by which a D5 figure
  could arrive, and a test renders a profile that does carry parsed assignment
  outcomes to prove none of them reaches the markup.
- Deterministic pages: re-rendering is byte-identical, asserted in the test suite
  and again in CI by building the offline site twice and diffing the hashes.
- ADR 0001 records the page toolchain chosen at M4: stdlib Python rendering, typed
  per-locale string dictionaries, and node checkers that never ship in a page.
- Teacher assignment monitoring (D5), parser only: `src/homeroom/assignments.py`
  reads CDE's Teacher Assignment Monitoring Outcome files, published from the
  Commission on Teacher Credentialing's CalSAAS system, and carries five
  authorization outcomes per school as counts and published shares. Shares are
  copied, never divided out of counts; no outcome is ever recovered as the total
  minus its visible siblings. Profiles gain an optional `teacher_assignments`
  block joined on the 14-digit CDS code, artifacts gain the block and its
  coverage, and `--assignments` is a new optional input to `make data`.
  **No D5 file has been acquired**, so no D5 number about a real school is
  published anywhere. The parser was built against `fixtures/tamo.sample.txt`, a
  synthetic fixture, and the column contract is provisional until the real file
  is in hand; the drift errors are what make that safe, because a contract that
  turns out wrong stops the build instead of mis-reading a file.
- Each source now keeps its own school year. Assignment monitoring reports on a
  different cycle than Census Day enrollment, and a profile carries both years
  rather than putting one label over data from two calendars.
- Unacquired sources state their absence rather than rendering as zeros: with no
  D5 file, `coverage.json` records the source as unsupplied and no school carries
  an assignment block at all. A build cannot stamp an acquisition date nobody
  recorded, and the code constant and PROVENANCE.md are tested for agreement.
- School profiles (M3a): one `SchoolProfile` per active school joining directory
  identity, academic year, total enrollment, TK-12 grade spans, and subgroup
  enrollment for the four families the 2025-26 file carries (race/ethnicity,
  gender, English language acquisition, student groups), every value a `Measure`.
  All 33 observed ReportingCategory codes carry display names reviewed against
  CDE's file structure page; an unreviewed code fails the build.
- Deterministic artifacts and `make data` / `make data-offline`: `schools.json`
  and `coverage.json` in `data/out/` (gitignored), byte-identical across re-runs;
  a Measure serializes with a `value` key only when the state published a number.
  Coverage is first class: per-measure status counts, join gaps in both
  directions (698 school totals without a directory match, 674 active schools
  without enrollment rows, from the acquired files), PROVENANCE access dates, and
  an `is_fixture` flag.
- Suppression-fidelity guarantee, the rule owed before M3: published values are
  exactly CDE-published cells, and tests assert no artifact value can be a
  complement of a masked cell (`tests/test_profiles.py`,
  `tests/test_artifacts.py`).
- Fixture growth: a committed enrollment fixture exercising every rendering case
  (reported, suppressed, not reported, genuine zero, unjoined enrollment row,
  closed school, active school with no enrollment), so CI covers profiles and
  artifacts without any acquired data.

- CDS-code spine: parser for the CDE public school directory (`pubschls.txt`)
  with header-addressed columns and hard drift errors; verified against the live
  file acquired 2026-08-07 (18,396 rows, 10,534 active schools, 1,048 districts).
- Census Day enrollment: parser for the 2025-26 file (269,090 rows) with TK-12
  grade columns, aggregate-level separation, and CDS join to the spine (10,558
  school totals, 9,860 joined; school totals sum to the state's own row at
  5,731,260).
- Null-never-zero machinery: the `Measure` type distinguishes reported,
  suppressed, and not reported; a masked cell (CDE's `*`; 117,946 rows carry at
  least one in the 2025-26 enrollment file) cannot be read as a number; unknown
  sentinels fail the build; coverage is a first-class output.
- Provenance record (PROVENANCE.md) for sources D1-D6, including the
  browser-acquisition rule that keeps every file's origin and date on the record.
- Founding ADR 0000: the anti-ranking rule as an architectural decision.
- Conformance scaffold from `standards-init` (STANDARDS EXP-09), conformant with
  `STANDARDS/` `v1.0.1` at birth: CI with fully SHA-pinned actions, signed-tag
  release pipeline with SBOM and provenance, roadmap with metrics ledger,
  responsible-tech audit record, security policy, and citation metadata.

### Fixed
- **The release trust root pointed at a file nothing read.** The maintainer's
  signing key was committed 2026-08-07 to `.github/allowed_signers`, while
  `release.yml` reads `.github/signing-allowed-signers`, which still held the
  scaffold placeholder, so no tag could ever have verified. The signing
  principal and public key, checked against the key registered on the
  maintainer's GitHub account, now live in the file the workflow reads,
  restricted to the `git` signature namespace, and the unread duplicate file is
  removed so the trust root has one home (RR-04, closed).
- **The hosted-ruleset binding check could never run.** The release workflow
  called `check_release_ruleset.py` with `--tag "${TAG}"-message`, a mangled
  spelling of `--tag "${TAG}" --verify-tag-message`: argparse accepted the
  garbage tag value, no message operation was selected, and the step passed on
  ruleset parity alone while the signed-tag-message binding it exists to
  enforce silently never executed. The flag is now spelled correctly, so a
  release tag must carry the exact message binding the hosted tag ruleset's id
  and `updated_at` (`--print-tag-message` prints it for the tag command).
- Two D2 values recorded at M2 were corrected by M3a re-measurement: rows
  carrying at least one masked cell are 117,946 (first recorded as 88,207), and
  the state's own statewide row is 5,731,260 (5,692,490, first recorded as that
  row, is the joined-schools sum; the 698 unjoined school totals carry the
  38,770-student difference). The corrections are also marked in the ROADMAP
  metrics ledger.
- PROVENANCE now records the D2 acquisition itself (2025-26 file, acquired
  2026-08-07 as `cdenroll2526.txt`), which the coverage artifact stamps.
- **The release workflow could never extract its own release notes.** The
  CHANGELOG section pattern in `.github/workflows/release.yml` is built in an
  f-string, where `{4}` is a replacement field rather than a regex quantifier,
  so `\d{4}-\d{2}-\d{2}` had silently become `\d4-\d2-\d2` and matched no date
  ever written. Every release would have aborted at "matching dated CHANGELOG
  section is missing". The braces are doubled and the reason is in a comment
  beside the line. It fails closed, so nothing was ever published wrongly; the
  workflow simply could not run to completion.
- **A test that could not fail.** The D5 acquisition-date test compared the
  access date in `coverage.json` against `ASSIGNMENTS_ACCESS_DATE`, the constant
  that writes that field, so the assertion could not fail whatever either one
  said: setting the constant to a date PROVENANCE.md does not record still
  passed. The expectation is now read from PROVENANCE.md, which is where a
  person records an acquisition, so that mutation fails.
- **The catalog figures in the prose were two short.** README, CHANGELOG and the
  ROADMAP ledger all still gave the M4 figure of 120; the district and statewide
  columns added two interface keys and none of the three was updated.
  `tests/test_i18n.py` now reads the true count (stated correctly, and kept
  current, everywhere else in these three documents) out of all three and
  compares it to the catalogs, failing when a document drops the claim as well
  as when it states it wrongly.
- The ROADMAP row "measure cells per page" gave 40, which is the number of
  measures; each is rendered in three columns, so the row now says so.
- **"No script, no external asset, no tracking" had no gate.** Neither
  html-validate nor axe-core has an opinion about it: a page that loads a CDN
  font or a tracking pixel is conformant and accessible. `tests/test_pages.py`
  now checks every built page for script and subresource elements, fetching
  attributes, inline event handlers, `@import`, `url(`, and `javascript:`, and
  requires the stylesheet to still be present and inline so the check cannot be
  met by a page that stopped rendering.
- A CDS code the enrollment parser cannot assemble into 14 digits raises, and
  now has a test; the guard was previously the only uncovered branch in that
  module. Removed `context._empty`, which no caller ever used.
