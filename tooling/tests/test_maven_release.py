import hashlib
import io
import shutil
import subprocess
import zipfile

import pytest

from tooling.maven_release import central_files, signed_envelope


@pytest.mark.parametrize(
    "fingerprints",
    [("A" * 40, "A" * 40), ("A" * 40, "B" * 40), ("A" * 40, ""), ("", "")],
)
def test_java_and_kotlin_require_the_same_approved_primary(fingerprints):
    from tooling.maven_release import maven_signing_identity

    destinations = [
        dict(artifact_id="release:" + slug, signing_key_fingerprint=value)
        for slug, value in zip(("java", "kotlin"), fingerprints)
    ]
    if fingerprints == ("A" * 40, "A" * 40):
        assert maven_signing_identity(destinations) == "A" * 40
    else:
        with pytest.raises(ValueError, match="shared"):
            maven_signing_identity(destinations)


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "expired",
        "revoked",
        "subkey",
        "weak",
        "curve",
        "no-expiry",
        "future",
        "unavailable",
        "no-sign",
        "duplicate",
        "wrong",
    ],
)
def test_maven_primary_key_metadata_policy(mutation):
    from tooling.maven_release import primary_signer

    fingerprint = "B" * 40
    fields = [
        "sec",
        "u",
        "3072",
        "1",
        "KEY",
        "100",
        "200",
        "",
        "",
        "",
        "",
        "scSC",
        "",
        "",
        "+",
        "",
    ]
    positions = {
        "expired": (6, "150"),
        "revoked": (1, "r"),
        "subkey": (0, "ssb"),
        "weak": (2, "2048"),
        "curve": (3, "22"),
        "no-expiry": (6, ""),
        "future": (5, "175"),
        "unavailable": (14, "#"),
        "no-sign": (11, "cC"),
    }
    if mutation in positions:
        index, value = positions[mutation]
        fields[index] = value
    listing = ":".join(fields) + "\nfpr:::::::::" + fingerprint + ":\n"
    if mutation == "duplicate":
        listing += listing
    if mutation is None:
        primary_signer(listing, fingerprint, now=150)
    else:
        with pytest.raises(ValueError):
            primary_signer(
                listing, "A" * 40 if mutation == "wrong" else fingerprint, now=150
            )


@pytest.mark.parametrize("passphrase", ["", "bad\nframe", "bad\rframe"])
def test_maven_requires_nonempty_well_framed_passphrase(passphrase):
    with pytest.raises(ValueError, match="passphrase"):
        signed_envelope({"fixture.jar": b"fixture"}, "", passphrase, "B" * 40)


