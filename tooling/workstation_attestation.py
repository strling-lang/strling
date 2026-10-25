"""Verifier-owned workstation attestation reconstruction.

Candidate content is data. Helper callbacks and Git reads belong to the pinned
trusted verifier. No candidate module or executable is imported or run.
"""

import base64
import hashlib
import io
from pathlib import PurePosixPath, PureWindowsPath
import re
import subprocess
import zipfile

HARNESS = "tests/certification/performance-resource/1.0/runner"


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def decoded(value):
    need(
        type(value) is str and len(value) <= 96 * 1024 * 1024, "bounded encoded stream"
    )
    return base64.b64decode(value, validate=True)


def archive_catalog(data):
    need(
        type(data) is bytes and len(data) <= 32 * 1024 * 1024, "bounded source archive"
    )
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        need(
            len(entries) <= 10000
            and sum(x.file_size for x in entries) <= 64 * 1024 * 1024,
            "source archive expansion bound",
        )
        result = {}
        names = set()
        for entry in entries:
            path = PurePosixPath(entry.filename)
            need(
                entry.orig_filename == entry.filename
                and not path.is_absolute()
                and ".." not in path.parts
                and "\\" not in entry.filename
                and ":" not in entry.filename,
                "source archive path",
            )
            need(entry.filename not in names, "duplicate archive entry")
            names.add(entry.filename)
            need(
                (entry.external_attr >> 16) & 0o170000 != 0o120000,
                "source archive link",
            )
            if not entry.is_dir():
                result[entry.filename] = archive.read(entry)
    return result


def git_catalog(root, revision):
    need(
        type(revision) is str and re.fullmatch("[0-9a-f]{40}", revision),
        "exact source revision",
    )
    done = subprocess.run(
        ["git", "--no-optional-locks", "archive", "--format=zip", revision],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120,
    )
    need(done.returncode == 0, "trusted source archive read failed")
    return archive_catalog(done.stdout)


