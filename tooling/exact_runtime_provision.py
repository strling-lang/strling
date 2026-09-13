#!/usr/bin/env python3
"""Provision the immutable Linux runtime set used by empirical certification.

Network access is confined to this setup command. Certification operations are
offline and consume only paths that this command has hash- and identity-checked.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tooling.exact_runtime_toolchains import (
    EXPECTED_KEYS,
    ExactRuntimeToolchainError,
    file_sha256,
    load_manifest,
    verify_configured_runtimes,
)

OWNED_ROOT = Path("/opt/strling-toolchains")
ROOT = Path(__file__).resolve().parents[1]
JVM_RELEASE_GRAPH = ROOT / "tests/adapters/3.0/release-graph.json"
GRADLE_VERIFICATION_METADATA = ROOT / "bindings/kotlin/gradle/verification-metadata.xml"


class ExactRuntimeProvisionError(ValueError):
    """The governed runtime set could not be reconstructed safely."""


def _run(command: Sequence[str], *, cwd: Path | None = None, env=None) -> None:
    try:
        subprocess.run(
            list(command),
            cwd=cwd,
            env=env,
            check=True,
            timeout=1800,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ExactRuntimeProvisionError(
            f"runtime provisioning command failed: {' '.join(command)}"
        ) from error


def _record_path(record: Mapping[str, Any]) -> Path:
    return Path(str(record["layout"]["absolute_path"]))


def runtime_environment(manifest: Mapping[str, Any]) -> dict[str, str]:
    """Return the canonical environment handoff in stable key order."""

    return {
        str(manifest["toolchains"][key]["environment"]): str(
            manifest["toolchains"][key]["layout"]["absolute_path"]
        )
        for key in EXPECTED_KEYS
    }


def pull_request_environment(manifest: Mapping[str, Any]) -> dict[str, str]:
    """Return the supported deterministic Pull Request environment handoff."""

    environment = runtime_environment(manifest)
    environment.update(
        {
            "JAVA_HOME": os.environ.get("JAVA_HOME", "/opt/temurin-11.0.32+9"),
            "STRLING_MAVEN_REPOSITORY": os.environ.get(
                "STRLING_MAVEN_REPOSITORY",
                str(Path.home() / ".m2" / "repository"),
            ),
        }
    )
    return environment


def _verification_hashes(path: Path = GRADLE_VERIFICATION_METADATA) -> dict[str, str]:
    hashes: dict[str, str] = {}
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise ExactRuntimeProvisionError(
            f"cannot read JVM verification metadata: {path}: {error}"
        ) from error
    for component in root.findall(".//{*}component"):
        group = component.get("group")
        name = component.get("name")
        version = component.get("version")
        if not all((group, name, version)):
            continue
        for artifact in component.findall("{*}artifact"):
            artifact_name = artifact.get("name")
            sha = artifact.find("{*}sha256")
            if artifact_name and sha is not None and sha.get("value"):
                hashes[f"{group}:{name}:{version}:{artifact_name}"] = str(
                    sha.get("value")
                )
    return hashes


def _maven_jar(repository: Path, coordinate: str) -> Path:
    group, name, version = coordinate.split(":")
    return (
        repository / Path(*group.split(".")) / name / version / f"{name}-{version}.jar"
    )


def verify_maven_repository(
    repository: Path,
    *,
    release_graph_path: Path = JVM_RELEASE_GRAPH,
    verification_metadata_path: Path = GRADLE_VERIFICATION_METADATA,
    run: Any = subprocess.run,
) -> dict[str, Any]:
    """Verify the declared offline Maven cache against existing JVM authority."""

    repository = repository.resolve()
    if not repository.is_dir():
        raise ExactRuntimeProvisionError(
            f"STRLING_MAVEN_REPOSITORY is not a directory: {repository}"
        )
    try:
        graph = json.loads(release_graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ExactRuntimeProvisionError(
            f"cannot read JVM release graph: {release_graph_path}: {error}"
        ) from error
    roots = graph.get("roots", {}).get("jvm")
    packages = graph.get("packages")
    if not isinstance(roots, list) or not isinstance(packages, list):
        raise ExactRuntimeProvisionError("JVM release graph is malformed")
    external = {
        package.get("coordinate")
        for package in packages
        if isinstance(package, dict) and package.get("internal") is False
    }
    coordinates = sorted(
        coordinate
        for coordinate in roots
        if isinstance(coordinate, str) and coordinate in external
    )
    expected_hashes = _verification_hashes(verification_metadata_path)
    verified: dict[str, str] = {}
    for coordinate in coordinates:
        jar = _maven_jar(repository, coordinate)
        key = f"{coordinate}:{jar.name}"
        expected = expected_hashes.get(key)
        if expected is None:
            raise ExactRuntimeProvisionError(
                f"JVM dependency has no governed SHA-256: {coordinate}"
            )
        if not jar.is_file():
            raise ExactRuntimeProvisionError(
                f"Maven repository is missing {coordinate}: {jar}"
            )
        observed = file_sha256(jar)
        if observed != expected:
            raise ExactRuntimeProvisionError(
                f"Maven repository artifact SHA-256 differs: {coordinate}"
            )
        verified[coordinate] = observed
    bridge = _maven_jar(repository, "com.strling:strling-jvm:3.0.0")
    if not bridge.is_file():
        raise ExactRuntimeProvisionError(
            "Maven repository is missing prepared com.strling:strling-jvm:3.0.0"
        )
    maven = shutil.which("mvn")
    if maven is None:
        raise ExactRuntimeProvisionError("mvn is unavailable")
    command = [
        maven,
        "-o",
        "-B",
        "-q",
        f"-Dmaven.repo.local={repository}",
        "-DskipTests",
        "test-compile",
    ]
    try:
        completed = run(
            command,
            cwd=ROOT / "bindings/jvm",
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ExactRuntimeProvisionError(
            f"offline Maven repository probe failed to execute: {error}"
        ) from error
    if completed.returncode != 0:
        diagnostics = (completed.stderr.strip() or completed.stdout.strip())[-4000:]
        raise ExactRuntimeProvisionError(
            "offline Maven repository probe failed: " + diagnostics
        )
    return {
        "path": str(repository),
        "release_graph_fingerprint": graph.get("fingerprint"),
        "verified_artifacts": verified,
        "prepared_bridge": "com.strling:strling-jvm:3.0.0",
        "offline_probe": command,
    }


def verify_pull_request_environment(
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Fail before a Pull Request profile if its exact inputs are unavailable."""

    exact = verify_configured_runtimes(manifest or load_manifest())
    repository = os.environ.get("STRLING_MAVEN_REPOSITORY")
    if not repository:
        raise ExactRuntimeProvisionError("STRLING_MAVEN_REPOSITORY is not configured")
    return {
        "status": "passed",
        "exact_runtimes": exact,
        "maven_repository": verify_maven_repository(Path(repository)),
    }


