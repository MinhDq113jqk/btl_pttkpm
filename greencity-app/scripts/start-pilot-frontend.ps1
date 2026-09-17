[CmdletBinding()]
param(
    [string]$Npm = 'npm',
    [string]$BindHost = '127.0.0.1',
    [int]$Port = 3000,
    [string]$ApiBaseUrl,
    [string]$ProxyTarget
)

$ErrorActionPreference = 'Stop'
$frontendRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$previousApiBaseUrl = [Environment]::GetEnvironmentVariable('VITE_API_BASE_URL', 'Process')
$previousProxyTarget = [Environment]::GetEnvironmentVariable('VITE_DEV_API_PROXY_TARGET', 'Process')
$resultCode = 0

function Restore-ProcessEnvironment {
    param([string]$Name, [string]$Value)
    if ($null -eq $Value) {
        Remove-Item -LiteralPath "Env:$Name" -ErrorAction SilentlyContinue
    }
    else {
        Set-Item -Path "Env:$Name" -Value $Value
    }
}

try {
    Push-Location -LiteralPath $frontendRoot
    if ($PSBoundParameters.ContainsKey('ApiBaseUrl')) {
        $env:VITE_API_BASE_URL = $ApiBaseUrl
    }
    if ($PSBoundParameters.ContainsKey('ProxyTarget')) {
        $env:VITE_DEV_API_PROXY_TARGET = $ProxyTarget
    }
    & $Npm run dev -- --host $BindHost --port $Port
    $resultCode = $LASTEXITCODE
}
catch {
    Write-Error "Pilot frontend did not start: $($_.Exception.Message)"
    $resultCode = 2
}
finally {
    if ((Get-Location).Path -eq $frontendRoot) {
        Pop-Location
    }
    Restore-ProcessEnvironment -Name 'VITE_API_BASE_URL' -Value $previousApiBaseUrl
    Restore-ProcessEnvironment -Name 'VITE_DEV_API_PROXY_TARGET' -Value $previousProxyTarget
}
exit $resultCode
