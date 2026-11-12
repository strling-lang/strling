# STRling R adapter

STRling 4.0.0 is not publicly published. Public installation commands describe
the proposed separately authorized release. Candidate tests use staged artifacts.
See the [support matrix](../../docs/support-matrix.md) for exact supported scopes.

This package is a thin R projection of the canonical STRling compiler. Registered `.Call` routines perform explicit dynamic loading and bounded byte transport over a caller-selected `strling.c-abi` version 1 library; R functions project versioned requests and canonical results. The package does not implement parsing, semantics, validation, target planning, or emission.

The adapter is a provisional Preview candidate during the Fourth Edition migration. This is not a publication or permanent support-tier promise.

## Requirements

-   R `>= 4.3, < 5.0`
-   `jsonlite >= 1.8.8`
-   a compatible native STRling library chosen by the application

## Use

Pass the authenticated absolute native-library path as the first program argument.
The example requires an installed package and its declared dependencies.

```r
library(strling)

client <- strling_load_native(commandArgs(trailingOnly = TRUE)[[1]])
result <- strling_compile(
  client,
  strling_source_compile_request('semantic strling 1.0; case sensitive; pattern text "hello";')
)

stopifnot(identical(result$outcome, "succeeded"))

builder <- strling_simply_builder_request(list(sl_email("root")), "root")
simply_result <- strling_simply_compile(client, builder)

stopifnot(identical(simply_result$status, "success"))
stopifnot(identical(simply_result$compile_result$outcome, "succeeded"))
strling_close(client)
```

Generated helpers are lexical-shape recipes, not semantic validators. Loading is explicit and fails closed on path, ABI, symbol, encoding, JSON, duplicate-property, size, ownership, and lifecycle violations. No ambient or fallback compiler route exists.

See the [canonical interop contract](../../spec/interop/1.0/README.md) and the [migration record](../../docs/migration/dynamic-language-adapter-migration.md).

## Proposed public installation

After separately authorized publication, the exact proposed coordinate is:

```bash
git clone --branch r-v4.0.0 --single-branch https://github.com/strling-lang/strling.git
```

Install the authenticated subtree with `R CMD INSTALL strling/bindings/r`. The application supplies the exact matching native library; the source package does not discover or download it.
