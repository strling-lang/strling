#!/bin/bash
set -e

# STRling Lua Binding Setup Script
# This script installs the required LuaRocks dependencies for the Lua binding.

echo "Setting up STRling Lua binding dependencies..."

# Ensure luarocks local paths are set up
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
luarocks install $LOCAL_FLAG --only-deps strling-scm-1.rockspec

# Install test runner
echo "Installing busted test runner..."
luarocks install $LOCAL_FLAG busted

# Build/Install the rock locally to ensure paths are correct
echo "Building and installing strling rock..."
luarocks make $LOCAL_FLAG

echo "Lua binding setup complete."
echo ""
echo "Note: To run tests manually, first set up paths with:"
echo '  eval "$(luarocks path --bin)"'
