import hashlib
import io
import shutil
import subprocess
import zipfile

import pytest

from tooling.maven_release import central_files, signed_envelope


def fixture_files(tmp_path):
    files = {}
    for name in ("strling", "strling-jvm"):
        pom = tmp_path / name / "pom.xml"
        pom.parent.mkdir()
        pom.write_text(f"""<project><groupId>com.strling</groupId><artifactId>{name}</artifactId><version>4.0.0</version>
<name>STRling</name><description>Canonical adapter</description><url>https://github.com/strling-lang/strling</url>
<licenses><license><name>Apache License 2.0</name><url>https://www.apache.org/licenses/LICENSE-2.0</url></license></licenses><developers><developer><name>STRling Team</name></developer></developers><scm><connection>scm:git:https://github.com/strling-lang/strling.git</connection><developerConnection>scm:git:ssh://git@github.com/strling-lang/strling.git</developerConnection><url>https://github.com/strling-lang/strling</url></scm></project>""")
        if name == "strling":
            pom.write_text(
                pom.read_text().replace(
                    "</project>",
                    "<dependencies><dependency><groupId>com.strling</groupId><artifactId>strling-jvm</artifactId><version>4.0.0</version></dependency></dependencies></project>",
                )
            )
        files[pom.relative_to(tmp_path).as_posix()] = pom.read_bytes()
        for suffix in (".jar", "-sources.jar", "-javadoc.jar"):
            path = pom.parent / (name + "-4.0.0" + suffix)
            path.write_bytes((name + suffix + " exact certified bytes").encode())
            files[path.relative_to(tmp_path).as_posix()] = path.read_bytes()
    return [{"name": name} for name in files]


def test_central_layout_preserves_all_certified_file_bytes(tmp_path):
    members = fixture_files(tmp_path)
    layout = central_files(tmp_path, {"id": "release:java"}, "4.0.0", members)
    assert len(layout) == 8
    assert all(name.startswith("com/strling/") for name in layout)
    assert sorted(
        hashlib.sha256(data).hexdigest() for data in layout.values()
    ) == sorted(
        hashlib.sha256((tmp_path / member["name"]).read_bytes()).hexdigest()
        for member in members
    )


def test_central_rejects_missing_companion_and_classifier(tmp_path):
    members = fixture_files(tmp_path)
    for incomplete in (
        [row for row in members if not row["name"].startswith("strling-jvm/")],
        [row for row in members if not row["name"].endswith("-sources.jar")],
    ):
        with pytest.raises(ValueError):
            central_files(tmp_path, {"id": "release:java"}, "4.0.0", incomplete)


def test_central_rejects_substituted_coordinate(tmp_path):
    members = fixture_files(tmp_path)
    path = tmp_path / "strling/pom.xml"
    path.write_text(path.read_text().replace("<version>4.0.0", "<version>3.0.0"))
    with pytest.raises(ValueError, match="coordinate"):
        central_files(tmp_path, {"id": "release:java"}, "4.0.0", members)


@pytest.mark.parametrize(
    "mutation", ["stale", "range", "system", "missing", "duplicate"]
)
def test_central_rejects_unsafe_companion_dependency(tmp_path, mutation):
    members = fixture_files(tmp_path)
    path = tmp_path / "strling/pom.xml"
    data = path.read_text()
    dependency = data[
        data.index("<dependencies>") : data.index("</dependencies>")
        + len("</dependencies>")
    ]
    replacements = {
        "stale": dependency.replace("<version>4.0.0", "<version>3.0.0"),
        "range": dependency.replace("<version>4.0.0", "<version>[4.0.0,5.0.0)"),
        "system": dependency.replace(
            "</dependency>",
            "<scope>system</scope><systemPath>/workspace/bridge.jar</systemPath></dependency>",
        ),
        "missing": "",
        "duplicate": dependency.replace(
            "</dependencies>", dependency.removeprefix("<dependencies>")
        ),
    }
    path.write_text(data.replace(dependency, replacements[mutation]))
    with pytest.raises(ValueError, match="companion|system paths"):
        central_files(tmp_path, {"id": "release:java"}, "4.0.0", members)


