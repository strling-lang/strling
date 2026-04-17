# Test Environment Setup Guide

[← Back to Developer Hub](index.md)

This guide provides the **Golden Path** for setting up your local development environment. STRling uses a unified CLI tool to manage dependencies and run tests across all bindings.

---

## Prerequisites

Before starting, ensure you have the following installed:

1.  **Python 3.10+** (Required for the CLI and Python binding)
2.  **Node.js 20+** (Required for TypeScript binding)
3.  **Git**

_Note: Specific bindings (Rust, Go, etc.) require their respective toolchains (Cargo, Go) if you intend to work on them._

---

## The Golden Path

### 1. Discovery

Run the root CLI to see available commands and supported bindings:

```bash
./strling list
```

### 2. Setup

Initialize the environment for the whole project or for a single binding. This handles virtual environments, dependency installation, and build steps automatically.

```bash
# Bootstrap every binding end-to-end
./strling bootstrap all

# Or bootstrap a single binding
./strling bootstrap python

# Install dependencies only, without running tests
./strling setup rust
```

### 3. Verification

Verify your setup by running the test suite:

```bash
./strling test all
./strling test python
./strling audit
```

`./strling bootstrap all` is the recommended first-run command on a fresh machine. It will iterate every binding in `toolchain.json`, attempt best-effort prerequisite installation where package-manager metadata is available, and stop only after every binding has reached a pass or fail state.

---

## Troubleshooting

If you encounter issues, you can clean the environment and start over:

```bash
./strling clean all
./strling bootstrap all

# Or target a single binding
./strling clean python
./strling setup python
```
