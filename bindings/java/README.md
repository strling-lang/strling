# STRling Java adapter

The Java package is a thin STRling 4.0 facade over the shared
`com.strling:strling-jvm` bridge. It does not contain a parser, compiler,
semantic IR, validator, diagnostic engine, or target emitter.

> **Migration status:** canonical adapter complete. The retired Java-owned
> implementation remains compatibility evidence, not the compiler boundary.

Semantic STRling is the flagship textual language. Regex-compatible text is an
import/compatibility surface, not Semantic STRling.
STRling 4.0 uses one canonical pipeline for Semantic, Simply, and explicit
compatibility requests.

## Build and test

Use JDK 11 or 21 for canonical source builds. After preparing the governed SDKs
and dependency caches with `./strling setup all`, run from the repository root:

```text
python tooling/jvm_adapter_package.py --install-product --skip-tests
./strling build java
./strling test java
```

Both artifacts target Java 11 bytecode. The release-package build scope is
Windows x86_64 with the governed JDK 21 SDK; see the current
[release policy](../../docs/release-policy.md). Runtime calls require an absolute
path to the matching product's `strling.c-abi` v1 library. Build it from the
authenticated source revision using the [shared bridge instructions](../jvm/README.md);
the Maven artifacts do not include native classifiers. Historical adapter
matrices do not expand the current package certification scope. No package
publication is performed by these source-build commands.

## Canonical compile

```java
import com.strling.Compiler;
import com.strling.jvm.NativeClient;
import java.nio.file.Path;

try (NativeClient client = NativeClient.load(Path.of(args[0]).toAbsolutePath())) {
    Compiler compiler = new Compiler(client);
    Object result = compiler.parse("literal \"hello\"");
    System.out.println(result);
}
```

`Compiler.parse` is a compatibility name that returns canonical compile data,
never a Java-owned AST. Target artifacts require both an exact target-profile
reference and the matching profile document through `SourceCompileOptions`.
There is no ambient target selection.

## Simply and standard helpers

`com.strling.simply.Simply` records host-neutral Simply 1.1 recipes. A
`Pattern` is evaluated only by `Pattern.compile(NativeClient, ...)`; `exec()`
and implicit regex rendering are intentionally rejected.

`com.strling.simply.Essential` is generated from the canonical standard-library
registry and exposes `dateTime`, `email`, `ip`, `url`, and `uuid`. These helpers
currently promise `lexical_shape`, not semantic validity. For example, the IP
helper may accept a lexically shaped value whose numeric components are not a
valid IP address.

See the [Java API reference](docs/api_reference.md), the
[shared JVM bridge](../jvm/README.md), and the
[migration certification](../../docs/migration/jvm-adapter-migration.md).
