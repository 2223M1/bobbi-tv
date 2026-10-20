# Runtime portability audit — 2026-10-19

Scope: the restored candidate's actual service/client execution paths, not a
claim that mock tests certify a television, HDR, audio passthrough or Android.

## Executable defects found and fixed

| Finding | Correction and evidence |
| --- | --- |
| Native subtitle lookup still attempted `AF_UNIX.connect_ex(None)` after the default preparation socket moved to the host | Native adapter now uses `subtitle_lookup_portable`: one bounded background lookup, latest intent only, late-result discard, no waiting on the serialized player actor |
| Metadata/card refresh used unconditional `fcntl` in Windows execution paths | Frontend metadata, season-card queue, TV detail and movie detail leases use the shared Windows/POSIX `InstanceLock`; real Windows lock exclusion and refresh tests pass |
| Non-Windows search admission defaulted to `/storage/.local/share/bobitv` | Uses the configured Kodi profile's `search-admission` directory; existing OS lease and retained IO ownership remain |
| Prepared direct snapshot defaulted to a CE `/storage/.kodi` pathname | Uses lazy `ProfilePath`; both prepared/direct projections carry and verify account generation |
| Subtitle authority accepted only a hard-coded CE export directory | Uses the same `ProfilePath('subtitle-browser')` as actual subtitle exporters; exact basename/hash/size/intent checks remain |
| Optional BT startup hashed a 60MB binary and performed HTTP health IO on the native actor | Single opt-in startup worker; shutdown racing startup closes only that worker's child process |
| CE F9's native subtitle ABI still expects the historical export root | Host verifies real CoreELEC, actual native-method capability and the observed F9 executable SHA256 before selecting that single legacy directory; other binaries/platforms retain the bobbi profile |
| The manual OpenSubtitles script was omitted from the portable inventory | Restored as `script.bobbi.opensubtitles`, portable lock/publication, shared root, native intent and account-generation guards; empty user-configured API key, no bundled application key/private proxy |
| Preparation client existed without a bound portable implementation | Explicit optional CE preparation host, same policies/SQLite owner, real UID verification, revoke/drain handshake and per-epoch state |
| Preparation resolver/font/protection shutdown used a Python 3.9-only keyword | Three single-future lanes now use Python 3.8-compatible shutdown |

Image service and catalogue refresh are independent capabilities. Empty host
startup does not import CD2, native BT engine, ctypes, native player or old
Linux preparation bootstrap. The image capability may fail independently
without preventing the base host from starting.

## Deliberately retained platform-specific code

- CD2 prepared-file mount strings remain in the CE preparation/resolution and
  native prepared-source adapters. They are not generalized to guessed Android
  mounts and do not run on empty configuration.
- Legacy Unix playback/preparation transports remain only for callers that
  explicitly pass a socket path. The default route is authenticated loopback
  host IPC. The native adapter no longer uses the old Unix subtitle lookup.
- Font extraction's `resource` limits live inside its separate extraction
  worker, not in base startup. Preparation/ffprobe/font installation remains an
  explicit CE capability until other backends are proven.
- OS leases choose `msvcrt` on Windows and lazy `fcntl` on POSIX. No top-level
  fcntl dependency or system-unit management is introduced.
- The CE F9 subtitle root is an explicit ABI adapter, not a general path
  override. The observed executable SHA256 is
  `8962740e718a7978acadbf2ae7ad55b0cd0742f6d0db162e9c1a1d8645ef834b`.
  One hash read occurs before the host/native actor starts. A bounded,
  non-secret `plugin.video.bobbi/runtime-paths.json` records the ABI selector;
  independent Kodi interpreters read the same selector. Only the profile root
  and the exact known CE legacy subtitle directory are accepted; symlink roots,
  arbitrary paths, copied CE markers on non-CE platforms and malformed records
  are rejected. This does not migrate or delete any previous subtitle files.

## Manual subtitle capability

- Skin action: `RunScript(script.bobbi.opensubtitles)`; configuration action:
  `Addon.OpenSettings(script.bobbi.opensubtitles)`.
- Requires Kodi Python 3, bobbi core and bobbi platform (all declared in its
  manifest). The API path uses the already packaged bounded subtitle HTTP
  worker; no separate external provider package is required. A personal
  OpenSubtitles API key is required and is intentionally not shipped.
- Search/download uses Chinese text identity/quality, not timeline acceptance;
  downloaded candidates remain “待校准”. It downloads only the chosen text,
  presents a human-readable immutable file in the unified subtitle root, and
  opens native BrowseSubtitle only after explicit confirmation. The native
  browser still owns loading/manual intent; no `setSubtitles` shortcut exists.
- Changing film, native instance, selection epoch, manual subtitle intent or
  115 account generation invalidates a pending search/download. No 115 login is
  required to search: an unauthenticated account snapshot is still guarded.
- Stock Kodi lacks this native context contract and gets a clear capability
  error rather than simulated receipts. Windows/Android source/lock tests are
  not actual native-dialog acceptance. API availability/quota/download must
  still be tested with the owner's configured key; no live request was made
  by this audit agent.

## Platform and verification boundaries

| Platform/mode | Evidence | Not established by this review |
| --- | --- | --- |
| Windows Python 3.12, empty Kodi profile with minimal Kodi stubs | Actual `lib.portable_runtime.main` starts and closes; pure host startup, locks, scheduler, account and preparation regression tests execute | Actual Kodi GUI, playback, HDR, audio, native binary ABI |
| Python 3.8 source compatibility | 507 addon Python modules parse with the 3.8 grammar; no eager builtin-generic/union annotation findings in the scan | Execution under a real Python 3.8 interpreter and every third-party binary dependency |
| Stock Kodi 21 | Capability-based player factory selects the non-owning standard handoff, never synthesizes native receipts; no preparation/BT import on empty config | Native automatic continuation/subtitle authority is intentionally not claimed |
| CoreELEC native candidate | Existing native actor retained; preparation/BT adapters are isolated and tested with local fixtures | Actual native package installation, mounted-account match, 115 mutation/reconciliation, fonts and real video acceptance must be run on-device |
| Android Kodi 21 / Android 8+ | Profile-relative code and default IPC avoid `/storage` assumptions and AF_UNIX startup | Android filesystem permission behavior, process lifecycle, native ABI, renderer, background helper and real playback are unverified |

## Regression evidence

- Combined account/stream, runtime/engine, preparation, native subtitle-owner and
  portability selection: **300 passed** (Windows, 11.17s).
- Directory API shape/budget/identity tests: **9 passed**.
- New manual UI/provider, subtitle ABI path, and portable-host path selection:
  **73 passed** (Windows, 1.11s), including different native roots, fresh
  interpreter path agreement, no-key behavior, API-key separation from CDN
  requests, no signed URL persistence, account/manual-intent races, locks and
  immutable subtitle publication. Provider responses are local fixtures, not
  a live OpenSubtitles acceptance claim.
- Preparation regression cases were copied from the private prior baseline;
  only module names/import locations were retargeted. The exact-file selector
  is the same policy, moved into core rather than loading another addon's
  private namespace.
- No device action, CD2 mount/config edit, system upgrade, cloud submission or
  credentials migration was performed by this audit agent.

The main integration run owns inventory regeneration, the full-suite gate and
real native/device acceptance. See `optional-preparation.md` for deployment
requirements and the irreversible boundary of an already-transmitted remote
offline request.
