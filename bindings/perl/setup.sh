#!/bin/bash
set -e

# STRling Perl Binding Setup Script
# This script installs the required CPAN dependencies for the Perl binding.

echo "Setting up STRling Perl binding dependencies..."

# Install cpanminus if not present
if ! command -v cpanm &> /dev/null; then
    echo "Installing cpanminus..."
    curl -L https://cpanmin.us | perl - --sudo App::cpanminus 2>/dev/null || \
    curl -L https://cpanmin.us | perl - App::cpanminus
fi

# Install dependencies from Makefile.PL
echo "Installing Perl dependencies..."
cpanm --installdeps . --notest || cpanm --installdeps . --notest --sudo

# Generate Makefile
echo "Generating Makefile..."
perl Makefile.PL

echo "Perl binding setup complete."
