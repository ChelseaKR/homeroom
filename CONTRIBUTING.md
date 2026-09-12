# Contributing

## If you are not here to write code

The thing this project is most stuck on does not need code. Nobody has ever
walked a page of this site with a screen reader or a keyboard, in either
language, and no test can do it: `tools/a11y.mjs` runs in jsdom, which does no
layout and paints no pixels. One page type in one language, in one sitting, is
a complete contribution and gets your name and the date in the record.

[`docs/HELP-WANTED.md`](docs/HELP-WANTED.md) says what is open, roughly what
each row costs in real minutes, and what you get. The
[session template](.github/ISSUE_TEMPLATE/screen-reader-session.md) is how to
report one.

If you know a California school and a page about it says something wrong, that
is the other one: [school page looks
wrong](.github/ISSUE_TEMPLATE/school-page-looks-wrong.md), five minutes, no
setup.

## Local gate

```sh
uv sync
make verify
```

`make verify` is the single local gate. It is a strict superset of CI, not a copy
of it: CI's `verify` job runs `make verify-ci`, and `make verify` is that plus the
working-tree secret scan, which needs a binary the runner does not carry and which
in CI would have no uncommitted file to find. So green locally implies green in CI,
never the reverse (`STANDARDS/CODE-QUALITY-STANDARD.md` §2).

This paragraph said `make verify` was "byte-for-byte identical to the `verify`
job"; it was not, and the Makefile's own comment and `AGENTS.md` were corrected on
2026-08-28 while this file was missed. Corrected 2026-08-29.
`tests/test_ci_parity.py` is what holds the relationship in place.

It ends in `make pages`, which builds the school pages from committed fixtures and
runs `html-validate` and `axe-core` over every one of them, in both languages. That
step needs Node 22 and runs `npm ci`; nothing it installs ever reaches a page (ADR
0001). No acquired data and no network access are involved beyond the package
installs themselves.

## Spanish

Spanish is a launch requirement here, not a later translation phase, and it is the
contribution this repo most needs from somebody other than its author. Every
user-visible string lives in `src/homeroom/i18n.py`, all in one file on purpose.
The tests in `tests/test_i18n.py` catch a missing key, an untranslated string, and
a lost placeholder. What they cannot catch is Spanish that is technically complete
and still reads like a form. If you can tell the difference, an issue or a PR is
worth more here than a feature.

## The ask layer

`src/homeroom/ask/` is the optional AI question-answering layer (ADR 0003). It
imports the `anthropic` SDK lazily and only when a provider is configured, so
`make verify` needs no credential and makes no model call. The evaluation
suites in `evals/` do need one; read `evals/README.md` before running them, and
never commit a results file from anything but a real run. `AGENTS.md` lists the
rules that bind changes here, starting with: the verifier is not to be weakened
to make a suite pass, and the refusal strings are not to be generated.

## Review

Every PR requires review sign-off before merge. PRs touching
`.github/workflows/`, `.github/CODEOWNERS`, the `STANDARDS/` pin, or any
guardrail/threshold route to the code owner automatically (see
`.github/CODEOWNERS`) and must link an ADR (`docs/adr/`) per
`STANDARDS/DOCUMENTATION-STANDARD.md` §3.

## Standards

This repo vendors `STANDARDS/` as a pinned git submodule. See the
[Standards Conformance table](README.md#standards-conformance) in the README
for which standards apply here and their current state.

## Commercial solicitation

Issues here are not open to bids. They are design records — written so a decision is
reconstructable later — not scope documents for outside quoting, and unsolicited offers to
implement one for a fee will be declined.

Contributions through the normal fork-and-PR process are welcome, and `good first issue` is the
place to start.
