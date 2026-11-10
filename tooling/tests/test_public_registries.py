"""Protocol fixtures use explicit synthetic authority for every registered route."""

import hashlib
import json
from pathlib import Path
from urllib.parse import quote

import pytest

from tooling.public_registries import retrieve
from tooling.public_retrieval import FixtureTransport, RetrievalError

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads(
    (ROOT / "tests/certification/release-supply-chain/1.0/manifest.json").read_text()
)
ARTIFACTS = MANIFEST["artifacts"]
SOURCE = "a" * 40
PAYLOAD = b"synthetic protocol payload, never a certified package"
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


def fixture(artifact):
    registry, name = artifact["registry"], artifact["package_name"]
    destination = {
        "artifact_id": artifact["id"],
        "registry": registry,
        "package_name": name,
        "registry_owner": "STRLING",
    }
    subjects = {"package.archive": DIGEST}
    responses = {}
    extra = {}

    def document(url, data):
        responses[url] = json.dumps(data).encode()

    if registry.startswith("github-tag:"):
        tag = registry.removeprefix("github-tag:").replace("VERSION", "4.0.0")
        base = "https://api.github.com/repos/strling-lang/strling/git/"
        document(
            base + "ref/tags/" + quote(tag, safe=""),
            {"ref": "refs/tags/" + tag, "object": {"type": "commit", "sha": SOURCE}},
        )
        document(base + "commits/" + SOURCE, {"sha": SOURCE, "tree": {"sha": "b" * 40}})
        responses[
            "https://codeload.github.com/strling-lang/strling/tar.gz/" + SOURCE
        ] = PAYLOAD
    elif registry == "pypi.org":
        document(
            f"https://pypi.org/pypi/{name}/4.0.0/json",
            {
                "info": {"name": name, "version": "4.0.0"},
                "urls": [
                    {
                        "filename": "package.archive",
                        "url": "https://files.pythonhosted.org/package.archive",
                        "digests": {"sha256": DIGEST},
                        "yanked": False,
                    }
                ],
            },
        )
        responses["https://files.pythonhosted.org/package.archive"] = PAYLOAD
    elif registry == "npmjs.org":
        document(
            "https://registry.npmjs.org/" + quote(name, safe="@") + "/4.0.0",
            {
                "name": name,
                "version": "4.0.0",
                "dist": {
                    "tarball": "https://registry.npmjs.org/package.archive",
                    "shasum": hashlib.sha1(PAYLOAD).hexdigest(),
                },
            },
        )
        responses["https://registry.npmjs.org/package.archive"] = PAYLOAD
    elif registry == "crates.io":
        document(
            f"https://crates.io/api/v1/crates/{name}/4.0.0",
            {
                "version": {
                    "crate": name,
                    "num": "4.0.0",
                    "yanked": False,
                    "checksum": DIGEST,
                }
            },
        )
        responses[f"https://static.crates.io/crates/{name}/{name}-4.0.0.crate"] = (
            PAYLOAD
        )
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
        prefix = (
            "https://api.nuget.org/v3-flatcontainer/"
            + name.lower()
            + "/4.0.0/"
            + name.lower()
        )
        responses[prefix + ".nuspec"] = b"<package/>"
        responses[prefix + ".4.0.0.nupkg"] = PAYLOAD
    elif registry == "maven-central":
        module = name.split(":")[1]
        subjects = {f"bindings/{artifact['surface']}/target/{module}-4.0.0.jar": DIGEST}
        responses[
            f"https://repo1.maven.org/maven2/com/strling/{module}/4.0.0/{module}-4.0.0.jar"
        ] = PAYLOAD
    elif registry == "pub.dev":
        document(
            f"https://pub.dev/api/packages/{name}/versions/4.0.0",
            {
                "version": "4.0.0",
                "pubspec": {"name": name},
                "archive_url": "https://pub.dev/package.archive",
                "archive_sha256": DIGEST,
            },
        )
        responses["https://pub.dev/package.archive"] = PAYLOAD
    elif registry == "rubygems.org":
        document(
            f"https://rubygems.org/api/v2/rubygems/{name}/versions/4.0.0.json",
            {"name": name, "version": "4.0.0", "sha": DIGEST},
        )
        responses[f"https://rubygems.org/downloads/{name}-4.0.0.gem"] = PAYLOAD
    elif registry == "cpan":
        url = "https://cpan.metacpan.org/authors/id/S/ST/STRLING/STRling-4.0.0.tar.gz"
        document(
            "https://fastapi.metacpan.org/v1/release/STRLING/STRling-4.0.0",
            {
                "author": "STRLING",
                "distribution": name,
                "version": "4.0.0",
                "download_url": url,
            },
        )
        responses[url] = PAYLOAD
    elif registry == "luarocks.org":
        subjects = {
            "bindings/lua/strling-4.0.0-1." + suffix: DIGEST
            for suffix in ("rockspec", "src.rock")
        }
        for path in subjects:
            responses["https://luarocks.org/manifests/STRLING/" + Path(path).name] = (
                PAYLOAD
            )
    elif registry == "conan":
        destination["registry_endpoint"] = "https://conan.example.test"
        revision, package, binary = "a" * 32, "b" * 40, "c" * 32
        inventory = {
            "product_version": "4.0.0",
            "recipe_revision": revision,
            "packages": {package: binary},
            "file_sha256": {
                "recipe/conanfile.py": DIGEST,
                f"packages/{package}/conan_package.tgz": DIGEST,
            },
        }
        base = f"https://conan.example.test/v2/conans/strling/4.0.0/_/_/revisions/{revision}"
        document(base + "/files", {"files": {"conanfile.py": {}}})
        responses[base + "/files/conanfile.py"] = PAYLOAD
        base += f"/packages/{package}/revisions/{binary}"
        document(base + "/files", {"files": {"conan_package.tgz": {}}})
        responses[base + "/files/conan_package.tgz"] = PAYLOAD
        extra["conan_inventories"] = [inventory]
    else:
        raise AssertionError(
            "fixture missing for registered artifact " + artifact["id"]
        )
    return FixtureTransport(responses), subjects, destination, extra


