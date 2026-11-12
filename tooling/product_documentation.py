"""Check reviewed product examples against their current documentation bytes.

Only canonical language/JSON cases execute here. Host SDK examples execute in
the governed package consumers, never in a documentation link checker.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

try:
    from tooling.documentation_integrity import Check, Finding
except ModuleNotFoundError:
    from documentation_integrity import Check, Finding


MANIFEST = "tests/documentation/1.0/manifest.json"
KINDS = {
    "canonical",
    "consumer",
    "fragment",
    "historical",
    "installation",
    "procedure",
    "diagram",
    "signature",
}
ENTRYPOINTS = {"README.md", "CONTRIBUTING.md", "SECURITY.md", "core/README.md"}
HOST_LANGUAGES = {
    "cpp",
    "csharp",
    "dart",
    "fsharp",
    "go",
    "java",
    "kotlin",
    "lua",
    "perl",
    "php",
    "python",
    "r",
    "ruby",
    "rust",
    "swift",
    "typescript",
}
CONTEXT_EXAMPLES = {
    "docs/capability-evaluation.md#2",
    "docs/portability-planning.md#2",
    "docs/tutorial/first_contribution.md#5",
    "bindings/jvm/README.md#1",
}


def current_document(relative: str) -> bool:
    return (
        relative in ENTRYPOINTS
        or relative.startswith("bindings/")
        or relative.startswith("docs/")
        and not relative.startswith(
            ("docs/migration/", "docs/audits/", "docs/templates/")
        )
    ) and not relative.endswith("AGENTS.md")


def fences(text: str) -> list[dict]:
    result = []
    marker = None
    body: list[str] = []
    language = ""
    for number, line in enumerate(text.splitlines(), 1):
        match = re.match(r"^\s*(`{3,}|~{3,})(.*)$", line)
        if match:
            if marker is None:
                marker, language, start = match[1][0], match[2].strip(), number
                body = []
            elif match[1][0] == marker:
                content = "\n".join(body) + "\n"
                result.append(
                    dict(
                        language=language,
                        line=start,
                        body=content,
                        sha256=hashlib.sha256(content.encode()).hexdigest(),
                    )
                )
                marker = None
        elif marker is not None:
            body.append(line)
    if marker is not None:
        raise ValueError("unclosed documentation fence")
    return result


def validate_manifest(root: Path, manifest: dict, paths: list[str]) -> list[str]:
    errors = []
    if (
        set(manifest) != {"schema_version", "documents", "examples"}
        or manifest.get("schema_version") != "1.0.0"
    ):
        errors.append("invalid closed documentation manifest")
    expected = sorted(path for path in paths if current_document(path))
    if manifest.get("documents") != expected or len(expected) != len(set(expected)):
        errors.append("current product document inventory differs")
    observed = {}
    for path in expected:
        for index, block in enumerate(
            fences((root / path).read_text(encoding="utf-8")), 1
        ):
            observed[path + "#" + str(index)] = block
    examples = manifest.get("examples", [])
    ids = [row.get("id") for row in examples]
    if ids != sorted(observed) or len(ids) != len(set(ids)):
        errors.append("missing, duplicate or unknown documentation example")
    for row in examples:
        if set(row) != {"id", "kind", "sha256", "language", "evidence", "reason"}:
            errors.append("invalid closed example record")
            continue
        block = observed.get(row["id"])
        if (
            block is None
            or row["sha256"] != block["sha256"]
            or row["language"] != block["language"]
        ):
            errors.append("changed documentation example: " + row["id"])
        if row["kind"] not in KINDS or not row["reason"] or not row["evidence"]:
            errors.append("unclassified documentation example: " + row["id"])
        if row["language"] in {"strling", "json"} and row["kind"] != "canonical":
            errors.append("canonical example omitted from execution: " + row["id"])
        if (
            row["language"] in HOST_LANGUAGES
            and row["id"]
            not in CONTEXT_EXAMPLES
            | {"docs/migration-guide.md#1", "docs/migration-guide.md#4"}
            and row["kind"] != "consumer"
        ):
            errors.append("host example omitted from consumer execution: " + row["id"])
        if row["kind"] == "historical" and row["id"] not in {
            "docs/migration-guide.md#1",
            "docs/migration-guide.md#4",
        }:
            errors.append("unregistered historical exception: " + row["id"])
    return errors


def check_inventory(root: Path) -> Check:
    paths = subprocess.check_output(
        ["git", "ls-files", "--", "*.md"], cwd=root, text=True
    ).splitlines()
    # New authored entrypoints are checked before their checkpoint commit too.
    paths = sorted(
        set(paths)
        | {path.relative_to(root).as_posix() for path in (root / "docs").glob("*.md")}
    )
    try:
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
        errors = validate_manifest(root, manifest, paths)
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors = [str(error)]
    return Check(
        "documentation.product-inventory",
        "failed" if errors else "passed",
        "Reviewed product document and example completeness.",
        tuple(Finding("DOC-PRODUCT-INVENTORY", error, MANIFEST) for error in errors),
    )


def check_canonical_examples(root: Path, execute: Callable = subprocess.run) -> Check:
    findings = []
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="strling-documentation-") as directory:
        for row in manifest["examples"]:
            if row["kind"] != "canonical":
                continue
            path, ordinal = row["id"].rsplit("#", 1)
            block = fences((root / path).read_text(encoding="utf-8"))[int(ordinal) - 1]
            source = Path(directory) / (
                "example.json" if row["language"] == "json" else "example.strl"
            )
            source.write_text(block["body"], encoding="utf-8")
            command = [
                "cargo",
                "run",
                "--quiet",
                "--manifest-path",
                "core/internal/Cargo.toml",
                "--bin",
                "strling-kernel",
                "--",
                "compile",
                "--format",
                "json",
            ]
            if row["language"] == "json":
                completed = execute(
                    command,
                    cwd=root,
                    input=block["body"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            else:
                completed = execute(
                    [*command, "--input", str(source)],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            try:
                result = json.loads(completed.stdout)
                if completed.returncode != 0 or result.get("outcome") != "succeeded":
                    raise ValueError("canonical example did not succeed")
            except ValueError as error:
                findings.append(
                    Finding("DOC-CANONICAL-EXAMPLE", str(error), path, block["line"])
                )
        findings.extend(check_getting_started_commands(root, Path(directory), execute))
    return Check(
        "documentation.product-canonical-examples",
        "failed" if findings else "passed",
        "Executed reviewed Semantic programs and canonical request examples.",
        tuple(findings),
    )


def check_getting_started_commands(
    root: Path, work: Path, execute: Callable
) -> list[Finding]:
    relative = "docs/getting-started.md"
    blocks = fences((root / relative).read_text(encoding="utf-8"))
    observed = []
    for ordinal in (1, 2):
        body = blocks[ordinal]["body"].replace("\\\n", " ")
        observed.extend(shlex.split(line) for line in body.splitlines() if line.strip())
    expected = [
        [
            "./strling",
            "compile",
            "--input",
            "hello.strl",
            "--output",
            "semantic",
            "--format",
            "json",
        ],
        ["./strling", "target", "list", "--format", "json"],
        [
            "./strling",
            "compile",
            "--input",
            "hello.strl",
            "--output",
            "target_artifact",
            "--target-profile",
            "spec/targets/profiles/pcre2-10.43.json",
            "--format",
            "json",
        ],
        [
            "./strling",
            "import",
            "--input",
            "hello.regex",
            "--output",
            "semantic",
            "--format",
            "json",
        ],
    ]
    if observed != expected:
        return [
            Finding(
                "DOC-CLI-COMMAND",
                "Getting-started commands require explicit reviewed execution coverage.",
                relative,
            )
        ]
    (work / "hello.strl").write_text(blocks[0]["body"], encoding="utf-8")
    (work / "hello.regex").write_text("hello", encoding="utf-8")
    findings = []
    bash = shutil.which("bash") or "bash"
    if os.name == "nt":
        git = shutil.which("git")
        candidates = (
            []
            if git is None
            else [
                Path(git).parent.parent / "bin/bash.exe",
                Path(git).parent.parent / "usr/bin/bash.exe",
            ]
        )
        found = next((path for path in candidates if path.is_file()), None)
        if found is None:
            return [
                Finding(
                    "DOC-CLI-COMMAND",
                    "The Windows source CLI requires the governed Git Bash installation.",
                    relative,
                )
            ]
        bash = str(found)
    for command in observed:
        arguments = [bash, (root / "strling").as_posix(), *command[1:]]
        for name in ("hello.strl", "hello.regex"):
            arguments = [
                (work / name).as_posix() if value == name else value
                for value in arguments
            ]
        # Invoke the root transport itself. Markdown is never a shell program.
        completed = execute(
            arguments, cwd=root, capture_output=True, text=True, check=False
        )
        try:
            value = json.loads(completed.stdout)
            if completed.returncode != 0 or not value:
                raise ValueError("documented CLI command failed")
            if command[1] != "target" and value.get("outcome") != "succeeded":
                raise ValueError("documented compilation did not succeed")
            if (
                "target_artifact" in command
                and value.get("artifact", {}).get("pattern", {}).get("text") != "hello"
            ):
                raise ValueError("documented PCRE2 artifact changed")
        except ValueError as error:
            findings.append(Finding("DOC-CLI-COMMAND", str(error), relative))
    return findings


def check_support_matrix(root: Path) -> Check:
    try:
        from tooling.release_candidate import OUTPUT, render
    except ModuleNotFoundError:
        from release_candidate import OUTPUT, render

    try:
        if (root / OUTPUT).read_text(encoding="utf-8") != render(root):
            raise ValueError("support matrix differs from governed inputs")
        from tooling.public_metadata import verify_readme_commands
        from tooling.release_candidate import scope

        data = scope(root)
        for artifact in data["artifacts"]:
            readme = root / (
                "bindings/rust/README.md"
                if artifact["id"] == "release:rust"
                else artifact["package_root"] + "/README.md"
            )
            result = verify_readme_commands(
                readme.read_bytes(), artifact, data["product"]["version"]
            )
            if result["exact_install_commands_found"] < 1:
                raise ValueError(
                    "missing exact proposed installation command: " + artifact["id"]
                )
        findings = ()
    except (OSError, ValueError, KeyError) as error:
        findings = (Finding("DOC-SUPPORT-MATRIX", str(error), OUTPUT),)
    return Check(
        "documentation.support-matrix",
        "failed" if findings else "passed",
        "Reconciled distributions, support claims, target profiles and toolchains.",
        findings,
    )
