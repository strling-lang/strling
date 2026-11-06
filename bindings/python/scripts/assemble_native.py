"""Build the governed host-native interop library for Python packaging/tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BUNDLED_SOURCE_ROOT = PACKAGE_ROOT / "_native_source"
ROOT = (
    BUNDLED_SOURCE_ROOT
    if (BUNDLED_SOURCE_ROOT / "bindings" / "interop" / "Cargo.toml").is_file()
    else REPOSITORY_ROOT
)
MANIFEST = ROOT / "bindings" / "interop" / "Cargo.toml"


def cargo() -> str:
    resolved = shutil.which("cargo")
    if resolved is not None:
        return resolved
    candidate = Path.home() / ".cargo" / "bin" / "cargo.exe"
    if sys.platform == "win32" and candidate.is_file():
        return str(candidate)
    raise RuntimeError("Cargo is required to assemble the STRling native library")


def library_name() -> str:
    if platform.machine().lower() not in {"amd64", "x86_64"} or sys.platform not in {
        "win32",
        "linux",
    }:
        raise RuntimeError(
            "Only Windows/Linux x86_64 has a certified native package row"
        )
    if sys.platform == "win32":
        return "strling_interop.dll"
    if sys.platform == "darwin":
        return "libstrling_interop.dylib"
    return "libstrling_interop.so"


def assemble(output_directory: Path) -> Path:
    environment = dict(os.environ)
    # An sdist builds from its embedded source root, which may differ from the
    # caller's checkout. Remap the actual compiler inputs, not that caller path.
    environment["RUSTFLAGS"] = "--remap-path-prefix=" + str(ROOT) + "=/strling"
    if sys.platform == "win32":
        environment["RUSTFLAGS"] += " -Clink-arg=/Brepro -Clink-arg=/DEBUG:NONE"
    environment["CARGO_INCREMENTAL"] = "0"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tooling/native_release_build.py"),
            "--source-root", str(ROOT),
            "--target-dir", str(ROOT / "bindings/interop/target"),
        ],
        cwd=ROOT,
        env=environment,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    source = ROOT / "bindings" / "interop" / "target" / "release" / library_name()
    if not source.is_file():
        raise RuntimeError("Cargo did not produce the expected native library")
    output_directory.mkdir(parents=True, exist_ok=True)
    output = output_directory / library_name()
    shutil.copyfile(source, output)
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tooling/release_notices.py"),
            "--output",
            str(output_directory / "THIRD_PARTY_NOTICES.txt"),
        ],
        check=True,
    )
    # Bind this wheel to its exact native payload; ABI compatibility alone does
    # not identify the compiler build embedded in a coordinated product package.
    version = tomllib.loads(
        (PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    identity = {
        "product_version": version,
        "native_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "protocol_version": "1.0.0",
        "abi_major": 1,
        "platform": "windows-x86_64" if sys.platform == "win32" else "linux-x86_64",
    }
    (output_directory / "kernel-identity.json").write_text(
        json.dumps(identity, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("assembled {}".format(output.resolve()))
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assemble(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