@pytest.mark.parametrize("artifact", ARTIFACTS, ids=lambda a: a["id"])
def test_every_registered_route_retrieves_synthetic_protocol(artifact):
    transport, subjects, destination, extra = fixture(artifact)
    result = retrieve(
        transport, artifact, "4.0.0", subjects, destination, source_sha=SOURCE, **extra
    )
    assert result["authority"] == "synthetic"
    assert transport.observations
    assert "status" not in result
    assert "release_transition" not in result


@pytest.mark.parametrize("artifact", ARTIFACTS, ids=lambda a: a["id"])
@pytest.mark.parametrize("status", ["NOT_PUBLISHED", "INDETERMINATE"])
def test_absence_and_network_failure_remain_distinct(artifact, status):
    transport, subjects, destination, extra = fixture(artifact)
    for url in transport.responses:
        transport.responses[url] = RetrievalError(
            "missing-coordinate" if status == "NOT_PUBLISHED" else "registry-network",
            "synthetic failure",
            status=status,
        )
    with pytest.raises(RetrievalError) as caught:
        retrieve(
            transport,
            artifact,
            "4.0.0",
            subjects,
            destination,
            source_sha=SOURCE,
            **extra,
        )
    assert caught.value.status == status


@pytest.mark.parametrize("artifact", ARTIFACTS, ids=lambda a: a["id"])
@pytest.mark.parametrize("field", ["registry", "package_name", "artifact_id"])
def test_wrong_destination_rejected_without_retrieval(artifact, field):
    transport, subjects, destination, extra = fixture(artifact)
    destination[field] = "substituted"
    with pytest.raises(RetrievalError):
        retrieve(
            transport,
            artifact,
            "4.0.0",
            subjects,
            destination,
            source_sha=SOURCE,
            **extra,
        )
    assert not transport.observations


@pytest.mark.parametrize(
    "artifact",
    [a for a in ARTIFACTS if a["delivery_kind"] == "source-tag"],
    ids=lambda a: a["id"],
)
def test_wrong_git_commit_rejected(artifact):
    transport, subjects, destination, extra = fixture(artifact)
    with pytest.raises(RetrievalError, match="another source"):
        retrieve(
            transport,
            artifact,
            "4.0.0",
            subjects,
            destination,
            source_sha="b" * 40,
            **extra,
        )
