"""Prepare only pinned Kotlin compiler dependencies in a fresh credential-free cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

from tooling.release_consumers import public_consumer_environment, run_consumer


def prepare_jvm(harness: Path, output: Path) -> dict:
    from tooling.jvm_adapter_package import EXTERNAL_PACKAGES
    from tooling.public_retrieval import PublicTransport, RetrievalError

    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    metadata = harness / "bindings/kotlin/gradle/verification-metadata.xml"
    verification = ET.parse(metadata).getroot()
    for element in verification.iter():
        element.tag = element.tag.split("}")[-1]
    transport = PublicTransport(output / "responses", {"https://repo1.maven.org"})
    dependencies = {}
    for coordinate, version, _ in EXTERNAL_PACKAGES:
        group, name = coordinate.split(":")
        filename = name + "-" + version + ".jar"
        component = next(
            row
            for row in verification.iter("component")
            if row.attrib == {"group": group, "name": name, "version": version}
        )
        accepted = {
            sha.get("value")
            for row in component.findall("artifact")
            if row.get("name") == filename
            for sha in row.findall("sha256")
        }
        relative = Path(*group.split(".")) / name / version / filename
        payload = transport.get(
            "https://repo1.maven.org/maven2/" + relative.as_posix(),
            maximum=64 * 1024 * 1024,
        )
        digest = hashlib.sha256(payload).hexdigest()
        if digest not in accepted:
            raise RetrievalError(
                "dependency-resolution",
                "JVM runtime differs from reviewed dependency lock",
            )
        target = output / "repository" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        dependencies[coordinate + ":" + version] = digest
    receipt = {
        "status": "passed",
        "purpose": "runtime-prerequisite-only",
        "strling_packages": [],
        "verification_metadata_sha256": hashlib.sha256(
            metadata.read_bytes()
        ).hexdigest(),
        "dependencies": dependencies,
        "repository": str(output / "repository"),
        "publication_authorized": False,
    }
    (output / "receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    return receipt


def prepare_dart(harness: Path, output: Path) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    environment = public_consumer_environment(output, dict(os.environ))
    environment["PUB_CACHE"] = str(output / "dependency-cache")
    source_lock = harness / "bindings/dart/pubspec.lock"
    lock = yaml.safe_load(source_lock.read_text(encoding="utf-8"))
    package = yaml.safe_load(
        (harness / "bindings/dart/pubspec.yaml").read_text(encoding="utf-8")
    )
    names = set(package["dependencies"])
    selected = {name: lock["packages"][name] for name in names}
    if any(
        row["source"] != "hosted" or row["description"]["url"] != "https://pub.dev"
        for row in selected.values()
    ):
        raise ValueError(
            "Dart consumer prerequisites require governed public hosted locks"
        )
    project = output / "sdk-project"
    project.mkdir()
    (project / "pubspec.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "strling_consumer_prerequisites",
                "environment": package["environment"],
                "dependencies": {
                    name: row["version"] for name, row in selected.items()
                },
            }
        ),
        encoding="utf-8",
    )
    (project / "pubspec.lock").write_text(
        yaml.safe_dump({"packages": selected, "sdks": lock["sdks"]}), encoding="utf-8"
    )
    log = run_consumer(
        ["dart", "pub", "get", "--enforce-lockfile"], project, environment
    )
    (output / "preparation.log").write_text(log, encoding="utf-8")
    receipt = {
        "purpose": "runtime-prerequisite-only",
        "status": "passed",
        "strling_packages": [],
        "lock_sha256": hashlib.sha256(source_lock.read_bytes()).hexdigest(),
        "dependencies": selected,
        "pub_cache": environment["PUB_CACHE"],
        "publication_authorized": False,
    }
    (output / "receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    return receipt


def prepare_kotlin(harness: Path, output: Path) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    environment = public_consumer_environment(output, dict(os.environ))
    environment["GRADLE_USER_HOME"] = str(output / "dependency-cache")
    project = output / "sdk-project"
    project.mkdir()
    (project / "settings.gradle.kts").write_text(
        'rootProject.name="IndependentConsumerSDK"\n', encoding="utf-8"
    )
    (project / "build.gradle.kts").write_text(
        'plugins { kotlin("jvm") version "2.0.20" }\nrepositories { mavenCentral() }\n',
        encoding="utf-8",
    )
    source = project / "src/main/kotlin/Prerequisite.kt"
    source.parent.mkdir(parents=True)
    source.write_text('fun main() { println("SDK qualification") }\n', encoding="utf-8")
    (project / "gradle").mkdir()
    metadata = harness / "bindings/kotlin/gradle/verification-metadata.xml"
    shutil.copyfile(metadata, project / "gradle/verification-metadata.xml")
    wrapper = (
        harness / "bindings/kotlin" / ("gradlew.bat" if os.name == "nt" else "gradlew")
    )
    log = run_consumer(
        [
            str(wrapper.resolve()),
            "--no-daemon",
            "--dependency-verification",
            "strict",
            "compileKotlin",
        ],
        project,
        environment,
    )
    (output / "preparation.log").write_text(log, encoding="utf-8")
    receipt = {
        "purpose": "compiler-prerequisite-only",
        "status": "passed",
        "strling_packages": [],
        "verification_metadata_sha256": hashlib.sha256(
            metadata.read_bytes()
        ).hexdigest(),
        "gradle_cache": environment["GRADLE_USER_HOME"],
        "publication_authorized": False,
    }
    (output / "receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--ecosystem", choices=("kotlin", "dart", "jvm"), default="kotlin"
    )
    args = parser.parse_args()
    prepare = {"kotlin": prepare_kotlin, "dart": prepare_dart, "jvm": prepare_jvm}[
        args.ecosystem
    ]
    print(json.dumps(prepare(args.harness, args.output)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
