#!/usr/bin/env python3
"""Sync the governed product-version projection across language bindings.

This script reads the single machine authority in `governance/release-policy.json`
and synchronizes its active repository projection with language-specific metadata.

The module is written to be importable and testable; functions raise
exceptions instead of calling sys.exit() directly so callers (or tests)
can decide how to handle errors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable, List, Optional

try:
    from tooling.lua_rockspec import normalize_lua_rockspec_version
except ModuleNotFoundError:  # Direct ``python tooling/sync_versions.py`` execution.
    from lua_rockspec import normalize_lua_rockspec_version

logger = logging.getLogger(__name__)


def normalize_ruby_gem_version(version: str) -> str:
    """Convert semver prereleases to a RubyGems-friendly version string."""
    return version.replace("-", ".")


# Configuration
ROOT_DIR: Path = Path(__file__).resolve().parent.parent
SOURCE_FILE: Path = ROOT_DIR / "governance/release-policy.json"


def unique_json(content: str) -> dict:
    def pairs(items):
        document = {}
        for key, value in items:
            if key in document:
                raise ValueError("Duplicate JSON metadata key: " + key)
            document[key] = value
        return document

    return json.loads(content, object_pairs_hook=pairs)


def get_source_version() -> str:
    """Return the governed repository projection version.

    Raises:
        FileNotFoundError: if the policy does not exist.
        ValueError: if the projection is malformed.
    """
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(f"Source file {SOURCE_FILE} not found.")

    document = unique_json(SOURCE_FILE.read_text(encoding="utf-8"))
    try:
        version = document["product"]["version"]
        projection = document["product"]["repository_projection"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Could not find the product repository projection") from exc
    if (
        not isinstance(version, str)
        or re.fullmatch(
            r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-rc\.[1-9][0-9]*)?",
            version,
        )
        is None
    ):
        raise ValueError("Product version must be a governed stable or RC SemVer")
    if projection != {**projection, "version": version, "status": "active"}:
        raise ValueError(
            "Repository projection must be active and equal the product version"
        )
    return version


def projected_contents(root: Path, policy: dict, version: str) -> dict[Path, str]:
    """Plan every substitution before writing; reject missing or ambiguous probes.

    The policy's closed version inventory, rather than a second updater list,
    selects product fields. Independent identities are checked but never rewritten.
    """
    contents: dict[Path, str] = {}
    ids: set[str] = set()
    registered: set[str] = set()
    for surface in policy["version_surfaces"]:
        if surface["id"] in ids:
            raise ValueError("Duplicate version surface: " + surface["id"])
        ids.add(surface["id"])
        relative = surface["path"]
        path = root / relative
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Version surface escapes repository: " + relative)
        registered.add(relative)
        content = contents.get(path, path.read_text(encoding="utf-8"))
        probe = surface["probe"]
        kind = probe["kind"]
        if path.suffix == ".json":
            unique_json(content)
        expected = (
            version
            if probe["expected"] == "repository_projection"
            else probe["expected"]
        )
        if path.suffix == ".toml" or path.name == "Cargo.lock":
            parsed = tomllib.loads(content)
            if path.name == "Cargo.toml" and not isinstance(
                parsed.get("package", {}).get("version"), str
            ):
                raise ValueError("Cargo package version is missing: " + relative)
            if path.name == "pyproject.toml" and not isinstance(
                parsed.get("project", {}).get("version"), str
            ):
                raise ValueError("Python project version is missing: " + relative)
        if path.suffix in (".xml", ".csproj", ".fsproj"):
            ET.fromstring(content)
        if kind == "tag":
            continue
        if kind in ("json", "absent"):
            document = unique_json(content)
            tokens = probe["pointer"].lstrip("/").split("/")
            parent = document
            for token in tokens[:-1]:
                parent = parent[token.replace("~1", "/").replace("~0", "~")]
            key = tokens[-1]
            if kind == "absent":
                if key in parent:
                    raise ValueError(
                        "Non-product manifest declares a version: " + relative
                    )
                continue
            observed = parent[key]
            if probe["expected"] == "repository_projection":
                parent[key] = version
                if observed != version:
                    indent = re.search(r'\n( +)"', content)
                    content = (
                        json.dumps(
                            document,
                            indent=len(indent[1]) if indent else 2,
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            elif observed != expected:
                raise ValueError("Independent version drift: " + surface["id"])
        else:
            matches = list(re.finditer(probe["pattern"], content))
            if len(matches) != 1 or matches[0].lastindex != 1:
                raise ValueError(
                    "Version probe must select exactly one field: " + surface["id"]
                )
            match = matches[0]
            if probe["expected"] == "repository_projection":
                content = content[: match.start(1)] + version + content[match.end(1) :]
            elif match[1] != expected:
                raise ValueError("Independent version drift: " + surface["id"])
        contents[path] = content

    # Detect newly introduced package manifests before silently leaving them out.
    for pattern in (
        "bindings/*/pyproject.toml",
        "bindings/*/package.json",
        "bindings/*/pubspec.yaml",
        "bindings/*/pom.xml",
        "bindings/*/composer.json",
        "bindings/*/DESCRIPTION",
        "bindings/*/dist.ini",
        "bindings/*/Cargo.toml",
        "bindings/*/go.mod",
        "bindings/*/Package.swift",
        "bindings/*/src/*/*.csproj",
        "bindings/*/src/*/*.fsproj",
    ):
        for path in root.glob(pattern):
            if path.relative_to(root).as_posix() not in registered:
                raise ValueError(
                    "Unregistered public manifest: " + path.relative_to(root).as_posix()
                )
    composer = root / "bindings/php/composer.json"
    if composer in contents:
        lock = composer.with_name("composer.lock")
        contents[lock] = composer_lock_projection(
            contents[composer], lock.read_text(encoding="utf-8")
        )
    return contents


def composer_lock_projection(manifest: str, lock: str) -> str:
    """Project Composer 2's content hash without resolving any dependency.

    Algorithm authority: composer/composer 2.7.1, Package/Locker::getContentHash.
    Only the root metadata hash changes; every resolved package record is retained.
    """
    document = unique_json(manifest)
    locked = unique_json(lock)
    if re.fullmatch(r"[0-9a-f]{32}", str(locked.get("content-hash", ""))) is None:
        raise ValueError("Composer lock has no unique valid content hash")
    relevant_keys = {
        "name",
        "version",
        "require",
        "require-dev",
        "conflict",
        "replace",
        "provide",
        "minimum-stability",
        "prefer-stable",
        "repositories",
        "extra",
    }
    relevant = {key: value for key, value in document.items() if key in relevant_keys}
    if "platform" in document.get("config", {}):
        relevant["config"] = {"platform": document["config"]["platform"]}

    def php_arrays(value):
        if isinstance(value, float):
            raise ValueError(
                "Composer resolution metadata cannot contain floating point values"
            )
        if isinstance(value, dict):
            return (
                {key: php_arrays(child) for key, child in value.items()}
                if value
                else []
            )
        if isinstance(value, list):
            return [php_arrays(child) for child in value]
        return value

    ordered = {key: php_arrays(relevant[key]) for key in sorted(relevant)}
    encoded = json.dumps(
        ordered, ensure_ascii=True, separators=(",", ":"), allow_nan=False
    ).replace("/", "\\/")
    digest = hashlib.md5(encoded.encode("utf-8"), usedforsecurity=False).hexdigest()
    if locked["content-hash"] == digest:
        return lock
    return re.sub(
        r'("content-hash"\s*:\s*")[0-9a-f]{32}(\")',
        lambda match: match[1] + digest + match[2],
        lock,
        count=1,
    )


def write_projection(planned: dict[Path, str]) -> None:
    """Stage all changed files first and roll back a failed multi-file update."""
    originals: dict[Path, bytes] = {}
    staged: dict[Path, Path] = {}
    changed: list[Path] = []
    try:
        for path, content in planned.items():
            if path.read_text(encoding="utf-8") == content:
                continue
            originals[path] = path.read_bytes()
            with tempfile.NamedTemporaryFile(
                dir=path.parent, delete=False, suffix=".version-sync.new"
            ) as stream:
                temporary = Path(stream.name)
                staged[path] = temporary
                stream.write(content.encode("utf-8"))
            shutil.copymode(path, temporary)
        for path, temporary in staged.items():
            os.replace(temporary, path)
            changed.append(path)
    except OSError:
        for path in reversed(changed):
            path.write_bytes(originals[path])
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def update_file(
    path: str,
    new_version: str,
    dry_run: bool = False,
    updater_func: Optional[Callable[[str, str, Path], str]] = None,
) -> bool:
    """Read a target file, run an updater func on its contents and write back.

    Returns True if the file already matched or was updated. In dry-run mode,
    a required change returns False so callers can use the function as an exact
    drift check. Missing files and processing errors also return False.
    """
    file_path: Path = ROOT_DIR / path
    if not file_path.exists():
        logger.warning("Target file %s not found. Skipping.", path)
        return False

    if updater_func is None:
        raise ValueError("updater_func must be provided")

    try:
        content: str = file_path.read_text(encoding="utf-8")
        new_content: str = updater_func(content, new_version, file_path)

        if new_content != content:
            if not dry_run:
                file_path.write_text(new_content, encoding="utf-8")
                logger.info("Updated %s to %s", path, new_version)
                return True
            else:
                logger.info("Would update %s to %s", path, new_version)
                return False
        else:
            logger.debug("No changes needed for %s", path)

        return True
    except Exception:
        logger.exception("Error updating %s", path)
        return False


# --- Updater Functions ---


def update_toml_cargo(content: str, version: str, path: Path) -> str:
    # Update the version inside [package] section in a Cargo.toml
    pattern = re.compile(
        r'(^\[package\][\s\S]*?^version\s*=\s*")([^\"]+)(")',
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    if match:
        return content[: match.start(2)] + version + content[match.end(2) :]
    return content


def update_json(content: str, version: str, path: Path) -> str:
    data = json.loads(content)
    if data.get("version") == version:
        return content

    data["version"] = version

    # Try to detect indentation from the existing file (fallback to 2)
    indent = 2
    m = re.search(r"\n(\s+)\"[^\"]+\":", content)
    if m:
        indent = len(m.group(1))

    return json.dumps(data, indent=indent, ensure_ascii=False) + "\n"


def update_composer_json(content: str, version: str, path: Path) -> str:
    # Use JSON parsing to handle both replacement and insertion robustly.
    # Composer files are valid JSON; json.loads/json.dumps will correctly
    # handle both updating an existing "version" key and inserting one when
    # missing. We try to detect indentation to preserve formatting.
    data = json.loads(content)
    if data.get("version") == version:
        return content

    data["version"] = version

    # Detect indentation similar to update_json
    indent = 2
    m = re.search(r"\n(\s+)\"[^\"]+\":", content)
    if m:
        indent = len(m.group(1))

    return json.dumps(data, indent=indent, ensure_ascii=False) + "\n"


def update_yaml_pubspec(content: str, version: str, path: Path) -> str:
    return re.sub(
        r"(^version:\s*)(.+)",
        lambda m: m.group(1) + version,
        content,
        flags=re.MULTILINE,
    )


def update_ruby_gemspec(content: str, version: str, path: Path) -> str:
    gem_version = normalize_ruby_gem_version(version)
    # Use callable replacement to avoid ambiguous group concatenation
    return re.sub(
        r'(spec\.version\s*=\s*")([^\"]+)(")',
        lambda m: m.group(1) + gem_version + m.group(3),
        content,
    )


def update_ruby_version_file(content: str, version: str, path: Path) -> str:
    return re.sub(
        r"(^\s*VERSION\s*=\s*')([^']+)(')",
        lambda m: m.group(1) + version + m.group(3),
        content,
        flags=re.MULTILINE,
    )


def update_xml_csproj(content: str, version: str, path: Path) -> str:
    if "<Version>" in content:
        return re.sub(
            r"(<Version>)([^<]+)(</Version>)",
            lambda m: m.group(1) + version + m.group(3),
            content,
        )

    # Insert a Version element into the first PropertyGroup if missing
    return re.sub(
        r"(<PropertyGroup>)",
        lambda m: m.group(1) + "\n    <Version>" + version + "</Version>",
        content,
        count=1,
    )


def update_xml_pom(content: str, version: str, path: Path) -> str:
    # Replace the first project-level <version>...</version> occurrence.
    return re.sub(
        r"(<version>)([^<]+)(</version>)",
        lambda m: m.group(1) + version + m.group(3),
        content,
        count=1,
    )


def update_kotlin_gradle(content: str, version: str, path: Path) -> str:
    return re.sub(
        r'(^version\s*=\s*")([^\"]+)(")',
        lambda m: m.group(1) + version + m.group(3),
        content,
        flags=re.MULTILINE,
    )


def update_r_description(content: str, version: str, path: Path) -> str:
    return re.sub(
        r"(^Version:\s*)(.+)",
        lambda m: m.group(1) + version,
        content,
        flags=re.MULTILINE,
    )


def update_perl_pm(content: str, version: str, path: Path) -> str:
    return re.sub(
        r"(our\s+\$VERSION\s*=\s*')([^']+)(';)",
        lambda m: m.group(1) + version + m.group(3),
        content,
    )


def update_cmake(content: str, version: str, path: Path) -> str:
    cmake_version = version.split("-", 1)[0]
    return re.sub(
        r"(project\s*\([\s\S]*?VERSION\s+)([\d\.\w-]+)([\s\S]*?\))",
        lambda m: m.group(1) + cmake_version + m.group(3),
        content,
    )


def update_c_source(content: str, version: str, path: Path) -> str:
    pattern = re.compile(
        r'(const\s+char\s*\*\s*strling_version\s*\(\s*void\s*\)\s*\{[\s\S]*?return\s*")([^\"]+)(\")',
        re.DOTALL,
    )
    # callable replacement is safest
    return pattern.sub(lambda m: m.group(1) + version + m.group(3), content)


def update_php_source_version(content: str, version: str, path: Path) -> str:
    return re.sub(
        r"(public\s+const\s+VERSION\s*=\s*')([^']+)(')",
        lambda m: m.group(1) + version + m.group(3),
        content,
    )


def update_java_source_version(content: str, version: str, path: Path) -> str:
    content = re.sub(
        r"(@version\s+)([^\s]+)",
        lambda m: m.group(1) + version,
        content,
        count=1,
    )
    return re.sub(
        r'((?:public\s+)?static\s+final\s+String\s+VERSION\s*=\s*")([^\"]+)(";)',
        lambda m: m.group(1) + version + m.group(3),
        content,
        count=1,
    )


def update_lua_rockspec(content: str, version: str, path: Path) -> str:
    """Update Lua rockspec version and handle file rename.

    LuaRocks requires rockspec files to be named with the version.
    This repo uses prerelease filenames like 3.0.0-1.
    """
    rockspec_version = normalize_lua_rockspec_version(version)

    # Update version field
    new_content = re.sub(
        r'(^version\s*=\s*")([^\"]+)(")',
        lambda m: m.group(1) + rockspec_version + m.group(3),
        content,
        flags=re.MULTILINE,
    )

    # Update tag in source block
    new_content = re.sub(
        r'(tag\s*=\s*")([^\"]+)(")',
        lambda m: m.group(1) + "v" + version + m.group(3),
        new_content,
    )

    return new_content


def rename_lua_rockspec(version: str, dry_run: bool = False) -> bool:
    """Rename Lua rockspec file to match version.

    LuaRocks requires the filename to match the version.
    """
    lua_dir = ROOT_DIR / "bindings" / "lua"
    rockspec_version = normalize_lua_rockspec_version(version)

    new_name = f"strling-{rockspec_version}.rockspec"
    new_path = lua_dir / new_name

    # Find existing rockspec file
    existing_rockspecs = list(lua_dir.glob("strling-*.rockspec"))
    if not existing_rockspecs:
        logger.warning("No existing rockspec file found in %s", lua_dir)
        return False

    old_path = existing_rockspecs[0]

    if old_path.name == new_name:
        logger.debug("Rockspec filename already correct: %s", new_name)
        return True

    if dry_run:
        logger.info("Would rename %s to %s", old_path.name, new_name)
    else:
        old_path.rename(new_path)
        logger.info("Renamed %s to %s", old_path.name, new_name)

    return True


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Sync project version across bindings")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check",
        action="store_true",
        help="Check if versions are in sync without modifying",
    )
    mode.add_argument("--write", action="store_true", help="Write changes to files")
    args = parser.parse_args(argv)

    if not args.check and not args.write:
        parser.print_usage()
        return 1

    try:
        version = get_source_version()
    except Exception as exc:
        logger.exception("Failed to determine source version: %s", exc)
        return 2

    logger.info("Governed repository projection: %s", version)

    # Retained updater helpers are compatibility APIs; registry probes own writes.
    try:
        policy = unique_json(SOURCE_FILE.read_text(encoding="utf-8"))
        planned = projected_contents(ROOT_DIR, policy, version)
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
        logger.error("Version projection refused: %s", exc)
        return 2
    drift = [
        path
        for path, content in planned.items()
        if path.read_text(encoding="utf-8") != content
    ]
    for path in drift:
        logger.info(
            "%s %s", "Updating" if args.write else "Stale", path.relative_to(ROOT_DIR)
        )
    if args.check:
        return 3 if drift else 0
    try:
        write_projection(planned)
    except OSError as exc:
        logger.error("Version projection write failed: %s", exc)
        return 2
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
