# Windows native installation and 115 authorization readiness

This is the **1902 historical readiness record**, not the final runtime status.
Subsequent 1903 isolated playback testing reused the owner's existing CE session
through the running host's account-generation API, in memory, without a new QR
exchange, renewal or logout. The personal TMDb configuration was likewise kept
only in the ignored test profile. See `windows-local-account-acceptance.json`
and `windows-local-metadata-acceptance.json` under `review-evidence/`.
This does not certify fresh QR login, multi-account switching or Android.

## Actual execution, not a package-only inspection

- Sequence 2026101902 installer was executed silently at the isolated test path
  `native/build/windows-installer-1902`, exit 0. All 4,397 frozen-image files
  matched SHA-256; only the generated uninstaller was additional.
- The installed launcher was then run without `--portable`, on a private
  Windows desktop never switched onto the user's desktop. The standard profile
  `%LOCALAPPDATA%/bobbi TV/profile` did not exist before this test. Only minimal
  window/RPC settings were provided as a fixture; no account, original Kodi
  settings or device state was copied.
- JSON-RPC ping, active `skin.bobbi.cinema`, all seven native `Player.Bobi*`
  methods and graceful exit 0 were verified. The minimal settings fixture
  generated the known default-settings initialization log line; no Python
  exception was observed. This is startup, not media playback certification.
- The real uninstaller then removed only the exact test installation,
  registration and shortcut. All 25 shared-profile files remained byte-for-byte
  identical. This new empty-account profile is retained. Original Kodi profile
  was absent throughout. No credentials appeared.

Evidence: `review-evidence/native-windows-installer-1902-20261019.json`,
`native-windows-installed-startup-1902-20261019.json`, and
`native-windows-uninstall-1902-20261019.json`.

## Installation/profile choices

NSIS permits another new empty program directory using `/D=<absolute path>` as
the final argument. It does not expose a profile-directory option. Normal
launch uses the above per-user shared profile; `--portable` instead uses a
`profile` beside that executable. The two are explicit modes, not a copied
device configuration. Do not run the frozen packaging image directly, because
the launcher creates a maintenance directory; install or copy a test generation.

## QR UI and safety boundary at the 1902 checkpoint

The intended user route is **我的 → 影院设置 · 登录 / 后台 / 更新 → 115 账号 ·
用自己的手机扫码登录**. `script.bobbi.setup` calls the packaged
`bobbi_platform.cloud_ui.login`. The main window must be visible for the user
to scan; this is separate from the private desktop used for startup tests.

- QR data comes from `qrcodeapi.115.com`, rendered locally with bundled Segno.
  No external QR-rendering service or password form is used.
- The UI polls every 2 seconds, expires after 180 seconds and supports Back to
  cancel. It exchanges the approved session once, without retrying an ambiguous
  login write. Confirmation is saved atomically through the current host-owned
  account generation. A cancelled/failed exchange does not deliberately replace
  an existing local login.
- The local storage is
  `%LOCALAPPDATA%/bobbi TV/profile/userdata/addon_data/script.module.bobbi.platform/115-os_linux.json`.
  Do not print it, manually overwrite it with CE credentials, or include it in
  artifacts. Later controlled test authorization used the host account API,
  not direct profile-file copying.
- No QR was requested and no account was authorized during these checks.
- **Cross-device session isolation is not established.** The current exchange
  endpoint and stored app type are fixed to `os_linux`, including on Windows.
  A second authorization of the same 115 account/client class could invalidate
  the CE Linux session according to provider policy. Until evidence establishes
  an isolated compatible client type, do not promise no effect on CE and do not
  initiate an account exchange as a background test.
- The smoke profile temporarily enables unauthenticated Kodi HTTP on port
  18089 for test RPC. Kodi is now stopped. Before interactive reuse, the
  controlling agent should remove/disable that test HTTP setting or explicitly
  restrict and authenticate it; the login UI itself does not require HTTP.

At that checkpoint playback was not authorized. Later isolated test-session
installation enabled media trials without a second provider login; those trials
and their failures must be read from the newer evidence, not inferred here.
Android still has no connected ADB device or verified remote return to CE.
