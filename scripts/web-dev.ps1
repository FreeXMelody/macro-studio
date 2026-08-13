param(
    [int]$FrontendPort = 1420,
    [int]$SidecarPort = 8765
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = if ($env:MACRO_STUDIO_PYTHON) { $env:MACRO_STUDIO_PYTHON } else { "python" }

if (Get-NetTCPConnection -State Listen -LocalPort $SidecarPort -ErrorAction SilentlyContinue) {
    throw "端口 $SidecarPort 已被占用，请先关闭旧的 Macro Studio sidecar。"
}
if (Get-NetTCPConnection -State Listen -LocalPort $FrontendPort -ErrorAction SilentlyContinue) {
    throw "端口 $FrontendPort 已被占用，请先关闭旧的前端开发服务器。"
}

$tokenBytes = New-Object byte[] 32
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($tokenBytes)
$rng.Dispose()
$token = [Convert]::ToBase64String($tokenBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
$env:MACRO_STUDIO_SESSION_TOKEN = $token
$env:VITE_API_HOST = "127.0.0.1"
$env:VITE_API_PORT = "$SidecarPort"
$env:VITE_API_TOKEN = $token

$outputDir = Join-Path $projectRoot "output"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$sidecarOut = Join-Path $outputDir "web-dev-sidecar.stdout.log"
$sidecarErr = Join-Path $outputDir "web-dev-sidecar.stderr.log"
$sidecar = Start-Process -FilePath $python -ArgumentList "-m", "backend.main", "--port", "$SidecarPort" -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $sidecarOut -RedirectStandardError $sidecarErr -PassThru

try {
    Write-Host "Macro Studio Web 开发服务"
    Write-Host "前端: http://127.0.0.1:$FrontendPort"
    Write-Host "Sidecar: http://127.0.0.1:$SidecarPort"
    Write-Host "连接令牌: $token"
    Write-Host "浏览器会自动连接，无需手动填写。"
    & npm.cmd --prefix (Join-Path $projectRoot "frontend") run dev -- --host 127.0.0.1 --port $FrontendPort
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    if ($sidecar -and -not $sidecar.HasExited) {
        Stop-Process -Id $sidecar.Id -Force -ErrorAction SilentlyContinue
        $sidecar.WaitForExit()
    }
}