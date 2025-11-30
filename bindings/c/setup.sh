#!/bin/bash
set -e

# STRling C Binding Setup Script
# This script downloads required dependencies for building and testing the C binding.

echo "Setting up STRling C binding dependencies..."

# Create deps directory if it doesn't exist
mkdir -p deps

# Parson commit to use (pinned for reproducibility and security)
# Using commit from 2024 release for stability
PARSON_COMMIT="a0e93b2cdea28aa44e48b7cf8e635131ada3fd86"

# Download parson (public domain JSON parser) if not present
if [ ! -f deps/parson.c ] || [ ! -f deps/parson.h ]; then
    echo "Downloading parson JSON parser (commit: ${PARSON_COMMIT})..."
    curl -sL "https://raw.githubusercontent.com/kgabis/parson/${PARSON_COMMIT}/parson.c" -o deps/parson.c
    curl -sL "https://raw.githubusercontent.com/kgabis/parson/${PARSON_COMMIT}/parson.h" -o deps/parson.h
    echo "Parson downloaded successfully."
else
    echo "Parson already present."
fi

# Install jansson library if not present
if ! pkg-config --exists jansson 2>/dev/null; then
    echo "jansson library not found, attempting to install..."
    
    # Detect OS and install accordingly
    if [ -f /etc/debian_version ] || [ -f /etc/ubuntu_version ] || command -v apt-get &> /dev/null; then
        # Debian/Ubuntu
        sudo apt-get update -qq && sudo apt-get install -y -qq libjansson-dev
    elif [ -f /etc/redhat-release ] || command -v dnf &> /dev/null; then
        # Fedora/RHEL
        sudo dnf install -y jansson-devel
    elif [ -f /etc/arch-release ] || command -v pacman &> /dev/null; then
        # Arch Linux
        sudo pacman -Sy --noconfirm jansson
    elif command -v brew &> /dev/null; then
        # macOS
        brew install jansson
    else
        echo "Warning: Could not auto-install jansson. Please install manually:"
        echo "  Ubuntu/Debian: sudo apt-get install libjansson-dev"
        echo "  macOS: brew install jansson"
        echo "  Fedora: sudo dnf install jansson-devel"
    fi
fi

# Verify jansson is now available
if pkg-config --exists jansson 2>/dev/null; then
    echo "jansson library is available."
else
    echo "Warning: jansson library still not found."
fi

echo "C binding setup complete."
