# STRling Go adapter

STRling 4.0.0 is not publicly published. Public installation commands describe
the proposed separately authorized release. Candidate tests use staged artifacts.
See the [support matrix](../../docs/support-matrix.md) for exact supported scopes.

The Go module is a semantic-free facade over the governed `strling.c-abi` v1.
It requires a caller-supplied absolute path to the native library and cgo for
execution. `CGO_ENABLED=0` builds fail closed with `ErrCgoUnavailable`.

Pass the absolute authenticated native-library path as the first program argument.
The program requires that argument; it never searches a developer installation.

```go
package main

import (
    "fmt"
    "os"
    strling "github.com/strling-lang/strling/bindings/go"
)

func main() {
    client, err := strling.LoadNative(os.Args[1])
    if err != nil { panic(err) }
    defer client.Close()
    request := strling.SourceCompileRequest("semantic strling 1.0; case sensitive; pattern text \"hello\";", nil)
    raw, err := client.Compile(request, nil)
    if err != nil { panic(err) }
    result, ok := raw.(map[string]any)
    if !ok { panic("invalid canonical result") }
    if result["outcome"] != "succeeded" { panic(result) }
    fmt.Println(result["outcome"])
}
```

`Describe`, `Compile`, `InspectTargetProfile`, and `SimplyCompile` preserve the
canonical JSON result. Canonical rejected responses become `ProtocolError`;
loading, ABI, lifecycle, size, encoding, and transport failures remain
`NativeError` values.

The generated Essential helpers create Simply 1.1 `stdlib_helper` steps. They
retain the registry's `lexical_shape` guarantee and do not validate semantic
correctness. No ambient library probing, network download, subprocess route,
socket route, package-local parser, target selection, or regex emitter exists.

## Product compatibility

Fourth Edition packages require the exact 4.0.0 native product identity in
addition to ABI 1 and protocol 1.0.0. Dynamic loaders check the bounded binary
product marker before loading; installed CMake packages check their static
archive during configuration. Unmarked older kernels and mismatched product
versions fail closed. This package check does not authenticate arbitrary local
files; release checksums and signed evidence authenticate distribution bytes.
The compiler semantics and versioned ABI/protocol are unchanged.

## Product release installation

Install the immutable product source tag explicitly:

```sh
go get github.com/strling-lang/strling/bindings/go@go-v4.0.0
```

Go records a canonical pseudo-version for this non-semantic-version tag. The
product release remains STRling 4.0.0, mapped to the exact certified source
commit by `go-v4.0.0`. The module path remains unchanged. Verification compares
the resolved Git commit with release provenance; it does not infer product
identity from the pseudo-version's leading module major number.
