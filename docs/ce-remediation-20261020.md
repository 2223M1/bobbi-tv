# AM6B CE remediation — 2026-10-20

Branch: `codex/ce-am6b-remediation-20261020`; base `f1495ef` (code `cdf0c48`).
Independent candidate worktree; original dirty personal project is untouched.

## Authority and boundaries

- CE / AM6B Plus only; no sub-agents this round.
- User explicitly permits device operations this round, superseding the Web
  bundle's older device pause. Deployment follows local regression and backup.
- Preserve original quality/audio, manual source selection, new UI, fonts,
  sound effects, manual subtitle intent and strict same-edition continuation.
- No firmware, SYSTEM, eMMC, CD2, mount, Yatse, VPS/newapi/proxy changes.
- GitHub delivery was initially deferred. The user subsequently requested a
  private GitHub push for Web review; see `CE2006-WEB-REVIEW-20261020.md`.
- TMDb project application was approved after the user confirmed personal,
  non-commercial use and accepted the terms. The user submitted contact details.
  The project key was imported locally without copying a login session/password;
  it is ignored by Git and is intended for the private client bundle. Catalogue,
  warmup and optional preparation use that application configuration first.
  This is not yet China-direct or clean-install certification.

## Gates (open until evidenced)

1. Shared filename semantics; Web 18-case before/after and actual call chain.
2. Opt-in bounded progressive ShareStream with block-mode fallback; real HTTP.
3. BT add reconciliation, bounded diagnostics and explicit wait/return choices.
4. Manual real-file confirmation, terminal handling and continuation guards.
5. CE clean-install / optional BT / project metadata configuration.
6. Exact program backup, device same-file comparison and new-work coverage.
7. One final receipt separating tests, device evidence and unverified gates.

The Web transport model is not a throughput test. Unit tests are not playback
certification. Keep first failures and never restore account/watch databases as
part of program rollback.

## Implemented before device deployment

- Unified filename semantics now distinguish resolution/codec fields from
  season/episode identity. The unchanged Web counterexamples improved from
  13/18 to 18/18; actual selectors, release families and subtitle matching use
  the same parser. Historical uppercase family-key bytes remain unchanged.
- Progressive ShareStream is opt-in, with an 8 MiB bounded queue, distinct
  received/queued/delivered offsets and a separate cap of six producer threads.
  Reads use public urllib3 `read1`, finite network timeouts and bounded retries.
  Block delivery remains the default. A provider stalled inside its own resolver
  is not claimed to be instantly cancellable; occupied producer slots remain
  counted. No file transcoding or quality reduction is introduced.
- BT add receipt loss first reconciles the same torrent hash. Real metadata
  supports explicit user file confirmation followed by metadata rechecks;
  `USER_CONFIRMED_FILE` cannot become cloud-preparation or same-release next proof.
  Paths and explicit wrong work/year/episode remain rejected.
- Abnormal terminal events retain real resume progress. Only native natural EOF
  completes a new exact-play record. The instance-local terminal menu offers
  manual reselection/episodes, cannot automatically play, and yields to a newer
  request. A rejected continuation no longer suppresses the menu merely because
  a candidate was cached. Trakt/Simkl receive pause instead of completed stop
  after abnormal endings; legacy records are not mass-rewritten.
- Setup includes TMDb official attribution/logo and transmission-mode fallback.
  The application config is a separate ignored build input, canonicalized and
  bundled only after validation, with a digest-only build receipt. Clean source
  tests do not require the maintainer's key. The historical diagnostic builder's
  dependency closure now includes the core and its original Python dependencies.
- `clean-install` reuses the signed program transaction, requires empty own/old
  cinema state and the reviewed native host, preserves Kodi-owned dependencies,
  and never reads retired account/CD2 configuration. It touches only Kodi's
  service; optional preparation and BT are absent. See the separate clean-install
  guide. Tests are not an actual blank-device installation certificate.

## Regression receipts retained

`regression-first.xml` and `regression-second.xml` retain intermediate failures.
`regression-third.xml`: 2461 passed, 6 skipped, one genuine failure in the old
diagnostic ZIP dependency closure. This was repaired in the builder, not hidden
by disabling the test. Final full regression and device evidence follow below.

