"""Hosted workflow contexts and optional immutable operational dispatch are bounded."""

import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def workflow():
    return yaml.load(
        (ROOT / ".github/workflows/public-verification.yml").read_text(),
        Loader=yaml.BaseLoader,
    )


def test_runner_context_is_only_used_after_runner_allocation():
    definition = workflow()
    assert set(definition["on"]) == {"workflow_dispatch"}
    for job in definition["jobs"].values():
        assert "runner." not in str(job.get("env", {}))
        assert job["environment"] == "public-verification"
    steps = definition["jobs"]["verify"]["steps"]
    setup = next(
        s for s in steps if s.get("name") == "Configure isolated verification storage"
    )
    assert len(setup["env"]) == 4
    assert all(
        v.startswith("${{ runner.temp }}/public-") for v in setup["env"].values()
    )
    assert steps.index(setup) < next(i for i, s in enumerate(steps) if "uses" in s)


@pytest.mark.parametrize("newline", ["", "\nINJECTED=bad", "\rINJECTED=bad"])
def test_isolated_storage_export_preserves_paths_and_rejects_injection(
    tmp_path, newline
):
    step = next(
        s
        for s in workflow()["jobs"]["verify"]["steps"]
        if s.get("name") == "Configure isolated verification storage"
    )
    script = step["run"].split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    values = {key: str(tmp_path / "space in path" / key) for key in step["env"]}
    values["CARGO_HOME"] += newline
    output = tmp_path / "github-env"
    env = dict(os.environ, **values, GITHUB_ENV=str(output))
    result = subprocess.run(
        [sys.executable, "-I", "-c", script], env=env, capture_output=True
    )
    if newline:
        assert result.returncode != 0
        assert not output.read_text()
    else:
        assert result.returncode == 0
        assert output.read_text().splitlines() == [
            f"{key}={value}" for key, value in values.items()
        ]


@pytest.mark.parametrize(
    "repository,ref,ref_name,pin,approved_ref,approved_pin,accepted",
    [
        ("strling-lang/strling", "refs/heads/main", "main", "a" * 40, "", "", True),
        (
            "strling-lang/strling",
            "refs/heads/ops",
            "ops",
            "a" * 40,
            "refs/heads/ops",
            "a" * 40,
            True,
        ),
        ("strling-lang/strling", "refs/heads/ops", "ops", "a" * 40, "", "", False),
        (
            "strling-lang/strling",
            "refs/heads/ops",
            "ops",
            "a" * 40,
            "refs/heads/ops",
            "b" * 40,
            False,
        ),
        (
            "strling-lang/strling",
            "refs/heads/other",
            "other",
            "a" * 40,
            "refs/heads/ops",
            "a" * 40,
            False,
        ),
        (
            "untrusted/fork",
            "refs/heads/ops",
            "ops",
            "a" * 40,
            "refs/heads/ops",
            "a" * 40,
            False,
        ),
    ],
)
def test_operational_dispatch_requires_exact_repository_ref_and_workflow(
    repository, ref, ref_name, pin, approved_ref, approved_pin, accepted
):
    values = {
        "github.repository": repository,
        "github.ref_name": ref_name,
        "github.event.repository.default_branch": "main",
        "github.ref": ref,
        "github.workflow_sha": pin,
        "vars.PUBLIC_WORKFLOW_REF": approved_ref,
        "vars.PUBLIC_WORKFLOW_SHA": approved_pin,
    }
    for name, job in workflow()["jobs"].items():
        expression = job["if"].strip()
        if name == "reconcile":
            assert expression.startswith("always() && !cancelled() && ")
            expression = expression.removeprefix("always() && !cancelled() && ")
        for key in sorted(values, key=len, reverse=True):
            expression = expression.replace(key, repr(values[key]))
        assert (
            bool(
                eval(
                    expression.replace("&&", " and ").replace("||", " or "),
                    {"__builtins__": {}},
                    {},
                )
            )
            is accepted
        )
