"""Source-factory regression tests against the ratified frontend identities."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = 'semantic strling 1.0;\ncase sensitive;\npattern text "hello";\n'


class SourceFrontendDefaultsTests(unittest.TestCase):
    def request(self, options: dict[str, object] | None = None) -> dict[str, object]:
        script = (
            "import json,sys;"
            "sys.path.insert(0,sys.argv[1]);"
            "from STRling.compiler import source_compile_request;"
            "print(json.dumps(source_compile_request(sys.argv[2],json.loads(sys.argv[3]))))"
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                script,
                str(ROOT / "bindings/python/src"),
                SOURCE,
                json.dumps(options),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_default_source_selects_ratified_semantic_frontend(self) -> None:
        request = self.request()
        document = request["input"]["document"]
        self.assertEqual(
            {"id": "strling.semantic", "dialect_version": "1.0.0"},
            document["frontend"],
        )
        self.assertEqual("text/x-strling-semantic", document["content"]["media_type"])
        self.assertEqual(SOURCE, document["content"]["text"])
        self.assertEqual("1.0-draft.1", request["specification_version"])

    def test_dialect_default_does_not_follow_independent_specification_version(
        self,
    ) -> None:
        request = self.request({"specification_version": "2.0-draft.1"})
        self.assertEqual("2.0-draft.1", request["specification_version"])
        self.assertEqual(
            "1.0.0", request["input"]["document"]["frontend"]["dialect_version"]
        )

    def test_explicit_regex_frontend_gets_its_exact_transport_media_type(self) -> None:
        document = self.request({"frontend_id": "strling.regex-compat"})["input"][
            "document"
        ]
        self.assertEqual(
            {"id": "strling.regex-compat", "dialect_version": "1.0.0"},
            document["frontend"],
        )
        self.assertEqual(
            "text/x-strling-regex-compat", document["content"]["media_type"]
        )

    def test_obsolete_explicit_identity_is_not_silently_reinterpreted(self) -> None:
        document = self.request(
            {
                "frontend_id": "semantic_strling",
                "frontend_version": "1.0-draft.1",
                "media_type": "text/strling",
            }
        )["input"]["document"]
        self.assertEqual(
            {"id": "semantic_strling", "dialect_version": "1.0-draft.1"},
            document["frontend"],
        )
        self.assertEqual("text/strling", document["content"]["media_type"])

    def test_explicit_unknown_frontend_and_version_reach_canonical_refusal(
        self,
    ) -> None:
        document = self.request(
            {
                "frontend_id": "example.unsupported",
                "frontend_version": "9.7.3",
                "media_type": "text/x-example",
            }
        )["input"]["document"]
        self.assertEqual(
            {"id": "example.unsupported", "dialect_version": "9.7.3"},
            document["frontend"],
        )
        self.assertEqual("text/x-example", document["content"]["media_type"])


if __name__ == "__main__":
    unittest.main()
