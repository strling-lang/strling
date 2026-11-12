# STRling Python adapter

STRling 4.0.0 is not publicly published. Public installation commands describe
the proposed separately authorized release. Candidate tests use staged artifacts.
See the [support matrix](../../docs/support-matrix.md) for exact supported scopes.

This package is the supported Python host adapter for the canonical STRling
compiler. It sends versioned JSON requests through `strling.c-abi` v1 using
`ctypes`; it does not contain an independent parser, validator, target emitter,
or standard-library implementation.

## Installation and runtime

The Supported distribution scope is CPython 3.12 on Windows/Linux x86_64.
Platform wheels embed
the exact native interop library assembled from the governed Rust source. The
adapter never downloads a library, searches `PATH`, selects a semantic target,
or falls back to the historical Python compiler.

```python
from STRling import Compiler, load_native, source_compile_request

client = load_native()
compiler = Compiler(client)

source = 'semantic strling 1.0; case sensitive; pattern text "hello";'
result = compiler.compile(source_compile_request(source))
if result["outcome"] != "succeeded":
    raise RuntimeError(result["diagnostics"])
print(result["outcome"])
```

Source-tree and development use can select one exact library explicitly:

```python
from STRling import load_native

def connect(authenticated_library_path):
    return load_native(authenticated_library_path)
```

Canonical compile failures remain result values. Native loading, ABI, memory,
and interop-envelope failures use distinct adapter exceptions and preserve
stable interop codes and paths where the protocol supplies them.

## Simply requests

The `STRling.simply` namespace retains ergonomic constructors while recording
only canonical Simply protocol operations:

```python
from STRling import simply

pattern = simply.merge(simply.lit("A"), simply.digit(1, 3))
response = pattern.compile(client, compile_projection, exact_target_profile)
if response["status"] != "success" or response["compile_result"]["outcome"] != "succeeded":
    raise RuntimeError(response)
```

Standard helpers delegate by canonical registry identity. Helpers declared
`lexical_shape` remain lexical-shape helpers and may accept semantically invalid
values. `Pattern.exec` and implicit string rendering are retired because this
adapter does not simulate target-engine execution.

The Simply fragment assumes the preceding `client` and application-owned
`compile_projection` and `exact_target_profile` JSON values. Request a target
artifact only with the exact profile and its reference; the adapter never
infers a target. The source factory defaults to `strling.semantic@1.0.0`;
regex-compatible source requires `frontend_id="strling.regex-compat"`.

## Architecture

The host package owns only deterministic request construction, native-library
loading, bounded borrowed-input transfer, same-descriptor response release,
strict UTF-8/JSON projection, exceptions, package mechanics, and ergonomic
Simply recipes. Language semantics, diagnostics, portability, lowering,
serialization, and helper meaning remain in the canonical Rust kernel.

## Product compatibility

Fourth Edition packages require the exact 4.0.0 native product identity in
addition to ABI 1 and protocol 1.0.0. Dynamic loaders check the bounded binary
product marker before loading; installed CMake packages check their static
archive during configuration. Unmarked older kernels and mismatched product
versions fail closed. This package check does not authenticate arbitrary local
files; release checksums and signed evidence authenticate distribution bytes.
The compiler semantics and versioned ABI/protocol are unchanged.

## Proposed public installation

After separately authorized publication, the exact proposed coordinate is:

```bash
python -m pip install STRling==4.0.0
```

Use only the runtime, OS, CPU and native/WASM loading scope declared above and in the support matrix.