def _download(source: Mapping[str, Any], downloads: Path) -> Path:
    archive = downloads / str(source["archive"])
    expected = str(source["sha256"])
    if archive.is_file() and file_sha256(archive) == expected:
        return archive
    downloads.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=downloads, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with urllib.request.urlopen(str(source["url"]), timeout=120) as response:
            with temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
        if file_sha256(temporary) != expected:
            raise ExactRuntimeProvisionError(
                f"source archive SHA-256 differs: {source['archive']}"
            )
        temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)
    return archive


def _extract(archive: Path, destination: Path) -> None:
    if destination.exists() and (
        not destination.is_dir() or any(destination.iterdir())
    ):
        raise ExactRuntimeProvisionError(
            f"partial governed source or runtime already exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as bundle:
        roots = {Path(member.name).parts[0] for member in bundle.getmembers()}
        if len(roots) != 1 or "" in roots or "." in roots or ".." in roots:
            raise ExactRuntimeProvisionError("source archive root is malformed")
        bundle.extractall(destination.parent, filter="data")
    extracted = destination.parent / next(iter(roots))
    if extracted != destination:
        extracted.rename(destination)


def _provision_node(record: Mapping[str, Any], downloads: Path) -> None:
    executable = _record_path(record)
    if executable.is_file():
        return
    archive = _download(record["source"], downloads)
    _extract(archive, executable.parents[1])


def _provision_python(record: Mapping[str, Any], downloads: Path) -> None:
    executable = _record_path(record)
    if executable.is_file():
        return
    archive = _download(record["source"], downloads)
    source = OWNED_ROOT / "sources" / "Python-3.11.15"
    build = OWNED_ROOT / "build" / "cpython-3.11.15"
    _extract(archive, source)
    if build.exists():
        raise ExactRuntimeProvisionError(f"partial governed build exists: {build}")
    build.mkdir(parents=True)
    environment = dict(os.environ)
    environment.update(
        {
            "CFLAGS": str(record["build"]["cflags"]),
            "SOURCE_DATE_EPOCH": str(record["build"]["source_date_epoch"]),
        }
    )
    _run(
        [str(source / "configure"), *record["build"]["configure"]],
        cwd=build,
        env=environment,
    )
    _run(["make", "-j2"], cwd=build, env=environment)
    _run(["make", "install"], cwd=build, env=environment)


def _provision_pcre2(key: str, record: Mapping[str, Any], sources: Path) -> None:
    library = _record_path(record)
    if library.is_file():
        return
    source = sources / key
    build = library.parent
    if source.exists() or (build.exists() and any(build.iterdir())):
        raise ExactRuntimeProvisionError(
            f"partial governed PCRE2 source/build exists for {key}"
        )
    source.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", str(source)])
    _run(
        [
            "git",
            "-C",
            str(source),
            "fetch",
            "--depth=1",
            str(record["source"]["repository"]),
            str(record["source"]["tag"]),
        ]
    )
    _run(["git", "-C", str(source), "checkout", "--detach", "FETCH_HEAD"])
    observed = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if observed != record["source"]["commit"]:
        raise ExactRuntimeProvisionError(f"{key} source commit differs")
    build.mkdir(parents=True, exist_ok=True)
    options = [
        f"-D{name}={value}" for name, value in record["build"]["options"].items()
    ]
    _run(["cmake", "-S", str(source), "-B", str(build), *options])
    _run(["cmake", "--build", str(build), "--parallel", "2"])


def provision(manifest: Mapping[str, Any]) -> dict[str, Any]:
    if os.name != "posix" or Path("/opt").anchor != "/":
        raise ExactRuntimeProvisionError(
            "exact runtimes are governed for Ubuntu 24.04 x86_64"
        )
    OWNED_ROOT.mkdir(parents=True, exist_ok=True)
    downloads = OWNED_ROOT / "downloads"
    toolchains = manifest["toolchains"]
    for key in EXPECTED_KEYS:
        record = toolchains[key]
        path = _record_path(record)
        if path.is_file() and file_sha256(path) != record["artifact"]["sha256"]:
            raise ExactRuntimeProvisionError(
                f"cached {key} artifact SHA-256 differs; discard that cache entry"
            )
        if key.startswith("node-"):
            _provision_node(record, downloads)
        elif key.startswith("cpython-"):
            _provision_python(record, downloads)
        else:
            _provision_pcre2(key, record, OWNED_ROOT / "sources")
    environment = runtime_environment(manifest)
    os.environ.update(environment)
    return verify_configured_runtimes(manifest)


def write_environment(path: Path, environment: Mapping[str, str]) -> None:
    for name, value in environment.items():
        if "\n" in name or "\r" in name or "=" in name:
            raise ExactRuntimeProvisionError("runtime variable name is malformed")
        if "\n" in value or "\r" in value:
            raise ExactRuntimeProvisionError("runtime path contains a line ending")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        for name, value in sorted(environment.items()):
            stream.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provision", action="store_true")
    parser.add_argument("--github-env", type=Path)
    parser.add_argument("--print-env", action="store_true")
    parser.add_argument("--print-pull-request-env", action="store_true")
    parser.add_argument("--check-pull-request", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--execute-adversarial",
        action="store_true",
        help="run the governed strict real-engine equivalence check after verification",
    )
    parser.add_argument(
        "--evidence-output",
        type=Path,
        default=Path("artifacts/adversarial-semantic-runtime/evidence.json"),
    )
    args = parser.parse_args()
    manifest = load_manifest()
    environment = runtime_environment(manifest)
    if args.print_pull_request_env:
        for name, value in sorted(pull_request_environment(manifest).items()):
            print(f"export {name}={shlex.quote(value)}")
        return 0
    if args.check_pull_request:
        try:
            result = verify_pull_request_environment(manifest)
        except (ExactRuntimeProvisionError, ExactRuntimeToolchainError) as error:
            print(f"Pull Request exact environment: FAILED: {error}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, sort_keys=True))
        else:
            print("Pull Request exact environment: PASSED")
        return 0
    if args.provision:
        result = provision(manifest)
    else:
        os.environ.update(environment)
        try:
            result = verify_configured_runtimes(manifest)
        except ExactRuntimeToolchainError as error:
            raise ExactRuntimeProvisionError(str(error)) from error
    if args.github_env is not None:
        write_environment(args.github_env, environment)
    if args.execute_adversarial:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tooling.adversarial_semantic_audit",
                "--strict",
                "--json",
                "--output",
                str(args.evidence_output),
            ],
            check=False,
            env=os.environ,
        )
        return completed.returncode
    if args.print_env:
        for name, value in sorted(environment.items()):
            print(f"export {name}={value}")
    else:
        print(
            "Exact governed runtimes: PASSED "
            f"({len(result['toolchains'])}/{len(EXPECTED_KEYS)})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
