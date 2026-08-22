# Deployment shape for the ask service: prepared, not applied

Nothing in this directory has been deployed, and nothing in this repository
deploys it. ADR 0003 records that exposing the ask service to families is a
separate decision with its own consequences, and this directory is what that
decision would apply if it were made.

## The shape

One AWS Lambda function (Python 3.12, arm64, 512 MB, 40 s) behind a Lambda
Function URL, `AuthType: NONE`, with CORS allowing exactly one origin (the
site's) and one method (POST). The function runs `homeroom.ask.http.lambda_handler`,
which is the same code the local server runs. The evidence bundle and the
corpus ship inside the package; no database, no storage, no account.

Cost is bounded three ways, because one is not enough:

1. **Reserved concurrency** (default 2): at most two questions in flight
   across the whole function. This is the bound that actually holds under
   abuse; everything below is per container.
2. **The service's own limits**: six requests per client per minute and a
   daily cap of 400 model calls (two per answered question) per warm
   container, both from the environment. A refused request costs nothing and
   returns a fixed string; the page is complete without it.
3. **A CloudWatch alarm** on daily invocations, to an SNS topic if one is
   given. Pair it with an AWS Budgets alert on the account; budgets are
   account-level and not in this template.

The in-memory daily cap is per container, which is honest about what it is: a
bound on what one running copy spends, not a ledger. With reserved concurrency
2 the worst case is two containers each spending their cap. A shared counter
(DynamoDB, one item, conditional increment) is the upgrade if that matters.

## Provider and credentials

`Provider=bedrock` is the keyless path: the function's IAM role is allowed
`bedrock:InvokeModel` on `BedrockModelArn`, which must be narrowed to the exact
model or inference-profile ARN before deploying (the default is a wildcard so
the template validates; do not deploy it that way). The model id is whatever
the account can invoke; on 2026-08-21 this account could invoke
`global.anthropic.claude-sonnet-4-6` and was refused Sonnet 5 and Opus 5.

`Provider=anthropic` uses the public API with the code default
`claude-sonnet-5`. The key is a `NoEcho` parameter that lands in the function's
environment, encrypted at rest by Lambda; it is never written to this
repository, to a results file, or to a log. No `ANTHROPIC_API_KEY` existed in
the build environment on 2026-08-21.

## Privacy

The handler never logs a request body. The default access log is silenced in
the local server; in Lambda only the runtime's START/END/REPORT lines reach
CloudWatch, retained 14 days. The rate-limit key is a salted hash of the source
address with a per-process salt, never stored. The question and one school's
published records are sent to the model provider for the duration of the
request; that subprocessor relationship is recorded in
`docs/RESPONSIBLE-TECH-AUDITS.md` under Privacy (Amazon Bedrock, us-west-2,
owner-approved 2026-08-22). RR-07 to RR-09 in
`docs/audits/residual-risk-register.md` carry the rest.

## Building and deploying (by a person, after the decision)

```sh
make data                                               # acquired files -> data/out
uv run python -m homeroom.ask.evidence \
  --directory data/raw/pubschls.txt --enrollment data/raw/cdenroll2526.txt \
  --absenteeism data/raw/chronicabsenteeism25.txt --out data/out/ask
./deploy/ask/build.sh                                   # -> dist/ask-lambda.zip
aws s3 cp dist/ask-lambda.zip s3://<bucket>/ask/<git sha>.zip
aws cloudformation deploy --template-file deploy/ask/template.yaml \
  --stack-name homeroom-ask --capabilities CAPABILITY_IAM \
  --parameter-overrides CodeBucket=<bucket> CodeKey=ask/<git sha>.zip \
    SiteOrigin=https://<site> Provider=bedrock \
    Model=global.anthropic.claude-sonnet-4-6 \
    BedrockModelArn=<exact arn> AlarmTopicArn=<optional>
```

The stack's `FunctionUrl` output is what the site build takes as
`--ask-endpoint`; a build without it renders no ask page and no link, and is
byte-identical to a build before ADR 0003.

`build.sh` refuses to package a fixture bundle. The package is about 9 MB
compressed (the bundle's 206 MB of per-school files compress to about 8 MB)
and about 230 MB unzipped, under Lambda's 250 MB limit but not by much; a
fourth data source means moving the bundle to S3 and reading one school per
request, which is a small change to `homeroom.ask.evidence.load_school`.

## Before deploying, decide

- Whether to deploy at all (owner).
- The cost envelope: reserved concurrency, daily cap, alarm threshold, and an
  account budget. At Bedrock Sonnet 4.6 list prices and the measured token
  counts (roughly 1.5k uncached input, 7.8k cached, 500 output per answered
  question), 400 calls a day is on the order of a dollar a day.
- Which model. The evaluation results in `evals/results/` are for the model
  they name; deploying a different model means re-running them first.
- A person reading a sample of real answers in each language (RR-07, RR-08).
