# Optional preparation capability

The portable host starts without CD2, TorrServer, ffprobe, a proxy or a native
player. Share playback and account management do not depend on this feature.
The preparation implementation is now an explicitly configured **CoreELEC
capability**, not an imported Linux daemon or an unauthenticated socket bridge.

## Configuration and ownership

The host reads `special://profile/addon_data/script.module.bobbi.platform/preparation.json`
once at startup, only if that file exists. It must be locally provisioned; no
credentials, endpoint defaults or existing device configuration are shipped.

Required fields, all from the actual local installation:

| Field | Contract |
| --- | --- |
| `schema`, `enabled` | `1`, `true` |
| `cd2_endpoint`, `torrserver_endpoint` | Explicit IPv4 loopback HTTP origins |
| `cd2_token_file` | Local private CD2 token file; contents never in diagnostics |
| `account` | Existing CD2 legacy account-scope digest, not a substitute for UID proof |
| `destination` | Existing `/115open/…` preparation directory; no directory is created remotely |
| `ffprobe`, `download_capability` | Verified local probe binary and verified CD2 download API capability |
| `tmdb_api_key_file` | Local private metadata API credential file |

Optional fields: `cd2_login_file`; `tmdb_proxy`; `torrserver_pairing_file`;
`jackett_endpoint` + `jackett_api_key_file`; `font_tool` +
`font_native_directory`. Pairs must be configured together. Torrent pairing
must exactly match the configured origin. Nothing changes CD2 account, mounts,
system units, proxies, firmware or `newapi`.

State belongs under the `plugin.video.bobbi` profile:
`preparation/<hashed-account-id>-<epoch>/`. The prepared/direct projections stay
at `bobi-prepared.json` and `bobi-direct.json` and carry the current
`account_scope`. A different or unavailable runtime generation cannot advertise
those bytes as ready. Old epoch directories are retained, not deleted or
silently replayed. Existing private daemon state is not automatically imported.

Each incarnation has a separate OS file lease, retained until all IO and
SQLite handles close. A new host cannot write the same epoch while an old
process is draining. The old external preparation daemon must be stopped by a
reviewed deployment before enabling this capability; this module does not
operate arbitrary system services.

## Account and revoke protocol

The host is the sole account writer. An operation captures
`{account_id, epoch, authenticated}` before admission. Official 115 login UID
uses its numeric prefix; renewing that account's session preserves its epoch.
Logout writes a generation tombstone. A later login to the same UID is still a
new epoch.

The configured CD2 `/115open` root is read through the official schema:
`CloudDriveFile.CloudAPI` (field 9), `CloudAPI.name` (1), `userName` (2).
Only a strict numeric `userName` can be compared to the independent QR-login
UID digest. Nicknames, uncertain strings or legacy digest equality do not
prove identity. Every provider operation checks both that identity and its
local account generation. A mismatch admits no cloud work.

Account change synchronously closes admission and revokes the old lease.
`preparation ping` exposes `revoke.admission_closed` and `revoke.drained`:
the latter changes only after old IO and lanes close. The next incarnation
does not start before that drain. Pending old requests and late success results
cannot publish ready files, apply fonts, or start more cloud mutations.

A cloud submission already transmitted before revocation cannot be recalled.
Its durable submitting/uncertain record is preserved; shutdown never retries
it, deletes its cloud result or imports it into another epoch. The feature
does not claim that a remote offline task itself was cancelled.

## Preserved behavior

- One SQLite owner; one main provider-IO lane, independent bounded resolver,
  font-preflight and playback-protection lanes.
- Exact chosen release/episode and full media quality; no transcode, largest
  file guess or silent replacement release.
- Current/next exact preparation, optional next discovery, original durable
  uncertain-submit reconciliation, subtitles and existing ASS/font policies.
- Heavy subtitle extraction/font warming remains idle-only; cached font
  preflight remains available before AV startup, without hot skin/font reload.
- Public Juku catalogue refresh and renewable share HTTP stream ownership stay
  in the main host. This capability does not create a second ShareStream.
- `preparation-first-failure.json` records exception type and frame positions
  only, preserving the first failure without credentials or signed URLs.

## Validation scope

`tests/test_runtime_host.py` covers empty startup, owner-thread routing,
expired requests, conditional native stop and catalogue progression.
`tests/test_preparation_host.py` covers real numeric UID comparison, mismatch
and logout admission, drain ordering, same-account renewal, epoch isolation,
real empty Session initialization and late-result rejection.
`tests/private_baseline/test_subtitle_content_policy.py` checks the actual
native player/preparation host retains cached-font preflight and idle extraction.

Passing these tests is not live CD2, source playback, Android or native-device
certification. Deployment must check actual provider identity, observe a real
preparation/resolve cycle, and test account switching with an in-flight job.
