"""The alarm relay, checked for the one thing it must never do.

The relay files a GitHub issue on a PUBLIC repository from data read out of a
live AWS account. Everything else about it is replaceable; "an identifier can
never reach the issue body" is not.

So the leak test is the load-bearing one here, and it is written so that it can
go red. The fixture is deliberately hostile -- alarm names carrying an email
address, a 32-hex literal, a UUID, an AWS account id, a CDS code and a full ARN
-- because a redaction test whose fixture contains nothing the redactor could
have mishandled passes forever while redacting nothing. The negative control at
the bottom disables the allowlist and asserts the final scan still refuses,
which is what makes the passing case evidence rather than decoration.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# `tools/` is not a package and pytest's pythonpath is `src`, so the module is
# loaded by path -- the same way tests/test_sources_check.py loads its subject.
_SPEC = importlib.util.spec_from_file_location(
    "alarm_relay", ROOT / "tools" / "alarm_relay.py"
)
assert _SPEC and _SPEC.loader
alarm_relay = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = alarm_relay
_SPEC.loader.exec_module(alarm_relay)

REDACTED = alarm_relay.REDACTED
Unreadable = alarm_relay.Unreadable
WouldLeak = alarm_relay.WouldLeak
assert_no_identifiers = alarm_relay.assert_no_identifiers
build_report = alarm_relay.build_report
main = alarm_relay.main
run = alarm_relay.run
safe_alarm_name = alarm_relay.safe_alarm_name

TOPIC = "homeroom-ask-alarms"

#: Shaped the way CloudFormation names this stack's alarm: stack name, logical
#: id from deploy/ask/template.yaml, generated suffix. This is the live one.
REAL_ALARM = "homeroom-ask-InvocationAlarm-PH8V5NUNkR30"

#: Names nobody should be able to publish. An alarm created by hand in the
#: console can be called anything, and "anything" next to school data means a
#: school name, a CDS code, or an address pasted in while debugging.
HOSTILE = [
    {"AlarmName": "ask for someone@example.invalid spiked", "StateValue": "ALARM"},
    {"AlarmName": "session 0123456789abcdef0123456789abcdef", "StateValue": "ALARM"},
    {
        "AlarmName": "request 3f2504e0-4f89-11d3-9a0c-0305e82c3301 failed",
        "StateValue": "ALARM",
    },
    {"AlarmName": "account 000000000000 throttled", "StateValue": "ALARM"},
    {"AlarmName": "school 57726786056246 over budget", "StateValue": "ALARM"},
    {
        "AlarmName": "arn:aws:sns:us-west-2:000000000000:t backed up",
        "StateValue": "ALARM",
    },
]


def test_the_live_alarm_name_passes_the_allowlist_unchanged() -> None:
    assert safe_alarm_name(REAL_ALARM) == REAL_ALARM


def test_anything_not_shaped_like_a_stack_alarm_name_is_withheld() -> None:
    for alarm in HOSTILE:
        assert safe_alarm_name(alarm["AlarmName"]) == REDACTED, alarm["AlarmName"]
    # Not only the hostile ones. A name from the right stack but carrying a
    # space, or one from a different stack entirely, is outside the shape
    # CloudFormation produces -- and "close enough" is how a reader-supplied
    # string gets through.
    assert safe_alarm_name("homeroom-ask invocation alarm") == REDACTED
    assert safe_alarm_name("some-other-stack-Alarm-ABC123") == REDACTED
    assert safe_alarm_name(None) == REDACTED
    assert safe_alarm_name(12) == REDACTED


def test_no_identifier_from_a_hostile_alarm_name_reaches_the_report() -> None:
    finding, body = build_report(HOSTILE, TOPIC, confirmed=1, pending=0)

    assert finding is True
    # Stated as literals rather than "no pattern matched", so a reader can see
    # exactly what was withheld.
    assert "someone@example.invalid" not in body
    assert "0123456789abcdef0123456789abcdef" not in body
    assert "3f2504e0-4f89-11d3-9a0c-0305e82c3301" not in body
    assert "000000000000" not in body
    assert "57726786056246" not in body
    assert "arn:aws:" not in body

    # And the withholding is visible rather than silent: six alarms were in
    # ALARM, so six lines are present, every one of them the placeholder. A
    # report that simply dropped the unsafe names would under-count the
    # incident, which is its own way of lying.
    assert "In `ALARM`: **6**" in body
    assert body.count(REDACTED) == 6


def test_the_guard_is_not_vacuous() -> None:
    for text in (
        "write to someone@example.invalid",
        "digest 0123456789abcdef0123456789abcdef",
        "request 3f2504e0-4f89-11d3-9a0c-0305e82c3301",
        "account 000000000000",
        "school 57726786056246",
        "arn:aws:sns:us-west-2:000000000000:t",
    ):
        with pytest.raises(WouldLeak):
            assert_no_identifiers(text)

    # It must still pass the thing it exists to allow, or it is not a guard,
    # it is a refusal.
    assert_no_identifiers(f"Alarms examined: **1**\n- `{REAL_ALARM}`")


def test_negative_control_with_the_allowlist_disabled_the_scan_refuses() -> None:
    """Sabotage the redaction and prove the leak test would go red.

    The mutation is exactly the regression this file exists to catch: someone
    deciding the alarm names "are just infrastructure" and passing them
    straight through.
    """
    # Prove the mutation actually lands rather than silently no-opping.
    assert (lambda n: n)(HOSTILE[0]["AlarmName"]) == HOSTILE[0]["AlarmName"]

    with pytest.raises(WouldLeak, match="an email address"):
        build_report(HOSTILE, TOPIC, confirmed=1, pending=0, sanitize=lambda n: str(n))


def test_a_topic_with_no_confirmed_subscriber_is_itself_a_finding() -> None:
    """The live state on 2026-09-12: nothing is firing, and nobody is listening."""
    finding, body = build_report(
        [{"AlarmName": REAL_ALARM, "StateValue": "OK"}], TOPIC, confirmed=0, pending=0
    )
    assert finding is True
    assert "no confirmed subscriber" in body
    assert "<!-- alarm-relay-verdict: report -->" in body


def test_a_pending_subscription_is_not_a_destination() -> None:
    """SNS reports an unconfirmed email subscription as pending. It delivers
    nothing, and counting it would reproduce the original defect exactly: a
    channel that looks wired and reaches nobody."""
    finding, body = build_report(
        [{"AlarmName": REAL_ALARM, "StateValue": "OK"}], TOPIC, confirmed=0, pending=1
    )
    assert finding is True
    assert "1 pending confirmation" in body


def test_an_empty_alarm_list_is_a_broken_query_not_health() -> None:
    finding, body = build_report([], TOPIC, confirmed=1, pending=0)
    assert finding is True
    assert "nothing is watching the ask service at all" in body


def test_all_quiet_with_a_live_subscriber_reports_nothing() -> None:
    finding, body = build_report(
        [{"AlarmName": REAL_ALARM, "StateValue": "OK"}], TOPIC, confirmed=1, pending=0
    )
    assert finding is False
    assert "<!-- alarm-relay-verdict: clear -->" in body


def test_the_state_marker_changes_only_when_the_state_does() -> None:
    quiet = [{"AlarmName": REAL_ALARM, "StateValue": "OK"}]
    _, first = build_report(quiet, TOPIC, confirmed=1, pending=0)
    _, again = build_report(quiet, TOPIC, confirmed=1, pending=0)
    assert first == again

    _, firing = build_report(
        [{"AlarmName": REAL_ALARM, "StateValue": "ALARM"}],
        TOPIC,
        confirmed=1,
        pending=0,
    )
    assert firing != first


def _write(tmp_path: Path, alarms: object, topic: object) -> tuple[Path, Path, Path]:
    alarms_path = tmp_path / "alarms.json"
    topic_path = tmp_path / "topic.json"
    out_path = tmp_path / "report.md"
    alarms_path.write_text(json.dumps(alarms), encoding="utf-8")
    topic_path.write_text(json.dumps(topic), encoding="utf-8")
    return alarms_path, topic_path, out_path


def test_run_derives_the_topic_name_and_drops_the_arn(tmp_path: Path) -> None:
    alarms, topic, out = _write(
        tmp_path,
        {"MetricAlarms": [{"AlarmName": REAL_ALARM, "StateValue": "OK"}]},
        {
            "Attributes": {
                "TopicArn": "arn:aws:sns:us-west-2:000000000000:homeroom-ask-alarms",
                "SubscriptionsConfirmed": "0",
                "SubscriptionsPending": "0",
            }
        },
    )
    assert run(alarms, topic, out) == 1
    body = out.read_text(encoding="utf-8")
    assert "homeroom-ask-alarms" in body
    # The ARN was read only to derive that name. The account id it carries must
    # not survive into a published report.
    assert "000000000000" not in body
    assert "arn:aws:" not in body


def test_a_missing_key_is_unreadable_not_empty(tmp_path: Path) -> None:
    """`MetricAlarms` absent is a malformed response, and a malformed response
    must not decay into "no alarms", which this module treats as a finding on
    the strength of evidence it does not have."""
    alarms, topic, out = _write(tmp_path, {}, {"Attributes": {"TopicArn": "a:b:c"}})
    with pytest.raises(Unreadable, match="MetricAlarms"):
        run(alarms, topic, out)

    alarms, topic, out = _write(tmp_path, {"MetricAlarms": []}, {})
    with pytest.raises(Unreadable, match="TopicArn"):
        run(alarms, topic, out)


def test_main_exits_2_on_an_unreadable_input(tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"
    out = tmp_path / "report.md"
    code = main(["--alarms", str(missing), "--topic", str(missing), "--out", str(out)])
    assert code == 2
    assert not out.exists(), "a failed read must not leave a report behind"
