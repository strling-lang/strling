"""Public contract certification must retain actual, source-bound execution."""

from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tooling import public_distribution as public
from tooling.local_certification_attestation import (
    AttestationError,
    _validate_atomic_evidence,
)
from tooling.product_certification import (
    ProductCertificationError,
    validate_producer_manifest,
)
from tooling.quality import Execution, QualityRunner, Toolchain
from tooling.structured_operation_execution import document_fingerprint


ROOT = Path(__file__).resolve().parents[2]
OPERATION = "public_distribution_contract"


@pytest.fixture(autouse=True)
def fixture_source(monkeypatch):
    # Transport tests use a fixed synthetic identity; real source admission is
    # exercised by the authoritative profiles, without mocking Git.
    monkeypatch.setattr(
        "tooling.quality.repository_state",
        lambda root: {"commit": "1" * 40, "dirty": False},
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
            return Execution(0, '{"status":"passed"}', "")
        source = command[command.index("--expected-source-sha") + 1]

        def git_output(args, **kwargs):
            assert args[0] == "git"
            return source if "rev-parse" in args else b""

        stdout = io.StringIO()
        with (
            patch("subprocess.check_output", side_effect=git_output),
            redirect_stdout(stdout),
        ):
            assert public.main(command[3:]) == 0
        directory = Path(command[command.index("--execution-directory") + 1])
        if mutate:
            document = json.loads((directory / "result.json").read_text())
            mutate(document)
            # Recompute the outer digest so identity checks must reject the mutation.
            document["artifact_fingerprint"] = document_fingerprint(document)
            (directory / "result.json").write_text(json.dumps(document))
        return Execution(0, stdout.getvalue(), "")

    return toolchain, QualityRunner(toolchain, hardgate_executor=hardgate)


@pytest.mark.parametrize("profile", ["local", "pull-request", "full", "release"])
def test_public_contract_executes_and_independently_reconstructs(profile):
    toolchain, runner = public_runner()
    stages = runner._profile_stages(profile, None)
    assert sum(stage.operation == OPERATION for stage in stages) == 1
    result = runner.run_repository_operation(
        OPERATION, toolchain.operation(OPERATION), certification_profile=profile
    )
    assert result.status == "passed", result.reason
    assert result.structured_result["details"]["obligations"] == len(
        public.validate_contract(ROOT)["obligations"]
    )
    assert result.structured_result["details"]["public_release_verified"] is False
    operation = {
        "result_id": OPERATION + "@repository",
        "operation_id": OPERATION,
        "status": result.status,
        "structured_evidence": result.structured_result,
        "execution_integrity": result.execution_integrity,
    }
    _validate_atomic_evidence(
        ROOT,
        ROOT,
        result.structured_result["commit"],
        profile,
        operation,
        toolchain.operation(OPERATION),
    )
    omitted = copy.deepcopy(operation)
    omitted.pop("execution_integrity")
    with pytest.raises(AttestationError, match="invocation-bound"):
        _validate_atomic_evidence(
            ROOT,
            ROOT,
            result.structured_result["commit"],
            profile,
            omitted,
            toolchain.operation(OPERATION),
        )


def test_zero_exit_without_public_producer_execution_is_incomplete():
    toolchain, runner = public_runner(execute=False)
    result = runner.run_repository_operation(
        OPERATION, toolchain.operation(OPERATION), certification_profile="full"
    )
    assert result.status == "incomplete"


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_sha", "9" * 40),
        ("certification_profile", "pull-request"),
        ("producer_profile", "full"),
        ("producer_id", "incorrect@repository"),
        ("operation_id", "certification.incorrect"),
        ("invocation_id", "9" * 32),
    ],
)
def test_substituted_public_execution_identity_is_rejected(field, value):
    toolchain, runner = public_runner(lambda document: document.update({field: value}))
    result = runner.run_repository_operation(
        OPERATION, toolchain.operation(OPERATION), certification_profile="full"
    )
    assert result.status == "incomplete"


def test_missing_public_evidence_is_rejected():
    toolchain, runner = public_runner(
        lambda document: document.update(structured_result=None)
    )
    result = runner.run_repository_operation(
        OPERATION, toolchain.operation(OPERATION), certification_profile="full"
    )
    assert result.status == "incomplete"


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "failed"),
        ("commit", "9" * 40),
        ("profile", "full"),
        ("operation_id", "certification.incorrect"),
        ("evidence_fingerprint", "9" * 64),
    ],
)
def test_public_producer_result_cannot_be_substituted_or_incorrectly_aggregated(
    field, value
):
    def mutate(document):
        document["structured_result"][field] = value

    toolchain, runner = public_runner(mutate)
    result = runner.run_repository_operation(
        OPERATION, toolchain.operation(OPERATION), certification_profile="full"
    )
    assert result.status == "incomplete"