def fixture_files(tmp_path):
    files = {}
    for name in ("strling", "strling-jvm"):
        pom = tmp_path / name / "pom.xml"
        pom.parent.mkdir()
        pom.write_text(f"""<project><groupId>io.github.strling-lang</groupId><artifactId>{name}</artifactId><version>4.0.0</version>
<name>STRling</name><description>Canonical adapter</description><url>https://github.com/strling-lang/strling</url>
<licenses><license><name>Apache License 2.0</name><url>https://www.apache.org/licenses/LICENSE-2.0</url></license></licenses><developers><developer><name>STRling Team</name></developer></developers><scm><connection>scm:git:https://github.com/strling-lang/strling.git</connection><developerConnection>scm:git:ssh://git@github.com/strling-lang/strling.git</developerConnection><url>https://github.com/strling-lang/strling</url></scm></project>""")
        if name == "strling":
            pom.write_text(
                pom.read_text().replace(
                    "</project>",
                    "<dependencies><dependency><groupId>io.github.strling-lang</groupId><artifactId>strling-jvm</artifactId><version>4.0.0</version></dependency></dependencies></project>",
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
    assert all(name.startswith("io/github/strling-lang/") for name in layout)
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


@pytest.mark.parametrize(
    "old,new",
    [("<version>4.0.0", "<version>3.0.0"), ("io.github.strling-lang", "com.strling")],
)
def test_central_rejects_substituted_coordinate(tmp_path, old, new):
    members = fixture_files(tmp_path)
    path = tmp_path / "strling/pom.xml"
    path.write_text(path.read_text().replace(old, new))
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
@pytest.mark.parametrize("signing_subkey", [False, True])
def test_signatures_bind_existing_bytes_and_owner_signer(tmp_path, signing_subkey):
    home = tmp_path / "test-keyring"
    home.mkdir(mode=0o700)
    public_home = tmp_path / "public-only-keyring"
    public_home.mkdir(mode=0o700)
    password = "synthetic-fixture-only"

    def gpg(*args):
        return subprocess.run(
            [
                "gpg",
                "--homedir",
                str(home),
                "--batch",
                "--no-tty",
                "--pinentry-mode",
                "loopback",
                "--passphrase-fd",
                "0",
                *args,
            ],
            input=(password + "\n").encode(),
            capture_output=True,
            check=True,
        ).stdout

    def verify(*args):
        return subprocess.run(
            [
                "gpg",
                "--homedir",
                str(public_home),
                "--batch",
                "--no-auto-key-retrieve",
                *args,
            ],
            capture_output=True,
            check=True,
        ).stdout

    try:
        gpg(
            "--quick-generate-key",
            "STRling local test <test@example.invalid>",
            "rsa3072",
            "cert" if signing_subkey else "sign",
            "1y",
        )
        fingerprint = next(
            line.split(":")[9]
            for line in gpg("--with-colons", "--list-secret-keys").decode().splitlines()
            if line.startswith("fpr:")
        )
        primary = fingerprint
        if signing_subkey:
            gpg("--quick-add-key", primary, "rsa3072", "sign", "1y")
            fingerprint = [
                line.split(":")[9]
                for line in gpg(
                    "--with-colons", "--with-subkey-fingerprint", "--list-secret-keys"
                )
                .decode()
                .splitlines()
                if line.startswith("fpr:")
            ][1]
        key = gpg(
            "--armor",
            "--export-secret-subkeys" if signing_subkey else "--export-secret-keys",
            fingerprint + "!",
        ).decode()
        files = {
            f"io/github/strling-lang/{module}/4.0.0/{module}-4.0.0.{kind}": b"exact synthetic fixture bytes: "
            + module.encode()
            + kind.encode()
            for module in ("strling", "strling-kotlin", "strling-jvm")
            for kind in ("jar", "pom", "sources.jar", "javadoc.jar")
        }
        if signing_subkey:
            with pytest.raises(ValueError, match="primary key, not a subkey"):
                signed_envelope(files, key, password, fingerprint)
            return
        data, digest = signed_envelope(files, key, password, fingerprint)
        first_name = next(iter(files))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            (tmp_path / "untrusted.asc").write_bytes(archive.read(first_name + ".asc"))
        (tmp_path / "untrusted").write_bytes(files[first_name])
        with pytest.raises(subprocess.CalledProcessError):
            verify(
                "--verify", str(tmp_path / "untrusted.asc"), str(tmp_path / "untrusted")
            )
        public = gpg("--armor", "--export", primary)
        subprocess.run(
            ["gpg", "--homedir", str(public_home), "--batch", "--import"],
            input=public,
            capture_output=True,
            check=True,
        )
        assert b"sec:" not in verify("--with-colons", "--list-secret-keys")
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
                signature = tmp_path / "payload.asc"
                payload_path = tmp_path / "payload"
                signature.write_bytes(archive.read(name + ".asc"))
                payload_path.write_bytes(payload)
                status = verify(
                    "--status-fd", "1", "--verify", str(signature), str(payload_path)
                ).decode()
                valid = next(
                    line.split()
                    for line in status.splitlines()
                    if line.startswith("[GNUPG:] VALIDSIG ")
                )
                assert valid[2] == fingerprint
                assert valid[9] == "8"
                assert valid[-1] == primary
                payload_path.write_bytes(payload + b"modified")
                with pytest.raises(subprocess.CalledProcessError):
                    verify("--verify", str(signature), str(payload_path))
                payload_path.write_bytes(payload)
                signature.write_bytes(b"invalid detached signature")
                with pytest.raises(subprocess.CalledProcessError):
                    verify("--verify", str(signature), str(payload_path))
                signature.unlink()
                with pytest.raises(subprocess.CalledProcessError):
                    verify("--verify", str(signature), str(payload_path))
        with pytest.raises(subprocess.CalledProcessError):
            signed_envelope(files, key, password + "wrong", fingerprint)
        with pytest.raises(subprocess.CalledProcessError):
            signed_envelope(files, "", password, fingerprint)
        with pytest.raises(ValueError, match="owner authorization"):
            signed_envelope(files, key, password, "A" * 40)
    finally:
        for keyring in (home, public_home):
            subprocess.run(
                ["gpgconf", "--homedir", str(keyring), "--kill", "gpg-agent"],
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
