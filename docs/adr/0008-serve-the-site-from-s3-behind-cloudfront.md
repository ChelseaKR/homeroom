# 0008. Serve the published site from S3 behind CloudFront, and keep GitHub Pages as the way back

Status: Accepted (owner decision, 2026-09-18, issue #82 option 1; bridge added by owner decision 2026-11-17). Applied 2026-11-17: DNS moved to the CloudFront distribution at 16:38 PST (2026-11-18T00:38:53Z), and `deploy/site/served-by` says `cloudfront`. GitHub Pages is the rollback copy. The temporary bridge that held the tree to 96% of the Pages ceiling ended with the flip, and the budget is 90% again.
Date: 2026-11-17
Deciders: Chelsea Kelly-Reif (move decided 2026-09-18; bridge decided and both recorded here 2026-11-17; DNS switched 2026-11-17)
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
**953,659,316 bytes in 23,312 files**: 95.4% of the Pages ceiling and 53.7 MB
over the 900 MB budget, so `make publish` refused it while `served-by` said
`github-pages`. Nothing in the repository was wrong; the gate was doing what
#75 wrote it to do.

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
   immediate. The tree fits under the hard ceiling with 46.3 MB to spare and
   under the raised budget with 6.3 MB. As a place to stay it fails: every one
   of the nine gated features is blocked again by the first of them to land,
   and most of the margin that let this repository refuse a tree before GitHub
   did is spent. As a way to publish before option 1 is run, it is what was
   chosen; see "The bridge" below.
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

Option 1, with option 2 as a temporary bridge until it is applied. The domain
moves to the origin in `deploy/site/template.yaml`,
published by `.github/workflows/site-publish.yml` after ci succeeds on `main`,
through a GitHub OIDC role with no stored key.

`deploy/site/served-by` is the switch. It says `github-pages` until DNS has
moved and the live sentinel has passed against the new origin, and only then
`cloudfront`, in its own pull request. While it says `github-pages`, a
total-size budget under the Pages ceiling holds. Once it says `cloudfront`,
`make publish` and the suite hold the tree to no total-size budget, because S3
has none; the 100 MiB per-file limit still binds, because `site/` is committed.

### Applied (2026-11-17)

The move was made the same day as the bridge publish. The owner chose to switch
that day rather than a day after the TTL was lowered.

- **DNS.** The `homeroom.chelseakr.com` CNAME went from `chelseakr.github.io`
  to the distribution's `*.cloudfront.net` name at 16:38:53 PST
  (2026-11-18T00:38:53Z), with a TTL of 60 seconds. Both public resolvers
  checked returned the new name about 70 seconds later.
- **Before the switch**, `tools/verify_live_site.py --sample 0` compared all
  23,312 files on the `*.cloudfront.net` name with the committed tree, byte
  for byte, and they matched.
- **After it**, the domain answers from the new origin: 200 over HTTPS with
  the headers `deploy/site/README.md` lists, 301 from plain HTTP, 404 for a
  page that does not exist, and the sentinel run against the domain compared
  410 files and found no difference.
- **The switch file** says `cloudfront`, in the pull request that followed.
  The bridge ended there: `SITE_BUDGET_SHARE` is `PUBLISHED_BUDGET_SHARE`
  again.
- **What is still at its cautious setting:** `Strict-Transport-Security` is
  300 seconds and the record's TTL is 60, so that a rollback is quick. Both
  go up once the daily sentinel has been green for a few days
  (`deploy/site/CUTOVER.md`, "Rollback").

The sections below are the decision as it was written before the move, and
they are left in its tense.

### Two things the cutover found (2026-11-17)

Neither changes the decision; both change how it is carried out, and both are
recorded here because each was chosen rather than forced.

- **The certificate is a wildcard, `*.chelseakr.com`.** ACM refused a
  certificate naming `homeroom.chelseakr.com` with `CAA_ERROR`: a CAA lookup
  follows the record's CNAME to GitHub Pages, whose CAA records do not allow
  Amazon. The owner chose the wildcard, which is checked at `chelseakr.com`,
  over changing the type of the live record before the cutover.
- **The publish role is pinned to GitHub's immutable subject**, the form that
  carries the owner's and the repository's ids. The repository issues that
  form, the role had been pinned to `owner/name`, and the first publish was
  refused. The owner chose to keep immutable subjects on and change the
  template, which now takes the subject as a parameter and refuses the
  `owner/name` form.

### The bridge

On 2026-11-17 the owner chose to publish the next tree on GitHub Pages now and
run the cutover after, in two sittings, rather than hold approved search titles
and the D5 section back until the move. The budget is what stood in the way,
not the host: GitHub accepts a 953.7 MB site.

So `SITE_BUDGET_SHARE` in `src/homeroom/publish_limits.py`, the share of the
Pages ceiling the tree is held to, is **96% (960.0 MB) instead of 90%
(900.0 MB)**. It is a temporary bridge and it is bounded three ways:

- **By size.** It admits 953,659,316 bytes with 6.3 MB to spare and still
  refuses 40 MB short of the ceiling. It was raised for one measured tree, not
  to make room for the next feature. A tree that does not fit under it waits
  for the cutover.
- **By scope.** Only the tree's budget moved. `PUBLISHED_BUDGET_SHARE` is
  still 0.90 and the two sitemap budgets still use it.
- **By time.** It ends at the `served-by` flip. Once the switch says
  `cloudfront` no total-size budget is applied at all, and the pull request
  that flips it sets `SITE_BUDGET_SHARE` back to `PUBLISHED_BUDGET_SHARE`.
  `tests/test_hosting_decision.py` fails that pull request until it does, so
  the 96% cannot outlive its reason. If the switch is ever pointed back at
  `github-pages` with a tree over 900 MB, that is a new decision with its own
  record, not this one resumed.

What the bridge costs while it lasts: the next refusal for size is 40 MB from
GitHub's own, where it used to be 100 MB. That is the margin being spent, on
purpose, for the weeks between the two.

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
  request with the date DNS moved, and the bridge's 96% goes back to 90%.
  `tests/test_hosting_decision.py` fails until both are done.
- While the bridge lasts, none of the nine per-page features in #82's triage
  can be published. They wait for the cutover, which is the point of it.

## What would reopen this

A bill that stops being cents (under consolidated billing the CloudFront
always-free tier is, as understood here, one allowance for the whole AWS
organization rather than one per stack), a CloudFront change that breaks the byte-for-byte check in
`tools/verify_live_site.py`, or a decision to record readers that the current
host does not.
