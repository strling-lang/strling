# STRling Dart adapter

The Dart package is a semantic-free `dart:ffi` facade for Dart VM/native
runtimes. Web runtimes are not supported. A caller must supply an absolute path
to the governed `strling.c-abi` v1 library.

```dart
final client = NativeClient.load('/absolute/path/to/libstrling_interop.so');
final request = sourceCompileRequest("'hello'");
final result = client.compile(request);
client.close();
```

`describe`, `compile`, `inspectTargetProfile`, and `simplyCompile` preserve
canonical JSON results. Canonical rejected responses use
`InteropProtocolException`; loading, ABI, lifecycle, size, encoding, and
transport failures use `NativeAdapterException`.

Generated Essential helpers create Simply 1.1 `stdlib_helper` steps and retain
their `lexical_shape` guarantee. They do not validate semantic correctness.
Dart owns the `DynamicLibrary` lifetime, so `close` refuses later calls but does
not promise deterministic operating-system unload.

## Product compatibility

Fourth Edition packages require the exact 4.0.0 native product identity in
addition to ABI 1 and protocol 1.0.0. Dynamic loaders check the bounded binary
product marker before loading; installed CMake packages check their static
archive during configuration. Unmarked older kernels and mismatched product
versions fail closed. This package check does not authenticate arbitrary local
files; release checksums and signed evidence authenticate distribution bytes.
The compiler semantics and versioned ABI/protocol are unchanged.
