"""Turn the ask stack's CloudWatch alarm state into a redacted GitHub issue.

## What was wrong

`deploy/ask/template.yaml` creates an SNS topic and points the daily-invocation
alarm at it, and `deploy/ask/README.md` has said since the stack was applied
that nobody is subscribed to it. Measured against the live account on
2026-09-12, that is still true: `homeroom-ask-alarms` has zero subscriptions,
confirmed or pending. The alarm has never been able to reach a person. It is
the shape this repository already refuses elsewhere -- a check whose silence
cannot be distinguished from a check that works.

The README's answer was "an address is the owner's to give". This is a
different answer: report into a GitHub issue, which needs no address at all and
lands where the source-freshness and live-integrity findings already land.

## What this reads, and what it will not print

Two read-only AWS responses, captured by `.github/workflows/ask-alarm-relay.yml`
and passed in as files: `cloudwatch describe-alarms` and
`sns get-topic-attributes`. It creates and changes nothing.

The report is ASSEMBLED, not forwarded. This repository is public and its
issues are world-readable, so the body carries fixed prose, integers, alarm
names that matched a strict shape, and a pointer to the log group -- and
nothing else. In particular it never carries an alarm's `StateReason` (which
quotes metric values), any ARN (which carries the AWS account id), or any name
that did not come out of this stack's own template.

`assert_no_identifiers` then re-reads the finished report and refuses to emit
it if anything identifier-shaped survived. That is deliberately redundant with
`safe_alarm_name`: the allowlist is the guarantee and the scan is the proof.
`tests/test_alarm_relay.py` sabotages the allowlist to show the scan catches
what it claims to.

## Three states, not two

An empty alarm list is not "nothing is firing". It means the query failed, the
credentials were wrong or scoped elsewhere, the region is wrong, or the stack
is gone. Every one of those is a state in which nothing is watching anything,
so it is reported as its own finding rather than read as quiet.

Exit codes, in the same spirit as `tools/sources_check.py`:

    0  read cleanly, nothing to report
    1  read cleanly, there is a finding (the report says what)
    2  could not read: the input was missing or malformed

The workflow does not trust the exit code alone -- it reads the verdict marker
out of the report, because a crashed script also exits non-zero and an issue
opened from a crash would assert a finding on no evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

#: Shown in place of an alarm name that did not match the expected shape.
REDACTED = "(name withheld: did not match the expected alarm-name shape)"

#: The only alarm names allowed through verbatim.
#:
#: CloudFormation names this stack's alarm `<stack>-<LogicalId>-<suffix>`, e.g.
#: `homeroom-ask-InvocationAlarm-PH8V5NUNkR30`: the stack name, a logical id
#: from the template, and a generated suffix. Nothing a person or a reader ever
#: typed can take that shape, and an alarm created by hand in the console --
#: which can be named anything at all -- does not match and is withheld.
SAFE_ALARM_NAME = re.compile(r"^homeroom-ask-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$")

#: Patterns that must never appear in a report this module emits. Not the
#: redaction mechanism (`safe_alarm_name` is) -- the assertion that it worked.
IDENTIFIER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("an email address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("a 32-or-more-character hex literal", re.compile(r"\b[0-9a-fA-F]{32,}\b")),
    (
        "a UUID",
        re.compile(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
        ),
    ),
    ("a 12-digit run (an AWS account id is 12 digits)", re.compile(r"\b\d{12}\b")),
    ("an ARN", re.compile(r"arn:aws[a-z-]*:")),
    # A CDS code is the 14-digit key every Homeroom page is keyed on. It is
    # public, but it identifies one named school, and a report that only ever
    # needs counts has no reason to carry one.
    ("a 14-digit CDS code", re.compile(r"\b\d{14}\b")),
)

LOG_GROUP = "/aws/lambda/homeroom-ask"


class Unreadable(Exception):
    """The AWS response was missing or malformed: exit 2, report nothing."""


class WouldLeak(Exception):
    """The finished report contained something identifier-shaped."""


def safe_alarm_name(name: object) -> str:
    """Return `name` if it matched the allowlist, otherwise `REDACTED`."""
    if isinstance(name, str) and SAFE_ALARM_NAME.match(name):
        return name
    return REDACTED


def assert_no_identifiers(text: str, where: str = "the report") -> None:
    """Raise `WouldLeak` if `text` contains anything identifier-shaped."""
    for label, pattern in IDENTIFIER_PATTERNS:
        hit = pattern.search(text)
        if hit:
            raise WouldLeak(
                f"refusing to publish {where}: it contains {label} "
                f"(matched {hit.group(0)!r}). This repository is public. Widen "
                "safe_alarm_name only if the new shape is provably "
                "template-controlled; never widen assert_no_identifiers to make "
                "a report pass."
            )


def build_report(
    alarms: list[dict[str, Any]],
    topic_name: str,
    confirmed: int,
    pending: int,
    *,
    sanitize: Callable[[object], str] = safe_alarm_name,
) -> tuple[bool, str]:
    """Build the issue body. Returns `(there_is_a_finding, markdown)`.

    `sanitize` exists so the test can disable the allowlist and prove the
    final scan still refuses. Production callers do not pass it.
    """
    examined = len(alarms)
    alarming = sorted(
        sanitize(a.get("AlarmName")) for a in alarms if a.get("StateValue") == "ALARM"
    )
    ok = sum(1 for a in alarms if a.get("StateValue") == "OK")
    insufficient = sum(1 for a in alarms if a.get("StateValue") == "INSUFFICIENT_DATA")

    no_alarms_found = examined == 0
    no_destination = confirmed == 0
    finding = no_alarms_found or no_destination or bool(alarming)

    # Compared between runs so a standing condition does not produce a comment
    # every night. Built only from values already proven safe above; a withheld
    # name collapses to a short token rather than repeating the placeholder.
    state = " ".join(
        (
            f"examined={examined}",
            f"alarming={len(alarming)}",
            f"confirmed_subscribers={confirmed}",
            "names="
            + (
                "|".join("withheld" if n == REDACTED else n for n in alarming)
                if alarming
                else "none"
            ),
        )
    )

    out: list[str] = []
    out.append(
        "Filed by `.github/workflows/ask-alarm-relay.yml`, which reads the ask "
        "stack's CloudWatch alarm state directly. It reports whether or not "
        "anything is subscribed to the alarm topic -- that independence is the "
        "point of it."
    )
    out.append("")
    out.append(
        "This issue is updated in place, never duplicated, and never closed by "
        "the workflow. A person closes it, having looked."
    )
    out.append("")
    out.append("## Counts")
    out.append("")
    out.append(f"- Alarms examined: **{examined}**")
    out.append(f"- In `ALARM`: **{len(alarming)}**")
    out.append(f"- In `OK`: **{ok}**")
    out.append(f"- In `INSUFFICIENT_DATA`: **{insufficient}**")
    out.append(f"- Confirmed subscribers on the alarm topic: **{confirmed}**")
    out.append(f"- Pending (unconfirmed) subscriptions on that topic: **{pending}**")
    out.append("")

    if no_alarms_found:
        out.append("## The query returned no alarms")
        out.append("")
        out.append(
            "No alarm matched this stack's prefix. That is not the same as "
            "nothing firing: `deploy/ask/template.yaml` declares "
            "`InvocationAlarm` and the stack is applied, so an empty result "
            "means the query failed, the credentials were wrong or scoped to "
            "another account, the region is wrong, or the alarm was deleted. "
            "Each of those is a state in which nothing is watching the ask "
            "service at all."
        )
        out.append("")

    if no_destination:
        out.append("## The alarm topic has no confirmed subscriber")
        out.append("")
        out.append(
            f"SNS topic `{topic_name}` reports **{confirmed}** confirmed "
            + (
                f"subscriptions ({pending} pending confirmation). "
                if pending
                else "subscriptions. "
            )
            + "The daily-invocation alarm publishes there and nowhere else, so "
            "on the SNS side it reaches nobody. This is the condition "
            "`deploy/ask/README.md` recorded as open when the stack was "
            "applied. This issue is the substitute channel, not a fix for that "
            "one: an SNS subscriber is still worth adding, and adding one needs "
            "no stack change."
        )
        out.append("")

    if alarming:
        out.append("## Alarms currently in `ALARM`")
        out.append("")
        out.extend(f"- `{name}`" for name in alarming)
        out.append("")
        out.append(
            "Names only. An alarm's `StateReason` quotes metric values and "
            "dimensions and is deliberately not reproduced here."
        )
        out.append("")

    out.append("## Where the detail is")
    out.append("")
    out.append(f"- Lambda log group: `{LOG_GROUP}`")
    out.append(
        "- The alarm's threshold and meaning are in `deploy/ask/template.yaml` "
        "(`InvocationAlarm`, `DailyInvocationAlarm`), and the cost envelope it "
        "guards is in `deploy/ask/README.md`."
    )
    out.append("")
    out.append(f"<!-- alarm-relay-verdict: {'report' if finding else 'clear'} -->")
    out.append(f"<!-- alarm-relay-state: {state} -->")

    body = "\n".join(out)
    assert_no_identifiers(body)
    return finding, body


def _load(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Unreadable(f"could not read {what} from {path}: {exc}") from exc


def run(alarms_path: Path, topic_path: Path, out_path: Path) -> int:
    alarms_doc = _load(alarms_path, "the describe-alarms response")
    topic_doc = _load(topic_path, "the get-topic-attributes response")

    # A missing key is a malformed response, which is a different thing from an
    # empty list and is not allowed to decay into one.
    metric_alarms = (
        alarms_doc.get("MetricAlarms") if isinstance(alarms_doc, dict) else None
    )
    if not isinstance(metric_alarms, list):
        raise Unreadable("describe-alarms response carries no MetricAlarms list")

    attributes = topic_doc.get("Attributes") if isinstance(topic_doc, dict) else None
    if not isinstance(attributes, dict) or not isinstance(
        attributes.get("TopicArn"), str
    ):
        raise Unreadable("get-topic-attributes response carries no Attributes.TopicArn")

    # The ARN is read to derive the topic NAME and then dropped: it carries the
    # AWS account id, and this report is published publicly.
    topic_name = attributes["TopicArn"].rsplit(":", 1)[-1]
    if safe_alarm_name(topic_name) == REDACTED:
        topic_name = REDACTED

    finding, body = build_report(
        metric_alarms,
        topic_name,
        int(attributes.get("SubscriptionsConfirmed", 0)),
        int(attributes.get("SubscriptionsPending", 0)),
    )
    out_path.write_text(body + "\n", encoding="utf-8")
    return 1 if finding else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alarms", type=Path, required=True)
    parser.add_argument("--topic", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        return run(args.alarms, args.topic, args.out)
    except (Unreadable, WouldLeak) as exc:
        # Loud, not quiet. A relay that cannot report must not exit 0 with
        # nothing to say; that is the defect it exists to remove, one layer up.
        print(f"alarm-relay: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised by the workflow
    raise SystemExit(main())
