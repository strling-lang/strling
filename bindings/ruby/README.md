# STRling Ruby adapter

STRling 4.0.0 is not publicly published. Public installation commands describe
the proposed separately authorized release. Candidate tests use staged artifacts.
See the [support matrix](../../docs/support-matrix.md) for exact supported scopes.

This package is a thin Ruby projection of the canonical STRling compiler. It does not contain a parser, semantic model, validator, target planner, or regex emitter. The caller supplies an absolute path to a `strling.c-abi` version 1 library; Ruby's standard `Fiddle` interface carries strict JSON requests and canonical results across that boundary.

The adapter is a provisional Preview candidate during the Fourth Edition migration. This is not a publication or permanent support-tier promise.

## Requirements

-   Ruby `>= 3.0, < 4.0`
-   a compatible native STRling library chosen by the application

## Use

Pass the authenticated absolute native-library path as the first program argument.
The example requires an installed package and its declared dependencies.

```ruby
require 'strling'

client = Strling.load_native(ARGV.fetch(0))
result = client.compile(Strling.source_compile_request('semantic strling 1.0; case sensitive; pattern text "hello";'))

raise 'canonical compile failed' unless result['outcome'] == 'succeeded'

step = Strling.email('root')
builder = Strling.simply_builder_request([step], 'root')
simply_result = client.simply_compile(builder)

raise 'Simply compile failed' unless simply_result['status'] == 'success' &&
  simply_result['compile_result']['outcome'] == 'succeeded'
client.close
```

The five generated standard-library helpers are lexical-shape recipes. They do not claim that accepted text is semantically valid.

Loading is explicit and fails closed: relative or missing paths, ABI mismatch, missing symbols, invalid UTF-8/JSON, duplicate JSON properties, oversized messages, release failures, and use after close are errors. The package never searches ambient library names and has no subprocess, socket, download, or local-compiler fallback.

See the [canonical interop contract](../../spec/interop/1.0/README.md) and the [migration record](../../docs/migration/dynamic-language-adapter-migration.md).

## Proposed public installation

After separately authorized publication, the exact proposed coordinate is:

```bash
gem install strling --version 4.0.0
```

Use only the runtime, OS, CPU and native/WASM loading scope declared above and in the support matrix.
