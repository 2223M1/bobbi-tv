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
Kodi engine, UI and the packaged MatriX.147 local BT service. The service starts
only for a BT selection or an explicit setup action, with a visible stop control.
An existing explicit backend configuration takes priority.
Native updates use Android's package manager; runtime add-on hot replacement is
not enabled. A rollback APK must use the same signer and a new, higher version
code. Do not uninstall/clear data to bypass an installation conflict.

The Android generation 2074 stages the same 22 current component archives as
CoreELEC, including the current cinema skin, search, library, cloud and subtitle
code. Maintenance menus offer online APK lookup and local APK installation,
delegating confirmation and data-preserving replacement to Android.
Both ABI-native Kodi 21.3 engines are recompiled with original-audio selection
and the single-use transport capsule for playback position and manual audio/
subtitle intent. Hardware-specific CE playback code is not included.

Optional cloud preparation connects to a separately running, local Android
CloudDrive service. The configured 115 account must match the cinema account.
Fresh file verification returns an ephemeral local HTTP route, so Android does
not need a filesystem mount or root. CloudDrive remains responsible for its
login and background lifecycle. A packaged Android ffprobe qualifies media.
Exact-release font archives use packaged decoder tools in a resource-limited
child, with private font storage read by the next subtitle renderer.

To refresh an existing isolated native build, build the root components first
with the maintainer's application configuration (not `--source-check`). Package
each ABI with a strictly increasing Android version code and explicit display
version. For the original 21-component native staging image only, pass the
reviewed addition flag for the 22nd torrent adapter.
For a new build tree, first run `build-android.sh ROOT ABI template` with the
frozen manifest environment. Its temporary APK supplies the upstream assets,
not a distributable application. Repackage it with all native host/tool inputs;
omit the addition flag when its manifest already contains all 22 components.

```sh
python3 native/repackage-android.py --root /opt/bobbi-native-20261019 \
  --manifest /absolute/path/components/manifest.json --sequence 2026102074 \
  --version-name '2074 (Kodi 21.3)' --abi arm64 \
  --allow-component-addition plugin.video.bobbi.torrent \
  --native-library /opt/bobbi-native-20261019/build-arm64/libkodi.so \
  --engine-root /absolute/path/to/locked/jniLibs \
  --probe-library /opt/bobbi-native-20261019/probe-arm64/ffprobe \
  --font-directory /opt/bobbi-native-20261019/fonts-arm64
```

Repeat with `--abi armv7`. Re-sign both build-only APKs with `sign-host-apk.py`
using the existing local release key and that exact components manifest. Do not
publish the temporary-signed inputs, private build inputs or profile backups.
The `android/` directory is the legacy helper, not the full cinema APK source.
Its engine implementation is reused by `stage-android-host.py`; do not install
the helper over the full cinema. Build native tools with `build-android-probe.sh`
and `build-android-fonts.sh`, then sign only the final frozen component snapshot.

The normal Kodi audio/video path remains full quality. Device-level decoder,
HDR, audio passthrough and Android 16KiB page-size compatibility still require
real hardware validation; compilation and ZIP inspection do not certify them.
CloudDrive grant/range playback, BT-to-115 handoff, system install prompts and
font appearance also remain unverified on Android hardware. Ordinary same-pack
preparation is available; cross-torrent advance discovery still requires an
explicitly configured search backend. No private CE service is copied into an APK.

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
