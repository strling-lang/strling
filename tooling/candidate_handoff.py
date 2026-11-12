"""Derive a publication handoff from already authenticated candidate evidence."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from tooling.release_candidate_evidence import source_data
from tooling.release_supply_chain import document_fingerprint, load_json


HANDOFF_PATH = "docs/migration/final-release-candidate-handoff.json"
TERMINAL_STATE = "RELEASE CANDIDATE CERTIFIED — PUBLICATION AUTHORIZATION PENDING"


def derive(repository: Path, trust: Path, bundle: Path, *, provisional_rc: str) -> dict:
    if re.fullmatch(r"4\.0\.0-rc\.[1-9][0-9]*", provisional_rc) is None:
        raise ValueError("unregistered provisional candidate coordinate")
    attestation = load_json(bundle / "attestation.json")
    payload = attestation["signed_payload"]
    source = payload["certified_source"]["commit"]
    entries = payload["evidence_files"]
    preflights = [
        bundle / row["path"]
        for row in entries
        if row["role"] == "coordinate-preflight"
        and row["path"].endswith("/report.json")
    ]
    if len(preflights) != 1:
        raise ValueError("handoff requires one retained read-only coordinate preflight")
    preflight = load_json(preflights[0])
    if (
        preflight.get("provisional_rc") != provisional_rc
        or preflight.get("rc_reserved") is not False
        or preflight.get("publication_authorized") is not False
        or preflight.get("registry_mutation_authorized") is not False
    ):
        raise ValueError(
            "handoff coordinate or authorization contradicts planning evidence"
        )
    packages = [
        bundle / row["path"]
        for row in entries
        if row["role"] == "release-supply-chain"
        and row["path"].endswith("/release-supply-chain-evidence.json")
    ]
    if len(packages) != 1:
        raise ValueError("handoff has no unique authenticated distribution evidence")
    release = load_json(packages[0])
    verifier = subprocess.check_output(
        ["git", "-C", str(trust), "rev-parse", "HEAD"], text=True
    ).strip()
    with source_data(repository, source) as root:
        policy = load_json(root / "governance/release-policy.json")
        manifest = load_json(
            root / "tests/certification/release-supply-chain/1.0/manifest.json"
        )
        examples = load_json(root / "tests/documentation/1.0/manifest.json")
        public = load_json(root / "governance/public-distribution.json")
        observed = {row["id"]: row for row in release["artifacts"]}
        distributions = []
        for artifact in manifest["artifacts"]:
            result = observed[artifact["id"]]
            contract = artifact["distribution_contract"]
            distributions.append(
                dict(
                    artifact_id=artifact["id"],
                    package_name=artifact["package_name"],
                    registry=artifact["registry"],
                    package_root=artifact["package_root"],
                    tier=contract["tier"],
                    platforms=contract["platforms"],
                    scope=contract["scope"],
                    native_runtime_prerequisites=contract.get(
                        "native_runtime_prerequisites", []
                    ),
                    registry_owner=contract["registry_owner"],
                    ownership_status=contract["ownership_status"],
                    publication_eligibility=contract["publication_eligibility"],
                    external_prerequisites=contract["external_prerequisites"],
                    subject=result["subject"],
                    checksum=result["checksum"],
                    sbom=result["sbom"],
                    provenance=result["provenance"],
                    toolchains=[
                        row
                        for row in release["toolchains"]
                        if row["artifact_id"] == artifact["id"]
                    ],
                    upload_contract=artifact["upload_contract"],
                    credential_policy=artifact["credential_policy"],
                )
            )
        document_paths = [
            "tests/documentation/1.0/manifest.json",
            "docs/getting-started.md",
            "docs/migration-guide.md",
            "docs/architecture.md",
            "docs/support-matrix.md",
            "docs/benchmark-report.md",
        ]
        result = dict(
            schema_version="1.0.0",
            document_kind="strling-certified-candidate-publication-handoff",
            state=TERMINAL_STATE,
            lifecycle="certified",
            source_sha=source,
            product_version=policy["product"]["version"],
            product_authority=policy["product"]["version_authority"],
            certified_artifact_coordinate=policy["product"]["version"],
            release_channel_proposal="release-candidate",
            provisional_public_rc=dict(
                coordinate=provisional_rc,
                provisional=True,
                reserved=False,
                rc_artifacts_certified=False,
                coordinate_specific_certification_required=True,
            ),
            publication_authorized=False,
            registry_mutation_authorized=False,
            public_release_verified=False,
            certification=dict(
                evidence_root_sha256=payload["evidence_root_sha256"],
                attestation_sha256=hashlib.sha256(
                    (bundle / "attestation.json").read_bytes()
                ).hexdigest(),
                signature_sha256=attestation["signature"]["signature_sha256"],
                certifier=payload["certifier"],
                trusted_verifier_sha=verifier,
                profile_results=payload["profile_results"],
                waiver_inventory=payload["waiver_inventory"],
                certification_contract=payload["certification_contract"],
            ),
            manifest_fingerprint=document_fingerprint(manifest),
            distributions=distributions,
            coordinate_preflight=dict(
                report_sha256=hashlib.sha256(preflights[0].read_bytes()).hexdigest(),
                observations=preflight["observations"],
                limitations=preflight["limitations"],
            ),
            documentation=dict(
                documents=len(examples["documents"]),
                examples=len(examples["examples"]),
                subjects={
                    path: hashlib.sha256((root / path).read_bytes()).hexdigest()
                    for path in document_paths
                },
            ),
            public_verification_inputs=dict(
                contract=public["contract"],
                qualified_protocol_verifier_sha=verifier,
                qualified_consumer_harness_sha=verifier,
                source_sha=source,
                product_version=policy["product"]["version"],
                packaging_verifier_sha=public["certification_verifier"],
                publication_request_requires_exact_owner_destinations=True,
                public_registry_results_available=False,
            ),
            stable_promotion=policy["release_lifecycle"]["release_candidate"],
            future_publication_prerequisites=[
                "Exact owner authorization naming channel, version, source, artifact subjects, destinations and run.",
                "Approved existing registry owners, Conan endpoint, protected environment reviewers and trusted publishers or credentials.",
                "Reconcile all registry/tag histories and immutable coordinate availability immediately before publication.",
                "Use the certified bytes without rebuilding; any coordinate projection requires its exact governed certification.",
                "A published terminal RC and its stable promotion must use the same source and fresh required stable certification.",
                "After publication execute the qualified independent public verifier against actual authorized coordinates; preserve partial-publication failures.",
            ],
        )
    result["handoff_fingerprint"] = document_fingerprint(result)
    return result


def verify(repository: Path, trust: Path, bundle: Path, handoff: Path) -> dict:
    observed = load_json(handoff)
    coordinate = observed.get("provisional_public_rc", {}).get("coordinate", "")
    expected = derive(repository, trust, bundle, provisional_rc=coordinate)
    if observed != expected:
        raise ValueError(
            "publication handoff contradicts authenticated source or evidence"
        )
    return dict(
        status="passed",
        source=expected["source_sha"],
        distributions=len(expected["distributions"]),
        publication_authorized=False,
        public_release_verified=False,
    )
