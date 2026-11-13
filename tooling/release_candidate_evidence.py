"""Independently reconcile candidate package, example and staged public evidence.

Candidate repository content is data. Only verifier-owned modules are imported;
the temporary source checkout is never placed on Python's import path.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from tooling.documentation_programs import expected_proof
from tooling.public_distribution import obligations
from tooling.release_consumers import CONSUMER_FIXTURES
from tooling.release_supply_chain import document_fingerprint, load_json, verify_bundle
from tooling.evidence_bytes import decode
from tooling.public_registries import coordinate_version


def validate_coordinate_preflight(manifest: dict, report: dict) -> None:
    rows = report.get("observations", [])
    indexed = {row.get("artifact_id"): row for row in rows}
    expected = {row["id"]: row for row in manifest["artifacts"]}
    coordinate = report.get("provisional_rc", "")
    if (
        report.get("status") != "read-only-preflight-completed"
        or report.get("authoritative") is not False
        or report.get("publication_authorized") is not False
        or report.get("registry_mutation_authorized") is not False
        or report.get("rc_reserved") is not False
        or re.fullmatch(r"4\.0\.0-rc\.[1-9][0-9]*", coordinate) is None
        or len(indexed) != len(rows)
        or set(indexed) != set(expected)
    ):
        raise ValueError(
            "candidate coordinate preflight is incomplete or misclassified"
        )
    for identity, artifact in expected.items():
        row = indexed[identity]
        if (
            row.get("package_name") != artifact["package_name"]
            or row.get("registry") != artifact["registry"]
            or row.get("ownership_confirmed") is not False
        ):
            raise ValueError("preflight package namespace or ownership claim changed")
        if row.get("status") == "owner-specific-coordinate-unverified":
            if artifact["registry"] not in {"conan", "cpan", "luarocks.org"}:
                raise ValueError("preflight omitted a resolved registry route")
            continue
        coordinates = row.get("coordinates", [])
        versions = [value.get("version") for value in coordinates]
        if (
            row.get("status") != "read-only-coordinate-observation"
            or len(versions) != 2
            or set(versions) != {coordinate, "4.0.0"}
            or any(
                value.get("coordinate")
                != coordinate_version(value["version"], artifact["registry"])
                for value in coordinates
            )
        ):
            raise ValueError("preflight omitted or substituted a planned coordinate")


def reconstruct_packaging_inputs(
    bundle: Path, entries: list[dict], source_sha: str, output: Path
) -> tuple[Path, dict]:
    """Rebuild the nested certificate's exact bytes; this alone is not acceptance."""
    attested = [row for row in entries if row["role"] == "staged-package-attestation"]
    if len(attested) != 1:
        raise ValueError("candidate requires one original staged package attestation")
    data = (bundle / attested[0]["path"]).read_bytes()
    attestation = load_json(bundle / attested[0]["path"])
    payload = attestation["signed_payload"]
    if payload["certified_source"]["commit"] != source_sha:
        raise ValueError("nested package certificate has a different source")
    indexed = {}
    for row in entries:
        raw = (bundle / row["path"]).read_bytes()
        if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError("nested package source bytes changed")
        indexed[(len(raw), row["sha256"])] = raw
        if row["role"] == "sealed-original-metadata":
            original = decode(load_json(bundle / row["path"]), source_sha)
            indexed[(len(original), hashlib.sha256(original).hexdigest())] = original
    output.mkdir(exist_ok=False)
    (output / "attestation.json").write_bytes(data)
    seen = set()
    for row in payload["evidence_files"]:
        relative = PurePosixPath(row["path"])
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not relative.parts
            or relative.parts[0] != "evidence"
            or "\\" in row["path"]
            or ":" in row["path"]
            or row["path"] in seen
        ):
            raise ValueError("nested package evidence path is unsafe or duplicated")
        seen.add(row["path"])
        identity = (row["bytes"], row["sha256"])
        if identity not in indexed:
            raise ValueError("nested package evidence is missing from candidate root")
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(indexed[identity])
    return output, payload


