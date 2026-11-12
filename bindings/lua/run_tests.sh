#!/bin/bash
set -e

# STRling Lua Binding Test Runner
# This script sets up the luarocks environment and runs busted tests.

# Set up luarocks paths
eval "$(luarocks path --bin)"

# Dependencies use the prepared LuaRocks environment; product code comes from
# this checkout rather than a previously installed STRling rock.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec busted --helper "${SCRIPT_DIR}/spec/source_loader.lua" -v "$@"
