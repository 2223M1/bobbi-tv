# CE native lifetime and rollback review — 2026-10-19

Independent review by `candidate_unify`; production source was not edited by
this reviewer. Scope: the directory lifetime patch, isolated build evidence,
native overlay transition, and its ordering with the add-on rollback.

## Result

No remaining blocking finding in the reviewed changes. The first review found
that a lost transition acknowledgement could leave a `prepared` receipt or no
running Kodi process that the original rollback command refused to recover.
The revised controller closes that gap. This is a code/build/control-plane
review, **not real playback or power-loss certification**.

## Native change and build evidence

- `native/ce-directory-lifetime-20261019/Directory.patched.cpp` differs from
  `Directory.original.cpp` only by renaming the shared-pointer reference
  argument and retaining a local owning copy before the existing operation.
  Nested GUI message handling can no longer replace or clear this request's
  directory implementation through the caller's shared-pointer member.
- No decoder, audio, HDR/Dolby Vision, subtitle-rendering or playback-selection
  source change is present in this patch. The null-directory check is retained.
- The recorded build invokes source compilation only for the original/control
  `Directory.cpp` and patched `Directory.cpp`. It copies `filesystem.a`, replaces
  that object in the copy, and links to a new run directory. It does not invoke
  a general Ninja rebuild or overwrite the production source/archive/binary.
- Build evidence is in
  `native/ce-directory-lifetime-20261019/run-1792413397048752728/build-result.json`.
  Its builder and patched-source hashes match the files reviewed. Explicit
  linker input hashes and recorded build-control hashes were unchanged across
  the build according to that report; this review did not independently re-read
  the remote build tree.
- The reviewer independently hashed the three local output binaries:

| Output | SHA-256 |
| --- | --- |
| Baseline relink | `8962740e718a7978acadbf2ae7ad55b0cd0742f6d0db162e9c1a1d8645ef834b` |
| Original-source control rebuild | `8962740e718a7978acadbf2ae7ad55b0cd0742f6d0db162e9c1a1d8645ef834b` |
| Patched candidate | `d750a88c3dc041d17ea34d06e2b2ddadcf4db0f9fffdaaa727c8a6b7427f21d3` |

The build uses `-flto=4`. Therefore the supported claim is that production
audio/video source and existing input objects were not changed or separately
recompiled. It is **not** a claim that all final audio/video machine-code bytes
are identical: link-time optimization can operate across translation units.
The standalone `reentry_test.cpp` models reset/replacement/lifetime/null cases;
it is not an end-to-end Kodi crash reproduction.

## Deployment and rollback boundaries

Reviewed `tools/ce_native_update.py` and the native-order guard in
`tools/deploy_ce_remote.py`:

- Staging uses a dedicated `/storage/.local/share/bobbi-native/2026101908`
  directory. Apply checks staged hashes, the exact old running binary, old
  launcher/configuration/binary, compatible add-on generation and reviewed
  candidate hash before stopping Kodi.
- The change replaces only the named Kodi systemd drop-in and points its
  service-private read-only bind at the staged binary. Old overlay files are
  retained. No firmware, SYSTEM image, eMMC or host-wide mount-table write is
  present. The existing version-pinned launcher and system-fallback behavior
  are preserved; only its candidate hash is substituted.
- Configuration/receipt writes now use unique same-directory temporary files,
  file flush/fsync and replace; leftover names no longer block subsequent
  attempts. Directory fsync/power-cut durability is not claimed.
- Status tolerates an absent Kodi process. Rollback accepts `prepared`,
  `applied`, `rolled_back` and `recovered_after_failure`; it does not require a
  live new Kodi. It permits only the exact old/new configuration hashes and
  verifies the backup plus old launcher/binary before restoring. A responsive
  active player is rejected; an unresponsive process can be stopped for this
  explicit maintenance recovery. Restoration must pass the old binary and
  native-API readiness check before success is reported.
- New program deployment receipts record `native_before`. Program rollback
  refuses a different running native binary before stopping services or
  reverting add-ons. Restore the prior native overlay first, then the older
  add-on generation. Historical receipts without this field retain their
  previous behavior and are not retroactively certified by this guard.
- Exact reviewed native hashes select the existing CE subtitle ABI. The
  executable is hashed through `/proc/PID/exe`, not a resolved pathname from
  another mount namespace.

## Reviewed reapply extension (not yet device-certified)

The first controller intentionally rejected a second `apply`, even after a
confirmed rollback. `ce_native_update.py` now has an explicit `reapply` mode:

- Only a `rolled_back` receipt with `recovered: true` is eligible. Its old/new
  binary and configuration pins must match the immutable candidate inputs.
- The running old binary, old launcher, current old configuration and saved
  configuration are checked before any service mutation. The fixed candidate
  is pinned in the local driver, verified again from staged bytes, and must be
  explicitly recognized by the installed core. A generation at least 1908 is
  required; this permits a new 1909 generation after program rollback without
  lowering or deleting program state. Initial `apply` still requires 1908.
- Playback must be absent. Reapply uses the same stop/configure/start/readiness
  boundary and failure recovery as first apply. It never overwrites the saved
  old configuration. An interrupted prepared reapply can use normal rollback.
- Every transition preserves the preceding receipt as a history entry; earlier
  history entries are retained. No receipt, backup or generation state is
  deleted to permit a repeat operation.

