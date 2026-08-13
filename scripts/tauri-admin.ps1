param(
    [ValidateSet("dev", "build")]
    [string]$Mode = "dev",
    [switch]$Elevated
)

$ErrorActionPreference = "Stop"
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin -and -not $Elevated) {
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $PSCommandPath,
        "-Mode", $Mode,
        "-Elevated"
    )
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $arguments
    exit 0
}

if (-not $isAdmin) {
    throw "Administrator permission was not granted."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$logDirectory = Join-Path $projectRoot "output"
$logPath = Join-Path $logDirectory "admin-dev.log"
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
Set-Location -LiteralPath $projectRoot
Start-Transcript -LiteralPath $logPath -Force | Out-Null
try {
    & (Join-Path $PSScriptRoot "tauri.ps1") $Mode
    exit $LASTEXITCODE
}
finally {
    Stop-Transcript | Out-Null
}