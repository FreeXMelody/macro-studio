param(
    [ValidateSet("dev", "build")]
    [string]$Mode = "dev"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

$cargoCommand = Get-Command cargo -ErrorAction SilentlyContinue
$cargoPath = if ($cargoCommand) { $cargoCommand.Source } else { $null }

if (-not $cargoPath) {
    $cargoCandidates = @()
    if ($env:CARGO_HOME) {
        $cargoCandidates += Join-Path $env:CARGO_HOME "bin\cargo.exe"
    }
    $cargoCandidates += Join-Path $HOME ".cargo\bin\cargo.exe"
    $cargoPath = $cargoCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

if (-not $cargoPath) {
    throw "Cargo was not found. Install Rust with rustup, then reopen the terminal."
}

$cargoBin = Split-Path -Parent $cargoPath
if (($env:PATH -split ";") -notcontains $cargoBin) {
    $env:PATH = "$cargoBin;$env:PATH"
}

$targetFile = Join-Path $projectRoot ".cargo-target"
if (-not $env:CARGO_TARGET_DIR -and (Test-Path -LiteralPath $targetFile)) {
    $configuredTarget = (Get-Content -LiteralPath $targetFile -Raw).Trim()
    if ($configuredTarget) {
        $env:CARGO_TARGET_DIR = $configuredTarget
    }
}

$tauri = Join-Path $projectRoot "node_modules\.bin\tauri.cmd"
if (-not (Test-Path -LiteralPath $tauri)) {
    throw "Tauri CLI is missing. Run npm install in the project root first."
}

Write-Host "Cargo: $cargoPath"
if ($env:CARGO_TARGET_DIR) {
    Write-Host "Cargo target: $env:CARGO_TARGET_DIR"
}

& $tauri $Mode
exit $LASTEXITCODE