def validate_builds(payload, *, root, source_sha, policy, parse):
    catalogs = {
        revision: git_catalog(root, revision)
        for revision in {source_sha, policy["reference_source"]}
    }
    candidate = catalogs[source_sha]
    expected_harness = {
        PurePosixPath(name).name: sha(data)
        for name, data in candidate.items()
        if PurePosixPath(name).parent.as_posix() == HARNESS + "/src"
        and name.endswith(".rs")
    }
    builds = {}
    used_archives = set()
    toolchains = set()
    for lane in ("reference", "candidate", "slowdown"):
        data = payload["builds"][lane]
        recipe_bytes = decoded(data["recipe_bytes"])
        recipe, built = parse(recipe_bytes), data["built"]
        revision = policy["reference_source"] if lane == "reference" else source_sha
        build = PureWindowsPath(built["build_root"])
        need(build.is_absolute(), "absolute build root")
        archive_pin = recipe["source_archive_sha256"]
        used_archives.add(archive_pin)
        archive_bytes = decoded(payload["source_archives"][archive_pin])
        need(sha(archive_bytes) == archive_pin, "source archive byte pin")
        actual = archive_catalog(archive_bytes)
        need(
            not any(
                name.startswith(("core/internal/target/", "bindings/interop/target/"))
                for name in actual
            ),
            "no archived compiled objects",
        )
        need(actual == catalogs[revision], "source archive differs from Git source")
        need(
            recipe["kernel_source_files"]
            == {name: sha(content) for name, content in actual.items()},
            "complete source catalog",
        )
        need(
            recipe["kernel_revision"] == built["kernel_revision"] == revision,
            "kernel source revision",
        )
        need(recipe["mixed_source_build"] is True, "explicit mixed-source recipe")
        need(
            recipe["negative_control"]
            is built["negative_control"]
            is (lane == "slowdown"),
            "build role",
        )
        need(
            recipe["harness_source_sha256"] == expected_harness,
            "actual candidate harness source",
        )
        need(
            recipe["harness_manifest_source_sha256"]
            == sha(candidate[HARNESS + "/Cargo.toml"]),
            "harness manifest source",
        )
        need(
            recipe["cargo_lock_sha256"] == sha(candidate[HARNESS + "/Cargo.lock"]),
            "exact harness dependency lock",
        )
        manifest = candidate[HARNESS + "/Cargo.toml"].decode("utf-8")
        for original, relative in [
            ("../../../../../bindings/interop", "bindings/interop"),
            ("../../../../../core/internal", "core/internal"),
            ("../../../../../", ""),
        ]:
            needle = 'path = "' + original + '"'
            need(manifest.count(needle) == 1, "reviewed dependency layout")
            manifest = manifest.replace(
                needle, 'path = "' + (build / "source" / relative).as_posix() + '"'
            )
        need(
            decoded(data["manifest_bytes"])
            == manifest.replace("\n", "\r\n").encode("utf-8"),
            "materialized manifest bytes",
        )
        need(
            recipe["materialized_manifest_sha256"]
            == sha(manifest.replace("\n", "\r\n").encode("utf-8")),
            "materialized manifest pin",
        )
        need(
            built["recipe_sha256"] == sha(recipe_bytes) and built["status"] == "passed",
            "completed exact build recipe",
        )
        flags = [
            f"--remap-path-prefix={build}=C:/strling-workstation-build",
            "-C",
            "link-arg=/Brepro",
            "-C",
            "link-arg=/PDBALTPATH:%_PDB%",
        ]
        need(recipe["rust_flags"] == flags, "reviewed build flags")
        toolchains.add((recipe["cargo_sha256"], recipe["rustc_sha256"]))
        commands = {
            "harness-build": [
                "build",
                "--release",
                "--locked",
                "--offline",
                "--manifest-path",
                str(build / "harness/Cargo.toml"),
                "--target-dir",
                str(build / "harness/target"),
                "--bins",
            ]
            + (
                ["--features", "workstation-slowdown-challenge"]
                if lane == "slowdown"
                else []
            ),
            "kernel-build": [
                "build",
                "--release",
                "--locked",
                "--offline",
                "--manifest-path",
                str(build / "source/core/internal/Cargo.toml"),
                "--target-dir",
                str(build / "source/core/internal/target"),
                "--bin",
                "strling-kernel",
            ],
            "interop-build": [
                "build",
                "--release",
                "--locked",
                "--offline",
                "--manifest-path",
                str(build / "source/bindings/interop/Cargo.toml"),
                "--target-dir",
                str(build / "source/bindings/interop/target"),
                "--lib",
            ],
        }
        need(set(data["steps"]) == set(commands), "complete build steps")
        for name, expected in commands.items():
            step = data["steps"][name]
            receipt = step["receipt"]
            need(
                type(receipt["exit_code"]) is int
                and receipt["exit_code"] == 0
                and receipt["command"][1:] == expected,
                "build command/exit",
            )
            need(
                PureWindowsPath(receipt["command"][0]).name == "cargo.exe",
                "native Cargo",
            )
            for channel in ("stdout", "stderr"):
                need(
                    receipt[channel + "_sha256"] == sha(decoded(step[channel])),
                    "raw build stream pin",
                )
        expected_paths = {
            "runner": build / "harness/target/release/strling-performance-runner.exe",
            "memory_worker": build
            / "harness/target/release/strling-performance-memory-worker.exe",
            "kernel": build / "source/core/internal/target/release/strling-kernel.exe",
            "interop": build
            / "source/bindings/interop/target/release/strling_interop.dll",
        }
        need(set(built["artifacts"]) == set(expected_paths), "four native artifacts")
        for name, path in expected_paths.items():
            artifact = built["artifacts"][name]
            need(
                artifact["path"] == str(path)
                and type(artifact["bytes"]) is int
                and artifact["bytes"] > 0
                and re.fullmatch("[0-9a-f]{64}", artifact["sha256"]),
                "native artifact identity",
            )
        builds[lane] = built
    need(len(toolchains) == 1, "same pinned toolchain across independent lanes")
    need(
        set(payload["source_archives"]) == used_archives,
        "complete unique archive denominator",
    )
    return builds


def validate_resources(resources, *, commands, cwd):
    need(
        type(resources) is list and [x["id"] for x in resources] == list(commands),
        "five resource groups in authority order",
    )
    for group in resources:
        need(group["status"] == "passed", "functional resource group")
        steps = group["details"]["steps"]
        need(len(steps) == len(commands[group["id"]]), "all resource steps")
        for step, expected in zip(steps, commands[group["id"]]):
            actual = list(step["command"])
            need(
                PureWindowsPath(actual[0]).name == "cargo.exe", "native resource Cargo"
            )
            actual[0] = "cargo"
            if actual[1] != "+1.75.0":
                actual.insert(1, "+1.75.0")
            need(
                actual
                == [
                    *expected,
                    "--target-dir",
                    str(
                        PureWindowsPath(cwd) / "target/rust-1.75-resource-certification"
                    ),
                ],
                "resource command source",
            )
            need(
                step["status"] == "passed"
                and type(step.get("return_code")) is int
                and step.get("return_code") == 0,
                "resource command exit",
            )


