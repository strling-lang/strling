"""Assemble governed release subjects without any publication capability.

This is the build adapter for release_supply_chain, not another certification
authority. Receipts, SBOMs, reproducibility, and approval stay with that producer.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tarfile
import uuid
import zipfile
import tomllib
import importlib.metadata
from pathlib import Path

from tooling.release_supply_chain import (
    MANIFEST_PATH,
    ROOT,
    ReleaseSupplyChainError,
    authenticate_source,
    load_json,
    _surface_members,
    inspect_release_payload,
    scoped_artifact,
    validate_manifest,
)
from tooling.sync_versions import get_source_version, projected_contents


def host_scope() -> str:
    system = {"Windows": "windows", "Linux": "linux"}.get(platform.system())
    if system is None or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise ReleaseSupplyChainError(
            "packaging-platform", "unregistered release build platform"
        )
    return system + "-x86_64"


def build_environment(root: Path, epoch: str, manifest: dict) -> dict[str, str]:
    environment = dict(os.environ)
    forbidden = {
        name
        for row in manifest["artifacts"]
        for name in row["credential_policy"]["secret_names"]
    }
    forbidden.update(
        {
            "GITHUB_TOKEN",
            "GH_TOKEN",
            "NODE_AUTH_TOKEN",
            "NPM_TOKEN",
            "CARGO_REGISTRY_TOKEN",
            "PIP_INDEX_URL",
            "PIP_EXTRA_INDEX_URL",
            "CARGO_TARGET_DIR",
            "CARGO_BUILD_TARGET",
            "RUSTC_WRAPPER",
            "RUSTC_WORKSPACE_WRAPPER",
            "RUSTC",
            "RUSTDOC",
            "CARGO_ENCODED_RUSTFLAGS",
            "CC",
            "CXX",
            "CMAKE_GENERATOR",
            "CMAKE_TOOLCHAIN_FILE",
            "LD_PRELOAD",
            "DYLD_INSERT_LIBRARIES",
            "STRLING_NATIVE_LIBRARY",
            "STRlingNativeLibrary",
            "STRLING_NATIVE_PATH",
        }
    )
    for name in list(environment):
        if (
            name in forbidden
            or name.startswith(("CARGO_PROFILE_", "CARGO_TARGET_", "CARGO_BUILD_"))
            or re.search(
                r"(?:TOKEN|PASSWORD|PASSPHRASE|PRIVATE_KEY|API_KEY)$", name, re.I
            )
        ):
            environment.pop(name)
    environment.update(
        TZ="UTC",
        LC_ALL="C",
        PYTHONHASHSEED="0",
        CARGO_INCREMENTAL="0",
        SOURCE_DATE_EPOCH=epoch,
    )
    environment["RUSTFLAGS"] = "--remap-path-prefix=" + str(root) + "=/strling"
    if os.name == "nt":
        environment["RUSTFLAGS"] += " -Clink-arg=/Brepro -Clink-arg=/DEBUG:NONE"
    environment["CFLAGS"] = (
        "" if os.name == "nt" else "-ffile-prefix-map=" + str(root) + "=/strling"
    )
    environment["CXXFLAGS"] = environment["CFLAGS"]
    environment["PIP_CONFIG_FILE"] = os.devnull
    return environment


def windows_cmake_toolset(root: Path) -> str:
    """Select the same installed MSVC toolset that the receipt authenticates."""
    from tooling.release_supply_chain import _probe_toolchain, document_fingerprint

    observed = _probe_toolchain(
        root,
        artifact_id="release:c",
        toolchain_id="cc",
        scope="windows-x86_64",
        policy_sha256=document_fingerprint(load_json(root / "toolchain.json")),
    )
    if observed["status"] != "passed":
        raise ReleaseSupplyChainError(
            "packaging-toolchain", "the registered MSVC compiler is unavailable"
        )
    return "v143,version=" + Path(observed["executable"]).parents[3].name


def staged_source(root: Path, relative: str, destination: Path) -> None:
    """Copy only tracked source; caches and developer outputs cannot leak in."""
    if destination.exists():
        raise ReleaseSupplyChainError(
            "packaging-stage", "staging directory already exists"
        )
    tracked = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "-z", "--", relative]
    )
    for raw in tracked.split(b"\0"):
        if not raw:
            continue
        path = Path(raw.decode("utf-8"))
        source = root / path
        if source.is_symlink() or not source.resolve().is_relative_to(root.resolve()):
            raise ReleaseSupplyChainError(
                "packaging-stage", "source staging forbids symlinks"
            )
        target = destination / path.relative_to(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    shutil.copyfile(root / "LICENSE", destination / "LICENSE")


def canonical_rust_archive(
    source: Path, destination: Path, *, version: str, epoch: int
) -> None:
    """Assemble one portable crate while preserving every Cargo payload byte.

    Cargo 1.75's host tar implementations use different fixed source timestamps.
    Canonical headers are build output, before capture or exact-byte publication;
    the registered byte-for-byte comparison admits no normalization.
    """
    from tooling.release_payload import archive_files

    if source.resolve() == destination.resolve() or not 0 <= epoch <= 0xFFFFFFFF:
        raise ReleaseSupplyChainError(
            "packaging-archive", "invalid crate output or epoch"
        )
    files = archive_files(source)
    prefix = "strling-" + version + "/"
    with tarfile.open(source, "r:gz") as archive:
        entries = archive.getmembers()
        if (
            not entries
            or any(
                not row.isfile() or row.mode not in (0o644, 0o755) for row in entries
            )
            or any(not name.startswith(prefix) for name in files)
            or len(entries) != len(files)
        ):
            raise ReleaseSupplyChainError(
                "packaging-archive", "crate contains an unregistered root, type or mode"
            )
        modes = {row.name: row.mode for row in entries}
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for name, data in sorted(files.items()):
            header = tarfile.TarInfo(name)
            header.size = len(data)
            header.mode = modes[name]
            header.mtime = epoch
            archive.addfile(header, io.BytesIO(data))
    with destination.open("wb") as output:
        with gzip.GzipFile(
            filename="", fileobj=output, mode="wb", mtime=epoch, compresslevel=9
        ) as archive:
            archive.write(stream.getvalue())
    if archive_files(destination) != files:
        raise ReleaseSupplyChainError(
            "packaging-archive", "crate assembly changed Cargo payload bytes"
        )


def canonical_nuget_archive(source: Path, destination: Path) -> None:
    """Give the unsigned SDK package stable OPC identifiers before capture."""
    import xml.etree.ElementTree as ET

    from tooling.release_payload import archive_files

    files = archive_files(source)
    properties = [
        name
        for name in files
        if re.fullmatch(
            r"package/services/metadata/core-properties/[0-9a-fA-F]{32}\.psmdcp", name
        )
    ]
    if (
        source.resolve() == destination.resolve()
        or ".signature.p7s" in files
        or len(properties) != 1
    ):
        raise ReleaseSupplyChainError(
            "packaging-archive", "one unsigned NuGet core-properties part is required"
        )
    old = properties[0]
    new = (
        "package/services/metadata/core-properties/"
        + hashlib.sha256(files[old]).hexdigest()[:32]
        + ".psmdcp"
    )
    namespace = "http://schemas.openxmlformats.org/package/2006/relationships"
    kind = "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
    relationships = ET.fromstring(files["_rels/.rels"])
    candidates = [row for row in relationships if row.get("Type") == kind]
    if (
        relationships.tag != "{" + namespace + "}Relationships"
        or any(row.tag != "{" + namespace + "}Relationship" for row in relationships)
        or len(candidates) != 1
        or candidates[0].get("Target") != "/" + old
        or candidates[0].get("TargetMode", "Internal") != "Internal"
        or len({row.get("Id") for row in relationships}) != len(relationships)
    ):
        raise ReleaseSupplyChainError(
            "packaging-archive", "ambiguous NuGet core-properties relationship"
        )
    types = ET.fromstring(files["[Content_Types].xml"])
    if (
        any(row.get("PartName") == "/" + old for row in types)
        or sum(
            row.get("Extension") == "psmdcp"
            and row.get("ContentType")
            == "application/vnd.openxmlformats-package.core-properties+xml"
            for row in types
        )
        != 1
    ):
        raise ReleaseSupplyChainError(
            "packaging-archive", "unsupported NuGet core-properties content type"
        )
    candidates[0].set("Target", "/" + new)
    candidates[0].set("Id", "R" + hashlib.sha256(new.encode()).hexdigest()[:32])
    if len({row.get("Id") for row in relationships}) != len(relationships):
        raise ReleaseSupplyChainError(
            "packaging-archive", "NuGet relationship ID collision"
        )
    files[new] = files.pop(old)
    files["_rels/.rels"] = ET.tostring(
        relationships, encoding="utf-8", xml_declaration=True
    )
    with (
        zipfile.ZipFile(source) as original,
        zipfile.ZipFile(
            destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive,
    ):
        archive.comment = original.comment
        for name, data in sorted(files.items()):
            prior = original.getinfo(old if name == new else name)
            header = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            header.create_system = prior.create_system
            header.external_attr = prior.external_attr
            header.internal_attr = prior.internal_attr
            header.comment = prior.comment
            archive.writestr(header, data, compress_type=zipfile.ZIP_DEFLATED)
    if archive_files(destination) != files:
        raise ReleaseSupplyChainError(
            "packaging-archive", "NuGet package content changed"
        )


def prepare_sdk(artifact_id: str, *, engineering: bool = False) -> dict:
    """Populate pinned JVM dependency caches in a credential-free build context.

    Disposable warmup products never become release subjects. The registered
    assembly command subsequently cleans and rebuilds each independent checkout.
    """
    manifest = validate_manifest(load_json(MANIFEST_PATH))
    artifact = next(
        (row for row in manifest["artifacts"] if row["id"] == artifact_id), None
    )
    if artifact is None or artifact_id not in {"release:java", "release:kotlin"}:
        raise ReleaseSupplyChainError(
            "packaging-toolchain",
            "SDK preparation is restricted to registered JVM dependency caches",
        )
    scoped_artifact(artifact, host_scope())
    if not engineering:
        authenticate_source(ROOT)
    environment = build_environment(ROOT, "946684800", manifest)
    maven = shutil.which("mvn", path=environment.get("PATH"))
    if maven is None:
        raise ReleaseSupplyChainError(
            "packaging-toolchain", "the governed Maven SDK is missing"
        )
    version = get_source_version()
    from tooling.maven_release import canonical_binary_jar

    with tempfile.TemporaryDirectory(prefix="strling-jvm-sdk-") as temporary:
        workspace = Path(temporary)
        settings = workspace / "settings.xml"
        settings.write_text(
            '<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0"/>\n',
            encoding="utf-8",
        )
        environment["MAVEN_ARGS"] = ""
        maven_command = [
            maven,
            "--settings",
            str(settings),
            "--global-settings",
            str(settings),
            "--strict-checksums",
        ]
        shutil.copyfile(ROOT / "LICENSE", workspace / "LICENSE")
        bridge = workspace / "bindings/jvm"
        staged_source(ROOT, "bindings/jvm", bridge)
        subprocess.run(
            [*maven_command, "-B", "-DskipTests", "package"],
            cwd=bridge,
            env=environment,
            check=True,
        )
        jar = bridge / "target" / ("strling-jvm-" + version + ".jar")
        canonical_binary_jar(jar)
        subprocess.run(
            [
                *maven_command,
                "-B",
                "org.apache.maven.plugins:maven-install-plugin:3.1.2:install-file",
                "-Dfile=" + str(jar),
                "-DpomFile=" + str(bridge / "pom.xml"),
            ],
            cwd=bridge,
            env=environment,
            check=True,
        )
        slug = artifact_id.removeprefix("release:")
        binding = workspace / "bindings" / slug
        staged_source(ROOT, "bindings/" + slug, binding)
        if slug == "java":
            subprocess.run(
                [*maven_command, "-B", "-DskipTests", "package"],
                cwd=binding,
                env=environment,
                check=True,
            )
        else:
            wrapper = binding / ("gradlew.bat" if os.name == "nt" else "gradlew")
            subprocess.run(
                [
                    str(wrapper),
                    "--no-daemon",
                    "--no-build-cache",
                    "--rerun-tasks",
                    "--dependency-verification",
                    "strict",
                    "classes",
                ],
                cwd=binding,
                env=environment,
                check=True,
            )
    return {
        "status": "passed",
        "artifact_id": artifact_id,
        "purpose": "dependency-cache-preparation-only",
        "publication_authorized": False,
    }


def build(
    artifact_id: str, *, engineering: bool = False, preview: bool = False
) -> dict:
    version = get_source_version()
    policy = load_json(ROOT / "governance/release-policy.json")
    plan = projected_contents(ROOT, policy, version)
    if any(path.read_text(encoding="utf-8") != text for path, text in plan.items()):
        raise ReleaseSupplyChainError(
            "packaging-version", "stale coordinated version metadata"
        )
    manifest = validate_manifest(load_json(MANIFEST_PATH))
    artifact = next((a for a in manifest["artifacts"] if a["id"] == artifact_id), None)
    if artifact is None:
        raise ReleaseSupplyChainError("packaging-artifact", "unknown release surface")
    distribution = artifact["distribution_contract"]
    if distribution["tier"] != "Supported" and not preview:
        raise ReleaseSupplyChainError(
            "packaging-preview",
            "Preview builds require an explicit Preview classification",
        )
    scope = host_scope()
    if scope not in artifact["build_platforms"]:
        raise ReleaseSupplyChainError(
            "packaging-platform", "this distribution is not Supported on the build host"
        )
    source = None if engineering else authenticate_source(ROOT)
    epoch = subprocess.check_output(
        ["git", "-C", str(ROOT), "show", "-s", "--format=%ct", "HEAD"], text=True
    ).strip()
    environment = build_environment(ROOT, epoch, manifest)
    slug = artifact_id.removeprefix("release:")
    binding = ROOT / artifact["package_root"]

    def run(*args: str, cwd: Path = binding) -> None:
        executable = shutil.which(args[0], path=environment.get("PATH"))
        if executable is None and (cwd / args[0]).is_file():
            executable = str((cwd / args[0]).resolve())
        if executable is None:
            raise ReleaseSupplyChainError(
                "packaging-toolchain",
                "required build executable is unavailable: " + args[0],
            )
        if (
            os.name == "nt"
            and Path(executable).suffix.lower() in {".cmd", ".bat"}
            and any(
                re.search(r"[&|<>^%!\r\n]", argument)
                for argument in (executable, *args[1:])
            )
        ):
            raise ReleaseSupplyChainError(
                "packaging-command", "unsafe Windows batch argument"
            )
        subprocess.run([executable, *args[1:]], cwd=cwd, env=environment, check=True)

    def native() -> None:
        run(
            sys.executable,
            str(ROOT / "tooling/native_release_build.py"),
            "--source-root",
            str(ROOT),
            "--target-dir",
            str(ROOT / "bindings/interop/target"),
        )

    if slug in {"go", "dart", "swift", "java", "kotlin"}:
        native()
    if slug in {"fsharp", "kotlin"}:
        companion_id = "release:csharp" if slug == "fsharp" else "release:java"
        companion = next(
            row for row in manifest["artifacts"] if row["id"] == companion_id
        )
        companion = scoped_artifact(companion, scope)
        try:
            companion_members = _surface_members(ROOT, companion, version)
            inspect_release_payload(ROOT, companion, version, companion_members)
        except ReleaseSupplyChainError as error:
            raise ReleaseSupplyChainError(
                "packaging-companion",
                "assemble or restore the exact "
                + companion_id
                + " subjects before this dependent package",
            ) from error

    if slug == "rust":
        # Cargo verifies the extracted crate in a new filesystem workspace.
        # Canonicalize only archive headers before any capture or publication.
        with tempfile.TemporaryDirectory(prefix="strling-rust-package-") as temporary:
            run(
                "cargo",
                "+1.75.0",
                "package",
                "--locked",
                "--offline",
                "--target-dir",
                temporary,
                *(["--allow-dirty"] if engineering else []),
                cwd=ROOT,
            )
            archive = Path(temporary) / "package" / ("strling-" + version + ".crate")
            destination = ROOT / "target/package" / archive.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            staged = destination.with_suffix(".crate.tmp")
            canonical_rust_archive(archive, staged, version=version, epoch=int(epoch))
            os.replace(staged, destination)
    elif slug == "python":
        if sys.version_info[:2] != (3, 12):
            raise ReleaseSupplyChainError(
                "packaging-runtime",
                "release Python packaging requires the certified CPython 3.12 row",
            )
        build_requirements = tomllib.loads((binding / "pyproject.toml").read_text())[
            "build-system"
        ]["requires"]
        for requirement in build_requirements:
            name, expected = requirement.split("==")
            if importlib.metadata.version(name) != expected:
                raise ReleaseSupplyChainError(
                    "packaging-toolchain",
                    "Install the repository hash-locked Python build requirements before assembly",
                )
        run(sys.executable, "-m", "build", "--no-isolation")
    elif slug == "typescript":
        run("npm", "ci", "--offline", "--ignore-scripts")
        run("npm", "pack", "--json")
    elif slug == "cpp":
        profile = binding / "profiles" / scope
        if not profile.is_file():
            raise ReleaseSupplyChainError(
                "packaging-toolchain",
                "a reviewed Conan build profile is required for this platform",
            )
        cache_name = "conan-home-" + uuid.uuid4().hex if engineering else "conan-home"
        environment["CONAN_HOME"] = str(ROOT / "target/release-packaging" / cache_name)
        if Path(environment["CONAN_HOME"]).exists():
            raise ReleaseSupplyChainError(
                "packaging-rebuild",
                "Conan assembly requires an independent empty cache",
            )
        run(
            "conan",
            "create",
            ".",
            "--version",
            version,
            "--profile:all=" + str(profile),
            "--build=strling/*",
            "--no-remote",
        )
        output = binding / "dist" / ("strling-" + version + "-" + scope + ".tgz")
        output.parent.mkdir(exist_ok=True)
        staged_output = output.with_name(".staging-" + output.name)
        run(
            "conan",
            "cache",
            "save",
            "strling/" + version + ":*",
            "--file=" + str(staged_output),
        )
        os.replace(staged_output, output)
        from tooling.conan_release import materialize_upload

        materialize_upload(output, output.with_suffix(".upload.zip"), version)
    elif slug == "c":
        compiler_options = (
            [
                "-G",
                "Visual Studio 17 2022",
                "-A",
                "x64",
                "-T",
                windows_cmake_toolset(ROOT),
            ]
            if os.name == "nt"
            else ["-DCMAKE_C_COMPILER=gcc-13"]
        )
        run(
            "cmake",
            "-S",
            ".",
            "-B",
            "build",
            "-DCMAKE_BUILD_TYPE=Release",
            "-DBUILD_TESTING=OFF",
            "-DPython3_EXECUTABLE=" + sys.executable,
            *compiler_options,
        )
        run("cmake", "--build", "build", "--config", "Release")
        run(
            "cmake",
            "--install",
            "build",
            "--config",
            "Release",
            "--prefix",
            str(binding / "build/install"),
        )
    elif slug in {"csharp", "fsharp"}:
        native()
        from tooling.release_notices import write_notices

        third_party = ROOT / "target/release-packaging/THIRD_PARTY_NOTICES.txt"
        write_notices(third_party)
        environment["STRlingThirdPartyNotices"] = str(third_party)
        environment["STRlingNativeLibrary"] = str(
            ROOT / "bindings/interop/target/release/strling_interop.dll"
        )
        environment["STRlingNativeRid"] = "win-x64"
        project = (
            "src/STRling/STRling.csproj"
            if slug == "csharp"
            else "src/STRling.FSharp/STRling.FSharp.fsproj"
        )
        release_options = []
        if slug == "fsharp":
            from tooling.dotnet_adapter_package import _fsharp_core_package

            dotnet = shutil.which("dotnet")
            if dotnet is None:
                raise ReleaseSupplyChainError(
                    "packaging-toolchain", "the governed .NET SDK is missing"
                )
            feed_name = (
                "fsharp-feed-" + uuid.uuid4().hex if engineering else "fsharp-feed"
            )
            feed = ROOT / "target/release-packaging" / feed_name
            if feed.exists():
                raise ReleaseSupplyChainError(
                    "packaging-rebuild", "F# release feed must be fresh"
                )
            feed.mkdir(parents=True)
            for member in companion_members:
                shutil.copyfile(ROOT / member["name"], feed / Path(member["name"]).name)
            shutil.copyfile(
                _fsharp_core_package(dotnet), feed / "FSharp.Core.9.0.300.nupkg"
            )
            environment["NUGET_PACKAGES"] = str(
                ROOT / "target/release-packaging" / (feed_name + "-nuget-cache")
            )
            config = feed / "NuGet.Config"
            import xml.etree.ElementTree as ET

            configuration = ET.Element("configuration")
            sources = ET.SubElement(configuration, "packageSources")
            ET.SubElement(sources, "clear")
            ET.SubElement(sources, "add", key="certified", value=str(feed))
            ET.ElementTree(configuration).write(
                config, encoding="utf-8", xml_declaration=True
            )
            release_options = [
                "-p:STRlingReleasePackage=true",
                "-p:RestoreConfigFile=" + str(config),
                "-p:NuGetAudit=false",
            ]
        run(
            "dotnet",
            "pack",
            project,
            "-c",
            "Release",
            "-p:ContinuousIntegrationBuild=true",
            "-p:PathMap=" + str(ROOT) + "=/_/",
            *release_options,
        )
        packages = list((ROOT / project).parent.glob("bin/Release/*.nupkg"))
        if len(packages) != 1:
            raise ReleaseSupplyChainError(
                "packaging-archive", "one exact NuGet output is required"
            )
        canonical = packages[0].with_suffix(".nupkg.tmp")
        canonical_nuget_archive(packages[0], canonical)
        os.replace(canonical, packages[0])
    elif slug in {"java", "kotlin"}:
        if slug == "java":
            run(
                "mvn",
                "-B",
                "--offline",
                "-DskipTests",
                "clean",
                "install",
                cwd=ROOT / "bindings/jvm",
            )
            run("mvn", "-B", "--offline", "-DskipTests", "clean", "package")
        else:
            # Install the staged companion bytes, without replacing them with
            # a second build in this dependent package's job.
            run(
                "mvn",
                "-B",
                "--offline",
                "org.apache.maven.plugins:maven-install-plugin:3.1.2:install-file",
                "-Dfile="
                + str(
                    ROOT / "bindings/jvm/target" / ("strling-jvm-" + version + ".jar")
                ),
                "-DpomFile=" + str(ROOT / "bindings/jvm/pom.xml"),
            )
            wrapper = "gradlew.bat" if os.name == "nt" else "./gradlew"
            run(
                wrapper,
                "--offline",
                "--no-daemon",
                "--no-build-cache",
                "--rerun-tasks",
                "clean",
                "publishToMavenLocal",
                "-Pversion=" + version,
            )
        from tooling.maven_release import classifiers, canonical_binary_jar

        if slug == "java":
            canonical_binary_jar(
                ROOT / "bindings/jvm/target" / ("strling-jvm-" + version + ".jar")
            )
            canonical_binary_jar(binding / "target" / ("strling-" + version + ".jar"))
        else:
            canonical_binary_jar(
                binding / "build/libs" / ("strling-kotlin-" + version + ".jar")
            )

        if slug == "java":
            classifiers(ROOT, "jvm", version)
        classifiers(ROOT, slug, version)
    elif slug == "go":
        run("go", "build", "./...")
    elif slug == "swift":
        run("swift", "build", "-c", "release")
    elif slug == "php":
        run("composer", "validate", "--no-check-publish")
    elif slug == "ruby":
        stage = ROOT / "target/release-packaging/ruby"
        staged_source(ROOT, "bindings/ruby", stage)
        gemspec = stage / "strling.gemspec"
        gemspec.write_text(
            gemspec.read_text().replace("'0.0.0.dev'", repr(version)), encoding="utf-8"
        )
        run("gem", "build", "strling.gemspec", cwd=stage)
        shutil.copyfile(
            stage / f"strling-{version}.gem", binding / f"strling-{version}.gem"
        )
    elif slug == "lua":
        # The canonical materializer owns prerelease and rock revision spelling.
        run(
            sys.executable,
            str(ROOT / "tooling/lua_rockspec.py"),
            "materialize",
            "--version-from-source",
            "--output-dir",
            str(binding),
        )
        from tooling.lua_rockspec import rockspec_name

        rockspec = binding / rockspec_name(version)
        source_rock = rockspec.with_suffix(".src.rock")
        tracked = subprocess.check_output(
            [
                "git",
                "-C",
                str(ROOT),
                "ls-files",
                "-z",
                "--",
                "bindings/lua/src",
                "bindings/lua/README.md",
            ]
        )
        files = {
            rockspec.name: rockspec.read_bytes(),
            "strling/bindings/lua/LICENSE": (ROOT / "LICENSE").read_bytes(),
        }
        for raw in tracked.split(b"\0"):
            if raw:
                relative = raw.decode("utf-8")
                files["strling/" + relative] = (ROOT / relative).read_bytes()
        with zipfile.ZipFile(
            source_rock, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for name, data in sorted(files.items()):
                entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, data)
    elif slug == "perl":
        stage = ROOT / "target/release-packaging/perl"
        staged_source(ROOT, "bindings/perl", stage)
        run("perl", "Makefile.PL", cwd=stage)
        run("make", "dist", cwd=stage)
        shutil.copyfile(
            stage / f"STRling-{version}.tar.gz", binding / f"STRling-{version}.tar.gz"
        )
    elif slug == "r":
        run("R", "CMD", "build", ".")
    elif slug == "dart":
        stage = ROOT / "target/release-packaging/dart"
        if stage.exists():
            raise ReleaseSupplyChainError(
                "packaging-stage", "Dart staging directory already exists"
            )
        tracked = subprocess.check_output(
            [
                "git",
                "-C",
                str(ROOT),
                "ls-files",
                "-z",
                "--",
                "bindings/dart/lib",
                "bindings/dart/pubspec.yaml",
                "bindings/dart/README.md",
                "bindings/dart/CHANGELOG.md",
            ]
        )
        for raw in tracked.split(b"\0"):
            if not raw:
                continue
            relative = Path(raw.decode("utf-8"))
            destination = stage / relative.relative_to("bindings/dart")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        shutil.copyfile(ROOT / "LICENSE", stage / "LICENSE")
        # Override the parent repository's ignored target/ directory. Pub
        # excludes hidden control files; the certified assembly still binds it.
        (stage / ".pubignore").write_text(
            ".dart_tool/\npubspec.lock\n", encoding="utf-8"
        )
        # Pub evaluates ancestor Git ignores. Validate an exact relocation
        # outside the checkout, leaving the certified assembly untouched.
        with tempfile.TemporaryDirectory(prefix="strling-pub-dry-run-") as temporary:
            validation = Path(temporary) / "package"
            shutil.copytree(stage, validation)
            run("dart", "pub", "publish", "--dry-run", cwd=validation)

    selected = scoped_artifact(artifact, scope)
    members = _surface_members(ROOT, selected, version)
    content_files = inspect_release_payload(ROOT, selected, version, members)
    return {
        "status": "passed",
        "artifact_id": artifact_id,
        "version": version,
        "source": source,
        "scope": scope,
        "tier": distribution["tier"],
        "engineering": engineering,
        "inspected_content_files": len(content_files),
        "publication_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--engineering", action="store_true")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--prepare-sdk", action="store_true")
    args = parser.parse_args()
    try:
        result = (
            prepare_sdk(args.artifact_id, engineering=args.engineering)
            if args.prepare_sdk
            else build(
                args.artifact_id, engineering=args.engineering, preview=args.preview
            )
        )
    except (ReleaseSupplyChainError, OSError, subprocess.CalledProcessError) as error:
        result = {
            "status": "failed",
            "error": str(error),
            "publication_authorized": False,
        }
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
