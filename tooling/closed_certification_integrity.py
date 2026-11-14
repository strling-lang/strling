"""Preserve exact, previously accepted certificates without renewing certification.

Only the frozen closed-subject registry in this verifier is authority. All data
come from its exact Git objects. This operation cannot certify a new source,
renew a waiver, accept an altered certificate, or authorize publication.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tooling import local_certification_attestation as attestation
from tooling.public_distribution import strict_json

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "governance/closed-certifications.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def git(repository: Path, *arguments: str, data: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "--no-replace-objects", "-C", str(repository), *arguments],
        input=data,
        capture_output=True,
        check=False,
        timeout=120,
    )
    require(result.returncode == 0, "required immutable Git object is unavailable")
    return result.stdout


def registered_subject(identity: str) -> dict:
    registry = strict_json(REGISTRY.read_bytes())
    require(
        registry.get("schema_version") == "1.0.0"
        and registry.get("purpose") == "preserve-closed-certification-evidence"
        and registry.get("current_certification_authority") is False
        and registry.get("publication_authority") is False,
        "invalid historical preservation authority",
    )
    subjects = registry["subjects"]
    ids = [row["id"] for row in subjects]
    require(len(ids) == len(set(ids)), "duplicate closed certification subject")
    selected = [row for row in subjects if row["id"] == identity]
    require(len(selected) == 1, "unregistered closed certification subject")
    subject = selected[0]
    for field in (
        "closure_sha",
        "original_verifier_sha",
        "certified_source_sha",
        "certified_tree_sha",
        "bundle_tree",
    ):
        require(
            re.fullmatch(r"[0-9a-f]{40}", subject[field]) is not None,
            "invalid immutable historical object identity",
        )
    for field in ("attestation_sha256", "evidence_root_sha256"):
        require(
            re.fullmatch(r"[0-9a-f]{64}", subject[field]) is not None,
            "invalid historical evidence identity",
        )
    require(
        subject["bundle_path"].startswith("tests/certification/")
        and subject["trust_policy"].startswith("governance/"),
        "invalid historical authority path",
    )
    return subject


def bundle_bytes(repository: Path, subject: dict) -> dict[str, bytes]:
    closure, prefix = subject["closure_sha"], subject["bundle_path"]
    require(
        git(repository, "rev-parse", closure + ":" + prefix).decode().strip()
        == subject["bundle_tree"],
        "historical bundle tree differs from accepted authority",
    )
    records = git(repository, "ls-tree", "-rz", closure, "--", prefix).split(b"\0")
    indexed = []
    for record in records:
        if not record:
            continue
        metadata, name = record.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        path = name.decode()
        require(
            mode in {"100644", "100755"}
            and kind == "blob"
            and path.startswith(prefix + "/"),
            "historical bundle contains a linked or non-file object",
        )
        indexed.append((path[len(prefix) + 1 :], oid))
    require(bool(indexed), "historical bundle inventory is empty")
    raw = git(
        repository,
        "cat-file",
        "--batch",
        data="".join(oid + "\n" for _, oid in indexed).encode(),
    )
    result = {}
    cursor = 0
    for path, oid in indexed:
        end = raw.index(b"\n", cursor)
        actual, kind, size = raw[cursor:end].decode().split()
        size = int(size)
        require(
            actual == oid and kind == "blob" and 0 <= size <= 64 * 1024 * 1024,
            "invalid historical blob response",
        )
        cursor = end + 1
        payload = raw[cursor : cursor + size]
        require(
            len(payload) == size and raw[cursor + size : cursor + size + 1] == b"\n",
            "truncated historical blob",
        )
        require(path not in result, "duplicate historical bundle path")
        result[path] = payload
        cursor += size + 1
    require(cursor == len(raw), "unexpected historical blob response")
    return result


def verify_snapshot(subject: dict, files: dict[str, bytes], original: dict) -> dict:
    raw = files["attestation.json"]
    require(
        hashlib.sha256(raw).hexdigest() == subject["attestation_sha256"],
        "certificate differs from the exact previously accepted certificate",
    )
    document = strict_json(raw)
    payload, signature_record = document["signed_payload"], document["signature"]
    require(
        payload["certification_state"] == "LOCALLY_CERTIFIED"
        and payload["certified_source"]
        == {
            "commit": subject["certified_source_sha"],
            "tree": subject["certified_tree_sha"],
            "clean": True,
        },
        "historical certified source identity changed",
    )
    certifier = attestation._certifier(original, subject["certifier_id"])
    require(
        signature_record["scheme"] == "SSHSIG_ED25519"
        and signature_record["namespace"] == original["signature_namespace"]
        and signature_record["certifier_id"] == subject["certifier_id"]
        and payload["certifier"]["certifier_id"] == subject["certifier_id"]
        and payload["certifier"]["ssh_key_fingerprint"]
        == certifier["ssh_key_fingerprint"]
        == subject["ssh_key_fingerprint"],
        "historical signature authority changed",
    )
    signed = attestation.canonical_bytes(payload)
    signature = base64.b64decode(signature_record["signature_base64"], validate=True)
    require(
        hashlib.sha256(signed).hexdigest() == signature_record["signed_payload_sha256"]
        and hashlib.sha256(signature).hexdigest()
        == signature_record["signature_sha256"],
        "historical signature or signed payload digest changed",
    )
    attestation._verify_signature(
        signed, signature, certifier, original["signature_namespace"]
    )
    projection = dict(payload)
    root = projection.pop("evidence_root_sha256")
    require(
        root
        == subject["evidence_root_sha256"]
        == attestation.object_sha256(projection),
        "historical signed evidence root changed",
    )
    paths = set()
    for entry in payload["evidence_files"]:
        path = entry["path"]
        relative = PurePosixPath(path)
        require(
            isinstance(path, str)
            and relative.as_posix() == path
            and not relative.is_absolute()
            and ".." not in relative.parts
            and "\\" not in path
            and len(relative.parts) >= 3
            and relative.parts[0] == "evidence"
            and relative.parts[1] == entry["role"]
            and path not in paths,
            "unsafe or duplicated historical evidence path",
        )
        paths.add(path)
        require(
            path in files
            and type(entry["bytes"]) is int
            and len(files[path]) == entry["bytes"]
            and hashlib.sha256(files[path]).hexdigest() == entry["sha256"],
            "historical producer evidence is missing or changed",
        )
    require(
        bool(paths) and set(files) == paths | {"attestation.json"},
        "historical certificate has missing or additional files",
    )
    return {
        "status": "preserved-historical-certification",
        "operation_id": "certification.closed-evidence-integrity",
        "subject": subject["id"],
        "certified_source_sha": subject["certified_source_sha"],
        "closure_sha": subject["closure_sha"],
        "original_verifier_sha": subject["original_verifier_sha"],
        "evidence_root_sha256": root,
        "signature_sha256": signature_record["signature_sha256"],
        "evidence_files": len(paths),
        "accepted_hosted_run": subject["accepted_hosted_run"],
        "current_release_certification": False,
        "waiver_renewed": False,
        "publication_authorized": False,
    }


def verify(repository: Path, identity: str) -> dict:
    subject = registered_subject(identity)
    for field in ("closure_sha", "original_verifier_sha", "certified_source_sha"):
        require(
            git(repository, "rev-parse", subject[field] + "^{commit}").decode().strip()
            == subject[field],
            "historical source or authority object changed",
        )
    require(
        git(repository, "rev-parse", subject["certified_source_sha"] + "^{tree}")
        .decode()
        .strip()
        == subject["certified_tree_sha"],
        "historical certified tree identity changed",
    )
    original = strict_json(
        git(
            repository,
            "show",
            subject["original_verifier_sha"] + ":" + subject["trust_policy"],
        )
    )
    git(
        repository,
        "merge-base",
        "--is-ancestor",
        subject["certified_source_sha"],
        subject["closure_sha"],
    )
    return verify_snapshot(subject, bundle_bytes(repository, subject), original)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = verify(args.repository_root, args.subject)
    except Exception as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
