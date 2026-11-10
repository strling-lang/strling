"""Compare registry descriptions with the authenticated release source as data."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from tooling.public_retrieval import RetrievalError
from tooling.release_payload import unique_yaml


def compare_fields(actual: dict, expected: dict) -> dict:
    for key, value in expected.items():
        if actual.get(key) != value:
            raise RetrievalError(
                "metadata",
                "public metadata differs from certified value: " + key,
                expected={key: value},
                observed={key: actual.get(key)},
            )
    return {"status": "passed", "fields": sorted(expected)}


def verify_registry_metadata(artifact: dict, metadata: dict, source: Path) -> dict:
    """Source is the independently authenticated clean implementation checkout.

    Archive metadata is separately authenticated by its complete signed file graph.
    These checks additionally reject divergent registry-visible descriptions.
    """
    registry = artifact["registry"]
    if registry == "pypi.org":
        project = tomllib.loads(
            (source / "bindings/python/pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        return compare_fields(
            metadata["info"],
            {
                "name": project["name"],
                "version": project["version"],
                "summary": project["description"],
                "license_expression": project["license"],
                "requires_python": ",".join(
                    sorted(project["requires-python"].split(","))
                ),
                "project_urls": project["urls"],
            },
        )
    if registry == "npmjs.org":
        package = json.loads(
            (source / "bindings/typescript/package.json").read_text(encoding="utf-8")
        )
        keys = (
            "name",
            "version",
            "description",
            "license",
            "homepage",
            "repository",
            "engines",
            "dependencies",
            "exports",
            "type",
        )
        return compare_fields(metadata, {key: package.get(key) for key in keys})
    if registry == "crates.io":
        package = tomllib.loads((source / "Cargo.toml").read_text(encoding="utf-8"))[
            "package"
        ]
        return compare_fields(
            metadata["version"],
            {
                "crate": package["name"],
                "num": package["version"],
                "license": package["license"],
                "rust_version": package["rust-version"],
                "description": package["description"],
                "homepage": package["homepage"],
                "repository": package["repository"],
                "documentation": package["documentation"],
            },
        )
    if registry == "pub.dev":
        package = unique_yaml((source / "bindings/dart/pubspec.yaml").read_bytes())
        return compare_fields(
            metadata["pubspec"],
            {
                key: package[key]
                for key in (
                    "name",
                    "version",
                    "description",
                    "repository",
                    "environment",
                    "dependencies",
                )
            },
        )
    if registry == "rubygems.org":
        text = (source / "bindings/ruby/strling.gemspec").read_text(encoding="utf-8")

        def field(name):
            found = re.findall(
                r"(?m)^\s*s\." + name + r"\s*=\s*(['\"])(.*?)\1\s*$", text
            )
            if len(found) != 1:
                raise RetrievalError("contract", "ambiguous certified Ruby metadata")
            return found[0][1]

        return compare_fields(
            metadata,
            {
                "name": field("name"),
                "info": field("description"),
                "homepage_uri": field("homepage"),
                "licenses": [field("license")],
                "source_code_uri": "https://github.com/strling-lang/strling",
            },
        )
    if registry == "cpan":
        return compare_fields(
            metadata,
            {"distribution": artifact["package_name"], "license": ["apache_2_0"]},
        )
    # These protocols expose immutable source/package metadata directly. Their
    # complete certified graph is checked before a metadata obligation can pass.
    if registry.startswith("github-tag:") or registry in {
        "maven-central",
        "nuget.org",
        "conan",
        "luarocks.org",
    }:
        return {"status": "requires-authenticated-payload-metadata", "fields": []}
    raise RetrievalError("contract", "metadata adapter is missing")


def verify_documented_coordinate(command: str, artifact: dict, version: str) -> dict:
    """Inspect a documented command as text; never execute downloaded prose."""
    if any(
        character in command
        for character in ("\x00", "\r", "\n", "`", ";", "|", "$", ">", "<")
    ):
        raise RetrievalError(
            "documentation", "installation command contains untrusted shell syntax"
        )
    name = artifact["package_name"]
    registry = artifact["registry"]
    patterns = {
        "pypi.org": rf"(?:python(?:3)? -m )?pip install {re.escape(name)}=={re.escape(version)}",
        "npmjs.org": rf"npm install {re.escape(name)}@{re.escape(version)}",
        "crates.io": rf"cargo add {re.escape(name)}@={re.escape(version)}",
        "nuget.org": rf"dotnet add package {re.escape(name)} --version {re.escape(version)}",
        "pub.dev": rf"dart pub add {re.escape(name)}:{re.escape(version)}",
        "rubygems.org": rf"gem install {re.escape(name)} --version {re.escape(version)}",
        "luarocks.org": rf"luarocks install {re.escape(name)} {re.escape(version)}-1",
    }
    if registry in patterns:
        valid = re.fullmatch(patterns[registry], command.strip()) is not None
    elif registry.startswith("github-tag:"):
        tag = registry.removeprefix("github-tag:").replace("VERSION", version)
        valid = (
            command.strip() == "go get " + name + "@" + tag
            if artifact["id"] == "release:go"
            else (
                command.strip()
                == "git clone --branch "
                + tag
                + " --single-branch https://github.com/strling-lang/strling.git"
            )
        )
    elif registry == "maven-central":
        valid = (
            command.strip()
            == "mvn dependency:get -Dartifact="
            + name
            + ":"
            + version
            + " -DremoteRepositories=https://repo1.maven.org/maven2"
        )
    elif registry == "cpan":
        valid = command.strip() == "cpanm " + name + "@" + version
    elif registry == "conan":
        valid = (
            command.strip()
            == "conan install --requires=" + name + "/" + version + " --build=never"
        )
    else:
        valid = False
    if not valid:
        raise RetrievalError(
            "documentation",
            "documented installation coordinate differs from the exact public release",
        )
    return {"status": "passed", "command": command, "executed": False}


def verify_readme_commands(payload: bytes, artifact: dict, version: str) -> dict:
    """Validate actual installation lines; prose is never a command authority."""
    text = payload.decode("utf-8")
    commands = []
    fence = False
    prefixes = (
        "pip install ",
        "python -m pip install ",
        "python3 -m pip install ",
        "npm install ",
        "cargo add ",
        "dotnet add package ",
        "dart pub add ",
        "gem install ",
        "luarocks install ",
        "go get ",
        "git clone ",
        "mvn dependency:get ",
        "cpanm ",
        "conan install ",
    )
    for line in text.splitlines():
        if line.strip().startswith("```"):
            fence = not fence
            continue
        if fence and line.strip().startswith(prefixes):
            commands.append(
                verify_documented_coordinate(line.strip(), artifact, version)
            )
    return {
        "status": "passed",
        "commands": commands,
        "exact_install_commands_found": len(commands),
        "execution_authority": "trusted-clean-consumer-contract",
    }
