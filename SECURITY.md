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

Scan configuration (SAST/SCA/secret-scan/container-CVE) lives in
`.github/workflows/ci.yml` and is specified by
`STANDARDS/SECURITY-AND-SUPPLY-CHAIN-STANDARD.md`, not here.
