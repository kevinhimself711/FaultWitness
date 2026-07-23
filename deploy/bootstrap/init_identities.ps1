[CmdletBinding()]
param(
    [string]$ConfigRoot = (Join-Path $env:APPDATA 'FaultWitness'),
    [string]$ToolRoot = (Join-Path $env:LOCALAPPDATA 'FaultWitness\tools')
)

$ErrorActionPreference = 'Stop'
$ageKeygen = Join-Path $ToolRoot 'age\1.3.1\age-keygen.exe'
$ageIdentity = Join-Path $ConfigRoot 'keys\age\identity.txt'
$sshPrivate = Join-Path $ConfigRoot 'keys\ssh\faultwitness_ed25519'
$sshPublic = "$sshPrivate.pub"

if (-not (Test-Path -LiteralPath $ageKeygen)) {
    throw 'Pinned age-keygen is missing; run install_tools.ps1 first.'
}
if ((Test-Path -LiteralPath $ageIdentity) -or (Test-Path -LiteralPath $sshPrivate)) {
    throw 'A project identity already exists; refusing to overwrite it.'
}

[System.IO.Directory]::CreateDirectory((Split-Path -Parent $ageIdentity)) | Out-Null
[System.IO.Directory]::CreateDirectory((Split-Path -Parent $sshPrivate)) | Out-Null

$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $ageKeygen -o $ageIdentity 2>$null
$ageExit = $LASTEXITCODE
$ErrorActionPreference = $previousPreference
if ($ageExit -ne 0 -or -not (Test-Path -LiteralPath $ageIdentity)) {
    throw 'Age identity generation failed.'
}

$current = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$ageAcl = New-Object System.Security.AccessControl.FileSecurity
$ageAcl.SetOwner($current.User)
$ageAcl.SetAccessRuleProtection($true, $false)
$ageRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    $current.User,
    'FullControl',
    'Allow'
)
$ageAcl.AddAccessRule($ageRule)
Set-Acl -LiteralPath $ageIdentity -AclObject $ageAcl

ssh-keygen -q -t ed25519 -a 100 -f $sshPrivate -N '""' -C 'faultwitness-i0007'
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $sshPublic)) {
    throw 'SSH identity generation failed.'
}
$sid = $current.User.Value
& icacls.exe $sshPrivate /inheritance:r /grant:r "*$sid`:(F)" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'SSH private-key ACL hardening failed.'
}

Write-Output 'PASS bootstrap identities: Age and SSH identities created outside repository'
