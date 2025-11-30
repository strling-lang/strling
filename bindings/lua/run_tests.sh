#!/bin/bash
set -e

# STRling Lua Binding Test Runner
# This script sets up the luarocks environment and runs busted tests.

# Set up luarocks paths
eval "$(luarocks path --bin)"

# Run busted tests
exec busted -v "$@"
