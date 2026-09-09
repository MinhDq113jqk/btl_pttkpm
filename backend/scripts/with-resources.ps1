[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Python = "$PSScriptRoot/../.venv/Scripts/python.exe",
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$PythonArgs
)
$ErrorActionPreference = 'Stop'
$previousDatabaseUrl = $env:DATABASE_URL
try {
    if (-not $env:DATABASE_URL) {
        $repoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')
        $resourcePath = Get-ChildItem -LiteralPath $repoRoot -File |
            Where-Object { $_.Name -like 'T?i_nguy?n.md' } |
            Select-Object -First 1
        if (-not $resourcePath) { throw 'No local resource Markdown file found.' }
        $resourceText = [IO.File]::ReadAllText($resourcePath.FullName)
        $uriMatch = [regex]::Match($resourceText, 'postgres(?:ql)?://[^\s`"<>]+')
        if (-not $uriMatch.Success) { throw 'No PostgreSQL URI found in local resource file.' }
        # Decode Markdown escaping without modifying the original secret file.
        $env:DATABASE_URL = $uriMatch.Value -replace '\\([_!*])', '$1'
        $resourceText = $null
        $uriMatch = $null
    }
    # Gemini is intentionally not loaded or called in Phase 1.
    & $Python @PythonArgs
    $resultCode = $LASTEXITCODE
} finally {
    $env:DATABASE_URL = $previousDatabaseUrl
}
exit $resultCode
