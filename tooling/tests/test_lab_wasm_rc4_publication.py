"""Exercise the RC4-specific publication locks without provider writes."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tooling import lab_wasm_rc4_publication as publication


class Rc4PublicationTests(unittest.TestCase):
    def setUp(self):
        self.spec = publication.load(publication.POLICY)
        self.context = {
            "workflow_sha": "1" * 40,
            "run_id": "70",
            "run_attempt": "1",
            "environment": "release",
        }
        self.env = {
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REPOSITORY": self.spec["repository"],
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": self.context["workflow_sha"],
            "GITHUB_WORKFLOW_SHA": self.context["workflow_sha"],
            "GITHUB_RUN_ID": self.context["run_id"],
            "GITHUB_RUN_ATTEMPT": self.context["run_attempt"],
            "GITHUB_ACTOR": self.spec["owner"],
            "GITHUB_TRIGGERING_ACTOR": self.spec["owner"],
            "RC4_ENVIRONMENT": "release",
        }
        self.approval = publication.approval_document(self.spec, self.context)
        self.digest = publication.sha(publication.canonical(self.approval))
        self.decision = {
            "user": {"login": self.spec["owner"]},
            "state": "approved",
            "comment": "P20-T05 approve sha256:" + self.digest,
            "environments": [{"name": "release"}],
        }

    def release(self, *, draft=True):
        return {
            "id": 451,
            "tag_name": self.spec["tag"],
            "target_commitish": self.spec["adapter_source"],
            "draft": draft,
            "prerelease": True,
            "immutable": not draft,
            "name": f"STRling Lab Wasm {self.spec['version']} Preview",
            "body": publication.release_notes(self.spec),
            "assets": [
                {
                    "name": name,
                    "state": "uploaded",
                    "size": entry["bytes"],
                    "digest": "sha256:" + entry["sha256"],
                }
                for name, entry in self.spec["assets"].items()
            ],
        }

    def test_workflow_context_is_exact(self):
        self.assertEqual(publication.context(self.spec, self.env), self.context)
        for field, value in {
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_REF": "refs/tags/v4.0.3",
            "GITHUB_REPOSITORY": "another/strling",
            "GITHUB_WORKFLOW_SHA": "2" * 40,
            "GITHUB_RUN_ID": "0",
            "GITHUB_RUN_ATTEMPT": "1;2",
            "GITHUB_TRIGGERING_ACTOR": "another-account",
        }.items():
            with self.subTest(field=field), self.assertRaises(ValueError):
                publication.context(self.spec, {**self.env, field: value})

    def test_only_exact_owner_environment_approval_is_accepted(self):
        self.assertEqual(
            publication.verify_approval(self.approval, self.env, [self.decision]),
            self.digest,
        )
        for alteration in [
            {"state": "rejected"},
            {"comment": "Ship it"},
            {"user": {"login": "another-account"}},
            {"environments": [{"name": "release-attestation"}]},
        ]:
            with self.subTest(alteration=alteration), self.assertRaises(ValueError):
                publication.verify_approval(
                    self.approval, self.env, [{**self.decision, **alteration}]
                )
        for field, changed in [
            ("workflow_sha", "2" * 40),
            ("run_id", "71"),
            ("run_attempt", "2"),
        ]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                proposal = publication.approval_document(
                    self.spec, {**self.context, field: changed}
                )
                publication.verify_approval(proposal, self.env, [self.decision])
        with self.assertRaises(ValueError):
            publication.verify_approval(self.approval, self.env, [])
        with self.assertRaises(ValueError):
            publication.verify_approval(
                self.approval,
                {**self.env, "RC4_ENVIRONMENT": "release-attestation"},
                [self.decision],
            )

    def test_local_bytes_and_complete_attestation_required(self):
        names = {
            publication.WASM: b"\x00asm-pinned",
            publication.ATTESTATION: b"signed-evidence",
        }
        spec = {
            "assets": {
                name: {"bytes": len(data), "sha256": publication.sha(data)}
                for name, data in names.items()
            }
        }
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in names.items():
                (root / name).write_bytes(data)
            publication.verify_local_assets(root, spec)
            wasm = root / publication.WASM
            wasm.write_bytes(b"\x00asm-edited")
            with self.assertRaisesRegex(ValueError, "asset identity"):
                publication.verify_local_assets(root, spec)
            wasm.write_bytes(names[publication.WASM])
            (root / publication.ATTESTATION).unlink()
            with self.assertRaisesRegex(ValueError, "missing or unexpected"):
                publication.verify_local_assets(root, spec)

    def test_coordinate_and_immutability_reads_fail_closed(self):
        tag = f"git/ref/tags/{self.spec['tag']}"
        release = f"releases/tags/{self.spec['tag']}"
        commit = f"commits/{self.spec['adapter_source']}"
        baseline = {
            tag: None,
            release: None,
            commit: {
                "sha": self.spec["adapter_source"],
                "commit": {"tree": {"sha": self.spec["adapter_tree"]}},
            },
        }
        publication.verify_destination(
            self.spec, lambda _, path, **kwargs: baseline[path]
        )
        for route, response in [
            (tag, {"object": {}}),
            (release, {"id": 1, "draft": True}),
            (commit, {"sha": "3" * 40}),
        ]:
            with self.subTest(route=route), self.assertRaises(ValueError):
                state = {**baseline, route: response}
                publication.verify_destination(
                    self.spec, lambda _, path, **kwargs: state[path]
                )
        publication.verify_immutability(
            self.spec, lambda *_args, **_kwargs: {"enabled": True}
        )
        with self.assertRaisesRegex(ValueError, "immutability is disabled"):
            publication.verify_immutability(
                self.spec, lambda *_args, **_kwargs: {"enabled": False}
            )

    def test_substituted_assets_and_mutable_public_metadata_are_refused(self):
        notes = publication.release_notes(self.spec)
        self.assertTrue(
            publication.verify_release(self.release(), self.spec, notes, draft=True)
        )
        for value in [
            {"target_commitish": "b" * 40},
            {"prerelease": False},
            {
                "assets": [
                    {**self.release()["assets"][0], "digest": "sha256:" + "b" * 64}
                ]
            },
            {"assets": [{**self.release()["assets"][0], "name": "unapproved.exe"}]},
            {"assets": [self.release()["assets"][0]] * 2},
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                publication.verify_release(
                    {**self.release(), **value}, self.spec, notes, draft=True
                )
        missing = self.release()
        missing["assets"].pop()
        self.assertFalse(
            publication.verify_release(missing, self.spec, notes, draft=True)
        )
        with self.assertRaises(ValueError):
            publication.verify_release(
                {**self.release(draft=False), "immutable": False},
                self.spec,
                notes,
                draft=False,
            )

    def test_publisher_preflights_then_creates_draft_and_publishes_once(self):
        calls = []
        draft = self.release()
        published = self.release(draft=False)

        def request(spec, path, *, method="GET", body=None, **kwargs):
            calls.append((method, path))
            if path == "immutable-releases":
                self.assertTrue(kwargs.get("admin"))
                return {"enabled": True}
            if path.startswith("git/ref/tags/"):
                return (
                    {"object": {"type": "commit", "sha": self.spec["adapter_source"]}}
                    if ("PATCH", "releases/451") in calls
                    else None
                )
            if path.startswith("releases/tags/"):
                return None
            if path.startswith("commits/"):
                return {
                    "sha": self.spec["adapter_source"],
                    "commit": {"tree": {"sha": self.spec["adapter_tree"]}},
                }
            if path.startswith("releases?"):
                return []
            if method == "POST":
                self.assertEqual(path, "releases")
                self.assertEqual(body["target_commitish"], self.spec["adapter_source"])
                self.assertTrue(body["draft"] and body["prerelease"])
                return deepcopy(draft)
            if method == "PATCH":
                self.assertEqual(body, {"draft": False, "make_latest": "false"})
                return deepcopy(published)
            self.assertEqual(path, "releases/451")
            return deepcopy(draft)

        with (
            patch.object(publication, "api", request),
            patch.object(publication.subprocess, "run") as cli,
        ):
            cli.return_value.returncode = 0
            cli.return_value.stdout = '{"verified": true}'
            result = publication.publish(
                self.spec, publication.release_notes(self.spec)
            )
        self.assertEqual(result["published_release_id"], 451)
        mutations = [entry for entry in calls if entry[0] != "GET"]
        self.assertEqual(mutations, [("POST", "releases"), ("PATCH", "releases/451")])
        cli.assert_called_once()
        self.assertEqual(
            cli.call_args.args[0][:4], ["gh", "release", "verify", self.spec["tag"]]
        )

    def test_disabled_immutability_stops_before_any_release_request(self):
        with patch.object(
            publication, "api", return_value={"enabled": False}
        ) as request:
            with self.assertRaisesRegex(ValueError, "immutability is disabled"):
                publication.publish(self.spec, publication.release_notes(self.spec))
        request.assert_called_once_with(self.spec, "immutable-releases", admin=True)
