"""Explicitly synthetic registry responses backed by certified staged subjects.

This module has no public transport and cannot produce public verification.
It exercises protocol decoders and authentication using retained package bytes.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import tarfile
import tomllib
from pathlib import Path
from urllib.parse import quote

from tooling.public_authentication import subject_checksums
from tooling.public_retrieval import FixtureTransport, RetrievalError
from tooling.release_payload import archive_files, unique_yaml
from tooling.release_supply_chain import canonical_json, load_json


def materialize_exports(
    *, manifest: dict, evidence: Path, exports: Path, source_sha: str, output: Path
) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    files = {}
    for artifact in manifest["artifacts"]:
        checks = subject_checksums(evidence, artifact)
        directory = exports / (
            "certified-" + artifact["id"].removeprefix("release:") + "-" + source_sha
        )
        kind = artifact["artifact_policy"]["subject_kind"]
        if kind in {"source-tree", "registry-assembled"}:
            sbom = load_json(
                evidence.parent / "sbom" / (artifact["surface"] + ".spdx.json")
            )
            rows = {
                row["fileName"]: next(
                    c["checksumValue"]
                    for c in row["checksums"]
                    if c["algorithm"] == "SHA256"
                )
                for row in sbom["files"]
            }
            prefix = (
                Path(next(iter(checks)))
                if kind == "registry-assembled"
                else Path(os.path.commonpath([str(Path(name).parent) for name in rows]))
            )
        else:
            rows = checks
            prefix = Path(os.path.commonpath([str(Path(name).parent) for name in rows]))
        for name, digest in rows.items():
            path = directory / Path(name).relative_to(prefix)
            payload = path.read_bytes()
            if path.is_symlink() or hashlib.sha256(payload).hexdigest() != digest:
                raise RetrievalError(
                    "artifact-integrity", "staged export differs from its signed graph"
                )
            target = output / name
            if target.exists():
                if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                    raise RetrievalError(
                        "artifact-integrity", "staged exports disagree on shared bytes"
                    )
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
            files[name] = digest
    return {
        "authority": "staged",
        "files": len(files),
        "files_sha256": hashlib.sha256(canonical_json(files)).hexdigest(),
    }


def tar_bytes(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, payload in sorted(files.items()):
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode, entry.mtime = len(payload), 0o644, 0
            archive.addfile(entry, io.BytesIO(payload))
    return stream.getvalue()


def protocol_fixture(
    *,
    artifact: dict,
    evidence: Path,
    staged: Path,
    source: Path,
    source_sha: str,
    source_tree: str,
    version: str,
) -> tuple[FixtureTransport, dict, dict]:
    registry, name = artifact["registry"], artifact["package_name"]
    destination = {
        "artifact_id": artifact["id"],
        "registry": registry,
        "package_name": name,
        "registry_owner": "STRLING",
        "tier": artifact["distribution_contract"]["tier"],
    }
    subjects = subject_checksums(evidence, artifact)
    responses = {}

    def document(url, value):
        responses[url] = canonical_json(value)

    if registry.startswith("github-tag:"):
        tag = registry.removeprefix("github-tag:").replace("VERSION", version)
        base = "https://api.github.com/repos/strling-lang/strling/git/"
        document(
            base + "ref/tags/" + quote(tag, safe=""),
            {
                "ref": "refs/tags/" + tag,
                "object": {"type": "commit", "sha": source_sha},
            },
        )
        document(
            base + "commits/" + source_sha,
            {"sha": source_sha, "tree": {"sha": source_tree}},
        )
        sbom = load_json(
            evidence.parent / "sbom" / (artifact["surface"] + ".spdx.json")
        )
        responses[
            "https://codeload.github.com/strling-lang/strling/tar.gz/" + source_sha
        ] = tar_bytes(
            {
                "strling-" + source_sha + "/" + row["fileName"]: (
                    staged / row["fileName"]
                ).read_bytes()
                for row in sbom["files"]
            }
        )
    elif registry == "pypi.org":
        project = tomllib.loads(
            (source / "bindings/python/pyproject.toml").read_text()
        )["project"]
        rows = []
        for subject, digest in subjects.items():
            filename = Path(subject).name
            url = "https://files.pythonhosted.org/packages/synthetic/" + filename
            rows.append(
                {
                    "filename": filename,
                    "url": url,
                    "digests": {"sha256": digest},
                    "yanked": False,
                }
            )
            responses[url] = (staged / subject).read_bytes()
        document(
            f"https://pypi.org/pypi/{name}/{version}/json",
            {
                "info": {
                    "name": name,
                    "version": version,
                    "summary": project["description"],
                    "license_expression": project["license"],
                    "requires_python": ",".join(
                        sorted(project["requires-python"].split(","))
                    ),
                    "project_urls": project["urls"],
                },
                "urls": rows,
            },
        )
    elif registry == "npmjs.org":
        package = load_json(source / "bindings/typescript/package.json")
        payload = (staged / next(iter(subjects))).read_bytes()
        url = (
            "https://registry.npmjs.org/@strling-lang/strling/-/strling-"
            + version
            + ".tgz"
        )
        package["dist"] = {"tarball": url, "shasum": hashlib.sha1(payload).hexdigest()}
        document(
            "https://registry.npmjs.org/" + quote(name, safe="@") + "/" + version,
            package,
        )
        responses[url] = payload
    elif registry == "crates.io":
        package = tomllib.loads((source / "Cargo.toml").read_text())["package"]
        row = {
            key: package[key]
            for key in (
                "license",
                "description",
                "homepage",
                "repository",
                "documentation",
            )
        }
        row.update(
            crate=name,
            num=version,
            yanked=False,
            checksum=next(iter(subjects.values())),
            rust_version=package["rust-version"],
        )
        document(f"https://crates.io/api/v1/crates/{name}/{version}", {"version": row})
        responses[f"https://static.crates.io/crates/{name}/{name}-{version}.crate"] = (
            staged / next(iter(subjects))
        ).read_bytes()
    elif registry == "nuget.org":
        document(
            "https://api.nuget.org/v3/index.json",
            {
                "resources": [
                    {
                        "@type": "PackageBaseAddress/3.0.0",
                        "@id": "https://api.nuget.org/v3-flatcontainer/",
                    }
                ]
            },
        )
        payload = (staged / next(iter(subjects))).read_bytes()
        inner = archive_files(io.BytesIO(payload))
        prefix = (
            "https://api.nuget.org/v3-flatcontainer/"
            + name.lower()
            + "/"
            + version
            + "/"
            + name.lower()
        )
        responses[prefix + ".nuspec"] = next(
            value for key, value in inner.items() if key.endswith(".nuspec")
        )
        responses[prefix + "." + version + ".nupkg"] = payload
    elif registry == "maven-central":
        from tooling.maven_release import central_files

        for coordinate, payload in central_files(
            staged, artifact, version, [{"name": path} for path in subjects]
        ).items():
            responses["https://repo1.maven.org/maven2/" + coordinate] = payload
    elif registry == "pub.dev":
        subject = next(iter(subjects))
        package = unique_yaml((source / "bindings/dart/pubspec.yaml").read_bytes())
        root = staged / subject
        payload = tar_bytes(
            {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
        )
        url = "https://pub.dev/api/archives/strling-" + version + ".tar.gz"
        document(
            "https://pub.dev/api/packages/" + name + "/versions/" + version,
            {
                "version": version,
                "pubspec": package,
                "archive_url": url,
                "archive_sha256": hashlib.sha256(payload).hexdigest(),
            },
        )
        responses[url] = payload
    elif registry == "rubygems.org":
        text = (source / "bindings/ruby/strling.gemspec").read_text()
        description = re.search(r's.description = "([^"]+)"', text)[1]
        document(
            f"https://rubygems.org/api/v2/rubygems/{name}/versions/{version}.json",
            {
                "name": name,
                "version": version,
                "sha": next(iter(subjects.values())),
                "info": description,
                "homepage_uri": "https://github.com/strling-lang/strling",
                "licenses": ["Apache-2.0"],
                "source_code_uri": "https://github.com/strling-lang/strling",
            },
        )
        responses[f"https://rubygems.org/downloads/{name}-{version}.gem"] = (
            staged / next(iter(subjects))
        ).read_bytes()
    elif registry == "cpan":
        url = f"https://cpan.metacpan.org/authors/id/S/ST/STRLING/STRling-{version}.tar.gz"
        document(
            f"https://fastapi.metacpan.org/v1/release/STRLING/STRling-{version}",
            {
                "author": "STRLING",
                "distribution": name,
                "version": version,
                "download_url": url,
                "license": ["apache_2_0"],
            },
        )
        responses[url] = (staged / next(iter(subjects))).read_bytes()
    elif registry == "luarocks.org":
        for subject in subjects:
            responses[
                "https://luarocks.org/manifests/STRLING/" + Path(subject).name
            ] = (staged / subject).read_bytes()
    elif registry == "conan":
        from tooling.conan_release import upload_inventory

        destination["registry_endpoint"] = "https://conan.example.test"
        for subject in subjects:
            if not subject.endswith(".upload.zip"):
                continue
            inventory, files = upload_inventory(staged / subject, version)
            base = (
                "https://conan.example.test/v2/conans/strling/"
                + version
                + "/_/_/revisions/"
                + inventory["recipe_revision"]
            )
            groups = {"recipe/": base}
            groups.update(
                {
                    "packages/" + package + "/": base
                    + "/packages/"
                    + package
                    + "/revisions/"
                    + revision
                    for package, revision in inventory["packages"].items()
                }
            )
            for group, url in groups.items():
                selected = {
                    path[len(group) :]: payload
                    for path, payload in files.items()
                    if path.startswith(group)
                }
                document(url + "/files", {"files": {key: {} for key in selected}})
                for key, payload in selected.items():
                    responses[url + "/files/" + key] = payload
    else:
        raise RetrievalError(
            "fixture-missing", "no certified protocol fixture for " + registry
        )
    documents = {"artifact_id": artifact["id"]}
    for kind, suffix in (("sbom", ".spdx.json"), ("provenance", ".intoto.json")):
        payload = (evidence.parent / kind / (artifact["surface"] + suffix)).read_bytes()
        url = (
            "https://evidence.example.test/" + artifact["id"].replace(":", "-") + suffix
        )
        responses[url] = payload
        documents[kind] = {"url": url, "sha256": hashlib.sha256(payload).hexdigest()}
    readme = (
        "bindings/rust/README.md"
        if artifact["id"] == "release:rust"
        else artifact["package_root"] + "/README.md"
    )
    payload = (source / readme).read_bytes()
    url = "https://evidence.example.test/" + readme
    responses[url] = payload
    documents["documentation"] = {
        "url": url,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    return FixtureTransport(responses), destination, documents
