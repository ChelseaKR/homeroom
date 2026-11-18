# Deployment of the published site: S3 behind CloudFront, applied 2026-11-17

**This is applied.** `homeroom.chelseakr.com` is served by CloudFront from a
private S3 bucket, and has been since the DNS switch at 16:38:53 PST on
2026-11-17 (2026-11-18T00:38:53Z). The stack is `homeroom-site` in
`us-west-2`. Read back from the domain after the switch:

```
$ dig +noall +answer homeroom.chelseakr.com @1.1.1.1
homeroom.chelseakr.com.	60	IN	CNAME	d28my37ix3s050.cloudfront.net.
$ curl -sI https://homeroom.chelseakr.com/ | grep -i -E '^(HTTP|server|via|strict-transport|cache-control)'
HTTP/2 200
server: AmazonS3
cache-control: public, max-age=300, s-maxage=86400
via: 1.1 <an edge>.cloudfront.net (CloudFront)
strict-transport-security: max-age=300
```

**The decision** was the owner's, on 2026-09-18 (#82, option 1; recorded as
ADR 0008), because the D5 publish did not fit under this repository's budget
for GitHub Pages. **[`CUTOVER.md`](CUTOVER.md) is the commands as they were
run**, in order -- certificate, plan and apply of each phase, the four
variables, the first sync, verification on the `*.cloudfront.net` name, the
DNS switch, the flip of `served-by`, and the rollback -- with what each
should print and what the run found wrong in them. This file is the record
and the reasoning.

GitHub Pages no longer serves families. It is the rollback copy:
`.github/workflows/pages.yml` still deploys every tree that fits under the
Pages ceiling after ci succeeds on main, beside
`.github/workflows/site-publish.yml`, which syncs the same commit to the
bucket. Going back is one DNS record ("Rolling back", below).

`template.yaml` is what the stack is, including the page for a missing
address that was added later the same day ("Prepared, not applied", below, which
keeps its name and now records the date it was applied).

## As applied

| | |
|---|---|
| Stack | `homeroom-site`, `us-west-2`, beside `homeroom-ask`. Created 2026-11-17 by three change sets, each read before it was executed: phase one (seven `Add` rows), the publish role's subject (one `Modify`), and phase two (two `Modify` rows) |
| Distribution | `d28my37ix3s050.cloudfront.net`, with the alias `homeroom.chelseakr.com`, SNI, TLS 1.2 (2021 policy) at least |
| Certificate | ACM, **`us-east-1`**, for `*.chelseakr.com`, validated by DNS. The wildcard, because ACM may not issue for the site's own name while it is a CNAME to GitHub Pages (CUTOVER.md step 1) |
| Origin | one private S3 bucket: no public access, no ACLs, no website endpoint, versioned. Its name is the stack's `BucketName` output and is not written here, because it ends in the AWS account id |
| Edge | CloudFront with Origin Access Control (not the legacy OAI) |
| Publish | `.github/workflows/site-publish.yml`, GitHub OIDC, no stored key, as the role `homeroom-site-publish` |
| DNS | Route 53 zone `chelseakr.com`: `homeroom.chelseakr.com` is a CNAME to the distribution's name, TTL 60 |
| The switch | `deploy/site/served-by`, which says `cloudfront` |
| Rollback copy | GitHub Pages, kept current by `pages.yml` while the tree is under 1 GB |

The parameters as applied:

| Parameter | Value |
|---|---|
| `SiteDomain` | `homeroom.chelseakr.com` |
| `GitHubRepository` | `ChelseaKR/homeroom` |
| `GitHubOidcSubjectRepository` | `ChelseaKR@3114598/homeroom@1327291879` |
| `GitHubBranch` | `main` (the default) |
| `AttachDomain` | `true` |
| `CertificateArn` | the `*.chelseakr.com` certificate above. The ARN is not written here: every ARN carries the account id |
| `CreateOidcProvider` | `false`: the account already had GitHub's provider |
| `HstsMaxAgeSeconds` | `300`, the cautious first value; see below |
| `PriceClass`, `NoncurrentVersionDays` | the defaults, `PriceClass_100` and `30` |

The four repository variables (`SITE_S3_BUCKET`,
`SITE_CLOUDFRONT_DISTRIBUTION_ID`, `SITE_PUBLISH_ROLE_ARN`, `SITE_AWS_REGION`)
are set from the stack's outputs. Their values are not recorded here either:
two of them carry the account id.

**Proved before DNS moved:** `tools/verify_live_site.py --skip-rebuild
--sample 0 --url https://d28my37ix3s050.cloudfront.net/` printed `serves
exactly what this checkout publishes: 23312 of 23312 file(s) compared,
953659316 bytes, 21068 of them school pages`.

**Still at its cautious setting:** `Strict-Transport-Security` is 300 seconds
and the record's TTL is 60, so that a rollback takes effect in about a minute
and no browser is held to HTTPS for long if GitHub's certificate has lapsed.
Both go up once the daily sentinel has been green for a few days:
`HstsMaxAgeSeconds=31536000` in a change set that changes nothing else, and
the TTL back to 300.

## Why

`site/` is 857 MB as `du -sm` reports it, against the 1 GB GitHub Pages
documents as the maximum size of a published site. That is 84% of the cap, and
it got there in one day: 212 KB on the morning of 2026-09-05, then all 10,534
schools, then a county and district page for each of the 2,234 places a family
walks through to find their school.

The cap then stopped being a background number and started deciding what this
project may publish:

* The ask layer for every school is another **303 MB** — 21,068 pages, and the
  two published ask pages average 14,392 bytes each. 857 MB plus 303 MB is
  1.09 GiB, and it does not fit. (An earlier estimate of 299 MB is the same
  number measured slightly differently.)
