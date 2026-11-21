"""Prepare and verify the separately admitted RC4 Preview artifact."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

from tooling.release_supply_chain import ReleaseSupplyChainError, _validate_spdx

ROOT = Path(__file__).resolve().parents[1]
OPERATION = "certification.lab-wasm-preview"
RECEIPTS = ("rebuild-1-receipt.json", "rebuild-2-receipt.json")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def admission(root: Path) -> dict:
    entry = read_json(root / "governance/lab-wasm-preview.json")
    pin = read_json(root / "bindings/lab-wasm/qualification.json")
    require(
        entry["schema_version"] == "1.0.0"
        and entry["scope"] == "browser-compiler-tools-preview"
        and entry["admission"] == "approved-for-certification"
        and entry["publication_authorized"] is False
        and entry["required_profiles"] == ["full", "release"]
        and entry["package"] == "strling-lab-wasm"
        and pin["adapter_version"] == entry["version"]
        and pin["wire_protocol"] == entry["wire_protocol"]
        and pin["compiler_base_revision"] == entry["compiler_base"]
        and pin["rustc"] == entry["rust_version"]
        and pin["build_target"] == entry["target"]
        and pin["replay_recipe"] == entry["build_recipe"]
        and pin["maximum_memory_bytes"] == entry["memory_bytes"]
        and pin["maximum_stack_bytes"] == entry["stack_bytes"]
        and pin["sha256"] == entry["artifact"]["sha256"]
        and pin["bytes"] == entry["artifact"]["bytes"]
        and entry["reserved_destination"]
        == {
            "repository": "strling-lang/strling",
            "tag": "lab-wasm-v" + entry["version"],
            "asset": "strling_lab_wasm.wasm",
            "immutable_required": True,
        },
        "Preview admission does not match the frozen qualification",
    )
    tree = subprocess.check_output(
        ["git", "rev-parse", entry["source_revision"] + "^{tree}"],
        cwd=root,
        text=True,
    ).strip()
    require(tree == entry["source_tree"], "Frozen Git tree does not match admission")
    return entry


def verify_inputs(evidence: Path, entry: dict) -> None:
    asset = evidence / entry["reserved_destination"]["asset"]
    require(
        asset.stat().st_size == entry["artifact"]["bytes"]
        and sha256(asset) == entry["artifact"]["sha256"],
        "Preview Wasm does not match the admitted bytes",
    )
    for filename in RECEIPTS:
        receipt_path = evidence / filename
        require(
            sha256(receipt_path) == entry["rebuild_receipt_sha256"],
            f"{filename} does not match the independently reproduced receipt",
        )
        receipt = read_json(receipt_path)
        for field in (
            "source_revision",
            "source_tree",
            "source_archive_sha256",
            "cargo_lock_sha256",
            "target",
        ):
            require(
                receipt[field] == entry[field],
                f"{filename} does not bind the admitted {field}",
            )
    sbom_path = evidence / "draft-sbom.spdx.json"
    require(
        sha256(sbom_path) == entry["draft_spdx_sha256"],
        "Draft SPDX inventory does not match the admitted artifact inventory",
    )
    _validate_spdx(read_json(sbom_path))


def provenance(entry: dict) -> dict:
    return {
        "_type": "https://in-toto.io/Statement/v1",
        "predicateType": "https://slsa.dev/provenance/v1",
        "subject": [
            {
                "name": entry["reserved_destination"]["asset"],
                "digest": {"sha256": entry["artifact"]["sha256"]},
            }
        ],
        "predicate": {
            "buildDefinition": {
                "buildType": "https://strling.dev/build-types/lab-wasm-replay/v1",
                "externalParameters": {
                    "recipe": entry["build_recipe"],
                    "target": entry["target"],
                },
                "internalParameters": {
                    "rebuildReceiptSha256": entry["rebuild_receipt_sha256"],
                    "rustVersion": entry["rust_version"],
                },
                "resolvedDependencies": [
                    {
                        "uri": "git+https://github.com/strling-lang/strling",
                        "digest": {"gitCommit": entry["source_revision"]},
                    },
                    {
                        "uri": "bindings/lab-wasm/Cargo.lock",
                        "digest": {"sha256": entry["cargo_lock_sha256"]},
                    },
                ],
            },
            "runDetails": {
                "builder": {"id": "https://strling.dev/builders/lab-wasm-replay/v1"}
            },
        },
    }


def seal_check(root: Path, evidence: Path, archive: Path, entry: dict) -> dict:
    with archive.open("rb") as handle:
        integrity = "sha512-" + base64.b64encode(
            hashlib.file_digest(handle, "sha512").digest()
        ).decode("ascii")
    require(
        integrity == entry["sealed_npm_archive_integrity"],
        "Sealed 4.0.3 npm archive failed its integrity pin",
    )
    with tempfile.TemporaryDirectory(prefix="strling-preview-sealed-") as temporary:
        with tarfile.open(archive, "r:gz") as packed:
            packed.extractall(temporary, filter="data")
        output = subprocess.check_output(
            [
                "node",
                str(root / "bindings/lab-wasm/verify-browser-artifact.mjs"),
                str(evidence / entry["reserved_destination"]["asset"]),
                entry["artifact"]["sha256"],
                str(Path(temporary) / "package"),
                entry["version"],
            ],
            text=True,
            cwd=root,
            timeout=60,
        )
    result = json.loads(output)
    require(
        result["status"] == "passed"
        and result["base_revision"] == entry["compiler_base"]
        and result["candidate_sha256"] == entry["artifact"]["sha256"]
        and result["sealed_operation_count"] == 4
        and result["maximum_memory_bytes"] == entry["memory_bytes"],
        "Canonical adapter replay does not bind the admitted identities",
    )
    return result


def prepare(inputs: Path, destination: Path, entry: dict) -> None:
    verify_inputs(inputs, entry)
    destination.mkdir()
    filename = entry["reserved_destination"]["asset"]
    for name in (filename, *RECEIPTS, "draft-sbom.spdx.json"):
        shutil.copyfile(inputs / name, destination / name)
    (destination / "unsigned-provenance.json").write_text(
        json.dumps(provenance(entry), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (destination / "SHA256SUMS").write_text(
        f"{entry['artifact']['sha256']}  {filename}\n", encoding="utf-8"
    )
    verify_package(destination, entry)


def verify_package(evidence: Path, entry: dict) -> None:
    verify_inputs(evidence, entry)
    require(
        read_json(evidence / "unsigned-provenance.json") == provenance(entry),
        "Preview source-bound provenance does not match admission",
    )
    require(
        (evidence / "SHA256SUMS").read_text(encoding="utf-8")
        == f"{entry['artifact']['sha256']}  {entry['reserved_destination']['asset']}\n",
        "Preview checksum file does not match admission",
    )


def verify_signed(root: Path, bundle: Path, source: str, entry: dict) -> dict:
    from tooling.local_certification_attestation import verify_attestation

    signed = verify_attestation(
        repository_root=root,
        trust_root=root,
        bundle_dir=bundle,
        policy_name="release-candidate-certification-trust.json",
    )
    require(signed["certified_source_sha"] == source, "Unexpected certification source")
    admitted = json.loads(
        subprocess.check_output(
            ["git", "show", f"{source}:governance/lab-wasm-preview.json"],
            cwd=root,
            text=True,
        )
    )
    require(admitted == entry, "Signed source does not contain the exact admission")
    for claim in signed["profile_results"]:
        profile = claim["profile"]
        artifact = read_json(bundle / claim["evidence_path"])
        relevant = [
            operation
            for operation in artifact["deterministic_evidence"]["operations"]
            if operation["operation_id"] == "lab_wasm_preview_certification"
        ]
        require(len(relevant) == 1, f"Signed {profile} lacks the Preview replay")
        result = relevant[0]["structured_evidence"]
        require(
            relevant[0]["status"] == result["status"] == "passed"
            and result["operation_id"] == OPERATION
            and result["publication_authorized"] is False
            and result["commit"] == source
            and result["adapter_source"] == entry["source_revision"]
            and result["artifact_sha256"] == entry["artifact"]["sha256"]
            and result["receipt_sha256"] == entry["rebuild_receipt_sha256"]
            and result["canonical_replay"]["status"] == "passed"
            and result["canonical_replay"]["candidate_sha256"]
            == entry["artifact"]["sha256"],
            f"Signed {profile} does not bind the exact Preview bytes",
        )
    return signed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--qualify", action="store_true")
    mode.add_argument("--prepare", type=Path)
    mode.add_argument("--verify-signed-bundle", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--sealed-archive", type=Path)
    parser.add_argument("--certification-source")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = {
        "schema_version": "certification-result-v1",
        "operation_id": OPERATION,
        "status": "failed",
        "publication_authorized": False,
    }
    try:
        entry = admission(ROOT)
        result.update(
            adapter_source=entry["source_revision"],
            artifact_sha256=entry["artifact"]["sha256"],
            receipt_sha256=entry["rebuild_receipt_sha256"],
        )
        if args.verify_signed_bundle:
            require(
                args.certification_source is not None,
                "Signed verification requires an exact certification source",
            )
            result["signed"] = verify_signed(
                ROOT,
                args.verify_signed_bundle.resolve(),
                args.certification_source,
                entry,
            )
        elif args.prepare:
            require(
                args.evidence is not None, "Preparation requires an input directory"
            )
            prepare(args.evidence.resolve(), args.prepare, entry)
        else:
            given = os.environ.get("STRLING_LAB_PREVIEW_EVIDENCE")
            sealed = os.environ.get("STRLING_LAB_PREVIEW_SEALED_ARCHIVE")
            evidence = args.evidence or (Path(given) if given else None)
            archive = args.sealed_archive or (Path(sealed) if sealed else None)
            require(
                evidence is not None and archive is not None,
                "Preview replay requires the exact local package and pinned 4.0.3 npm archive",
            )
            verify_package(evidence.resolve(), entry)
            result["canonical_replay"] = seal_check(
                ROOT, evidence.resolve(), archive.resolve(), entry
            )
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        if args.qualify:
            require(
                not subprocess.check_output(
                    ["git", "--no-optional-locks", "status", "--porcelain"],
                    cwd=ROOT,
                    text=True,
                ).strip(),
                "Preview qualification requires a clean certification source",
            )
            subprocess.run(
                [
                    "git",
                    "merge-base",
                    "--is-ancestor",
                    entry["source_revision"],
                    commit,
                ],
                check=True,
                cwd=ROOT,
            )
        result.update(status="passed", commit=commit)
    except (
        OSError,
        ValueError,
        KeyError,
        ReleaseSupplyChainError,
        subprocess.SubprocessError,
        tarfile.TarError,
    ) as error:
        result["error"] = str(error)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
