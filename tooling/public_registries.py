"""Official public protocol adapters; expectations come from authenticated data.

Adapters retrieve data only. They neither import packages nor invoke installers,
and cannot turn their retrieval result into public release verification.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit

from tooling.public_distribution import strict_json
from tooling.public_retrieval import RetrievalError


def require(value: bool, detail: str, category: str = "metadata") -> None:
    if not value:
        raise RetrievalError(category, detail)


def coordinate_version(version: str, ecosystem: str) -> str:
    require(
        re.fullmatch(
            r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-rc\.[1-9][0-9]*)?",
            version,
        )
        is not None,
        "unregistered release version",
    )
    if ecosystem == "pypi.org":
        return version.replace("-rc.", "rc")
    if ecosystem == "luarocks.org":
        return version + "-1"
    if ecosystem == "rubygems.org":
        return version.replace("-", ".")
    return version


def retrieve(
    transport,
    artifact: dict,
    version: str,
    subjects: dict[str, str],
    destination: dict,
    *,
    source_sha: str,
    conan_inventories: list[dict] | None = None,
) -> dict:
    """Retrieve the complete registered subject set, without a local fallback.

    The caller must authenticate subjects, destination and source before entry.
    Returned bytes are untrusted until the supply-chain authentication stage.
    """
    registry = artifact["registry"]
    name = artifact["package_name"]
    coordinate = coordinate_version(version, registry)
    require(
        destination.get("artifact_id") == artifact["id"]
        and destination.get("registry") == registry
        and destination.get("package_name") == name,
        "destination differs from governed registry",
        "source-identity",
    )
    files = {}
    metadata = {}

    def data(url):
        return strict_json(transport.get(url))

    def fetch(subject, url, checksum=None):
        require(
            subject in subjects and subject not in files,
            "unexpected or duplicate public subject",
            "artifact-integrity",
        )
        payload = transport.get(url, maximum=512 * 1024 * 1024)
        if checksum is not None:
            require(
                re.fullmatch(r"[0-9a-f]{64}", checksum) is not None
                and hashlib.sha256(payload).hexdigest() == checksum,
                "registry checksum differs from downloaded bytes",
                "artifact-integrity",
            )
        files[subject] = payload

    def by_basename():
        result = {PurePosixPath(path).name: path for path in subjects}
        require(
            len(result) == len(subjects),
            "ambiguous certified public filenames",
            "contract",
        )
        return result

    if registry.startswith("github-tag:"):
        require(
            re.fullmatch(r"[0-9a-f]{40}", source_sha) is not None,
            "invalid certified source",
            "source-identity",
        )
        tag = registry.removeprefix("github-tag:").replace("VERSION", version)
        base = "https://api.github.com/repos/strling-lang/strling/git/"
        metadata = data(base + "ref/tags/" + quote(tag, safe=""))
        require(
            metadata.get("ref") == "refs/tags/" + tag,
            "wrong public tag",
            "source-identity",
        )
        obj = metadata.get("object", {})
        for _ in range(4):
            if obj.get("type") == "commit":
                break
            require(
                obj.get("type") == "tag"
                and re.fullmatch(r"[0-9a-f]{40}", obj.get("sha", "")) is not None,
                "malformed tag object",
                "source-identity",
            )
            annotated = data(base + "tags/" + obj["sha"])
            require(
                annotated.get("sha") == obj["sha"],
                "tag object identity mismatch",
                "source-identity",
            )
            obj = annotated.get("object", {})
        require(
            obj.get("type") == "commit" and obj.get("sha") == source_sha,
            "public tag resolves to another source",
            "source-identity",
        )
        commit = data(base + "commits/" + source_sha)
        require(
            commit.get("sha") == source_sha,
            "public commit identity differs",
            "source-identity",
        )
        payload = transport.get(
            "https://codeload.github.com/strling-lang/strling/tar.gz/" + source_sha,
            maximum=512 * 1024 * 1024,
        )
        return {
            "authority": transport.authority,
            "metadata": metadata,
            "source_commit": source_sha,
            "source_tree": commit.get("tree", {}).get("sha"),
            "source_archive": payload,
            "tag": tag,
            "package_root": artifact["package_root"],
        }
    if registry == "pypi.org":
        metadata = data(
            f"https://pypi.org/pypi/{quote(name, safe='')}/{coordinate}/json"
        )
        info = metadata.get("info", {})
        require(
            info.get("name", "").lower() == name.lower()
            and info.get("version") == coordinate,
            "wrong PyPI coordinate",
        )
        expected = by_basename()
        rows = metadata.get("urls", [])
        names = [row.get("filename") for row in rows]
        require(
            len(names) == len(set(names)) and set(names) == set(expected),
            "missing, duplicate or extra PyPI files",
            "artifact-integrity",
        )
        for row in rows:
            require(row.get("yanked") is False, "PyPI file is withdrawn")
            fetch(
                expected[row["filename"]],
                row["url"],
                row.get("digests", {}).get("sha256"),
            )
    elif registry == "npmjs.org":
        metadata = data(
            "https://registry.npmjs.org/" + quote(name, safe="@") + "/" + coordinate
        )
        require(
            metadata.get("name") == name and metadata.get("version") == coordinate,
            "wrong npm coordinate",
        )
        require(len(subjects) == 1, "npm subject set mismatch", "contract")
        dist = metadata.get("dist", {})
        fetch(next(iter(subjects)), dist["tarball"])
        require(
            dist.get("shasum") == hashlib.sha1(next(iter(files.values()))).hexdigest(),
            "npm digest mismatch",
            "artifact-integrity",
        )
    elif registry == "crates.io":
        metadata = data(f"https://crates.io/api/v1/crates/{name}/{coordinate}")
        row = metadata.get("version", {})
        require(
            row.get("crate") == name
            and row.get("num") == coordinate
            and row.get("yanked") is False,
            "wrong or yanked Cargo coordinate",
        )
        require(len(subjects) == 1, "Cargo subject set mismatch", "contract")
        fetch(
            next(iter(subjects)),
            f"https://static.crates.io/crates/{name}/{name}-{coordinate}.crate",
            row.get("checksum"),
        )
    elif registry == "nuget.org":
        index = data("https://api.nuget.org/v3/index.json")
        bases = [
            row["@id"]
            for row in index.get("resources", [])
            if row.get("@type") == "PackageBaseAddress/3.0.0"
        ]
        require(
            bases == ["https://api.nuget.org/v3-flatcontainer/"],
            "unexpected NuGet content authority",
        )
        package = name.lower()
        prefix = bases[0] + package + "/" + coordinate.lower() + "/" + package
        metadata = {"nuspec": transport.get(prefix + ".nuspec")}
        require(len(subjects) == 1, "NuGet subject set mismatch", "contract")
        fetch(next(iter(subjects)), prefix + "." + coordinate.lower() + ".nupkg")
    elif registry == "maven-central":
        mappings = {}
        for subject in subjects:
            basename = PurePosixPath(subject).name
            if basename in {"pom.xml", "pom-default.xml"}:
                module = (
                    "strling-jvm"
                    if subject.startswith("bindings/jvm/")
                    else name.split(":")[1]
                )
                basename = module + "-" + coordinate + ".pom"
            else:
                require(
                    "-" + coordinate in basename, "Maven classifier has wrong version"
                )
                module = basename.split("-" + coordinate)[0]
            require(
                module
                in (
                    {"strling", "strling-jvm"}
                    if artifact["id"] == "release:java"
                    else {"strling-kotlin"}
                ),
                "unregistered Maven companion",
            )
            url = (
                "https://repo1.maven.org/maven2/com/strling/"
                + module
                + "/"
                + coordinate
                + "/"
                + basename
            )
            require(url not in mappings, "duplicate Maven coordinate")
            mappings[url] = subject
            fetch(subject, url)
        metadata = {"coordinates": sorted(mappings)}
    elif registry == "pub.dev":
        metadata = data(
            "https://pub.dev/api/packages/" + name + "/versions/" + coordinate
        )
        require(
            metadata.get("version") == coordinate
            and metadata.get("pubspec", {}).get("name") == name,
            "wrong pub.dev coordinate",
        )
        require(len(subjects) == 1, "Dart subject set mismatch", "contract")
        fetch(
            next(iter(subjects)),
            metadata["archive_url"],
            metadata.get("archive_sha256"),
        )
    elif registry == "rubygems.org":
        metadata = data(
            f"https://rubygems.org/api/v2/rubygems/{name}/versions/{coordinate}.json"
        )
        require(
            metadata.get("name") == name and metadata.get("version") == coordinate,
            "wrong RubyGems coordinate",
        )
        require(len(subjects) == 1, "Ruby subject set mismatch", "contract")
        fetch(
            next(iter(subjects)),
            f"https://rubygems.org/downloads/{name}-{coordinate}.gem",
            metadata.get("sha"),
        )
    elif registry == "cpan":
        owner = destination.get("registry_owner", "")
        require(
            re.fullmatch(r"[A-Z][A-Z0-9]+", owner) is not None,
            "exact approved PAUSE owner is required",
            "contract",
        )
        metadata = data(
            f"https://fastapi.metacpan.org/v1/release/{owner}/{name}-{coordinate}"
        )
        require(
            metadata.get("author") == owner
            and metadata.get("distribution") == name
            and str(metadata.get("version")) == coordinate,
            "wrong CPAN coordinate or owner",
        )
        expected = f"https://cpan.metacpan.org/authors/id/{owner[0]}/{owner[:2]}/{owner}/{name}-{coordinate}.tar.gz"
        require(
            metadata.get("download_url") == expected,
            "unexpected CPAN download location",
        )
        require(len(subjects) == 1, "CPAN subject set mismatch", "contract")
        fetch(next(iter(subjects)), expected)
    elif registry == "luarocks.org":
        owner = destination.get("registry_owner", "")
        require(
            re.fullmatch(r"[A-Za-z0-9_-]+", owner) is not None,
            "exact approved LuaRocks owner is required",
            "contract",
        )
        for basename, subject in by_basename().items():
            require(
                basename
                in {f"{name}-{coordinate}.rockspec", f"{name}-{coordinate}.src.rock"},
                "unexpected LuaRocks payload",
            )
            fetch(subject, "https://luarocks.org/manifests/" + owner + "/" + basename)
        metadata = {"owner": owner, "version": coordinate, "name": name}
    elif registry == "conan":
        endpoint = destination.get("registry_endpoint", "")
        parsed = urlsplit(endpoint)
        require(
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment,
            "exact public Conan endpoint is required",
            "contract",
        )
        require(
            bool(conan_inventories),
            "authenticated Conan upload inventory is required",
            "contract",
        )
        remote_files = {}
        for inventory in conan_inventories:
            require(
                inventory.get("product_version") == version,
                "wrong Conan inventory version",
            )
            revision = inventory.get("recipe_revision", "")
            require(
                re.fullmatch(r"[0-9a-f]{32}", revision) is not None,
                "invalid Conan recipe revision",
            )
            prefix = (
                endpoint.rstrip("/")
                + f"/v2/conans/{name}/{coordinate}/_/_/revisions/{revision}"
            )
            groups = {"recipe/": prefix}
            for package_id, package_revision in inventory["packages"].items():
                require(
                    re.fullmatch(r"[0-9a-f]{40}", package_id) is not None
                    and re.fullmatch(r"[0-9a-f]{32}", package_revision) is not None,
                    "invalid Conan binary revision",
                )
                groups["packages/" + package_id + "/"] = (
                    prefix
                    + "/packages/"
                    + package_id
                    + "/revisions/"
                    + package_revision
                )
            for group, base in groups.items():
                expected = {
                    path[len(group) :]: digest
                    for path, digest in inventory["file_sha256"].items()
                    if path.startswith(group)
                }
                snapshot = data(base + "/files")
                require(
                    set(snapshot.get("files", {})) == set(expected),
                    "public Conan file inventory differs",
                    "artifact-integrity",
                )
                for filename, digest in expected.items():
                    require(
                        re.fullmatch(r"[A-Za-z0-9_.-]+", filename) is not None,
                        "unsafe Conan filename",
                        "security",
                    )
                    url = base + "/files/" + filename
                    payload = transport.get(url, maximum=512 * 1024 * 1024)
                    require(
                        hashlib.sha256(payload).hexdigest() == digest,
                        "Conan public bytes differ from certified upload",
                        "artifact-integrity",
                    )
                    if url in remote_files:
                        require(
                            remote_files[url] == payload,
                            "conflicting public Conan observations",
                            "artifact-integrity",
                        )
                    remote_files[url] = payload
        return {
            "authority": transport.authority,
            "metadata": {"endpoint": endpoint, "version": coordinate},
            "conan_files": remote_files,
        }
    else:
        raise RetrievalError(
            "contract", "registry adapter is not qualified: " + registry
        )
    require(
        set(files) == set(subjects),
        "public subject set is incomplete",
        "artifact-integrity",
    )
    return {"authority": transport.authority, "metadata": metadata, "files": files}