New-work candidates for this round are Coherence (TMDb 220289, TMDb release year
2014) and ODDTAXI (TMDb 116727, 2021 S1E1). Their identities were checked with the
project application API; prior acceptance documents/evidence contain neither.
Absence from a local shared-cache query is not proof of no available source.
Flip Flappers and Tokyo Godfathers may be reused only as old-defect regressions.

## Device findings and follow-up fixes

The first actual upgrade was generation 2026102001, run 20261020-134012.
The original F9 binary remained `8962740e718a7978acadbf2ae7ad55b0cd0742f6d0db162e9c1a1d8645ef834b`.
The 13 owned components were installed, with all nine upstream dependencies
retained under their own IDs/origins. Ten profile sentinels were unchanged.
115 remained authenticated at epoch 1; the preparation host and existing
TorrServer MatriX.144.1 were ready. Old standalone preparation is disabled;
the new resident host owns it. No CD2/mount/Yatse/VPS changes were made.

Dedicated TMDb application configuration returned HTTP 200 from the device in
about 0.8 s using an opener with no explicit proxy. This is **not** proof that
the home router/ISP has no transparent routing. It does not certify every
Chinese network. No TMDb password/session is included in the component bundle.

### Previously untested works

| Work / exact version | Original block mode | Opt-in progressive mode |
| --- | --- | --- |
| Coherence, 15.6 GB 1080p MPEG-2 / DTS-HD MA | Select→observed AV 9.394 s. Startup clock held while decoder progressed (no caching); initial observation fails. Later 30 s stable. | Same source/native, 4.545 s. About 34.5 s startup observation without caching/drop/hardware error; middle seek and subsequent 30 s passed. |
| ODDTAXI S1E1, 4.23 GB JPBD Remux / Japanese FLAC | Same-file A/B, 8.137 s. Real early caching plus startup clock anomaly; initial observation fails. Later 30 s stable. | 7.175 s; real early caching around 10 s, stationary decoder about 8.5 s. Not passed. |

Both used automatically enabled embedded Chinese subtitles. Coherence's audio
track has no language metadata, so original-language listening is not certified.
The ODDTAXI track explicitly reports Japanese. No quality reduction was made.
Coherence manual subtitle off/on retained intent on the same native instance.
Evidence is in the timestamped `ce-new-work-*`, `ce-operator-*` and
`ce-playback-log-*` JSON files. Original failures are retained. Single-run A/B
has CDN/cache/network confounders and is not a universal performance claim.
The device has been restored to **block** mode; progressive stays opt-in.

### Two defects revealed by actual playback

1. `S01E01-[1080p][JP.BD.Remux][group]` was refused by the legacy catalogue
   envelope's episode-title prose guard. Decorated cases now fall through to
   the existing strict full-family comparison, retaining group, edition, quality,
   container and standalone revisions. Real direct-provider and Juku SQLite
   chains have positive/negative tests. Ordinary episode-title prose behavior
   and old identity keys are not rewritten.
2. Flip Flappers' observed same-torrent `.SweetSub-SC.ass`/`.SweetSub-TC.ass`
   filenames were missed despite exact video-stem matching. A declared release
   group plus language suffix is now recognized; unrelated groups, different
   cuts, forced/commentary markers, wrong episodes and duplicate best candidates
   remain ineligible. Actual text still passes content/metadata validation, not
   filename-only proof. The existing generic matcher is reused by live and
   preparation consumers, with no per-title exception.

Flip Flappers' 40-file BT pack now selected actual file 3 / 411570230 bytes;
about 25.7 s to AV (about 21.5 s in real BT buffering with 3 peers). Startup
bounded observation and later 30 s passed with no dropped/hardware error.
That first attempt had **no Chinese subtitle** and is not an overall success;
it is the evidence that motivated fix 2. It is an old-work regression, not
additional new-work coverage.

### Frozen generations and local verification

- 2001: first device upgrade; complete local regression 2464 passed, 6 skipped.
- 2002: signed and staged at run `20261020-141008`, **never installed**. Contains
  the bracketed continuation fix; 2480 passed, 6 skipped. Kept as evidence.
- 2003: adds sidecar compatibility, core 0.1.8; 2488 passed, 6 skipped and
  4 subtests passed (`regression-2003.xml`). One JUnit property-format warning.
  Other component versions are unchanged from 2001. 22-component signed bundle,
  1384 files, 95,977,113 component ZIP bytes. Actual extraction, wrong platform,
  damaged signature/member and missing-member checks passed.

