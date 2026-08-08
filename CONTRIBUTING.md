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
