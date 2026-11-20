# Build the qualification artifact with the reviewed Windows Rust compiler.
param(
    [Parameter(Mandatory)]
    [string]$TargetDirectory,
    [string]$Toolchain = '1.97.1'
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$requiredRust = 'rustc 1.97.1 (8bab26f4f 2026-07-14)'
if ((rustc "+$Toolchain" --version) -cne $requiredRust) {
    throw "Qualification requires $requiredRust."
}

$repository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).ProviderPath
$cargoHome = $env:CARGO_HOME
if (-not $cargoHome) {
    $cargoHome = Join-Path $env:USERPROFILE '.cargo'
}
$cargoHome = (Resolve-Path -LiteralPath $cargoHome).ProviderPath
$flags = @('-C', 'link-arg=--max-memory=67108864', '-C', 'link-arg=-zstack-size=2097152')
foreach ($source in @($repository, $repository.Replace('\', '/')) | Select-Object -Unique) {
    $flags += "--remap-path-prefix=$source=/strling/source"
}
# Rust uses the last matching prefix. Keep Cargo's map last for a cache inside the workspace.
foreach ($source in @($cargoHome, $cargoHome.Replace('\', '/')) | Select-Object -Unique) {
    $flags += "--remap-path-prefix=$source=/strling/cargo"
}

$previousFlags = $env:CARGO_ENCODED_RUSTFLAGS
try {
    $env:CARGO_ENCODED_RUSTFLAGS = $flags -join [char]31
    cargo "+$Toolchain" build --locked --offline --manifest-path (Join-Path $PSScriptRoot Cargo.toml) --target wasm32-unknown-unknown --target-dir $TargetDirectory --release
} finally {
    $env:CARGO_ENCODED_RUSTFLAGS = $previousFlags
}
