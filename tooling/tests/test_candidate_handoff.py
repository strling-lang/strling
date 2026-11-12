"""Synthetic handoff mutations must not turn certification into publication."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tooling import candidate_handoff, candidate_integrity
from tooling.local_certification_attestation import AttestationError


class CandidateHandoffBoundaryTests(unittest.TestCase):
    def test_every_derived_field_is_required_and_exact(self):
        expected = dict(
            source_sha="a" * 40,
            distributions=[dict(artifact_id="synthetic")],
            provisional_public_rc=dict(coordinate="4.0.0-rc.1"),
            publication_authorized=False,
            registry_mutation_authorized=False,
            public_release_verified=False,
            certification=dict(evidence_root_sha256="b" * 64),
            documentation=dict(subjects={"synthetic": "c" * 64}),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "handoff.json"
            with patch.object(candidate_handoff, "derive", return_value=expected):
                path.write_text(json.dumps(expected), encoding="utf-8")
                self.assertEqual(
                    "passed", candidate_handoff.verify(root, root, root, path)["status"]
                )
                for key in expected:
                    with self.subTest(field=key):
                        observed = copy.deepcopy(expected)
                        if key in {
                            "publication_authorized",
                            "registry_mutation_authorized",
                            "public_release_verified",
                        }:
                            observed[key] = True
                        elif key == "provisional_public_rc":
                            observed[key]["reserved"] = True
                        else:
                            observed[key] = None
                        path.write_text(json.dumps(observed), encoding="utf-8")
                        with self.assertRaises(ValueError):
                            candidate_handoff.verify(root, root, root, path)

    def test_invalid_signature_cannot_create_a_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "handoff.json"
            arguments = [
                "candidate_integrity",
                "--repository-root",
                str(root),
                "--trust-root",
                str(root),
                "--bundle",
                str(root),
                "--handoff",
                str(path),
                "--write-handoff",
            ]
            with (
                patch("sys.argv", arguments),
                patch.object(
                    candidate_integrity,
                    "verify_attestation",
                    side_effect=AttestationError("invalid signature"),
                ),
                patch.object(candidate_integrity, "derive") as derive,
            ):
                with self.assertRaises(AttestationError):
                    candidate_integrity.main()
                derive.assert_not_called()
                self.assertFalse(path.exists())

    def test_unregistered_rc_coordinate_is_rejected_before_loading_evidence(self):
        for version in ("latest", "4.0.0", "4.0.0-rc.0", "4.0.0-rc.01", "5.0.0-rc.1"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                candidate_handoff.derive(
                    Path("missing"),
                    Path("missing"),
                    Path("missing"),
                    provisional_rc=version,
                )


if __name__ == "__main__":
    unittest.main()
