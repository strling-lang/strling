"""Profile gateway for the versioned shared-workstation certification policy."""

from pathlib import Path
import base64
import json
import os
import uuid

from tooling import performance_resource_certification as legacy
from tooling import workstation_campaign as campaign
from tooling import workstation_evidence as reader
from tooling import workstation_performance as score

METHOD_CHECK = "method:shared-workstation-v1"


def acquisition_directory(root):
    """Leave room for native linker outputs inside an isolated Release checkout.

    Acquisition still creates this fresh directory exclusively; a collision is
    rejected rather than reusing artifacts. Build recipes and workloads retain
    their existing layout below this shorter, repository-owned prefix.
    """
    return Path(root) / "target" / ("wp-" + uuid.uuid4().hex[:16])


def read_json(path):
    return reader.parse(Path(path).read_bytes())


def raw_file(path):
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


def campaign_payload(directory):
    directory = Path(directory)
    builds = {}
    for lane in ("reference", "candidate", "slowdown"):
        root = directory / lane
        builds[lane] = dict(
            recipe_bytes=raw_file(root / "recipe.json"),
            built=read_json(root / "built.json"),
            manifest_bytes=raw_file(root / "harness/Cargo.toml"),
            steps={
                name: dict(
                    receipt=read_json(root / (name + ".json")),
                    stdout=raw_file(root / (name + ".stdout")),
                    stderr=raw_file(root / (name + ".stderr")),
                )
                for name in ("harness-build", "kernel-build", "interop-build")
            },
        )
    return dict(
        contract="shared-workstation-profile-evidence-v2",
        cohort=reader.parse_container((directory / "cohort.json").read_bytes()),
        prospective_plan=read_json(directory / "prospective-plan.json"),
        builds=builds,
        source_archives={
            campaign.digest(directory / lane / "kernel-source.zip"): raw_file(
                directory / lane / "kernel-source.zip"
            )
            for lane in ("reference", "candidate", "slowdown")
        },
        terminal=read_json(directory / "terminal.json"),
        reconstruction=read_json(directory / "independent-reconstruction.json"),
        resources=read_json(directory / "functional-resource-checks.json"),
        native_memory={
            name: dict(
                receipt=read_json(directory / (name + ".json")),
                stdout=raw_file(directory / (name + ".stdout")),
                stderr=raw_file(directory / (name + ".stderr")),
            )
            for name in ("native-memory-test-build", "native-memory-tests")
        },
    )


def checks_from_payload(payload, manifest):
    cohort = payload["cohort"]
    checks = [
        dict(
            id=METHOD_CHECK,
            status="passed",
            details=reader.pack_profile_payload(payload),
        )
    ]
    for row in cohort["observations"]:
        raw = reader.parse(base64.b64decode(row["files"]["stdout.bin"], validate=True))
        samples = (
            [raw["workstation_memory"]["peak_commit_bytes"]]
            if row["coordinate"][0].startswith("memory:")
            else raw["samples"]
        )
        checks.append(
            dict(
                id="measurement:" + row["slot"],
                status="passed",
                details=dict(
                    coordinate=row["coordinate"],
                    lane=row["lane"],
                    purpose=row["purpose"],
                    terminal_sha256=row["terminal_sha256"],
                    samples=samples,
                    control_samples=raw["control_samples"],
                ),
            )
        )
    size = next(
        row
        for row in payload["reconstruction"]["decisions"]
        if row["coordinate"][0] == "size:kernel-artifacts"
    )
    checks.append(
        dict(
            id="measurement:size:kernel-artifacts",
            status="passed",
            details=dict(
                samples=[size["sizes"][lane] for lane in ("reference", "candidate")],
                control_samples=[],
            ),
        )
    )
    operations = {op["id"]: op for op in manifest["operations"]}
    for row in payload["reconstruction"]["decisions"]:
        enforced = operations[row["coordinate"][0]]["enforcement"] == "hard"
        checks.append(
            dict(
                id="comparison:"
                + "/".join(x or "fixture-free" for x in row["coordinate"]),
                status="passed" if row["passed"] or not enforced else "failed",
                details=dict(
                    decision=row,
                    enforcement=operations[row["coordinate"][0]]["enforcement"],
                ),
            )
        )
    checks.extend(payload["resources"])
    checks.append(
        dict(
            id="controlled:actual-double-work",
            status="passed"
            if payload["reconstruction"]["negative_control"]["passed"] is False
            else "failed",
            details=payload["reconstruction"]["negative_control"],
        )
    )
    return checks


def certify(
    profile,
    *,
    root=legacy.ROOT,
    execution_ledger=None,
    preflight_only=False,
    authority=legacy,
):
    legacy = authority
    policy = score.load_policy(root / "governance/workstation-performance-policy.json")
    manifest = legacy.load_json(root / legacy.MANIFEST_PATH.relative_to(legacy.ROOT))
    if preflight_only:
        raise legacy.PerformanceResourceError(
            "workstation-preflight",
            "Use complete fresh acquisition; workstation policy has no quiet-window admission.",
        )
    if profile != "full":
        result = legacy.certify(profile, root=root, execution_ledger=execution_ledger)
        checks = result["checks"] + [
            dict(
                id=METHOD_CHECK,
                status="passed",
                details=dict(
                    contract="shared-workstation-policy-contract-v2",
                    policy_id=policy["policy_id"],
                    policy_revision=policy["policy_revision"],
                    policy_sha256=campaign.digest(
                        root / "governance/workstation-performance-policy.json"
                    ),
                    live_measurement=False,
                    scope=policy["scope"],
                ),
            )
        ]
        return legacy._certification_evidence(
            profile=profile, commit=result["commit"], checks=checks, manifest=manifest
        )
    # A fresh directory and three independent builds are mandatory on every run,
    # including the independent Release invocation. Never load an earlier cohort.
    directory = acquisition_directory(root)
    directory.parent.mkdir(exist_ok=True)
    rust = Path(
        os.environ.get(
            "STRLING_PERFORMANCE_RUSTC",
            str(
                Path(os.environ["USERPROFILE"])
                / ".rustup/toolchains/1.75.0-x86_64-pc-windows-msvc/bin/rustc.exe"
            ),
        )
    )
    cargo = Path(
        os.environ.get("STRLING_PERFORMANCE_CARGO", str(rust.with_name("cargo.exe")))
    )
    terminal = campaign.acquire(
        root, directory, cargo=cargo, rustc=rust, execution_ledger=execution_ledger
    )
    commit, dirty = legacy._git_identity(root)
    if dirty or commit != terminal["source_sha"]:
        raise legacy.PerformanceResourceError(
            "workstation-source", "source changed during acquisition"
        )
    if (
        not (directory / "cohort.json").is_file()
        or not (directory / "independent-reconstruction.json").is_file()
    ):
        raise legacy.PerformanceResourceError(
            "workstation-acquisition", json.dumps(terminal, sort_keys=True)
        )
    payload = campaign_payload(directory)
    return legacy._certification_evidence(
        profile=profile,
        commit=commit,
        checks=checks_from_payload(payload, manifest),
        manifest=manifest,
    )
