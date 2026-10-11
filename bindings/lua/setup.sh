#!/bin/bash
set -e

# STRling Lua Binding Setup Script
# This script installs the required LuaRocks dependencies for the Lua binding.

echo "Setting up STRling Lua binding dependencies..."

# The candidate-preparation phase owns rockspec materialization. Build/setup
# consumes only the existing canonical current-product projection, including
# during certification; STRLING_VERSION must not override its governed source.
if ! ROCKSPEC="$(python3 ../../tooling/lua_rockspec.py check-generated \
    --version-from-source --output-dir . --print-path-only)"; then
    echo "Error: prepare the canonical Lua rockspec before building or freezing a candidate." >&2
    echo "From the repository root: python3 tooling/lua_rockspec.py materialize --version-from-source --output-dir bindings/lua" >&2
    exit 1
fi

# No dependency/build command is allowed before the read-only integrity check.
eval "$(luarocks path --bin)"

# Check if running as root
if [ "$(id -u)" -eq 0 ]; then
    LOCAL_FLAG=""
    echo "Running as root, installing globally..."
else
    LOCAL_FLAG="--local"
    echo "Running as non-root, installing locally..."
fi

# Install dependencies from rockspec
echo "Installing dependencies from rockspec..."
luarocks install $LOCAL_FLAG --only-deps "$ROCKSPEC"

# Install test runner
echo "Installing busted test runner..."
luarocks install $LOCAL_FLAG busted

# Build/Install the rock locally to ensure paths are correct
echo "Building and installing strling rock..."
luarocks make $LOCAL_FLAG "$ROCKSPEC"

echo "Lua binding setup complete."
echo ""
echo "Note: To run tests manually, first set up paths with:"
echo '  eval "$(luarocks path --bin)"'