The extension was authored by this reviewer after the independent review, and
needs the parent maintainer's review before device use. Its actual remote branch
is covered by **13 local simulations** (success, pin/configuration/backup/account-
independent generation guards, active playback, restart failure and interrupted
reapply). Together with the earlier three deployment/ABI files: **96 passed**.

## Minimal maintenance order and exact existing inputs

Do not attempt to reinstall the 1908 program bundle after rollback. Program
rollback retains the 1908 high-water sequence while restoring the 1907 component
version vector. The supported sequence is:

1. Stop the currently bound trial through its existing owner; check no active
   player. Save independent upstream/profile/account checkpoints.
2. Roll back native to the old `8962740...` binary while 1908 add-ons still run.
   Confirm native receipt recovery and runtime readiness. In particular,
   `runtime-paths.json.native_sha256` must have returned to the old pin before
   loading the old add-ons.
3. Roll back programs using **1908's frozen run `20261019-205008`**, not 1907's
   install run. Inspect the receipt: high-water sequence remains 1908, component
   versions must match `program_before`. Check runtime/account/upstream state.
4. Stage and upgrade a newly signed **1909** program generation under a new run
   ID. It must include the reviewed 1908 fixes and recognize the candidate native
   pin. Do not use `deploy`, re-run migration, or replay the old 1908 package.
5. Verify the old native plus new add-ons are ready, then explicitly `reapply`
   the unchanged native candidate. Recheck native hash, runtime and upstream
   preservation. This is not literally a 1908 program sequence round trip.

PowerShell inputs, from the candidate repository (commands are checkpoints, not
an unattended all-in-one script):

```powershell
$cePython = 'D:/AM6B-Project/AM6B-B-FULL-execution/20260908-115110/venv/Scripts/python.exe'
$ceTransport = 'D:/AM6B-Project/AM6B-review-ui-anirss-20261018'
$ceNativeBuild = 'native/ce-directory-lifetime-20261019/run-1792413397048752728/build-result.json'

& $cePython tools/ce_native_update.py --transport-source $ceTransport --build-result $ceNativeBuild --mode rollback
& $cePython tools/ce_native_update.py --transport-source $ceTransport --build-result $ceNativeBuild --mode status
& $cePython tools/ce_runtime_probe.py --transport-source $ceTransport --mode health --report review-evidence/ce-native-rollback-before-program1907.json

& $cePython tools/deploy_ce_candidate.py --transport-source $ceTransport --mode rollback --run-id 20261019-205008
& $cePython tools/inspect_ce_deployment.py --transport-source $ceTransport --run-id 20261019-205008
& $cePython tools/ce_runtime_probe.py --transport-source $ceTransport --mode health --report review-evidence/ce-program-rollback1907-native-old.json

# Only after the 1909 bundle has actually been built, signed and checked:
$ceRun1909 = Get-Date -Format 'yyyyMMdd-HHmmss'
& $cePython tools/deploy_ce_candidate.py --transport-source $ceTransport --mode stage --run-id $ceRun1909 --bundle dist/private-releases/bobbi-private-2026101909-coreelec.bobbi-update.zip
& $cePython tools/deploy_ce_candidate.py --transport-source $ceTransport --mode upgrade --run-id $ceRun1909

# Only after 1909's runtime checks succeed on the old native:
& $cePython tools/ce_native_update.py --transport-source $ceTransport --build-result $ceNativeBuild --mode reapply
& $cePython tools/ce_native_update.py --transport-source $ceTransport --build-result $ceNativeBuild --mode status
```

Checkpoint reports are create-once: use a fresh report filename for a later
attempt, never overwrite failed evidence. A lost tool response is not proof of
remote failure; inspect the existing receipt before repeating a mutation.

### What program rollback does not restore

`plugin.video.jacktorr` and `repository.jacktook` are absent from the full
22-component inventory and the controller's three `OLD_IDS`. Neither their
files nor their installed database rows are targets. The original JackTorr
1.2.2 / `repository.jacktook` origin observed in
`review-evidence/ce-upstream-restored1908.json` must therefore remain rather
than restoring the old fork. Restart-time behavior and concurrent Kodi updates
still need before/after observation; inspect the content hash, version, origin,
enabled state and existing TorrServer ownership/PID rather than assuming them.

The update engine restores only its 13 owned program directories. Controller
rollback restores recorded enable/disabledReason rows and only skin/soundskin
GUI choices, not a complete Addons33 database or guisettings backup. It does not
invoke `migrate_profiles`, replace account/profile files, restore old cloud
credentials, delete the torrent connection profile or roll back viewing data.
Thus a whole-box/profile backup restore is neither needed nor appropriate.

## Independent checks

- `test_subtitle_runtime_paths.py`, `test_ce_deploy_controller.py` and
  `test_portable_host_paths.py`: **83 passed** on the revised controller.
- An in-memory harness executed the actual parsed remote rollback branch for
  all four accepted receipt states, each with old/new configuration and no
  responsive JSON-RPC: **8 cases passed**. It performed no device/file writes.
- Related subtitle/preparation review: **163 passed** across CE parity,
  preparation host, share subtitle/reference, prepared-scope and external-owner
  tests. Ready prepared subtitles now retain account scope through the cached
  lookup; a logout before final application rejects the old result. Lost
  preparation receipts query status, with resubmission only after matching
  explicit absence. The final account check is immediately before native
  submission, not a lock held across a potentially blocking native call.

No device deployment, restart or media trial was performed by this reviewer.
