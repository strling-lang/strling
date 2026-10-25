"""Gateway authority tests use a synthetic controller, never native samples."""

import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from tooling import workstation_certification as gateway

ROOT = Path(__file__).resolve().parents[2]


class GatewayAuthorityTests(unittest.TestCase):
    def authority(self):
        class ControllerError(ValueError):
            pass

        calls = []

        def certify(profile, **kwargs):
            calls.append((profile, kwargs))
            return dict(
                commit="a" * 40,
                checks=[dict(id="synthetic-contract", status="passed", details={})],
            )

        def evidence(**kwargs):
            return kwargs

        return SimpleNamespace(
            ROOT=ROOT,
            MANIFEST_PATH=ROOT
            / "tests/certification/performance-resource/1.0/manifest.json",
            load_json=lambda path: json.loads(path.read_bytes()),
            certify=certify,
            _certification_evidence=evidence,
            PerformanceResourceError=ControllerError,
            calls=calls,
        )

    def test_local_contract_retains_the_calling_controller_and_ledger(self):
        authority = self.authority()
        ledger = object()
        result = gateway.certify(
            "local", root=ROOT, authority=authority, execution_ledger=ledger
        )
        self.assertEqual(authority.calls[0][0], "local")
        self.assertIs(authority.calls[0][1]["execution_ledger"], ledger)
        self.assertEqual(result["checks"][-1]["id"], gateway.METHOD_CHECK)
        self.assertIs(result["checks"][-1]["details"]["live_measurement"], False)

    def test_controlled_errors_use_the_actual_main_module_error_class(self):
        authority = self.authority()
        with self.assertRaises(authority.PerformanceResourceError):
            gateway.certify("full", root=ROOT, authority=authority, preflight_only=True)
        self.assertEqual(authority.calls, [])


if __name__ == "__main__":
    unittest.main()