PREVIEW_COMMANDS = {
    "lua": ["luarocks", "lua"],
    "perl": ["perl", "make", "make", "perl"],
    "php": ["composer", "php"],
    "r": ["R", "Rscript"],
    "ruby": ["gem", "ruby"],
    "typescript": ["npm", *(["node", "node"] * 4)],
}


def preview_expected(manifest: dict, slug: str) -> list[dict]:
    rows = expected_proof(manifest, slug)
    if slug == "typescript":
        selected = next(
            row
            for row in manifest["examples"]
            if row["id"] == "docs/migration-guide.md#5"
        )
        rows.append(dict(id=selected["id"], sha256=selected["sha256"], status="passed"))
    return sorted(rows, key=lambda row: row["id"])


def validate_preview_reports(
    *,
    reports: list[dict],
    manifest: dict,
    examples: dict,
    release: dict,
    fixture_hashes: dict,
    product_version: str,
    documentation_sha256: str,
) -> None:
    expected = {
        row["id"]
        for row in manifest["artifacts"]
        if row["distribution_contract"]["tier"] == "Preview"
    }
    identities = [row.get("artifact_id") for row in reports]
    if len(identities) != len(set(identities)) or set(identities) != expected:
        raise ValueError("missing, duplicate or unknown Preview documentation producer")
    invocations = [row.get("invocation_id") for row in reports]
    if len(set(invocations)) != len(invocations) or any(
        not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{32}", value) is None
        for value in invocations
    ):
        raise ValueError("Preview producer invocation is missing or reused")
    subjects = {row["id"]: row["subject"]["sha256"] for row in release["artifacts"]}
    platforms = {row["id"]: row["build_platforms"] for row in manifest["artifacts"]}
    native = {
        row["receipt"]["consumer"]["result"].get("native_sha256")
        for row in release["build_receipts"]
        if row["receipt"].get("consumer") is not None
        and row["receipt"]["scope"] == "linux-x86_64"
    }
    native.discard(None)
    for report in reports:
        identity = report["artifact_id"]
        commands = report.get("command_evidence", [])
        if [
            Path(row.get("command", [""])[0]).name for row in commands
        ] != PREVIEW_COMMANDS[identity.split(":")[1]] or any(
            row.get("exit_code") != 0
            or not re.fullmatch(r"[0-9a-f]{64}", row.get("metadata_sha256", ""))
            or not row.get("metadata")
            for row in commands
        ):
            raise ValueError(
                "Preview producer commands are missing or did not complete"
            )
        if (
            report.get("status") != "passed"
            or report.get("authority") != "bounded-preview-documentation"
            or report.get("supported_claim") is not False
            or report.get("public_retrieval") is not False
            or report.get("engineering") is not False
            or report.get("source") != release["source"]
            or report.get("product_version") != product_version
            or report.get("runner_scope") not in platforms[identity]
            or report.get("subject_sha256") != subjects[identity]
            or report.get("fixture_sha256") != fixture_hashes
            or report.get("documentation_manifest_sha256") != documentation_sha256
            or report.get("evidence_fingerprint")
            != document_fingerprint(report, "evidence_fingerprint")
        ):
            raise ValueError(
                "Preview documentation source, subject or authority differs"
            )
        if report.get("documentation_examples") != preview_expected(
            examples, identity.split(":")[1]
        ):
            raise ValueError("missing or substituted Preview documentation example")
        if (
            identity != "release:typescript"
            and report.get("native_sha256") not in native
        ):
            raise ValueError("Preview example used an unauthenticated native companion")


