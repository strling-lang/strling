# Contribution & Documentation Guidelines

[← Back to Developer Hub](index.md)

This document outlines the guidelines for contributing to STRling and writing documentation.

---

## Contribution Guidelines

### The Golden Master Rule

-   **Logic SSOT (Single Source of Truth):** The **TypeScript** binding (`bindings/typescript`) is the reference implementation for all logic. If a behavior is undefined, the TypeScript implementation's behavior is the standard.
-   **Versioning SSOT:** The **Python** binding (`bindings/python/pyproject.toml`) is the source of truth for the project version. Do not manually bump versions in other manifests; the release process propagates the version from Python to all other bindings.

### The "Zero Friction" Promise

-   **Universal Interface:** All development tasks must be executable via the `./strling` CLI wrapper.
-   **No Manual Setup:** A developer should be able to clone the repo and run `./strling test <lang>` without manually installing language-specific toolchains (where reasonable) or configuring complex environments. The `setup` command should handle dependencies.

### Commit Standards

We enforce **Conventional Commits** to automate changelogs and versioning.

-   `feat:` A new feature
-   `fix:` A bug fix
-   `docs:` Documentation only changes
-   `chore:` Changes to the build process or auxiliary tools and libraries such as documentation generation
-   `refactor:` A code change that neither fixes a bug nor adds a feature
-   `test:` Adding missing tests or correcting existing tests

### PR Process

-   **Certification:** All Pull Requests must pass the **Omega Audit** (`audit_omega.py`). This ensures that the directory structure, file naming, and conformance pass rates meet the project's strict standards.
-   **Status:** Look for the `🟢 CERTIFIED` badge in the audit output before requesting a review.

## Documentation Guidelines

### Topology: Hub-and-Spoke

-   **Structure:** `docs/index.md` is the **Hub**. All other documentation files are **Spokes**.
-   **Rule:** Spokes should link back to the Hub, but should generally avoid lateral links to other spokes unless necessary for context. This prevents "spaghetti documentation" and ensures a clear hierarchy.

### Standard Header

Every documentation file must start with the following navigation link to ensure users can always find their way home:

```markdown
[← Back to Developer Hub](index.md)
```

### Voice: "Junior First"

-   **Audience:** Write for a junior developer who is smart but unfamiliar with compiler theory.
-   **Jargon:** Define technical terms (AST, IR, Emitter, Tokenizer) upon their first use in a document.
-   **Tone:** Professional, encouraging, and instructional. Explain _why_ a decision was made, not just _what_ it is.
