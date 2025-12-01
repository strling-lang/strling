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

Initialize the environment for your target language. This handles virtual environments, dependency installation, and build steps automatically.

```bash
# Setup Python environment
./strling setup python

# Setup TypeScript environment
./strling setup typescript

# Setup Rust environment (if applicable)
./strling setup rust
```

### 3. Verification

Verify your setup by running the test suite:

```bash
./strling test python
./strling test typescript
```

---

## Troubleshooting

If you encounter issues, you can clean the environment and start over:

```bash
./strling clean python
./strling setup python
```