* D4 (Dashboard indicators) and D6 (ESSA per-pupil expenditure) each add
  measures to all 23,310 pages. Neither is acquired yet and neither figure is
  guessable from here, but both are growth on the same 23,310 files.
* The one large saving available was to lift the ask page's inline CSS and
  script into shared files — 10,993 of its 14,206 bytes, so about 216 MB across
  the projected ask layer. That saving is not available, because those bytes
  being inline is the promise: `tools/ask-optin.mjs` loads each ask page in a
  DOM with every network path stubbed and asserts **zero requests on load**. An
  external stylesheet and an external script are two requests on load. The
  saving costs the guarantee, so it is not a saving.

The owner's decision is to move the host rather than keep shaving bytes. What
replaces the cap is money, and the numbers are below: at this size the origin
costs about two cents a month, and there is no total-size ceiling to grow into
at all.

## What is deliberately not applied

Stated item by item, because each is something a deployment like this usually
has and a reader would otherwise assume:

- No access log of any kind: no CloudFront standard or real-time log and no S3
  server access log. A viewer's address beside a school page's path is a
  record about a family, and this project keeps none ("The shape", below, and
  the hosting record in `docs/RESPONSIBLE-TECH-AUDITS.md`).
- No AWS WAF.
- No `Content-Security-Policy`. That is parity with GitHub Pages and open
  work, not a decision that one is unnecessary.
- No second OIDC provider: the account's existing one is trusted, and this
  stack does not own it.
- No access key anywhere. The publish role is assumed per run through OIDC.
- GitHub Pages was not unpublished, `pages.yml` was not removed, and
  `site/CNAME` was not deleted. Each is part of the rollback.
- `site/` was not re-rendered for the move. The bytes served are the bytes
  that were committed before it.

## Prepared, not applied: a page for a missing address

**The missing-page response was applied on 2026-11-17.** The template and
the page are in the repository, and the running distribution matches them: one
change set, `missing-page`, with one row (`Modify`, `Distribution`, no
replacement), read before it was executed. `tests/test_deploy_site_template.py`
holds this file to saying either that the response is prepared and not
applied, or the date it was applied.

**Checked afterwards, from outside.** Three made-up addresses (at the root,
under `county/`, and three levels deep) each answered `404` with
`text/html; charset=utf-8` and the page in both languages. The front door, a
school page in each language, `robots.txt` and `sitemap.xml` still answered
`200` with their own types, and `tools/verify_live_site.py` still passed.

**What a reader got before.** For about four hours after the domain moved,
any address with no page answered `404` with `content-type: application/xml`
and S3's error document: no title, no language, no heading, no link.

**What the change is.** Two lines on the 404 entry of the distribution's
`CustomErrorResponses`, `ResponseCode: 404` and `ResponsePagePath: /404.html`.
Nothing else in the template differs from what is applied.

- The status stays 404. It is never 200: `tools/verify_live_site.py` needs a
  guaranteed-missing path to answer 404, a crawler must not be handed a page
  for an address that has none, and
  `test_a_missing_address_answers_404_never_200` holds the template to it.
- The 403 entry is not touched. With `s3:ListBucket` granted, S3 answers a
  missing key with 404, and answers 403 only when CloudFront may not read an
  object that exists. That is a broken bucket policy or Origin Access Control,
  and it has to keep looking like one rather than like "this school is not
  published".
- Errors are still cached for 10 seconds.

**How the page gets into the bucket.** It is `site/404.html`, committed like
every other published file. `src/homeroom/missing.py` writes it and
`homeroom.analytics` adds the loader and the note, both addressed from the site
root because the page is served at whatever address was missing;
`tests/test_published_site.py` holds the committed file to those bytes.
`site-publish.yml` needs no change: its `*.html` pass uploads the file as
`text/html; charset=utf-8` with the same `Cache-Control` as every page, its
inventory comparison counts it, and its invalidation of `/*` covers it.
`pages.yml` deploys the same tree, and GitHub Pages serves a root `404.html`
for a missing address with no setting, so the rollback copy behaves the same
way without anything being applied there.

**The order.**

1. Merge. ci runs, then `site-publish.yml` puts `404.html` in the bucket and
   `pages.yml` puts it on GitHub Pages.
2. Check the page is there. Missing addresses still answer with XML at this
   point, which is expected.

   ```sh
   curl -sI https://homeroom.chelseakr.com/404.html | grep -i -E '^(HTTP|content-type)'
   # HTTP/2 200
   # content-type: text/html; charset=utf-8
   ```

3. Plan it. Every parameter keeps its applied value, so no ARN is typed:

   ```sh
   STACK=homeroom-site; export AWS_REGION=us-west-2
   aws cloudformation create-change-set --stack-name "$STACK" \
     --change-set-name missing-page --change-set-type UPDATE \
     --template-body file://deploy/site/template.yaml \
     --capabilities CAPABILITY_NAMED_IAM \
     --parameters \
       ParameterKey=SiteDomain,UsePreviousValue=true \
       ParameterKey=AttachDomain,UsePreviousValue=true \
       ParameterKey=CertificateArn,UsePreviousValue=true \
       ParameterKey=GitHubRepository,UsePreviousValue=true \
       ParameterKey=GitHubOidcSubjectRepository,UsePreviousValue=true \
       ParameterKey=GitHubBranch,UsePreviousValue=true \
       ParameterKey=CreateOidcProvider,UsePreviousValue=true \
       ParameterKey=HstsMaxAgeSeconds,UsePreviousValue=true \
       ParameterKey=PriceClass,UsePreviousValue=true \
       ParameterKey=NoncurrentVersionDays,UsePreviousValue=true
   aws cloudformation wait change-set-create-complete \
     --stack-name "$STACK" --change-set-name missing-page
   aws cloudformation describe-change-set --stack-name "$STACK" \
     --change-set-name missing-page \
     --query 'Changes[].ResourceChange.[Action,LogicalResourceId,ResourceType,Replacement]' \
     --output table
   ```

   Expected plan: **one row.** `Modify`, `Distribution`,
   `AWS::CloudFront::Distribution`, `Replacement` `False`. A second row means
   stop: a `SiteBucketPolicy` or `PublishRole` row says a parameter did not
   keep its value, and `Add`, `Remove` or `True` anywhere says this is not the
   change described here.

