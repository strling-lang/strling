# STRling Swift adapter

The Swift package is a semantic-free facade over a small C loader target and
the governed `strling.c-abi` v1. A caller supplies an absolute native library
path; the package performs no ambient lookup or download.

```swift
let client = try NativeClient(libraryPath: "/absolute/path/to/libstrling_interop.so")
let request = sourceCompileRequest("'hello'")
let result = try client.compile(request)
client.close()
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
