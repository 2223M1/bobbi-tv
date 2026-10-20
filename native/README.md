# bobbi TV native private candidate

This is an actual Kodi 21.3 host with the bobbi UI, offline add-ons and generic
`Player.Bobi*` playback contracts. It is not a helper-only application. It does
not contain a shared account, proxy, remote server address, CE device backup,
release signing secret, or default cloud account. No CoreELEC/AMLogic/Dolby
Vision device patches are imported into Windows or Android.

## Windows

Launch **bobbi.exe**, never `host/kodi.exe`. The portable ZIP uses `profile/`
beside the launcher; the user-level installer uses
`%LOCALAPPDATA%/bobbi TV/profile`. There is no service or administrator setup.
The installer creates a new version directory and refuses to overwrite an old
one. Keep the previous directory for native-host rollback. Uninstallation
preserves the shared profile. Windows executables are currently unsigned;
the package receipt records their SHA256, but is not an Authenticode identity.

Close the application before importing a private signed offline update:

```text
bobbi.exe --apply C:\path\candidate.bobbi-update.zip
bobbi.exe --rollback
```

For the portable image keep `portable.flag` or add `--portable`. A local
recovery check must complete before any add-on is loaded. The launcher holds a
profile-specific mutex and a nonshared, inherited file handle for the entire
Kodi/maintenance lifecycle. A kill-on-close job prevents orphan players. The
Kodi entry point rejects ordinary launches without its inherited host lease.
This coordination is not a sandbox against malicious programs running under
the same Windows account. A first-start short-lived lifecycle probe is only an
exit proof for maintenance; it is not a playback test.

The maintenance host loads Kodi's bundled Python 3.8 DLL, standard library and
Cryptodome libraries. No separate Python installation is necessary. It accepts
only local signed full component generations; it has no anonymous update URL
or embedded GitHub credential. The launcher does not perform in-play updates.
New profiles do not auto-enable upstream `service.xbmc.versioncheck`, avoiding
official-Kodi installer prompts inside this private host. Its files/credits and
existing user-profile choices are preserved.

## Android

Android 8/API26 or newer; ABI-specific ARM64 and ARMv7 APKs. Application ID
`org.bobbi.helper` and the original release signer are preserved, so installation
does not require clearing account/app data. This candidate contains the actual
Kodi engine and UI, but not the previous helper's TorrServer/BT service. A BT
backend remains optional and must not be represented as already installed.
Native updates use Android's package manager; runtime add-on hot replacement is
not enabled. A rollback APK must use the same signer and a new, higher version
code. Do not uninstall/clear data to bypass an installation conflict.

The normal Kodi audio/video path remains full quality. Device-level decoder,
HDR, audio passthrough and Android 16KiB page-size compatibility still require
real hardware validation; compilation and ZIP inspection do not certify them.

## Reproducible build boundary

Official base: `xbmc/xbmc`, tag `21.3-Omega`, commit
`a3a448d26b8d560a65655dab2cd122994dc4e146`. Apply the ordered files in `patches/`.
`toolchain-lock.json` records pinned toolchain sources/checksums. Windows uses
VS2022 Build Tools 17.14, SDK10.0.22621 and upstream Win32 dependency downloads.
Use `/utf-8` for MSVC on non-English Windows. Android uses NDK21e, API26,
SDK34, Temurin17 and isolated upstream depends builds. `build-android.sh` never
uses CE target libraries. Build artifacts and development toolchains are not
source-controlled.

Freeze components with the root release tool, then stage only its manifest ZIP
snapshot. `stage-components.py` verifies package hashes and XML IDs, and adds
optional system add-on entries so fresh profiles enable the intended UI without
overriding later user disable decisions. Android staging runs after Kodi's
bundle copy, before Gradle. APK signing is performed by `sign-host-apk.py` with
the existing local key; secrets travel via the child process environment only.

Official Cryptodome is ABI-native host content: Windows Python3.8 / 3.9.4;
Android Python3.11 / 3.12.0. The upstream addon metadata version is 3.4.3 and is
not the library version. Never copy a CE ARM32 crypto binary into these hosts.
Windows AES known-vector and P-256 DSS self-tests are part of packaging.

Stable rollout remains closed until clean install, lifecycle recovery,
update/rollback, UI, and genuinely new-work playback gates pass. Read each
artifact's verification receipt; `real_device_verified: false` is intentional
until those checks have actually been performed.