@pytest.mark.skipif(
    shutil.which("gpg") is None, reason="Linux publication qualification requires GnuPG"
)
def test_signatures_bind_existing_bytes_and_owner_signer(tmp_path):
    home = tmp_path / "test-keyring"
    home.mkdir(mode=0o700)

    def gpg(*args):
        return subprocess.run(
            ["gpg", "--homedir", str(home), "--batch", "--no-tty", *args],
            capture_output=True,
            check=True,
        ).stdout

    try:
        gpg(
            "--passphrase",
            "",
            "--quick-generate-key",
            "STRling local test <test@example.invalid>",
            "ed25519",
            "sign",
            "0",
        )
        fingerprint = next(
            line.split(":")[9]
            for line in gpg("--with-colons", "--list-secret-keys").decode().splitlines()
            if line.startswith("fpr:")
        )
        key = gpg("--armor", "--export-secret-keys", fingerprint).decode()
        files = {
            "com/strling/strling/4.0.0/strling-4.0.0.jar": b"exact approved binary bytes"
        }
        data, digest = signed_envelope(files, key, "", fingerprint)
        assert hashlib.sha256(data).hexdigest() == digest
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for name, payload in files.items():
                assert archive.read(name) == payload
                assert (
                    archive.read(name + ".sha256")
                    == hashlib.sha256(payload).hexdigest().encode()
                )
                assert archive.read(name + ".asc").startswith(
                    b"-----BEGIN PGP SIGNATURE-----"
                )
        with pytest.raises(ValueError, match="owner authorization"):
            signed_envelope(files, key, "", "A" * 40)
    finally:
        subprocess.run(
            ["gpgconf", "--homedir", str(home), "--kill", "gpg-agent"],
            capture_output=True,
        )


@pytest.mark.parametrize(
    "mutation", ["empty-license", "empty-scm", "duplicate-version"]
)
def test_central_rejects_incomplete_or_ambiguous_pom(tmp_path, mutation):
    members = fixture_files(tmp_path)
    path = tmp_path / "strling/pom.xml"
    text = path.read_text()
    if mutation == "empty-license":
        text = text.replace("<name>Apache License 2.0</name>", "<name/>")
    elif mutation == "empty-scm":
        text = text.replace(
            "<connection>scm:git:https://github.com/strling-lang/strling.git</connection>",
            "<connection/>",
        )
    else:
        text = text.replace(
            "<version>4.0.0</version>",
            "<version>3.0.0</version><version>4.0.0</version>",
        )
    path.write_text(text)
    with pytest.raises(ValueError, match="metadata|duplicate"):
        central_files(tmp_path, {"id": "release:java"}, "4.0.0", members)


def test_binary_jar_assembly_removes_host_modes_without_changing_content(tmp_path):
    from tooling.maven_release import canonical_binary_jar

    paths = [tmp_path / "windows.jar", tmp_path / "linux.jar"]
    content = {
        "META-INF/MANIFEST.MF": b"Manifest-Version: 1.0\r\n\r\n",
        "Api.class": b"exact compiled bytecode",
    }
    for path, mode in zip(paths, (0o100644, 0o100755)):
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in reversed(list(content.items())):
                info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = mode << 16
                archive.writestr(info, data)
        canonical_binary_jar(path)
    assert paths[0].read_bytes() == paths[1].read_bytes()
    with zipfile.ZipFile(paths[0]) as archive:
        assert archive.namelist()[0] == "META-INF/MANIFEST.MF"
        assert {name: archive.read(name) for name in archive.namelist()} == content
        assert all(row.external_attr >> 16 == 0o100644 for row in archive.infolist())
