#!/usr/bin/env python3
"""Validate protected release tags and bind hosted state into a signed tag.

The committed tag ruleset is the reviewable policy.  The GitHub Metadata API
is queried with an ordinary read token; no ruleset-administration credential is
accepted by the release workflow.  GitHub may redact ``bypass_actors`` from
that response.  In that case the release owner makes the missing assertion by
signing an exact annotated-tag message bound to the hosted ruleset id and
``updated_at`` value.  Any later ruleset edit invalidates that assertion.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

RULESET_NAME = "protect-release-tags"
SEMVER_TAG_RE = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SSH_SIGNATURE_MARKER = "-----BEGIN SSH SIGNATURE-----"


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_ruleset(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return None, [f"cannot load tag ruleset profile {path}: {exc}"]
    if not isinstance(value, dict):
        return None, ["tag ruleset profile root must be an object"]
    return value, []


def validate_ruleset(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected_keys = {
        "name",
        "target",
        "enforcement",
        "conditions",
        "rules",
        "bypass_actors",
    }
    if set(value) != expected_keys:
        errors.append("tag ruleset must contain only the canonical top-level fields")
    for field, expected in (
        ("name", RULESET_NAME),
        ("target", "tag"),
        ("enforcement", "active"),
        ("bypass_actors", []),
    ):
        if value.get(field) != expected:
            errors.append(f"tag ruleset `{field}` must be exactly {expected!r}")

    conditions = value.get("conditions")
    expected_conditions = {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}}
    if conditions != expected_conditions:
        errors.append(
            "tag ruleset conditions must include exactly refs/tags/v* with no exclusions"
        )

    rules = value.get("rules")
    expected_rules = {"update", "deletion"}
    if not isinstance(rules, list):
        errors.append("tag ruleset `rules` must be an array")
    else:
        actual: list[str] = []
        for rule in rules:
            if not isinstance(rule, dict) or set(rule) != {"type"}:
                errors.append(
                    "tag rules must be parameterless objects containing only `type`"
                )
                continue
            rule_type = rule.get("type")
            if not isinstance(rule_type, str):
                errors.append("tag rule type must be a string")
                continue
            actual.append(rule_type)
        if len(actual) != len(set(actual)):
            errors.append("tag rule types must be unique")
        if set(actual) != expected_rules:
            errors.append("tag ruleset must contain exactly deletion and update")
    return errors


def security_snapshot(value: dict[str, Any], *, include_bypass: bool) -> dict[str, Any]:
    snapshot = {
        "name": value.get("name"),
        "target": value.get("target"),
        "enforcement": value.get("enforcement"),
        "conditions": value.get("conditions"),
        "rules": sorted(
            (
                rule
                for rule in value.get("rules", [])
                if isinstance(rule, dict) and isinstance(rule.get("type"), str)
            ),
            key=lambda rule: rule["type"],
        ),
    }
    if include_bypass:
        snapshot["bypass_actors"] = value.get("bypass_actors")
    return snapshot


def _gh_api(endpoint: str) -> Any:
    result = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", endpoint],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"gh api {endpoint} failed")
    try:
        return json.loads(
            result.stdout, object_pairs_hook=_object_without_duplicate_keys
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"gh api {endpoint} returned invalid JSON: {exc}") from exc


def _list_response(value: Any) -> list[Any] | None:
    if not isinstance(value, list):
        return None
    if all(isinstance(page, list) for page in value):
        return [item for page in value for item in page]
    return value


def _detail_response(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        return value[0]
    return None


def _canonical_timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip() or "\n" in value:
        return None
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    canonical = parsed.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")
    return canonical if canonical == value else None


def fetch_hosted_ruleset(
    repository: str,
    *,
    api: Callable[[str], Any] = _gh_api,
    environ: dict[str, str] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    if not REPOSITORY_RE.fullmatch(repository):
        return None, ["hosted tag ruleset check requires exact owner/repository"]
    env = os.environ if environ is None else environ
    if api is _gh_api and not env.get("GH_TOKEN") and not env.get("GITHUB_TOKEN"):
        # Local `gh` credential storage remains supported; CI must be explicit.
        if env.get("GITHUB_ACTIONS") == "true":
            return None, [
                "CI hosted tag ruleset check requires GH_TOKEN or GITHUB_TOKEN"
            ]
    if api is _gh_api and shutil.which("gh") is None:
        return None, ["hosted tag ruleset check requires the `gh` CLI"]

    list_endpoint = f"repos/{repository}/rulesets?includes_parents=false&per_page=100"
    try:
        summaries = _list_response(api(list_endpoint))
    except (OSError, RuntimeError) as exc:
        return None, [f"GitHub tag ruleset-list lookup failed closed: {exc}"]
    if summaries is None:
        return None, ["GitHub tag ruleset-list response is not an array"]
    matches = [
        item
        for item in summaries
        if isinstance(item, dict)
        and item.get("name") == RULESET_NAME
        and item.get("target") in (None, "tag")
        and item.get("enforcement") == "active"
    ]
    if len(matches) != 1:
        return None, [
            "expected exactly one active hosted tag ruleset named "
            f"`{RULESET_NAME}`; found {len(matches)}"
        ]
    ruleset_id = matches[0].get("id")
    if (
        not isinstance(ruleset_id, int)
        or isinstance(ruleset_id, bool)
        or ruleset_id < 1
    ):
        return None, ["hosted tag ruleset id is missing or malformed"]
    try:
        hosted = _detail_response(api(f"repos/{repository}/rulesets/{ruleset_id}"))
    except (OSError, RuntimeError) as exc:
        return None, [f"GitHub tag ruleset-detail lookup failed closed: {exc}"]
    if hosted is None:
        return None, ["GitHub tag ruleset-detail response is not an object"]
    errors: list[str] = []
    if hosted.get("id") != ruleset_id:
        errors.append("hosted tag ruleset detail id differs from list response")
    if hosted.get("source_type") != "Repository":
        errors.append("hosted tag ruleset must be repository-owned")
    source = hosted.get("source")
    if not isinstance(source, str) or source.casefold() != repository.casefold():
        errors.append("hosted tag ruleset source differs from repository")
    if _canonical_timestamp(hosted.get("updated_at")) is None:
        errors.append("hosted tag ruleset updated_at is missing or non-canonical")
    return (None, errors) if errors else (hosted, [])


def validate_hosted_parity(
    committed: dict[str, Any], hosted: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    bypass_visible = "bypass_actors" in hosted
    if bypass_visible and hosted.get("bypass_actors") != []:
        errors.append("hosted tag ruleset bypass actors must be exactly empty")
    expected = security_snapshot(committed, include_bypass=bypass_visible)
    actual = security_snapshot(hosted, include_bypass=bypass_visible)
    if actual != expected:
        errors.append(
            "API-visible hosted tag security profile differs from "
            "`.github/rulesets/tags.json`"
        )
    return errors


def tag_message(tag: str, ruleset_id: int, updated_at: str) -> str:
    if not SEMVER_TAG_RE.fullmatch(tag):
        raise ValueError("release tag must be canonical vX.Y.Z")
    if (
        not isinstance(ruleset_id, int)
        or isinstance(ruleset_id, bool)
        or ruleset_id < 1
    ):
        raise ValueError("tag ruleset id must be a positive integer")
    if _canonical_timestamp(updated_at) is None:
        raise ValueError("tag ruleset updated_at must be canonical UTC RFC 3339")
    return "\n".join(
        (
            f"Release {tag}",
            f"Tag-Ruleset-Name: {RULESET_NAME}",
            f"Tag-Ruleset-ID: {ruleset_id}",
            f"Tag-Ruleset-Updated-At: {updated_at}",
            "Tag-Ruleset-Bypass-Actors: empty",
        )
    )


def signed_tag_message(repo_root: Path, tag: str) -> str:
    if not SEMVER_TAG_RE.fullmatch(tag):
        raise ValueError("release tag must be canonical vX.Y.Z")
    result = subprocess.run(
        ["git", "-C", str(repo_root), "cat-file", "tag", f"refs/tags/{tag}"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or f"cannot read annotated tag {tag}")
    try:
        _, body = result.stdout.split("\n\n", 1)
    except ValueError as exc:
        raise ValueError(f"annotated tag {tag} has no message body") from exc
    marker = f"\n{SSH_SIGNATURE_MARKER}\n"
    if marker not in body:
        raise ValueError(f"annotated tag {tag} has no embedded SSH signature")
    message, _ = body.split(marker, 1)
    return message.rstrip("\n")


def verify_tag_message(
    repo_root: Path, tag: str, ruleset_id: int, updated_at: str
) -> list[str]:
    try:
        actual = signed_tag_message(repo_root, tag)
        expected = tag_message(tag, ruleset_id, updated_at)
    except (OSError, ValueError) as exc:
        return [str(exc)]
    if actual != expected:
        return [
            "signed tag message does not exactly bind the current hosted tag "
            "ruleset id/updated_at and an empty bypass list"
        ]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ruleset", type=Path)
    parser.add_argument("--hosted", action="store_true")
    parser.add_argument("--repository")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--tag")
    message = parser.add_mutually_exclusive_group()
    message.add_argument("--print-tag-message", action="store_true")
    message.add_argument("--verify-tag-message", action="store_true")
    args = parser.parse_args(argv)
    if args.hosted and not args.repository:
        parser.error("--hosted requires --repository")
    if (args.print_tag_message or args.verify_tag_message) and (
        not args.hosted or not args.tag
    ):
        parser.error("tag-message operations require --hosted and --tag")

    committed, errors = load_ruleset(args.ruleset)
    hosted: dict[str, Any] | None = None
    if committed is not None:
        errors.extend(validate_ruleset(committed))
    if args.hosted and committed is not None and not errors:
        hosted, hosted_errors = fetch_hosted_ruleset(args.repository)
        errors.extend(hosted_errors)
        if hosted is not None:
            errors.extend(validate_hosted_parity(committed, hosted))
    if (
        args.verify_tag_message
        and hosted is not None
        and not errors
        and args.tag is not None
    ):
        errors.extend(
            verify_tag_message(
                args.repo_root,
                args.tag,
                hosted["id"],
                hosted["updated_at"],
            )
        )
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if args.print_tag_message:
        assert hosted is not None and args.tag is not None
        print(tag_message(args.tag, hosted["id"], hosted["updated_at"]))
    else:
        mode = "hosted" if args.hosted else "committed"
        print(f"PASS: release tag ruleset ({mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
