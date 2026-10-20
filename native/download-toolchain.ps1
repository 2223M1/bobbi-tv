param([string]$Name = '')
$ErrorActionPreference = 'Stop'
$nativeRoot = $PSScriptRoot
$downloadRoot = Join-Path $nativeRoot 'downloads'
New-Item -ItemType Directory -Force $downloadRoot | Out-Null
$lock = Get-Content -LiteralPath (Join-Path $nativeRoot 'toolchain-lock.json') -Raw | ConvertFrom-Json
$archives = $lock.android.archives
if ($Name) { $archives = @($archives | Where-Object { $_.name -eq $Name }) }
if (!$archives) { throw 'No locked archive selected' }
foreach ($archive in $archives) {
    $destination = Join-Path $downloadRoot $archive.name
    $valid = (Test-Path -LiteralPath $destination) -and
        ((Get-Item -LiteralPath $destination).Length -eq $archive.bytes) -and
        ((Get-FileHash -LiteralPath $destination -Algorithm $archive.algorithm).Hash.ToLowerInvariant() -eq $archive.digest)
    if (!$valid) {
        & curl.exe --location --fail --retry 2 --connect-timeout 20 --max-time 1200 --output $destination $archive.url
        if ($LASTEXITCODE -ne 0) { throw "Download failed: $($archive.name)" }
    }
    if ((Get-Item -LiteralPath $destination).Length -ne $archive.bytes -or
        (Get-FileHash -LiteralPath $destination -Algorithm $archive.algorithm).Hash.ToLowerInvariant() -ne $archive.digest) {
        throw "Locked length/checksum mismatch: $($archive.name)"
    }
    [pscustomobject]@{ name=$archive.name; verified=$true; sha256=(Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() }
}
