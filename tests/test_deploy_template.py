"""The deployment template, checked for the things a green deploy still gets wrong.

`aws cloudformation deploy` succeeding proves the template is well-formed, not
that the service works. Everything asserted here is something that deployed
cleanly and then failed in front of a reader, so each test names the symptom it
would have caught.

The template is read as text rather than parsed: CloudFormation YAML carries
`!Ref` and `!GetAtt` tags that a plain YAML loader rejects, and adding a parser
plus a tag-tolerant loader to this project's dependencies to check one file is a
worse trade than reading the block by indentation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "deploy" / "ask" / "template.yaml"


def resource(name: str) -> str:
    """One top-level entry of `Resources:`, by its four-space indentation."""
    lines = TEMPLATE.read_text(encoding="utf-8").splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.startswith(f"  {name}:")), None
    )
    assert start is not None, f"no resource named {name} in the template"
    body = []
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith("    "):
            break
        body.append(line)
    return "\n".join(body)


def uncommented(block: str) -> str:
    return "\n".join(
        line for line in block.splitlines() if not line.strip().startswith("#")
    )


def test_the_function_url_declares_no_cors_block() -> None:
    """Two CORS sources send the header twice and every browser rejects it.

    The handler emits the full CORS set and is the same code that enforces the
    origin server-side, which is the check that actually refuses anybody; a
    Function URL `Cors` config only adds response headers and answers preflight.
    With both configured the browser receives

        access-control-allow-origin: https://site, https://site

    and refuses it ("contains multiple values, but only one is allowed"). The
    ask page then shows its fixed "service is not available" string, which is
    correct behaviour and hides the cause completely. curl never sees it: it
    prints the header and does not enforce it. This shipped, and was found by
    loading the live page in a real browser after curl had called the same
    endpoint healthy and answering.
    """
    assert "Cors:" not in uncommented(resource("Url"))


def test_the_function_url_is_reachable_without_authentication() -> None:
    """AuthType NONE is the whole design: an opt-in page with no account."""
    assert "AuthType: NONE" in uncommented(resource("Url"))


def test_both_invoke_grants_are_present() -> None:
    """One grant is not enough on this account, and the symptom is a blanket 403.

    `lambda:InvokeFunctionUrl` alone left every request returning 403 while the
    CORS preflight returned 200, because the URL service answers preflight
    before anything reaches the function.
    """
    body = TEMPLATE.read_text(encoding="utf-8")
    assert "Action: lambda:InvokeFunctionUrl" in body
    assert "Action: lambda:InvokeFunction\n" in body


def test_the_bedrock_grant_has_no_default_and_no_wildcard() -> None:
    """A wildcard here grants every model in the account, not the one deployed."""
    body = TEMPLATE.read_text(encoding="utf-8")
    start = body.index("  BedrockModelArns:")
    end = body.index("  ApiKey:")
    declaration = uncommented(body[start:end])
    assert "Default:" not in declaration, declaration
    assert "*" not in declaration, declaration


@pytest.mark.parametrize(
    ("variable", "why"),
    [
        ("HOMEROOM_ASK_BUNDLE", "the evidence bundle is not where a checkout puts it"),
        ("HOMEROOM_ASK_CORPUS", "the corpus is not where a checkout puts it"),
        ("HOMEROOM_ASK_ORIGIN", "without it the handler refuses nobody"),
    ],
)
def test_the_function_names_the_paths_and_the_origin_it_cannot_infer(
    variable: str, why: str
) -> None:
    assert variable in resource("Function"), why


def test_the_cost_bounds_are_all_wired() -> None:
    """Each of these is a separate ceiling, and one alone does not hold."""
    function = resource("Function")
    assert "ReservedConcurrentExecutions:" in function
    assert "HOMEROOM_ASK_DAILY_CAP" in function
    assert "HOMEROOM_ASK_PER_MINUTE" in function
    assert "AWS::CloudWatch::Alarm" in resource("InvocationAlarm")


def test_the_alarm_has_somewhere_to_fire() -> None:
    """An alarm with an empty action list is a dashboard nobody looks at."""
    assert "AlarmActions: [!Ref AlarmTopic]" in uncommented(resource("InvocationAlarm"))


def test_the_alarm_also_has_a_reader_that_needs_no_address() -> None:
    """Somewhere to fire is not somewhere that reaches a person.

    The topic above has had zero subscriptions since the stack was applied
    (`README.md` in this directory, "Still open"; re-measured against the live
    account 2026-09-12). `AlarmRelayRole` is what lets
    `.github/workflows/ask-alarm-relay.yml` read the alarm's state and report
    it into a GitHub issue instead, so the alarm has a destination that does
    not depend on anyone having given an address.
    """
    role = uncommented(resource("AlarmRelayRole"))
    assert "AWS::IAM::Role" in role
    assert "oidc-provider/token.actions.githubusercontent.com" in role
    assert "AlarmRelayRoleArn" in TEMPLATE.read_text(encoding="utf-8"), (
        "the role's ARN must be an output, or nobody can wire the workflow to it"
    )


def test_the_relay_role_can_only_read_and_only_from_one_branch() -> None:
    """A role that exists to read must not be able to do anything else.

    Two independent failures are asserted, because they fail independently: a
    policy that grew a write action, and a trust policy that stopped naming one
    repository and one branch (which would let a pull request, or a fork,
    assume it).
    """
    role = uncommented(resource("AlarmRelayRole"))
    # The grants only. The trust policy legitimately names an IAM ARN (the OIDC
    # provider), so scanning the whole role for "iam:" would fail on it.
    grants = role.split("Policies:", 1)[1]

    assert "Action: cloudwatch:DescribeAlarms" in grants
    assert "Action: sns:GetTopicAttributes" in grants
    for forbidden in (
        "sns:Publish",
        "sns:Subscribe",
        "lambda:",
        "s3:",
        "bedrock:",
        "iam:",
        "logs:",
        "cloudwatch:PutMetricAlarm",
        "cloudwatch:DeleteAlarms",
        "cloudwatch:*",
        "sns:*",
        'Action: "*"',
    ):
        assert forbidden not in grants, f"the read-only relay role grants {forbidden}"

    # cloudwatch:DescribeAlarms has no resource-level permissions, so its
    # Resource is "*" and must be the ONLY one that is: the topic read is
    # pinned to this stack's own topic.
    assert grants.count('Resource: "*"') == 1
    assert "Resource: !Ref AlarmTopic" in grants

    trust = role.split("Policies:", 1)[0]
    assert "repo:${AlarmRelayRepository}:ref:refs/heads/main" in trust
    assert '"token.actions.githubusercontent.com:aud": sts.amazonaws.com' in trust


def test_the_relay_role_is_not_created_without_a_repository_to_trust() -> None:
    """An empty AlarmRelayRepository must create no role and no trust.

    A default here would let a fork of this template hand read access to a
    repository its deployer does not control, which is the same reasoning
    `BedrockModelArns` carries for having no default.
    """
    body = TEMPLATE.read_text(encoding="utf-8")
    assert 'RelayEnabled: !Not [!Equals [!Ref AlarmRelayRepository, ""]]' in body
    assert "Condition: RelayEnabled" in uncommented(resource("AlarmRelayRole"))
    params = body.split("Conditions:")[0]
    block = params.split("  AlarmRelayRepository:")[1]
    assert 'Default: ""' in block.split("\n\n")[0]


def test_the_logs_expire() -> None:
    assert "RetentionInDays:" in resource("LogGroup")


def test_the_code_bucket_is_private() -> None:
    bucket = resource("CodeBucket")
    for setting in (
        "BlockPublicAcls: true",
        "BlockPublicPolicy: true",
        "IgnorePublicAcls: true",
        "RestrictPublicBuckets: true",
    ):
        assert setting in bucket, setting
