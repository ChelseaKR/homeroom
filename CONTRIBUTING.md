# Contributing

## Local gate

```sh
uv sync
make verify
```

`make verify` is the single local gate and is byte-for-byte identical to the
`verify` job in `.github/workflows/ci.yml` — if it's green locally, CI is
green (`STANDARDS/CODE-QUALITY-STANDARD.md` §2).

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
