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

-   **Mandatory Certification:** All Pull Requests **must** pass the **Omega Audit** (`audit_omega.py`) returning `🟢 CERTIFIED` status. This is a **non-negotiable requirement** for merge approval.
-   **What the Audit Validates:**
    -   Directory structure and file naming conventions
    -   Test conformance pass rates across all bindings
    -   Zero test skips (no skipped or ignored tests)
    -   Zero warnings in build/test output
    -   Semantic verification (duplicate capture groups, invalid ranges)
-   **Status Check:** Look for the `🟢 CERTIFIED` badge in the audit output for **all 17 bindings** before requesting a review.
-   **Regression Policy:** If the audit shows any binding with a non-certified status, the PR must be revised until 100% certification is achieved.

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

## Task Architecture Standards

### The "Fill-in-the-Blank" Imperative

To maximize accessibility for junior contributors, STRling enforces a **Cognitive Offloading** strategy for task definition. We do not ask contributors to "architect" a solution; we ask them to "implement" a logic unit within a pre-defined architecture.

**The Task Architect's Responsibility:**
When creating a task (Issue) for a contributor, you must not simply describe the feature. You must provide the **Scaffolding**:

1.  **Target Vector:** The exact file path(s) where changes must occur.
2.  **The Container:** The class or function signature (e.g., `public uuid(): Pattern`).
3.  **The Logic Gap:** A specific comment block indicating where the contributor's logic goes.
4.  **The Verification:** A pre-written test case they can copy-paste to verify their work.

**Rule:** _A task is only ready for a junior developer if the question is "How do I write this Regex?" and not "Where does this file go?"_

### Tooling Feedback Standards (The Signpost Pattern)

STRling tooling must adhere to **Instructional Error Engineering**. When a high-level tool (like an audit or setup script) fails, it must not simply exit. It must act as a **Signpost** pointing to the specific remedy.

**The Failure Contract:**

1.  **State the Failure:** Clearly identify _what_ failed (e.g., "Golden Master Check Failed").
2.  **Explain the Constraint:** Briefly explain _why_ it matters (e.g., "To prevent logic drift...").
3.  **Direct the Action:** Explicitly print the command the user must run next to debug the issue (e.g., "Run `./strling test python` to see specific errors").

_Example: "Do not dump a stack trace in the audit tool. Redirect the user to the test runner."_
