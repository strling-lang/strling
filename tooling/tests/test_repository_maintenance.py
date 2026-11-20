import subprocess
from pathlib import Path

import pytest
import yaml

from tooling.verify_repository_maintenance import check


ROOT = Path(__file__).resolve().parents[2]


def test_maintenance_requires_exact_approved_push_and_rejects_product_change(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    def commit(path):
        (tmp_path / path).write_text("test\n", encoding="utf-8")
        git("add", path)
        git(
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-m",
            path,
        )
        return git("rev-parse", "HEAD")

    git("init")
    baseline = commit("README.md")
    approved = commit("CONTRIBUTING.md")
    context = dict(
        GITHUB_EVENT_NAME="push",
        GITHUB_REF="refs/heads/dev",
        GITHUB_SHA=approved,
        GITHUB_WORKFLOW_SHA=approved,
    )
    assert (
        check(tmp_path, baseline, approved, context)["publication_authorized"] is False
    )
    for key, replacement in (
        ("GITHUB_EVENT_NAME", "workflow_dispatch"),
        ("GITHUB_REF", "refs/heads/main"),
        ("GITHUB_SHA", baseline),
        ("GITHUB_WORKFLOW_SHA", baseline),
    ):
        with pytest.raises(ValueError, match="approved dev push"):
            check(tmp_path, baseline, approved, context | {key: replacement})

    modified = commit("Cargo.toml")
    with pytest.raises(ValueError, match="Cargo.toml"):
        check(
            tmp_path,
            baseline,
            modified,
            context
            | {
                "GITHUB_SHA": modified,
                "GITHUB_WORKFLOW_SHA": modified,
            },
        )


def test_public_workflow_requires_protected_exact_ref_and_digest_for_each_job():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/public-verification.yml").read_text()
    )
    for job in workflow["jobs"].values():
        assert job["environment"] == "public-verification"
        for guard in (
            "github.event_name == 'workflow_dispatch'",
            "vars.PUBLIC_VERIFICATION_ENABLED == 'true'",
            "github.ref == vars.PUBLIC_WORKFLOW_REF",
            "github.sha == vars.PUBLIC_WORKFLOW_SHA",
            "github.workflow_sha == vars.PUBLIC_WORKFLOW_SHA",
        ):
            assert guard in job["if"]
        assert "default_branch" not in job["if"]
        materialize = next(
            step
            for step in job["steps"]
            if step.get("name") == "Authenticate and materialize the protected request"
        )
        assert "hashlib.sha256(raw).hexdigest()" in materialize["run"]
        assert "os.environ['PUBLIC_WORKFLOW_SHA']" in materialize["run"]
