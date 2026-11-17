# 0008. Serve the published site from S3 behind CloudFront, and keep GitHub Pages as the way back

Status: Accepted (owner decision, 2026-09-18, issue #82 option 1). Not applied: `deploy/site/served-by` says `github-pages`, and no stack, bucket, distribution, certificate or DNS change exists.
Date: 2026-11-17
Deciders: Chelsea Kelly-Reif (decided 2026-09-18; recorded here 2026-11-17)
Relates to: ADR 0001, which is not amended: the pages stay static and
rendered by the same renderer, and the bytes committed under `site/` are the
bytes served. ADR 0005, whose teacher-assignment section is the growth that
forced this. The search-title decisions waiting on open branches reach readers
only with the next full publish, which this decision unblocks.

## Context

`.github/workflows/pages.yml` uploads the committed `site/` tree to GitHub
Pages and builds nothing. GitHub documents 1 GB as the most a published Pages
site may weigh, and `src/homeroom/publish_limits.py` holds every publish to
90% of that, so that a tree near the cliff is refused while there is still time
to decide something.

The committed tree is 877,171,581 bytes in 23,311 files. ADR 0005 puts the
teacher-assignment section on all 21,068 school pages, a measured 8,723 bytes
each (#82). Rendered in full on 2026-11-17 from `origin/main` with both
search-title branches merged in, the next `make publish` is
**953,659,316 bytes in 23,312 files**: 95.4% of the
Pages ceiling and over the 900 MB budget, so `make publish` refuses it while
`served-by` says `github-pages`. Nothing in the repository is wrong; the gate
is doing what #75 wrote it to do.

Nine open issues add bytes to every page (#82's triage lists them), and the
ask layer for every school is another 303 MB. Whatever is decided has to
leave room for those, not only for D5.

## Options considered

1. **Move the domain to the S3 + CloudFront origin in `deploy/site/`.** No
   total-size ceiling. Same URLs, same bytes, same domain. About $0.02 to
   $0.05 a month in storage plus about $0.12 per full republish; serving sits
   inside CloudFront's always-free 1 TB and 10 million requests a month. The
   owner runs `deploy/site/CUTOVER.md` once, about an hour of commands.
2. **Stay on GitHub Pages and raise the budget from 90% to 96%.** Free and
   immediate, and the tree fits under the hard ceiling with about
   46 MB to spare, and about 6 MB under the raised budget. Every one of the nine gated features is then
   blocked again by the first of them to land, and the next refusal would come
   from GitHub at deploy time instead of from this repository beforehand.
3. **Republish without `--assignments`.** Contradicts ADR 0005 and needs its
   own record.
4. **Take an existing section off every school page.** 184 MB is more than
   the county and district trees together; this is removing content to pay
   for content.
5. **Split the site across several Pages sites.** Each repository gets one
   site. Splitting by language or by county moves half of the URLs to another
   host, and GitHub Pages cannot answer the old ones with a 301. That resets
   search for the moved half.
6. **Cloudflare Pages or Workers static assets.** 20,000 files on the free
   plan, which the site passed at 23,311; 100,000 on Workers Paid, which is
   $5 a month, a new vendor and a new subprocessor record. It would work, at
   about a hundred times the AWS cost, with no rollback path prepared.
7. **Build the site in Actions instead of committing it.** The 1 GB ceiling
   applies to the artifact Pages serves, not to the repository, so this does
   not change the arithmetic. It also cannot run: the pages are rendered from
   CDE files acquired by hand into `data/raw/`, and CI never touches the
   network (AGENTS.md).

## Decision

Option 1. The domain moves to the origin in `deploy/site/template.yaml`,
published by `.github/workflows/site-publish.yml` after ci succeeds on `main`,
through a GitHub OIDC role with no stored key.

`deploy/site/served-by` is the switch. It says `github-pages` until DNS has
moved and the live sentinel has passed against the new origin, and only then
`cloudfront`, in its own pull request. While it says `github-pages`, the 900 MB
budget holds exactly as before. Once it says `cloudfront`, `make publish` and
the suite hold the tree to no total-size budget, because S3 has none; the
100 MiB per-file limit still binds, because `site/` is committed.

`pages.yml` stays. It keeps deploying every tree that fits under the Pages
ceiling, so the rollback is one DNS record back to `chelseakr.github.io`.
When a tree no longer fits, `pages.yml` skips it with a warning, and from then
on the rollback serves the last tree Pages accepted.

## Consequences

- URLs, canonical links, hreflang, `sitemap.xml` and `robots.txt` do not
  change, because the domain and the bytes do not change. The Search Console
  domain property `sc-domain:chelseakr.com` already covers the subdomain.
- Two behaviors differ at the edge: an extensionless path such as
  `/57726786056246.en` is a 404 on S3 where Pages served the `.html` page, and
  a missing page returns S3's short XML body instead of Pages' 404 page, with
  the same 404 status. Nothing the site links, lists or names as canonical is
  extensionless.
- The distribution keeps no access log, as Pages kept none. Turning one on is
  a change to `docs/RESPONSIBLE-TECH-AUDITS.md` first.
- A second AWS stack exists to look after. `DeletionPolicy: Retain` on the
  bucket means deleting the stack cannot take the bytes families read.
- When `served-by` flips, this ADR's status line is rewritten in the same pull
  request with the date DNS moved. `tests/test_hosting_decision.py` fails until
  it is.

## What would reopen this

A bill that stops being cents (under consolidated billing the CloudFront
always-free tier is, as understood here, one allowance for the whole AWS
organization rather than one per stack), a CloudFront change that breaks the byte-for-byte check in
`tools/verify_live_site.py`, or a decision to record readers that the current
host does not.
