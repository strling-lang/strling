"""Prepare and guard the single independently versioned RC4 Preview release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "governance/lab-wasm-rc4-publication.json"
WASM = "strling_lab_wasm.wasm"
ATTESTATION = "rc4-certification-attestation.json"
SIGNED_PREVIEW = "evidence/lab-wasm-preview-evidence/"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(data):
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_bytes())


def git(repository, *arguments):
    return subprocess.check_output(["git", "-C", str(repository), *arguments])


def file_identity(path):
    require(
        path.is_file() and not path.is_symlink(), f"Missing regular file {path.name}"
    )
    with path.open("rb") as stream:
        return {
            "bytes": path.stat().st_size,
            "sha256": hashlib.file_digest(stream, "sha256").hexdigest(),
        }


def verify_local_assets(assets, spec):
    require(
        {file.name for file in assets.iterdir()} == set(spec["assets"]),
        "Local inventory contains missing or unexpected assets",
    )
    for name, expected in spec["assets"].items():
        require(
            file_identity(assets / name) == expected,
            f"Local asset identity differs for {name}",
        )


def verify_certification(repository, bundle, verified, spec):
    require(
        verified["status"] == "passed" and verified["publication_authorized"] is False,
        "Independent certification receipt did not pass",
    )
    cert = verified["certification"]
    expected = {
        "certification_state": "CLOUD_VERIFIED",
        "verified_head_sha": spec["closure_commit"],
        "certified_source_sha": spec["certified_source"],
        "evidence_root_sha256": spec["certified_root"],
        "attestation_sha256": spec["assets"][ATTESTATION]["sha256"],
        "waiver_inventory": ["WVR-SEC-VSCE-LICENSE-001"],
    }
    require(
        all(cert[key] == value for key, value in expected.items()),
        "Certified closure identity differs",
    )
    require(
        git(repository, "rev-parse", "HEAD").decode().strip() == spec["closure_commit"],
        "Wrong evidence checkout",
    )
    require(
        git(repository, "rev-parse", spec["adapter_source"] + "^{tree}")
        .decode()
        .strip()
        == spec["adapter_tree"],
        "Wrong frozen source tree",
    )
    for name, digest in spec["source_policies"].items():
        require(
            sha(git(repository, "show", f"{spec['certified_source']}:{name}"))
            == digest,
            f"Certified policy differs for {name}",
        )
    path = bundle / "attestation.json"
    require(
        file_identity(path) == spec["assets"][ATTESTATION],
        "Signed attestation bytes differ",
    )
    signed = load(path)["signed_payload"]
    require(
        signed["evidence_root_sha256"] == spec["certified_root"],
        "Signed evidence root differs",
    )
    entries = {
        row["path"]: {"bytes": row["bytes"], "sha256": row["sha256"]}
        for row in signed["evidence_files"]
    }
    require(
        len(entries) == len(signed["evidence_files"]), "Duplicate signed evidence path"
    )
    for name in set(spec["assets"]) - {WASM, ATTESTATION}:
        relative = SIGNED_PREVIEW + name
        require(
            file_identity(bundle / relative)
            == entries.get(relative)
            == spec["assets"][name],
            f"Signed release metadata differs for {name}",
        )
    admission = load(bundle / SIGNED_PREVIEW / "lab-wasm-preview.json")
    require(
        entries.get(SIGNED_PREVIEW + "lab-wasm-preview.json")
        == file_identity(bundle / SIGNED_PREVIEW / "lab-wasm-preview.json")
        and admission["artifact"] == spec["assets"][WASM]
        and admission["source_revision"] == spec["adapter_source"]
        and admission["wire_protocol"] == spec["protocol"]
        and admission["version"] == spec["version"]
        and admission["reserved_destination"]
        == {
            "repository": spec["repository"],
            "tag": spec["tag"],
            "asset": WASM,
            "immutable_required": True,
        },
        "Preview admission does not bind these release subjects",
    )
    profiles = cert["profile_results"]
    require(
        len(profiles) == 2
        and {row["profile"] for row in profiles} == {"full", "release"},
        "Missing mandatory profile",
    )
    for row in profiles:
        counts = row["counts"]
        require(
            row["definition_version"] == "1.34.0"
            and row["operation_count"] == 126
            and counts["passed"] == 125
            and counts["waived"] == 1
            and sum(counts.values()) == 126
            and row["exit_code"] == 0,
            "Mandatory profile denominator differs",
        )
        profile = load(bundle / row["evidence_path"])
        preview = [
            item["structured_evidence"]
            for item in profile["deterministic_evidence"]["operations"]
            if item["operation_id"] == "lab_wasm_preview_certification"
            and item["status"] == "passed"
        ]
        require(len(preview) == 1, "Missing successful Preview replay")
        replay = preview[0]
        require(
            replay["commit"] == spec["certified_source"]
            and replay["adapter_source"] == spec["adapter_source"]
            and replay["artifact_sha256"] == spec["assets"][WASM]["sha256"]
            and replay["canonical_replay"]["maximum_memory_bytes"]
            == admission["memory_bytes"]
            and replay["canonical_replay"]["sealed_operation_count"] == 4,
            "Signed Preview replay does not bind the Wasm",
        )


def context(spec, environ):
    workflow = environ.get("GITHUB_WORKFLOW_SHA", "")
    run = environ.get("GITHUB_RUN_ID", "")
    attempt = environ.get("GITHUB_RUN_ATTEMPT", "")
    require(
        environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        and environ.get("GITHUB_REPOSITORY") == spec["repository"]
        and environ.get("GITHUB_REF") == "refs/heads/main"
        and environ.get("GITHUB_ACTOR") == spec["owner"]
        and environ.get("GITHUB_TRIGGERING_ACTOR") == spec["owner"]
        and re.fullmatch(r"[0-9a-f]{40}", workflow)
        and environ.get("GITHUB_SHA") == workflow
        and re.fullmatch(r"[1-9][0-9]*", run)
        and re.fullmatch(r"[1-9][0-9]*", attempt),
        "Wrong workflow source, repository, run, or attempt",
    )
    return {
        "workflow_sha": workflow,
        "run_id": run,
        "run_attempt": attempt,
        "environment": spec["environment"],
    }


def release_notes(spec):
    return (
        "Browser compiler-tools Preview for canonical Semantic STRling formatting, proof-carrying "
        "conversion, and bounded no-match explanation.\n\n"
        f"The adapter uses {spec['protocol']} alongside sealed STRling 4.0.3. "
        "Verify the Wasm against SHA256SUMS and the independently authenticated certification.\n\n"
        f"Frozen artifact source: {spec['adapter_source']}\n"
        f"Certified compiler source: {spec['certified_source']}\n"
        f"Signed evidence root (SHA-256): {spec['certified_root']}\n"
        f"Hosted certification: https://github.com/{spec['repository']}/actions/runs/{spec['hosted_certification_run']}\n"
        f"Full signed evidence: https://github.com/{spec['repository']}/tree/{spec['closure_commit']}/tests/certification/release-candidate/1.0/current\n"
    )


def approval_document(spec, run):
    return {
        "kind": "strling-lab-wasm-preview-publication-authorization-v1",
        "decision": "approve-exact-immutable-preview-publication",
        "subject": spec,
        "context": run,
        "release_notes_sha256": sha(release_notes(spec).encode()),
    }


def verify_approval(expected, environ, reviews):
    spec, run = expected["subject"], expected["context"]
    require(
        environ.get("RC4_ENVIRONMENT") == run["environment"],
        "Wrong protected environment",
    )
    digest = sha(canonical(expected))
    comment = "P20-T05 approve sha256:" + digest
    decisions = [
        review
        for review in reviews
        if any(entry["name"] == run["environment"] for entry in review["environments"])
    ]
    require(
        decisions
        and all(
            review["user"]["login"] == spec["owner"]
            and review["state"] == "approved"
            and review["comment"] == comment
            for review in decisions
        ),
        "Missing or mismatched exact Program Owner approval",
    )
    return digest


def api(spec, path, *, method="GET", body=None, absent=False, admin=False):
    environment = dict(os.environ)
    if admin:
        reader = environment.get("RC4_IMMUTABILITY_READER")
        require(
            reader, "Protected repository Administration read credential is unavailable"
        )
        environment["GH_TOKEN"] = reader
    environment.pop("RC4_IMMUTABILITY_READER", None)
    command = [
        "gh",
        "api",
        "--include",
        "--method",
        method,
        "-H",
        "X-GitHub-Api-Version: 2026-03-10",
        f"repos/{spec['repository']}/{path}",
    ]
    if body is not None:
        command.extend(["--input", "-"])
    response = subprocess.run(
        command,
        input=json.dumps(body) if body is not None else None,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    header, _, data = response.stdout.partition("\n\n")
    status = re.match(r"HTTP/\S+ (\d{3})\b", header)
    code = int(status[1]) if status else 0
    if absent and code == 404:
        return None
    require(
        response.returncode == 0 and code == (201 if method == "POST" else 200),
        f"GitHub {method} {path} returned {code}",
    )
    return json.loads(data)


def verify_destination(spec, request=api, *, draft_id=None):
    tag = spec["tag"]
    require(
        request(spec, f"git/ref/tags/{tag}", absent=True) is None,
        "Reserved tag already exists",
    )
    release = request(spec, f"releases/tags/{tag}", absent=True)
    require(
        release is None or (release["draft"] is True and release["id"] == draft_id),
        "Reserved release already exists",
    )
    target = request(spec, f"commits/{spec['adapter_source']}")
    require(
        target["sha"] == spec["adapter_source"]
        and target["commit"]["tree"]["sha"] == spec["adapter_tree"],
        "GitHub tag target or tree differs",
    )


def verify_immutability(spec, request=api):
    require(
        request(spec, "immutable-releases", admin=True)["enabled"] is True,
        "Repository release immutability is disabled",
    )


def verify_release(release, spec, notes, *, draft):
    require(
        release["tag_name"] == spec["tag"]
        and release["target_commitish"] == spec["adapter_source"]
        and release["draft"] is draft
        and release["prerelease"] is True
        and release["name"] == f"STRling Lab Wasm {spec['version']} Preview"
        and release["body"] == notes
        and release.get("immutable", False) is (not draft),
        "GitHub release identity differs from the approved Preview",
    )
    assets = {}
    seen = set()
    for asset in release["assets"]:
        name = asset["name"]
        require(
            name in spec["assets"] and name not in seen,
            "Unexpected or duplicate release asset",
        )
        seen.add(name)
        if asset["state"] == "starter" and draft:
            continue
        expected = spec["assets"][name]
        require(
            asset["state"] == "uploaded"
            and asset["size"] == expected["bytes"]
            and asset["digest"] == "sha256:" + expected["sha256"],
            f"GitHub release asset identity differs for {name}",
        )
        assets[name] = expected
    return assets == spec["assets"]


def publish(spec, notes):
    verify_immutability(spec, api)
    verify_destination(spec, api)
    page = 1
    while True:
        existing = api(spec, f"releases?per_page=100&page={page}")
        require(
            all(row["tag_name"] != spec["tag"] for row in existing),
            "An existing draft uses the reserved coordinate",
        )
        if len(existing) < 100:
            break
        page += 1
    release = api(
        spec,
        "releases",
        method="POST",
        body={
            "tag_name": spec["tag"],
            "target_commitish": spec["adapter_source"],
            "draft": True,
            "prerelease": True,
            "make_latest": "false",
            "name": f"STRling Lab Wasm {spec['version']} Preview",
            "body": notes,
        },
    )
    release_id = release["id"]
    require(type(release_id) is int and release_id > 0, "Invalid draft release ID")
    print(
        f"Approved draft {release_id} awaits the seven exact assets from the frozen local bundle.",
        flush=True,
    )
    deadline = time.monotonic() + 900
    while not verify_release(release, spec, notes, draft=True):
        require(
            time.monotonic() < deadline,
            "Timed out waiting for exact assets. Draft held without publishing.",
        )
        time.sleep(5)
        release = api(spec, f"releases/{release_id}")
    verify_immutability(spec, api)
    verify_destination(spec, api, draft_id=release_id)
    require(
        verify_release(api(spec, f"releases/{release_id}"), spec, notes, draft=True),
        "Draft inventory changed",
    )
    published = api(
        spec,
        f"releases/{release_id}",
        method="PATCH",
        body={"draft": False, "make_latest": "false"},
    )
    require(
        published["id"] == release_id
        and verify_release(published, spec, notes, draft=False),
        "Immutable published release verification failed",
    )
    target = api(spec, f"git/ref/tags/{spec['tag']}")
    require(
        target["object"]["type"] == "commit"
        and target["object"]["sha"] == spec["adapter_source"],
        "Published tag points to a different source",
    )
    attestation_command = [
        "gh",
        "release",
        "verify",
        spec["tag"],
        "--repo",
        spec["repository"],
        "--format=json",
    ]
    # GitHub generates the release attestation asynchronously after publication.
    for attempt in range(12):
        result = subprocess.run(
            attestation_command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )
        if result.returncode == 0:
            return {
                "published_release_id": release_id,
                "immutable": True,
                "release_attestation": json.loads(result.stdout),
            }
        if attempt < 11:
            time.sleep(5)
    raise ValueError(
        f"Release {release_id} is published, but its attestation could not be verified"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["plan", "authorize", "publish"])
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--verification-receipt", type=Path)
    parser.add_argument("--local-assets", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    spec = load(POLICY)
    run = context(spec, os.environ)
    approval = approval_document(spec, run)
    digest = sha(canonical(approval))
    if args.mode != "plan":
        verify_approval(
            approval, os.environ, api(spec, f"actions/runs/{run['run_id']}/approvals")
        )
    if args.mode == "publish":
        print(json.dumps(publish(spec, release_notes(spec)), indent=2))
        return
    if args.mode == "authorize":
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.write("approved=true\n")
        return
    require(
        args.evidence_root and args.verification_receipt,
        "Plan requires the verified signed closure",
    )
    bundle = args.evidence_root / "tests/certification/release-candidate/1.0/current"
    verify_certification(
        args.evidence_root, bundle, load(args.verification_receipt), spec
    )
    if args.local_assets:
        verify_local_assets(args.local_assets, spec)
    if args.live:
        verify_destination(spec)
    print(
        json.dumps(
            {
                "status": "passed",
                "authorization_proposal": approval,
                "proposed_approval_sha256": digest,
                "release_notes": release_notes(spec),
                "live_coordinate_checked": args.live,
                "local_bytes_verified": bool(args.local_assets),
                "publication_authorized": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
