# Deployment shape for the ask service: applied 2026-08-22

This is deployed. ADR 0003 records that exposing the ask service to families is
a separate decision with its own consequences; the owner made it on 2026-08-22,
and this directory is what was applied.

| | |
|---|---|
| Stack | `homeroom-ask` |
| Region | `us-west-2` |
| Stack ARN | `arn:aws:cloudformation:us-west-2:014248889144:stack/homeroom-ask/4c826de0-9e29-11f1-9e5f-0642c3e5a3a7` |
| Function URL | `https://vlbgna342rtuvkikbuwuwgosuu0jgvdp.lambda-url.us-west-2.on.aws/` |
| Model | Bedrock `global.anthropic.claude-sonnet-4-6` |
| Site origin | `https://homeroom.chelseakr.com` |
| Alarm topic | `arn:aws:sns:us-west-2:014248889144:homeroom-ask-alarms` (**no subscriber yet**) |

Parameters as applied: `DeployFunction=true`, `SiteOrigin=https://homeroom.chelseakr.com`,
`Provider=bedrock`, `Model=global.anthropic.claude-sonnet-4-6`,
`ReservedConcurrency=2`, `DailyCap=400`, `PerMinute=6`,
`DailyInvocationAlarm=400`, and `BedrockModelArns` set to exactly the
inference-profile ARN and the two foundation-model ARNs it routes to.

## Rolling it back

Two steps, in this order, so no page is ever left pointing at a service that is
gone:

```sh
make publish ASK_ENDPOINT=            # fails: the target requires an endpoint
```

is not the rollback. The rollback is to rebuild the site without one and to
delete the stack:

```sh
uv run python -m homeroom.site --directory data/raw/pubschls.txt \
  --enrollment data/raw/cdenroll2526.txt \
  --absenteeism data/raw/chronicabsenteeism25.txt \
  --cds 57726786056246 --out site --landing
echo homeroom.chelseakr.com > site/CNAME
# commit site/ -- the school pages return to byte-identical-to-pre-ADR-0003,
# the ask pages and the one link to them stop existing, and the pages are
# complete without them. Then, once that is published:
aws cloudformation delete-stack --stack-name homeroom-ask --region us-west-2
```

Deleting the stack first would leave a live ask page whose every submission
fails. The site is the thing families see, so the site changes first.

The stack's own code bucket is versioned and is deleted with the stack only if
it is empty; emptying it is a deliberate step, because those objects are the
exact packages that were served.

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

`Provider=bedrock` is the keyless path and is what is deployed: the function's
IAM role is allowed `bedrock:InvokeModel` on `BedrockModelArns`, which has no
default on purpose and is set to exactly three ARNs -- the inference profile and
the two foundation models it routes to. A wildcard there would be a wider grant
than the one model this service runs.

The model id is whatever the account can invoke. This account could invoke
`global.anthropic.claude-sonnet-4-6` and was refused Sonnet 5 and Opus 5, which
is settled and does not need re-probing: the availability API reports Sonnet 5
as AUTHORIZED for this account and `InvokeModel` still returns
`AccessDeniedException`. Believe the invoke, not the catalogue.

Two traps worth writing down, both of which cost a deploy cycle:

- **Pass `BedrockModelArns` from a parameters file, not the `Key=Value`
  shorthand.** Escaping the commas as `\,` puts the backslashes *into* the
  ARNs. The stack deploys green, the role holds two malformed ARNs, and the
  only symptom is that every question comes back `unavailable` with
  `model_calls: 0`, because the service maps a provider error to a fixed
  refusal and never logs the cause. Use
  `--parameter-overrides file://params.json` with
  `[{"ParameterKey": ..., "ParameterValue": ...}]`.
- **The Function URL needs two grants on this account**, not the one the
  documentation implies. See the note in `template.yaml`.

`Provider=anthropic` uses the public API with the code default
`claude-sonnet-5`. The key is a `NoEcho` parameter that lands in the function's
environment, encrypted at rest by Lambda; it is never written to this
repository, to a results file, or to a log. No `ANTHROPIC_API_KEY` existed in
the build environment on 2026-08-21.

