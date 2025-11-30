#!/bin/bash
set -e

# STRling Perl Binding Setup Script
# This script installs the required CPAN dependencies for the Perl binding.

echo "Setting up STRling Perl binding dependencies..."

# Try cpanm first, fall back to cpan
install_module() {
    local module=$1
    if command -v cpanm &> /dev/null; then
        cpanm --notest "$module" || cpanm --notest --sudo "$module"
    else
        # Fall back to cpan (less friendly but available)
        echo "yes" | cpan "$module" || true
    fi
}

# Install cpanminus if not present and we have network
if ! command -v cpanm &> /dev/null; then
    echo "cpanm not found, attempting to install..."
    if curl -sL --connect-timeout 5 https://cpanmin.us -o /tmp/cpanm_installer 2>/dev/null; then
        perl /tmp/cpanm_installer --sudo App::cpanminus 2>/dev/null || \
        perl /tmp/cpanm_installer App::cpanminus 2>/dev/null || \
        echo "Could not install cpanm, will use cpan instead"
        rm -f /tmp/cpanm_installer
    else
        echo "Network unavailable or cpanmin.us unreachable, will use cpan"
    fi
fi

# Install dependencies from Makefile.PL
echo "Installing Perl dependencies..."
install_module "Moo"
install_module "Type::Tiny"

# Generate Makefile
echo "Generating Makefile..."
perl Makefile.PL

echo "Perl binding setup complete."
