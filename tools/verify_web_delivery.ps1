param(
    [string]$Repository = '2223M1/bobbi-tv',
    [string]$Branch = 'codex/private-three-platform-20261019',
    [string]$Tag = 'audit-20261019-private-ce1909'
)

# Read-only GitHub/local artifact verification. Does not connect to the device,
# install artifacts, change Git refs, or read/upload authentication material.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceFreeze = 'cdf0c487c3640228cfe5844a3af2813e5367aa3b'

function Get-GitHubJson([string]$Path) {
    $raw = & gh api $Path
    if ($LASTEXITCODE -ne 0) { throw "GitHub metadata request failed: $Path" }
    return (($raw -join "`n") | ConvertFrom-Json)
}

$repo = Get-GitHubJson "repos/$Repository"
$release = Get-GitHubJson "repos/$Repository/releases/tags/$Tag"
$branchRef = Get-GitHubJson "repos/$Repository/git/ref/heads/$Branch"
$mainRef = Get-GitHubJson "repos/$Repository/git/ref/heads/main"
$tagRef = Get-GitHubJson "repos/$Repository/git/ref/tags/$Tag"
$comparison = Get-GitHubJson "repos/$Repository/compare/$sourceFreeze...$Branch"
$manifestPath = Join-Path $projectRoot 'review-evidence/web-artifact-manifest-20261019.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$manifestFile = Get-Item -LiteralPath $manifestPath
$localManifestBlob = & git -C $projectRoot hash-object -- $manifestPath
if ($LASTEXITCODE -ne 0) { throw 'Cannot hash local manifest as a Git object' }
$frozenManifestBlob = & git -C $projectRoot rev-parse "${sourceFreeze}:review-evidence/web-artifact-manifest-20261019.json"
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve manifest in frozen source commit' }
$expected = @($manifest.attachments) + @([pscustomobject]@{
    path = 'review-evidence/web-artifact-manifest-20261019.json'
    bytes = $manifestFile.Length
    sha256 = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
})
$checks = @{
    repository_private = [bool]$repo.private
    release_prerelease_not_draft = [bool]($release.prerelease -and -not $release.draft)
    source_tag_matches = [bool]($tagRef.object.type -eq 'commit' -and $tagRef.object.sha -eq $sourceFreeze)
    branch_contains_source_freeze = [bool]($comparison.merge_base_commit.sha -eq $sourceFreeze)
    main_unchanged = [bool]($mainRef.object.sha -eq '71ea55831c58f26cd6ab89ff5331b86ae33ca869')
    manifest_matches_source_freeze = [bool]($localManifestBlob -ceq $frozenManifestBlob)
    unique_expected_names = [bool](@($expected | ForEach-Object { [IO.Path]::GetFileName($_.path) } | Sort-Object -Unique).Count -eq $expected.Count)
    expected_asset_count = [bool](@($release.assets).Count -eq $expected.Count)
    no_quarantined_paths = [bool]($manifest.statistics.quarantined_paths -eq 0)
}
$assets = @()
foreach ($entry in $expected) {
    $name = [IO.Path]::GetFileName($entry.path)
    $remote = @($release.assets | Where-Object { $_.name -ceq $name })
    $localPath = Join-Path $projectRoot $entry.path
    $localFile = Get-Item -LiteralPath $localPath
    $localHash = (Get-FileHash -LiteralPath $localPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $localMatches = $localFile.Length -eq $entry.bytes -and $localHash -ceq $entry.sha256
    $remoteMatches = $remote.Count -eq 1 -and $remote[0].state -eq 'uploaded' -and
        $remote[0].size -eq $entry.bytes -and $remote[0].digest -ceq "sha256:$($entry.sha256)"
    $checks["asset:$name"] = [bool]($localMatches -and $remoteMatches)
    $assets += [ordered]@{
        name = $name
        local_path = $entry.path
        expected_bytes = $entry.bytes
        expected_sha256 = $entry.sha256
        local_matches = [bool]$localMatches
        remote_matches = [bool]$remoteMatches
        remote = @($remote | Select-Object id,name,state,size,digest,browser_download_url)
    }
}
$verified = @($checks.Values | Where-Object { -not $_ }).Count -eq 0
[ordered]@{
    schema_version = 1
    verified_at_utc = [DateTime]::UtcNow.ToString('o')
    verified = $verified
    repository = [ordered]@{ name=$repo.full_name; private=$repo.private; default_branch=$repo.default_branch }
    branch = [ordered]@{ name=$Branch; commit_at_verification=$branchRef.object.sha }
    main_commit_observed = $mainRef.object.sha
    source_freeze = [ordered]@{ tag=$Tag; commit=$tagRef.object.sha }
    release = [ordered]@{ id=$release.id; url=$release.html_url; draft=$release.draft; prerelease=$release.prerelease }
    checks = $checks
    artifacts = $manifest.statistics
    assets = $assets
    scope = 'Upload verification only; no device operations or playback tests. Later documentation commits may advance the review branch without changing the source tag.'
} | ConvertTo-Json -Depth 10
if (-not $verified) { exit 1 }
