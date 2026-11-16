"""Exact upstream license correction must not permit unrelated unknown metadata."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from tooling.security import SecurityEngine


ROOT = Path(__file__).resolve().parents[2]


def configured_engine():
    policy = json.loads((ROOT / "governance/security-policy.json").read_text())
    return SecurityEngine(ROOT, policy, tracked_files=[])


def test_exact_pyelftools_metadata_retains_both_license_obligations():
    engine = configured_engine()
    expression = engine._license_override("python", "pyelftools", "0.33")
    assert expression == "Unlicense AND MIT"
    assert engine._license_classification(expression) == "permitted"
    assert engine._license_classification("non-standard") == "unknown"


@pytest.mark.parametrize(
    "ecosystem,package,version",
    [
        ("python", "pyelftools", "0.32"),
        ("python", "pyelftools", "0.34"),
        ("python", "other-pyelftools", "0.33"),
        ("npm", "pyelftools", "0.33"),
    ],
)
def test_pyelftools_correction_cannot_cover_another_identity(
    ecosystem, package, version
):
    assert configured_engine()._license_override(ecosystem, package, version) is None


@pytest.mark.parametrize(
    "expression",
    ["Unlicense AND AGPL-3.0-only", "MIT AND UNKNOWN", "Unlicense AND MIT AND UNKNOWN"],
)
def test_other_composites_still_fail_closed(expression):
    assert configured_engine()._license_classification(expression) != "permitted"


def test_new_conjunction_requires_its_exact_policy_entry():
    engine = configured_engine()
    engine.policy = copy.deepcopy(engine.policy)
    engine.policy["license_policy"]["permitted"].remove("Unlicense AND MIT")
    assert engine._license_classification("Unlicense AND MIT") == "unknown"


def test_exact_review_binds_lock_archive_notices_and_upstream_vendor_identity():
    directory = ROOT / "docs/migration/license-reviews/pyelftools-0.33"
    review = json.loads((directory / "review.json").read_text())
    assert review["status"] == "PASSED"
    assert review["expression"] == "Unlicense AND MIT"
    assert review["archive_sha256"] in (ROOT / review["lock"]).read_text()
    assert review["upstream_commit"] == "52ce435186022bd6b32012a998931fe86c985ec8"
    assert len(review["bundled_construct_files"]) == 10
    assert {row["spdx"] for row in review["licenses"]} == {"Unlicense", "MIT"}
    for row in review["licenses"]:
        notice = (directory / (row["spdx"] + ".LICENSE")).read_bytes()
        assert hashlib.sha256(notice).hexdigest() == row["sha256"]
        assert hashlib.sha256(notice + b"altered").hexdigest() != row["sha256"]
    overrides = configured_engine().policy["license_policy"]["metadata_overrides"]
    binding = next(
        row
        for row in overrides
        if row["ecosystem"] == "python" and row["package"] == "pyelftools"
    )
    assert binding["version"] == review["version"] == "0.33"
    assert review["archive_sha256"] in binding["evidence"]
    assert all(row["sha256"] in binding["evidence"] for row in review["licenses"])
