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
