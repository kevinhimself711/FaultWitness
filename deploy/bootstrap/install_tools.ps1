[CmdletBinding()]
param(
    [string]$ToolRoot = (Join-Path $env:LOCALAPPDATA 'FaultWitness\tools')
)

$ErrorActionPreference = 'Stop'
$headers = @{ 'User-Agent' = 'FaultWitness-I0007' }

$sopsVersion = '3.13.2'
$sopsHash = 'cb6fec76e23cb4ac56771ac38472b0fe1ba79a849bf2200aeda7c9467a045b7b'
$sopsUrl = 'https://github.com/getsops/sops/releases/download/v3.13.2/sops-v3.13.2.amd64.exe'
$sopsDirectory = Join-Path $ToolRoot "sops\$sopsVersion"
$sopsExecutable = Join-Path $sopsDirectory 'sops.exe'

$ageVersion = '1.3.1'
$ageArchiveHash = 'c56e8ce22f7e80cb85ad946cc82d198767b056366201d3e1a2b93d865be38154'
$ageExecutableHash = '90f5cc37249c06e0b302e476a8a63bcefeecd9437c192b8af33e6ff2d69558dd'
$ageKeygenHash = '8b9c27ef2ab6f215f689bf1e609bf82c8faf4c041f32452fa80396b3f8c4f687'
$ageUrl = 'https://github.com/FiloSottile/age/releases/download/v1.3.1/age-v1.3.1-windows-amd64.zip'
$ageDirectory = Join-Path $ToolRoot "age\$ageVersion"
$ageExecutable = Join-Path $ageDirectory 'age.exe'
$ageKeygen = Join-Path $ageDirectory 'age-keygen.exe'

function Assert-Hash {
    param([string]$Path, [string]$Expected)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Required tool artifact is absent."
    }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Expected) {
        throw "Pinned tool checksum mismatch."
    }
}

[System.IO.Directory]::CreateDirectory($sopsDirectory) | Out-Null
if (-not (Test-Path -LiteralPath $sopsExecutable)) {
    Invoke-WebRequest -Headers $headers -Uri $sopsUrl -OutFile $sopsExecutable
}
Assert-Hash -Path $sopsExecutable -Expected $sopsHash

[System.IO.Directory]::CreateDirectory($ageDirectory) | Out-Null
if (-not (Test-Path -LiteralPath $ageExecutable) -or -not (Test-Path -LiteralPath $ageKeygen)) {
    $temporary = Join-Path ([System.IO.Path]::GetTempPath()) ("faultwitness-age-" + [guid]::NewGuid().ToString('N'))
    [System.IO.Directory]::CreateDirectory($temporary) | Out-Null
    try {
        $archive = Join-Path $temporary 'age.zip'
        $expanded = Join-Path $temporary 'expanded'
        Invoke-WebRequest -Headers $headers -Uri $ageUrl -OutFile $archive
        Assert-Hash -Path $archive -Expected $ageArchiveHash
        Expand-Archive -LiteralPath $archive -DestinationPath $expanded
        $ageSource = Get-ChildItem -LiteralPath $expanded -Recurse -Filter 'age.exe' | Select-Object -First 1
        $keygenSource = Get-ChildItem -LiteralPath $expanded -Recurse -Filter 'age-keygen.exe' | Select-Object -First 1
        if (-not $ageSource -or -not $keygenSource) {
            throw 'Pinned Age archive is missing required executables.'
        }
        Copy-Item -LiteralPath $ageSource.FullName -Destination $ageExecutable
        Copy-Item -LiteralPath $keygenSource.FullName -Destination $ageKeygen
    }
    finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Recurse
        }
    }
}
Assert-Hash -Path $ageExecutable -Expected $ageExecutableHash
Assert-Hash -Path $ageKeygen -Expected $ageKeygenHash

Write-Output "PASS bootstrap tools: sops=$sopsVersion age=$ageVersion checksums=verified"
