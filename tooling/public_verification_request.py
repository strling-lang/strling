"""Read-only release verification requests authenticated by protected control."""

from __future__ import annotations

import hashlib
import re
import json
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

from tooling.public_distribution import CONTRACT, exact_rows, obligations
from tooling.public_retrieval import RetrievalError
from tooling.release_supply_chain import canonical_json, document_fingerprint


def validate_request(
    request: dict,
    *,
    expected_sha256: str,
    manifest: dict,
    authentication: dict,
    authority: str,
) -> dict:
    """Expected digest is protected configuration, never candidate or dispatch data."""
    schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "governance/schemas/public-verification-request.schema.json"
        ).read_text(encoding="utf-8")
    )
    errors = list(Draft202012Validator(schema).iter_errors(request))
    if errors:
        raise RetrievalError(
            "contract",
            "verification request violates its versioned schema: " + errors[0].message,
        )
    keys = {
        "contract",
        "version",
        "channel",
        "certified_source_sha",
        "closure_source_sha",
        "signed_evidence_root",
        "manifest_fingerprint",
        "destinations",
        "documents",
        "publication_receipts",
        "obligations",
        "lifecycle_state",
        "authority",
    }
    if set(request) != keys or request.get("contract") != CONTRACT:
        raise RetrievalError(
            "contract", "verification request has an unknown shape or contract"
        )
    if (
        not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
        or hashlib.sha256(canonical_json(request)).hexdigest() != expected_sha256
    ):
        raise RetrievalError(
            "authority", "verification request differs from protected approved digest"
        )
    if (
        authority not in {"public", "synthetic", "staged"}
        or request["authority"] != authority
    ):
        raise RetrievalError("authority", "verification request authority mismatch")
    if request["lifecycle_state"] != (
        "published" if authority == "public" else "certified"
    ):
        raise RetrievalError(
            "authority", "verification cannot skip release lifecycle boundaries"
        )
    for field in ("certified_source_sha", "closure_source_sha", "signed_evidence_root"):
        if request[field] != authentication[field]:
            raise RetrievalError(
                "provenance-signature",
                "verification request is bound to another signed release",
            )
    if request["manifest_fingerprint"] != document_fingerprint(manifest):
        raise RetrievalError("contract", "verification manifest identity changed")
    version = request["version"]
    if not isinstance(version, str) or version != authentication.get("product_version"):
        raise RetrievalError(
            "contract", "verification version differs from certified product authority"
        )
    if request["channel"] != ("release-candidate" if "-rc." in version else "stable"):
        raise RetrievalError(
            "contract", "verification channel differs from immutable coordinate"
        )
    artifacts = {row["id"]: row for row in manifest["artifacts"]}
    destinations = exact_rows(request["destinations"], "artifact_id", set(artifacts))
    documents = exact_rows(request["documents"], "artifact_id", set(artifacts))
    exact_rows(request["publication_receipts"], "artifact_id", set(artifacts))
    required = obligations(manifest)
    if request["obligations"] != required:
        raise RetrievalError(
            "contract", "verification denominator or scope was changed"
        )
    for identity, destination in destinations.items():
        artifact = artifacts[identity]
        distribution = artifact["distribution_contract"]
        if artifact["registry"] == "conan":
            endpoint = urlsplit(destination.get("registry_endpoint", ""))
            if (
                endpoint.scheme != "https"
                or not endpoint.hostname
                or endpoint.username is not None
                or endpoint.password is not None
                or endpoint.query
                or endpoint.fragment
                or endpoint.port not in (None, 443)
            ):
                raise RetrievalError(
                    "contract", "exact public Conan endpoint is required"
                )
        for key in ("registry", "package_name"):
            if destination.get(key) != artifact[key]:
                raise RetrievalError(
                    "source-identity", "wrong approved public distribution destination"
                )
        if destination.get("tier") != distribution["tier"]:
            raise RetrievalError("contract", "destination attempts support promotion")
        if authority == "public" and (
            distribution["ownership_status"] != "verified"
            or destination.get("registry_owner") != distribution["registry_owner"]
            or destination["registry_owner"].startswith("existing ")
        ):
            raise RetrievalError(
                "authority",
                "public registry ownership has not been governed and verified",
            )
        associations = documents[identity]
        if set(associations) != {"artifact_id", "sbom", "provenance", "documentation"}:
            raise RetrievalError(
                "contract", "public evidence associations are incomplete"
            )
        for kind in ("sbom", "provenance", "documentation"):
            item = associations[kind]
            if (
                not isinstance(item, dict)
                or set(item) != {"url", "sha256"}
                or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
            ):
                raise RetrievalError(
                    "contract", "invalid evidence document association"
                )
            location = urlsplit(item["url"])
            if (
                location.scheme != "https"
                or not location.hostname
                or location.username
                or location.password
                or location.fragment
            ):
                raise RetrievalError(
                    "security",
                    "public evidence requires an exact credential-free HTTPS location",
                )
    return {
        "status": "passed",
        "authority": authority,
        "request_sha256": expected_sha256,
        "required": len(required),
        "artifacts": len(artifacts),
        "publication_authorized": False,
    }
