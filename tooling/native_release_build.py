"""Build the unchanged kernel and interop sources in one private Cargo workspace.

Cargo 1.75 hashes absolute paths for path dependencies outside its workspace.
The repository intentionally keeps independent development workspaces. Release
assembly copies their exact source bytes and replaces only workspace tables in
a disposable root, so Cargo can give both crates relative package identities.
No dependency resolution, compiler-source rewrite or output normalization occurs.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


SOURCE_PATHS = (
    "bindings/interop/Cargo.toml",
    "bindings/interop/Cargo.lock",
    "bindings/interop/src",
    "bindings/interop/fuzz/Cargo.toml",
    "bindings/interop/fuzz/fuzz_targets",
    "core/internal/Cargo.toml",
    "core/src",
    "spec",
    "tests/conformance",
)


def stage_workspace(source: Path, destination: Path) -> None:
    if destination.exists():
        raise ValueError("native assembly workspace must be new")
    destination.mkdir(parents=True)
    for relative in SOURCE_PATHS:
        path = source / relative
        if path.is_symlink():
            raise ValueError("native assembly forbids symbolic links")
        paths = sorted(path.rglob("*")) if path.is_dir() else [path]
        for item in paths:
            if item.is_symlink():
                raise ValueError("native assembly forbids symbolic links")
            if item.is_file():
                output = destination / item.relative_to(source)
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(item, output)
    for relative in ("bindings/interop/Cargo.toml", "core/internal/Cargo.toml"):
        path = destination / relative
        original = path.read_text(encoding="utf-8")
        rewritten, count = re.subn(
            r"(?ms)^\[workspace\]\s*\n.*?(?=^\[|\Z)", "", original
        )
        if count != 1:
            raise ValueError("native source must have one independent workspace table")
        path.write_text(rewritten, encoding="utf-8", newline="\n")
    (destination / "Cargo.toml").write_text(
        '[workspace]\nmembers = ["bindings/interop", "bindings/interop/fuzz", "core/internal"]\n'
        'default-members = ["bindings/interop"]\nresolver = "2"\n',
        encoding="utf-8",
        newline="\n",
    )
    shutil.copyfile(source / "bindings/interop/Cargo.lock", destination / "Cargo.lock")


def build(source: Path, target_dir: Path, target: str | None = None) -> None:
    source, target_dir = source.resolve(), target_dir.resolve()
    if target not in {None, "wasm32-unknown-unknown"}:
        raise ValueError("unregistered native assembly target")
    with tempfile.TemporaryDirectory(prefix="strling-native-source-") as temporary:
        workspace = Path(temporary) / "workspace"
        stage_workspace(source, workspace)
        environment = dict(os.environ)
        for key in (
            "RUSTC",
            "RUSTDOC",
            "RUSTC_WRAPPER",
            "RUSTC_WORKSPACE_WRAPPER",
            "CARGO_ENCODED_RUSTFLAGS",
            "CARGO_BUILD_TARGET",
        ):
            environment.pop(key, None)
        for key in list(environment):
            if key.startswith(("CARGO_PROFILE_", "CARGO_BUILD_", "CARGO_TARGET_")):
                environment.pop(key)
        cargo_home = Path(
            environment.get("CARGO_HOME", Path.home() / ".cargo")
        ).resolve()
        flags = [
            "--remap-path-prefix=" + str(path) + "=" + label
            for path, label in ((workspace, "/strling"), (cargo_home, "/cargo"))
        ]
        if os.name == "nt" and target is None:
            flags.extend(["-Clink-arg=/Brepro", "-Clink-arg=/DEBUG:NONE"])
        environment.pop("RUSTFLAGS", None)
        environment["CARGO_ENCODED_RUSTFLAGS"] = "\x1f".join(flags)
        environment["CARGO_INCREMENTAL"] = "0"
        command = [
            "cargo",
            "+1.75.0",
            "build",
            "--manifest-path",
            str(workspace / "Cargo.toml"),
            "-p",
            "strling-interop",
            "--release",
            "--locked",
            "--offline",
            "--target-dir",
            str(target_dir),
        ]
        if target:
            command.extend(["--target", target])
        subprocess.run(command, cwd=workspace, env=environment, check=True)
        if (workspace / "Cargo.lock").read_bytes() != (
            source / "bindings/interop/Cargo.lock"
        ).read_bytes():
            raise ValueError("native assembly changed the governed dependency lock")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--target-dir", type=Path, required=True)
    parser.add_argument("--target", choices=["wasm32-unknown-unknown"])
    args = parser.parse_args()
    build(args.source_root, args.target_dir, args.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
