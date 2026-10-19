# Real user-level installer acceptance. Never starts the player or changes a profile.
param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [Parameter(Mandatory=$true)][string]$Image,
    [Parameter(Mandatory=$true)][string]$Target,
    [Parameter(Mandatory=$true)][string]$Report,
    [string]$ExpectedInstallerSha256 = '4c6b9901ccecad54a18d60dfab388b9585325aec9cba33fdd08d90da3f3fd30a'
)
$ErrorActionPreference = 'Stop'
$installerPath = (Resolve-Path -LiteralPath $Installer).Path
$imagePath = (Resolve-Path -LiteralPath $Image).Path
$targetPath = [IO.Path]::GetFullPath($Target)
$reportPath = [IO.Path]::GetFullPath($Report)
$build = Get-Content -LiteralPath (Join-Path $imagePath 'bobbi-build.json') -Raw | ConvertFrom-Json
$version = $build.version
$sequence = $build.sequence
$registryPath = "HKCU:/Software/Microsoft/Windows/CurrentVersion/Uninstall/bobbiTV-$version-$sequence"
$programsPath = [Environment]::GetFolderPath('Programs')
$shortcutPath = Join-Path $programsPath "bobbi TV/bobbi TV $version-$sequence.lnk"
$sharedProfile = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'bobbi TV/profile'
$originalKodi = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'Kodi'
foreach ($path in @($targetPath, $registryPath, $shortcutPath, $reportPath)) {
    if (Test-Path -LiteralPath $path) { throw "Existing destination or registration must not be overwritten: $path" }
}
$sharedBefore = Test-Path -LiteralPath $sharedProfile
$kodiBefore = Test-Path -LiteralPath $originalKodi
$expectedHash = $ExpectedInstallerSha256
$actualHash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedHash) { throw 'Wrong frozen installer' }
if ($targetPath.Contains(' ')) { throw 'Use a space-free throwaway test target for an unambiguous NSIS /D argument' }
$watch = [Diagnostics.Stopwatch]::StartNew()
$process = Start-Process -FilePath $installerPath -ArgumentList @('/S', "/D=$targetPath") -WindowStyle Hidden -PassThru
if (-not $process.WaitForExit(180000)) { throw 'Installer still running; no process or data was forcibly removed' }
$process.Refresh()
if ($process.ExitCode -ne 0) { throw "Installer returned $($process.ExitCode)" }
$verified = 0
$imageFiles = @(Get-ChildItem -LiteralPath $imagePath -Recurse -File)
foreach ($file in $imageFiles) {
    $relative = $file.FullName.Substring($imagePath.Length).TrimStart('\', '/')
    $installed = Join-Path $targetPath $relative
    if (-not (Test-Path -LiteralPath $installed -PathType Leaf)) { throw "Missing installed file: $relative" }
    if ((Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $installed -Algorithm SHA256).Hash) {
        throw "Installed bytes differ: $relative"
    }
    $verified++
}
$installedFiles = @(Get-ChildItem -LiteralPath $targetPath -Recurse -File)
if ($installedFiles.Count -ne ($verified + 1)) { throw 'Unexpected installed file set' }
if (-not (Test-Path -LiteralPath (Join-Path $targetPath 'Uninstall.exe') -PathType Leaf)) { throw 'Uninstaller missing' }
if (Test-Path -LiteralPath (Join-Path $targetPath 'portable.flag')) { throw 'Installed mode accidentally marked portable' }
$registration = Get-ItemProperty -LiteralPath $registryPath
if ($registration.InstallLocation -ne $targetPath) { throw 'Wrong registered install location' }
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
if ($shortcut.TargetPath -ne (Join-Path $targetPath 'bobbi.exe')) { throw 'Wrong Start Menu target' }
if ((Test-Path -LiteralPath $sharedProfile) -ne $sharedBefore) { throw 'Installer unexpectedly created or removed the shared profile' }
if ((Test-Path -LiteralPath $originalKodi) -ne $kodiBefore) { throw 'Installer unexpectedly created or removed the original Kodi profile' }
$receipt = [ordered]@{
    schema = 1
    timestamp_utc = [DateTime]::UtcNow.ToString('o')
    release_sequence = $sequence
    installer = $installerPath
    installer_sha256 = $actualHash
    installer_executed = $true
    installer_exit = $process.ExitCode
    execution_level = 'user; no elevation requested'
    silent = $true
    target = $targetPath
    frozen_image = $imagePath
    frozen_image_files_verified_sha256 = $verified
    installed_files = $installedFiles.Count
    uninstall_executable_present = $true
    registry_target_verified = $true
    start_menu_target_verified = $true
    shared_profile_exists_before = $sharedBefore
    shared_profile_exists_after = (Test-Path -LiteralPath $sharedProfile)
    original_kodi_profile_exists_before = $kodiBefore
    original_kodi_profile_exists_after = (Test-Path -LiteralPath $originalKodi)
    player_launched = $false
    account_state_copied = $false
    real_playback_verified = $false
    uninstall_executed = $false
    disposition = 'Isolated installed test generation retained; installer registration and Start Menu shortcut point to this path.'
    elapsed_seconds = [Math]::Round($watch.Elapsed.TotalSeconds, 3)
}
$receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $reportPath -Encoding utf8
$receipt | ConvertTo-Json -Depth 5
