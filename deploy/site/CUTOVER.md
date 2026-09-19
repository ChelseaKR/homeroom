# Moving homeroom.chelseakr.com to S3 + CloudFront: the owner's commands

The owner decided on 2026-09-18 to move hosting to the origin in this directory
(issue #82, option 1). **Nothing below has been run.** No stack, bucket,
distribution, role or certificate exists, no repository variable is set, and
the DNS record is unchanged. Every command here is the owner's, run in this
order, from a checkout of `main` at the repository root.

`README.md` beside this file is the reasoning: the shape, the costs, the
limits, the rollback. This file is only the commands, with what each one should
print. Everything before step 8 is invisible to families.

## Why now

The next `make publish` carries D5, the teaching-assignment section ADR 0005
publishes on every school page. Measured 2026-09-18: `site/` is 877.2 MB
(877,171,581 bytes, 23,311 files) and D5 adds 8,723 bytes to each of 21,068
school pages, so the render is **1,060.9 MB, 106% of the 1 GB GitHub Pages
allows**. With #98's shared stylesheet it is about 943.8 MB: under the Pages
ceiling but over this repository's 900 MB budget, so `make publish` still
refuses it while GitHub Pages is the origin. After the move there is no
total-size ceiling at all.

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

## The switch that keeps GitHub Pages serving

`deploy/site/served-by` says `github-pages`. While it does, `pages.yml`
deploys every commit to GitHub Pages exactly as before, `make publish` holds
the render to the Pages ceiling, and a tree Pages cannot take is an error.
**It changes to `cloudfront` in step 9, after DNS has moved, never before.**
If it is flipped while the domain still resolves to GitHub Pages, `pages.yml`
fails rather than leave families on an older tree.

## 0. Session setup

```sh
export AWS_REGION=us-west-2 AWS_DEFAULT_REGION=us-west-2
STACK=homeroom-site
REPO=ChelseaKR/homeroom
DOMAIN=homeroom.chelseakr.com
ZONE_ID=$(aws route53 list-hosted-zones-by-name --dns-name chelseakr.com \
  --query 'HostedZones[0].Id' --output text)
aws sts get-caller-identity
echo "$ZONE_ID"            # /hostedzone/Z...
```

## 1. Certificate, in us-east-1 (CloudFront reads no other region)

```sh
CERT_ARN=$(aws acm request-certificate --region us-east-1 \
  --domain-name "$DOMAIN" --validation-method DNS \
  --query CertificateArn --output text)
sleep 10   # ACM needs a moment before it names the validation record
read -r VNAME VVALUE < <(aws acm describe-certificate --region us-east-1 \
  --certificate-arn "$CERT_ARN" \
  --query 'Certificate.DomainValidationOptions[0].ResourceRecord.[Name,Value]' \
  --output text)
aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" \
  --change-batch "{\"Changes\":[{\"Action\":\"UPSERT\",\"ResourceRecordSet\":{\"Name\":\"$VNAME\",\"Type\":\"CNAME\",\"TTL\":300,\"ResourceRecords\":[{\"Value\":\"$VVALUE\"}]}}]}"
aws acm wait certificate-validated --region us-east-1 --certificate-arn "$CERT_ARN"
```

*Check:* `aws acm describe-certificate --region us-east-1 --certificate-arn
"$CERT_ARN" --query Certificate.Status` prints `"ISSUED"`, and
`dig +short "$DOMAIN"` still prints `chelseakr.github.io.` The validation
record is a new `_…` name; it does not touch the record families resolve.

## 2. Phase one: plan, then apply (origin on its own `*.cloudfront.net` name)

`deploy/site/params.json` is gitignored at any depth. Keep it that way: by
phase two it carries an ARN, and every ARN carries the account id.

```sh
cat > deploy/site/params.json <<'JSON'
[
  {"ParameterKey": "SiteDomain",         "ParameterValue": "homeroom.chelseakr.com"},
  {"ParameterKey": "GitHubRepository",   "ParameterValue": "ChelseaKR/homeroom"},
  {"ParameterKey": "AttachDomain",       "ParameterValue": "false"},
  {"ParameterKey": "CreateOidcProvider", "ParameterValue": "false"}
]
JSON
git status --short deploy/site/params.json   # must print nothing (ignored)
```

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

## 4. First sync

```sh
gh workflow run site-publish.yml --repo "$REPO" --ref main
sleep 5
gh run watch --repo "$REPO" \
  "$(gh run list --repo "$REPO" --workflow site-publish.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```

*Check:* the run is green, its inventory step prints `N files, and the bucket
holds exactly those`, and its content-type step lists every kind. About 877 MB
and 23,311 PUTs, roughly $0.12.

## 5. Verify on the CloudFront URL, before any DNS change

```sh
uv run python tools/verify_live_site.py --skip-rebuild --sample 0 \
  --url "https://$DIST_DOMAIN/"
curl -sI "https://$DIST_DOMAIN/" | grep -iE \
  '^(content-type|cache-control|strict-transport-security|x-content-type-options|x-frame-options|referrer-policy|content-security-policy):'
```

*Check:* `serves exactly what this checkout publishes: 23311 of 23311 file(s)
compared` (the count is whatever `find site -type f | wc -l` says on the day),
then `text/html; charset=utf-8`, `public, max-age=300, s-maxage=86400`, HSTS,
`nosniff`, `DENY`, `same-origin`, and **no** `content-security-policy` line,
which is parity with GitHub Pages today (see "Headers" in `README.md`).

Google Analytics does not fire on this URL, and that is correct: the loader
runs only on `homeroom.chelseakr.com`. The sentinel has already proved
`analytics.js` is byte-identical to the committed one.

## 6. Phase two: attach the domain (plan, then apply)

```sh
cat > deploy/site/params.json <<JSON
[
  {"ParameterKey": "SiteDomain",         "ParameterValue": "homeroom.chelseakr.com"},
  {"ParameterKey": "GitHubRepository",   "ParameterValue": "ChelseaKR/homeroom"},
  {"ParameterKey": "AttachDomain",       "ParameterValue": "true"},
  {"ParameterKey": "CreateOidcProvider", "ParameterValue": "false"},
  {"ParameterKey": "CertificateArn",     "ParameterValue": "$CERT_ARN"},
  {"ParameterKey": "HstsMaxAgeSeconds",  "ParameterValue": "300"}
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
max-age 300). A `True` anywhere means stop.

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

Wait at least five minutes (the old TTL) before step 8; a day is better.

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

## 9. Flip the switch, then publish D5

Only after step 8 checks out:

```sh
git switch -c deploy/served-by-cloudfront origin/main
printf 'cloudfront\n' > deploy/site/served-by
git add deploy/site/served-by
git commit -S -m "deploy: cloudfront serves the domain"
git push -u origin deploy/served-by-cloudfront
gh pr create --repo "$REPO" --fill
```

Merge it when ci is green. Then the D5 republish, which `make publish` now
holds to no total-size ceiling:

```sh
ASK_ENDPOINT=$(aws cloudformation describe-stacks --stack-name homeroom-ask \
  --query "Stacks[0].Outputs[?OutputKey=='FunctionUrl'].OutputValue" --output text)
make publish ASK_ENDPOINT="$ASK_ENDPOINT"
make publish-limits
```

Commit `site/` on a branch and open a PR; when ci merges it, `site-publish.yml`
syncs it to S3 and invalidates, and `pages.yml` deploys the same tree to the
Pages rollback copy if it fits under 1 GB, or skips it with a warning if not.

## Rollback -- one record

```sh
aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" \
  --change-batch '{"Changes":[{"Action":"UPSERT","ResourceRecordSet":{"Name":"homeroom.chelseakr.com","Type":"CNAME","TTL":60,"ResourceRecords":[{"Value":"chelseakr.github.io"}]}}]}'
dig +short homeroom.chelseakr.com   # chelseakr.github.io.
uv run python tools/verify_live_site.py --skip-rebuild --sample 0
```

Before step 9, GitHub Pages has received every commit and is current, so this is
the whole rollback. After step 9, Pages holds the last tree that fit under
1 GB: if the D5 tree did not fit, rolling back serves the older, pre-D5 tree
until the owner sets `served-by` back to `github-pages` and publishes something
that fits. If HTTPS fails after rolling back, GitHub's certificate lapsed while
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
