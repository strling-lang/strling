"""Move already certified bytes into Actions artifacts without building or publishing.

The archive digest and source/root identities are protected owner inputs. They
do not replace original-authority signature verification or subject checks.
No package-provided code, lifecycle script, signing key, or registry is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import zipfile
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tooling.local_certification_attestation import verify_attestation
from tooling.public_authentication import git, subject_checksums
from tooling.public_distribution import strict_json
from tooling.release_payload import MAX_FILE, MAX_TOTAL, archive_files
from tooling.release_supply_chain import MANIFEST_PATH, ROOT, load_json, verify_bundle


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def export_graph(manifest: dict, evidence: Path, source: str) -> dict[str, str]:
    """Derive the complete transport file inventory from signed SPDX subjects."""
    result = {}
    for artifact in manifest["artifacts"]:
        checks = subject_checksums(evidence, artifact)
        kind = artifact["artifact_policy"]["subject_kind"]
        if kind in {"source-tree", "registry-assembled"}:
            sbom = load_json(
                evidence.parent / "sbom" / (artifact["surface"] + ".spdx.json")
            )
            rows = {
                row["fileName"]: next(
                    c["checksumValue"]
                    for c in row["checksums"]
                    if c["algorithm"] == "SHA256"
                )
                for row in sbom["files"]
            }
            prefix = (
                Path(next(iter(checks)))
                if kind == "registry-assembled"
                else Path(os.path.commonpath([str(Path(name).parent) for name in rows]))
            )
        else:
            rows = checks
            prefix = Path(os.path.commonpath([str(Path(name).parent) for name in rows]))
        directory = (
            "certified-" + artifact["id"].removeprefix("release:") + "-" + source
        )
        for name, checksum in rows.items():
            relative = (Path(directory) / Path(name).relative_to(prefix)).as_posix()
            need(relative not in result, "duplicate certified export path")
            result[relative] = checksum
    return result


def inventory(root: Path) -> dict[str, str]:
    need(
        root.is_dir() and not root.is_symlink(),
        "transport root is not a regular directory",
    )
    result = {}
    for path in root.rglob("*"):
        need(
            not path.is_symlink() and path.resolve().is_relative_to(root.resolve()),
            "linked transport member",
        )
        if path.is_file():
            need(path.stat().st_size <= MAX_FILE, "oversized transport member")
            result[path.relative_to(root).as_posix()] = digest(path)
        else:
            need(path.is_dir(), "special transport member")
    return result


def authenticate(
    source_root: Path,
    trust: Path,
    bundle: Path,
    source: str,
    evidence_root: str,
    closure: Path,
) -> tuple[dict, dict[str, str]]:
    need(
        re.fullmatch(r"[0-9a-f]{40}", source) is not None
        and re.fullmatch(r"[0-9a-f]{64}", evidence_root) is not None,
        "invalid protected identity",
    )
    need(
        trust.resolve() == ROOT.resolve()
        and not git(trust, "status", "--porcelain", "--untracked-files=all"),
        "trust must be this clean immutable verifier",
    )
    need(
        git(source_root, "rev-parse", "HEAD") == source
        and not git(source_root, "status", "--porcelain", "--untracked-files=all"),
        "source is not the exact clean certified commit",
    )
    need(
        not git(closure, "status", "--porcelain", "--untracked-files=all"),
        "candidate closure must be clean",
    )
    candidate_bundle = closure / "tests/certification/release-candidate/1.0/current"
    candidate = verify_attestation(
        repository_root=closure,
        trust_root=trust,
        bundle_dir=candidate_bundle,
        policy_name="release-candidate-certification-trust.json",
    )
    need(
        candidate["certified_source_sha"] == source,
        "candidate certificate names another source",
    )
    candidate_payload = load_json(candidate_bundle / "attestation.json")[
        "signed_payload"
    ]
    nested = [
        row
        for row in candidate_payload["evidence_files"]
        if row["role"] == "staged-package-attestation"
    ]
    need(
        len(nested) == 1
        and (candidate_bundle / nested[0]["path"]).read_bytes()
        == (bundle / "attestation.json").read_bytes(),
        "package certificate differs from the exact candidate-certified original",
    )
    result = verify_attestation(
        repository_root=source_root,
        trust_root=trust,
        bundle_dir=bundle,
        policy_name="release-certification-trust.json",
    )
    need(
        result["certified_source_sha"] == source
        and result["evidence_root_sha256"] == evidence_root,
        "signed source or root differs from protected identity",
    )
    payload = load_json(bundle / "attestation.json")["signed_payload"]
    expected_bundle = {row["path"]: row["sha256"] for row in payload["evidence_files"]}
    expected_bundle["attestation.json"] = digest(bundle / "attestation.json")
    need(
        inventory(bundle) == expected_bundle,
        "signed package bundle has extra or missing files",
    )
    evidence = (
        bundle / "evidence/release-supply-chain/release-supply-chain-evidence.json"
    )
    need(
        "evidence/release-supply-chain/release-supply-chain-evidence.json"
        in expected_bundle,
        "missing signed Release supply-chain evidence",
    )
    manifest = load_json(source_root / MANIFEST_PATH.relative_to(ROOT))
    supply = verify_bundle(
        root=source_root,
        evidence_path=evidence,
        manifest=manifest,
        verify_subjects=False,
    )
    need(
        supply["source"]["commit"] == source
        and supply["status"] == "passed"
        and supply["profile"] == "release"
        and supply["evidence_authority"] == "live-dry-run",
        "not complete exact-source Release evidence",
    )
    expected = export_graph(manifest, evidence, source)
    expected.update(
        {
            "signed-release-" + source + "/" + name: checksum
            for name, checksum in expected_bundle.items()
        }
    )
    return result, expected


def seal(
    *,
    source_root: Path,
    trust: Path,
    bundle: Path,
    exports: Path,
    source: str,
    evidence_root: str,
    closure: Path,
    output: Path,
) -> dict:
    need(
        output.absolute() == output.resolve()
        and not any(
            output.resolve().is_relative_to(path.resolve())
            for path in (source_root, trust, bundle, exports, closure)
        ),
        "capsule must be outside protected source and evidence directories",
    )
    _, expected = authenticate(
        source_root, trust, bundle, source, evidence_root, closure
    )
    prefix = "signed-release-" + source + "/"
    observed = inventory(exports)
    need(
        observed
        == {
            name: value
            for name, value in expected.items()
            if not name.startswith(prefix)
        },
        "exports differ from the complete signed file graph",
    )
    need(not output.exists() and not output.is_symlink(), "capsule already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, checksum in sorted(expected.items()):
            path = (
                bundle / name[len(prefix) :]
                if name.startswith(prefix)
                else exports / name
            )
            data = path.read_bytes()
            total += len(data)
            need(
                total <= MAX_TOTAL
                and len(data) <= MAX_FILE
                and hashlib.sha256(data).hexdigest() == checksum,
                "certified bytes changed during sealing",
            )
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    return dict(
        status="passed-local-certified-transport-seal",
        source=source,
        evidence_root=evidence_root,
        capsule_sha256=digest(output),
        bytes=output.stat().st_size,
        files=len(expected),
        publication_authorized=False,
    )


def restore(
    *,
    capsule: Path,
    capsule_sha256: str,
    source_root: Path,
    trust: Path,
    source: str,
    evidence_root: str,
    closure: Path,
    output: Path,
) -> dict:
    need(
        not any(
            output.resolve().is_relative_to(path.resolve())
            for path in (source_root, trust, closure)
        ),
        "exports must be outside protected checkouts",
    )
    need(
        re.fullmatch(r"[0-9a-f]{64}", capsule_sha256) is not None
        and capsule.is_file()
        and not capsule.is_symlink()
        and capsule.stat().st_size <= MAX_TOTAL
        and digest(capsule) == capsule_sha256,
        "capsule differs from protected digest or size bound",
    )
    need(
        not output.exists() and output.absolute() == output.resolve(),
        "output must be a new unlinked directory",
    )
    files = archive_files(capsule)
    # Parse only regular bounded bytes, never archive extraction or member code.
    with tempfile.TemporaryDirectory(
        prefix="strling-certified-transport-"
    ) as temporary:
        work = Path(temporary)
        for name, data in files.items():
            path = work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        bundle = work / ("signed-release-" + source)
        _, expected = authenticate(
            source_root, trust, bundle, source, evidence_root, closure
        )
        need(
            {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
            == expected,
            "capsule has extra, absent, or substituted certified files",
        )
        output.mkdir(parents=True, exist_ok=False)
        for name, data in files.items():
            destination = output / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
    return dict(
        status="passed-certified-byte-restoration",
        source=source,
        evidence_root=evidence_root,
        capsule_sha256=capsule_sha256,
        files=len(files),
        rebuilt=False,
        registry_requests=0,
        publication_authorized=False,
    )


def fetch_draft(
    *, release_id: str, asset_id: str, source: str, capsule_sha256: str, output: Path
) -> None:
    """Read one separately authorized private staging asset; never create a release."""
    need(
        not output.resolve().is_relative_to(ROOT.resolve()),
        "private staging must be outside the verifier checkout",
    )
    need(
        all(re.fullmatch(r"[1-9][0-9]*", value) for value in (release_id, asset_id)),
        "invalid staging identity",
    )
    need(
        re.fullmatch(r"[0-9a-f]{40}", source) is not None
        and re.fullmatch(r"[0-9a-f]{64}", capsule_sha256) is not None,
        "invalid protected staging identity",
    )
    need(
        not output.exists() and output.absolute() == output.resolve(),
        "staging output exists or is linked",
    )
    endpoint = "repos/strling-lang/strling/releases/" + release_id
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        in {
            "PATH",
            "SystemRoot",
            "SYSTEMROOT",
            "WINDIR",
            "HOME",
            "USERPROFILE",
            "GH_TOKEN",
            "GITHUB_TOKEN",
        }
    }
    command = ["gh", "api", "--hostname", "github.com"]
    record = strict_json(
        subprocess.check_output([*command, endpoint], env=env, timeout=60)
    )
    need(
        record.get("id") == int(release_id)
        and record.get("draft") is True
        and record.get("published_at") is None
        and record.get("target_commitish") == source,
        "staging release is public, changed, or from another source",
    )
    assets = [a for a in record["assets"] if a["id"] == int(asset_id)]
    need(len(assets) == 1, "private staging asset is absent or ambiguous")
    asset = assets[0]
    need(
        asset["name"] == "strling-certified-" + source + ".zip"
        and asset["state"] == "uploaded"
        and type(asset["size"]) is int
        and 0 < asset["size"] <= MAX_TOTAL
        and asset.get("digest") == "sha256:" + capsule_sha256,
        "staging asset metadata differs from approved bytes",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        [
            *command,
            "repos/strling-lang/strling/releases/assets/" + asset_id,
            "--header",
            "Accept: application/octet-stream",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    timer = threading.Timer(300, process.kill)
    timer.start()
    try:
        total = 0
        with output.open("xb") as stream:
            while block := process.stdout.read(min(65536, asset["size"] - total + 1)):
                total += len(block)
                need(
                    total <= asset["size"],
                    "private staging download exceeds approved size",
                )
                stream.write(block)
        need(process.wait(timeout=10) == 0, "private staging download failed")
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        process.stdout.close()
    need(
        output.stat().st_size == asset["size"] and digest(output) == capsule_sha256,
        "private staging download changed",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("seal", "restore", "fetch"))
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--trust-root", type=Path)
    parser.add_argument("--closure-root", type=Path)
    parser.add_argument("--evidence-root")
    parser.add_argument("--capsule", type=Path)
    parser.add_argument("--capsule-sha256")
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--exports", type=Path)
    parser.add_argument("--release-id")
    parser.add_argument("--asset-id")
    args = parser.parse_args()
    if args.command == "fetch":
        need(
            all((args.release_id, args.asset_id, args.capsule_sha256)),
            "fetch requires protected staging identities",
        )
        fetch_draft(
            release_id=args.release_id,
            asset_id=args.asset_id,
            source=args.source,
            capsule_sha256=args.capsule_sha256,
            output=args.output,
        )
        result = dict(
            status="passed-private-staging-download", publication_authorized=False
        )
    else:
        need(
            all(
                (
                    args.source_root,
                    args.trust_root,
                    args.evidence_root,
                    args.closure_root,
                )
            ),
            "transport requires source, trust, candidate closure and signed root",
        )
        kwargs = dict(
            source_root=args.source_root,
            trust=args.trust_root,
            source=args.source,
            evidence_root=args.evidence_root,
            closure=args.closure_root,
            output=args.output,
        )
        if args.command == "seal":
            need(
                args.bundle is not None and args.exports is not None,
                "seal requires signed bundle and exports",
            )
            result = seal(bundle=args.bundle, exports=args.exports, **kwargs)
        else:
            need(
                args.capsule is not None and args.capsule_sha256 is not None,
                "restore requires exact capsule",
            )
            result = restore(
                capsule=args.capsule, capsule_sha256=args.capsule_sha256, **kwargs
            )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
