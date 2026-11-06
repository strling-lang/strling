from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tooling import jvm_adapter_runtime as runtime


class JvmAdapterRuntimeTests(unittest.TestCase):
    def test_current_repository_has_one_governed_shared_bridge(self) -> None:
        runtime._assert_dependency_direction()

    def test_kotlin_bridge_tracks_authority_and_rejects_stale_or_duplicate_routes(
        self,
    ) -> None:
        for dependency, accepted in (
            ('api("com.strling:strling-jvm:4.1.0")', True),
            ('api("com.strling:strling-jvm:3.0.0")', False),
            ('api("com.strling:strling-jvm:4.1.0-extra")', False),
            (
                'api("com.strling:strling-jvm:4.1.0")\n'
                'api("com.strling:strling-jvm:3.0.0")',
                False,
            ),
        ):
            with self.subTest(dependency=dependency), TemporaryDirectory() as directory:
                root = Path(directory)
                for path, text in (
                    ("bindings/java/pom.xml", "<artifactId>strling-jvm</artifactId>"),
                    ("bindings/kotlin/build.gradle.kts", dependency),
                    (
                        "bindings/jvm/pom.xml",
                        "<artifactId>jna</artifactId><version>5.19.1</version>",
                    ),
                ):
                    output = root / path
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_text(text, encoding="utf-8")
                with (
                    patch.object(runtime, "ROOT", root),
                    patch.object(runtime, "get_source_version", return_value="4.1.0"),
                ):
                    if accepted:
                        runtime._assert_dependency_direction()
                    else:
                        with self.assertRaisesRegex(
                            runtime.JvmAdapterRuntimeError, "exactly one shared bridge"
                        ):
                            runtime._assert_dependency_direction()

    def test_fingerprint_is_order_stable(self) -> None:
        self.assertEqual(
            runtime._fingerprint({"b": 2, "a": 1}),
            runtime._fingerprint({"a": 1, "b": 2}),
        )

    def test_repository_gradle_wrapper_precedes_host_tool(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            wrapper = (
                root
                / "bindings/kotlin"
                / ("gradlew.bat" if runtime.os.name == "nt" else "gradlew")
            )
            wrapper.parent.mkdir(parents=True)
            wrapper.write_text("governed wrapper", encoding="utf-8")
            with (
                patch.object(runtime, "ROOT", root),
                patch.object(runtime, "_tool", side_effect=AssertionError),
            ):
                self.assertEqual(str(wrapper), runtime._gradle_tool())

    def test_host_gradle_is_fallback_when_wrapper_is_absent(self) -> None:
        with TemporaryDirectory() as directory:
            with (
                patch.object(runtime, "ROOT", Path(directory)),
                patch.object(runtime, "_tool", return_value="host-gradle") as tool,
            ):
                self.assertEqual("host-gradle", runtime._gradle_tool())
                tool.assert_called_once_with("STRLING_GRADLE", ("gradle", "gradle.bat"))

    def test_declared_maven_repository_is_forced_on_maven_commands(self) -> None:
        with TemporaryDirectory() as directory:
            repository = Path(directory).resolve()
            with patch.dict(
                runtime.os.environ,
                {"STRLING_MAVEN_REPOSITORY": str(repository)},
                clear=True,
            ):
                resolved, argument = runtime._maven_repository()
            self.assertEqual(str(repository), resolved)
            self.assertEqual(f"-Dmaven.repo.local={repository}", argument)

    def test_missing_declared_maven_repository_fails_closed(self) -> None:
        with patch.dict(runtime.os.environ, {}, clear=True):
            with self.assertRaisesRegex(FileNotFoundError, "STRLING_MAVEN_REPOSITORY"):
                runtime._maven_repository()


if __name__ == "__main__":
    unittest.main()
