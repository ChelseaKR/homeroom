# Deployment shape for the published site: prepared, not applied

**Nothing here has been applied.** There is no `homeroom-site` stack, no
bucket, no distribution, no IAM role and no certificate. `homeroom.chelseakr.com`
is still a CNAME to `chelseakr.github.io`, measured on 2026-09-05:

```
$ dig +short homeroom.chelseakr.com
chelseakr.github.io.
185.199.108.153
185.199.111.153
185.199.110.153
185.199.109.153
```

GitHub Pages serves every family reading these pages today.
`.github/workflows/pages.yml` is unchanged and still publishes after ci
succeeds on main. `.github/workflows/site-publish.yml` sits beside it and is
inert as committed: it is gated on four repository variables, none of which is
set, so it skips rather than runs. Setting them is step 4 below, and moving DNS
is step 7. Both are the owner's to do, deliberately, at a moment of their
choosing.

This directory is the shape that would be applied, sized against what the site
actually is, so that the decision can be made from measurements rather than
from a plan.

| | |
|---|---|
| Stack | `homeroom-site` (**does not exist**) |
| Region | `us-west-2` intended, to sit with `homeroom-ask` |
| Certificate | ACM, **`us-east-1`**, whatever region the stack is in |
| Origin | private S3 bucket, no public access, no ACLs, no website endpoint |
| Edge | CloudFront with Origin Access Control (not the legacy OAI) |
| Publish | `.github/workflows/site-publish.yml`, GitHub OIDC, no stored key |
| Today's host | GitHub Pages, untouched, and it stays that way until step 7 |

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

## What is NOT applied

Everything. Stated item by item, because "prepared" is a word that can hide a
half-finished deploy:

- No CloudFormation stack has been created, updated, validated against the
  live API, or deployed in any account.
- No S3 bucket exists and no byte of `site/` has been uploaded anywhere.
- No CloudFront distribution, cache policy, response-headers policy or origin
  access control exists.
- No IAM role, no OIDC provider, no trust policy.
- No ACM certificate has been requested.
- No DNS record has been created, changed, or deleted. `homeroom.chelseakr.com`
  resolves to GitHub Pages, as it has since 2026-08-22.
- No repository variable is set, so `site-publish.yml` skips on every run.
- `.github/workflows/pages.yml` is byte-for-byte unchanged and is still the
  deploy families receive.
- `site/` is unchanged and was not re-rendered or re-published.

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

A missing page stays missing. The two `CustomErrorResponses` entries set only
`ErrorCachingMinTTL: 10`; neither carries `ResponseCode` or `ResponsePagePath`,
so a request for a school that is not published gets the origin's own 404, not
a 200 carrying something else's bytes. Turning 404 into 200 is the most common
thing done to a static site behind a CDN and it would make the live sentinel
vacuous. Ten seconds rather than the 300-second default so that a 404 cached in
the gap between a delete and an upload does not outlive the publish that caused
it.

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
  behaviour and hides the cause completely, which is exactly how the CORS trap
  in `deploy/ask/template.yaml` behaved. `tools/ask-optin.mjs` proves that page
  in a DOM and cannot see a header added out here. Adding a CSP means first
  giving it something that can fail loudly.

`Referrer-Policy` is `same-origin`, not `no-referrer`. `same-origin` already
stops the URL of a named child's school page leaving with an outbound click.
`no-referrer` can cause a fetch's `Origin` header to be sent as `null` in some
paths, and the ask service refuses by origin — the same silent failure again.

**The publish role** is assumed through GitHub OIDC; no AWS access key exists
for it anywhere. Its trust policy pins
`token.actions.githubusercontent.com:sub` to
`repo:<owner/name>:ref:refs/heads/main`, so a pull request branch, a fork, and
every other repository on GitHub get nothing. Its permissions are the bucket
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

**Content-Type is stated, not guessed.** The site publishes five kinds:
`.html`, `.png`, `.xml`, `.txt`, and the extensionless `CNAME`. The CLI guesses
from the extension, which is right for four of them and gives `CNAME`
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

Six passes are written out rather than looped. A shell `for` loop exits with
only its last iteration's status and would swallow a failed upload in any
earlier one — the same reason `make secret-scan` runs its two scans as two
commands.

## Cutover, in order, with what to check after each step

Every step before 7 is invisible to families. Step 7 is the cutover.

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
  --domain-name homeroom.chelseakr.com --validation-method DNS
```

Add the `_<hash>.homeroom.chelseakr.com` validation CNAME at the DNS provider.
That is a new name; it does not touch the record the site resolves through.

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
  {"ParameterKey": "SiteDomain",       "ParameterValue": "homeroom.chelseakr.com"},
  {"ParameterKey": "GitHubRepository", "ParameterValue": "ChelseaKR/homeroom"},
  {"ParameterKey": "AttachDomain",     "ParameterValue": "false"}
]
```

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

It should print `serves exactly what this checkout publishes: 23310 of 23310
file(s) compared`. That is 868 MB pulled once, inside the free tier. This is
the strongest check available and it costs nothing to run before the cutover
rather than after.

**5. Deploy phase two — attach the domain.**

