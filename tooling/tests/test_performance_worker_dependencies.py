"""Keep worker-only preparation separate from the complete runner contract."""

from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tests/certification/performance-resource/1.0/runner/Cargo.toml"


class PerformanceWorkerDependencyTests(unittest.TestCase):
    def setUp(self):
        self.manifest = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_full_runner_dependencies_remain_enabled_by_default(self):
        self.assertEqual(self.manifest["features"]["default"], ["full-runner"])
        self.assertEqual(
            self.manifest["features"]["full-runner"],
            ["dep:strling", "dep:strling-interop"],
        )

    def test_worker_does_not_require_public_or_interop_artifacts(self):
        dependencies = self.manifest["dependencies"]
        for name in ("strling", "strling-interop"):
            with self.subTest(dependency=name):
                self.assertIs(dependencies[name].get("optional"), True)
        self.assertEqual(dependencies["serde_json"], "1.0")
        self.assertEqual(
            dependencies["strling-kernel"], {"path": "../../../../../core/internal"}
        )

    def test_full_runner_cannot_build_with_incomplete_dependency_selection(self):
        binaries = {item["name"]: item for item in self.manifest["bin"]}
        self.assertEqual(
            binaries["strling-performance-runner"]["required-features"],
            ["full-runner"],
        )
        self.assertEqual(
            binaries["strling-performance-memory-worker"],
            {
                "name": "strling-performance-memory-worker",
                "path": "src/memory_worker.rs",
            },
        )
        self.assertEqual(len(binaries), 2)

    def test_codegen_and_runtime_semantics_are_not_changed(self):
        self.assertEqual(
            self.manifest["profile"]["release"],
            {"codegen-units": 1, "lto": "thin"},
        )
        self.assertEqual(self.manifest["package"]["rust-version"], "1.75")


if __name__ == "__main__":
    unittest.main()
