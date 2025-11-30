#!/bin/bash
set -e

# Install dependencies from rockspec (use --local to avoid permission issues)
luarocks install --local --only-deps strling-scm-1.rockspec

# Install test runner
luarocks install --local busted

# Build/Install the rock locally to ensure paths are correct
luarocks make --local
