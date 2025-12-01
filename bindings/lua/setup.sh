#!/bin/bash
set -e

# STRling Lua Binding Setup Script
# This script installs the required LuaRocks dependencies for the Lua binding.

echo "Setting up STRling Lua binding dependencies..."

# Ensure luarocks local paths are set up
eval "$(luarocks path --bin)"

# Install dependencies from rockspec (use --local to avoid permission issues)
echo "Installing dependencies from rockspec..."
luarocks install --local --only-deps strling-scm-1.rockspec

# Install test runner
echo "Installing busted test runner..."
luarocks install --local busted

# Build/Install the rock locally to ensure paths are correct
echo "Building and installing strling rock..."
luarocks make --local

echo "Lua binding setup complete."
echo ""
echo "Note: To run tests manually, first set up paths with:"
echo '  eval "$(luarocks path --bin)"'
