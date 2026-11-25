# bobbi TV native private candidate

This is an actual Kodi 21.3 host with the bobbi UI, offline add-ons and generic
`Player.Bobi*` playback contracts. It is not a helper-only application. It does
not contain a shared account, proxy, remote server address, CE device backup,
release signing secret, or default cloud account. No CoreELEC/AMLogic/Dolby
Vision device patches are imported into Windows or Android.

## Target platform and Python runtime floor (PLAT-01)

- **Active release target**: **CoreELEC 21.x / Kodi 21 Omega (`xbmc.python >= 3.0.1`, CPython 3.11+)**. `xbmc.python` names the Kodi addon API; record the actual interpreter on each device. Existing Kodi-owned HTTP addons are supported from `requests 2.31.0` / `urllib3 2.2.3`; fresh offline installs retain bundled `2.34.2` / `2.8.0`. `release/http-runtime-policy.json` and the exact-byte consumer matrix define this compatibility boundary, not general security equivalence of the libraries. The prior local report records an AM6B+ running Python 3.11.9 with bundled HTTP versions; it does not prove that every CE2184 installation already has them.
- **Windows (`native/windows/maintenance.cpp`, `python3.8.dll`) — UNCERTIFIED / OUT OF CURRENT CE RELEASE SCOPE**: The legacy Windows maintenance host links `python3.8.dll`, whereas the current shared component generation and `urllib3 2.8.0` (`urllib3/_collections.py` runtime generic aliases such as `tuple[str, str]`) require **Python 3.11+** at runtime. Adding `from __future__ import annotations` to first-party modules does **not** fix third-party runtime type aliases and must never be used to claim Python 3.8 compatibility. Restoring Windows delivery requires upgrading the embedded Windows host Python runtime to **Python 3.11+** (matching Kodi 21 Omega) and passing full packaged-interpreter entrypoint import and live HTTP smoke gates.
- **Android — SEPARATE LINK & DEVICE GATES**: Android Kodi 21.3 embeds Python 3.11+, but APK delivery remains gated on clean NDK/SDK link receipts (`LINKED_NOT_DEVICE_VERIFIED`) and real hardware verification; missing build toolchains are recorded as `BLOCKED` / `NOT_TESTED`, never `PASS`.

## Windows (legacy host reference — uncertified for current Python 3.11+ component generation)

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

Historically, `native/windows/maintenance.cpp` loaded an embedded `python3.8.dll`,
standard library and Cryptodome libraries. That Python 3.8 host is **not** compatible
with the current Python 3.11+ (`xbmc.python 3.0.1` / `urllib3 2.8.0`) component
generation and is **uncertified / excluded from current CE release delivery** until
the embedded Windows Python runtime is upgraded to Python 3.11+. It accepts
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

The historical Android generation 2074 staged the same 22 component archives as
its contemporaneous CoreELEC snapshot, including the cinema skin, search,
library, cloud and subtitle code. It is not the later `ff0422c` component snapshot
and does not establish an Android clean link or packaged APK for that freeze.
Maintenance menus offer online APK lookup and local APK installation,
delegating confirmation and data-preserving replacement to Android.
For generation 2074, both ABI-native Kodi 21.3 engines were recompiled with
original-audio selection and the single-use transport capsule for playback
position and manual audio/subtitle intent. Hardware-specific CE playback code
is not included.

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
The `host` build now requires a new `BOBBI_NATIVE_PROOF` output path. It verifies
the actual source against the complete canonical series and performs a clean
link before writing `LINKED_NOT_DEVICE_VERIFIED`. Pass that exact receipt as
`--native-proof` to both repackaging and signing. Old marker-only binaries and
`COMPILED_NOT_LINKED` receipts are not packageable; do not manufacture a proof
when the Android compiler or linked output is unavailable. The receipt is local
build provenance, not remote attestation, toolchain reproducibility or device
certification. Existing receipts are preserved, so choose a new output path for
each build attempt.
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
  --native-proof /absolute/path/to/current-arm64-clean-link.json \
  --engine-root /absolute/path/to/locked/jniLibs \
  --probe-library /opt/bobbi-native-20261019/probe-arm64/ffprobe \
  --font-directory /opt/bobbi-native-20261019/fonts-arm64