4. Apply it. CloudFront takes a few minutes to carry a change to every edge.

   ```sh
   aws cloudformation execute-change-set --stack-name "$STACK" --change-set-name missing-page
   aws cloudformation wait stack-update-complete --stack-name "$STACK"
   ```

5. Check it, from outside.

   ```sh
   D=https://homeroom.chelseakr.com
   # A missing address, at the root and three levels down: 404, and a page.
   for p in /no-such-page /county/no-such-county.en.html /a/b/c; do
     curl -s -o /tmp/missing.html -w "$p %{http_code} %{content_type}\n" "$D$p"
     grep -c -E '<section lang="(en|es)"' /tmp/missing.html     # 2
     grep -c -E 'Page not found|Página no encontrada' /tmp/missing.html   # 3 or more
   done
   # Real pages and the plain-text file are untouched.
   curl -s -o /dev/null -w "%{http_code} %{content_type}\n" "$D/"             # 200 text/html; charset=utf-8
   curl -s -o /dev/null -w "%{http_code} %{content_type}\n" "$D/57726786056246.en.html"   # 200 text/html; charset=utf-8
   curl -s -o /dev/null -w "%{http_code} %{content_type}\n" "$D/robots.txt"   # 200 text/plain; charset=utf-8
   curl -s -o /dev/null -w "%{http_code}\n" "$D/homeroom.css"                 # 200: the page's stylesheet, from the root
   # And the sentinel, which requires the guaranteed-missing path to be a 404.
   uv run python tools/verify_live_site.py
   ```

   Each missing address prints `404 text/html; charset=utf-8`. A `200` on any
   of them is the failure this section exists to prevent: roll back.

6. Record it: the sentence at the top of this section, and the paragraphs in
   "The shape" and "Headers" that say "as applied".

**The way back.** Check out the template as it was before this change and run
steps 3 and 4 again; the plan is the same single `Modify` row. Missing
addresses answer with S3's XML again within minutes. `site/404.html` can stay
where it is: with no error response naming it, it is an ordinary page nobody
links to, and it is what keeps GitHub Pages' copy answering the same way.

**If the change is applied before the page is in the bucket**, nothing a
reader sees gets worse: CloudFront cannot fetch the page it was told to send,
and by AWS's documentation returns the error status it has. That was not
tested here. Publishing first (step 1) means it never comes up.

## The shape

One S3 bucket, one CloudFront distribution, one publish role.

**The bucket** blocks all four kinds of public access, enforces bucket-owner
object ownership so there are no ACLs to get wrong, encrypts at rest, and has
no website endpoint. Nothing on the internet can reach it. Its policy allows
exactly two things to one principal: `s3:GetObject` on the objects and
`s3:ListBucket` on the bucket, both to `cloudfront.amazonaws.com` and both
conditioned on `AWS:SourceArn` being this distribution — the service principal
without that condition would let any CloudFront distribution in any AWS account
read it. A third statement denies everything not over TLS.

`s3:ListBucket` is there for one specific reason and it is worth knowing before
someone tidies it away. Without it, S3 answers a GET for a key that does not
exist with **403 AccessDenied** rather than 404 — it will not confirm absence
to a caller who may not list — and CloudFront passes the 403 through.
Everything real would work, and `tools/verify_live_site.py` would exit 4:
that file refuses to pass against an origin that answers a guaranteed-missing
path with anything but 404, "because a host that answers everything with 200
makes every comparison meaningless". CloudFront never issues a ListBucket
request. The grant changes which of two error codes S3 returns and nothing
else.

The bucket is versioned, with superseded versions expiring after 30 days. That
is not the record of what was served — git is — it is an undo for a sync that
went wrong, and it costs about two cents a month. It carries
`DeletionPolicy: Retain`, so deleting the stack cannot take the bytes families
are reading.

**The distribution** serves HTTPS only and redirects HTTP, with a minimum of
TLS 1.2 (2021 policy) once the domain is attached. `DefaultRootObject` is
`index.html`. Compression is on, which matters here: these pages are HTML and
compress about fivefold, so it is a fivefold cut in the only line of the bill
that can grow.

A missing page stays missing. As applied, the two `CustomErrorResponses`
entries set only `ErrorCachingMinTTL: 10`; neither carries `ResponseCode` or
`ResponsePagePath`, so a request for a school that is not published gets the
origin's own 404, not a 200 carrying something else's bytes. Turning 404 into
200 is the most common thing done to a static site behind a CDN and it would
make the live sentinel vacuous. Ten seconds rather than the 300-second default
so that a 404 cached in the gap between a delete and an upload does not outlive
the publish that caused it.

The origin's own 404 has a body, though, and it is S3's: an XML document that
begins `<Error><Code>NoSuchKey</Code>`, which a browser shows as a tree of
tags. The template now gives the 404 entry a page and keeps its status
(`ResponseCode: 404`, `ResponsePagePath: /404.html`); the 403 entry is
unchanged. That is the prepared change in the section above this one.