Maintenance tools are not production control paths. Standard seek/subtitle
operator checks are explicitly non-atomic and bracketed with ownership checks.
The first invalid test seek was corrected after reading Kodi's real RPC schema;
no hidden retry or production seek change was made. A missing source-card
selection now returns NOT TESTED instead of a successful CLI exit. Full raw
records remain separate from bounded console summaries.

### Upgrade-state regression, not a cache wipe

2003 installed successfully at run `20261020-141423`. Existing preparation had
completed the exact Flip Flappers E1/E2 cloud files, so the ordinary picker
correctly exposed 115 and suppressed the corresponding BT pack. E1 selected
to AV in 2.957 s with 36.9 s of positive continuous startup observation,
full-screen 1080p HEVC and no hardware/drop error. However it had no subtitles:
the earlier matcher had durably stored `NO_EXACT_SIDECAR` with no policy version.
Read-only, current-request-bound SQLite evidence is
`flip-prepared-negative-bound-2003.json`. Fixing matching alone did not revisit
this old negative, so 2003 is not claimed as subtitle acceptance.

2004 adds a matcher-policy marker and revisits only older `NO_EXACT_SIDECAR`
records on the existing one-at-a-time idle preparation lane. Same-policy
negatives do not spin; successful records, manual revisions, identity failures
and exhausted network reads are not reset. This does not create cloud tasks,
replace video mappings or clear the library. Targeted preparation/matcher tests:
24 passed, including old-negative upgrade, no-spin and manual-preservation cases.

In the 2003 same-file regression, seeking near E1's end produced a genuine
`NATURAL_EOF`, then `NATURAL_EOF_SAME_VERSION_HANDOFF`, followed by a new exact
E2 request. The next episode was foreground/fullscreen, original 1080p HEVC,
and uncached-stall-free at the bounded observation points. It was explicitly
stopped by its newly observed native instance. This establishes continuation,
not subtitle success, and does not count as another new work.
The first successor probe expected the old terminal to remain in live memory;
the actor correctly retires it on child start. That incomplete probe is retained.
The revised probe reports live and ordered-log evidence separately and checks
TMDb/season/episode plus exact native owner before any attended stop.

2004 local full regression: **2490 passed, 6 skipped, 4 subtests passed**.
One JUnit property-format warning remains. It is installed via
`20261020-142257` with core **0.1.9**. The signed ZIP is
`dist/private-releases/bobbi-private-2026102004-coreelec.bobbi-update.zip`,
SHA-256 `a7348cd82dfb3a34cbd35e584bb0c58c031a5b4c687b6098ed73ff3af229f3eb`.
Actual bundle extraction and tamper/profile/member negative checks passed.
`ce-20261020-142257-inspect.json` confirms all ten profile sentinels and nine
upstream dependencies preserved. Current legacy JackTorr is still
`1.2.2+am6b.317`; it is **not** claimed to be a newly installed upstream original.
Existing engine MatriX.144.1 and native F9 remain unchanged.

### 2005: evidence-led subtitle and RAR font compatibility

The 2004 idle retry exposed a second, independent first-episode failure. Exact
cloud task/file mapping fetched only the 417001-byte SC subtitle, SHA-256
`fa055b54bd5cc16fdfef97939b8bcfb70705aba9a261426c9d6df0cf00a7fec4`.
One ASS event runs from `0:09:12.88` to the same timestamp; no reversed event
was present. The old evidence projection rejected the whole subtitle. The
projection now skips invisible zero-duration ASS events, leaving the original
bytes/styles intact for libass; malformed/reversed timestamps remain rejected.
Only legacy exhausted `ValueError` records may receive one policy-versioned
retry cycle. Network/account failures, successful/manual bindings and identity
rejections are not reset. Failure receipts now identify the bounded stage,
without URLs or exception contents. No cloud task or video mapping is recreated.

The same release contains a 47296835-byte RAR5 font archive, SHA-256
`0cdf357b08a3e48d0664a6afe6e382ccf3bc9b54dd24209c83d7a6d872efa1be`.
The pinned existing 7-Zip supports RAR, but asset selection omitted `.rar`.
Actual extraction also found a parser bug: stripping whitespace from the final
empty `NT Security = ` property made the listing invalid. RAR selection and
empty-field parsing are fixed; copy links, alternate streams and split volumes
are explicitly refused alongside existing path/link/encryption/budget checks.
The same helper and process/memory/time budgets remain. An isolated device
candidate decoded **7 font files in 1.66 s**, without activating them or replacing
the installed program. This establishes decode compatibility, not screen style.
Old `NO_RELEASE_FONT_ASSETS` failures receive a one-time asset-policy recheck.

