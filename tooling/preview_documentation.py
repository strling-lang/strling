"""Execute bounded Preview documentation against staged local packages.

These observations never establish Supported clean-consumer certification or
public registry retrieval. Installation is local and dependency networking is
disabled. The application supplies the authenticated native/WASM payload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import uuid
from pathlib import Path

from tooling.documentation_programs import block, completed, expected_proof
from tooling.release_consumers import (
    copy_subject_directory,
    fixture_files,
    run_consumer,
)
from tooling.release_supply_chain import (
    MANIFEST_PATH,
    ROOT,
    _surface_identity,
    _surface_members,
    authenticate_source,
    document_fingerprint,
    load_json,
    scoped_artifact,
    inspect_release_payload,
)


def execute(
    artifact_id: str,
    *,
    artifacts: Path,
    harness: Path,
    output: Path,
    native: Path | None = None,
    typescript_sdk: Path | None = None,
    engineering: bool = False,
) -> dict:
    if output.exists():
        raise ValueError("Preview documentation output already exists")
    manifest = load_json(harness / MANIFEST_PATH.relative_to(ROOT))
    candidates = [row for row in manifest["artifacts"] if row["id"] == artifact_id]
    if (
        len(candidates) != 1
        or candidates[0]["distribution_contract"]["tier"] != "Preview"
    ):
        raise ValueError("an exact registered Preview package is required")
    from tooling.release_packaging import build_environment, host_scope

    artifact = scoped_artifact(candidates[0], host_scope())
    version = load_json(harness / "governance/release-policy.json")["product"][
        "version"
    ]
    source = None if engineering else authenticate_source(harness)
    members = _surface_members(artifacts, artifact, version)
    inspect_release_payload(artifacts, artifact, version, members)
    slug = artifact_id.removeprefix("release:")
    output.mkdir(parents=True)
    environment = build_environment(harness, "0", manifest)
    for name in (
        "PYTHONPATH",
        "PYTHONHOME",
        "VIRTUAL_ENV",
        "PERL5LIB",
        "R_LIBS_USER",
        "R_LIBS",
        "GEM_HOME",
        "GEM_PATH",
        "LUA_PATH",
        "LUA_CPATH",
        "NODE_PATH",
    ):
        environment.pop(name, None)
    environment.update(
        COMPOSER_DISABLE_NETWORK="1",
        PIP_NO_INDEX="1",
        npm_config_offline="true",
        npm_config_audit="false",
        npm_config_fund="false",
    )
    with tempfile.TemporaryDirectory(
        prefix="strling-preview-documentation-"
    ) as directory:
        work = Path(directory)
        commands = []
        environment.update(
            COMPOSER_HOME=str(work / "composer-home"),
            npm_config_userconfig=str(work / "user.npmrc"),
            npm_config_globalconfig=str(work / "global.npmrc"),
        )
        for name in ("user.npmrc", "global.npmrc"):
            (work / name).write_text("", encoding="utf-8")
        for name in (
            "NPM_TOKEN",
            "NODE_AUTH_TOKEN",
            "COMPOSER_AUTH",
            "GEM_HOST_API_KEY",
        ):
            environment.pop(name, None)
        fixtures = fixture_files(harness, work)

        def run(command: list[str], cwd: Path | None = None) -> str:
            cwd = cwd or work
            before = set(cwd.glob("consumer-command-*"))
            try:
                return run_consumer(command, cwd, environment)
            finally:
                for path in sorted(set(cwd.glob("consumer-command-*")) - before):
                    if path.is_file():
                        prefix = hashlib.sha256(
                            cwd.relative_to(work).as_posix().encode()
                        ).hexdigest()[:12]
                        destination = output / (prefix + "-" + path.name)
                        shutil.copyfile(path, destination)
                        if path.suffix == ".json":
                            metadata = load_json(path)
                            commands.append(
                                dict(
                                    metadata=destination.name,
                                    metadata_sha256=hashlib.sha256(
                                        destination.read_bytes()
                                    ).hexdigest(),
                                    command=metadata["command"],
                                    exit_code=metadata.get("exit_code"),
                                )
                            )

        library = None
        if slug != "typescript":
            from tooling.release_payload import native_identity
            from tooling.release_native import inspect_native

            if native is None or native.stat().st_size > 128 * 1024 * 1024:
                raise ValueError(
                    "an explicit bounded matching native runtime is required"
                )
            data = native.read_bytes()
            native_identity(data, version)
            inspect_native(data)
            library = work / native.name
            library.write_bytes(data)
        if slug in {"php", "r"}:
            selected = next(row for row in members if row["name"] == "bindings/" + slug)
            package = work / "package"
            copy_subject_directory(artifacts, selected, package)
        if slug == "ruby":
            package = next(
                artifacts / row["name"]
                for row in members
                if row["name"].endswith(".gem")
            )
            install = work / "gems"
            run(
                [
                    "gem",
                    "install",
                    "--local",
                    "--ignore-dependencies",
                    "--no-document",
                    "--install-dir",
                    str(install),
                    str(package),
                ]
            )
            environment.update(GEM_HOME=str(install), GEM_PATH=str(install))
            program = work / "example.rb"
            program.write_text(
                block(work, "bindings/ruby/README.md#1"), encoding="utf-8"
            )
            run(["ruby", str(program), str(library)])
        elif slug == "perl":
            from tooling.release_payload import archive_files

            archive = next(
                artifacts / row["name"]
                for row in members
                if row["name"].endswith(".tar.gz")
            )
            files = archive_files(archive)
            prefixes = {Path(name).parts[0] for name in files}
            if len(prefixes) != 1:
                raise ValueError("ambiguous CPAN archive root")
            package = work / "package"
            for name, data in files.items():
                relative = Path(name).relative_to(next(iter(prefixes)))
                destination = package / relative
                if not destination.resolve().is_relative_to(package.resolve()):
                    raise ValueError("CPAN archive path escapes package")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            install = work / "perl"
            # Makefile.PL and dependency SDKs are the registered local package
            # mechanism; no CPAN resolver or network installation is invoked.
            run(["perl", "Makefile.PL", "INSTALL_BASE=" + str(install)], package)
            run(["make"], package)
            run(["make", "install"], package)
            environment["PERL5LIB"] = str(install / "lib/perl5")
            program = work / "example.pl"
            program.write_text(
                block(work, "bindings/perl/README.md#1"), encoding="utf-8"
            )
            run(["perl", str(program), str(library)])
        elif slug == "php":
            run(
                [
                    "composer",
                    "install",
                    "--no-dev",
                    "--no-scripts",
                    "--no-plugins",
                    "--no-interaction",
                    "--prefer-dist",
                ],
                package,
            )
            program = package / "example.php"
            program.write_text(
                block(work, "bindings/php/README.md#1"), encoding="utf-8"
            )
            run(["php", "-d", "ffi.enable=1", str(program), str(library)])
        elif slug == "r":
            install = work / "r-library"
            install.mkdir()
            run(["R", "CMD", "INSTALL", "--library=" + str(install), str(package)])
            # Put this installed package first while retaining R's ordinary
            # dependency SDK libraries, as the governed R test runner does.
            # Replacing R_LIBS_USER would hide that SDK's jsonlite dependency.
            environment["R_LIBS"] = str(install)
            program = work / "example.R"
            program.write_text(
                "stopifnot(normalizePath(find.package('strling')) == normalizePath("
                + json.dumps(str(install / "strling"))
                + "))\n"
                + block(work, "bindings/r/README.md#1"),
                encoding="utf-8",
            )
            run(["Rscript", "--vanilla", str(program), str(library)])
        elif slug == "lua":
            archive = next(
                artifacts / row["name"]
                for row in members
                if row["name"].endswith(".src.rock")
            )
            install = work / "lua-tree"
            run(
                [
                    "luarocks",
                    "--lua-version=5.1",
                    "--tree=" + str(install),
                    "install",
                    "--deps-mode=none",
                    str(archive),
                ]
            )
            # Preserve only the explicit governed dependency SDK search paths.
            environment["LUA_PATH"] = (
                str(install / "share/lua/5.1/?.lua")
                + ";"
                + str(install / "share/lua/5.1/?/init.lua")
                + ";;"
            )
            environment["LUA_CPATH"] = str(install / "lib/lua/5.1/?.so") + ";;"
            program = work / "example.lua"
            program.write_text(
                block(work, "bindings/lua/README.md#2"), encoding="utf-8"
            )
            run(["lua", str(program), str(library)])
        elif slug == "typescript":
            if typescript_sdk is None:
                raise ValueError(
                    "an explicit governed TypeScript compiler SDK is required"
                )
            from tooling.quality import version_satisfies
            import re

            compiler = load_json(typescript_sdk / "typescript/package.json")
            resolution = load_json(harness / "toolchain.json")["tools"][
                "typescript-binding"
            ]["resolution"]
            governed = re.search(
                resolution["file_pattern"],
                (harness / resolution["file"]).read_text(encoding="utf-8"),
            )
            if governed is None or not version_satisfies(
                compiler["version"], governed[1]
            ):
                raise ValueError("TypeScript SDK differs from its governed constraint")
            archive = next(
                artifacts / row["name"]
                for row in members
                if row["name"].endswith(".tgz")
            )
            (work / "package.json").write_text(
                '{"name":"strling-preview-documentation","private":true,"type":"module"}\n',
                encoding="utf-8",
            )
            run(
                [
                    "npm",
                    "install",
                    "--offline",
                    "--ignore-scripts",
                    "--no-audit",
                    "--no-fund",
                    "--save-exact",
                    str(archive),
                ]
            )
            wasm = work / "node_modules/@strling-lang/strling/dist/strling_interop.wasm"
            identities = (
                "bindings/typescript/README.md#2",
                "bindings/typescript/README.md#3",
                "bindings/typescript/README.md#4",
                "docs/migration-guide.md#5",
            )
            for index, identity in enumerate(identities):
                body = block(work, identity)
                if identity.endswith("README.md#4"):
                    body = (
                        'import {loadBundledWasm} from "@strling-lang/strling/node";\nimport {readFileSync} from "node:fs";\nconst client=await loadBundledWasm();\nconst exactTargetProfile=JSON.parse(readFileSync("target.json","utf8"));\nconst request=JSON.parse(readFileSync("request.json","utf8"));\nconst compileProjection={target_profile:request.target_profile,requested_outputs:request.requested_outputs,compiler_options:request.compiler_options};\n'
                        + body
                    )
                    body += '\nif(response.status!=="success" || (response.compile_result as {outcome:string}).outcome!=="succeeded") throw new Error("Simply example failed");\n'
                elif identity.endswith("README.md#3") or identity.endswith(
                    "migration-guide.md#5"
                ):
                    function = (
                        "describePackage"
                        if identity.endswith("README.md#3")
                        else "connect"
                    )
                    body += (
                        '\nimport {readFileSync} from "node:fs";\nconst bytes=readFileSync('
                        + json.dumps(str(wasm))
                        + ");\nconst buffer=new ArrayBuffer(bytes.byteLength);\nnew Uint8Array(buffer).set(bytes);\nconst value=await "
                        + function
                        + "(buffer);\n"
                    )
                    body += (
                        'if(!(value as {native_abi:{major:number}}).native_abi || (value as {native_abi:{major:number}}).native_abi.major!==1) throw new Error("description failed");\n'
                        if function == "describePackage"
                        else 'if((value.describe() as {native_abi:{major:number}}).native_abi.major!==1) throw new Error("description failed");\n'
                    )
                program = work / f"example-{index}.ts"
                program.write_text(
                    body + '\nconsole.log("documentation passed");\n', encoding="utf-8"
                )
                run(
                    [
                        "node",
                        str(typescript_sdk / "typescript/bin/tsc"),
                        "--module",
                        "nodenext",
                        "--target",
                        "ES2022",
                        "--strict",
                        "--typeRoots",
                        str(typescript_sdk / "@types"),
                        "--types",
                        "node",
                        str(program),
                    ]
                )
                if (
                    not run(["node", str(program.with_suffix(".js"))])
                    .rstrip()
                    .endswith("documentation passed")
                ):
                    raise ValueError("TypeScript documented example did not complete")
        else:
            raise ValueError("unimplemented Preview documentation route")
        result = dict(
            status="passed",
            authority="bounded-preview-documentation",
            supported_claim=False,
            public_retrieval=False,
            engineering=engineering,
            source=source,
            artifact_id=artifact_id,
            runner_scope=host_scope(),
            invocation_id=uuid.uuid4().hex,
            command_evidence=commands,
            product_version=version,
            subject_sha256=_surface_identity(members)[1],
            fixture_sha256=fixtures,
            native_sha256=hashlib.sha256(library.read_bytes()).hexdigest()
            if library
            else None,
            limitations=[
                "Preview policy and dependency-locking limits remain unchanged.",
                "Browser-safe factory execution on Node is not an actual browser support claim.",
            ],
        )
        identities = (
            ("bindings/" + slug + "/README.md#" + ("2" if slug == "lua" else "1"),)
            if slug != "typescript"
            else identities
        )
        completed(result, work, identities)
        registered = load_json(harness / "tests/documentation/1.0/manifest.json")
        expected = expected_proof(registered, slug)
        if slug == "typescript":
            row = next(
                row
                for row in registered["examples"]
                if row["id"] == "docs/migration-guide.md#5"
            )
            expected = sorted(
                [*expected, dict(id=row["id"], sha256=row["sha256"], status="passed")],
                key=lambda row: row["id"],
            )
        if result["documentation_examples"] != expected:
            raise ValueError("Preview documentation producer coverage differs")
        result["evidence_fingerprint"] = document_fingerprint(result)
        (output / "result.json").write_text(
            json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--harness", type=Path, default=ROOT)
    parser.add_argument("--native-library", type=Path)
    parser.add_argument("--typescript-sdk", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engineering", action="store_true")
    args = parser.parse_args()
    result = execute(
        args.artifact_id,
        artifacts=args.artifacts.resolve(),
        harness=args.harness.resolve(),
        output=args.output.resolve(),
        native=args.native_library,
        typescript_sdk=args.typescript_sdk,
        engineering=args.engineering,
    )
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "status",
                    "artifact_id",
                    "authority",
                    "supported_claim",
                    "engineering",
                )
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
