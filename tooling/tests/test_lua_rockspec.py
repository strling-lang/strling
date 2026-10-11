from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tooling.lua_rockspec import (
    RockspecError,
    check_generated,
    materialize,
    render_rockspec,
    rockspec_name,
    verify_rockspec,
)


TEMPLATE = """package = "strling"
version = "VERSION-1"
source = { tag = "vVERSION" }
"""


class LuaRockspecTests(unittest.TestCase):
    def test_render_preserves_release_revision_contract(self) -> None:
        self.assertIn('version = "3.0.0-1"', render_rockspec(TEMPLATE, "3.0.0"))
        self.assertIn(
            'version = "3.0.0-rc1-2"',
            render_rockspec(TEMPLATE, "3.0.0-rc1-2"),
        )
        self.assertEqual("strling-3.0.0-rc1-2.rockspec", rockspec_name("3.0.0-rc1-2"))

    def test_materialized_output_verifies_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template.rockspec"
            template.write_text(TEMPLATE, encoding="utf-8")
            output = materialize("3.0.0", root, template)
            self.assertEqual("strling-3.0.0-1.rockspec", output.name)
            verify_rockspec("3.0.0", output, template)

    def test_verification_rejects_content_or_filename_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template.rockspec"
            template.write_text(TEMPLATE, encoding="utf-8")
            output = materialize("3.0.0", root, template)
            output.write_text("stale\n", encoding="utf-8")
            with self.assertRaisesRegex(RockspecError, "content"):
                verify_rockspec("3.0.0", output, template)
            with self.assertRaisesRegex(RockspecError, "filename"):
                verify_rockspec("3.0.0", root / "wrong.rockspec", template)

    def test_template_requires_both_governed_placeholders(self) -> None:
        with self.assertRaisesRegex(RockspecError, "exactly one"):
            render_rockspec('version = "VERSION-1"\n', "3.0.0")

    def test_generated_check_is_read_only_and_regeneration_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template.rockspec"
            template.write_text(TEMPLATE, encoding="utf-8")
            output = materialize("3.0.0", root, template)
            first = output.read_bytes()
            self.assertEqual(output, check_generated("3.0.0", root, template))
            materialize("3.0.0", root, template)
            self.assertEqual(first, output.read_bytes())
            self.assertEqual(output, check_generated("3.0.0", root, template))
            self.assertEqual(first, output.read_bytes())

    def test_generated_check_rejects_missing_stale_and_unexpected_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template.rockspec"
            template.write_text(TEMPLATE, encoding="utf-8")
            with self.assertRaisesRegex(RockspecError, "set differs"):
                check_generated("3.0.0", root, template)
            self.assertEqual([template], list(root.iterdir()))
            output = materialize("3.0.0", root, template)
            output.write_text("stale\n", encoding="utf-8")
            stale = output.read_bytes()
            with self.assertRaisesRegex(RockspecError, "content"):
                check_generated("3.0.0", root, template)
            self.assertEqual(stale, output.read_bytes())
            materialize("3.0.0", root, template)
            materialize("2.0.0", root, template)
            with self.assertRaisesRegex(RockspecError, "set differs"):
                check_generated("3.0.0", root, template)

    def test_generated_check_rejects_noncanonical_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template.rockspec"
            template.write_text(TEMPLATE, encoding="utf-8")
            output = materialize("3.0.0", root, template)
            output.write_bytes(output.read_bytes().replace(b"\n", b"\r\n"))
            before = output.read_bytes()
            with self.assertRaisesRegex(RockspecError, "content"):
                check_generated("3.0.0", root, template)
            self.assertEqual(before, output.read_bytes())

    def test_generated_check_rejects_malformed_template_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template.rockspec"
            template.write_text('version = "VERSION-1"\n', encoding="utf-8")
            with self.assertRaisesRegex(RockspecError, "exactly one"):
                check_generated("3.0.0", root, template)
            self.assertEqual([template], list(root.iterdir()))