2005 is core **0.1.10**, installed under run `20261020-143900`. The post-upgrade
receipt confirms original F9, all ten profile sentinels and all nine upstream
dependencies preserved. Package:
`dist/private-releases/bobbi-private-2026102005-coreelec.bobbi-update.zip`.
Actual updater extraction and wrong-platform/tampered/missing-member checks
passed: 22 components, 1384 files, 95,977,744 component ZIP bytes.
Raw diagnostic failures and the successful candidate decode are retained in
`review-evidence/ce-20261020/`, not replaced with success-only reports.

2005 regression is split into explicit scopes: `tests/` **2467 passed, 6
skipped**, build-bootstrap **8 passed and 4 subtests**, packaging **33 passed**;
total **2508 passed, 6 skipped, 4 subtests**. The latter two are local regression
checks only, not resumed Android/Windows builds or device certification. One
JUnit property-format warning remains. A separate 47-test post-tool-edit check
passed and is not added to the unique total. Signed package validation ran
against the actual ZIP, not a simulated artifact.

### Final program generation 2006

The real RAR contains no matching faces for the ASS requirements `Arial` and
`0`. Under 2005, five matching font files were prepared but the all-or-nothing
activation gate rejected them too. 2006 activates only matched, verified inputs
while preserving normal libass fallback for missing families. It does not alter
ASS bytes/fonts or relabel incomplete coverage as complete. Existing per-request
guards, hardlink checks, cancellation rollback, user-font preservation and cache
leases still apply; zero matched inputs remain ineligible. Preflight receipts
explicitly carry `inputs_complete=false` and `missing_count=2` for this sample.
The real ledger/store/cache/preflight regression includes cancellation.

Installed: **2026102006 / core 0.1.11**, run `20261020-144700`.
Bundle `dist/private-releases/bobbi-private-2026102006-coreelec.bobbi-update.zip`,
95,987,479 bytes; SHA-256
`e67860a890a5fdce75ab20ce4c0913ec7c29e1d649c5fe26e9bb740da54a3e57`.
22 components / 1384 files; actual unpacking and signature/platform/tamper/member
negative checks passed. Original F9, ten profile sentinels and nine upstream
dependencies were preserved. Full `pytest` discovery: **2512 passed, 6 skipped,
4 subtests passed**, one JUnit property-format warning (`regression-2006.xml`).
At device acceptance, no GitHub commit or push had been performed. Subsequent
user-authorized review delivery is recorded separately in the review entrypoint.

Final Flip Flappers E1 same-115-file regression: selected to AV **3.54 s**, then
**35.99 s** of continuous positive-time observation with no observed caching,
clock discontinuity, drop or hardware error. Native receipt confirms application
of the exact `fa055b…` SC ASS; current-request font activation confirms five
font files with two missing families honestly retained. Font preflight took
about **0.65 s**. Both manual subtitle off and on stayed in the same playback
instance for their 12-second checks and were not overridden. These establish
machine-visible loading/control, not translation timing or television appearance.
Evidence: `flip-live-font-2006.json`,
`ce-new-work-flip_flappers-select-1792479207815240000.json`, and the off/on
operator receipts. This is an old-work regression, not new-work coverage.

The final 2006 run also established E1 natural EOF → same-release 115 E2 in
foreground fullscreen. E2's exact external Chinese ASS was applied (SHA-256
`02b0c76a450599e7b77b3f4314baa02ea6a075ae3c9b679d7c489f88fc0c3906`),
with original 1080p HEVC and no caching at the recorded 33–53 s and 88 s
observation points. The child was then stopped by its observed native instance.
Evidence: `ce-continuation-flip_flappers-1792479373354999600.json` and
`ce-continuation-flip_flappers-1792479408506280400.json`.

Final handoff health (`ce-20261020/final-health-2006.json`) records no active
players, the cinema home window, generation 2026102006, authenticated account
epoch 1 and a ready preparation host, with no recorded Python failures. The
legacy standalone preparation service remains inactive by design; the new host
owns preparation. Playback trials are finished and the box is available to the
user. This health snapshot is not an additional physical audio/visual acceptance.

