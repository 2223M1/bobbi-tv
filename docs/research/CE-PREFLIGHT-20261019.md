# CE deployment preflight, 2026-10-19

The initial read-only probes used the existing hash-pinned SSH transport. No
device files, services, playback, cloud tasks or credentials were changed by
those probes. The later controlled 1903 deployment is recorded separately below.

## Actual dependency finding and correction

Kodi reports `script.module.pycryptodome` **3.4.3**, enabled, from
`/usr/share/kodi/addons`. Shell Python 3.11.9 and the running Kodi/libpython3.11
are ARM32. Both system package names report library version 3.20.0.

The initial candidate failed actual P-256 signing: CE's
`Cryptodome.Signature.DSS` expects `Crypto.PublicKey.ECC.EccKey`, not the class
returned by `Cryptodome.PublicKey.ECC`. Merely importing the official namespace
did not establish interoperability.

The corrected helper probes P-256 generation, binary signing and verification
once under its initialization lock, selects one complete working namespace and
caches it. It prefers Cryptodome but falls back as a whole suite to Crypto.
After exposing a key it never switches namespaces for a missing module.
Probe keys exist only in memory and are not installation identities.

Actual CE selects **Crypto**, with P-256 signing/verification and AES passing.
A second fresh-module probe removes site-packages/Kodi addons from `sys.path`:
the exact-package loader still passes without widening the search path.
The native verification agent separately reports real Windows Kodi Python 3.8
selects **Cryptodome**, with P-256 and AES NIST checks passing.

Evidence: `review-evidence/ce-dependencies-preflight.json`. The record is
pre-deployment evidence, not proof of a running candidate service.

## State that the deployment controller must preserve

- Assrt's existing token is present and has the expected shape at
  `/storage/.config/am6b-subtitles283/assrt-token`; the new runtime reads
  `plugin.video.bobbi`'s profile `assrt-token`. The controller must migrate it
  locally; installers must not contain it. At probe time the target did not exist.
- Existing `ffprobe` and `font-tools/7zzs` both exist, are executable ARM32 files.
  `/storage/.kodi/media/Fonts` exists. The portable preparation capability takes
  these paths explicitly from its private `preparation.json`; it does not guess
  a new default. The target configuration was not yet installed at probe time.
- Preserve the previous metadata transport configuration unless direct operation
  has actually been established; the separate controller audit owns this check.
- Remaining core `/storage` literals are CE prepared-source path contracts and
  the exact-hash F9 subtitle ABI adapter. They perform no import-time storage IO.
  Windows empty-profile runtime tests do not load CE preparation/native owners.

## New-work playback proposals — not playback results

Preferred movie: **荒蛮故事 / Wild Tales / Relatos salvajes (2014)**,
TMDb 265195. The existing Juku shared cache contains a 46,527,152,128-byte ISO
named as the UK disc with DIY simplified/traditional effects subtitles. This
is only a catalogue/filename observation; neither playback nor subtitle content
has been verified. ISO exercises the disc route, not just a repeated MKV route.

Preferred anime: **少女终末旅行 / Girls' Last Tour / Shoujo Shuumatsu Ryokou
(2017), season 1 episode 1**. Alternatives: movie **一次别离 / A Separation
(2011)** and anime **灰羽联盟 / Haibane Renmei (2002), season 1 episode 1**.
These three were absent from the current shared-cache search, which does not
imply absence from Juku's main catalogue or other providers. Use normal source
selection; do not force a guessed media identity or lower quality for the test.

Exclusion check used `rg -l`, all corresponding Chinese/English/romanized names,
and JSON/JSONL/Markdown/log records beneath:

- `D:/AM6B-Project/AM6B/implementation`
- `D:/AM6B-Project/AM6B/audit`
- `D:/AM6B-Project/AM6B-review-ui-anirss-20261018/ui-redesign/review-evidence`
- `D:/AM6B-Project/AM6B-review-ui-anirss-20261018/ui-redesign/runtime`

No historical match was found for the four proposed works. This is absence
from the available recorded tests, not proof about unrecorded activity.
Previously exercised **乒乓**, **昭和元禄落语心中**, **别对映像研出手** and
**鬼魅浮生** were explicitly excluded after finding their prior evidence.
Read-only catalogue observations are in `review-evidence/ce-new-work-candidates.json`.
The root deployment controller alone owns playback and final acceptance.

## Executable namespace finding and 1903 controlled deployment

The first deployment attempt, run `20261019-172841`, failed before its service
transaction. Inspection found no deployment receipt or new profiles, both old
services still active and no runtime masks. It did not replace the native
player, firmware or running add-ons.

Its native check had resolved `/proc/PID/exe` and reopened the target pathname.
On this CE device that pathname in the calling mount namespace reads a different
inode from the executable actually running in Kodi. The proc reference hashes
to the expected F9 pin; the resolved pathname does not. 1903 hashes the opened
kernel executable object itself, with regular-file and bounded-size checks.
The exact F9 trust pin remains unchanged; this is not an allow-all ABI bypass.
The runtime uses the same exact-object check to choose the F9 subtitle adapter.

After freezing the corrected 21-component generation, run `20261019-174118`
deployed 1903 successfully. Its health probe confirms:

- `skin.bobbi.cinema`, Kodi active and old external preparation service inactive;
- subtitle ABI `ce-f9` and the exact expected native hash;
- host ready/native owner, preparation `RUNNING` and current account match;
- account-scoped prepared snapshot: 14 titles / 58 sources, plus 3 direct entries;
- no Python failure reported by that health snapshot.

The ordinary Wild Tales movie picker produced 15 source rows, while two provider
timeouts remained explicitly reported. A 35-second idle observation stayed in
manual selection without starting video. This establishes a working selection
boundary, not complete search coverage or playback/subtitle acceptance. Root
continues separate new-work playback and rollback validation.

Evidence: `review-evidence/ce-20261019-172841-inspect.json`,
`review-evidence/ce-20261019-174118-deploy.json`,
`review-evidence/ce-runtime-health.json`,
`review-evidence/ce-new-work-wild_tales-picker_wait-1792402763075366600.json`.