@unittest.skipUnless(
    os.name == "posix" and shutil.which("bash"), "setup fixture requires POSIX Bash"
)
class LuaSetupImmutabilityTests(unittest.TestCase):
    def fixture(self, container: Path) -> tuple[Path, Path, dict[str, str]]:
        repository = container / "candidate"
        binding = repository / "bindings/lua"
        binding.mkdir(parents=True)
        tooling = repository / "tooling"
        tooling.mkdir()
        governance = repository / "governance"
        governance.mkdir()
        actual_root = Path(__file__).resolve().parents[2]
        shutil.copyfile(actual_root / "bindings/lua/setup.sh", binding / "setup.sh")
        shutil.copyfile(
            actual_root / "tooling/lua_rockspec.py", tooling / "lua_rockspec.py"
        )
        (governance / "release-policy.json").write_text(
            json.dumps({"product": {"repository_projection": {"version": "3.0.0"}}}),
            encoding="utf-8",
        )
        (binding / "strling-template.rockspec").write_text(TEMPLATE, encoding="utf-8")
        commands = container / "commands"
        commands.mkdir()
        log = container / "luarocks-calls"
        scripts = {
            "python3": f'#!/bin/bash\nexec "{sys.executable}" "$@"\n',
            "luarocks": '#!/bin/bash\nprintf "%s\\n" "$*" >> "$LUA_SETUP_CALLS"\n',
            "id": "#!/bin/bash\nprintf '1000\\n'\n",
        }
        for name, content in scripts.items():
            path = commands / name
            path.write_text(content, encoding="utf-8")
            path.chmod(0o755)
        environment = dict(os.environ)
        environment.update(
            {
                "PATH": str(commands) + os.pathsep + os.environ["PATH"],
                "LUA_SETUP_CALLS": str(log),
                "STRLING_VERSION": "dev",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        return binding, log, environment

    def snapshot(self, repository: Path) -> dict[str, tuple[bytes, int]]:
        return {
            path.relative_to(repository).as_posix(): (
                path.read_bytes(),
                stat.S_IMODE(path.stat().st_mode),
            )
            for path in repository.rglob("*")
            if path.is_file()
        }

    def run_setup(
        self, binding: Path, environment: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "setup.sh"],
            cwd=binding,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_fresh_setup_consumes_prepared_version_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            binding, log, environment = self.fixture(Path(directory))
            materialize("3.0.0", binding, binding / "strling-template.rockspec")
            repository = binding.parents[1]
            original = self.snapshot(repository)
            result = self.run_setup(binding, environment)
            self.assertEqual(0, result.returncode, result.stderr)
            calls = log.read_text(encoding="utf-8").splitlines()
            self.assertEqual("path --bin", calls[0])
            self.assertEqual(4, len(calls))
            self.assertTrue(calls[1].startswith("install --local --only-deps "))
            self.assertEqual("install --local busted", calls[2])
            self.assertTrue(calls[3].startswith("make --local "))
            self.assertTrue(calls[1].endswith("strling-3.0.0-1.rockspec"))
            self.assertTrue(calls[3].endswith("strling-3.0.0-1.rockspec"))
            self.assertEqual(original, self.snapshot(repository))
            self.assertFalse((binding / "strling-dev-1.rockspec").exists())

    def test_missing_and_stale_setup_fail_before_any_build_without_mutation(
        self,
    ) -> None:
        for state in ("missing", "stale"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as directory:
                binding, log, environment = self.fixture(Path(directory))
                if state == "stale":
                    output = materialize(
                        "3.0.0", binding, binding / "strling-template.rockspec"
                    )
                    output.write_text("stale\n", encoding="utf-8")
                repository = binding.parents[1]
                original = self.snapshot(repository)
                result = self.run_setup(binding, environment)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("prepare the canonical Lua rockspec", result.stderr)
                self.assertFalse(log.exists())
                self.assertEqual(original, self.snapshot(repository))


if __name__ == "__main__":
    unittest.main()
