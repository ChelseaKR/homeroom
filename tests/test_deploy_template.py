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