Caching is split between the two caches on purpose. Objects are published with
`Cache-Control: public, max-age=300, s-maxage=86400`: a day at the edge, five
minutes in a browser. An invalidation clears CloudFront and reaches no browser,
so the browser number is the one that decides how long a family can still be
looking at a page this project has already corrected. The cache key is the path
alone — no cookies, no headers, no query strings.

Two things are deliberately absent:

* **No access logs.** CloudFront standard logging records the viewer's IP and
  the exact path. On this site that pair reads "this address looked at this
  named school", which is a record about a family and their child that nothing
  in this project has ever kept. GitHub Pages gives the owner no access log
  either, so leaving it off is also what keeps the move invisible in the one
  way that matters. Turning it on is a change to
  `docs/RESPONSIBLE-TECH-AUDITS.md` first.
* **No Content-Security-Policy**, and that one is open work rather than a
  decision that it is unnecessary. A useful CSP would have to name the ask
  service's Function URL in `connect-src`. That host lives in a different
  stack, nothing in this repository could check the two still agree, and
  getting it wrong breaks the one page that carries a script — silently, in
  front of a family, showing the fixed "not available" string that is correct
  behavior and hides the cause completely, which is exactly how the CORS trap
  in `deploy/ask/template.yaml` behaved. `tools/ask-optin.mjs` proves that page
  in a DOM and cannot see a header added out here. Adding a CSP means first
  giving it something that can fail loudly.

`Referrer-Policy` is `same-origin`, not `no-referrer`. `same-origin` already
stops the URL of a named child's school page leaving with an outbound click.
`no-referrer` can cause a fetch's `Origin` header to be sent as `null` in some
paths, and the ask service refuses by origin — the same silent failure again.

**The publish role** is assumed through GitHub OIDC; no AWS access key exists
for it anywhere. Its trust policy pins
`token.actions.githubusercontent.com:sub`, with `StringEquals`, to
`repo:<owner>@<owner id>/<name>@<repository id>:ref:refs/heads/main`, so a
pull request branch, a fork, and every other repository on GitHub get nothing.
That is the subject as GitHub issues it for a repository on immutable subject
claims, which this one is; the ids mean a repository re-created under the same
name cannot inherit the trust. It is the `GitHubOidcSubjectRepository`
parameter, read from
`gh api repos/<owner>/<name>/actions/oidc/customization/sub` and never
composed from `owner/name`: the first publish, on 2026-11-17, was refused
because the role had been pinned to `repo:<owner>/<name>:ref:refs/heads/main`,
which GitHub does not issue here. The parameter's pattern now refuses that
form. Its permissions are the bucket
(list, get, put, delete) and `CreateInvalidation`/`GetInvalidation` on this one
distribution ARN — not `*`, which is how that grant is usually written and
would let a compromised run invalidate every distribution in the account.

## The publish path, and why it is a workflow

`.github/workflows/site-publish.yml`, triggered the way `pages.yml` is: after
ci concludes `success` on main, plus `workflow_dispatch`.

A `make` target was the alternative and it loses two things. The first is the
property `pages.yml` exists to carry — publishing only after ci succeeds is
what makes "a commit that fails the accessibility, parity or published-site
gates is never the one that reaches families" true, and a command run by hand
from a laptop cannot carry it. The second is the absence of keys: a local
target needs AWS credentials on a developer machine, where a workflow needs
only a short-lived OIDC token minted per run. The one thing a target was wanted
for — seeding the bucket by hand, before DNS moves — is `workflow_dispatch`,
running the same code as the automatic path rather than a second copy of it.

What the workflow has to preserve is that **the bytes committed are the bytes
served**, and three things follow from that.

**Deletions propagate.** A page removed from `site/` must stop being served.
Every sync pass carries `--delete`, whose filters apply to the bucket listing
as well as the local tree, so each pass removes the objects of its own kind
that the checkout no longer publishes; a sixth pass excludes all five kinds,
which leaves it nothing to upload and everything else to delete, so an object
of a kind this site does not publish goes too. Then the workflow lists the
bucket and diffs that against `find site -type f`, and fails on any difference
in either direction. That comparison, not the filter semantics, is the proof.

**Content-Type is stated, not guessed.** The site publishes six kinds today:
`.html`, `.png`, `.xml`, `.txt`, `.js` (the Google Analytics loader) and the
extensionless `CNAME`, and a seventh, `.css`, arrives with the first republish
after #98 (`homeroom.css`, the one shared stylesheet). The CLI guesses from the
extension, which is right for most of them and gives `CNAME`
`binary/octet-stream` — a file a browser offers to download. So each kind is
synced in its own pass with `--content-type`, and afterwards one object of each
kind is read back with `head-object` and its type asserted.

**A republish reaches readers.** One invalidation on `/*`, waited on. `/*` is a
single invalidation path; AWS gives 1,000 paths a month free and charges $0.005
each after that, so the wildcard is free at any plausible rate while naming the
23,310 changed pages individually would be about **$111 per publish**. Waiting
matters because the next thing to read the origin is the live sentinel, and a
comparison against an edge that has not turned over yet reports a difference
that is not there.

Eight passes are written out rather than looped. A shell `for` loop exits with
only its last iteration's status and would swallow a failed upload in any
earlier one — the same reason `make secret-scan` runs its two scans as two
commands.

## The switch: which origin serves the domain

`deploy/site/served-by` is one committed word naming the origin the domain
points at. `make publish`, `tests/test_published_limits.py` and `pages.yml` all
read it, through `homeroom.publish_limits`, so the three cannot hold the same
tree to different ceilings.

