[CmdletBinding()]
param(
    [string]$Python = "$PSScriptRoot/../.venv/Scripts/python.exe",
    [string]$BindHost = '127.0.0.1',
    [int]$Port = 8000,
    [switch]$SkipPreflight,
    [switch]$SeedDemo
)

$ErrorActionPreference = 'Stop'
$backendRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonPath = $Python
if (-not [IO.Path]::IsPathRooted($pythonPath)) {
    $pythonPath = (Resolve-Path -LiteralPath (Join-Path (Get-Location) $pythonPath)).Path
}

try {
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw "Python runtime not found: $pythonPath"
    }
    if (-not $SkipPreflight) {
        & (Join-Path $PSScriptRoot 'pilot-preflight.ps1') -Python $pythonPath -SeedDemo:$SeedDemo
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }

    Push-Location -LiteralPath $backendRoot
    try {
        # Keep a configuration check even when the caller intentionally skips
        # migration/probe after a separately completed preflight.
        & $pythonPath -m scripts.runtime_check
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
        & $pythonPath -m uvicorn app.main:create_app --factory --host $BindHost --port $Port
        $resultCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    exit $resultCode
}
catch {
    Write-Error "Pilot backend did not start: $($_.Exception.Message)"
    exit 2
}
