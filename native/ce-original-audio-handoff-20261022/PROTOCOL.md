# CE2038 original-audio and same-file transport handoff candidate

This candidate extends the currently installed F9 binary with a process-local,
one-use presentation capsule. It does not change firmware, codecs, resolution,
or the byte identity policy. Python must establish the complete selected file
identity before requesting capture; native additionally checks the old item's
exact file identity and the complete internal stream catalog at restore.

The ordinary initial open restores the reviewed native original-language
preference. A child carrying `bobitv.handoff_token` never creates an original
language plan: the capsule's current/manual stable audio key and delay win.

## API

`Player.BobiControl` retains its existing required fields:

`native_instance`, `user_intent`, `expected_sequence`, `selection_epoch`,
`command_id`, `action`.

For `action=handoff_capture`, also supply the old `request_id`,
`expected_subtitle_intent`, `expected_audio_intent`, and pre-generated
`child_request_id`. Capture does not stop playback. It requires the exact old
instance, current selection epoch, normal playback speed, no pause/menu,
seekability, current caching, and no pending user stream/seek/speed operation.

The actor publishes a receipt in `Player.BobiState.handoff` and includes the same
receipt in `OnBobiControl`. The queryable receipt survives destruction of the
old player. It includes `command_id`, `capture_command_id`, `token` (opaque
36-character native UUID), `child_request_id`, `expected_child_epoch`, parent
instance/request/epoch, intent counters, `position_ms`, `restorable`, `phase`,
and `reason`. External subtitle references never appear in the receipt.

For `action=handoff_stop`, send the same binding and `handoff_token=token`.
The selection epoch is still the old parent's epoch. The actor rechecks all
bindings, settings, stream catalog, external file contents, and caching. More
than 1500 ms of playback progress since capture rejects the handoff. The actor
captures the latest position and publishes `STOP_REQUESTED` before requesting
stop. Only its actual terminal reason `STOP` changes that to `STOPPED`.
`ERROR`, `NATURAL_EOF`, and `SUPERSEDED` invalidate the capsule.

Python must observe the real old-instance terminal `STOP` and then reserve the
pre-bound child request at exactly parent epoch + 1 using its existing authority
grant slot. A different reservation invalidates the capsule.

The new outer playback item must carry all of:

- `bobitv.request_id`: the bound child request UUID.
- `bobitv.file_identity`: exactly the old selected file identity.
- `bobitv.handoff_token`: the opaque native token.

A missing token for that bound child is rejected, including retries after
invalidation. A different ordinary open revokes pending handoff work. The token
expires 30 seconds after capture and can be consumed once. After consumption,
normal input/demux opening is allowed to take longer than 30 seconds; intent,
selection, and GUI return checks continue to apply before AV.

## Restoration and acknowledgement

Before initial stream selection, the child skips asynchronous database settings
loading, verifies the internal stream catalog, matches container stream identity
instead of reusing list indexes, reconstructs a verified external subtitle if
selected, and synchronously applies the complete `CVideoSettings`. It sets the
initial seconds-based resume before normal playback. Initial demux/subtitle seek
failure, stream mismatch, inaccessible external data, or revocation aborts before
claiming a successful restore. It never runs a later global seek or subtitle RPC.

The child's first `AV_STARTED` receipt carries `handoff_restored`,
`handoff_parent_instance`, `handoff_position_ms`, and `handoff_token`, with the
new native instance and child request. The global receipt changes to `RESTORED`
and contains the new instance plus `restored` fields for requested and actual
position, subtitle visibility, audio/subtitle delays, and the new instance's
selected indexes. An atomic final claim must succeed before the receipt is
announced. Manual subtitle/automatic-suppression counters and audio intent are
inherited by the child.

If the parent has `subtitle_file_applied=true`, capture requires its existing
`subtitle_file_sha256` to be a 64-character lowercase hexadecimal proof and
restores the pair together. This historical automatic-subtitle receipt proof
is distinct from the selected external file's current content hash; a later
manual subtitle choice or Off does not replace the historical proof. False
does not attach a hash to the child, and malformed true-without-proof state
rejects capture.

External subtitle capture accepts regular local files under `/storage` or
`/tmp`, verifies each path component without following symlinks, permits only
ext4/tmpfs, and hashes at most 64 MiB within a two-second read budget. Unsupported
network/FUSE/symlink references reject capture without stopping the old player.
IDX companions and the chosen external container stream are retained. The
contents are checked again before stop and restore.

## Build and validation boundary

`build_isolated.py` queries existing Ninja commands without invoking build
targets. It freezes candidate sources in each run, compiles five translation
units, regenerates the RPC schema, patches only copied archives, and links to
new output paths. The restored VideoPlayer layout adds PlayerCoreConfig.cpp as
a fifth rebuilt unit; all three header consumers are checked through depfiles.
Original sources, objects, archives, control files, and binary
are hashed before and after. The original stripped baseline is reproduced as
`8962740e718a7978acadbf2ae7ad55b0cd0742f6d0db162e9c1a1d8645ef834b`.

`tests/run_registry_test.py` compiles the actual capsule header together with
Kodi's actual `Variant.cpp` and `VideoSettings.cpp`. This verifies transactional
state behavior, not device playback. Device tests must still verify first AV
position, manual audio/delay, subtitle Off/internal/external/delay, stale-control
rejection, input failure, and ordinary playback before promotion.

## Responsiveness while the old transport is blocked

`BobiControl` only queues an actor message. It does not interrupt a synchronous
input read. `Process()` handles messages before `ReadPacket()`, whose demux read
can block in `av_read_frame` and the input file layer. With file caching enabled,
an empty cache can wait ten seconds inside `CFileCache::Read`. The FFmpeg read
has a twenty-second interrupt timer, but that timer does not forcibly interrupt
an already blocking file-layer call. Curl's default low-speed timer is twenty
seconds and its default retry count is two; runtime settings can change them.

Therefore a queued capture is not a promise of immediate execution. An
EAGAIN/EINTR return can let the actor reach the next message pass. A genuine
input/demux error can terminate the parent before that pass, in which case the
handoff is rejected. If data resumes first, the caching/progress checks reject
the late request. The candidate deliberately leaves this read path unchanged;
real BT stall responsiveness remains a device validation requirement.
