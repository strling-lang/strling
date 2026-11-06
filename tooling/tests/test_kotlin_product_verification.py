import hashlib
import json
import zipfile

import pytest

from tooling.jvm_adapter_package import (
    JvmPackageCertificationError,
    product_verification_projection,
    product_build_inputs,
    reviewed_product_hashes,
)


ENTRY = """<components>
      <component group="third.party" name="dependency" version="1.0">
         <artifact name="dependency.jar"><sha256 value="reviewed-external-hash"/></artifact>
      </component>
      <component group="com.strling" name="strling-jvm" version="3.0.0">
         <artifact name="strling-jvm-3.0.0.jar"><sha256 value="old"/></artifact>
      </component>
</components>
"""


def test_local_product_refresh_preserves_third_party_and_is_idempotent():
    updated = product_verification_projection(ENTRY, "4.0.0", "a" * 64, "b" * 64)
    assert (
        ENTRY.split('      <component group="com.strling"')[0]
        == updated.split('      <component group="com.strling"')[0]
    )
    assert "strling-jvm-4.0.0.jar" in updated
    assert "strling-jvm-4.0.0.pom" in updated
    assert "3.0.0" not in updated
    assert (
        product_verification_projection(updated, "4.0.0", "a" * 64, "b" * 64) == updated
    )


@pytest.mark.parametrize("text", ["<components/>", ENTRY + ENTRY])
def test_missing_or_ambiguous_product_entries_fail(text):
    with pytest.raises(JvmPackageCertificationError, match="exactly one"):
        product_verification_projection(text, "4.0.0", "a" * 64, "b" * 64)


def test_invalid_product_digest_fails():
    with pytest.raises(JvmPackageCertificationError, match="digest"):
        product_verification_projection(ENTRY, "4.0.0", "unverified", "b" * 64)


def test_only_complete_reviewed_variant_hashes_are_projected():
    hashes = ["c" * 64, "a" * 64]
    updated = product_verification_projection(ENTRY, "4.0.0", hashes, "b" * 64)
    assert updated.count("also-trust") == 1
    assert 'also-trust value="' + "c" * 64 in updated
    assert (
        product_verification_projection(
            updated, "4.0.0", list(reversed(hashes)), "b" * 64
        )
        == updated
    )
    single = product_verification_projection(updated, "4.0.0", "a" * 64, "b" * 64)
    assert "also-trust" not in single


def _reviewed_fixture(tmp_path):
    (tmp_path / "LICENSE").write_text("license\n")
    pom = tmp_path / "bindings/jvm/pom.xml"
    pom.parent.mkdir(parents=True)
    pom.write_text("<project/>\n")
    source = tmp_path / "bindings/jvm/src/main/java/Api.java"
    source.parent.mkdir(parents=True)
    source.write_text("public class Api {}\n")
    jar = tmp_path / "bridge.jar"
    with zipfile.ZipFile(jar, "w") as archive:
        archive.writestr(
            "META-INF/MANIFEST.MF",
            "Manifest-Version: 1.0\r\nBuild-Jdk-Spec: 11\r\n\r\n",
        )
        archive.writestr("Api.class", b"compiled bytes")
    document = {
        "schema_version": "1.0.0",
        "product_version": "4.0.0",
        "source_files": product_build_inputs(tmp_path),
        "compiler_variants": {
            "11": hashlib.sha256(jar.read_bytes()).hexdigest(),
            "21": "b" * 64,
        },
    }
    path = (
        tmp_path
        / "tests/certification/release-supply-chain/1.0/jvm-product-builds.json"
    )
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(document))
    return path, document, jar, pom, source


def test_reviewed_compiler_identity_is_bound_to_all_source_bytes(tmp_path):
    _, document, jar, pom, source = _reviewed_fixture(tmp_path)
    assert reviewed_product_hashes(tmp_path, jar, pom) == sorted(
        document["compiler_variants"].values()
    )
    source.write_text("public class Changed {}\n")
    with pytest.raises(JvmPackageCertificationError, match="source identities"):
        reviewed_product_hashes(tmp_path, jar, pom)


@pytest.mark.parametrize("mutation", ["output", "compiler", "version", "duplicate"])
def test_unreviewed_compiler_outputs_fail_closed(tmp_path, mutation):
    path, document, jar, pom, _ = _reviewed_fixture(tmp_path)
    if mutation == "output":
        jar.write_bytes(jar.read_bytes() + b"substituted")
    elif mutation == "compiler":
        document["compiler_variants"]["17"] = "c" * 64
    elif mutation == "version":
        document["product_version"] = "3.0.0"
    if mutation == "duplicate":
        path.write_text(
            json.dumps(document).replace(
                '"schema_version":', '"schema_version":"ignored","schema_version":'
            )
        )
    else:
        path.write_text(json.dumps(document))
    with pytest.raises(JvmPackageCertificationError):
        reviewed_product_hashes(tmp_path, jar, pom)
