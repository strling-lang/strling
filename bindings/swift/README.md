# STRling Swift adapter

STRling 4.0.0 is not publicly published. Public installation commands describe
the proposed separately authorized release. Candidate tests use staged artifacts.
See the [support matrix](../../docs/support-matrix.md) for exact supported scopes.

The Swift package is a semantic-free facade over a small C loader target and
the governed `strling.c-abi` v1. A caller supplies an absolute native library
path; the package performs no ambient lookup or download.

Pass the absolute authenticated native-library path as the first program argument.
The program requires that argument; it never searches a developer installation.

```swift
import Foundation
import STRling

let client = try NativeClient(libraryPath: CommandLine.arguments[1])
defer { client.close() }
let request = sourceCompileRequest("semantic strling 1.0; case sensitive; pattern text \"hello\";")
let result = try client.compile(request) as! [String: Any]
precondition(result["outcome"] as? String == "succeeded")
print(result["outcome"]!)
```

`describe`, `compile`, `inspectTargetProfile`, and `simplyCompile` preserve
canonical JSON results. Canonical rejected responses use
`InteropProtocolError`; loading, ABI, lifecycle, size, encoding, and transport
failures use `NativeAdapterError`.

Generated `Essential` helpers create Simply 1.1 `stdlib_helper` steps. Their
guarantee is `lexical_shape`, not semantic validation. Apple, Linux, and Windows
support claims require execution under the governed CP4 toolchain matrix.

## Product compatibility

Fourth Edition packages require the exact 4.0.0 native product identity in
addition to ABI 1 and protocol 1.0.0. Dynamic loaders check the bounded binary
product marker before loading; installed CMake packages check their static
archive during configuration. Unmarked older kernels and mismatched product
versions fail closed. This package check does not authenticate arbitrary local
files; release checksums and signed evidence authenticate distribution bytes.
The compiler semantics and versioned ABI/protocol are unchanged.

## Product release installation

Clone the immutable `swift-v4.0.0` product source tag, verify the checkout's
commit against release provenance, and use `bindings/swift` as the SwiftPM
package path. A consuming project can reference that checked-out package with
`.package(path: "/absolute/checkout/bindings/swift")`. The supported execution
scope is Linux x86_64; the native library is supplied through its explicit
absolute path.

## Proposed public installation

After separately authorized publication, the exact proposed coordinate is:

```bash
git clone --branch swift-v4.0.0 --single-branch https://github.com/strling-lang/strling.git
```

Use `swift build --package-path strling/bindings/swift` for this source route. A consuming SwiftPM project references that authenticated subtree as a local package; the repository root is not a SwiftPM package.
