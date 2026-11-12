# Migrating STRling 3.x applications to 4.0

This guide describes the implemented Fourth Edition interfaces and intentional
retirements. STRling 4.0.0 remains prepublication. Installation commands are
proposed public-release commands; no public 4.0.0 installation is claimed.

The historical comparison point is the repository's frozen 3.0.0 compatibility
baseline, `77f6a81e6b0a63cc6052fdadb428c719b16c7c61`. It is implementation and
interface evidence, not a ratified language specification or a promise that
every 3.x implementation quirk was supported. The versioned contracts and
[release policy](release-policy.md) remain authoritative.

## Replace host-owned compilation with the canonical client

Earlier Python code could import its binding-local parser and receive flags and
a Python-owned AST:

```python
# Historical 3.0.0 interface; do not run this against STRling 4.0.
from STRling.core.parser import parse

flags, node = parse("hello")
```

That module and its AST are retired. The historical source defines `parse(src)`
as returning `Tuple[Flags, Node]`; it does not define the current compiler API.
Use a versioned request and a native client instead:

```python
from STRling import Compiler, load_native, source_compile_request

client = load_native()
request = source_compile_request("hello", {"frontend_id": "strling.regex-compat"})
result = Compiler(client).compile(request)
if result["outcome"] != "succeeded":
    raise RuntimeError(result["diagnostics"])
print(result["outcome"])
```

`parse` compatibility conveniences now request canonical compile data; they do
not restore a binding-local AST. Code that depended on local parser, IR, emitter,
validator or compiler-stage internals needs a deliberate rewrite around the
canonical contracts. There is no automatic source-code migration tool for
arbitrary Python, TypeScript or other host programs.

## Choose the source frontend explicitly

For new textual intent, prefer the Semantic program:

```strling
semantic strling 1.0;
case sensitive;

pattern text "hello";
```

The complete program includes the edition selector and case declaration. The
source factory defaults to `strling.semantic@1.0.0`. To preserve regex-shaped
input, explicitly select `strling.regex-compat@1.0.0`, as in the preceding
Python example, or use the CLI's `import` command. Merely renaming a source file
does not select a frontend.

Early unpublished Fourth Edition factories emitted obsolete `semantic_strling`
metadata and coupled the source dialect to `1.0-draft.1`. That was a defect,
not a compatibility guarantee. Corrected defaults use the ratified frontend
identity and dialect; the broader specification identity remains independent.
Explicit obsolete or unknown frontend identities continue to reach canonical
refusal and are not silently mapped to another language. Replace the former
`legacy_regex` option with the actual `strling.regex-compat` identity.

Simply APIs retain idiomatic host shapes while recording canonical construction
operations. Simply 1.1 adds the governed standard-library helper operation;
helper meaning is selected by registry identity in the kernel. A host builder
is not an independent parser or target emitter.

## Bind the exact product kernel

Fourth Edition packages coordinate on product 4.0.0 and require its exact
native/WASM product marker, ABI 1 and interop protocol 1.0.0. Matching the ABI
number alone is insufficient. Unmarked older kernels and mismatched product
libraries are rejected before normal client use. This deliberately tightens
the earlier ABI-only packaging boundary without changing the ABI itself.

Use the sealed wheel, WASM, NuGet or Conan payload where the route provides one.
For an explicitly caller-supplied native mode, provide the absolute path to an
authenticated matching library. Do not copy a developer's search path or assume
that a compatible filename authenticates the bytes. See the
[package guides](support-matrix.md) for exact payload and runtime requirements.

Product, specification, source dialect, ABI, transport, compiler-description and
target-profile versions are separate identities. Do not change protocol or
specification versions to 4.0.0 merely because the package version is 4.0.0.

## Use the verified WASM construction path

Before packaging hardening, the Fourth Edition WASM client accepted direct
construction from an instance. That interface is recorded at H08 closure
`2d8d897504663211d3768517f0be9f0e28d0f11e`; it is distinct from the older 3.x
binding-owned compiler:

```typescript
// Historical pre-hardening interface; unavailable in the current package.
const client = new WasmClient(instance);
```

The constructor is now private and guarded. Use the public factory, which
binds the verified module, product identity and instance:

```typescript
import { instantiateWasm } from "@strling-lang/strling";

export async function connect(wasmBytes: ArrayBuffer) {
    return instantiateWasm(wasmBytes);
}
```

The application supplies the packaged bytes or a supported compiled module.
For Node, `loadBundledWasm()` loads the package's exact artifact explicitly.
The browser-safe root entrypoint does not fetch a binary or import Node built-ins.
No fallback to an older WASM kernel or host-owned compiler is provided.

## Consume results and diagnostics as contracts

Compile failures are ordinary canonical result values with stable diagnostic
codes, categories, locations and severity data. Native loading, malformed JSON,
ABI and interop failures remain separate host errors. Do not infer semantic
success from a successful FFI call, nonempty response buffer or process launch.

Retired `Pattern.exec`, `Pattern.toRegExp` and implicit rendering must not be
used as target-engine execution. Use the artifact's exact engine/profile,
pattern and consumer options in an application-owned runtime. The compiler
does not claim that a PCRE2 artifact executes as Python `re` or ECMAScript.
Lexical-shape standard helpers do not become standards validators through
this migration.

Final candidate preparation also corrected defects in the unpublished 4.0.0
adapters: source helpers now select the registered Semantic frontend by default,
and the .NET and JVM Simply start/end helpers use the canonical input-position
identities. These are corrections to invalid requests, not additional language
features or supported 3.x compatibility aliases. Explicit obsolete frontend
identities still receive the canonical refusal.

## Reconcile packages and support

Use the exact package coordinates and source-tag mappings in the
[support matrix](support-matrix.md) and [release policy](release-policy.md).
The Rust public crate is the same-source curated facade, not a second semantic
kernel package. Go's governed source tag resolves to a canonical pseudo-version;
its leading module major is not the STRling product version. Source-delivered
Swift, C, PHP and R routes require their documented subtree/build procedure;
do not assume that every repository root is a package-manager manifest.

Supported means the exact registered OS, architecture, runtime and consumer
scope. It does not cover all environments of that language. Preview remains
Preview even when staged assembly or a bounded example succeeds. No target
engine or binding support is inferred from another row.

The CLI's `migrate` command converts supported canonical values under its
versioned conversion contract. Exact conversion requires its reconstruction
proof; partial and unsupported conversions remain explicit. It does not restore
removed host APIs, repair arbitrary 3.x programs or authorize public publication.