def validate_public_coverage(manifest: dict, proof: dict, *, source_sha: str) -> None:
    required = {row["id"]: row for row in obligations(manifest)}
    rows = proof.get("coverage", [])
    identities = [row.get("id") for row in rows]
    scopes = {
        (row["id"], platform)
        for row in manifest["artifacts"]
        if row["distribution_contract"]["tier"] == "Supported"
        for platform in row["distribution_contract"]["platforms"]
    }
    if (
        proof.get("source") != source_sha
        or proof.get("status") != "passed-current-source-staged-qualification"
        or proof.get("public_release_verified") is not False
        or proof.get("publication_authorized") is not False
        or proof.get("artifact_routes") != len(manifest["artifacts"])
        or proof.get("supported_consumer_scopes") != len(scopes)
        or proof.get("public_obligations") != len(required)
        or len(identities) != len(set(identities))
        or set(identities) != set(required)
    ):
        raise ValueError("incomplete or incorrectly classified public fixture coverage")
    for row in rows:
        expected = required[row["id"]]
        authority = "synthetic" if expected["platform"] is None else "staged"
        if (
            any(row.get(key) != value for key, value in expected.items())
            or row.get("status") != "READY"
            or row.get("authority") != authority
            or not row.get("evidence")
        ):
            raise ValueError("public fixture obligation changed scope or authority")


def validate_public_producers(
    manifest: dict,
    proof: dict,
    examples: dict,
    fixture_hashes: dict,
    product_version: str,
    documentation_sha256: str,
    load_observation,
) -> None:
    """Reconstruct each obligation from its producer, not a coverage assertion."""
    required = obligations(manifest)
    artifact_records = {}
    consumer_records = {}
    for row in proof["coverage"]:
        observed = load_observation(row["evidence"])
        identity = row["artifact_id"]
        if row["platform"] is None:
            if (
                observed.get("artifact_id") != identity
                or "finding" in observed
                or observed.get("authority") != "synthetic"
                or observed.get("publication_authorized") is not False
            ):
                raise ValueError(
                    "public artifact producer identity or authority differs"
                )
            expected = [entry for entry in required if entry["artifact_id"] == identity]
            observations = observed.get("observations", [])
            indexed = {entry.get("id"): entry for entry in observations}
            if len(indexed) != len(observations) or set(indexed) != {
                entry["id"] for entry in expected
            }:
                raise ValueError("public artifact producer omitted an obligation")
            for entry in expected:
                result = indexed[entry["id"]]
                if (
                    any(result.get(key) != value for key, value in entry.items())
                    or result.get("authority") != "synthetic"
                    or result.get("status")
                    != ("READY" if entry["platform"] is None else "VERIFYING")
                ):
                    raise ValueError("public artifact producer changed an obligation")
            artifact_records[identity] = row["evidence"]
        else:
            receipt = observed.get("receipt", {})
            result = receipt.get("result", {})
            if (
                observed.get("status") != "passed"
                or observed.get("artifact_id") != identity
                or receipt.get("artifact_id") != identity
                or receipt.get("scope") != row["platform"]
                or receipt.get("authority") != "staged"
                or receipt.get("status") != "READY"
                or receipt.get("product_version") != product_version
                or receipt.get("publication_authorized") is not False
                or receipt.get("fixture_sha256") != fixture_hashes
                or result.get("documentation_manifest_sha256") != documentation_sha256
                or receipt.get("receipt_fingerprint")
                != document_fingerprint(receipt, "receipt_fingerprint")
                or row.get("receipt_fingerprint") != receipt.get("receipt_fingerprint")
                or not receipt.get("toolchains")
                or any(tool.get("status") != "passed" for tool in receipt["toolchains"])
                or result.get("status") != "passed"
                or result.get("source_outcome") != "succeeded"
                or result.get("target_pattern") != "abc"
            ):
                raise ValueError(
                    "staged consumer producer did not authenticate a passing result"
                )
            if identity == "release:rust":
                if (
                    result.get("linked_package_version") != product_version
                    or result.get("target_profile_mismatch_rejected") is not True
                ):
                    raise ValueError(
                        "staged Rust consumer omitted compatibility rejection"
                    )
            elif result.get("kernel_mismatch_rejected") is not True:
                raise ValueError("staged consumer omitted substituted-kernel rejection")
            if result.get("documentation_examples") != expected_proof(
                examples, identity.split(":")[1]
            ):
                raise ValueError("staged consumer omitted a documented program")
            consumer_records[(identity, row["platform"])] = row["evidence"]
    expected_scopes = {
        (entry["artifact_id"], entry["platform"])
        for entry in required
        if entry["platform"] is not None
    }
    if (
        set(artifact_records) != {entry["id"] for entry in manifest["artifacts"]}
        or set(consumer_records) != expected_scopes
    ):
        raise ValueError("public producer route or consumer scope is incomplete")