```

Repeat with `--abi armv7`. Re-sign both build-only APKs with `sign-host-apk.py`
using the existing local release key and that exact components manifest. Do not
publish the temporary-signed inputs, private build inputs or profile backups.
Signing independently checks `--native-proof` against both the APK's native
bytes and embedded build receipt, plus this checkout's canonical inputs.
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

The `native-contracts` CI job fetches the exact base commit into a fresh tree,
applies the full series and runs the production host C++ semantic harnesses plus
completion negative controls. `native/tests/run_ci_gate.py --output DIR` is the
same local entry (`--source REPOSITORY` optionally clones a pinned local source).
Missing git/g++ is a nonzero `NOT_TESTED` gate, never a pass. This job does not
link Android, sign an APK or certify hardware; those remain separate evidence.

### CoreELEC AM6B disc pages and file tempo

These overlays are downstream of the pinned CE image, **not** members of the
portable Kodi/Android series. Build each against the proof directory for its
exact predecessor, using a new output directory:

```sh
python3 native/tests/build_ce_bluray_pages_candidate.py --predecessor "$CE_BASE" --output "$DISC_OUT"
python3 native/tests/build_ce_pcm_tempo_candidate.py --predecessor "$DISC_PROOF" --output "$TEMPO_OUT"
```

The disc overlay coalesces overlapping reads of the same page; it does not set
global cache sizes or disable prefetch. The tempo overlay borrows the PCM clock
only on an eligible decoded audio/video file, then restores it. Do not infer
passthrough, disc, or Android tempo support from the CE result.
`check_ce_bluray_page_race.py` and `check_ce_pcm_tempo.py` exercise both the
unmodified predecessor and the patched production C++. Build receipts alone
do not authorize deployment. The `discpages2141` and `pcmtempo2148` device
profiles in `tools/ce_native_update.py` pin the install and rollback identities.

The next CE-only profile, `r18lifecycle2154`, fixes two independent AM6B
shutdown crashes: presenting an AML frame while its codec/pool is retiring,
and saving skin settings from a timer after the add-on manager has stopped.
The renderer uses the pinned frame; the active skin debounces on the GUI
thread and keeps Kodi's normal unload save. Build with
`build_ce_am6b_lifecycle.py --predecessor "$TEMPO_PROOF" --output "$NEW_OUT"`.
It rebuilds all three consumers of the modified frame layout plus the skin
translation unit. `check_ce_am6b_lifecycle.py` exercises the predecessor and
candidate using their production C++. The pinned candidate and rollback hashes,
reviewed component versions and evidence limits are recorded in the
[R18 device acceptance](../docs/architecture/r18-device-acceptance.md).

Freeze components with the root release tool, then stage only its manifest ZIP
snapshot. `stage-components.py` verifies package hashes and XML IDs, and adds
optional system add-on entries so fresh profiles enable the intended UI without
overriding later user disable decisions. Android staging runs after Kodi's
bundle copy, before Gradle. APK signing is performed by `sign-host-apk.py` with
the existing local key; secrets travel via the child process environment only.

Official Cryptodome is ABI-native host content: Android Python3.11 / 3.12.0
(legacy Windows Python3.8 / 3.9.4 remains uncertified and out of current CE scope until upgraded to Python 3.11+). The upstream addon metadata version is 3.4.3 and is
not the library version. Never copy a CE ARM32 crypto binary into these hosts.
Windows AES known-vector and P-256 DSS self-tests are part of packaging.

Stable rollout remains closed until clean install, lifecycle recovery,
update/rollback, UI, and genuinely new-work playback gates pass. Read each
artifact's verification receipt; `real_device_verified: false` is intentional
until those checks have actually been performed.
