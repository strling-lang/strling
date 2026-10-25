"""Post-validation cross-profile uniqueness tests; all data is synthetic."""

import base64
import copy
import json
import unittest

from tooling import workstation_attestation as audit
from tooling import workstation_evidence as reader


def encoded(value):
    return base64.b64encode(json.dumps(value).encode()).decode()


def profile(label, pid):
    payload = dict(
        prospective_plan=dict(invocation=dict(invocation_id=label)),
        builds={
            lane: dict(built=dict(build_root=f"C:/{label}/{lane}"))
            for lane in ("reference", "candidate", "slowdown")
        },
        cohort=dict(
            observations=[
                dict(
                    coordinate=["memory:kernel-peak-rss", "fixture:semantic-tiny"],
                    files={
                        "root-exit.json": encoded(dict(pid=pid, birth="1000")),
                        "stdout.bin": encoded(
                            dict(memory_lifetime=dict(pid=pid + 1, birth_100ns=1200))
                        ),
                    },
                )
            ]
        ),
    )
    return dict(
        deterministic_evidence=dict(
            operations=[
                dict(
                    operation_id="performance_resource_full_certification",
                    structured_evidence=dict(
                        checks=[
                            dict(id="method:shared-workstation-v1", details=payload)
                        ]
                    ),
                )
            ]
        )
    )


def payload(artifact):
    return artifact["deterministic_evidence"]["operations"][0]["structured_evidence"][
        "checks"
    ][0]["details"]


class WorkstationProfileUniquenessTests(unittest.TestCase):
    def test_separately_verified_profile_identities_remain_distinct(self):
        result = audit.require_distinct_profile_campaigns(
            [profile("full", 17), profile("release", 27)],
            reader.parse,
            lambda value: value,
        )
        self.assertEqual(
            result, dict(invocations=2, unique_processes=4, unique_build_roots=6)
        )

    def test_context_build_root_and_process_reuse_cannot_cross_profiles(self):
        full, release = profile("full", 17), profile("release", 27)
        attacks = [
            lambda p: p["prospective_plan"]["invocation"].__setitem__(
                "invocation_id", "full"
            ),
            lambda p: p["builds"]["reference"]["built"].__setitem__(
                "build_root", "C:/full/reference"
            ),
            lambda p: p["cohort"]["observations"][0]["files"].__setitem__(
                "root-exit.json", encoded(dict(pid=17, birth="1000"))
            ),
            lambda p: p["cohort"]["observations"][0]["files"].__setitem__(
                "stdout.bin",
                encoded(dict(memory_lifetime=dict(pid=18, birth_100ns=1200))),
            ),
        ]
        for attack in attacks:
            changed = copy.deepcopy(release)
            attack(payload(changed))
            with self.assertRaises(ValueError):
                audit.require_distinct_profile_campaigns(
                    [full, changed], reader.parse, lambda value: value
                )


if __name__ == "__main__":
    unittest.main()
