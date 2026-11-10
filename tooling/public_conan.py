"""Reconstruct a Conan consumer cache exclusively from authenticated public files."""

from __future__ import annotations

import copy
import hashlib
import io
import tarfile
from pathlib import Path

from tooling.conan_release import cache_inventory
from tooling.public_retrieval import RetrievalError
from tooling.release_payload import archive_files
from tooling.release_supply_chain import _normalized_conan_sha256


def reconstruct_cache(
    *,
    exemplar: Path,
    expected_sha256: str,
    inventory: dict,
    public_files: dict[str, bytes],
    endpoint: str,
    version: str,
    output: Path,
) -> dict:
    """Reuse certified layout metadata, never certified executable payload bytes."""
    if (
        hashlib.sha256(exemplar.read_bytes()).hexdigest() != expected_sha256
        or output.exists()
    ):
        raise RetrievalError(
            "artifact-integrity", "invalid Conan cache exemplar or occupied output"
        )
    layout = cache_inventory(exemplar, version)
    original = archive_files(exemplar)
    revision, recipe = next(iter(layout["strling/" + version]["revisions"].items()))
    if revision != inventory["recipe_revision"]:
        raise RetrievalError(
            "source-identity", "Conan recipe revision differs from certified cache"
        )
    base = (
        endpoint.rstrip("/") + f"/v2/conans/strling/{version}/_/_/revisions/{revision}"
    )
    restored = {"pkglist.json": original["pkglist.json"]}

    def read(group, name, url):
        payload = public_files.get(url + "/files/" + name)
        if payload is None or hashlib.sha256(payload).hexdigest() != inventory[
            "file_sha256"
        ].get(group + name):
            raise RetrievalError(
                "artifact-integrity",
                "required Conan public content is missing or changed",
            )
        return payload

    prefix = recipe["recipe_folder"]
    for name in ("conanfile.py", "conanmanifest.txt"):
        restored[prefix + "/e/" + name] = read("recipe/", name, base)
    for archive, target in (("conan_export.tgz", "/e/"), ("conan_sources.tgz", "/es/")):
        if "recipe/" + archive in inventory["file_sha256"]:
            for name, payload in archive_files(
                io.BytesIO(read("recipe/", archive, base))
            ).items():
                restored[prefix + target + name] = payload
                if target == "/es/":
                    restored[prefix + "/s/" + name] = payload
    for package_id, package in recipe["packages"].items():
        binary_revision, binary = next(iter(package["revisions"].items()))
        if inventory["packages"].get(package_id) != binary_revision:
            raise RetrievalError(
                "source-identity", "Conan binary revision differs from certified cache"
            )
        package_url = base + "/packages/" + package_id + "/revisions/" + binary_revision
        group = "packages/" + package_id + "/"
        target = binary["package_folder"] + "/"
        for name in ("conaninfo.txt", "conanmanifest.txt"):
            restored[target + name] = read(group, name, package_url)
        for name, payload in archive_files(
            io.BytesIO(read(group, "conan_package.tgz", package_url))
        ).items():
            restored[target + name] = payload
    if set(restored) != set(original):
        raise RetrievalError(
            "artifact-integrity",
            "public Conan transport cannot reconstruct the certified complete cache graph",
        )
    # Header metadata comes from the authenticated exemplar. Every nonmetadata
    # byte above comes from the independently retrieved revision files.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(exemplar, "r:*") as template, output.open("xb") as stream:
        with tarfile.open(fileobj=stream, mode="w:gz") as archive:
            for old in template:
                if old.isdir():
                    archive.addfile(copy.copy(old))
                    continue
                item = copy.copy(old)
                payload = restored[item.name]
                item.size = len(payload)
                archive.addfile(item, io.BytesIO(payload))
    expected_normalized = _normalized_conan_sha256(exemplar)
    if _normalized_conan_sha256(output) != expected_normalized:
        raise RetrievalError(
            "artifact-integrity", "public Conan cache exceeds registered normalization"
        )
    return {
        "status": "passed",
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "normalized_sha256": expected_normalized,
        "files": len(restored),
        "payload_source": "public-revision-files",
    }
