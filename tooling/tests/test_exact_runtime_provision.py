from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tooling.exact_runtime_provision import (
    ExactRuntimeProvisionError,
    main,
    pull_request_environment,
    runtime_environment,
    verify_maven_repository,
    verify_pull_request_environment,
    write_environment,
)
from tooling.exact_runtime_toolchains import ExactRuntimeToolchainError, load_manifest


class ExactRuntimeProvisionTests(unittest.TestCase):
    def maven_fixture(self, directory: Path) -> tuple[Path, Path, Path]:
        repository = directory / "repository"
        coordinates = (
            "com.fasterxml.jackson.core:jackson-annotations:2.18.10",
            "com.fasterxml.jackson.core:jackson-core:2.18.10",
            "com.fasterxml.jackson.core:jackson-databind:2.18.10",
            "net.java.dev.jna:jna:5.19.1",
        )
        components = []
        for coordinate in coordinates:
            group, name, version = coordinate.split(":")
            jar = (
                repository
                / Path(*group.split("."))
                / name
                / version
                / f"{name}-{version}.jar"
            )
            jar.parent.mkdir(parents=True, exist_ok=True)
            jar.write_bytes(coordinate.encode("utf-8"))
            components.append(
                f'<component group="{group}" name="{name}" version="{version}">'
                f'<artifact name="{jar.name}"><sha256 value="'
                f"{hashlib.sha256(jar.read_bytes()).hexdigest()}"
                '"/></artifact></component>'
            )
        bridge = repository / "com/strling/strling-jvm/3.0.0/strling-jvm-3.0.0.jar"
        bridge.parent.mkdir(parents=True)
        bridge.write_bytes(b"prepared bridge")
        graph = directory / "release-graph.json"
        graph.write_text(
            json.dumps(
                {
                    "roots": {"jvm": ["com.strling:strling-jvm:3.0.0", *coordinates]},
                    "packages": [
                        {"coordinate": coordinate, "internal": False}
                        for coordinate in coordinates
                    ],
                    "fingerprint": "sha256:fixture",
                }
            ),
            encoding="utf-8",
        )
        metadata = directory / "verification-metadata.xml"
        metadata.write_text(
            "<verification-metadata><components>"
            + "".join(components)
            + "</components></verification-metadata>",
            encoding="utf-8",
        )
        return repository, graph, metadata

    def test_environment_handoff_is_complete_and_stable(self) -> None:
        environment = runtime_environment(load_manifest())
        self.assertEqual(
            {
                "STRLING_CPYTHON_311_BINARY": (
                    "/opt/strling-toolchains/install/cpython-3.11.15/bin/python3.11"
                ),
                "STRLING_NODE_22_BINARY": "/opt/node-v22.23.2-linux-x64/bin/node",
                "STRLING_PCRE2_1042_LIBRARY": (
                    "/opt/pcre2-10.42-build-default/libpcre2-8.so.0.11.2"
                ),
                "STRLING_PCRE2_1043_LIBRARY": (
                    "/opt/pcre2-10.43-build-default/libpcre2-8.so.0.12.0"
                ),
            },
            environment,
        )

    @mock.patch.dict("tooling.exact_runtime_provision.os.environ", {}, clear=True)
    def test_pull_request_handoff_adds_maven_and_java_to_exact_runtimes(self) -> None:
        environment = pull_request_environment(load_manifest())
        self.assertEqual(
            str(Path.home() / ".m2" / "repository"),
            environment["STRLING_MAVEN_REPOSITORY"],
        )
        self.assertEqual("/opt/temurin-11.0.32+9", environment["JAVA_HOME"])
        self.assertIn("STRLING_PCRE2_1042_LIBRARY", environment)
        self.assertIn("STRLING_PCRE2_1043_LIBRARY", environment)

    def test_maven_repository_accepts_governed_artifacts_and_offline_probe(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, graph, metadata = self.maven_fixture(Path(directory))
            completed = mock.Mock(returncode=0, stdout="", stderr="")
            run = mock.Mock(return_value=completed)
            result = verify_maven_repository(
                repository,
                release_graph_path=graph,
                verification_metadata_path=metadata,
                run=run,
            )
        self.assertEqual(4, len(result["verified_artifacts"]))
        command = run.call_args.args[0]
        self.assertIn("-o", command)
        self.assertIn(f"-Dmaven.repo.local={repository.resolve()}", command)
        self.assertEqual(subprocess.DEVNULL, run.call_args.kwargs["stdin"])

    def test_maven_repository_rejects_missing_and_wrong_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository, graph, metadata = self.maven_fixture(Path(directory))
            bad = repository / ("net/java/dev/jna/jna/5.19.1/jna-5.19.1.jar")
            bad.write_bytes(b"wrong")
            with self.assertRaisesRegex(
                ExactRuntimeProvisionError, "artifact SHA-256 differs"
            ):
                verify_maven_repository(
                    repository,
                    release_graph_path=graph,
                    verification_metadata_path=metadata,
                    run=mock.Mock(),
                )
            bad.unlink()
            with self.assertRaisesRegex(
                ExactRuntimeProvisionError, "repository is missing"
            ):
                verify_maven_repository(
                    repository,
                    release_graph_path=graph,
                    verification_metadata_path=metadata,
                    run=mock.Mock(),
                )

    def test_pull_request_preflight_fails_closed_on_missing_or_wrong_pcre2(
        self,
    ) -> None:
        for reason in (
            "STRLING_PCRE2_1042_LIBRARY is not configured",
            "PCRE2 10.42 runtime identity differs",
        ):
            with (
                self.subTest(reason=reason),
                mock.patch(
                    "tooling.exact_runtime_provision.verify_configured_runtimes",
                    side_effect=ExactRuntimeToolchainError(reason),
                ),
                self.assertRaisesRegex(ExactRuntimeToolchainError, reason),
            ):
                verify_pull_request_environment(load_manifest())

    def test_pull_request_preflight_hands_declared_maven_repository_to_validator(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            with (
                mock.patch.dict(
                    "tooling.exact_runtime_provision.os.environ",
                    {"STRLING_MAVEN_REPOSITORY": str(repository)},
                    clear=True,
                ),
                mock.patch(
                    "tooling.exact_runtime_provision.verify_configured_runtimes",
                    return_value={"status": "passed"},
                ),
                mock.patch(
                    "tooling.exact_runtime_provision.verify_maven_repository",
                    return_value={"path": str(repository)},
                ) as verify_maven,
            ):
                result = verify_pull_request_environment(load_manifest())
        self.assertEqual("passed", result["status"])
        verify_maven.assert_called_once_with(repository)

    def test_environment_file_is_sorted_and_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "github.env"
            path.write_text("EXISTING=value\n", encoding="utf-8")
            write_environment(path, {"ZETA": "/z", "ALPHA": "/a"})
            self.assertEqual(
                "EXISTING=value\nALPHA=/a\nZETA=/z\n",
                path.read_text(encoding="utf-8"),
            )

    def test_environment_file_rejects_line_injection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "github.env"
            with self.assertRaises(ExactRuntimeProvisionError):
                write_environment(path, {"RUNTIME": "/safe\nUNSAFE=value"})
            self.assertFalse(path.exists())

    def test_environment_file_rejects_malformed_variable_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "github.env"
            with self.assertRaises(ExactRuntimeProvisionError):
                write_environment(path, {"RUNTIME=UNSAFE": "/safe"})
            self.assertFalse(path.exists())

    def test_execute_mode_hands_verified_environment_to_strict_audit(self) -> None:
        manifest = load_manifest()
        environment = runtime_environment(manifest)
        completed = mock.Mock(returncode=0)
        with (
            mock.patch(
                "tooling.exact_runtime_provision.load_manifest", return_value=manifest
            ),
            mock.patch(
                "tooling.exact_runtime_provision.verify_configured_runtimes",
                return_value={"toolchains": manifest["toolchains"]},
            ),
            mock.patch(
                "tooling.exact_runtime_provision.subprocess.run", return_value=completed
            ) as run,
            mock.patch(
                "sys.argv", ["exact-runtime-provision", "--execute-adversarial"]
            ),
            mock.patch("sys.stdout", new=io.StringIO()),
            mock.patch.dict(
                "tooling.exact_runtime_provision.os.environ", {}, clear=True
            ),
        ):
            self.assertEqual(0, main())
            command = run.call_args.args[0]
            self.assertIn("tooling.adversarial_semantic_audit", command)
            self.assertIn("--strict", command)
            self.assertIn("--output", command)
            for name, value in environment.items():
                self.assertEqual(value, run.call_args.kwargs["env"][name])


if __name__ == "__main__":
    unittest.main()
