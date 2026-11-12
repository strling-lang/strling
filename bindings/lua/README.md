# STRling Lua adapter

STRling 4.0.0 is not publicly published. Public installation commands describe
the proposed separately authorized release. Candidate tests use staged artifacts.
See the [support matrix](../../docs/support-matrix.md) for exact supported scopes.

This rock is a thin Lua projection of the canonical STRling compiler. A minimal C module performs dynamic loading and bounded byte transport over a caller-selected `strling.c-abi` version 1 library; the Lua facade projects canonical requests and results. Neither layer implements STRling semantics.

The adapter is a provisional Preview candidate during the Fourth Edition migration. This is not a publication or permanent support-tier promise.

> **Migration status:** canonical native adapter implemented and locally
> certified by P17-T07. The retired Lua implementation remains
> compatibility evidence, not the compiler boundary.

Semantic STRling is the flagship textual language. Regex-compatible text is an
import/compatibility surface, not Semantic STRling.
STRling 4.0 uses one canonical pipeline for Semantic, Simply, and explicit
compatibility requests.

## Requirements

-   Lua `>= 5.1, < 5.5`
-   `lua-cjson >= 2.1, < 3.0`
-   a C toolchain compatible with the selected Lua ABI
-   a compatible native STRling library chosen by the application

## Prepare and build

Before freezing a certification candidate, materialize the ordinary disposable
rockspec through its registered canonical generator:

```text
python3 tooling/lua_rockspec.py materialize --version-from-source --output-dir bindings/lua
```

Then run `./setup.sh` from this directory. Setup checks the existing closed
numeric rockspec set against the current product version and template before
any LuaRocks action. Missing, stale, or extra outputs fail with preparation
guidance; setup never generates or deletes a rockspec. `STRLING_VERSION` cannot
override the governed product version. Review obsolete numeric projections
explicitly rather than deleting them as an automatic build side effect.

## Use

Pass the authenticated absolute native-library path as the first program argument.
The example requires an installed package and its declared dependencies.

```lua
local strling = require("strling")

local client = strling.load_native(assert(arg[1], "pass the authenticated absolute native path"))
local result = client:compile(strling.source_compile_request('semantic strling 1.0; case sensitive; pattern text "hello";'))

assert(result.outcome == "succeeded")

local builder = strling.simply_builder_request({ strling.email("root") }, "root")
local simply_result = client:simply_compile(builder)

assert(simply_result.status == "success")
assert(simply_result.compile_result.outcome == "succeeded")
client:close()
```

Generated helpers are lexical-shape recipes, not semantic validators. The adapter fails closed on path, ABI, symbol, UTF-8/JSON, duplicate-property, size, ownership, and lifecycle violations. There is no ambient loading, download, subprocess, socket, or local compiler.

See the [canonical interop contract](../../spec/interop/1.0/README.md) and the [migration record](../../docs/migration/dynamic-language-adapter-migration.md).

## Proposed public installation

After separately authorized publication, the exact proposed coordinate is:

```bash
luarocks install strling 4.0.0-1
```

The exact approved LuaRocks owner and immutable rock revision must be reconciled in the protected publication handoff. Dependencies and runtime observations remain Preview.
