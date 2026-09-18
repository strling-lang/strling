#!/bin/bash
set -e

# STRling Perl Binding Build Script
# The Makefile consumed by make is a generated artifact of Makefile.PL and of
# the active interpreter's Config.pm/config.h. ExtUtils::MakeMaker refuses to
# build when that Makefile is absent, and when it is older than the
# interpreter it regenerates the Makefile and then fails on purpose, asking
# the caller to rerun make. The governed build therefore regenerates the
# Makefile from the tracked Makefile.PL before building, so a clean checkout
# and a changed Perl toolchain both build correctly on the first invocation.

echo "Generating Makefile from Makefile.PL..."
perl Makefile.PL

echo "Building STRling Perl binding..."
make
