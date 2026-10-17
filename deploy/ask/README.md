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
| Alarm topic | `arn:aws:sns:us-west-2:014248889144:homeroom-ask-alarms` (**still no subscriber**, re-measured 2026-09-12) |
| Alarm relay | `.github/workflows/ask-alarm-relay.yml` -> a GitHub issue (needs the `ASK_ALARM_RELAY_ROLE_ARN` repository variable; see below) |

Parameters as applied: `DeployFunction=true`, `SiteOrigin=https://homeroom.chelseakr.com`,
`Provider=bedrock`, `Model=global.anthropic.claude-sonnet-4-6`,
`ReservedConcurrency=2`, `DailyCap=400`, `PerMinute=6`,
`DailyInvocationAlarm=400`, and `BedrockModelArns` set to exactly the
inference-profile ARN and the two foundation-model ARNs it routes to.

**The template is ahead of the live stack.** As of 2026-10-17 the template
counts the daily cap in a shared DynamoDB table (`CapTable`) rather than in each
container's memory. The stack applied on 2026-08-22 still runs the in-memory
cap until a person redeploys it; see [The daily cap](#the-daily-cap) for what
changed and [Re-deploying](#re-deploying-by-a-person) for the steps.

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
corpus ship inside the package; no storage and no account. The one table,
`CapTable`, holds a count per day and nothing a reader sent.

Cost is bounded three ways, because one is not enough:

1. **Reserved concurrency** (default 2): at most two questions in flight
   across the whole function.
2. **The service's own limits**: six requests per client per minute (per
   container, in memory) and a daily cap of `DailyCap` model calls (two per
   answered question) across the whole function, counted in `CapTable`. A
   refused request costs nothing and returns a fixed string; the page is
   complete without it.
3. **A CloudWatch alarm** on daily invocations, to an SNS topic if one is
   given. Pair it with an AWS Budgets alert on the account; budgets are
   account-level and not in this template.

### The daily cap

Until 2026-10-17 the cap was counted in each container's memory. That was
described here as "two containers each spending their cap" at reserved
concurrency 2, and it was weaker than that: Lambda recycles execution
environments, and a fresh one starts its count at zero, so a day could see any
number of caps spent one after another. It was no ceiling.

The template now gives the function one DynamoDB table, `CapTable`, with one
item per UTC day: `{"day": "YYYY-MM-DD", "calls": N, "expires_at": <epoch>}`.
Before any model call the service makes one `UpdateItem` that adds the calls it
needs **only if** the day's total stays within `DailyCap`
(`attribute_not_exists(calls) OR calls <= DailyCap - n`). DynamoDB applies the
condition and the add atomically, so two containers reserving at once cannot
both take the last calls, and a recycled container reads the same total as the
one before it. Calls reserved and not made (a provider error, a question that
needed only the first call) are given back with a second conditional
`UpdateItem` that never takes the count below zero.

- **Fail closed.** If the table cannot be reached -- throttled, denied,
  missing, timed out (two seconds, two attempts) -- the service makes no model
  call and returns its fixed "not available" string. A failed give-back leaves
  the calls counted, which only ever errs toward spending less.
- **Least privilege.** The role may `dynamodb:UpdateItem` on `CapTable`'s ARN
  and nothing else; the condition is the read, so there is no `GetItem`.
- **On-demand billing, TTL on.** A few hundred writes a day is cents a year.
  TTL deletes each day's item two days after the day ends; the key is the
  date, so a late deletion changes nothing.
- **What it holds.** A date, a count, an expiry time. No question, no address,
  no hash of either. The privacy section below is unchanged by it.
- **Locally**, without `HOMEROOM_ASK_CAP_TABLE`, the service counts in memory
  as before; the evaluation harness does too.

The symptom of a broken counter is the same as the `BedrockModelArns` trap
below: every question returns `unavailable` with `model_calls: 0`. Check the
role's `daily-cap-counter` policy and the function's `HOMEROOM_ASK_CAP_TABLE`
before anything else.

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
`AccessDeniedException`. Believe the invoke, not the catalog.

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
and that trade is made deliberately in the reader's favor. The rate-limit key is a salted hash of the source
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
  --stack-name homeroom-ask --region us-west-2 --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides file://params.json               # see the trap above
```

The first redeploy after 2026-10-17 also creates `CapTable`, grants the role
`UpdateItem` on it and sets `HOMEROOM_ASK_CAP_TABLE`, all in the same stack
update as the new code, so there is no moment when the new code runs without
its table. No new parameter is needed. Then check the counter is counting, with
the operator's own credentials (the function's role cannot read it):

```sh
TABLE=$(aws cloudformation describe-stacks --stack-name homeroom-ask --region us-west-2 \
  --query "Stacks[0].Outputs[?OutputKey=='CapTableName'].OutputValue" --output text)
# ask one question on the live ask page, then:
aws dynamodb get-item --table-name "$TABLE" --region us-west-2 \
  --key "{\"day\":{\"S\":\"$(date -u +%F)\"}}"
# expect "calls": {"N": "2"} (or 1 for a refusal the model classified)
```

An `unavailable` answer with no item written means the counter is not
reachable; see [The daily cap](#the-daily-cap). Rolling back to the previous
`CodeKey` is safe: older code ignores the table, which stays and costs nothing.

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

- **Nobody is subscribed to the alarm topic.** Re-measured against the live
  account on 2026-09-12: zero subscriptions, confirmed or pending, since the
  stack was applied on 2026-08-22. The CloudWatch alarm at 400 daily
  invocations fires into `homeroom-ask-alarms` and, on the SNS side, still
  reaches no one. An address is the owner's to give; subscribing needs no stack
  change.

  What changed is that this is no longer the *only* path.
  `.github/workflows/ask-alarm-relay.yml` reads the alarm's state and the
  topic's subscriber count directly, once a day, and reports into a GitHub
  issue -- a channel that needs no address and cannot be unsubscribed from by
  accident. It reports the missing subscriber as a finding in its own right, so
  this bullet stops depending on somebody remembering to re-check it.

  Two owner steps switch it on, and until both are done the workflow fails
  loudly every day rather than skipping quietly:

  1. Add one parameter to your local `params.json` (it is gitignored, so it is
     not in this diff) and redeploy:

     ```json
     { "ParameterKey": "AlarmRelayRepository", "ParameterValue": "ChelseaKR/homeroom" }
     ```

     Redeploy with `--capabilities CAPABILITY_NAMED_IAM`, as the command
     above now does. The role has a fixed name (`homeroom-ask-alarm-relay`),
     and CloudFormation refuses a named IAM resource under `CAPABILITY_IAM`
     with `InsufficientCapabilities`, so the command this README carried until
     2026-10-01 would have stopped at this step.

     That creates `AlarmRelayRole` -- a role whose entire policy is
     `cloudwatch:DescribeAlarms` and `sns:GetTopicAttributes`, assumable only
     from this repository's `main` branch. Leaving the parameter out creates no
     role and no trust, which is the default on purpose: a default value here
     would let a fork of this template hand read access to a repository its
     deployer does not control.
  2. Set the repository variable `ASK_ALARM_RELAY_ROLE_ARN` to the stack's
     `AlarmRelayRoleArn` output (Settings > Secrets and variables > Actions >
     Variables). It is a variable, not a secret: a role ARN is not a
     credential, and OIDC means there is no long-lived key to store.

  No GitHub token grant is needed. The workflow files the issue with the
  built-in `GITHUB_TOKEN` under `issues: write`.
- **No account budget.** Budgets are account-level and touch other projects, so
  this stack does not create one. At Bedrock Sonnet 4.6 list prices and the
  measured token counts (roughly 1.5k uncached input, 7.8k cached, 500 output
  per answered question), 400 calls a day is on the order of a dollar a day;
  reserved concurrency 2 is the bound that actually holds under abuse.
- **The shared daily cap is in the template and not yet applied.** Until the
  owner redeploys, the live function still counts its cap per container, which
  is no ceiling (see [The daily cap](#the-daily-cap)).
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
