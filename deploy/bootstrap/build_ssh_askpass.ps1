[CmdletBinding()]
param(
    [string]$ToolRoot = (Join-Path $env:LOCALAPPDATA 'FaultWitness\tools')
)

$ErrorActionPreference = 'Stop'
$version = '1.0.0'
$source = Join-Path $PSScriptRoot 'ssh_askpass\Program.cs'
$destinationDirectory = Join-Path $ToolRoot "ssh-askpass\$version"
$destination = Join-Path $destinationDirectory 'faultwitness-ssh-askpass.exe'
$sourceDigestFile = Join-Path $destinationDirectory 'source.sha256'
$sourceDigest = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()

[System.IO.Directory]::CreateDirectory($destinationDirectory) | Out-Null
$temporary = Join-Path $destinationDirectory (
    '.faultwitness-ssh-askpass-' + [guid]::NewGuid().ToString('N') + '.exe'
)
$sentinel = Join-Path $destinationDirectory (
    '.faultwitness-ssh-askpass-' + [guid]::NewGuid().ToString('N') + '.sentinel'
)

try {
    Add-Type `
        -TypeDefinition (Get-Content -LiteralPath $source -Raw) `
        -Language CSharp `
        -OutputAssembly $temporary `
        -OutputType ConsoleApplication

    $previousPassword = $env:FW_SSH_PASSWORD
    $previousSentinel = $env:FW_SSH_ASKPASS_SENTINEL
    try {
        $env:FW_SSH_PASSWORD = 'example-askpass-self-test'
        $env:FW_SSH_ASKPASS_SENTINEL = $sentinel
        $captured = & $temporary
        if ($LASTEXITCODE -ne 0 -or
            $captured -ne 'example-askpass-self-test' -or
            -not (Test-Path -LiteralPath $sentinel -PathType Leaf)) {
            throw 'Compiled SSH askpass helper failed its no-secret self-test.'
        }
    }
    finally {
        if ($null -eq $previousPassword) {
            Remove-Item Env:FW_SSH_PASSWORD -ErrorAction SilentlyContinue
        }
        else {
            $env:FW_SSH_PASSWORD = $previousPassword
        }
        if ($null -eq $previousSentinel) {
            Remove-Item Env:FW_SSH_ASKPASS_SENTINEL -ErrorAction SilentlyContinue
        }
        else {
            $env:FW_SSH_ASKPASS_SENTINEL = $previousSentinel
        }
    }

    Move-Item -LiteralPath $temporary -Destination $destination -Force
    [System.IO.File]::WriteAllText($sourceDigestFile, $sourceDigest + [Environment]::NewLine)
}
finally {
    foreach ($path in @($temporary, $sentinel)) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            Remove-Item -LiteralPath $path
        }
    }
}

Write-Output "PASS SSH askpass helper: version=$version source_digest=verified"
