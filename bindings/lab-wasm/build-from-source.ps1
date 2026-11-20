# Replay a Git source at a fixed Windows build path, retaining the raw Wasm.
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$SourceRevision,
    [Parameter(Mandatory)]
    [string]$Workspace,
    [Parameter(Mandatory)]
    [string]$RegistrySeed
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
$repository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).ProviderPath
$registry = (Resolve-Path -LiteralPath $RegistrySeed).ProviderPath
$workspacePath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Workspace)
$subst = Join-Path $env:SystemRoot 'System32/subst.exe'
$tar = Join-Path $env:SystemRoot 'System32/tar.exe'

if (Test-Path -LiteralPath $workspacePath) {
    throw 'Supply a new replay directory.'
}
if ((Get-PSDrive R -ErrorAction SilentlyContinue) -or (& $subst | Select-String '^R:\\')) {
    throw 'The reproducible builder requires an unassigned R: drive.'
}
if ((git -C $repository rev-parse "$SourceRevision^{commit}") -cne $SourceRevision) {
    throw 'The requested source must be an exact Git commit.'
}

$source = Join-Path $workspacePath 'source'
$cargoHome = Join-Path $workspacePath 'cargo'
$archive = Join-Path $workspacePath 'source.tar'
$null = New-Item -ItemType Directory -Path $source, $cargoHome
git -C $repository archive '--format=tar' "--output=$archive" $SourceRevision
& $tar -xf $archive -C $source

# Seed archives and registry metadata only. Cargo extracts untouched sources
# into the new workspace after the archives have passed the lockfile checks.
$cargoRegistry = Join-Path $cargoHome 'registry'
$null = New-Item -ItemType Directory -Path $cargoRegistry
Copy-Item -LiteralPath (Join-Path $registry 'index') -Destination $cargoRegistry -Recurse
Copy-Item -LiteralPath (Join-Path $registry 'cache') -Destination $cargoRegistry -Recurse
$lockPath = Join-Path $source 'bindings/lab-wasm/Cargo.lock'
$cache = Join-Path $cargoRegistry 'cache'
foreach ($entry in (Get-Content -LiteralPath $lockPath -Raw) -split '(?m)^\[\[package\]\]\r?$') {
    if ($entry -notmatch '(?m)^source = ') { continue }
    if ($entry -notmatch '(?m)^source = "registry\+https://github\.com/rust-lang/crates\.io-index"\r?$' -or
        $entry -notmatch '(?m)^name = "([A-Za-z0-9_-]+)"\r?$') {
        throw 'The adapter lockfile contains an unrecognized registry dependency.'
    }
    $name = $Matches[1]
    if ($entry -notmatch '(?m)^version = "([A-Za-z0-9.+-]+)"\r?$') {
        throw "The adapter lockfile does not identify the version of $name."
    }
    $version = $Matches[1]
    if ($entry -notmatch '(?m)^checksum = "([a-f0-9]{64})"\r?$') {
        throw "The adapter lockfile does not identify the checksum of $name."
    }
    $checksum = $Matches[1]
    $files = @(Get-ChildItem -LiteralPath $cache -File -Recurse -Filter "$name-$version.crate")
    if ($files.Count -eq 0) { throw "The verified registry seed lacks $name $version." }
    foreach ($file in $files) {
        if ((Get-FileHash -LiteralPath $file.FullName).Hash.ToLowerInvariant() -cne $checksum) {
            throw "The registry seed failed the lockfile checksum for $name $version."
        }
    }
}

$overridePattern = '^(RUSTFLAGS|RUSTC|RUSTC_BOOTSTRAP|RUSTC_WRAPPER|RUSTC_WORKSPACE_WRAPPER|CARGO_HOME|CARGO_INCREMENTAL|CARGO_ENCODED_RUSTFLAGS|CARGO_PROFILE_.*|CARGO_BUILD_.*|CARGO_TARGET_WASM32_.*|CARGO_SOURCE_.*|CARGO_REGISTRIES_.*)$'
$saved = @(Get-ChildItem Env: | Where-Object { $_.Name -match $overridePattern })
& $subst R: $workspacePath
try {
    foreach ($entry in $saved) {
        [Environment]::SetEnvironmentVariable($entry.Name, $null, 'Process')
    }
    $env:CARGO_HOME = 'R:\cargo'
    Push-Location 'R:\source'
    try {
        & 'R:\source\bindings\lab-wasm\build-qualified.ps1' -TargetDirectory 'R:\target'
    } finally {
        Pop-Location
    }
} finally {
    [Environment]::SetEnvironmentVariable('CARGO_HOME', $null, 'Process')
    foreach ($entry in $saved) {
        [Environment]::SetEnvironmentVariable($entry.Name, $entry.Value, 'Process')
    }
    & $subst R: /D
}

$artifact = Get-Item -LiteralPath (Join-Path $workspacePath 'target/wasm32-unknown-unknown/release/strling_lab_wasm.wasm')
$rust = @(rustc +1.97.1 --version --verbose)
$sysroot = (rustc +1.97.1 --print sysroot)
$toolchainFiles = @('bin/rustc.exe', 'bin/cargo.exe', 'lib/rustlib/x86_64-pc-windows-msvc/bin/rust-lld.exe')
$toolchainFiles += Get-ChildItem -LiteralPath (Join-Path $sysroot 'bin') -Filter 'rustc_driver-*.dll' -File |
    Sort-Object Name |
    ForEach-Object { 'bin/' + $_.Name }
$toolchainFiles += Get-ChildItem -LiteralPath (Join-Path $sysroot 'lib/rustlib/wasm32-unknown-unknown/lib') -File |
    Sort-Object Name |
    ForEach-Object { 'lib/rustlib/wasm32-unknown-unknown/lib/' + $_.Name }
$toolchain = [ordered]@{}
foreach ($file in $toolchainFiles) {
    $toolchain[$file] = (Get-FileHash -LiteralPath (Join-Path $sysroot $file)).Hash.ToLowerInvariant()
}
$receipt = [ordered]@{
    source_revision = $SourceRevision
    source_tree = (git -C $repository rev-parse "$SourceRevision^{tree}")
    source_archive_sha256 = (Get-FileHash -LiteralPath $archive).Hash.ToLowerInvariant()
    cargo_lock_sha256 = (Get-FileHash -LiteralPath $lockPath).Hash.ToLowerInvariant()
    rust_identity = $rust
    toolchain_files = $toolchain
    target = 'wasm32-unknown-unknown'
    bytes = $artifact.Length
    sha256 = (Get-FileHash -LiteralPath $artifact.FullName).Hash.ToLowerInvariant()
}
$json = $receipt | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText((Join-Path $workspacePath 'build-receipt.json'), ($json + "`n"), [Text.UTF8Encoding]::new($false))
$json