ODDTAXI same-file attempt 3 (2005, before the independent font activation change)
proved E1 natural EOF → exact E2, JPBD 1080p H.264 / Japanese FLAC / Chinese
subtitle, foreground fullscreen. Bracketed-release continuation is now device
evidenced (`ce-continuation-odd_taxi-1792478953920030600.json`). E1 startup still
had a ~3 s clock anomaly and E2 initial caching was observed. It is **not** a
no-buffer playback pass. The child was explicitly stopped by its current native
instance. Block remains selected; no lower-quality source was substituted.

One 2-second account-status diagnostic timed out during idle font preparation;
the next read returned the same authenticated epoch and ready host. The raw
failure is retained in `idle-subtitle-font-2005-second.json`; it is not presented
as permanent account loss or silently omitted.

### User-reported subtitle bottom clipping

The user reported clipping on multiple works in yesterday's deep customization.
Read-only inspection found normal view mode, zoom 1.0, pixel ratio 1.0, vertical
shift 0 and no Kodi overscan crop for the active 1080p mode. F9 uses its custom
`Align::ORIGINAL` value 5; this was confirmed against the exact local F9 source,
not misdiagnosed using upstream's older 0–4-only settings list.

An attended, reversible **device preference** adjustment increased
`subtitles.marginvertical` from **4.95% to 7.5%**. Font, size, gray color,
alignment, ASS overrides, PGS mode and video framing are unchanged. The prior
value and readback receipt are stored at
`/storage/.local/share/bobbi-private-trials/20261020/subtitle-margin-1792479127599398658.json`
and locally in `subtitle-margin-1792479128057880100.json`.
This is a regular/adapted text safe-margin mitigation, **not a proven root-cause
fix for every ASS/bitmap subtitle or TV-side overscan**. Native positioned ASS
and PGS layouts were deliberately not flattened or resized. Physical TV
confirmation remains required. To undo just this preference while idle, use
Kodi's `Settings.SetSettingValue` for `subtitles.marginvertical` with `4.95`;
do not restore a whole `guisettings.xml` or profile over later user changes.

## Deliberately unverified / not promoted

- Blank-device install and rollback on a separate empty device; this existing
  machine was upgraded, never cleared to simulate a new user.
- Second real 115 account switching, physical TV audio/visual inspection,
  HDR brightness and subtitle timing/style appearance. Machine observations
  are separate from a viewer's confirmation.
- Progressive transport's universal superiority: real ODDTAXI cold-start
  buffering occurred in both modes, so block remains selected. No alternate
  lower-quality source or artificial pass threshold was used.
- The native directory-lifetime candidate is **not** reapplied. This round's
  observed repair and comparison use the original F9, avoiding an unmeasured
  native change. Prior independent build/code review is not playback acceptance.
- Android/Windows remain out of this round's scope. The subsequent authorized
  GitHub delivery does not merge main or promote a stable release. Work is in
  the independent candidate tree; the original dirty project is untouched.

## Program recovery (only if needed; not executed as part of handoff)

First stop the explicitly current owned playback and inspect the current
generation, native pin and frozen deployment receipt. Run from this worktree:

```powershell
$cePython = 'D:/AM6B-Project/AM6B-B-FULL-execution/20260908-115110/venv/Scripts/python.exe'
$ceTransport = 'D:/AM6B-Project/AM6B-review-ui-anirss-20261018'
& $cePython -X utf8 -B tools/deploy_ce_candidate.py --transport-source $ceTransport --mode rollback --run-id 20261020-144700
& $cePython -X utf8 -B tools/ce_runtime_probe.py --transport-source $ceTransport --mode health --report review-evidence/ce-20261020/recovery-new-checkpoint.json
```

This exact rollback restores 2005's program vector, not an old account/watch
database. Do not replay 2002's staged-but-never-installed run. To undo earlier
program steps, inspect each predecessor receipt and roll back in reverse order:
2006→2005 using 144700, 2005→2004 using 143900, 2004→2003 using 142257,
2003→2001 using 141423, then the initial upgrade using
134012. Retained high-water generations and current-native guards apply; do not
delete state files to bypass them. Account/media/watch changes made since
upgrade remain. Whole-box backup restoration is unnecessary and out of scope.
