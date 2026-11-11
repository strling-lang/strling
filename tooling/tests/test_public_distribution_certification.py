"""Public contract certification rejects absent, substituted and stale producers."""

from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tooling import public_distribution as public
from tooling.product_certification import (
    ProductCertificationError,
    validate_producer_manifest,
)
from tooling.quality import Execution, QualityRunner, Toolchain


ROOT = Path(__file__).resolve().parents[2]
OPERATION = "public_distribution_contract"
SOURCE = "1" * 40


@pytest.fixture(autouse=True)
def fixture_source(monkeypatch):
    monkeypatch.setattr(
        "tooling.quality.repository_state",
        lambda root: {"commit": SOURCE, "dirty": False},
    )


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "name", "contract", "identity"]
)
def test_public_producer_registration_is_mandatory(mutation):
    manifest = json.loads(
        (ROOT / "tests/certification/product/1.0/producer-manifest.json").read_text()
    )
    producer = next(p for p in manifest["producers"] if p["operation_id"] == OPERATION)
    if mutation == "missing":
        manifest["producers"].remove(producer)
    elif mutation == "duplicate":
        manifest["producers"].append(copy.deepcopy(producer))
    elif mutation == "name":
        producer["operation_id"] = "incorrect_public_contract"
    elif mutation == "contract":
        producer["result_contract"] = None
    else:
        producer["structured_operation_id"] = "certification.incorrect-public-contract"
    with pytest.raises(ProductCertificationError):
        validate_producer_manifest(
            ROOT, manifest, json.loads((ROOT / "toolchain.json").read_text())
        )


def public_runner(mutate=None, *, execute=True):
    toolchain = Toolchain.load(ROOT / "toolchain.json")

    def hardgate(operation, command):
        assert operation == OPERATION
        if not execute:
            return Execution(0, "", "")
        stdout = io.StringIO()
        with (
            patch("subprocess.check_output", return_value=SOURCE),
            redirect_stdout(stdout),
        ):
            assert public.main(command[3:]) == 0
        document = json.loads(stdout.getvalue())
        if mutate:
            mutate(document)
        return Execution(0, json.dumps(document), "")

    return toolchain, QualityRunner(toolchain, hardgate_executor=hardgate)


@pytest.mark.parametrize("profile", ["local", "pull-request", "full", "release"])
def test_public_contract_executes_and_independently_reconstructs(profile):
    toolchain, runner = public_runner()
    assert (
        sum(
            stage.operation == OPERATION
            for stage in runner._profile_stages(profile, None)
        )
        == 1
    )
    result = runner.run_repository_operation(
        OPERATION, toolchain.operation(OPERATION), certification_profile=profile
    )
    assert result.status == "passed", result.reason
    public.validate_certification_result(
        ROOT, result.structured_result, commit=SOURCE, profile="local"
    )
    assert result.structured_result["details"]["obligations"] == len(
        public.validate_contract(ROOT)["obligations"]
    )
    assert result.structured_result["details"]["public_release_verified"] is False
    assert (
        toolchain.operation("functional_resource_certification")["result_transport"]
        == "atomic-artifact-v1"
    )


def test_zero_exit_without_public_producer_execution_is_incomplete():
    toolchain, runner = public_runner(execute=False)
    result = runner.run_repository_operation(
        OPERATION, toolchain.operation(OPERATION), certification_profile="full"
    )
    assert result.status == "incomplete"


def test_actual_producer_failure_preserves_failed_aggregation():
    toolchain = Toolchain.load(ROOT / "toolchain.json")

    def failed(operation, command):
        output = io.StringIO()
        with (
            patch("subprocess.check_output", return_value=SOURCE),
            patch.object(
                public,
                "contract_result",
                side_effect=ValueError("invalid installation command"),
            ),
            redirect_stdout(output),
        ):
            assert public.main(command[3:]) == 1
        return Execution(1, output.getvalue(), "")

    row = QualityRunner(toolchain, hardgate_executor=failed).run_repository_operation(
        OPERATION, toolchain.operation(OPERATION), certification_profile="full"
    )
    assert row.status == "failed"
    assert row.structured_result["details"]["error"] == "invalid installation command"


def test_omission_from_independent_product_reconstruction_is_rejected():
    from tooling.certification import canonical_evidence_fingerprint
    from tooling.product_certification import build_product_artifact
    from tooling.tests.test_product_certification import (
        ProductCertificationImplementationTests as Fixtures,
        FIXTURE_REPOSITORY,
    )

    Fixtures.setUpClass()
    profile = copy.deepcopy(Fixtures.profile_artifact)
    deterministic = profile["deterministic_evidence"]
    deterministic["operations"] = [
        row for row in deterministic["operations"] if row["operation_id"] != OPERATION
    ]
    deterministic["aggregate"]["operation_count"] -= 1
    deterministic["aggregate"]["counts"]["passed"] -= 1
    profile["evidence_fingerprint"] = canonical_evidence_fingerprint(deterministic)
    with pytest.raises(ProductCertificationError):
        build_product_artifact(
            root=ROOT,
            profile_artifact=profile,
            manifest=Fixtures.manifest,
            toolchain=Fixtures.toolchain,
            resolved_repository_state=FIXTURE_REPOSITORY,
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "failed"),
        ("commit", "9" * 40),
        ("profile", "full"),
        ("operation_id", "certification.incorrect"),
        ("schema_version", "incorrect-v1"),
        ("evidence_fingerprint", "9" * 64),
        ("details", {}),
    ],
)
def test_public_producer_result_cannot_be_substituted_or_incorrectly_aggregated(
    field, value
):
    toolchain, runner = public_runner(lambda document: document.update({field: value}))
    result = runner.run_repository_operation(
        OPERATION, toolchain.operation(OPERATION), certification_profile="full"
    )
    assert result.status == "incomplete"


@pytest.mark.parametrize(
    "mutation", ["missing-evidence", "count", "public-claim", "documentation"]
)
def test_independent_reconstruction_rejects_omissions_and_false_claims(mutation):
    result = public.contract_result(ROOT, commit=SOURCE, profile="local")
    if mutation == "missing-evidence":
        result.pop("details")
    elif mutation == "count":
        result["details"]["obligations"] -= 1
    elif mutation == "public-claim":
        result["details"]["public_release_verified"] = True
    else:
        result["details"]["documentation"].pop(
            next(iter(result["details"]["documentation"]))
        )
    with pytest.raises(ValueError):
        public.validate_certification_result(
            ROOT, result, commit=SOURCE, profile="local"
        )
