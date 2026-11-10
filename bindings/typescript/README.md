# STRling TypeScript adapter

This package is the Preview TypeScript host adapter for the canonical STRling
compiler. It sends versioned JSON requests through the governed
`strling.wasm-abi` v1 boundary; it does not contain a parser, validator, target
emitter, or independent standard-library implementation.

## Installation

```bash
npm install @strling-lang/strling@4.0.0
```

Node 22 is the declared runtime. The package is ESM-only. The ratified support
tier remains Preview: historical Windows Node 24 evidence falls outside that
range, and browser harness evidence does not establish general browser support.

## Node use

The Node-only entrypoint loads the exact WebAssembly artifact included in the
package. Loading is explicit and never downloads an artifact or selects a
target from the host environment.

```typescript
import { Compiler } from "@strling-lang/strling";
import { loadBundledWasm } from "@strling-lang/strling/node";

const client = await loadBundledWasm();
const compiler = new Compiler(client);

// Both values are ordinary objects owned and pinned by the application.
const result = compiler.compile(compileRequest, exactTargetProfile);
if (result.outcome === "succeeded") {
    console.log(result.artifact);
}
```

Canonical compile failures are returned as compile-result values. WebAssembly
loading, memory, ABI, and interop-envelope failures use distinct adapter error
types and retain stable interop codes and paths where the protocol supplies
them.

## Browser use

The root entrypoint imports no Node built-ins and performs no implicit fetch.
The application or bundler supplies the packaged `strling_interop.wasm` bytes
or a previously compiled `WebAssembly.Module`:

```typescript
import { instantiateWasm } from "@strling-lang/strling";

const client = await instantiateWasm(wasmBytes);
const description = client.describe();
```

Calls on one client instance are serialized. Independent WebAssembly instances
may execute concurrently.

## Simply requests

The `./simply` entrypoint retains ergonomic constructors while recording only
canonical Simply protocol operations:

```typescript
import { digit, lit, merge } from "@strling-lang/strling/simply";

const pattern = merge(lit("A"), digit(1, 3));
const response = pattern.compile(client, compileProjection, exactTargetProfile);
```

Standard helpers delegate by canonical registry identity. Helpers declared
`lexical_shape` remain lexical-shape helpers and may accept semantically invalid
values. `Pattern.exec`, `Pattern.toRegExp`, and implicit string rendering are
retired because this adapter does not simulate target-engine execution.

## Supported entrypoints

-   `@strling-lang/strling` — browser-safe raw-WASM client and canonical compile
    conveniences
-   `@strling-lang/strling/node` — explicit filesystem loaders for Node
-   `@strling-lang/strling/simply` — canonical Simply request builders
-   `@strling-lang/strling/strling_interop.wasm` — the sealed raw-WASM artifact

Historical `./core` and `./emitters/pcre2` entrypoints are intentionally
removed. Canonical language and target contracts live in the main STRling
repository under `spec/`.

## Fourth Edition loader compatibility

Use `instantiateWasm(bytes)` or `instantiateWasm(precompiledModule)` to create a
client. Direct `new WasmClient(instance)` construction is retired: the factory
checks the exact product metadata before instantiating that same module. ABI 1,
protocol 1.0.0, and the six-export WASM boundary remain unchanged. This intentional
4.0 compatibility change prevents pairing an instance with unrelated metadata.