| `served-by` | `make publish` and the suite | `pages.yml` |
|---|---|---|
| `github-pages` (until 2026-11-17) | a budget under the 1 GB Pages ceiling: 900 MB (90%). For one day, 2026-11-17, it was 960 MB (96%), a temporary bridge so the D5 tree could be published before the cutover (ADR 0008) | deploys every tree; a tree Pages cannot take is an **error**, because families are on Pages |
| `cloudfront` (committed now, after the DNS switch) | no total-size budget, because S3 has none; the 100 MiB per-file limit still binds, because `site/` is committed | deploys the rollback copy when it fits under 1 GB, and **skips it with a warning** when it does not |

The flip came after DNS, never before, and a return would have to be made in
the same order. `pages.yml` enforces it: if
`served-by` says `cloudfront`, the tree does not fit, and the domain still
resolves to `*.github.io`, the run fails rather than leave families on an
older tree with every check green. The verdict and the upload are separate
jobs, so a skipped commit creates no `github-pages` deployment record for
`tools/deploy_staleness.py` to mistake for one that was served.

Once a tree over 1 GB is published, the rollback in "Rolling back" below
still works but serves the last tree GitHub Pages accepted, which is older. The
D5 tree is 1,060.9 MB without #98's shared stylesheet. With it, the tree
published on 2026-11-17 is 953.7 MB, so the Pages copy keeps receiving it,
with 46.3 MB to spare.

## Headers: GitHub Pages before the move, and this distribution

The GitHub Pages column was measured on 2026-09-18 with
`curl -sI https://homeroom.chelseakr.com/`. The other column is the template's
`ResponseHeadersPolicy` and the publish workflow's `--cache-control`, read
back from the domain after the switch on 2026-11-17:

| Header | GitHub Pages (2026-09-18) | This distribution |
|---|---|---|
| `Content-Security-Policy` | none | none -- parity, see "Two things are deliberately absent" |
| `Strict-Transport-Security` | none | `max-age=300` now; a year once the move has settled |
| `X-Content-Type-Options` | none | `nosniff` |
| `X-Frame-Options` | none | `DENY` |
| `Referrer-Policy` | none (the browser default) | `same-origin` |
| `Cache-Control` | `max-age=600` | `public, max-age=300, s-maxage=86400` |
| `Access-Control-Allow-Origin` | `*` | none; nothing on the site is fetched cross-origin |
| HTTP | 301 to HTTPS | 301 to HTTPS |

**Google Analytics is unaffected.** Neither origin sends a CSP, so nothing
blocks `https://www.googletagmanager.com` or the collection hosts; the loader
sends its own scrubbed `page_location` and `page_referrer`, so `same-origin`
costs it nothing; and `DENY` concerns framing, which GA does not use. The
allowlist a CSP would need is in "Before changing any of this" below.

Two behaviors differ that no header shows. GitHub Pages answers an
extensionless path (`/57726786056246.en`) with the `.html` page; S3 answers
404. Nothing this site links, lists in its sitemap or names as canonical is
extensionless. And a missing page on GitHub Pages was GitHub's own stock 404
page, where here it has been S3's short XML error body with the same 404
status, which is what `tools/verify_live_site.py` requires. Since 2026-11-17
the tree carries its own `404.html`: GitHub Pages serves it for a missing
address, and so does this distribution ("Prepared, not applied", above), so the two origins answer a missing address with the
same page and the same status.

## The cutover, in the order it was made, with what was checked after each step

All of this was done on 2026-11-17. It is kept, written as the instructions
it was, because it is why each step is where it is, and because a rollback
followed by a second cutover would walk it again. Every step before 7 was
invisible to families. Step 7 was the cutover. The exact commands, with the
plan output of each phase and what went wrong on the day, are in
[`CUTOVER.md`](CUTOVER.md), whose step numbers differ from these.

**0. Preflight, read-only.**

```sh
aws sts get-caller-identity
aws iam list-open-id-connect-providers   # decides CreateOidcProvider
```

If a provider for `token.actions.githubusercontent.com` is already listed,
leave `CreateOidcProvider=false` (the default). Creating a second one is an
error, and deleting this stack would delete a provider other stacks trust.

**1. Request the certificate, in `us-east-1`.**

```sh
aws acm request-certificate --region us-east-1 \
  --domain-name '*.chelseakr.com' --validation-method DNS
```

The wildcard, not `homeroom.chelseakr.com`, and not by preference. A CAA
lookup follows a CNAME, the site's record is a CNAME to `chelseakr.github.io`
until the cutover, and GitHub's CAA records do not allow Amazon to issue. A
certificate naming `homeroom.chelseakr.com` was requested on 2026-11-17 and
refused with `CAA_ERROR`. The wildcard is checked at `chelseakr.com`, which
has no CAA record, and it renews wherever the site's record points.

Its `_<hash>.chelseakr.com` validation CNAME is the same record a certificate
for `chelseakr.com` uses, and the zone already held it on 2026-11-17; add it
only if it is absent. Either way it does not touch the record the site
resolves through.

*Check:* `aws acm describe-certificate --region us-east-1 --certificate-arn <arn>
--query 'Certificate.Status'` returns `ISSUED`, and
`dig +short homeroom.chelseakr.com` is still `chelseakr.github.io.`

**2. Deploy phase one — the origin, on CloudFront's own name.**

Write the parameters to a file. Pass them from the file, not the `Key=Value`
shorthand: that shorthand's comma escaping is what put backslashes inside the
ARNs in `deploy/ask/`, and the stack deployed green with them.

