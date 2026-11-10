"""Bind public verification expectations to independent signed certification."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from tooling.public_distribution import strict_json
from tooling.public_retrieval import RetrievalError
from tooling.release_supply_chain import (
    MANIFEST_PATH,
    ROOT,
    canonical_json,
    load_json,
    verify_bundle,
)


def git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return completed.stdout.strip()


def authenticate_release(
    *,
    verifier: Path,
    implementation_source: Path,
    certification_source: Path,
    bundle: Path,
    evidence: Path,
    expected_source: str,
    expected_closure: str,
    expected_root: str,
    contract: dict,
    output: Path,
) -> dict:
    """Run immutable verifier-owned code; candidate source is data throughout.

    Expected identities and contract belong to the trusted verification caller.
    No publication approval, credentials or registry client is involved here.
    """
    policy = contract["certification_trust"]
    if policy not in {
        "governance/release-certification-trust.json",
        "governance/public-verification-certification-trust.json",
    }:
        raise RetrievalError(
            "provenance-signature", "unregistered certification trust context"
        )
    for value, width in (
        (expected_source, 40),
        (expected_closure, 40),
        (expected_root, 64),
    ):
        if re.fullmatch(r"[0-9a-f]{" + str(width) + r"}", value) is None:
            raise RetrievalError(
                "provenance-signature", "invalid expected certification identity"
            )
    if output.exists():
        raise RetrievalError(
            "provenance-signature", "verification output already exists"
        )
    if git(verifier, "rev-parse", "HEAD") != contract["certification_verifier"] or git(
        verifier, "status", "--porcelain", "--untracked-files=all"
    ):
        raise RetrievalError(
            "provenance-signature",
            "trusted verifier is not the exact clean immutable revision",
        )
    if git(certification_source, "rev-parse", "HEAD") != expected_closure or git(
        certification_source, "status", "--porcelain", "--untracked-files=all"
    ):
        raise RetrievalError(
            "source-identity", "certification source is not the exact clean closure"
        )
    if git(implementation_source, "rev-parse", "HEAD") != expected_source or git(
        implementation_source, "status", "--porcelain", "--untracked-files=all"
    ):
        raise RetrievalError(
            "source-identity",
            "implementation source is not the exact clean certified commit",
        )
    output.mkdir(parents=True)
    scratch = output / "scratch"
    scratch.mkdir()
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        in {
            "PATH",
            "SystemRoot",
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "PATHEXT",
            "PROGRAMDATA",
            "LANG",
            "LC_ALL",
        }
    }
    environment.update(
        TMP=str(scratch),
        TEMP=str(scratch),
        TMPDIR=str(scratch),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            str(verifier / "tooling/local_certification_attestation.py"),
            "--repository-root",
            str(certification_source),
            "--trust-root",
            str(verifier),
            "--trust-policy",
            Path(policy).name,
            "verify",
            "--bundle",
            str(bundle),
            "--json",
        ],
        capture_output=True,
        timeout=300,
        check=False,
        env=environment,
    )
    (output / "verification.stdout").write_bytes(completed.stdout)
    (output / "verification.stderr").write_bytes(completed.stderr)
    if completed.returncode:
        raise RetrievalError(
            "provenance-signature", "immutable certification verifier rejected evidence"
        )
    result = strict_json(completed.stdout)
    if result.get("status") != "passed":
        raise RetrievalError(
            "provenance-signature", "certification verifier did not pass"
        )
    attestation = load_json(bundle / "attestation.json")["signed_payload"]
    if (
        attestation["certified_source"]["commit"] != expected_source
        or attestation["evidence_root_sha256"] != expected_root
    ):
        raise RetrievalError(
            "provenance-signature",
            "signed root or source differs from authorized verification identity",
        )
    evidence_sha = hashlib.sha256(evidence.read_bytes()).hexdigest()
    if not any(
        row["role"] == "release-supply-chain" and row["sha256"] == evidence_sha
        for row in attestation["evidence_files"]
    ):
        raise RetrievalError(
            "provenance-signature",
            "supply-chain evidence is unrelated to the signed root",
        )
    manifest = load_json(implementation_source / MANIFEST_PATH.relative_to(ROOT))
    supply = verify_bundle(
        root=implementation_source,
        evidence_path=evidence,
        manifest=manifest,
        verify_subjects=False,
    )
    if (
        supply["source"]["commit"] != expected_source
        or supply["profile"] != "release"
        or supply["evidence_authority"] != "live-dry-run"
        or supply["status"] != "passed"
    ):
        raise RetrievalError(
            "provenance-signature",
            "expected complete source-bound Release supply-chain evidence",
        )
    receipt = {
        "status": "passed",
        "product_version": load_json(
            implementation_source / "governance/release-policy.json"
        )["product"]["version"],
        "certified_source_sha": expected_source,
        "closure_source_sha": expected_closure,
        "signed_evidence_root": expected_root,
        "verifier_source_sha": contract["certification_verifier"],
        "trust_policy": policy,
        "manifest_sha256": hashlib.sha256(canonical_json(manifest)).hexdigest(),
        "supply_chain_sha256": evidence_sha,
        "publication_authorized": False,
    }
    (output / "authentication.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {"receipt": receipt, "manifest": manifest, "evidence": supply}


def subject_checksums(evidence: Path, artifact: dict) -> dict[str, str]:
    """Read only after authenticate_release verified the entire companion set."""
    result = {}
    for line in (
        (evidence.parent / "checksums" / (artifact["surface"] + ".sha256"))
        .read_text(encoding="utf-8")
        .splitlines()[1:]
    ):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None or match[2] in result:
            raise RetrievalError(
                "provenance-signature", "invalid certified subject checksums"
            )
        result[match[2]] = match[1]
    if not result:
        raise RetrievalError("provenance-signature", "missing certified subjects")
    return result
