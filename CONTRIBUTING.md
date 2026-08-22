# Contributing

## Local gate

```sh
uv sync
make verify
```

`make verify` is the single local gate and is byte-for-byte identical to the
`verify` job in `.github/workflows/ci.yml`; if it is green locally, CI is
green (`STANDARDS/CODE-QUALITY-STANDARD.md` §2).

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
