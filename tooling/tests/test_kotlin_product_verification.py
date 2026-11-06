import pytest

from tooling.jvm_adapter_package import (
    JvmPackageCertificationError,
    product_verification_projection,
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
