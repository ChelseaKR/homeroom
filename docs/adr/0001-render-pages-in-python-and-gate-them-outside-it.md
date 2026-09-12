# 0001. Render the pages in Python, and gate them with a toolchain that never ships

Status: Accepted
Date: 2026-08-07
Deciders: Chelsea Kelly-Reif

## Context

`docs/ROADMAP.md` deferred one decision to M4: "Rendering target is static
bilingual pages; the page toolchain is chosen at M4, with accessibility and i18n
gates wired in the same milestone." This is that choice.

The constraints were already fixed by earlier decisions and by what the data is:

- The runtime is stdlib-only Python. The parsers reject a dataframe dependency
  surface because they need exact cell-level control (ROADMAP, Architecture).
- CI never touches the network, and every rendering case is exercised by committed
  fixtures.
- Output must be deterministic. The artifacts are already byte-identical across
  re-runs; pages that were not would make the guarantee meaningless.
- Accessibility and English/Spanish parity are launch requirements with gates, not
  aspirations (README standards table).
- The unit of output is one page per school per language. The directory holds
  10,534 active schools, so the renderer has to be cheap per page and boring.

The realistic options were a static site generator (Eleventy, Astro, Hugo), a
Python template engine (Jinja), or rendering in the standard library. A generator
would put a second language, a second dependency tree, and a build server between
the data and the page, for a site with no client-side behaviour at all. Jinja
would add one dependency and move the honesty rules into templates, where a
missing `{% if %}` silently renders an empty cell, which is the exact failure mode
this project refuses.

## Decision

Pages are rendered by `src/homeroom/render.py` in stdlib Python, and the checking
toolchain lives outside the product and never ships in it.

- **No template engine and no site generator.** One module builds the markup, and
  the four cell states are a function with four branches rather than a template
  with four conditionals. A measure that is withheld cannot fall through to an
  empty cell, because there is no fall-through.
- **The pages carry no script, no external stylesheet, no font, and no image.**
  The stylesheet is inlined and the palettes are Python dictionaries, which is
  what lets a test measure WCAG contrast without a browser.
  (**Amended 2026-09-07**, and unlike the note on "No deployment" below this one
  does change the bullet it sits under: the stylesheet is no longer inlined on
  the school, county, district and landing pages. It was 5,061 bytes on each of
  21,068 school pages and 5,169 on each of 2,234 browse pages — 118,190,092
  bytes, 13.62% of `site/`, measured over the published tree — and the byte
  budget in `src/homeroom/publish_limits.py` had become the thing deciding what
  Homeroom may publish at all. Those pages now link one file the same build
  wrote, `homeroom.css`, at the root of the site.
  Three parts of the bullet are unchanged and are load-bearing: **no font, no
  image and no third party** — the linked file is same-origin, written by this
  build, and `tests/test_pages.py` fails on an `@import` or a `url()` inside it;
  and **the palettes stay Python dictionaries**, so the contrast tests still
  measure them without a browser. What did change is that a page now makes one
  request it did not make before, and can be served before its stylesheet
  arrives. That is safe only because the four cell states are separated by words
  as well as colour — a withheld figure reads "withheld to protect privacy" and
  never a digit — so an unstyled page is less legible and not less true;
  `test_a_page_whose_stylesheet_never_arrives_still_tells_the_truth` asserts it
  rather than trusting it.
  **The ask pages are excluded and stay inline.** `tools/ask-optin.mjs` proves an
  ask page issues no request until a question is submitted, and a linked
  stylesheet is a request on load, so the saving that is right for the other four
  page kinds is exactly wrong for that one. Issue #95 carries the measurements.)
- **Strings live in typed Python dictionaries** (`src/homeroom/i18n.py`), keyed by
  locale, not in gettext or ICU catalogs. A missing key raises instead of falling
  back to English, and the parity gate in `tests/test_i18n.py` fails on a key
  present in one language and absent in the other, on a Spanish string left
  identical to its English original, and on a translated template that lost a
  placeholder. This mirrors the sibling Afterward project's ADR 0002 and the
  reasoning is the same: a silent English fallback is what makes a
  half-translated page shippable.
- **Node is a checker, not a runtime.** `package.json` holds three
  devDependencies (`html-validate`, `axe-core`, `jsdom`) used by `make pages` to
  read built files off disk. Nothing from `node_modules` reaches a page. If the
  node toolchain is unavailable, `make verify` still checks page structure, EN/ES
  parity, contrast, and counted numbers in Python, so the floor holds.
- **The gates run against pages built from committed fixtures**, in both
  languages, with no acquired file and no network. The fixture set covers all four
  cell states, including a school whose every figure is withheld and a school the
  enrollment file never mentions.
- **No deployment.** Nothing here publishes, serves, or hosts. Whether these pages
  go on the internet, and where, is a separate decision with its own consequences
  for families whose schools appear on them, and it is not made by a build.
  (Noted 2026-08-29, without altering the decision above: that separate decision
  was made on 2026-08-22. The pages are served at homeroom.chelseakr.com by
  `.github/workflows/pages.yml`, which publishes the committed `site/` and still
  builds nothing, and the ask service of ADR 0003 is deployed. The renderer is
  still what this ADR describes.)

## Consequences

- Adding a page type means writing Python, not learning a generator. The cost is
  that layout work is more literal; the benefit is that every honesty rule is
  enforceable by a unit test rather than by template review.
- The renderer is not a general-purpose site framework and should not become one.
  If the project ever needs client-side search over 10,534 schools, that is a new
  decision and a superseding ADR, not a quiet dependency.
- Two toolchains are maintained instead of one, and CI needs a node step. That is
  the price of a real WCAG gate; the alternative on offer was no gate.
- Translations are edited in a Python file. `CONTRIBUTING.md` says so and says
  Spanish review is the most valuable outside contribution this repo can take.
- Determinism is asserted twice: `tests/test_pages.py` re-renders and compares, and
  CI builds the offline site twice and diffs the hashes.
