"""Consumer success must mean canonical success, not merely a returned object."""

import copy
import hashlib

import pytest

from tooling.release_consumers import canonical_results, copy_subject_directory
from tooling.release_supply_chain import ReleaseSupplyChainError


def results():
    return (
        {
            "outcome": "succeeded",
            "semantic_result": {"program": {"root": {"text": "a"}}},
        },
        {"outcome": "succeeded", "artifact": {"pattern": {"text": "abc"}}},
    )


def envelope(result):
    return {
        "interop_protocol_version": "1.0.0",
        "operation": "compile",
        "status": "completed",
        "result": result,
    }


def test_consumer_accepts_canonical_values_and_completed_transport():
    source, target = results()
    assert canonical_results(source, target)["target_pattern"] == "abc"
    assert (
        canonical_results(envelope(source), envelope(target))["source_outcome"]
        == "succeeded"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "failed-source",
        "literal",
        "failed-target",
        "pattern",
        "transport",
        "protocol",
        "operation",
    ],
)
def test_consumer_rejects_plausible_but_incorrect_success(mutation):
    source, target = map(envelope, results())
    if mutation == "failed-source":
        source["result"]["outcome"] = "failed"
    elif mutation == "literal":
        source["result"]["semantic_result"]["program"]["root"]["text"] = "different"
    elif mutation == "failed-target":
        target["result"]["outcome"] = "failed"
    elif mutation == "pattern":
        target["result"]["artifact"]["pattern"]["text"] = "different"
    elif mutation == "transport":
        source["status"] = "error"
    elif mutation == "protocol":
        source["interop_protocol_version"] = "2.0.0"
    else:
        source["operation"] = "describe"
    with pytest.raises(ReleaseSupplyChainError):
        canonical_results(source, target)


def test_staging_copies_only_the_authenticated_file_graph(tmp_path):
    root = tmp_path / "source"
    package = root / "bindings/go"
    package.mkdir(parents=True)
    data = b"exact package bytes"
    (package / "go.mod").write_bytes(data)
    (package / "unregistered-cache").write_bytes(b"must not ship")
    member = {
        "name": "bindings/go",
        "files": [
            {"name": "bindings/go/go.mod", "sha256": hashlib.sha256(data).hexdigest()}
        ],
    }
    destination = tmp_path / "consumer/package"
    copy_subject_directory(root, member, destination)
    assert [path.name for path in destination.iterdir()] == ["go.mod"]
    assert (destination / "go.mod").read_bytes() == data
    tampered = copy.deepcopy(member)
    tampered["files"][0]["sha256"] = "0" * 64
    with pytest.raises(ReleaseSupplyChainError, match="changed"):
        copy_subject_directory(root, tampered, tmp_path / "other-consumer")


@pytest.mark.parametrize(
    "path",
    ["../private", "/private", "bindings/go/../../private", "bindings\\go\\go.mod"],
)
def test_staging_rejects_escape_before_reading(tmp_path, path):
    member = {"name": "bindings/go", "files": [{"name": path, "sha256": "0" * 64}]}
    with pytest.raises((ReleaseSupplyChainError, ValueError)):
        copy_subject_directory(tmp_path / "source", member, tmp_path / "consumer")
