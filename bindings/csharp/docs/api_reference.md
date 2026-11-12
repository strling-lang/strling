# C# API reference

[Package guide](../README.md) | [Canonical protocol](../../../spec/contracts/1.0/PROTOCOL.md) | [Support matrix](../../../docs/support-matrix.md)

The C# binding is a **Supported** thin adapter over the canonical Rust compiler.
It owns host projection and native transport, not parsing, semantic analysis,
target planning or emission. See the package guide for a complete example.
STRling 4.0.0 is not publicly published; staged-package evidence is distinct
from future public installation.

## Native client and ownership

`Strling.Native.NativeClient.Load(absolutePath)` returns a reentrant, disposable client. Dispose it after outstanding calls complete.

`Describe()`, `Compile(request, targetProfile = null)`, `InspectTargetProfile(profile)` and `SimplyCompile(builderRequest, targetProfile = null)` return canonical JSON values.

Use an authenticated matching 4.0.0 native payload with ABI 1 and protocol 1.0.0.
An absolute filename is not authentication. The exact OS, architecture and
runtime scope is governed by the support matrix; a successful local build
does not extend it. Native load, malformed-envelope, ABI, ownership and
closed-client errors remain distinct from normal canonical compile failures.

## Requests and results

`new Strling.Compiler(client)` exposes `Compile`, `Check`, `Parse`, `ParseToArtifact`, `Describe` and `InspectTargetProfile`. `Compiler.SourceCompileRequest` constructs source metadata; `SourceCompileOptions` controls routing. `Parse` returns a canonical result, not a local AST.

Source factories default to `strling.semantic@1.0.0` and
`text/x-strling-semantic`. A complete Semantic program needs its edition and
case declarations. For regex-compatible input select
`strling.regex-compat@1.0.0` explicitly. The broader specification version is
independent of the frontend dialect. Unknown frontend identities are refused.

Check the canonical `outcome` and structured diagnostics before consuming
semantic output or a target artifact. A successful FFI transport is insufficient.
Target-aware compilation requires the exact caller-owned target profile and
its reference; no profile is inferred from the host runtime or downloaded.

## Simply and retired interfaces

`Strling.Simply.S` records construction graphs; generated `Essential` methods select kernel helper identities.

Lexical-shape helper acceptance is not semantic validation of an email,
identifier or other real-world value. The adapter neither executes target
regexes nor strengthens kernel guarantees.

The former binding-local AST, flags/directive parser, compiler stages and
emitters are retired. Their old API-reference examples are not 4.0 APIs.
Use canonical requests and Simply construction instead; the
[migration guide](../../../docs/migration-guide.md) explains the replacement
and distinguishes historical behavior from current guarantees.