`params.json` is in `.gitignore`, at any depth, and stays there. By phase two
this file carries the certificate ARN, and every ARN carries the AWS account
id; the template keeps the account out of the committed bytes with
`${AWS::AccountId}` on purpose, and a parameter file committed beside it would
undo that in one `git add`.

```json
[
  {"ParameterKey": "SiteDomain",                  "ParameterValue": "homeroom.chelseakr.com"},
  {"ParameterKey": "GitHubRepository",            "ParameterValue": "ChelseaKR/homeroom"},
  {"ParameterKey": "GitHubOidcSubjectRepository", "ParameterValue": "ChelseaKR@3114598/homeroom@1327291879"},
  {"ParameterKey": "AttachDomain",                "ParameterValue": "false"}
]
```

`GitHubOidcSubjectRepository` is what the publish role trusts, and it is read
from GitHub rather than written by hand:
`gh api repos/ChelseaKR/homeroom/actions/oidc/customization/sub --jq .sub_claim_prefix`,
without the leading `repo:`. It has no default and refuses `owner/name`.

```sh
aws cloudformation deploy --template-file deploy/site/template.yaml \
  --stack-name homeroom-site --region us-west-2 \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides file://deploy/site/params.json
aws cloudformation describe-stacks --stack-name homeroom-site \
  --region us-west-2 --query 'Stacks[0].Outputs'
```

*Check:* the stack is `CREATE_COMPLETE`, the outputs name a bucket, a
distribution id, a role ARN and a `*.cloudfront.net` name, and
`curl -sI https://<that name>/` answers 404 (the bucket is empty and the origin
already discriminates). `homeroom.chelseakr.com` is untouched.

**3. Set the four repository variables.** This is the step that arms
`site-publish.yml`; nothing publishes to AWS before it and everything does
after.

```sh
gh variable set SITE_S3_BUCKET                 --body <BucketName output>
gh variable set SITE_CLOUDFRONT_DISTRIBUTION_ID --body <DistributionId output>
gh variable set SITE_PUBLISH_ROLE_ARN          --body <PublishRoleArn output>
gh variable set SITE_AWS_REGION                --body us-west-2
```

*Check:* `gh variable list` shows all four. From here on, every commit ci passes
on main is published to **both** origins — GitHub Pages by `pages.yml` and S3 by
`site-publish.yml` — which is the overlap that makes the rollback a DNS record
and nothing else.

**4. Seed the bucket.** Actions → *site-publish* → Run workflow.

*Check:* the run's own steps assert the inventory and the content types. Then
prove the whole origin from a checkout, before anything points at it:

```sh
python3 tools/verify_live_site.py --skip-rebuild --sample 0 \
  --url https://<DistributionDomainName>/
```

It should print `serves exactly what this checkout publishes: 23312 of 23312
file(s) compared`. That is 954 MB pulled once, inside the free tier. This is
the strongest check available and it costs nothing to run before the cutover
rather than after.

**5. Deploy phase two — attach the domain.**

```json
[
  {"ParameterKey": "SiteDomain",                  "ParameterValue": "homeroom.chelseakr.com"},
  {"ParameterKey": "GitHubRepository",            "ParameterValue": "ChelseaKR/homeroom"},
  {"ParameterKey": "GitHubOidcSubjectRepository", "ParameterValue": "ChelseaKR@3114598/homeroom@1327291879"},
  {"ParameterKey": "AttachDomain",                "ParameterValue": "true"},
  {"ParameterKey": "CertificateArn",              "ParameterValue": "arn:aws:acm:us-east-1:...:certificate/..."},
  {"ParameterKey": "HstsMaxAgeSeconds",           "ParameterValue": "300"}
]
```

`HstsMaxAgeSeconds=300` for the first weeks is the cheap way back; see the
rollback section for why it matters. Raise it to `31536000` once the move has
settled.

*Check:* the distribution carries the alias, and the edge answers for the name
before any DNS says so:

```sh
curl -sI --connect-to homeroom.chelseakr.com:443:<DistributionDomainName>:443 \
  https://homeroom.chelseakr.com/
```

200, `content-type: text/html; charset=utf-8`, and a certificate for the
domain. `dig +short homeroom.chelseakr.com` is still `chelseakr.github.io.`

**6. Lower the DNS TTL** on the `homeroom.chelseakr.com` CNAME to 60 seconds,
and wait out the old TTL — ideally a day or more ahead of step 7. This is the
step that decides how fast the rollback is.

*Check:* `dig homeroom.chelseakr.com | grep -A1 'ANSWER SECTION'` shows the new
TTL, and the answer is still `chelseakr.github.io.`

**7. Move DNS.** Change the `homeroom.chelseakr.com` CNAME from
`chelseakr.github.io` to `<DistributionDomainName>`. This is the cutover, and
it is the first step a family can see.

*Check:*

```sh
dig +short homeroom.chelseakr.com
python3 tools/verify_live_site.py --skip-rebuild --sample 0
```

The second command takes **no `--url`**: `LIVE_URL` in that file is the domain,
the domain has not changed, and so the sentinel now grades the new origin with
no edit to any code. Watch the daily run
(`.github/workflows/live-integrity.yml`, 13:07 UTC) for a few days, then raise
the DNS TTL and `HstsMaxAgeSeconds` back up.

**8. Flip `deploy/site/served-by` to `cloudfront`**, in its own pull request,
after step 7 has checked out. That is what takes the total-size budget off
`make publish` and the suite, and what turns `pages.yml` from the deploy
families receive into the rollback copy. (The D5 tree itself had already been
published, on Pages, under the one-day 96% bridge.)

