"""Collect notices from checksum-verified locked Rust source archives, offline."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import tarfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def locked_packages(root: Path) -> list[dict]:
    lock = tomllib.loads(
        (root / "bindings/interop/Cargo.lock").read_text(encoding="utf-8")
    )
    package_name = tomllib.loads(
        (root / "bindings/interop/Cargo.toml").read_text(encoding="utf-8")
    )["package"]["name"]
    roots = [
        item
        for item in lock["package"]
        if item["name"] == package_name and "source" not in item
    ]
    if len(roots) != 1:
        raise ValueError("canonical interop lock root is missing or ambiguous")
    reachable, pending = {}, roots[:]
    while pending:
        package = pending.pop()
        identity = (package["name"], package["version"], package.get("source"))
        if identity in reachable:
            continue
        reachable[identity] = package
        for dependency in package.get("dependencies", []):
            tokens = dependency.split()
            matches = [
                item
                for item in lock["package"]
                if item["name"] == tokens[0]
                and (len(tokens) < 2 or item["version"] == tokens[1])
                and (len(tokens) < 3 or item.get("source") == tokens[2].strip("()"))
            ]
            if len(matches) != 1:
                raise ValueError("locked native dependency is missing or ambiguous")
            pending.extend(matches)
    packages = []
    for package in reachable.values():
        if "source" not in package:
            continue
        if (
            package["source"] != "registry+https://github.com/rust-lang/crates.io-index"
            or re.fullmatch(r"[0-9a-f]{64}", package.get("checksum", "")) is None
        ):
            raise ValueError("unregistered or unlocked Rust dependency source")
        packages.append(package)
    if not packages:
        raise ValueError("native dependency graph is empty")
    return sorted(packages, key=lambda item: (item["name"], item["version"]))


def notices(root: Path = ROOT, cargo_home: Path | None = None) -> str:
    cargo_home = cargo_home or Path(
        os.environ.get("CARGO_HOME", str(Path.home() / ".cargo"))
    )
    lines = [
        "STRling locked Rust dependency notices",
        "",
        "Includes locked runtime, build, and test components; the SPDX SBOM identifies distribution scopes.",
        "",
    ]
    for package in locked_packages(root):
        filename = package["name"] + "-" + package["version"] + ".crate"
        matches = list((cargo_home / "registry/cache").glob("*/" + filename))
        verified = [
            path
            for path in matches
            if hashlib.sha256(path.read_bytes()).hexdigest() == package["checksum"]
        ]
        if not verified:
            raise ValueError("missing checksum-verified source archive: " + filename)
        found = []
        with tarfile.open(verified[0], "r:*") as archive:
            for entry in sorted(archive.getmembers(), key=lambda item: item.name):
                name = Path(entry.name)
                if (
                    name.is_absolute()
                    or ".." in name.parts
                    or entry.issym()
                    or entry.islnk()
                ):
                    raise ValueError("unsafe dependency source archive")
                if not entry.isfile() or not name.name.upper().startswith(
                    ("LICENSE", "COPYING", "NOTICE", "COPYRIGHT")
                ):
                    continue
                if entry.size > 2_000_000:
                    raise ValueError("unbounded dependency notice")
                file = archive.extractfile(entry)
                assert file is not None
                found.append((entry.name, file.read().decode("utf-8")))
        if not found:
            raise ValueError(
                "locked dependency has no redistributable notice: " + filename
            )
        lines.extend(
            [
                "=" * 72,
                package["name"] + " " + package["version"],
                "Source archive SHA-256: " + package["checksum"],
                "",
            ]
        )
        for name, content in found:
            lines.extend(["--- " + name, content.rstrip(), ""])
    return "\n".join(lines) + "\n"


def write_notices(output: Path, root: Path = ROOT) -> None:
    content = notices(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--check-inputs", action="store_true")
    args = parser.parse_args()
    try:
        if args.check_inputs:
            locked_packages(ROOT)
            print("release notices input contract: passed (not live artifact evidence)")
            return 0
        if args.output is None:
            parser.error("--output is required for assembly or artifact verification")
        content = notices()
        if args.check:
            if args.output.read_text(encoding="utf-8") != content:
                raise ValueError("third-party notices are stale")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding="utf-8", newline="\n")
    except (OSError, ValueError, tarfile.TarError) as error:
        print("release notices failed: " + str(error))
        return 1
    print("release notices: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
