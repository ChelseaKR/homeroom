# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| latest `main` | yes |
| tagged releases < latest | best-effort, see CHANGELOG |

## Reporting a vulnerability

Please use GitHub's [private vulnerability reporting](https://github.com/ChelseaKR/homeroom/security/advisories/new)
for this repo (enable it in repo Settings -> Security -> Private vulnerability
reporting if this is a brand-new repo). Do not open a public issue for a
security report.

**Response SLA:** acknowledgment within 72 hours.

## Scope

The ask service (ADR 0003) is deployed, and has been since 2026-08-22: one
unauthenticated POST endpoint on an AWS Lambda Function URL in `us-west-2`,
recorded in `deploy/ask/README.md` and named in the published pages under
`site/ask/`. This section said the opposite for seven days after that, which
understated the surface a reporter is being asked to look at. It is corrected
here (2026-08-29) rather than quietly rewritten.

In scope, through the private channel above: that endpoint, prompt injection,
a fabricated or judgmental answer reaching a reader, and a credential in a
build. The service stores no question and holds no user data. The static pages
at homeroom.chelseakr.com are files on GitHub Pages with no server-side
behaviour of their own.


Scan configuration (SAST/SCA/secret-scan/container-CVE) lives in
`.github/workflows/ci.yml` and is specified by
`STANDARDS/SECURITY-AND-SUPPLY-CHAIN-STANDARD.md`, not here.
