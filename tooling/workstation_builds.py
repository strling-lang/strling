"""Independent kernel builds with one explicitly pinned measurement harness."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

HARNESS = Path("tests/certification/performance-resource/1.0/runner")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)


def _run(command, *, root, directory, name, environment):
    with (
        (directory / (name + ".stdout")).open("xb") as stdout,
        (directory / (name + ".stderr")).open("xb") as stderr,
    ):
        result = subprocess.run(
            command,
            cwd=root,
            env=environment,
            stdout=stdout,
            stderr=stderr,
            timeout=1800,
        )
    save(
        directory / (name + ".json"),
        dict(
            command=command,
            exit_code=result.returncode,
            stdout_sha256=digest(directory / (name + ".stdout")),
            stderr_sha256=digest(directory / (name + ".stderr")),
        ),
    )
    if result.returncode:
        raise ValueError(name + " failed; raw build output retained")


def build_lane(
    root, directory, *, kernel_revision, harness_root, cargo, rustc, slowdown=False
):
    """A fresh directory is mandatory. Never reuse another lane's artifacts.

    Kernel code is a Git archive of kernel_revision; harness code is separately
    pinned to harness_root's actual bytes. Only three dependency paths in the
    copied manifest are materialized. This is explicitly a mixed-source build.
    The caller retains source ownership and verifies provenance before and after.
    """
    root, directory, harness_root = map(Path, (root, directory, harness_root))
    if not all(p.is_absolute() for p in (root, directory, harness_root)):
        raise ValueError("absolute roots required")
    directory.mkdir(exist_ok=False)
    archive = directory / "kernel-source.zip"
    environment = dict(os.environ, RUSTC=str(rustc), CARGO_NET_OFFLINE="true")
    environment["CARGO_INCREMENTAL"] = "0"
    for name in (
        "RUSTC_WRAPPER",
        "RUSTC_WORKSPACE_WRAPPER",
        "CARGO_BUILD_RUSTC_WRAPPER",
    ):
        environment.pop(name, None)
    with archive.open("xb") as stream:
        subprocess.run(
            [
                "git",
                "--no-optional-locks",
                "archive",
                "--format=zip",
                kernel_revision,
            ],
            cwd=root,
            stdout=stream,
            check=True,
            timeout=120,
        )
    source = directory / "source"
    source.mkdir()
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            path = PurePosixPath(member.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in member.filename
                or ":" in member.filename
            ):
                raise ValueError("unconfined archive entry")
            mode = member.external_attr >> 16
            if mode & 0o170000 == 0o120000:
                raise ValueError("source archive symlink")
            destination = source.joinpath(*path.parts)
            if not destination.resolve().is_relative_to(source.resolve()):
                raise ValueError("source archive escaped")
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("xb") as stream:
                    stream.write(zipped.read(member))
    harness = directory / "harness"
    (harness / "src").mkdir(parents=True)
    pins = {}
    for path in sorted((harness_root / HARNESS / "src").glob("*.rs")):
        if path.is_symlink():
            raise ValueError("harness source link")
        target = harness / "src" / path.name
        target.write_bytes(path.read_bytes())
        pins[path.name] = digest(path)
    manifest_source = harness_root / HARNESS / "Cargo.toml"
    manifest = manifest_source.read_text(encoding="utf-8")
    for original, target in [
        ("../../../../../bindings/interop", source / "bindings/interop"),
        ("../../../../../core/internal", source / "core/internal"),
        ("../../../../../", source),
    ]:
        needle = 'path = "' + original + '"'
        if manifest.count(needle) != 1:
            raise ValueError("unreviewed harness dependency layout")
        manifest = manifest.replace(needle, 'path = "' + target.as_posix() + '"')
    (harness / "Cargo.toml").write_text(manifest, encoding="utf-8")
    (harness / "Cargo.lock").write_bytes(
        (harness_root / HARNESS / "Cargo.lock").read_bytes()
    )
    recipe = dict(
        kernel_revision=kernel_revision,
        source_archive_sha256=digest(archive),
        kernel_source_files={
            p.relative_to(source).as_posix(): digest(p)
            for p in sorted(source.rglob("*"))
            if p.is_file()
        },
        harness_source_sha256=pins,
        harness_manifest_source_sha256=digest(manifest_source),
        materialized_manifest_sha256=digest(harness / "Cargo.toml"),
        cargo_lock_sha256=digest(harness / "Cargo.lock"),
        cargo_sha256=digest(Path(cargo)),
        rustc_sha256=digest(Path(rustc)),
        mixed_source_build=True,
        negative_control=slowdown,
    )
    save(directory / "recipe.json", recipe)
    _run(
        [
            str(cargo),
            "build",
            "--release",
            "--locked",
            "--offline",
            "--manifest-path",
            str(harness / "Cargo.toml"),
            "--target-dir",
            str(harness / "target"),
            "--bins",
            *(["--features", "workstation-slowdown-challenge"] if slowdown else []),
        ],
        root=root,
        directory=directory,
        name="harness-build",
        environment=environment,
    )
    _run(
        [
            str(cargo),
            "build",
            "--release",
            "--locked",
            "--offline",
            "--manifest-path",
            str(source / "core/internal/Cargo.toml"),
            "--target-dir",
            str(source / "core/internal/target"),
            "--bin",
            "strling-kernel",
        ],
        root=root,
        directory=directory,
        name="kernel-build",
        environment=environment,
    )
    executables = {
        "runner": harness / "target/release/strling-performance-runner.exe",
        "memory_worker": harness
        / "target/release/strling-performance-memory-worker.exe",
        "kernel": source / "core/internal/target/release/strling-kernel.exe",
    }
    for relative, expected in recipe["kernel_source_files"].items():
        if digest(source / relative) != expected:
            raise ValueError("kernel source changed during build")
    for relative, expected in pins.items():
        if digest(harness / "src" / relative) != expected:
            raise ValueError("harness source changed during build")
    if (
        digest(harness / "Cargo.lock") != recipe["cargo_lock_sha256"]
        or digest(harness / "Cargo.toml") != recipe["materialized_manifest_sha256"]
    ):
        raise ValueError("build manifest or lock changed")
    result = dict(
        status="passed",
        recipe_sha256=digest(directory / "recipe.json"),
        negative_control=slowdown,
        artifacts={
            name: dict(path=str(path), sha256=digest(path), bytes=path.stat().st_size)
            for name, path in executables.items()
        },
    )
    save(directory / "built.json", result)
    return result