**Do not, as part of the cutover:** remove `.github/workflows/pages.yml`,
unpublish the GitHub Pages site, or delete `site/CNAME`. Each of those is what
makes the rollback one step, and none of them costs anything to keep.

## Rolling back

The rollback is one DNS record, and it is one record because of step 3: while
both workflows are armed, GitHub Pages has been receiving every commit the
whole time, so it is already serving the current site.

**1. Point the CNAME back** at `chelseakr.github.io`.

*Check:* `dig +short homeroom.chelseakr.com` is `chelseakr.github.io.`, then
`python3 tools/verify_live_site.py --skip-rebuild --sample 0` — again with no
`--url`, and again passing, because the sentinel grades whatever the domain
resolves to.

**2. If HTTPS fails after the record changes, this is why.** GitHub provisions
a Let's Encrypt certificate for the custom domain and renews it by checking
that the domain points at GitHub. While DNS points at CloudFront, that check
fails and the certificate eventually lapses. Rolling back after it has lapsed
means HTTP works and HTTPS does not for as long as re-provisioning takes — and
`Strict-Transport-Security` means a browser that has seen the header will not
fall back to HTTP. That is the whole reason `HstsMaxAgeSeconds` is a parameter
and the reason to deploy it at 300 first.

If it happens: point DNS back, then in the repository's Settings → Pages remove
the custom domain and re-add it, which forces re-provisioning; watch
`curl -sI https://homeroom.chelseakr.com/` until it answers. A rollback done
inside the certificate's remaining validity avoids all of this.

**3. Nothing else has to happen.** The AWS side can stay up indefinitely: it
costs about two cents a month and it keeps a verified second copy of the site.
Tear it down only when the decision is settled, and in this order:

```sh
gh variable delete SITE_S3_BUCKET                  # disarms site-publish.yml first
gh variable delete SITE_CLOUDFRONT_DISTRIBUTION_ID
gh variable delete SITE_PUBLISH_ROLE_ARN
gh variable delete SITE_AWS_REGION
aws cloudformation delete-stack --stack-name homeroom-site --region us-west-2
```

Unsetting the variables first is not cosmetic: with them still set, the next
merge to main starts a publish into a bucket that is being deleted. The bucket
itself is `Retain` and survives the delete; emptying it
(`aws s3 rm s3://<bucket> --recursive`) is a separate, deliberate step, and
because the bucket is versioned that leaves delete markers until the 30-day
lifecycle rule expires them.

## What changes for `tools/verify_live_site.py`

**Nothing, and that was checked rather than assumed.** It works against the
new origin unchanged, as it would in the other direction across a rollback,
because it grades a domain and the domain did not move. On 2026-11-17 the same
code passed against the `*.cloudfront.net` name before the switch and against
the domain after it.

Four things it needs, and where each comes from:

| What it requires | Why it holds here |
|---|---|
| A guaranteed-missing path answers **404**, never 200 or anything else (`prove_the_origin_discriminates`) | The `s3:ListBucket` grant in the bucket policy, plus `CustomErrorResponses` that never change the status: as applied they pass it through, and the prepared 404 entry names a page and states `ResponseCode: 404`. The sentinel reads the status and not the body, so it passes either way. This is the reason that grant exists |
| `/` serves `index.html` byte-for-byte | `DefaultRootObject: index.html`, which applies to the root regardless of the query string it appends |
| A response that is not `Content-Encoding`-transformed — it sends `Accept-Encoding: identity` and refuses anything but `identity` | CloudFront compresses only when the viewer asks for a compressed encoding. Objects are stored uncompressed, so the identity response is the committed bytes |
| Every file under `site/` is fetchable, `CNAME` included (`NOT_PUBLISHED` is empty) | Every file is synced, and `CNAME` is an ordinary object to this origin exactly as it is to GitHub Pages |

One behavior genuinely changes, and it is not a problem: the
`?live-integrity=<nonce>` it appends stops busting the cache, because the cache
policy keys on the path alone. Freshness after a publish comes from the
invalidation the publish issues and waits for, not from the reader's ability to
bust a cache. The sentinel's three attempts with 20-second waits still cover the
tail.

`--url` is what made step 4 above possible: the same code, pointed at the
`*.cloudfront.net` name, verified the full 23,312-file origin before any DNS
change. A full pass is slow from a laptop, about 75 minutes: the tool opens
one connection per file, and one fetch that times out starts the whole
comparison again (three attempts). Keep the machine awake and on power.

## `site/CNAME` becomes inert, and stays

CloudFront reads its alternate domain name from the stack, not from a file in
the bucket, so `site/CNAME` configures nothing on the new origin. It is still
uploaded, still served at `/CNAME` as `text/plain` exactly as GitHub Pages
served it, and still compared by the sentinel.

Keep it, for two reasons. It is what holds the custom domain configured in the
repository's Pages settings, which is half of why the rollback is one DNS
record. And `pages.yml` refuses to publish a tree without it — "publishing
would unset the custom domain" — so removing it would break the deploy that
keeps the rollback copy.

## Cost, measured

The byte counts here were measured on `site/` on 2026-09-05. The rates are
AWS's published list prices for `us-west-2` as understood when this was
written; re-read the pricing pages before relying on a total. The distinction
matters the way PROVENANCE.md's does: the arithmetic is measured, the unit
prices are not.

