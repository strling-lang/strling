"""Authenticate independently retrieved distribution bytes without publication."""

from __future__ import annotations

import hashlib
import platform
import subprocess
from pathlib import Path

from tooling.public_authentication import subject_checksums
from tooling.public_distribution import (
    authenticate_archive,
    authenticate_assembled_archive,
    authenticate_source_archive,
    obligations,
    strict_json,
)
from tooling.public_metadata import verify_registry_metadata, verify_readme_commands
from tooling.public_registries import retrieve
from tooling.public_retrieval import RetrievalError
from tooling.release_supply_chain import (
    ReleaseSupplyChainError,
    canonical_json,
    load_json,
)


def write_retrieved(root: Path, name: str, payload: bytes) -> str:
    relative = Path(name)
    target = root / relative
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or "\\" in name
        or ".git" in relative.parts
        or not target.resolve().is_relative_to(root.resolve())
    ):
        raise RetrievalError("security", "unsafe retrieved subject path")
    digest = hashlib.sha256(payload).hexdigest()
    if target.exists():
        if (
            target.is_symlink()
            or hashlib.sha256(target.read_bytes()).hexdigest() != digest
        ):
            raise RetrievalError(
                "artifact-integrity", "conflicting retrieved subject bytes"
            )
        return digest
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(payload)
    return digest


def verify_associations(
    transport, documents: dict, *, evidence: Path, artifact: dict, source: Path
) -> dict:
    result = {}
    for kind, directory, suffix in (
        ("sbom", "sbom", ".spdx.json"),
        ("provenance", "provenance", ".intoto.json"),
    ):
        expected = load_json(
            evidence.parent / directory / (artifact["surface"] + suffix)
        )
        row = documents[kind]
        public_bytes = transport.get(row["url"])
        if hashlib.sha256(public_bytes).hexdigest() != row["sha256"]:
            raise RetrievalError(
                "provenance-signature",
                "public evidence response differs from its approved association",
            )
        if canonical_json(strict_json(public_bytes)) != canonical_json(expected):
            raise RetrievalError(
                "provenance-signature",
                "public evidence does not authenticate the certified subject",
            )
        result[kind] = {"url": row["url"], "sha256": row["sha256"]}
    document = documents["documentation"]
    readme = (
        "bindings/rust/README.md"
        if artifact["id"] == "release:rust"
        else artifact["package_root"] + "/README.md"
    )
    expected_bytes = (source / readme).read_bytes()
    public_bytes = transport.get(document["url"])
    # Git stores normalized source bytes; registry prose must preserve meaning
    # and exact source content after the registered text newline convention.
    if hashlib.sha256(public_bytes).hexdigest() != document[
        "sha256"
    ] or public_bytes.replace(b"\r\n", b"\n") != expected_bytes.replace(b"\r\n", b"\n"):
        raise RetrievalError(
            "documentation",
            "public installation documentation differs from the certified source",
        )
    result["documentation"] = {
        "url": document["url"],
        "sha256": document["sha256"],
        "source_path": readme,
        "installation_commands": verify_readme_commands(
            public_bytes,
            artifact,
            load_json(source / "governance/release-policy.json")["product"]["version"],
        ),
    }
    return result


