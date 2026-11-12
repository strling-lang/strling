# Getting started with STRling 4.0

STRling compiles pattern intent into a target-specific artifact. It does not
execute a regex engine for your application. Use Semantic STRling for textual
authoring, Simply for programmatic construction, and the regex frontend for
explicit compatibility imports.

STRling 4.0.0 is not yet publicly published. Public installation commands in
this guide and the binding guides are proposed release commands. Candidate
validation uses independently built staged packages, not public 4.0.0 downloads.
Check the [support matrix](support-matrix.md) before selecting an operating
system, architecture, runtime, binding or target engine.

## Write a complete Semantic program

Save this as `hello.strl`:

```strling
semantic strling 1.0;
case sensitive;

pattern text "hello";
```

The edition and case declarations are required. A regex-shaped fragment is not
automatically interpreted as Semantic STRling. The source frontend, its dialect
version and the broader specification version are distinct identities.

## Use the source-checkout CLI

The repository CLI uses the canonical Rust kernel and the governed toolchains
in `toolchain.json`. These commands run from the repository root:

```bash
./strling compile --input hello.strl --output semantic --format json
./strling target list --format json
./strling compile --input hello.strl --output target_artifact \
  --target-profile spec/targets/profiles/pcre2-10.43.json --format json
```

Check the returned `outcome` and diagnostics before using an artifact. The
artifact identifies its exact target profile and consumer options. A successful
compile does not establish that a different engine or version will behave the
same way. The target runtime executes the emitted pattern under those options;
it is not selected from the host language.

To import regex-compatible source instead, save `hello` as `hello.regex` and
select the import frontend explicitly:

```bash
./strling import --input hello.regex --output semantic --format json
```

`compile` defaults to Semantic STRling; `import` selects the regex-compatible
frontend. Neither command infers a target from the filename or host runtime.

## Use a packaged Python client

After a separately authorized public release, the proposed command is:

```bash
python -m pip install "STRling==4.0.0"
```

The Supported package scope is CPython 3.12 on the exact registered Windows and
Linux x86_64 environments. The wheel carries its matching native payload.
The following complete example requests canonical semantic output:

```python
from STRling import Compiler, load_native, source_compile_request

source = 'semantic strling 1.0; case sensitive; pattern text "hello";'
client = load_native()
result = Compiler(client).compile(source_compile_request(source))
if result["outcome"] != "succeeded":
    raise RuntimeError(result["diagnostics"])
print(result["outcome"])
```

Requesting a target artifact additionally requires the exact target profile and
its request reference. Applications own and pin those JSON values; the Python
adapter does not infer or download them. See the
[Python API reference](../bindings/python/docs/api_reference.md).

## Use Simply or another host

Simply builders record a versioned construction request. Compilation still
crosses the same canonical compiler boundary; builders do not emit regex as
their semantic implementation. The [architecture guide](architecture.md)
explains this boundary, and each binding's package guide documents its concrete
API and native/WASM loading contract.

Hosts with caller-supplied native loading need one absolute path to the correct
authenticated product library. A development path in an example is a parameter,
not a package dependency or a search instruction. Obtain the payload through
the certified distribution handoff; do not inherit a developer's library path.
The product marker, ABI and protocol checks reject incompatible kernels but do
not authenticate arbitrary local files. Distribution signatures and checksums
provide that authentication.

## Handle failures deliberately

A well-formed compile may return `outcome="failed"` with structured diagnostics.
Unsupported frontends, dialects, target capabilities and incomplete portability
evidence are refusals, not permission to switch engines or fall back to a local
compiler. Loading, ABI and transport failures use the host adapter's error type.

Structural safety diagnostics and bounded compiler operations are not a blanket
linear-time or ReDoS guarantee for every generated expression and runtime input.
Read the profile, diagnostics and helper guarantee vocabulary. In particular,
`lexical_shape` helpers are not standards-complete semantic validators.

For an existing application, use the [3.x-to-4.0 migration guide](migration-guide.md).
