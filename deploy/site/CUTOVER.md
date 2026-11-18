# Moving homeroom.chelseakr.com to S3 + CloudFront: the owner's commands

The owner decided on 2026-09-18 to move hosting to the origin in this directory
(issue #82, option 1; the decision record is ADR 0008). **Every step below was
run on 2026-11-17, and the domain has been served by CloudFront since 16:38:53
PST that day (2026-11-18T00:38:53Z).** "Where this stands" says what was run,
what the run found wrong in these commands, and what is still to do. The
commands are kept as they were run, in order, from a checkout of `main` at the
repository root: they are the record, and a rollback followed by a second
cutover would use them again.

`README.md` beside this file is the applied record and the reasoning: the
shape, the parameters, the costs, the limits, the rollback. This file is only
the commands, with what each one should print. Everything before step 8 was
invisible to families.

## Where this stands (2026-11-17)

Run that day, on the owner's authorization, in this order:

| Step | Result |
|---|---|
| 0 | Done. The account is the `homeroom-ask` one; the zone is there. |
| 1 | **Failed as first written**, then done another way. A certificate naming `homeroom.chelseakr.com` was refused with `CAA_ERROR` (why is in step 1). That request and its validation record were deleted. A certificate for `*.chelseakr.com` was requested instead and issued. |
| 2 | Done. The `phase-1` change set showed the seven `Add` rows and nothing else. Stack `homeroom-site` reached `CREATE_COMPLETE`, and its `*.cloudfront.net` name answered 404 from the empty bucket. |
| 3 | Done. All four variables are set, so `site-publish.yml` is armed. |
| 4 | **Failed the first time.** The run could not assume the publish role: "Not authorized to perform sts:AssumeRoleWithWebIdentity". Nothing was uploaded. |
| 2b | Done, after the template was fixed (#181). The `role-subject` change set showed one `Modify` row, `PublishRole`, no replacement. |
| 4 again | Done. The run that followed the merge of #181 was green: `23312 files, and the bucket holds exactly those`, and every content type as stated. |
| 5 | Done. `serves exactly what this checkout publishes: 23312 of 23312 file(s) compared, 953659316 bytes, 21068 of them school pages`, on the third attempt (see step 5). The headers were as listed. |
| 6 | Done. The `phase-2` change set showed the two `Modify` rows, no replacement and no third row. The edge answered 200 for the domain's name over the `*.chelseakr.com` certificate, with `strict-transport-security: max-age=300`. |
| 7 | Done at 2026-11-18T00:30:53Z. TTL 60, target unchanged. |
| 8 | Done at 2026-11-18T00:38:53Z (16:38:53 PST on 2026-11-17), eight minutes after step 7, on the owner's decision to switch that day. Both public resolvers checked returned the `*.cloudfront.net` name about 70 seconds later. The domain answered 200 with `server: AmazonS3` and a `via` naming CloudFront, plain HTTP answered 301, a made-up page answered 404, and the sentinel with no `--url` compared 410 files and found no difference. |
| 9 | The flip: `served-by` says `cloudfront`, `SITE_BUDGET_SHARE` is 90% again, and the records are rewritten, in one pull request. The `make publish` at its end was not needed: the D5 tree had already been published under the bridge. |

Why step 4 failed the first time: this repository issues GitHub's immutable
OIDC subject claims, so the token's subject was
`repo:ChelseaKR@3114598/homeroom@1327291879:ref:refs/heads/main` (read back
from CloudTrail's record of the refused call), and the role's condition had
been written from `owner/name` as
`repo:ChelseaKR/homeroom:ref:refs/heads/main`. The template now takes the
subject as its own parameter, `GitHubOidcSubjectRepository`, and refuses the
`owner/name` form. A stack created from this file as it now reads never needs
step 2b.

**Still to do, a few days on**, once the daily sentinel
(`.github/workflows/live-integrity.yml`) has been green since the switch. Both
are in "Rollback" below:

- a change set that changes only `HstsMaxAgeSeconds`, from `300` to
  `31536000`;
- the record's TTL from 60 back to 300.

And one check that is the owner's and was not made on the day: load a school
page in a browser with Do Not Track and Global Privacy Control off, and confirm
the Google Analytics request in the network panel.

## Why now

The next `make publish` carries D5, the teaching-assignment section ADR 0005
publishes on every school page. Measured 2026-09-18: `site/` is 877.2 MB
(877,171,581 bytes, 23,311 files) and D5 adds 8,723 bytes to each of 21,068
school pages, so the render is **1,060.9 MB, 106% of the 1 GB GitHub Pages
allows**. With #98's shared stylesheet it is about 943.8 MB: under the Pages
ceiling but over this repository's 900 MB budget, so `make publish` still
refuses it while GitHub Pages is the origin. After the move there is no
total-size ceiling at all. Rendered in full on 2026-09-18 with #98 and the
#131 fix, which prints FTE counts at the file's own precision, the tree is
**944.0 MB (944,014,201 bytes, 23,312 files)**: `publish-limits` passes it as
served by CloudFront, and at 94.4% of 1 GB the Pages rollback copy still fits.

Re-rendered in full on 2026-11-17 from `main` at `392b653c`, with the two
search-title branches (`seo/titles-hreflang`, `seo/landing-titles`) merged in
so the tree is the one the next publish would write: **953.7 MB (953,659,316 bytes,
23,312 files)**, 95.4% of 1 GB. `publish-limits` refuses it while `served-by`
says `github-pages` (53.7 MB over the 900 MB budget) and passes it as served
by CloudFront; the Pages rollback copy still fits, with 46.3 MB to spare.

That tree was published to GitHub Pages on 2026-11-17 under the temporary 96%
budget (ADR 0008), so `site/` is now those 953,659,316 bytes in 23,312 files,
with 6.3 MB of that budget left. The move below is still to be made.

## What was checked read-only on 2026-09-18

| | |
|---|---|
| Account | the `homeroom-ask` account, region `us-west-2` |
| GitHub OIDC provider | **already exists**, so `CreateOidcProvider=false` |
| Stack `homeroom-site` | does not exist |
| Certificate for `homeroom.chelseakr.com` | none; the account's `chelseakr.com` certificate covers the apex and `www` only |
| DNS | Route 53 zone `chelseakr.com`; `homeroom.chelseakr.com` is a `CNAME` to `chelseakr.github.io`, TTL 300 |
| Repository variables | none set, so `site-publish.yml` skips every run and `required configuration` is red |
| Template | `aws cloudformation validate-template` accepts it (needs `CAPABILITY_NAMED_IAM`); `cfn-lint` 1.46.0 reports nothing |

Two things that table did not check, and each stopped the run on 2026-11-17:

| | |
|---|---|
| CAA, through the CNAME | `dig +short CAA homeroom.chelseakr.com` follows the CNAME to `chelseakr.github.io` and returns GitHub's records, which allow Let's Encrypt, DigiCert and Sectigo and not Amazon. `dig +short CAA chelseakr.com` prints nothing, and the zone holds no CAA record. |
| The OIDC subject GitHub issues | `gh api repos/ChelseaKR/homeroom/actions/oidc/customization/sub` says `use_immutable_subject: true` with `sub_claim_prefix` `repo:ChelseaKR@3114598/homeroom@1327291879`, not `repo:ChelseaKR/homeroom` |

## The switch that kept GitHub Pages serving

`deploy/site/served-by` said `github-pages` until step 9. While it did,
`pages.yml` deployed every commit to GitHub Pages exactly as before,
`make publish` held the render to the Pages ceiling, and a tree Pages could
not take was an error. **It changed to `cloudfront` in step 9, after DNS had
moved, never before.** If it is flipped while the domain still resolves to
GitHub Pages and the tree does not fit there, `pages.yml` fails rather than
leave families on an older tree. It says `cloudfront` now: `pages.yml` keeps
the rollback copy, and skips it with a warning if a tree outgrows 1 GB.

## The bridge: 96% of the Pages ceiling, until step 9

On 2026-11-17 the owner chose to publish the next tree on GitHub Pages before
this cutover rather than after it (ADR 0008, "The bridge"). GitHub accepts the
953,659,316-byte tree; this repository's 900 MB budget is what refused it. So
`SITE_BUDGET_SHARE` in `src/homeroom/publish_limits.py` was 96% (960.0 MB)
instead of 90%, as a temporary bridge:

- It admitted that one tree with 6.3 MB to spare and refused anything larger,
  40 MB short of GitHub's own ceiling. No new per-page feature fit under it.
- The sitemap budgets were untouched, still 90%.
- **It ended in step 9**, the same day. The pull request that flipped
  `served-by` set `SITE_BUDGET_SHARE` back to `PUBLISHED_BUDGET_SHARE` (90%);
  `tests/test_hosting_decision.py` fails any flip that does not. Since the
  flip no total-size budget is applied at all, so the 90% that came back is
  only what a later return to `github-pages` would be held to.

The bridge publish was made before these steps were run, so two things below
read differently from how they were first written: the first sync in step 4
uploaded the D5 tree (953.7 MB and 23,312 files, about $0.12), and the
`make publish` at the end of step 9 was not needed.

## 0. Session setup

```sh
export AWS_REGION=us-west-2 AWS_DEFAULT_REGION=us-west-2
STACK=homeroom-site
REPO=ChelseaKR/homeroom
DOMAIN=homeroom.chelseakr.com
ZONE_ID=$(aws route53 list-hosted-zones-by-name --dns-name chelseakr.com \
  --query 'HostedZones[0].Id' --output text)
SUBJECT_REPO=$(gh api "repos/$REPO/actions/oidc/customization/sub" \
  --jq '.sub_claim_prefix | ltrimstr("repo:")')
aws sts get-caller-identity
echo "$ZONE_ID"            # /hostedzone/Z...
echo "$SUBJECT_REPO"       # ChelseaKR@3114598/homeroom@1327291879
```

`SUBJECT_REPO` is the repository half of the OIDC subject as GitHub issues it,
with the owner's and the repository's ids. It is read, never composed: the
publish role is pinned to it with `StringEquals`, and a role pinned to
`ChelseaKR/homeroom` deploys green and can never be assumed. If this prints a
plain `owner/name`, stop: the template refuses that form on purpose.

The variables do not outlive the terminal. In a new one, run this block again,
and for step 6 find the certificate with the lookup given there.

## 1. Certificate, in us-east-1 (CloudFront reads no other region)

**The certificate is for `*.chelseakr.com`, not for `homeroom.chelseakr.com`.**
A certificate authority checks CAA records before it issues, and a CAA lookup
follows a CNAME. `homeroom.chelseakr.com` is a CNAME to `chelseakr.github.io`,
and GitHub's CAA records allow Let's Encrypt, DigiCert and Sectigo only. So
while the record points at GitHub Pages, which is until step 8, ACM may not
issue a certificate that names `homeroom.chelseakr.com`: the request made on
2026-11-17 went to `FAILED` with `CAA_ERROR`. A CNAME cannot
share its name with a CAA record, so there is nothing to add that would allow
it. The wildcard's check is made at `chelseakr.com`, which has no CAA record.
It covers `homeroom.chelseakr.com`, and its renewal does not depend on where
that record points, so a long rollback to Pages cannot block it.

```sh
dig +short CAA chelseakr.com   # must print nothing
WILD='*.chelseakr.com'
CERT_ARN=$(aws acm request-certificate --region us-east-1 \
  --domain-name "$WILD" --validation-method DNS \
  --query CertificateArn --output text)
sleep 10   # ACM needs a moment before it names the validation record
read -r VNAME VVALUE < <(aws acm describe-certificate --region us-east-1 \
  --certificate-arn "$CERT_ARN" \
  --query 'Certificate.DomainValidationOptions[0].ResourceRecord.[Name,Value]' \
  --output text)
echo "$VNAME -> $VVALUE"
aws route53 list-resource-record-sets --hosted-zone-id "$ZONE_ID" \
  --query "ResourceRecordSets[?Name=='$VNAME'].ResourceRecords[0].Value" --output text
```

If `dig` prints CAA records and none of them names an Amazon authority
(`amazon.com`, `amazontrust.com`, `awstrust.com`, `amazonaws.com`), stop: the
wildcard would fail the same way.

The last command shows whether the validation record is already in the zone.
ACM uses one record for `chelseakr.com` and `*.chelseakr.com`, and the
account already has a certificate for `chelseakr.com`. On 2026-11-17 the zone
already held the record with the same value as `$VVALUE`, and nothing had to
be written. Three cases:

- It prints `$VVALUE`: the record exists. Write nothing.
- It prints nothing: add the record, with the command below.
- It prints anything else: stop. Something else owns that name.

```sh
# Only if the record is absent:
aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" \
  --change-batch "{\"Changes\":[{\"Action\":\"UPSERT\",\"ResourceRecordSet\":{\"Name\":\"$VNAME\",\"Type\":\"CNAME\",\"TTL\":300,\"ResourceRecords\":[{\"Value\":\"$VVALUE\"}]}}]}"
```

```sh
aws acm wait certificate-validated --region us-east-1 --certificate-arn "$CERT_ARN"
```

*Check:* `aws acm describe-certificate --region us-east-1 --certificate-arn
"$CERT_ARN" --query Certificate.Status` prints `"ISSUED"`, and
`dig +short "$DOMAIN"` still prints `chelseakr.github.io.` The validation
record is a `_…` name under `chelseakr.com`; it does not touch the record
families resolve. If the status is `FAILED`, read
`--query Certificate.FailureReason` before anything else.

## 2. Phase one: plan, then apply (origin on its own `*.cloudfront.net` name)

`deploy/site/params.json` is gitignored at any depth. Keep it that way: by
phase two it carries an ARN, and every ARN carries the account id.

```sh
cat > deploy/site/params.json <<JSON
[
  {"ParameterKey": "SiteDomain",                  "ParameterValue": "homeroom.chelseakr.com"},
  {"ParameterKey": "GitHubRepository",            "ParameterValue": "ChelseaKR/homeroom"},
  {"ParameterKey": "GitHubOidcSubjectRepository", "ParameterValue": "$SUBJECT_REPO"},
  {"ParameterKey": "AttachDomain",                "ParameterValue": "false"},
  {"ParameterKey": "CreateOidcProvider",          "ParameterValue": "false"}
]
JSON
git status --short deploy/site/params.json   # must print nothing (ignored)
grep -c "$SUBJECT_REPO" deploy/site/params.json   # 1: the subject was filled in
```

`GitHubOidcSubjectRepository` has no default. A change set made without it
fails with "Parameters: [GitHubOidcSubjectRepository] must have values", and
one given `ChelseaKR/homeroom` fails on the parameter's pattern. Both are the
template refusing to create a role nobody can assume.

**Plan** (a change set creates nothing until it is executed):

```sh
aws cloudformation create-change-set --stack-name "$STACK" \
  --change-set-name phase-1 --change-set-type CREATE \
  --template-body file://deploy/site/template.yaml \
  --parameters file://deploy/site/params.json \
  --capabilities CAPABILITY_NAMED_IAM
aws cloudformation wait change-set-create-complete \
  --stack-name "$STACK" --change-set-name phase-1
aws cloudformation describe-change-set --stack-name "$STACK" \
  --change-set-name phase-1 \
  --query 'Changes[].ResourceChange.[Action,LogicalResourceId,ResourceType]' \
  --output table
```

Expected plan: **seven `Add` rows, nothing else.** `OidcProvider` is absent
because its condition is false.

| Action | Logical id | Type |
|---|---|---|
| Add | SiteBucket | AWS::S3::Bucket |
| Add | SiteBucketPolicy | AWS::S3::BucketPolicy |
| Add | OriginAccessControl | AWS::CloudFront::OriginAccessControl |
| Add | CachePolicy | AWS::CloudFront::CachePolicy |
| Add | ResponseHeadersPolicy | AWS::CloudFront::ResponseHeadersPolicy |
| Add | Distribution | AWS::CloudFront::Distribution |
| Add | PublishRole | AWS::IAM::Role |

**Apply:**

```sh
aws cloudformation execute-change-set --stack-name "$STACK" --change-set-name phase-1
aws cloudformation wait stack-create-complete --stack-name "$STACK"   # ~5-15 min
out() { aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
BUCKET=$(out BucketName); DIST_ID=$(out DistributionId)
ROLE_ARN=$(out PublishRoleArn); DIST_DOMAIN=$(out DistributionDomainName)
echo "$BUCKET $DIST_ID $ROLE_ARN $DIST_DOMAIN"
curl -sI "https://$DIST_DOMAIN/" | head -1
```

*Check:* `CREATE_COMPLETE`, four outputs, and `HTTP/2 404` from the empty
origin (it already tells a missing key from a forbidden one). `dig` unchanged.

## 2b. Once, for the stack created on 2026-11-17: repin the publish role

Only for a stack created before the template took
`GitHubOidcSubjectRepository`. Its role is pinned to the `owner/name` subject
and cannot be assumed. This was run on 2026-11-17 and is not needed again. Write `params.json` exactly as in step 2 (the phase-one
values, now with the subject), then:

```sh
aws cloudformation create-change-set --stack-name "$STACK" \
  --change-set-name role-subject --change-set-type UPDATE \
  --template-body file://deploy/site/template.yaml \
  --parameters file://deploy/site/params.json \
  --capabilities CAPABILITY_NAMED_IAM
aws cloudformation wait change-set-create-complete \
  --stack-name "$STACK" --change-set-name role-subject
aws cloudformation describe-change-set --stack-name "$STACK" \
  --change-set-name role-subject \
  --query 'Changes[].ResourceChange.[Action,LogicalResourceId,Replacement]' \
  --output table
```

Expected plan: **one `Modify` row, `PublishRole`, `Replacement` `False`,
nothing else.** Anything more, or a `True`, means stop.

```sh
aws cloudformation execute-change-set --stack-name "$STACK" --change-set-name role-subject
aws cloudformation wait stack-update-complete --stack-name "$STACK"
aws iam get-role --role-name "$STACK-publish" \
  --query 'Role.AssumeRolePolicyDocument.Statement[0].Condition.StringEquals' --output json
```

*Check:* `UPDATE_COMPLETE`, and the role's `sub` is
`repo:<SUBJECT_REPO>:ref:refs/heads/main`, beside `aud` `sts.amazonaws.com`.
The role's ARN, the bucket and the distribution are unchanged, so the four
variables stay as they are.

## 3. Set the four repository variables (arms `site-publish.yml`)

These are the site variables that were reported unset. Until they are set,
`site-publish.yml` skips every run.

```sh
gh variable set SITE_S3_BUCKET                  --repo "$REPO" --body "$BUCKET"
gh variable set SITE_CLOUDFRONT_DISTRIBUTION_ID --repo "$REPO" --body "$DIST_ID"
gh variable set SITE_PUBLISH_ROLE_ARN           --repo "$REPO" --body "$ROLE_ARN"
gh variable set SITE_AWS_REGION                 --repo "$REPO" --body "$AWS_REGION"
gh variable list --repo "$REPO"
```

*Check:* all four listed. From here every commit ci passes on `main` goes to
**both** origins. (`required configuration` stays red until
`ASK_ALARM_RELAY_ROLE_ARN` is set too; that one is the ask stack's and is
unrelated to this move.)

Two things to know before setting them.

**They arm the workflow at once, whether or not a publish can succeed yet.**
From this command on, every merge to `main` starts a `site-publish` run. If
step 4 then fails, as it did on 2026-11-17, each later merge fails the same
way until the cause is fixed. `pages.yml` is unaffected, so families are too,
but the runs are red. To go quiet while a fix is made, delete the four
(`gh variable delete NAME --repo "$REPO"`) and set them again afterwards.

**Two of the values carry the AWS account id, and this repository is public.**
The bucket is named `homeroom-site-<account id>` and the role ARN contains the
id. GitHub prints repository variables unmasked, so both appear in the public
log of every `site-publish` run, in the `env:` and `with:` lines of its steps.
An account id is not a credential. It is stated here because the template
keeps the id out of the committed bytes on purpose and the logs do not.
Renaming the bucket would take it out of one of the two.

## 4. First sync

Look before dispatching. Once the variables are set, every commit ci passes on
`main` starts this workflow by itself, so a merge made since step 3 (a fix to
this very cutover, say) may already have a run in progress or finished. The
workflow never runs two at once, so a second dispatch only queues behind the
first and then uploads everything again.

```sh
gh run list --repo "$REPO" --workflow site-publish.yml --limit 3
```

If a run for the current `main` is in progress, watch that one. If one already
succeeded on it, this step is done. Otherwise:

```sh
gh workflow run site-publish.yml --repo "$REPO" --ref main
sleep 5
gh run watch --repo "$REPO" \
  "$(gh run list --repo "$REPO" --workflow site-publish.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```

*Check:* the run is green, its inventory step prints `N files, and the bucket
holds exactly those`, and its content-type step lists every kind. About 954 MB
and 23,312 PUTs, roughly $0.12.

If it fails at `aws-actions/configure-aws-credentials` with "Not authorized to
perform sts:AssumeRoleWithWebIdentity", the role's subject does not match the
token's. Nothing was uploaded and nothing was charged. Compare the two, and do
not loosen the condition to make them agree:

```sh
gh api "repos/$REPO/actions/oidc/customization/sub"          # what GitHub issues
aws iam get-role --role-name "$STACK-publish" \
  --query 'Role.AssumeRolePolicyDocument.Statement[0].Condition' --output json
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRoleWithWebIdentity \
  --max-results 1 --query 'Events[0].CloudTrailEvent' --output text
```

The last one prints the newest such call in the account, which can take a few
minutes to appear and may be another repository's: check its time. Its
`userIdentity.userName` is the subject exactly as GitHub issued it.

The log of this run is public and shows the role ARN and the bucket name
(step 3).

## 5. Verify on the CloudFront URL, before any DNS change

```sh
uv run python tools/verify_live_site.py --skip-rebuild --sample 0 \
  --url "https://$DIST_DOMAIN/"
curl -sI "https://$DIST_DOMAIN/" | grep -iE \
  '^(content-type|cache-control|strict-transport-security|x-content-type-options|x-frame-options|referrer-policy|content-security-policy):'
```

*Check:* `serves exactly what this checkout publishes: 23312 of 23312 file(s)
compared` (the count is whatever `find site -type f | wc -l` says on the day),
then `text/html; charset=utf-8`, `public, max-age=300, s-maxage=86400`, HSTS,
`nosniff`, `DENY`, `same-origin`, and **no** `content-security-policy` line,
which is parity with GitHub Pages today (see "Headers" in `README.md`).

Allow about 75 minutes, on a machine that stays awake and on power. The tool
opens one connection per file, about five files a second from a laptop, and it
does not resume: a single fetch that times out ends the attempt, and the next
attempt (there are three, 20 seconds apart) starts the whole comparison again.
On 2026-11-17 the first attempt ended when the laptop went to sleep on a low
battery, the second on one network timeout a quarter of the way in, and the
third ran to the end. Neither failed attempt had found a difference; each
prints `attempt N/3: GET ... failed: ... timed out`, which is not the same
thing as a difference. If all three end that way the tool exits 4, "could not
run": run it again, with `--timeout-seconds 60 --attempts 5` if the network is
poor. It is the same check and the same pass line.

Google Analytics does not fire on this URL, and that is correct: the loader
runs only on `homeroom.chelseakr.com`. The sentinel has already proved
`analytics.js` is byte-identical to the committed one.

## 6. Phase two: attach the domain (plan, then apply)

The certificate is the wildcard from step 1. The template pins
`CertificateArn` to an ARN in us-east-1 and to nothing about the name, and
CloudFront accepts `*.chelseakr.com` for the alias `homeroom.chelseakr.com`.
In a terminal that no longer has `$CERT_ARN`, find it by the name it was
issued for; looking it up by `homeroom.chelseakr.com` finds nothing:

```sh
CERT_ARN=$(aws acm list-certificates --region us-east-1 --certificate-statuses ISSUED \
  --query "CertificateSummaryList[?DomainName=='*.chelseakr.com'].CertificateArn | [0]" \
  --output text)
test "$CERT_ARN" != None && echo found
```

```sh
cat > deploy/site/params.json <<JSON
[
  {"ParameterKey": "SiteDomain",                  "ParameterValue": "homeroom.chelseakr.com"},
  {"ParameterKey": "GitHubRepository",            "ParameterValue": "ChelseaKR/homeroom"},
  {"ParameterKey": "GitHubOidcSubjectRepository", "ParameterValue": "$SUBJECT_REPO"},
  {"ParameterKey": "AttachDomain",                "ParameterValue": "true"},
  {"ParameterKey": "CreateOidcProvider",          "ParameterValue": "false"},
  {"ParameterKey": "CertificateArn",              "ParameterValue": "$CERT_ARN"},
  {"ParameterKey": "HstsMaxAgeSeconds",           "ParameterValue": "300"}
]
JSON
aws cloudformation create-change-set --stack-name "$STACK" \
  --change-set-name phase-2 --change-set-type UPDATE \
  --template-body file://deploy/site/template.yaml \
  --parameters file://deploy/site/params.json \
  --capabilities CAPABILITY_NAMED_IAM
aws cloudformation wait change-set-create-complete \
  --stack-name "$STACK" --change-set-name phase-2
aws cloudformation describe-change-set --stack-name "$STACK" \
  --change-set-name phase-2 \
  --query 'Changes[].ResourceChange.[Action,LogicalResourceId,Replacement]' \
  --output table
```

Expected plan: **two `Modify` rows, `Replacement` `False` on both** --
`Distribution` (alias and certificate) and `ResponseHeadersPolicy` (HSTS
max-age 300). A `True` anywhere means stop. So does a third row: a
`PublishRole` row here means step 2b was skipped, or `$SUBJECT_REPO` is not
the value the role already carries.

```sh
aws cloudformation execute-change-set --stack-name "$STACK" --change-set-name phase-2
aws cloudformation wait stack-update-complete --stack-name "$STACK"
curl -sI --connect-to "$DOMAIN:443:$DIST_DOMAIN:443" "https://$DOMAIN/" | head -3
```

*Check:* `HTTP/2 200` and `content-type: text/html; charset=utf-8` over a
certificate for the domain, while `dig +short "$DOMAIN"` still prints
`chelseakr.github.io.`

## 7. Lower the TTL, then wait out the old one (300 s)

```sh
aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" \
  --change-batch '{"Changes":[{"Action":"UPSERT","ResourceRecordSet":{"Name":"homeroom.chelseakr.com","Type":"CNAME","TTL":60,"ResourceRecords":[{"Value":"chelseakr.github.io"}]}}]}'
dig homeroom.chelseakr.com +noall +answer   # TTL 60, still chelseakr.github.io
```

Wait at least five minutes (the old TTL) before step 8; a day is better. On
2026-11-17 step 8 followed eight minutes later, on the owner's decision.

## 8. The DNS switch -- the first step a family can see

```sh
CHANGE_ID=$(aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" \
  --change-batch "{\"Changes\":[{\"Action\":\"UPSERT\",\"ResourceRecordSet\":{\"Name\":\"$DOMAIN\",\"Type\":\"CNAME\",\"TTL\":60,\"ResourceRecords\":[{\"Value\":\"$DIST_DOMAIN\"}]}}]}" \
  --query ChangeInfo.Id --output text)
aws route53 wait resource-record-sets-changed --id "$CHANGE_ID"
dig +short "$DOMAIN"
uv run python tools/verify_live_site.py --skip-rebuild --sample 0
```

*Check:* `dig` prints the `*.cloudfront.net` name, and the sentinel, run with
**no `--url`**, passes against the domain -- which now means the new origin.
`curl -sI "https://$DOMAIN/"` shows `server: AmazonS3` and a `via` naming
CloudFront instead of `server: GitHub.com`. Load one page in a browser with
Do Not Track and GPC off and confirm GA's request in the network panel.

## 9. Flip the switch (done, in one pull request)

Only after step 8 checks out:

```sh
git switch -c deploy/served-by-cloudfront origin/main
printf 'cloudfront\n' > deploy/site/served-by
# The bridge ends here: the tree's budget goes back to the standing 90%.
sed -i '' 's/^SITE_BUDGET_SHARE = 0.96$/SITE_BUDGET_SHARE = PUBLISHED_BUDGET_SHARE/' \
  src/homeroom/publish_limits.py
grep -n '^SITE_BUDGET_SHARE' src/homeroom/publish_limits.py   # = PUBLISHED_BUDGET_SHARE
```

Rewrite the `Status:` line of `docs/adr/0008-serve-the-site-from-s3-behind-cloudfront.md`
so it no longer says "Not applied" and gives the date DNS moved, then:

```sh
uv run --locked pytest tests/test_hosting_decision.py tests/test_publish_budget.py \
  tests/test_published_limits.py tests/test_deploy_site_template.py -q
```

`test_hosting_decision.py` fails until the switch, the budget and the ADR's
status agree. `test_deploy_site_template.py` fails until `README.md` beside
this file is an applied record: it has to say it is applied, name the stack,
the region and the distribution, give every parameter as applied, and carry
nothing that holds the AWS account id.

The same pull request put the rest of the records right: the bridge in the
past tense in `publish_limits.py` and its two test files; "Where this stands"
above; the headers of `.github/workflows/site-publish.yml`,
`.github/workflows/pages.yml`, `.github/workflows/required-configuration.yml`
and `tools/config_audit.py`, which described the four variables as unset; the
template's header; and the hosting record in
`docs/RESPONSIBLE-TECH-AUDITS.md`.

**What merging it starts.** ci runs on `main`. When it passes, two workflows
follow it:

- `site-publish.yml` syncs the commit's `site/` to the bucket, checks the
  inventory and the content types, and invalidates `/*`. The pull request
  does not change `site/`, so the bytes families read do not change.
- `pages.yml` asks whether GitHub Pages can take the tree. It can (953.7 MB,
  under 1 GB), so it deploys the same tree to the rollback copy.

Afterwards: both runs green on the merge commit; `make publish-limits` prints
"served by CloudFront from S3"; and the sentinel passes against the domain.

**No republish was needed.** These commands were first written for a D5
republish to follow the flip. D5 was published before the cutover instead,
under the bridge, so `site/` already carried it when the first sync ran. The
next `make publish`, whenever something changes what the pages say, is held to
no total-size ceiling:

```sh
ASK_ENDPOINT=$(aws cloudformation describe-stacks --stack-name homeroom-ask \
  --query "Stacks[0].Outputs[?OutputKey=='FunctionUrl'].OutputValue" --output text)
make publish ASK_ENDPOINT="$ASK_ENDPOINT"
make publish-limits
```

Commit `site/` on a branch and open a PR; when ci passes on the merge,
`site-publish.yml` syncs it to S3 and invalidates, and `pages.yml` deploys the
same tree to the Pages rollback copy if it fits under 1 GB, or skips it with a
warning if not. D5's own precondition is still worth running where the
acquired file is, before any publish that re-renders it (about five seconds;
`test_every_fte_cell_in_the_acquired_file_prints_as_published` must say
PASSED, not SKIPPED):

```sh
uv run --locked pytest tests/test_fte_precision.py -v
```

## Rollback -- one record

```sh
aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" \
  --change-batch '{"Changes":[{"Action":"UPSERT","ResourceRecordSet":{"Name":"homeroom.chelseakr.com","Type":"CNAME","TTL":60,"ResourceRecords":[{"Value":"chelseakr.github.io"}]}}]}'
dig +short homeroom.chelseakr.com   # chelseakr.github.io.
uv run python tools/verify_live_site.py --skip-rebuild --sample 0
```

GitHub Pages has received every commit and is current, so this is the whole
rollback: the tree published on 2026-11-17 is 953.7 MB, which fits under
Pages' 1 GB, and `pages.yml` deploys every tree that does. If a later tree
does not fit, `pages.yml` skips it with a warning, and from then on rolling
back serves the last tree that did fit, until something that fits is
published. Rolling DNS back does not by itself need `served-by` changed: both
workflows keep publishing. Setting it back to `github-pages` is a separate
step and a new decision, because the suite then holds the tree to 900 MB and
today's tree is over that (ADR 0008, "The bridge"). If HTTPS fails after
rolling back, GitHub's certificate lapsed while
DNS pointed away: in Settings -> Pages, remove and re-add the custom domain.
`HstsMaxAgeSeconds=300` is what keeps that window short; raise it to
`31536000` (a phase-two change set with only that parameter changed) once the
move has settled, and raise the DNS TTL back to 300.

Nothing on the AWS side has to be torn down to roll back. If it ever is: delete
the four variables first, then the stack (`README.md`, "Rolling back").

## Cost

At list price for `us-west-2`, rates to be re-read before relying on a total:

| | Measured | Cost |
|---|---|---|
| Storage, today's tree | 877,171,581 bytes (0.817 GiB) | $0.019/month at $0.023/GB-month |
| Storage, the D5 tree | ~943.8 MB with #98, 1,060.9 MB without (0.88-0.99 GiB) | $0.020-0.023/month |
| Superseded versions (30 days, one full republish) | one generation | +$0.020-0.023/month while they last |
| A full republish or the first sync | ~23,312 PUTs | $0.12 |
| Sync listings, head-object reads | ~250 requests | < $0.01 |
| Invalidation | 1 path (`/*`) | $0 (1,000 paths/month free) |
| S3 to CloudFront transfer | cache misses | $0 |
| Origin GETs, incl. one full `--sample 0` check | ~23,000 | ~$0.01 |
| CloudFront serving | always-free tier: 1 TB and 10,000,000 requests a month | $0 up to ~10 million page views a month |
| ACM certificate, IAM role, OIDC, CloudFormation | | $0 |
| Route 53 | existing zone, existing record | no change |

**About $0.02-0.05 a month, plus about $0.12 each time the whole tree is
republished.** Past the free tier, a further million page views is about 40 GB,
or $3.40 at $0.085/GB.