def verify_artifact(
    *,
    transport,
    artifact: dict,
    manifest: dict,
    destination: dict,
    documents: dict,
    version: str,
    source_sha: str,
    source_tree: str,
    source: Path,
    evidence: Path,
    materialized: Path,
    certified_subject_root: Path | None = None,
) -> dict:
    """Verify one complete retrieval; consumer obligations stay pending."""
    required = [
        row for row in obligations(manifest) if row["artifact_id"] == artifact["id"]
    ]
    authority = transport.authority
    selected = []
    files = {}
    checksums = {}
    try:
        checksums = subject_checksums(evidence, artifact)
        sbom = load_json(
            evidence.parent / "sbom" / (artifact["surface"] + ".spdx.json")
        )
        conan_inventories = None
        if artifact["registry"] == "conan":
            from tooling.conan_release import upload_inventory

            conan_inventories = []
            if certified_subject_root is None:
                raise RetrievalError(
                    "provenance-signature",
                    "certified Conan transport inventories are required",
                )
            for name, digest in checksums.items():
                if name.endswith(".upload.zip"):
                    path = certified_subject_root / name
                    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                        raise RetrievalError(
                            "provenance-signature",
                            "Conan expectation differs from the signed upload subject",
                        )
                    inventory, _ = upload_inventory(path, version)
                    conan_inventories.append(inventory)
        fetched = retrieve(
            transport,
            artifact,
            version,
            checksums,
            destination,
            source_sha=source_sha,
            conan_inventories=conan_inventories,
        )
        if "source_archive" in fetched:
            source_files = authenticate_source_archive(
                fetched["source_archive"],
                source_sha=source_sha,
                expected_tree=source_tree,
                observed_tree=fetched["source_tree"],
                sbom=sbom,
                artifact=artifact,
            )
            for name, payload in source_files.items():
                files[name] = write_retrieved(materialized, name, payload)
        elif "conan_files" in fetched:
            # These exact revision-bound transport bytes have already been
            # compared with the authenticated upload inventory by the adapter.
            for url, payload in fetched["conan_files"].items():
                name = "conan-public/" + hashlib.sha256(url.encode()).hexdigest()
                files[name] = write_retrieved(materialized, name, payload)
            from tooling.public_conan import reconstruct_cache

            for inventory in conan_inventories:
                name = "bindings/cpp/dist/" + inventory["cache_name"]
                result = reconstruct_cache(
                    exemplar=certified_subject_root / name,
                    expected_sha256=checksums[name],
                    inventory=inventory,
                    public_files=fetched["conan_files"],
                    endpoint=destination["registry_endpoint"],
                    version=version,
                    output=materialized / name,
                )
                files[name] = result["sha256"]
        else:
            for subject, payload in fetched["files"].items():
                if artifact["artifact_policy"]["subject_kind"] == "registry-assembled":
                    unpacked = authenticate_assembled_archive(
                        payload, subject=subject, sbom=sbom
                    )
                    for name, data in unpacked.items():
                        files[subject + "/" + name] = write_retrieved(
                            materialized, subject + "/" + name, data
                        )
                    continue
                if artifact["registry"] == "nuget.org" and authority == "public":
                    from tooling.nuget_signature import verify_nuget_registry_payload

                    verify_nuget_registry_payload(payload, sbom, fetch=transport.get)
                elif subject.endswith((".xml", ".rockspec")):
                    if hashlib.sha256(payload).hexdigest() != checksums[subject]:
                        raise RetrievalError(
                            "artifact-integrity",
                            "public package metadata differs from certified bytes",
                        )
                else:
                    exemplar = None
                    if (
                        certified_subject_root is not None
                        and (certified_subject_root / subject).is_file()
                    ):
                        exemplar = (certified_subject_root / subject).read_bytes()
                    authenticate_archive(
                        payload,
                        subject=subject,
                        expected_sha256=checksums[subject],
                        artifact=artifact,
                        sbom=sbom,
                        certified_payload=exemplar,
                    )
                files[subject] = write_retrieved(materialized, subject, payload)
        metadata = verify_registry_metadata(artifact, fetched["metadata"], source)
        associations = verify_associations(
            transport, documents, evidence=evidence, artifact=artifact, source=source
        )
        retrieval_digest = hashlib.sha256(
            canonical_json(transport.observations)
        ).hexdigest()
        for requirement in required:
            selected.append(
                {
                    **requirement,
                    "authority": authority,
                    "status": ("VERIFIED" if authority == "public" else "READY")
                    if requirement["platform"] is None
                    else "VERIFYING",
                    "retrieval_sha256": retrieval_digest,
                }
            )
        return {
            "artifact_id": artifact["id"],
            "authority": authority,
            "observations": selected,
            "retrieval_files": files,
            "metadata": metadata,
            "associations": associations,
            "publication_authorized": False,
        }
    except (
        RetrievalError,
        ReleaseSupplyChainError,
        ValueError,
        KeyError,
        TypeError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        category = (
            error.category
            if isinstance(error, RetrievalError)
            else "artifact-integrity"
        )
        status = error.status if isinstance(error, RetrievalError) else "FAILED"
        finding = {
            "category": category,
            "detail": str(error),
            "artifact_id": artifact["id"],
            "expected_source": source_sha,
            "expected": {
                "version": version,
                "registry": artifact["registry"],
                "package_name": artifact["package_name"],
                "subject_sha256": checksums,
                "specific": getattr(error, "expected", None),
            },
            "observed": {
                "responses": transport.observations,
                "authenticated_files": files,
                "specific": getattr(error, "observed", None),
            },
            "environment": {
                "os": platform.system(),
                "architecture": platform.machine(),
                "python": platform.python_version(),
            },
            "supporting_evidence": str(
                getattr(transport, "output", "synthetic-protocol-fixtures")
            ),
        }
        for requirement in required:
            selected.append(
                {
                    **requirement,
                    "authority": authority,
                    "status": status,
                    "finding": finding,
                }
            )
        return {
            "artifact_id": artifact["id"],
            "authority": authority,
            "observations": selected,
            "retrieval_files": files,
            "finding": finding,
            "publication_authorized": False,
        }
