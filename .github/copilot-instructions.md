# STRling AI Coding Instructions

STRling is a polyglot regex DSL compiler with 17 language bindings. The TypeScript binding is the **Reference Implementation**.

## Architecture: The Pipeline

```
DSL String → Parse → AST → Compile → IR → Emit → Target Regex (PCRE2/JS/Python)
```

Each binding implements the same 3-stage pipeline in `bindings/<lang>/src/`:

-   **Parser** (`core/parser.*`): DSL text → AST nodes
-   **Compiler** (`core/compiler.*`): AST → target-agnostic IR
-   **Emitter** (`emitters/pcre2.*`): IR → regex string

**Iron Law**: Emitters are pure functions with signature `emit(ir, flags) → string`. No side effects.

## Key Files & Directories

| Path                        | Purpose                                                |
| --------------------------- | ------------------------------------------------------ |
| `bindings/typescript/`      | **Reference Implementation** — all features start here |
| `tests/spec/*.json`         | Golden master test fixtures (generated from TS)        |
| `spec/grammar/dsl.ebnf`     | Canonical grammar definition                           |
| `spec/grammar/semantics.md` | Normative semantics for all constructs                 |
| `tooling/audit_omega.py`    | Final certification audit (validates all 17 bindings)  |
| `tooling/sync_versions.py`  | Propagates version from Python SSOT                    |

## Test Fixture Format

Each JSON file in [tests/spec/](../tests/spec/) follows this schema:

```json
{
  "id": "plus_greedy",
  "input_dsl": "a+",
  "input_ast": { "type": "Quantifier", "target": {...}, "min": 1, "max": null },
  "expected_ir": { "ir": "Quant", "child": {...}, "min": 1, "max": "Inf", "mode": "Greedy" },
  "expected_codegen": { "pcre": "a+" }
}
```

Conformance tests: Parse `input_ast` → Compile → Assert IR matches `expected_ir`.

## Developer Workflow Commands

```bash
# Regenerate all spec fixtures from TypeScript
cd bindings/typescript && npm run build:specs

# Run final certification audit across all 17 bindings
python3 tooling/audit_omega.py

# Run binding-specific tests
cd bindings/python && pytest
cd bindings/go && go test ./...
cd bindings/rust && cargo test
cd bindings/typescript && npm test
```

## Coding Conventions

1. **Mirror the Reference**: When implementing a feature, match TypeScript's logic exactly. Check `bindings/typescript/src/STRling/core/compiler.ts` for IR generation patterns.

2. **Simply API Pattern**: The user-facing API uses chainable `Pattern` objects:

    ```typescript
    // bindings/typescript/src/STRling/simply/pattern.ts
    simply.digit().oneOrMore(); // creates Pattern wrapping Quantifier node
    ```

3. **Error Classes**: Use `STRlingParseError` with instructional messages explaining what's wrong AND how to fix it.

4. **No Octal Escapes**: `\0` (null byte) only. All other octal patterns are forbidden per [semantics.md](../spec/grammar/semantics.md).

## Version Management (Critical)

**Single Source of Truth**: `bindings/python/pyproject.toml`

Never manually edit versions in `package.json`, `Cargo.toml`, etc. Use:

```bash
python3 tooling/sync_versions.py --write  # propagates to all bindings
```

## Adding a New Feature

1. **Grammar First**: Update `spec/grammar/dsl.ebnf` and `spec/grammar/semantics.md`
2. **TypeScript Implementation**: Add to `bindings/typescript/src/STRling/`
3. **Generate Specs**: `cd bindings/typescript && npm run build:specs`
4. **Implement in Other Bindings**: Match the TypeScript logic exactly
5. **Verify Conformance**: `python3 tooling/audit_omega.py`

## Debugging Tips

-   **IR Mismatch**: Compare `expected_ir` vs actual using the binding's `compileWithMetadata()` method
-   **Emitter Issues**: Check `_escapeLiteral()` and `_escapeClassChar()` in the PCRE2 emitter
-   **Conformance Failures**: Look at which fixtures fail in `tooling/test_logs/`