def reconstruct(
    payload,
    *,
    root,
    source_sha,
    expected_invocation,
    manifest,
    policy,
    implementation_pins,
    process_verifier,
    cohort_verifier,
    latency_scorer,
    memory_scorer,
    parse,
):
    need(
        payload["contract"] == "shared-workstation-profile-evidence-v2",
        "explicit profile policy contract",
    )
    prospective = payload["prospective_plan"]
    need(
        prospective["invocation"] == expected_invocation,
        "certification invocation provenance",
    )
    need(
        prospective["source_sha"] == source_sha and prospective["policy"] == policy,
        "prospective source/policy",
    )
    need(
        prospective["candidate_calibration"] is False
        and prospective["no_retries"] is True
        and prospective["full_coordinate_qualification"] is True,
        "full fixed prospective qualification",
    )
    operations = manifest["operations"]
    coordinates = [
        (op["id"], fixture)
        for op in operations
        if op["id"].startswith(("latency:", "memory:", "size:"))
        for fixture in (op["fixture_ids"] or [None])
    ]
    need(
        prospective["coordinates"] == [list(x) for x in coordinates],
        "governed coordinate plan",
    )
    pins = prospective["implementation_pins"]
    for key, value in implementation_pins.items():
        need(pins[key] == value, "reviewed implementation identity")
    need(
        PureWindowsPath(pins["cwd"]).is_absolute()
        and pins["timeout_seconds"] == 300
        and type(pins["timeout_seconds"]) is int,
        "native acquisition context",
    )
    need(
        type(pins["environment_sha256"]) is str
        and re.fullmatch("[0-9a-f]{64}", pins["environment_sha256"]),
        "environment observation pin",
    )
    builds = validate_builds(
        payload, root=root, source_sha=source_sha, policy=policy, parse=parse
    )
    result = cohort_verifier(
        payload["cohort"],
        coordinates=coordinates,
        expected_invocation=expected_invocation,
        policy=policy,
        source_sha=source_sha,
        policy_sha256=sha(
            catalog_bytes(
                root, source_sha, "governance/workstation-performance-policy.json"
            )
        ),
        manifest_sha256=sha(
            catalog_bytes(
                root,
                source_sha,
                "tests/certification/performance-resource/1.0/manifest.json",
            )
        ),
        build_identities=builds,
        implementation_pins=pins,
        process_verifier=process_verifier,
        latency_scorer=latency_scorer,
        memory_scorer=memory_scorer,
    )
    need(
        result == payload["reconstruction"],
        "independent complete decision reconstruction",
    )
    need(
        payload["terminal"]["source_unchanged"] is True
        and payload["terminal"]["status"] == "passed"
        and payload["terminal"]["hard_failures"] == [],
        "successful unchanged acquisition",
    )
    return result


