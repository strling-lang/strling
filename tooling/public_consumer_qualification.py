"""Run staged clean consumers from a successful authenticated retrieval campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from tooling.public_distribution import strict_json
from tooling.public_verification import write_retrieved
from tooling.release_consumers import verify_retrieved_consumer
from tooling.release_packaging import host_scope
from tooling.release_payload import archive_files
from tooling.release_supply_chain import load_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--harness", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifact-id", action="append")
    args = parser.parse_args()
    report = load_json(args.qualification / "qualification.json")
    if (
        report["status"] != "artifact-qualification-passed"
        or report["authority"] != "synthetic"
    ):
        raise ValueError("a complete staged artifact qualification is required")
    root = args.qualification.resolve() / "retrieved"
    manifest = load_json(
        args.harness / "tests/certification/release-supply-chain/1.0/manifest.json"
    )
    version = load_json(args.harness / "governance/release-policy.json")["product"][
        "version"
    ]
    files = {}
    for artifact in manifest["artifacts"]:
        receipt = strict_json(
            (
                args.qualification / (artifact["id"].replace(":", "-") + ".json")
            ).read_bytes()
        )
        if "finding" in receipt or receipt["authority"] != "synthetic":
            raise ValueError("staged retrieval did not pass")
        for name, digest in receipt["retrieval_files"].items():
            if name in files and files[name] != digest:
                raise ValueError("conflicting staged retrieval")
            files[name] = digest
    for name, digest in files.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError("staged retrieval changed")
    scope = host_scope()
    wheels = [
        name
        for name in files
        if name.endswith(".whl")
        and ("win_amd64" in name if os.name == "nt" else "linux_x86_64" in name)
    ]
    if len(wheels) != 1:
        raise ValueError(
            "one authenticated host wheel is required for the native companion"
        )
    native_files = {
        name: data
        for name, data in archive_files(root / wheels[0]).items()
        if name.endswith(
            "strling_interop.dll" if os.name == "nt" else "libstrling_interop.so"
        )
    }
    if len(native_files) != 1:
        raise ValueError("one authenticated native companion is required")
    native_name, native_bytes = next(iter(native_files.items()))
    native_name = "authenticated-native/" + scope + "/" + Path(native_name).name
    files[native_name] = write_retrieved(root, native_name, native_bytes)
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for artifact in manifest["artifacts"]:
        if (
            artifact["distribution_contract"]["tier"] != "Supported"
            or scope not in artifact["distribution_contract"]["platforms"]
        ):
            continue
        if args.artifact_id and artifact["id"] not in args.artifact_id:
            continue
        started = time.monotonic()
        slug = artifact["id"].split(":")[1]
        try:
            receipt = verify_retrieved_consumer(
                artifact["id"],
                retrieval_root=root,
                fixture_root=args.harness,
                work=args.output / (slug + "-consumer"),
                manifest=manifest,
                version=version,
                sdk_environment=dict(os.environ),
                retrieval_files=files,
                authority="staged",
                native=root / native_name,
            )
            row = {
                "artifact_id": artifact["id"],
                "status": "passed",
                "receipt": receipt,
            }
        except Exception as error:
            row = {
                "artifact_id": artifact["id"],
                "status": "failed",
                "error_type": type(error).__name__,
                "detail": str(error),
            }
        row["elapsed_seconds"] = time.monotonic() - started
        rows.append(row)
        (args.output / (slug + ".json")).write_text(
            json.dumps(row, indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps({key: value for key, value in row.items() if key != "receipt"}),
            flush=True,
        )
    passed = sum(row["status"] == "passed" for row in rows)
    summary = {
        "authority": "staged",
        "scope": scope,
        "selected": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "source": report["source"],
        "public_release_verified": False,
        "native_companion_wheel": wheels[0],
        "native_companion_sha256": files[native_name],
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return int(passed != len(rows) or not rows)


if __name__ == "__main__":
    raise SystemExit(main())
