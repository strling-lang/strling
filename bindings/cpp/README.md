# STRling C++ adapter

STRling 4.0.0 is not publicly published. Public installation commands describe
the proposed separately authorized release. Candidate tests use staged artifacts.
See the [support matrix](../../docs/support-matrix.md) for exact supported scopes.

The C++17 package is an idiomatic RAII facade over the governed STRling C/native
boundary. It does not contain a parser, compiler, IR, emitter, target model, or
standard-library regex implementation.

Canonical compile failures remain response values. Native transport status is
available separately through `strling::response::transport_status()`.

## Local build and test

```bash
cmake -S bindings/cpp -B bindings/cpp/build \
  -DSTRLING_CPP_WARNINGS_AS_ERRORS=ON
cmake --build bindings/cpp/build --config Release --parallel
ctest --test-dir bindings/cpp/build -C Release --output-on-failure
```

The build uses only repository-local C, interop, and kernel sources. Cargo is
invoked with the governed interop lockfile; no C++ dependency is downloaded.

## Installed package

```bash
cmake --install bindings/cpp/build --config Release \
  --prefix bindings/cpp/build/install
```

Consumers use:

```cmake
find_package(strling-cpp CONFIG REQUIRED)
target_link_libraries(my_program PRIVATE STRling::cpp)
```

The same prefix contains the required `strling-c` package and native archives.
No publication is performed by these commands.

## Example

```cpp
#include "strling/essential.hpp"
#include "strling/simply.hpp"
#include <iostream>

using namespace strling::simply;

int main() {
    pattern value = merge(start(), literal("hello").as_capture(), end());
    strling::response result = value.compile();
    if (result.transport_status() != STRLING_INTEROP_STATUS_RESPONSE_WRITTEN) return 1;
    std::cout << result.text() << std::endl;
    return 0;
}
```

Essential names select canonical registry helpers. Their current guarantees are
lexical shape only; the C++ facade does not strengthen them into semantic
validators.

The printed Simply adapter response has a construction `status` and, on
success, a nested `compile_result`. Check both `status="success"` and
`compile_result.outcome="succeeded"` before consuming semantic output.

See [the API reference](docs/api_reference.md) and the
[canonical specification](../../spec/README.md).

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
conan install --requires=strling/4.0.0 --build=never
```

Configure only the exact approved public Conan remote and registered host/build profile from the release handoff before this command. No Conan Center availability or alternate ABI/platform is implied. The binary consumer uses `--build=never`.
