[CmdletBinding()]
param(
    [string]$Python = "$PSScriptRoot/../.venv/Scripts/python.exe",
    [switch]$SkipMigration,
    [switch]$SeedDemo,
    [switch]$SkipDbProbe
)

$ErrorActionPreference = 'Stop'
$backendRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonPath = $Python
if (-not [IO.Path]::IsPathRooted($pythonPath)) {
    $pythonPath = (Resolve-Path -LiteralPath (Join-Path (Get-Location) $pythonPath)).Path
}

function Invoke-PilotPython {
    param([string[]]$Arguments)
    & $pythonPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE."
    }
}

$locationPushed = $false
try {
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw "Python runtime not found: $pythonPath"
    }
    Push-Location -LiteralPath $backendRoot
    $locationPushed = $true

    # Settings reads backend/.env plus process variables, validates the secret,
    # TLS policy and CORS, and emits only a redacted summary.
    Invoke-PilotPython @('-m', 'scripts.runtime_check')

    if (-not $SkipMigration) {
        Invoke-PilotPython @('-m', 'scripts.migrate', 'upgrade', 'head')
    }
    if ($SeedDemo) {
        Invoke-PilotPython @('-m', 'scripts.seed')
    }
    if (-not $SkipDbProbe) {
        Invoke-PilotPython @('-m', 'scripts.db_probe', '--expected-revision', '0015')
    }
    Write-Host 'Pilot preflight PASS: configuration, migration and schema readiness checks completed.'
}
catch {
    Write-Error "Pilot preflight failed: $($_.Exception.Message)"
    exit 2
}
finally {
    if ($locationPushed) {
        Pop-Location
    }
}
