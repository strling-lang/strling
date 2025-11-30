#!/bin/bash
set -e

# STRling C Binding Setup Script
# This script downloads required dependencies for building and testing the C binding.

echo "Setting up STRling C binding dependencies..."

# Create deps directory if it doesn't exist
mkdir -p deps

# Parson commit to use (pinned for reproducibility and security)
# Commit a0e93b2cdea28aa44e48b7cf8e635131ada3fd86 is from v1.5.3 (2024-01-14)
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

# Install system libraries if not present (jansson for JSON, cmocka for testing)
install_system_deps() {
    local deps_to_install=""
    
    # Check for jansson
    if ! pkg-config --exists jansson 2>/dev/null; then
        deps_to_install="$deps_to_install libjansson-dev"
    fi
    
    # Check for cmocka (test framework)
    if ! pkg-config --exists cmocka 2>/dev/null; then
        deps_to_install="$deps_to_install libcmocka-dev"
    fi
    
    if [ -z "$deps_to_install" ]; then
        echo "All system dependencies are already installed."
        return 0
    fi
    
    echo "Installing missing system dependencies: $deps_to_install"
    
    # Detect OS and install accordingly
    # Note: Package names are controlled by the case statement, so no injection risk
    if [ -f /etc/debian_version ] || [ -f /etc/ubuntu_version ] || command -v apt-get &> /dev/null; then
        # Debian/Ubuntu - use word-splitting intentionally for multiple packages
        # shellcheck disable=SC2086
        sudo apt-get update -qq && sudo apt-get install -y -qq $deps_to_install
    elif [ -f /etc/redhat-release ] || command -v dnf &> /dev/null; then
        # Fedora/RHEL - different package names
        local fedora_deps=""
        for dep in $deps_to_install; do
            case "$dep" in
                libjansson-dev) fedora_deps="$fedora_deps jansson-devel" ;;
                libcmocka-dev) fedora_deps="$fedora_deps libcmocka-devel" ;;
            esac
        done
        # shellcheck disable=SC2086
        sudo dnf install -y $fedora_deps
    elif [ -f /etc/arch-release ] || command -v pacman &> /dev/null; then
        # Arch Linux
        local arch_deps=""
        for dep in $deps_to_install; do
            case "$dep" in
                libjansson-dev) arch_deps="$arch_deps jansson" ;;
                libcmocka-dev) arch_deps="$arch_deps cmocka" ;;
            esac
        done
        # shellcheck disable=SC2086
        sudo pacman -Sy --noconfirm $arch_deps
    elif command -v brew &> /dev/null; then
        # macOS
        local brew_deps=""
        for dep in $deps_to_install; do
            case "$dep" in
                libjansson-dev) brew_deps="$brew_deps jansson" ;;
                libcmocka-dev) brew_deps="$brew_deps cmocka" ;;
            esac
        done
        # shellcheck disable=SC2086
        brew install $brew_deps
    else
        echo "Warning: Could not auto-install dependencies. Please install manually:"
        echo "  Ubuntu/Debian: sudo apt-get install $deps_to_install"
        echo "  macOS: brew install jansson cmocka"
        echo "  Fedora: sudo dnf install jansson-devel libcmocka-devel"
    fi
}

install_system_deps

# Verify dependencies
echo "Verifying dependencies..."
if pkg-config --exists jansson 2>/dev/null; then
    echo "  ✓ jansson library is available."
else
    echo "  ✗ jansson library not found."
fi

if pkg-config --exists cmocka 2>/dev/null; then
    echo "  ✓ cmocka library is available."
else
    echo "  ✗ cmocka library not found."
fi

echo "C binding setup complete."
