[CmdletBinding()]
param(
    [string]$OutputPath = (Join-Path $env:LOCALAPPDATA 'GreenCity\demo-credentials.json')
)

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$outputFullPath = [System.IO.Path]::GetFullPath($OutputPath)
$repoPrefix = $repoRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
if ($outputFullPath.Equals($repoRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
    $outputFullPath.StartsWith($repoPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Credential output must be outside the repository.'
}
if (Test-Path -LiteralPath $outputFullPath) {
    throw 'Credential output already exists. Choose a new private path; the existing file was not changed.'
}

$usernames = @(
    'admin_demo', 'director_west', 'cskh_west', 'cskh_east', 'accountant_west',
    'techlead_west', 'technician_west', 'cleaning_west', 'security_west', 'resident_west'
)
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$credentials = [ordered]@{}
try {
    foreach ($username in $usernames) {
        $bytes = New-Object byte[] 32
        $rng.GetBytes($bytes)
        $password = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
        $credentials[$username] = $password
        [Array]::Clear($bytes, 0, $bytes.Length)
    }
} finally {
    $rng.Dispose()
}

$parentPath = Split-Path -Parent $outputFullPath
if (-not (Test-Path -LiteralPath $parentPath)) {
    New-Item -ItemType Directory -Path $parentPath -Force | Out-Null
}
$json = $credentials | ConvertTo-Json -Depth 3
[System.IO.File]::WriteAllText($outputFullPath, $json, ([System.Text.UTF8Encoding]::new($false)))

try {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = Get-Acl -LiteralPath $outputFullPath
    $acl.SetAccessRuleProtection($true, $false)
    $acl.SetOwner($identity)
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'Allow')
    $acl.SetAccessRule($rule)
    Set-Acl -LiteralPath $outputFullPath -AclObject $acl
} catch {
    Remove-Item -LiteralPath $outputFullPath -Force -ErrorAction SilentlyContinue
    throw 'Could not restrict access to the generated credential file; it was removed.'
}

$credentials.Clear()
$password = $null
$json = $null
Write-Output "Generated 10 unique demo credentials in a current-user-only file: $outputFullPath"
Write-Output 'The credential values were not printed. Keep this file outside the repository.'
