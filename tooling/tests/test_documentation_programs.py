"""The example wrapper must preserve Python imports and application context."""

import contextlib
import io
import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

from tooling.documentation_programs import prepare, python_program


def test_reviewed_python_examples_execute_with_function_local_imports(tmp_path):
    root = Path(__file__).resolve().parents[2]
    prepare(root, tmp_path)
    for name in ("request.json", "target.json"):
        (tmp_path / name).write_text(json.dumps({}), encoding="utf-8")
    native_calls = []
    compilation_calls = []

    def load_native(*arguments):
        native_calls.append(arguments)
        return types.SimpleNamespace(describe=lambda: {"native_abi": {"major": 1}})

    class Compiler:
        def __init__(self, client):
            self.client = client

        def compile(self, request):
            compilation_calls.append(request)
            return {"outcome": "succeeded"}

    class Pattern:
        def compile(self, client, projection, profile):
            assert projection == profile == {}
            compilation_calls.append("simply")
            return {"status": "success", "compile_result": {"outcome": "succeeded"}}

    module = types.ModuleType("STRling")
    module.load_native = load_native
    module.Compiler = Compiler
    module.source_compile_request = lambda *arguments: arguments
    module.bundled_library_path = lambda: Path("authenticated-library")
    module.simply = types.SimpleNamespace(
        lit=lambda text: text,
        digit=lambda *bounds: bounds,
        merge=lambda *patterns: Pattern(),
    )
    previous = Path.cwd()
    output = io.StringIO()
    try:
        os.chdir(tmp_path)
        with (
            patch.dict(sys.modules, {"STRling": module}),
            contextlib.redirect_stdout(output),
        ):
            exec(
                compile(python_program(tmp_path), "reviewed-python-examples", "exec"),
                {},
            )
    finally:
        os.chdir(previous)
    assert len(compilation_calls) == 4
    assert len(native_calls) == 9
    assert output.getvalue().rstrip().endswith("documentation passed")
