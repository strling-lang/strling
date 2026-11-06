# STRling C++ adapter

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

using namespace strling::simply;

int main() {
    pattern value = merge(start(), literal("hello").as_capture(), end());
    strling::response result = value.compile();
    return result.owns_bytes() ? 0 : 1;
}
```

Essential names select canonical registry helpers. Their current guarantees are
lexical shape only; the C++ facade does not strengthen them into semantic
validators.

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
