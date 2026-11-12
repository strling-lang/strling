"""Stage reviewed host examples for the isolated package consumer SDKs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tooling.product_documentation import MANIFEST, fences, validate_manifest

PYTHON_EXAMPLES = (
    "bindings/python/README.md#1",
    "bindings/python/README.md#2",
    "bindings/python/README.md#3",
    "docs/getting-started.md#5",
    "docs/migration-guide.md#2",
)


def expected_proof(manifest: dict, slug: str) -> list[dict]:
    return [
        dict(id=row["id"], sha256=row["sha256"], status="passed")
        for row in manifest["examples"]
        if row["kind"] == "consumer"
        and (
            row["id"].startswith(f"bindings/{slug}/")
            or slug == "python"
            and row["id"] in PYTHON_EXAMPLES
        )
    ]


def completed(result: dict, work: Path, identities: tuple[str, ...]) -> None:
    manifest = json.loads(
        (work / "documentation-manifest.json").read_text(encoding="utf-8")
    )
    result["documentation_manifest_sha256"] = hashlib.sha256(
        (work / "documentation-manifest.json").read_bytes()
    ).hexdigest()
    rows = {row["id"]: row for row in manifest["examples"]}
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate documentation producer")
    result["documentation_examples"] = [
        dict(id=identity, sha256=rows[identity]["sha256"], status="passed")
        for identity in sorted(identities)
    ]


def verify_proof(root: Path, slug: str, result: dict) -> None:
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    if result.get("documentation_manifest_sha256") != hashlib.sha256(
        (root / MANIFEST).read_bytes()
    ).hexdigest() or result.get("documentation_examples") != expected_proof(
        manifest, slug
    ):
        raise ValueError("missing, changed or unexecuted documented package example")


def prepare(root: Path, work: Path) -> None:
    data = (root / MANIFEST).read_bytes()
    (work / "documentation-manifest.json").write_bytes(data)
    manifest = json.loads(data)
    errors = validate_manifest(root, manifest, manifest["documents"])
    if errors:
        raise ValueError("documentation source integrity: " + "; ".join(errors))
    blocks = {}
    for row in manifest["examples"]:
        if row["kind"] != "consumer":
            continue
        path, ordinal = row["id"].rsplit("#", 1)
        blocks[row["id"]] = fences((root / path).read_text(encoding="utf-8"))[
            int(ordinal) - 1
        ]["body"]
    (work / "documentation-examples.json").write_text(
        json.dumps(blocks, sort_keys=True), encoding="utf-8"
    )


def block(work: Path, identity: str) -> str:
    return json.loads(
        (work / "documentation-examples.json").read_text(encoding="utf-8")
    )[identity]


def readme(work: Path, slug: str, ordinal: int = 1) -> str:
    return block(work, f"bindings/{slug}/README.md#{ordinal}")


def python_program(work: Path) -> str:
    program = [
        "import json, pathlib\nfrom STRling import load_native, bundled_library_path\n"
    ]
    context = "client = load_native()\ncompile_projection = json.loads(pathlib.Path('request.json').read_text())\ncompile_projection = {key: value for key, value in compile_projection.items() if key in ('target_profile', 'requested_outputs', 'compiler_options')}\nexact_target_profile = json.loads(pathlib.Path('target.json').read_text())\n"
    for index, identity in enumerate(PYTHON_EXAMPLES):
        body = context + block(work, identity)
        if identity.endswith("README.md#2"):
            body += "client = connect(str(bundled_library_path()))\nassert client.describe()['native_abi']['major'] == 1\n"
        if identity.endswith("README.md#3"):
            body += "assert response['status'] == 'success'\nassert response['compile_result']['outcome'] == 'succeeded'\n"
        program.append(
            f"def documented_example_{index}():\n"
            + "".join("    " + line + "\n" for line in body.splitlines())
        )
        program.append(f"documented_example_{index}()\n")
    program.append("print('documentation passed')\n")
    return "\n".join(program)


def rust_program(work: Path) -> str:
    program = []
    for ordinal in (1, 2):
        body = readme(work, "rust", ordinal)
        program.append(
            f"fn documented_example_{ordinal}(canonical_request_json: &str, canonical_profile_json: &str) -> Result<(), Box<dyn std::error::Error>> {{\n"
            + body
            + '\nassert_eq!(serde_json::to_value(&result)?["outcome"], "succeeded");\nOk(())\n}\n'
        )
    program.append(
        'fn main() -> Result<(), Box<dyn std::error::Error>> {\nlet source=std::fs::read_to_string("source.json")?;\nlet request=std::fs::read_to_string("request.json")?;\nlet profile=std::fs::read_to_string("target.json")?;\ndocumented_example_1(&source, &profile)?;\ndocumented_example_2(&request, &profile)?;\nprintln!("documentation passed");\nOk(())\n}\n'
    )
    return "\n".join(program)
