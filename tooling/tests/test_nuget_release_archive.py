"""NuGet assembly preserves payloads while making SDK OPC identifiers stable."""

import xml.etree.ElementTree as ET
import zipfile

import pytest

from tooling.release_packaging import canonical_nuget_archive
from tooling.release_payload import archive_files
from tooling.release_supply_chain import ReleaseSupplyChainError


NS = "http://schemas.openxmlformats.org/package/2006/relationships"
KIND = NS + "/metadata/core-properties"
BODY = b"<coreProperties><identifier>STRling</identifier></coreProperties>"


def package(path, identifier, *, signed=False, duplicate=False):
    target = "package/services/metadata/core-properties/" + identifier + ".psmdcp"
    relationships = ET.Element("{" + NS + "}Relationships")
    ET.SubElement(
        relationships,
        "{" + NS + "}Relationship",
        Id="manifest",
        Type="manifest",
        Target="/STRling.nuspec",
    )
    ET.SubElement(
        relationships,
        "{" + NS + "}Relationship",
        Id="R" + identifier,
        Type=KIND,
        Target="/" + target,
    )
    if duplicate:
        ET.SubElement(
            relationships,
            "{" + NS + "}Relationship",
            Id="duplicate",
            Type=KIND,
            Target="/" + target,
        )
    files = {
        target: BODY,
        "_rels/.rels": ET.tostring(relationships),
        "[Content_Types].xml": b'<Types><Default Extension="psmdcp" ContentType="application/vnd.openxmlformats-package.core-properties+xml" /></Types>',
        "STRling.nuspec": b"<package><metadata><id>STRling</id><version>4.0.0</version></metadata></package>",
        "runtimes/win-x64/native/strling_interop.dll": bytes(range(256)),
    }
    if signed:
        files[".signature.p7s"] = b"existing seal"
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)


def test_sdk_random_identifiers_produce_identical_packages_and_exact_payloads(tmp_path):
    outputs = []
    for index, identifier in enumerate(("a" * 32, "b" * 32)):
        source, target = tmp_path / f"{index}.nupkg", tmp_path / f"{index}.nupkg.tmp"
        package(source, identifier)
        canonical_nuget_archive(source, target)
        files = archive_files(target)
        assert files["runtimes/win-x64/native/strling_interop.dll"] == bytes(range(256))
        properties = [name for name in files if name.endswith(".psmdcp")]
        assert len(properties) == 1 and files[properties[0]] == BODY
        root = ET.fromstring(files["_rels/.rels"])
        assert (
            next(row for row in root if row.get("Type") == KIND).get("Target")
            == "/" + properties[0]
        )
        outputs.append(target.read_bytes())
    assert outputs[0] == outputs[1]


def test_nuget_canonical_assembly_is_idempotent(tmp_path):
    source, target, repeated = [
        tmp_path / name for name in ("a.nupkg", "b.nupkg", "c.nupkg")
    ]
    package(source, "a" * 32)
    canonical_nuget_archive(source, target)
    canonical_nuget_archive(target, repeated)
    assert target.read_bytes() == repeated.read_bytes()


@pytest.mark.parametrize("signed,duplicate", [(True, False), (False, True)])
def test_nuget_assembly_rejects_sealed_or_ambiguous_packages(
    tmp_path, signed, duplicate
):
    source, target = tmp_path / "source.nupkg", tmp_path / "target.nupkg"
    package(source, "a" * 32, signed=signed, duplicate=duplicate)
    with pytest.raises(ReleaseSupplyChainError):
        canonical_nuget_archive(source, target)