def catalog_bytes(root, revision, path):
    done = subprocess.run(
        ["git", "--no-optional-locks", "show", revision + ":" + path],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    need(done.returncode == 0, "trusted Git blob unavailable")
    return done.stdout


def validate_native_memory(payload, *, root, source_sha, parse):
    native = payload["native_memory"]
    need(
        set(native) == {"native-memory-test-build", "native-memory-tests"},
        "native memory qualification steps",
    )
    cwd = PureWindowsPath(payload["prospective_plan"]["implementation_pins"]["cwd"])
    directory = PureWindowsPath(
        payload["builds"]["reference"]["built"]["build_root"]
    ).parent
    binary = directory / "native-memory-lifetime.exe"
    expected = {
        "native-memory-test-build": [
            "--edition=2021",
            "--test",
            str(cwd / "tooling/tests/memory_worker_lifetime.rs"),
            "-o",
            str(binary),
        ],
        "native-memory-tests": ["--test-threads=1", "--nocapture"],
    }
    for name, args in expected.items():
        step = native[name]
        receipt = step["receipt"]
        need(
            type(receipt["exit_code"]) is int
            and receipt["exit_code"] == 0
            and receipt["command"][1:] == args,
            "native qualification command",
        )
        need(
            PureWindowsPath(receipt["command"][0]).name
            == (
                "rustc.exe" if name.endswith("build") else "native-memory-lifetime.exe"
            ),
            "native qualification executable",
        )
        for channel in ("stdout", "stderr"):
            need(
                receipt[channel + "_sha256"] == sha(decoded(step[channel])),
                "native qualification stream",
            )
    text = decoded(native["native-memory-tests"]["stdout"]).decode("utf-8")
    need(
        "test result: ok. 18 passed; 0 failed; 5 ignored;" in text,
        "complete native memory qualification",
    )
    for label in [
        "workstation bytes=2097152 peak_commit=",
        "workstation bytes=100663296 peak_commit=",
        "restricted=false terminal=",
        "restricted=true terminal=",
        "terminal_peak_rss_bytes=",
    ]:
        need(label in text, "required native counterfactual trace")
    status = payload["terminal"]["native_memory_qualification"]
    need(
        status["status"] == "passed"
        and status["source_sha256"]
        == sha(
            catalog_bytes(root, source_sha, "tooling/tests/memory_worker_lifetime.rs")
        ),
        "native test source binding",
    )
    for channel in ("stdout", "stderr"):
        need(
            status[channel + "_sha256"]
            == sha(decoded(native["native-memory-tests"][channel])),
            "terminal native memory pin",
        )


def reconstructed_checks(payload, result, manifest, parse):
    # Deliberately reconstruct these projections here; do not import the producer.
    rows = [dict(id="method:shared-workstation-v1", status="passed", details=payload)]
    for observation in payload["cohort"]["observations"]:
        raw = parse(decoded(observation["files"]["stdout.bin"]))
        values = (
            [raw["workstation_memory"]["peak_commit_bytes"]]
            if observation["coordinate"][0].startswith("memory:")
            else raw["samples"]
        )
        rows.append(
            dict(
                id="measurement:" + observation["slot"],
                status="passed",
                details=dict(
                    coordinate=observation["coordinate"],
                    lane=observation["lane"],
                    purpose=observation["purpose"],
                    terminal_sha256=observation["terminal_sha256"],
                    samples=values,
                    control_samples=raw["control_samples"],
                ),
            )
        )
    size = next(
        row
        for row in result["decisions"]
        if row["coordinate"][0] == "size:kernel-artifacts"
    )
    rows.append(
        dict(
            id="measurement:size:kernel-artifacts",
            status="passed",
            details=dict(
                samples=[size["sizes"][lane] for lane in ("reference", "candidate")],
                control_samples=[],
            ),
        )
    )
    authority = {op["id"]: op for op in manifest["operations"]}
    for comparison in result["decisions"]:
        enforcement = authority[comparison["coordinate"][0]]["enforcement"]
        rows.append(
            dict(
                id="comparison:"
                + "/".join(x or "fixture-free" for x in comparison["coordinate"]),
                status="passed"
                if comparison["passed"] or enforcement != "hard"
                else "failed",
                details=dict(decision=comparison, enforcement=enforcement),
            )
        )
    rows.extend(payload["resources"])
    rows.append(
        dict(
            id="controlled:actual-double-work",
            status="passed"
            if result["negative_control"]["passed"] is False
            else "failed",
            details=result["negative_control"],
        )
    )
    return rows


def require_distinct_profile_campaigns(artifacts, parse, decode_payload):
    """Call only after each profile's full evidence has been reconstructed."""
    identities, build_roots, invocations = set(), set(), set()
    for artifact in artifacts:
        for operation in artifact["deterministic_evidence"]["operations"]:
            if operation["operation_id"] != "performance_resource_full_certification":
                continue
            structured = operation["structured_evidence"]
            payload = decode_payload(structured["checks"][0]["details"])
            need(
                structured["checks"][0]["id"] == "method:shared-workstation-v1",
                "named full policy",
            )
            invocation = payload["prospective_plan"]["invocation"]["invocation_id"]
            need(invocation not in invocations, "Full/Release invocation reused")
            invocations.add(invocation)
            roots = {
                build["built"]["build_root"] for build in payload["builds"].values()
            }
            need(not roots & build_roots, "Full/Release build roots reused")
            build_roots.update(roots)
            for row in payload["cohort"]["observations"]:
                files = {name: decoded(value) for name, value in row["files"].items()}
                root = parse(files["root-exit.json"])
                identity = (root["pid"], int(root["birth"]))
                need(identity not in identities, "Full/Release process reused")
                identities.add(identity)
                raw = parse(files["stdout.bin"])
                if row["coordinate"][0].startswith("memory:"):
                    child = raw["memory_lifetime"]
                    identity = (child["pid"], child["birth_100ns"])
                    need(identity not in identities, "Full/Release memory child reused")
                    identities.add(identity)
    return dict(
        invocations=len(invocations),
        unique_processes=len(identities),
        unique_build_roots=len(build_roots),
    )


def validate_profile_evidence(
    repository_root,
    source_sha,
    structured,
    integrity,
    *,
    authority,
    reader,
    score,
    process_reader,
):
    """Helpers are imported from the immutable verifier's own package by caller."""
    manifest = reader.parse(
        catalog_bytes(
            repository_root,
            source_sha,
            "tests/certification/performance-resource/1.0/manifest.json",
        )
    )
    policy = score.validate_policy(
        reader.parse(
            catalog_bytes(
                repository_root,
                source_sha,
                "governance/workstation-performance-policy.json",
            )
        )
    )
    authority.validate_evidence(structured, manifest=manifest)
    checks = structured["checks"]
    need(
        checks and checks[0]["id"] == "method:shared-workstation-v1",
        "named method first",
    )
    encoded_payload = checks[0]["details"]
    payload = reader.unpack_profile_payload(encoded_payload)
    expected_invocation = {
        key: integrity[key]
        for key in (
            "schema_version",
            "producer_id",
            "operation_id",
            "source_sha",
            "invocation_id",
            "certification_profile",
            "producer_profile",
        )
    }
    need(
        expected_invocation["source_sha"] == source_sha
        and expected_invocation["producer_profile"] == "full",
        "atomic invocation source/profile",
    )
    implementations = {
        key: sha(catalog_bytes(repository_root, source_sha, path))
        for key, path in {
            "implementation_sha256": "tooling/performance_process_envelope.py",
            "job_implementation_sha256": "tooling/performance_build_execution.py",
            "controls_implementation_sha256": "tooling/performance_windows.py",
            "observation_implementation_sha256": "tooling/performance_process_observation.py",
        }.items()
    }
    result = reconstruct(
        payload,
        root=repository_root,
        source_sha=source_sha,
        expected_invocation=expected_invocation,
        manifest=manifest,
        policy=policy,
        implementation_pins=implementations,
        process_verifier=process_reader.verify_process_receipt,
        cohort_verifier=reader.verify_cohort,
        latency_scorer=score.guarded_latency_decision,
        memory_scorer=score.memory_decision,
        parse=reader.parse,
    )
    validate_resources(
        payload["resources"],
        commands=authority.RESOURCE_COMMANDS,
        cwd=payload["prospective_plan"]["implementation_pins"]["cwd"],
    )
    validate_native_memory(
        payload, root=repository_root, source_sha=source_sha, parse=reader.parse
    )
    expected_checks = reconstructed_checks(payload, result, manifest, reader.parse)
    expected_checks[0]["details"] = encoded_payload
    need(checks == expected_checks, "complete independent check projection")
    need(
        all(row["status"] == "passed" for row in checks),
        "successful governed comparisons",
    )
    total = 2
    coordinate_ids = []
    size_recorded = False
    for row in payload["cohort"]["observations"]:
        if row["purpose"] == "negative-calibration" and not size_recorded:
            coordinate_ids.append("size:kernel-artifacts/fixture-free")
            size_recorded = True
        coordinate_ids.append(
            row["coordinate"][0]
            + "/"
            + row["slot"]
            + "/"
            + (row["coordinate"][1] or "fixture-free")
        )
        raw = reader.parse(decoded(row["files"]["stdout.bin"]))
        total += (
            1
            if row["coordinate"][0].startswith("memory:")
            else len(raw["samples"]) + len(raw["control_samples"])
        )
    need(size_recorded, "artifact-size ledger coordinate")
    expected_consumption = dict(
        state="consumed",
        authenticated_sample_count=total,
        completed_sample_count=total,
        coordinates_started=len(coordinate_ids),
        coordinates_completed=len(coordinate_ids),
        completed_coordinate_ids=coordinate_ids,
        current_coordinate_id=None,
    )
    need(
        integrity["sample_consumption"] == expected_consumption,
        "exact raw slot and size consumption ledger",
    )
    return dict(
        status="passed",
        observations=result["observations"],
        authenticated_samples=total,
    )
