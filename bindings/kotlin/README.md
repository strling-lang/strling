# STRling Kotlin adapter

STRling 4.0.0 is not publicly published. Public installation commands describe
the proposed separately authorized release. Candidate tests use staged artifacts.
See the [support matrix](../../docs/support-matrix.md) for exact supported scopes.

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

Pass the absolute authenticated native-library path as the first program argument.
The program requires that argument; it never searches a developer installation.

```kotlin
import com.strling.jvm.NativeClient
import java.nio.file.Path
import strling.Compiler

fun main(args: Array<String>) {
    NativeClient.load(Path.of(args[0]).toAbsolutePath()).use { client ->
        val compiler = Compiler(client)
        val result = compiler.parse("semantic strling 1.0; case sensitive; pattern text \"hello\";") as Map<*, *>
        check(result["outcome"] == "succeeded")
        println(result["outcome"])
    }
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

## Proposed public installation

After separately authorized publication, the exact proposed coordinate is:

```bash
mvn dependency:get -Dartifact=com.strling:strling-kotlin:4.0.0 -DremoteRepositories=https://repo1.maven.org/maven2
```

This proposed command resolves the exact Maven coordinate. Add `implementation("com.strling:strling-kotlin:4.0.0")` to the application dependency block. The application supplies the authenticated native library.