| | Measured | At list price |
|---|---|---|
| Objects | 23,313 | — |
| Bytes of content | 953,662,280 (0.888 GiB) | **$0.022/month** S3 Standard @ $0.023/GB-month |
| Superseded versions, worst case | one full generation for 30 days | +$0.022/month |
| A full republish | 23,313 PUTs | **$0.117** @ $0.005/1,000 |
| An invalidation | 1 path (`/*`) | **$0.000** — 1,000 paths/month are free |
| Origin fetches (S3 → CloudFront) | cache misses only | **$0.000** — AWS does not charge for this transfer |
| Daily live sentinel | 9.37 MB, 210 requests | within the free tier |
| A full `--sample 0` verification | 954 MB, 23,313 requests | within the free tier |

The steady state is **about two cents a month plus twelve cents per full
republish**, and CloudFront's always-free tier (1 TB out and 10,000,000
requests per month, not a 12-month trial) absorbs the serving.

One thing to measure now that it is running, because it decides how often
that twelve cents is paid. `site-publish.yml` runs on every commit ci passes
on main, whether or not the commit touched `site/`. `aws s3 sync` uploads a
file whose local modification time is newer than the object's, and a fresh
checkout's files are all newer, so each run is expected to be a full
republish: twelve cents, and one more superseded generation kept for 30 days.
The workflow's header says as much. It has not been measured on a second run;
the first publish after this record is where to read it.

`du -sm site` says 955 and the table says 953,662,280 bytes, and both are
right: `du` counts 4 KiB filesystem blocks, and 23,313 small files carry about
45 MiB of block slack that does not exist in a bucket. S3 bills content.
(Re-measured 2026-09-17, after Google Analytics added a script tag and a note to
every page and `analytics.js` to the root, and again on 2026-09-18 after the front
door gained its two-line link to the source, 436 bytes. The two tables' counts
and this paragraph were re-measured on 2026-11-17, after the publish that put
the teaching-assignment section and the search titles on every school page and
moved the stylesheet into `homeroom.css`, and once more the same day when the
missing page, `404.html`, added one file of 2,964 bytes; the traffic paragraph
below was not.)

**What the traffic actually is: unknown, and unmeasurable from here.** GitHub
Pages gave the owner no access log, and this stack turns CloudFront logging
off on purpose (above). So the honest statement is the headroom rather than the
usage. A school page averages 40,163 bytes uncompressed and the pages carry no
external asset, so one page view is one request; the free tier's 10,000,000
requests bind before its 1 TB does, at roughly **10 million page views a
month**. Past that, a further million page views is about 40 GB, or **$3.40**
at $0.085/GB.

Two lines that are not on this list: no Route 53 hosted zone, because
`homeroom.chelseakr.com` is a subdomain and a plain CNAME at whatever provider
holds `chelseakr.com` reaches CloudFront (only an apex would need an alias
record); and no AWS WAF, which is about $5/month plus per-request before it
inspects anything, against an origin that serves static files and cannot be
injected into.

## Limits, so the next person knows the new ceiling

The old ceiling was one number: 1 GB, total, for the whole published site. **The
new host has no equivalent.** An S3 bucket has no limit on total size and no
limit on the number of objects. What is left are per-object and per-operation
limits, and the site is nowhere near any of them:

| Limit | Value | This site |
|---|---|---|
| S3 total bucket size, object count | none | 954 MB, 23,313 objects |
| S3 maximum object size | 5 TiB | 1,821,378 bytes (`sitemap.xml`, the largest file) |
| S3 single-PUT size (the CLI multiparts above 8 MiB) | 5 GiB | as above |
| CloudFront maximum object size for a GET | 30 GB | as above |
| CloudFront alternate domain names per distribution | 100 | 1 |
| CloudFront requests per second per distribution | 250,000 (soft) | not measurable; see above |
| CloudFront invalidation paths per request | 3,000 | 1 (`/*`) |
| Free invalidation paths per month | 1,000 | 1 per publish |

So the binding constraint stops being bytes and becomes money, and the money is
two cents a month. Publishing the ask layer for every school — the thing that
does not fit today — would take the origin to 1.09 GiB and about $0.027 a
month.

**Cloudflare Pages was not an option** on its free plan, and not marginally:
the free plan caps a site at **20,000 files**, and `site/` is **23,313**. The
site is over that limit by 3,313 files, was over it before this question was
asked, and the county and district pages that made the site navigable are
2,234 of them.
Its 25 MiB per-file limit would have been fine; the file count is what rules it
out, and no amount of shrinking pages changes a file count.

Corrected 2026-11-17: Cloudflare's paid plans allow 100,000 files (Pages on a
paid zone plan, or Workers static assets on Workers Paid at $5 a month), so a
paid Cloudflare account would hold the site. It was still not chosen: about a
hundred times this origin's cost, a new vendor and subprocessor record, and no
prepared rollback. ADR 0008 lists it with the other options.

## Before changing any of this, decide

- **Whether the change adds a record about a reader.** Access logs, a WAF with
  logging, real-user monitoring, and an analytics tag are all the same
  decision, and `docs/RESPONSIBLE-TECH-AUDITS.md` has to move before the
  exposure does, not after. The analytics tag has since been decided: Google
  Analytics 4, on the owner's 2026-09-17 decision, with its own subprocessor
  record there. A CSP on this distribution would have to allow
  `https://www.googletagmanager.com` for scripts and
  `https://*.google-analytics.com` and `https://*.analytics.google.com` for
  connect and img.
- **Whether it can fail silently in front of a family.** A CSP, a referrer
  policy, an error-response mapping and a cache TTL can each break a page while
  every gate stays green, because they live at the edge and this repository's
  checks read files. If the repository cannot see it fail, it needs something
  that can before it ships.
- **Whether the bytes committed are still the bytes served.** That property is
  what makes reviewing a diff equivalent to reviewing the site. Anything that
  transforms, minifies, redirects or rewrites on the way out breaks it.
