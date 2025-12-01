---
name: 🏗️ Scaffolded Architecture Task
about: A rigorous, fill-in-the-blank unit of work for agents or junior devs.
title: "Task: [Verb] [Object]"
labels: "task, status: triage, good first issue"
assignees: ""
---

# Task: [Concise Title]

## 🎯 Goal

[One sentence description of the feature or logic required.]

## 📍 Target Vectors

The changes should be applied to the following files:

-   **Logic:** `path/to/source/file.ts`
-   **Tests:** `path/to/test/file.test.ts`

## 🏗️ Implementation Scaffolding

### 1. Test Definition (Copy-Paste)

Add this test case to the test suite **before** writing logic:

```typescript
// Copy this into describe(...) block in path/to/test/file.test.ts
test("feature behavior", () => {
    // TODO: Add specific assertions here
});
```

### 2\. Logic Skeleton (Fill-in-the-Blank)

In `path/to/source/file.ts`, implement the following method:

```typescript
/**
 * [Docstring explaining the intent]
 */
public methodName(input: Type): ReturnType {
    // ---------------------------------------------------
    // [YOUR LOGIC GOES HERE]
    // ---------------------------------------------------

    // Hint: Use simply.exact() or ...
}
```

## ✅ Acceptance Criteria

-   [ ] **Test Passing:** The provided test case passes.
-   [ ] **Logic:** The implementation handles edge case X.
-   [ ] **Audit:** Run `./strling test <lang>` to ensure no regressions.