@contextmanager
def source_data(repository: Path, source_sha: str):
    """Create an exact clean data checkout with no inherited hooks or filters."""
    if re.fullmatch(r"[0-9a-f]{40}", source_sha) is None:
        raise ValueError("source data requires one exact commit")
    environment = dict(
        os.environ,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT="0",
    )
    with tempfile.TemporaryDirectory(
        prefix="strling-candidate-source-data-"
    ) as directory:
        base = Path(directory)
        hooks = base / "empty-hooks"
        hooks.mkdir()
        root = base / "source"

        def git(*arguments):
            return subprocess.check_output(
                [
                    "git",
                    "-c",
                    "core.hooksPath=" + str(hooks),
                    "-c",
                    "safe.directory=" + str(repository.resolve()),
                    "-c",
                    "core.autocrlf=false",
                    "-c",
                    "core.longpaths=true",
                    *arguments,
                ],
                env=environment,
                stderr=subprocess.PIPE,
            )

        git(
            "clone",
            "--shared",
            "--no-hardlinks",
            "--no-checkout",
            "--template=" + str(hooks),
            str(repository),
            str(root),
        )
        git("-C", str(root), "config", "core.hooksPath", str(hooks))
        git("-C", str(root), "config", "core.autocrlf", "false")
        git("-C", str(root), "config", "core.longpaths", "true")
        git("-C", str(root), "checkout", "--detach", source_sha)
        if git("-C", str(root), "status", "--porcelain", "--untracked-files=all"):
            raise ValueError("source data checkout is not exact and clean")
        yield root


def _require_nested_verification(
    verified: dict, source_sha: str, evidence_root_sha256: str
) -> None:
    """Require verified source and root facts from the attestation API."""
    if (
        not isinstance(verified, dict)
        or verified.get("certification_state") != "CLOUD_VERIFIED"
        or verified.get("certified_source_sha") != source_sha
        or verified.get("evidence_root_sha256") != evidence_root_sha256
    ):
        raise ValueError("nested package certificate was not accepted")


