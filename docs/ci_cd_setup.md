# CI/CD Pipeline Setup Guide

[← Back to Developer Hub](index.md)

## Overview

The STRling project uses an automated CI/CD pipeline defined in `.github/workflows/ci.yml` that handles both continuous integration (testing) and continuous deployment (publishing to PyPI and NPM).

## Pipeline Architecture

### CI Jobs (Continuous Integration)

These jobs run on every push and pull request to `main`, `dev`, and `feature/**` branches:

1. **`test-matrix`**: The core validation engine.
    - **Strategy:** Uses a GitHub Actions Matrix to dynamically spawn runners for all 17 supported languages (Python, TypeScript, Rust, Go, etc.).
    - **Workflow:**
        1. **Universal Setup:** Prepares the environment.
        2. **Install Dependencies:** Runs `./strling setup <lang>`.
        3. **Compile:** Runs `./strling build <lang>` (if applicable).
        4. **Execute Tests:** Runs `./strling test <lang>`.
    - **Efficiency:** Runs in parallel to ensure rapid feedback.

### Certification (The Omega Audit)

Before any deployment can occur, the codebase must pass the **Omega Audit**.

-   **Job:** `audit-omega`
-   **Purpose:** Verifies structural integrity, file naming conventions, and conformance pass rates.
-   **Requirement:** The audit must return `🟢 CERTIFIED`. If the audit fails, the pipeline halts, preventing deployment of non-compliant code.

### CD Jobs (Continuous Deployment)

These jobs run **only** when:

-   The trigger is a `push` to the `main` branch (e.g., a merged PR)
-   Both `test-python` AND `test-javascript` jobs have passed successfully

1. **`deploy-python`**: Publishes the Python package to PyPI

    - Builds the package using `python -m build`
    - Publishes using `twine upload`
    - Requires: `PYPI_API_TOKEN` secret

2. **`deploy-javascript`**: Publishes the JavaScript package to NPM
    - Builds if necessary (TypeScript compilation)
    - Publishes using `npm publish`
    - Requires: `NPM_TOKEN` secret

## Required GitHub Secrets

Before the deployment jobs can work, you must add these secrets to your repository:

### 1. PYPI_API_TOKEN

**How to create:**

1. Log in to your PyPI account at https://pypi.org
2. Go to Account Settings > API tokens
3. Click "Add API token"
4. Set scope to "Entire account" or limit to the "STRling" project
5. Copy the generated token (starts with `pypi-`)

**How to add to GitHub:**

1. Go to your repository on GitHub
2. Navigate to **Settings** > **Secrets and variables** > **Actions**
3. Click **New repository secret**
4. Name: `PYPI_API_TOKEN`
5. Value: Paste your PyPI token
6. Click **Add secret**

### 2. NPM_TOKEN

**How to create:**

1. Log in to your NPM account at https://www.npmjs.com
2. Go to Account Settings > Access Tokens
3. Click "Generate New Token"
4. Choose "Automation" type (for CI/CD)
5. Set appropriate permissions (publish access needed)
6. Copy the generated token

**How to add to GitHub:**

1. Go to your repository on GitHub
2. Navigate to **Settings** > **Secrets and variables** > **Actions**
3. Click **New repository secret**
4. Name: `NPM_TOKEN`
5. Value: Paste your NPM token
6. Click **Add secret**

## Workflow Triggers

The pipeline is triggered by:

### Push Events

-   **Branches:** `main`, `dev`, `feature/**`
-   **Path filters:** Only runs when these paths change:
    -   `bindings/**`
    -   `spec/**`
    -   `tests/**`
    -   `.github/workflows/**`

### Pull Request Events

-   Same path filters as push events
-   Runs CI jobs only (no deployment)

## Branching Strategy

This workflow enforces the following branching model:

1. **`feature/**` branches\*\*: Development work happens here

    - CI runs on every push
    - No deployment occurs

2. **`dev` branch**: Integration and pre-release testing

    - CI runs on every push
    - No deployment occurs

3. **`main` branch**: Production-ready code
    - CI runs on every push
    - **Deployment occurs automatically** after successful tests
    - Only merge to `main` when ready to publish a new version

## Testing the Pipeline

### Test CI Only

To test the CI jobs without triggering deployment:

1. Push to a `feature/*` or `dev` branch
2. Or create a pull request to any branch

### Test Full CI/CD

To test the complete pipeline including deployment:

1. Ensure secrets are configured
2. Merge a PR to `main`
3. Monitor the workflow run in the Actions tab

## Deployment Checklist

Before merging to `main` (which triggers deployment):

-   [ ] All tests pass locally
-   [ ] Version number updated in:
    -   [ ] `bindings/python/pyproject.toml`
    -   [ ] `bindings/javascript/package.json`
-   [ ] Changelog updated (if applicable)
-   [ ] Documentation updated
-   [ ] `PYPI_API_TOKEN` secret is configured
-   [ ] `NPM_TOKEN` secret is configured

## Troubleshooting

### Deployment Fails: "Invalid credentials"

-   **Python:** Verify `PYPI_API_TOKEN` is set correctly and has upload permissions
-   **JavaScript:** Verify `NPM_TOKEN` is set correctly and has publish permissions

### Tests Pass Locally But Fail in CI

-   Check Python version (CI uses 3.12)
-   Check Node.js version (CI uses 20)
-   Ensure all dependencies are listed in requirements.txt / package.json

### Deployment Skipped

-   Verify the push was to the `main` branch (not a PR)
-   Ensure both test jobs passed
-   Check the workflow logs for the `if` condition evaluation

### Version Already Published

-   PyPI and NPM don't allow re-publishing the same version
-   Update version numbers before merging to `main`

## Version Management

Remember to increment versions before merging to `main`:

**Python** (`bindings/python/pyproject.toml`):

```toml
[project]
version = "3.0.0a1"  # Update this
```

**JavaScript** (`bindings/javascript/package.json`):

```json
{
    "version": "3.0.0-alpha" // Update this
}
```

## Monitoring

Monitor workflow runs:

1. Go to the **Actions** tab in your GitHub repository
2. Click on "STRling CI/CD Pipeline"
3. View recent runs and their status
4. Click on individual runs to see detailed logs for each job

## Security Best Practices

-   ✅ Never commit secrets to the repository
-   ✅ Use GitHub Secrets for sensitive tokens
-   ✅ Regularly rotate API tokens
-   ✅ Use scoped tokens (limit to specific packages when possible)
-   ✅ Review published packages after deployment
