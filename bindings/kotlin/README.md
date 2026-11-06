# STRling Kotlin adapter

The Kotlin package is an idiomatic thin facade over the same
`com.strling:strling-jvm` bridge used by Java. It contains no independent
parser, compiler, semantic IR, validator, diagnostics, or target emitter.

> **Migration status:** canonical adapter complete. The retired Kotlin-owned
> implementation remains compatibility evidence, not the compiler boundary.

Semantic STRling is the flagship textual language. Regex-compatible text is an
import/compatibility surface, not Semantic STRling.
STRling 4.0 uses one canonical pipeline for Semantic, Simply, and explicit
compatibility requests.

## Build and test

Use JDK 11 or 21 for canonical source builds. After `./strling setup all` has
prepared the governed SDKs and dependency caches, run from the repository root:

```text
python tooling/jvm_adapter_package.py --install-product --skip-tests
./strling build kotlin
./strling test kotlin
```

The adapter targets Java 11 bytecode. Release-package build certification uses
the governed JDK 21 SDK on Windows x86_64; the current
[release policy](../../docs/release-policy.md) defines the exact scope. Runtime
calls require an absolute path to the matching native product. Follow the
[shared bridge instructions](../jvm/README.md) to build it from the authenticated
source revision. Canonical JAR installation preserves strict dependency
verification; plain `mvn install` is not a replacement for that assembly step.
These source-build commands do not publish packages.

## Canonical compile

```kotlin
import com.strling.jvm.NativeClient
import java.nio.file.Path
import strling.Compiler

NativeClient.load(Path.of(args[0]).toAbsolutePath()).use { client ->
    val compiler = Compiler(client)
    println(compiler.parse("literal \"hello\""))
}
```

`Compiler.parse` returns canonical compile data, never a Kotlin-owned AST.
Target artifacts require an exact target-profile reference and the matching
profile document through `SourceCompileOptions`; there is no ambient target.

## Simply and standard helpers

`Simply` records host-neutral Simply 1.1 recipes while retaining Kotlin
defaults and nullability where those are mechanically representable. A
`Pattern` is evaluated only through `Pattern.compile`; runtime-regex execution
and implicit rendering are rejected.

`Essential` is generated from the canonical registry and exposes `dateTime`,
`email`, `ip`, `url`, and `uuid`. The current guarantee is `lexical_shape`, not
semantic validity, so the host adapter deliberately does not strengthen these
helpers with local validation.

See the [Kotlin API reference](docs/api_reference.md), the
[shared JVM bridge](../jvm/README.md), and the
[migration certification](../../docs/migration/jvm-adapter-migration.md).
