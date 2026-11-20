# Build the qualification artifact with the reviewed Windows Rust compiler.
param(
    [Parameter(Mandatory)]
    [string]$TargetDirectory,
    [string]$Toolchain = '1.97.1'
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$requiredRust = 'rustc 1.97.1 (8bab26f4f 2026-07-14)'
$compilerCommit = '8bab26f4f68e0e26f0bb7960be334d5b520ea452'
if ((rustc "+$Toolchain" --version) -cne $requiredRust) {
    throw "Qualification requires $requiredRust."
}

$repository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).ProviderPath
$cargoHome = $env:CARGO_HOME
if (-not $cargoHome) {
    $cargoHome = Join-Path $env:USERPROFILE '.cargo'
}
$cargoHome = (Resolve-Path -LiteralPath $cargoHome).ProviderPath
$sysroot = (Resolve-Path -LiteralPath (rustc "+$Toolchain" --print sysroot)).ProviderPath
$rustLibrary = Join-Path $sysroot 'lib/rustlib/src/rust/library'
$flags = @('-C', 'link-arg=--max-memory=67108864', '-C', 'link-arg=-zstack-size=2097152')
$remappings = @(
    @{ location = $repository; logicalPath = '/strling/source' }
    @{ location = $cargoHome; logicalPath = '/strling/cargo' }
    @{ location = $sysroot; logicalPath = '/strling/rust-toolchain' }
    @{ location = $rustLibrary; logicalPath = "/rustc/$compilerCommit/library/" }
)
# Rust uses the last matching prefix. Keep more specific paths last.
foreach ($mapping in $remappings | Sort-Object { $_.location.Length }) {
    $location = $mapping.location
    $sources = @($location, $location.Replace('\', '/'))
    if ($location -match '^[A-Za-z]:\\') {
        $sources += "\\?\$location"
    }
    foreach ($source in $sources | Select-Object -Unique) {
        $flags += "--remap-path-prefix=$source=$($mapping.logicalPath)"
    }
}

$previousFlags = $env:CARGO_ENCODED_RUSTFLAGS
try {
    $env:CARGO_ENCODED_RUSTFLAGS = $flags -join [char]31
    cargo "+$Toolchain" build --locked --offline --manifest-path (Join-Path $PSScriptRoot Cargo.toml) --target wasm32-unknown-unknown --target-dir $TargetDirectory --release
} finally {
    $env:CARGO_ENCODED_RUSTFLAGS = $previousFlags
}
