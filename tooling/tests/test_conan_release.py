import io
import json
import tarfile
from pathlib import Path

import pytest

from tooling.conan_release import (
    cache_inventory,
    materialize_upload,
    verify_upload_archive,
    upload_inventory,
    _upload,
)


def cache_fixture(tmp_path):
    recipe_folder = "strli-fixture"
    package_folder = "b/strli-fixture/p"
    metadata = {
        "strling/4.0.0": {
            "revisions": {
                "a" * 32: {
                    "recipe_folder": recipe_folder,
                    "timestamp": 0,
                    "packages": {
                        "b" * 40: {
                            "revisions": {
                                "c" * 32: {
                                    "package_folder": package_folder,
                                    "timestamp": 0,
                                }
                            }
                        }
                    },
                }
            }
        }
    }
    files = {
        "pkglist.json": json.dumps(metadata).encode(),
        recipe_folder
        + "/e/conanfile.py": b'raise RuntimeError("CANDIDATE RECIPE EXECUTED")\n',
        recipe_folder + "/e/conanmanifest.txt": b"0\nconanfile.py: fixture\n",
        recipe_folder + "/es/source/LICENSE": b"Apache-2.0",
        package_folder + "/conaninfo.txt": b"[settings]\nos=Linux\narch=x86_64\n",
        package_folder + "/conanmanifest.txt": b"0\nlib/library.a: fixture\n",
        package_folder + "/lib/library.a": b"exact approved static library bytes",
    }
    path = tmp_path / "cache.tgz"
    with tarfile.open(path, "w:gz") as archive:
        for name, data in sorted(files.items()):
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
    return path, files


def test_transport_never_imports_candidate_recipe_and_preserves_payload(
    tmp_path, monkeypatch
):
    pytest.importorskip(
        "conan", reason="protected publication uses the pinned Linux client"
    )
    from conan.internal.loader import ConanFileLoader
    from conan.api.conan_api import ConanAPI

    path, files = cache_fixture(tmp_path)
    envelope = tmp_path / "cache.upload.zip"
    materialize_upload(path, envelope, "4.0.0")
    verify_upload_archive(envelope, path, "4.0.0")
    metadata, certified = upload_inventory(envelope, "4.0.0")
    calls = []

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "protected transport must never load recipes or access a real registry"
        )

    monkeypatch.setattr(ConanFileLoader, "load_basic", forbidden)
    import requests

    monkeypatch.setattr(requests.Session, "request", forbidden)

    class Manager:
        def authenticate(self, remote, username, password):
            assert remote.url == "https://registry.example.invalid"
            assert (username, password) == ("test-only", "not-a-real-secret")

        def get_recipe_revisions(self, ref, remote):
            return []

        def upload_recipe(self, ref, payloads, remote):
            calls.append(
                (
                    "recipe",
                    {
                        name: Path(value).read_bytes()
                        for name, value in payloads.items()
                    },
                )
            )

        def upload_package(self, pref, payloads, remote):
            calls.append(
                (
                    "packages/" + pref.package_id,
                    {
                        name: Path(value).read_bytes()
                        for name, value in payloads.items()
                    },
                )
            )

    manager = Manager()
    monkeypatch.setattr(
        ConanAPI._ApiHelpers, "remote_manager", property(lambda self: manager)
    )
    result = _upload(
        [envelope],
        "4.0.0",
        "https://registry.example.invalid",
        "test-only",
        "not-a-real-secret",
    )
    assert json.loads(result)["version"] == "4.0.0"
    assert len(calls) == 2
    for group, payloads in calls:
        for name, data in payloads.items():
            assert data == certified[group + "/" + name]
    assert certified["recipe/conanfile.py"].startswith(b"raise RuntimeError")


def test_upload_archive_rejects_payload_substitution(tmp_path):
    path, _ = cache_fixture(tmp_path)
    envelope = tmp_path / "cache.upload.zip"
    materialize_upload(path, envelope, "4.0.0")
    metadata, files = upload_inventory(envelope, "4.0.0")
    assert metadata["product_version"] == "4.0.0"
    import zipfile

    with zipfile.ZipFile(envelope, "w") as archive:
        archive.writestr("upload.json", json.dumps(metadata))
        for name, data in files.items():
            archive.writestr(
                name,
                data + b"substituted" if name.endswith("conan_package.tgz") else data,
            )
    with pytest.raises(ValueError, match="bytes changed"):
        upload_inventory(envelope, "4.0.0")


@pytest.mark.parametrize("alias", ["../../outside", "/absolute", "C:\\outside", "a/b"])
def test_cache_rejects_unsafe_recipe_alias(tmp_path, alias):
    path = tmp_path / "bad.tgz"
    document = {
        "strling/4.0.0": {
            "revisions": {"a" * 32: {"recipe_folder": alias, "packages": {}}}
        }
    }
    data = json.dumps(document).encode()
    with tarfile.open(path, "w:gz") as archive:
        entry = tarfile.TarInfo("pkglist.json")
        entry.size = len(data)
        archive.addfile(entry, io.BytesIO(data))
    with pytest.raises(ValueError, match="alias"):
        cache_inventory(path, "4.0.0")
