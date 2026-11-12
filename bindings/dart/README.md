# STRling Dart adapter

STRling 4.0.0 is not publicly published. Public installation commands describe
the proposed separately authorized release. Candidate tests use staged artifacts.
See the [support matrix](../../docs/support-matrix.md) for exact supported scopes.

The Dart package is a semantic-free `dart:ffi` facade for Dart VM/native
runtimes. Web runtimes are not supported. A caller must supply an absolute path
to the governed `strling.c-abi` v1 library.

Pass the absolute authenticated native-library path as the first program argument.
The program requires that argument; it never searches a developer installation.

```dart
import 'package:strling/strling.dart';

void main(List<String> args) {
  final client = NativeClient.load(args[0]);
  try {
    final request = sourceCompileRequest(
      'semantic strling 1.0; case sensitive; pattern text "hello";',
    );
    final result = client.compile(request) as Map;
    if (result['outcome'] != 'succeeded') throw StateError('$result');
    print(result['outcome']);
  } finally {
    client.close();
  }
}
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

## Proposed public installation

After separately authorized publication, the exact proposed coordinate is:

```bash
dart pub add strling:4.0.0
```

Use only the runtime, OS, CPU and native/WASM loading scope declared above and in the support matrix.