def verify_candidate_evidence(
    repository: Path, source_sha: str, bundle: Path, entries: list[dict]
) -> dict:
    def selected(role: str, suffix: str) -> list[Path]:
        return [
            bundle / row["path"]
            for row in entries
            if row["role"] == role and row["path"].endswith(suffix)
        ]

    packages = selected("release-supply-chain", "/release-supply-chain-evidence.json")
    public = selected("public-staged-qualification", "/proof.json")
    previews = selected("candidate-documentation", "/result.json")
    preflights = selected("coordinate-preflight", "/report.json")
    if len(packages) != 1 or len(public) != 1 or len(preflights) != 1:
        raise ValueError(
            "candidate requires unique package and public qualification evidence"
        )
    with source_data(repository, source_sha) as root:
        # Verify the original authority's complete nested certificate, from
        # reconstructed bytes, using only this immutable verifier's code.
        from tooling.local_certification_attestation import verify_attestation

        with tempfile.TemporaryDirectory(
            prefix="strling-nested-package-data-"
        ) as directory:
            nested, nested_payload = reconstruct_packaging_inputs(
                bundle, entries, source_sha, Path(directory) / "certificate"
            )
            verified = verify_attestation(
                repository_root=root,
                trust_root=Path(__file__).resolve().parents[1],
                bundle_dir=nested,
                policy_name="release-certification-trust.json",
            )
            _require_nested_verification(
                verified, source_sha, nested_payload["evidence_root_sha256"]
            )
        manifest = load_json(
            root / "tests/certification/release-supply-chain/1.0/manifest.json"
        )
        release = verify_bundle(
            root=root,
            evidence_path=packages[0],
            manifest=manifest,
            verify_subjects=False,
        )
        if release["status"] != "passed" or release["source"]["commit"] != source_sha:
            raise ValueError("candidate package evidence did not pass for this source")
        examples = load_json(root / "tests/documentation/1.0/manifest.json")
        preflight = load_json(preflights[0])
        validate_coordinate_preflight(manifest, preflight)
        fixtures = {
            relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
            for relative in CONSUMER_FIXTURES.values()
        }
        reports = [load_json(path) for path in previews]
        validate_preview_reports(
            reports=reports,
            manifest=manifest,
            examples=examples,
            release=release,
            fixture_hashes=fixtures,
            documentation_sha256=hashlib.sha256(
                (root / "tests/documentation/1.0/manifest.json").read_bytes()
            ).hexdigest(),
            product_version=load_json(root / "governance/release-policy.json")[
                "product"
            ]["version"],
        )
        for path, report in zip(previews, reports):
            for command in report["command_evidence"]:
                metadata = path.parent / command["metadata"]
                if (
                    not metadata.resolve().is_relative_to(path.parent.resolve())
                    or hashlib.sha256(metadata.read_bytes()).hexdigest()
                    != command["metadata_sha256"]
                ):
                    raise ValueError(
                        "Preview command has no authenticated terminal record"
                    )
                observed = load_json(metadata)
                if (
                    observed.get("exit_code") != 0
                    or observed.get("command") != command["command"]
                ):
                    raise ValueError("Preview command terminal result differs")
        proof = load_json(public[0])
        validate_public_coverage(manifest, proof, source_sha=source_sha)
        # Every obligation names retained, independently hashed producer data.
        listed = {row["path"]: row for row in proof["evidence_files"]}
        if len(listed) != len(proof["evidence_files"]):
            raise ValueError("duplicate public qualification file")
        for relative, entry in listed.items():
            path = public[0].parent / relative
            if (
                not path.resolve().is_relative_to(public[0].parent.resolve())
                or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]
                or path.stat().st_size != entry["bytes"]
            ):
                raise ValueError(
                    "public observation has no authenticated producer evidence"
                )
        if any(row["evidence"] not in listed for row in proof["coverage"]):
            raise ValueError("public obligation references unlisted producer data")
        qualification = load_json(public[0].parent / "artifacts/qualification.json")
        authentication = qualification.get("authentication", {})
        if (
            "artifacts/qualification.json" not in listed
            or qualification.get("source") != source_sha
            or qualification.get("status") != "artifact-qualification-passed"
            or qualification.get("authority") != "synthetic"
            or qualification.get("public_release_verified") is not False
            or qualification.get("failed") != 0
            or qualification.get("passed") != len(manifest["artifacts"])
            or authentication.get("certified_source_sha") != source_sha
            or authentication.get("signed_evidence_root")
            != nested_payload["evidence_root_sha256"]
            or authentication.get("verifier_source_sha")
            != load_json(root / "governance/public-distribution.json")[
                "certification_verifier"
            ]
            or not any(
                row["role"] == "release-supply-chain"
                and row["sha256"]
                == hashlib.sha256(packages[0].read_bytes()).hexdigest()
                for row in nested_payload["evidence_files"]
            )
        ):
            raise ValueError(
                "public qualification is not bound to the verified package certificate"
            )
        validate_public_producers(
            manifest,
            proof,
            examples,
            fixtures,
            load_json(root / "governance/release-policy.json")["product"]["version"],
            hashlib.sha256(
                (root / "tests/documentation/1.0/manifest.json").read_bytes()
            ).hexdigest(),
            lambda relative: load_json(public[0].parent / relative),
        )
    return dict(
        status="passed",
        source=source_sha,
        distributions=len(manifest["artifacts"]),
        public_obligations=len(obligations(manifest)),
        preview_documentation=len(previews),
        public_release_verified=False,
        publication_authorized=False,
    )