```json
[
  {"ParameterKey": "SiteDomain",       "ParameterValue": "homeroom.chelseakr.com"},
  {"ParameterKey": "GitHubRepository", "ParameterValue": "ChelseaKR/homeroom"},
  {"ParameterKey": "AttachDomain",     "ParameterValue": "true"},
  {"ParameterKey": "CertificateArn",   "ParameterValue": "arn:aws:acm:us-east-1:...:certificate/..."},
  {"ParameterKey": "HstsMaxAgeSeconds","ParameterValue": "300"}
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

**Nothing, and that was checked rather than assumed.** It keeps working against
the new origin unchanged, in both directions across the cutover, because it
grades a domain and the domain does not move.

Four things it needs, and where each comes from:

| What it requires | Why it holds here |
|---|---|
| A guaranteed-missing path answers **404**, never 200 or anything else (`prove_the_origin_discriminates`) | The `s3:ListBucket` grant in the bucket policy, plus `CustomErrorResponses` that pass the origin status through. This is the reason that grant exists |
| `/` serves `index.html` byte-for-byte | `DefaultRootObject: index.html`, which applies to the root regardless of the query string it appends |
| A response that is not `Content-Encoding`-transformed — it sends `Accept-Encoding: identity` and refuses anything but `identity` | CloudFront compresses only when the viewer asks for a compressed encoding. Objects are stored uncompressed, so the identity response is the committed bytes |
| Every file under `site/` is fetchable, `CNAME` included (`NOT_PUBLISHED` is empty) | Every file is synced, and `CNAME` is an ordinary object to this origin exactly as it is to GitHub Pages |

One behaviour genuinely changes, and it is not a problem: the
`?live-integrity=<nonce>` it appends stops busting the cache, because the cache
policy keys on the path alone. Freshness after a publish comes from the
invalidation the publish issues and waits for, not from the reader's ability to
bust a cache. The sentinel's three attempts with 20-second waits still cover the
tail.

`--url` is what makes step 4 above possible: the same code, pointed at the
`*.cloudfront.net` name, verifies the full 23,310-file origin before any DNS
change.

## `site/CNAME` becomes inert, and stays

CloudFront reads its alternate domain name from the stack, not from a file in
the bucket, so `site/CNAME` configures nothing on the new origin. It is still
uploaded, still served at `/CNAME` as `text/plain` exactly as GitHub Pages
serves it today, and still compared by the sentinel.

Keep it, for two reasons. It is what holds the custom domain configured in the
repository's Pages settings, which is half of why the rollback is one DNS
record. And `pages.yml` refuses to publish a tree without it — "publishing
would unset the custom domain" — so removing it would break the deploy that is
still the live one.

## Cost, measured

The byte counts here were measured on `site/` on 2026-09-05. The rates are
AWS's published list prices for `us-west-2` as understood when this was
written; re-read the pricing pages before relying on a total. The distinction
matters the way PROVENANCE.md's does: the arithmetic is measured, the unit
prices are not.

| | Measured | At list price |
|---|---|---|
| Objects | 23,310 | — |
| Bytes of content | 867,639,523 (0.808 GiB) | **$0.019/month** S3 Standard @ $0.023/GB-month |
| Superseded versions, worst case | one full generation for 30 days | +$0.019/month |
| A full republish | 23,310 PUTs | **$0.117** @ $0.005/1,000 |
| An invalidation | 1 path (`/*`) | **$0.000** — 1,000 paths/month are free |
| Origin fetches (S3 → CloudFront) | cache misses only | **$0.000** — AWS does not charge for this transfer |
| Daily live sentinel | 9.37 MB, 210 requests | within the free tier |
| A full `--sample 0` verification | 868 MB, 23,311 requests | within the free tier |

The steady state is **about two cents a month plus twelve cents per full
republish**, and CloudFront's always-free tier (1 TB out and 10,000,000
requests per month, not a 12-month trial) absorbs the serving.

`du -sm site` says 857 and the table says 867,639,523 bytes, and both are
right: `du` counts 4 KiB filesystem blocks, and 23,310 small files carry about
30 MiB of block slack that does not exist in a bucket. S3 bills content.

**What the traffic actually is: unknown, and unmeasurable from here.** GitHub
Pages gives the owner no access log, and this stack turns CloudFront logging
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
| S3 total bucket size, object count | none | 868 MB, 23,310 objects |
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

**Cloudflare Pages was not an option**, and not marginally: it caps a
deployment at **20,000 files**, and `site/` is **23,310**. The site exceeded
that limit before this question was asked, by 3,310 files, and the county and
district pages that made the site navigable are 2,234 of them. Its 25 MiB
per-file limit would have been fine; the file count is what rules it out, and no
amount of shrinking pages changes a file count.

## Before changing any of this, decide

- **Whether the change adds a record about a reader.** Access logs, a WAF with
  logging, real-user monitoring, and an analytics tag are all the same
  decision, and `docs/RESPONSIBLE-TECH-AUDITS.md` has to move before the
  exposure does, not after.
- **Whether it can fail silently in front of a family.** A CSP, a referrer
  policy, an error-response mapping and a cache TTL can each break a page while
  every gate stays green, because they live at the edge and this repository's
  checks read files. If the repository cannot see it fail, it needs something
  that can before it ships.
- **Whether the bytes committed are still the bytes served.** That property is
  what makes reviewing a diff equivalent to reviewing the site. Anything that
  transforms, minifies, redirects or rewrites on the way out breaks it.