## Privacy

The handler never logs a request body. The default access log is silenced in
the local server; in Lambda only the runtime's START/END/REPORT lines reach
CloudWatch, retained 14 days. This is why a failing provider call is diagnosed
by reading the IAM policy rather than a stack trace: the same silence that keeps
a family's question out of the logs keeps the operator's error out of them too,
and that trade is made deliberately in the reader's favour. The rate-limit key is a salted hash of the source
address with a per-process salt, never stored. The question and one school's
published records are sent to the model provider for the duration of the
request; that subprocessor relationship is recorded in
`docs/RESPONSIBLE-TECH-AUDITS.md` under Privacy (Amazon Bedrock, us-west-2,
owner-approved 2026-08-22). RR-07 to RR-09 in
`docs/audits/residual-risk-register.md` carry the rest.

## Re-deploying (by a person)

The stack is two-phase so that everything, including the code bucket, lives
inside it. Phase one already ran; a redeploy is phase two only.

```sh
make data                                               # acquired files -> data/out
make ask-bundle                                         # -> data/out/ask
./deploy/ask/build.sh                                   # -> dist/ask-lambda.zip
aws s3 cp dist/ask-lambda.zip \
  s3://homeroom-ask-code-014248889144/ask/$(git rev-parse --short HEAD).zip \
  --region us-west-2
aws cloudformation deploy --template-file deploy/ask/template.yaml \
  --stack-name homeroom-ask --region us-west-2 --capabilities CAPABILITY_IAM \
  --parameter-overrides file://params.json               # see the trap above
```

Then re-publish the site so the pages and the service agree:

```sh
make publish ASK_ENDPOINT=https://vlbgna342rtuvkikbuwuwgosuu0jgvdp.lambda-url.us-west-2.on.aws
```

and commit `site/`. Pushing to `main` publishes it after ci passes.

The stack's `FunctionUrl` output is what the site build takes as
`--ask-endpoint`; a build without it renders no ask page and no link, and is
byte-identical to a build before ADR 0003.

`build.sh` refuses to package a fixture bundle, installs the SDK's `bedrock`
extra (`AnthropicBedrock` signs through botocore; without it the function runs
on whatever boto3 the runtime happens to carry), and measures the unzipped
package against Lambda's limit: **231.7 MB, 92.7% of 250 MB**. It fails rather
than shipping something over. That margin is what is left, not what was chosen:
a fourth data source does not fit, and the answer then is to move the bundle to
S3 and read one school per request -- a small change to
`homeroom.ask.evidence.load_school` -- rather than to drop schools or trim data.

## Still open

- **Nobody is subscribed to the alarm topic.** The CloudWatch alarm at 400
  daily invocations fires into `homeroom-ask-alarms` and reaches no one. An
  address is the owner's to give; subscribing needs no stack change.
- **No account budget.** Budgets are account-level and touch other projects, so
  this stack does not create one. At Bedrock Sonnet 4.6 list prices and the
  measured token counts (roughly 1.5k uncached input, 7.8k cached, 500 output
  per answered question), 400 calls a day is on the order of a dollar a day;
  reserved concurrency 2 is the bound that actually holds under abuse.
- **The daily cap is per warm container**, not a shared ledger, so the worst
  case is two containers each spending it. A DynamoDB item with a conditional
  increment is the upgrade if that ever matters.
- **A person reading a sample of real answers in each language** (RR-07,
  RR-08). The evaluations are automated scorers; nobody has read the Spanish
  narration as a Spanish speaker.
- **Issue #6**: the keyboard and screen-reader walkthrough of the live ask
  page.

## Before changing any of this, decide

- Which model. The evaluation results in `evals/results/` are for the model
  they name; deploying a different one means re-running them first.
- Whether the change widens what leaves the reader's browser. The subprocessor
  record in `docs/RESPONSIBLE-TECH-AUDITS.md` has to move before the exposure
  does, not after.
