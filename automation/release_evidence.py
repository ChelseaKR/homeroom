#!/usr/bin/env python3
"""Deterministic release artifacts and exact offline attestation policy checks.

The release workflow deliberately keeps signing separate from repository code.
This helper runs only in read-only build/verification jobs.  Cosign performs the
cryptographic verification first; ``verify-bundle`` then applies the repository's
policy to the authenticated DSSE statement in that exact bundle.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import gzip
import hashlib
import importlib
import importlib.metadata
import json
import re
import shutil
import subprocess
import tarfile
import zipfile
from collections.abc import Iterable
from email.parser import Parser
from pathlib import Path
from typing import Any
from urllib.parse import quote

SLSA_V1 = "https://slsa.dev/provenance/v1"
CYCLONEDX_PREDICATE = "https://cyclonedx.org/bom"
STATEMENT_V1 = "https://in-toto.io/Statement/v1"
SEMVER_TAG_RE = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class ReleaseEvidenceError(ValueError):
    """A release artifact or evidence object violates the release contract."""


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseEvidenceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseEvidenceError(f"cannot read JSON {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_timestamp(value: str) -> str:
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ReleaseEvidenceError(f"invalid RFC 3339 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ReleaseEvidenceError("release timestamp must include a UTC offset")
    return parsed.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def build_source_archive(repo_root: Path, ref: str, prefix: str, output: Path) -> None:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", prefix):
        raise ReleaseEvidenceError(
            "archive prefix must be a safe single path component"
        )
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "archive",
            "--format=tar",
            f"--prefix={prefix}/",
            ref,
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise ReleaseEvidenceError(f"git archive failed: {stderr}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw, gzip.GzipFile(
        filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0
    ) as compressed:
        compressed.write(result.stdout)


def _normalise_project_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _pypi_purl(name: str, version: str) -> str:
    return f"pkg:pypi/{quote(_normalise_project_name(name))}@{quote(version)}"


def _github_purl(repository: str, version: str) -> str:
    if not REPOSITORY_RE.fullmatch(repository):
        raise ReleaseEvidenceError("repository must be owner/name")
    owner, name = repository.split("/", 1)
    return f"pkg:github/{quote(owner)}/{quote(name)}@{quote(version)}"


def _component(
    *, name: str, version: str, purl: str, digest: str, component_type: str
) -> dict[str, Any]:
    if not SHA256_RE.fullmatch(digest):
        raise ReleaseEvidenceError(f"invalid SHA-256 for component {name!r}")
    return {
        "type": component_type,
        "bom-ref": purl,
        "name": name,
        "version": version,
        "purl": purl,
        "hashes": [{"alg": "SHA-256", "content": digest}],
    }


def source_sbom(
    *,
    artifact: Path,
    name: str,
    version: str,
    repository: str,
    timestamp: str,
) -> dict[str, Any]:
    root = _component(
        name=name,
        version=version,
        purl=_github_purl(repository, version),
        digest=sha256_file(artifact),
        component_type="application",
    )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "serialNumber": f"urn:uuid:{_stable_uuid(root['hashes'][0]['content'])}",
        "version": 1,
        "metadata": {
            "timestamp": _canonical_timestamp(timestamp),
            "component": root,
            "properties": [
                {
                    "name": "portfolio.release.sbom.scope",
                    "value": "source archive; no runtime package dependency set",
                }
            ],
        },
        "components": [],
    }


def _stable_uuid(hex_digest: str) -> str:
    raw = bytearray.fromhex(hex_digest[:32])
    raw[6] = (raw[6] & 0x0F) | 0x50
    raw[8] = (raw[8] & 0x3F) | 0x80
    text = raw.hex()
    return f"{text[:8]}-{text[8:12]}-{text[12:16]}-{text[16:20]}-{text[20:]}"


def _distribution_digest(distribution: importlib.metadata.Distribution) -> str:
    files = distribution.files or []
    selected = []
    for relative in sorted(files, key=str):
        text = str(relative).replace("\\", "/")
        if text.endswith(".pyc") or "/__pycache__/" in f"/{text}":
            continue
        located = Path(distribution.locate_file(relative))
        if located.is_file():
            selected.append((text, located))
    if not selected:
        name = distribution.metadata.get("Name", "<unknown>")
        raise ReleaseEvidenceError(
            f"installed distribution {name!r} has no hashable files"
        )
    digest = hashlib.sha256()
    for relative, located in selected:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(located)))
    return digest.hexdigest()


def runtime_sbom(
    *,
    artifact: Path,
    project_name: str,
    version: str,
    timestamp: str,
) -> dict[str, Any]:
    expected = _normalise_project_name(project_name)
    components: list[dict[str, Any]] = []
    root_found = False
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        dist_version = distribution.version
        if not name or not dist_version:
            raise ReleaseEvidenceError(
                "installed distribution lacks Name or Version metadata"
            )
        normalised = _normalise_project_name(name)
        if normalised == expected:
            root_found = True
            if dist_version != version:
                raise ReleaseEvidenceError(
                    f"installed project version {dist_version!r} != {version!r}"
                )
            continue
        components.append(
            _component(
                name=name,
                version=dist_version,
                purl=_pypi_purl(name, dist_version),
                digest=_distribution_digest(distribution),
                component_type="library",
            )
        )
    if not root_found:
        raise ReleaseEvidenceError(
            f"installed project distribution {project_name!r} not found"
        )
    root = _component(
        name=project_name,
        version=version,
        purl=_pypi_purl(project_name, version),
        digest=sha256_file(artifact),
        component_type="application",
    )
    components.sort(key=lambda item: (item["name"].lower(), item["version"]))
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.7",
        "serialNumber": f"urn:uuid:{_stable_uuid(root['hashes'][0]['content'])}",
        "version": 1,
        "metadata": {
            "timestamp": _canonical_timestamp(timestamp),
            "component": root,
            "properties": [
                {
                    "name": "portfolio.release.sbom.scope",
                    "value": "built package plus locked production environment; dev groups excluded",
                }
            ],
        },
        "components": components,
    }


def _validate_component(value: Any, location: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{location} must be an object")
        return
    for field in ("name", "version", "purl", "bom-ref"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            errors.append(f"{location}.{field} must be a non-empty string")
    if isinstance(value.get("purl"), str) and not value["purl"].startswith("pkg:"):
        errors.append(f"{location}.purl must be a package URL")
    hashes = value.get("hashes")
    if not isinstance(hashes, list) or len(hashes) != 1:
        errors.append(f"{location}.hashes must contain exactly one SHA-256")
    elif not isinstance(hashes[0], dict):
        errors.append(f"{location}.hashes entries must be objects")
    elif hashes[0].get("alg") != "SHA-256" or not SHA256_RE.fullmatch(
        str(hashes[0].get("content", ""))
    ):
        errors.append(f"{location}.hashes must contain a canonical SHA-256")


def validate_sbom(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["SBOM root must be an object"]
    if value.get("bomFormat") != "CycloneDX":
        errors.append("SBOM bomFormat must be CycloneDX")
    if value.get("specVersion") != "1.7":
        errors.append("SBOM specVersion must be 1.7")
    if value.get("version") != 1:
        errors.append("SBOM version must be 1")
    metadata = value.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("SBOM metadata must be an object")
    else:
        try:
            _canonical_timestamp(str(metadata.get("timestamp", "")))
        except ReleaseEvidenceError as exc:
            errors.append(str(exc))
        _validate_component(metadata.get("component"), "metadata.component", errors)
    components = value.get("components")
    if not isinstance(components, list):
        errors.append("SBOM components must be an array")
        components = []
    seen: set[str] = set()
    for index, component in enumerate(components):
        _validate_component(component, f"components[{index}]", errors)
        if isinstance(component, dict) and isinstance(component.get("bom-ref"), str):
            if component["bom-ref"] in seen:
                errors.append(f"duplicate component bom-ref: {component['bom-ref']}")
            seen.add(component["bom-ref"])
    return errors


def _artifact_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise ReleaseEvidenceError(
            f"build output directory does not exist: {directory}"
        )
    files = sorted(path for path in directory.iterdir() if path.is_file())
    wheels = [path for path in files if path.suffix == ".whl"]
    sdists = [path for path in files if path.name.endswith(".tar.gz")]
    if len(files) != 2 or len(wheels) != 1 or len(sdists) != 1:
        raise ReleaseEvidenceError(
            f"expected exactly one wheel and one sdist in {directory}; found "
            + ", ".join(path.name for path in files)
        )
    return files


def compare_builds(first: Path, second: Path, output: Path) -> None:
    first_files = _artifact_files(first)
    second_files = _artifact_files(second)
    if [path.name for path in first_files] != [path.name for path in second_files]:
        raise ReleaseEvidenceError("independent builds produced different filenames")
    for left, right in zip(first_files, second_files):
        if sha256_file(left) != sha256_file(right):
            raise ReleaseEvidenceError(f"independent builds differ: {left.name}")
    if output.exists():
        if output.resolve() in {Path("/").resolve(), Path.cwd().resolve()}:
            raise ReleaseEvidenceError("refusing to replace an unsafe output directory")
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for source in first_files:
        shutil.copyfile(source, output / source.name)


def _metadata_from_bytes(raw: bytes) -> tuple[str, str]:
    message = Parser().parsestr(raw.decode("utf-8"))
    name = message.get("Name")
    version = message.get("Version")
    if not name or not version:
        raise ReleaseEvidenceError("built package metadata lacks Name or Version")
    return name, version


def _wheel_identity(path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(path) as archive:
        matches = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(matches) != 1:
            raise ReleaseEvidenceError(
                f"wheel {path.name} has {len(matches)} METADATA files"
            )
        return _metadata_from_bytes(archive.read(matches[0]))


def _sdist_identity(path: Path) -> tuple[str, str]:
    with tarfile.open(path, mode="r:gz") as archive:
        matches = [
            member
            for member in archive.getmembers()
            if member.isfile()
            and member.name.count("/") == 1
            and member.name.endswith("/PKG-INFO")
        ]
        if len(matches) != 1:
            raise ReleaseEvidenceError(
                f"sdist {path.name} has {len(matches)} root PKG-INFO files"
            )
        stream = archive.extractfile(matches[0])
        if stream is None:
            raise ReleaseEvidenceError(f"cannot read PKG-INFO from {path.name}")
        return _metadata_from_bytes(stream.read())


def verify_dist(directory: Path, project_name: str, version: str) -> None:
    expected_name = _normalise_project_name(project_name)
    for artifact in _artifact_files(directory):
        name, built_version = (
            _wheel_identity(artifact)
            if artifact.suffix == ".whl"
            else _sdist_identity(artifact)
        )
        if _normalise_project_name(name) != expected_name:
            raise ReleaseEvidenceError(
                f"{artifact.name} project name {name!r} != {project_name!r}"
            )
        if built_version != version:
            raise ReleaseEvidenceError(
                f"{artifact.name} version {built_version!r} != {version!r}"
            )


def runtime_version(import_name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", import_name):
        raise ReleaseEvidenceError(
            "runtime import name is not a dotted Python identifier"
        )
    module = importlib.import_module(import_name)
    value = getattr(module, "__version__", None)
    if not isinstance(value, str) or not value:
        raise ReleaseEvidenceError(
            f"{import_name}.__version__ is missing or not a string"
        )
    return value


def provenance_predicate(
    *,
    repository: str,
    source_commit: str,
    tag: str,
    tag_object_sha: str,
    builder_id: str,
    invocation_id: str,
) -> dict[str, Any]:
    if not REPOSITORY_RE.fullmatch(repository):
        raise ReleaseEvidenceError("repository must be owner/name")
    if not GIT_SHA_RE.fullmatch(source_commit):
        raise ReleaseEvidenceError(
            "source commit must be a lowercase 40-character git SHA"
        )
    if not GIT_SHA_RE.fullmatch(tag_object_sha):
        raise ReleaseEvidenceError(
            "tag object must be a lowercase 40-character git SHA"
        )
    if not SEMVER_TAG_RE.fullmatch(tag):
        raise ReleaseEvidenceError("tag must be canonical vX.Y.Z")
    repo_uri = f"https://github.com/{repository}"
    return {
        "buildDefinition": {
            "buildType": f"{repo_uri}/.github/workflows/release.yml/trusted-main/v1",
            "externalParameters": {
                "repository": repo_uri,
                "sourceCommit": source_commit,
                "sourceRef": f"refs/tags/{tag}",
                "tag": tag,
                "tagObjectSha": tag_object_sha,
            },
            "internalParameters": {},
            "resolvedDependencies": [
                {
                    "uri": f"git+{repo_uri}@refs/tags/{tag}",
                    "digest": {"gitCommit": source_commit},
                }
            ],
        },
        "runDetails": {
            "builder": {"id": builder_id},
            "metadata": {"invocationId": invocation_id},
            "byproducts": [],
        },
    }


def _statement_from_bundle(bundle_path: Path) -> dict[str, Any]:
    bundle = load_json(bundle_path)
    if not isinstance(bundle, dict) or not isinstance(bundle.get("dsseEnvelope"), dict):
        raise ReleaseEvidenceError("Sigstore bundle has no DSSE envelope")
    envelope = bundle["dsseEnvelope"]
    if envelope.get("payloadType") not in {
        "application/vnd.in-toto+json",
        "application/vnd.in-toto.provenance+json",
        "application/vnd.in-toto.cyclonedx+json",
    }:
        raise ReleaseEvidenceError(
            "Sigstore bundle has an unexpected DSSE payload type"
        )
    payload = envelope.get("payload")
    if not isinstance(payload, str):
        raise ReleaseEvidenceError("Sigstore bundle DSSE payload is missing")
    try:
        decoded = base64.b64decode(payload, validate=True).decode("utf-8")
        statement = json.loads(
            decoded, object_pairs_hook=_object_without_duplicate_keys
        )
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseEvidenceError(f"cannot decode DSSE statement: {exc}") from exc
    if not isinstance(statement, dict):
        raise ReleaseEvidenceError("DSSE statement must be an object")
    return statement


def verify_bundle_statement(
    *,
    bundle: Path,
    artifact: Path,
    kind: str,
    expected_predicate: Path,
    repository: str | None = None,
    source_commit: str | None = None,
    tag: str | None = None,
    tag_object_sha: str | None = None,
    builder_id: str | None = None,
    invocation_id: str | None = None,
) -> None:
    statement = _statement_from_bundle(bundle)
    if statement.get("_type") != STATEMENT_V1:
        raise ReleaseEvidenceError("attestation statement type is not in-toto v1")
    subject = statement.get("subject")
    expected_subject = [
        {"name": artifact.name, "digest": {"sha256": sha256_file(artifact)}}
    ]
    if subject != expected_subject:
        raise ReleaseEvidenceError(
            "attestation subject name/digest does not match artifact"
        )
    predicate = statement.get("predicate")
    expected = load_json(expected_predicate)
    if predicate != expected:
        raise ReleaseEvidenceError(
            "authenticated predicate differs from retained predicate file"
        )
    if kind == "provenance":
        required_values = {
            "repository": repository,
            "source commit": source_commit,
            "tag": tag,
            "tag object SHA": tag_object_sha,
            "builder ID": builder_id,
            "invocation ID": invocation_id,
        }
        missing = [label for label, value in required_values.items() if not value]
        if missing:
            raise ReleaseEvidenceError(
                "provenance verification is missing: " + ", ".join(missing)
            )
        if statement.get("predicateType") != SLSA_V1:
            raise ReleaseEvidenceError("provenance predicate type is not SLSA v1")
        required = provenance_predicate(
            repository=repository,
            source_commit=source_commit,
            tag=tag,
            tag_object_sha=tag_object_sha,
            builder_id=builder_id,
            invocation_id=invocation_id,
        )
        if predicate != required:
            raise ReleaseEvidenceError(
                "provenance does not bind exact trusted-main release metadata"
            )
    elif kind == "sbom":
        if statement.get("predicateType") != CYCLONEDX_PREDICATE:
            raise ReleaseEvidenceError("SBOM predicate type is not CycloneDX")
        errors = validate_sbom(predicate)
        if errors:
            raise ReleaseEvidenceError(
                "invalid authenticated SBOM: " + "; ".join(errors)
            )
    else:
        raise ReleaseEvidenceError(f"unsupported attestation kind: {kind}")


def _fail(message: str) -> int:
    print(f"FAIL: {message}")
    return 1


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    archive = subparsers.add_parser("build-source-archive")
    archive.add_argument("--repo-root", type=Path, default=Path("."))
    archive.add_argument("--ref", required=True)
    archive.add_argument("--prefix", required=True)
    archive.add_argument("--output", type=Path, required=True)

    source = subparsers.add_parser("source-sbom")
    source.add_argument("--artifact", type=Path, required=True)
    source.add_argument("--name", required=True)
    source.add_argument("--version", required=True)
    source.add_argument("--repository", required=True)
    source.add_argument("--timestamp", required=True)
    source.add_argument("--output", type=Path, required=True)

    runtime = subparsers.add_parser("runtime-sbom")
    runtime.add_argument("--artifact", type=Path, required=True)
    runtime.add_argument("--project-name", required=True)
    runtime.add_argument("--version", required=True)
    runtime.add_argument("--timestamp", required=True)
    runtime.add_argument("--output", type=Path, required=True)

    validate = subparsers.add_parser("validate-sbom")
    validate.add_argument("sbom", type=Path)

    compare = subparsers.add_parser("compare-builds")
    compare.add_argument("--first", type=Path, required=True)
    compare.add_argument("--second", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)

    dist = subparsers.add_parser("verify-dist")
    dist.add_argument("--directory", type=Path, required=True)
    dist.add_argument("--project-name", required=True)
    dist.add_argument("--version", required=True)

    version_parser = subparsers.add_parser("runtime-version")
    version_parser.add_argument("--import-name", required=True)

    provenance = subparsers.add_parser("provenance-predicate")
    provenance.add_argument("--repository", required=True)
    provenance.add_argument("--source-commit", required=True)
    provenance.add_argument("--tag", required=True)
    provenance.add_argument("--tag-object-sha", required=True)
    provenance.add_argument("--builder-id", required=True)
    provenance.add_argument("--invocation-id", required=True)
    provenance.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify-bundle")
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--artifact", type=Path, required=True)
    verify.add_argument("--kind", choices=("provenance", "sbom"), required=True)
    verify.add_argument("--expected-predicate", type=Path, required=True)
    verify.add_argument("--repository")
    verify.add_argument("--source-commit")
    verify.add_argument("--tag")
    verify.add_argument("--tag-object-sha")
    verify.add_argument("--builder-id")
    verify.add_argument("--invocation-id")

    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "build-source-archive":
            build_source_archive(args.repo_root, args.ref, args.prefix, args.output)
        elif args.command == "source-sbom":
            write_json(
                args.output,
                source_sbom(
                    artifact=args.artifact,
                    name=args.name,
                    version=args.version,
                    repository=args.repository,
                    timestamp=args.timestamp,
                ),
            )
        elif args.command == "runtime-sbom":
            write_json(
                args.output,
                runtime_sbom(
                    artifact=args.artifact,
                    project_name=args.project_name,
                    version=args.version,
                    timestamp=args.timestamp,
                ),
            )
        elif args.command == "validate-sbom":
            errors = validate_sbom(load_json(args.sbom))
            if errors:
                raise ReleaseEvidenceError("; ".join(errors))
        elif args.command == "compare-builds":
            compare_builds(args.first, args.second, args.output)
        elif args.command == "verify-dist":
            verify_dist(args.directory, args.project_name, args.version)
        elif args.command == "runtime-version":
            print(runtime_version(args.import_name))
            return 0
        elif args.command == "provenance-predicate":
            write_json(
                args.output,
                provenance_predicate(
                    repository=args.repository,
                    source_commit=args.source_commit,
                    tag=args.tag,
                    tag_object_sha=args.tag_object_sha,
                    builder_id=args.builder_id,
                    invocation_id=args.invocation_id,
                ),
            )
        elif args.command == "verify-bundle":
            verify_bundle_statement(
                bundle=args.bundle,
                artifact=args.artifact,
                kind=args.kind,
                expected_predicate=args.expected_predicate,
                repository=args.repository,
                source_commit=args.source_commit,
                tag=args.tag,
                tag_object_sha=args.tag_object_sha,
                builder_id=args.builder_id,
                invocation_id=args.invocation_id,
            )
    except (
        OSError,
        ReleaseEvidenceError,
        subprocess.SubprocessError,
        tarfile.TarError,
        zipfile.BadZipFile,
    ) as exc:
        return _fail(str(exc))
    print(f"PASS: {args.command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
