#!/bin/bash
set -e

# STRling C Binding Setup Script
# This script downloads required dependencies for building and testing the C binding.

echo "Setting up STRling C binding dependencies..."

# Create deps directory if it doesn't exist
mkdir -p deps

# Download parson (public domain JSON parser) if not present
if [ ! -f deps/parson.c ] || [ ! -f deps/parson.h ]; then
    echo "Downloading parson JSON parser..."
    curl -sL https://raw.githubusercontent.com/kgabis/parson/master/parson.c -o deps/parson.c
    curl -sL https://raw.githubusercontent.com/kgabis/parson/master/parson.h -o deps/parson.h
    echo "Parson downloaded successfully."
else
    echo "Parson already present."
fi

# Check for jansson library (required for main strling.c)
if ! pkg-config --exists jansson 2>/dev/null; then
    echo "Warning: jansson library not found."
    echo "On Ubuntu/Debian: sudo apt-get install libjansson-dev"
    echo "On macOS: brew install jansson"
    echo "On Fedora: sudo dnf install jansson-devel"
fi

echo "C binding setup complete."
