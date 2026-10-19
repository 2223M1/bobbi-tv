# Windows real-playback loading-window retirement defect

## Scope and result

Isolated actual Windows installer 2026101903; visible user-authorized test window.
The installed portable validation profile has separate user settings and retained
authenticated account state. No QR/login exchange, CE mutation, resolution/audio
change, or reduced-quality video substitution was performed in this investigation.

One newly selected work: *A Separation* (2011), TMDb 60243. Repeated attempts of
the same file below are **one work plus bug regressions**, not new-work coverage.
File: `A.Separation.2011.BluRay.1080p.x265.10bit.2Audio.MNHD-FRDS.mkv`.
Source key: `3aa51fbc82c49da139c25741d4064028220884892aaeb538f330b1ae02888041`.

The first hidden-desktop and second visible-desktop attempts reached HEVC decoding,
original Persian AC3 audio, and Chinese subtitles but cancelled after an unconfirmed
fullscreen handoff. These are failures, not passes.

## Exact observed cause

Temporary diagnostic-only native logging preserved the fullscreen guard's order
and predicates. It showed `MODAL_PRESENT`, not a generation/identity mismatch:

```text
18:04:04.077 reason=MODAL_PRESENT expected_generation=11 actual_generation=11
expected_gui_intent=0 actual_gui_intent=0 expected_epoch=1 actual_epoch=1
active_window=10000 top_modal=13001 nonclosing_modal=9999

18:07:23.106 resolver_init dialog_id=10138 modeless=True
18:07:25.583 resolver_started dialog_id=10138 modeless=True context=True current_dialog=13001
18:07:25.602 resolver_tracking tracked=False
18:07:25.643 reason=MODAL_PRESENT ... top_modal=13001 nonclosing_modal=9999
```

`9999` is Kodi's invalid window ID. During `onInit`, Kodi's busy dialog 10138 was
still topmost; the resolver recorded that other window's ID. The real resolver was
13001. It then asked the resident to track the wrong window, and the resident
correctly rejected that token mismatch. Waiting for the already-gone busy dialog
released the loading lease too early, while the real 13001 was still animating
closed. Native correctly refused to force fullscreen over a modal window.

## Minimal repair

Only the resolver frontend changes: accept a visible dialog ID if its
`AM6B.ResolverToken` matches this exact registered window; recheck immediately
before retirement; require the resident's owned-window tracking receipt; then
wait for that exact window to disappear before releasing its lease. The resident
continues checking request/native instance/selection epoch/GUI user intent.
No native predicate, arbitrary-generation retry, or unknown-modal bypass is added.
Tracking failure or unidentifiable window fails closed instead of granting handoff.

Ten executable method-level regression cases pass, covering the busy-overlay
reproduction, wrong token, hidden window, lost request/context, cancellation,
rejected resident receipt, bounded retirement timeout, and unknown user modal.
See `tests/private_baseline/test_resolver_window_retirement.py`.

## Actual repaired regression

```text
18:09:17.347 WINDOW_CLOSE OWNED_LOADING_VISIBLE
18:09:17.554 REQUEST CONDITIONAL_NATIVE_COMMAND
18:09:17.555 native active_window=12005 confirmed=true
18:09:17.606 CONFIRM NATIVE_INSTANCE_RECEIPT
```

Actual 40-second selection trace:
`windows-new-work-select-1792404594433948900.json`.
At its end: playback time 36.676s, 12005 fullscreen, 1920×1038 HEVC, Persian AC3
3.0 448kbps, Chinese subtitle index1 enabled, no observed clock stall/discontinuity
or sampling gap. Follow-up inspection at 70.292s still had the same fullscreen
player/streams; another 30-second observation is separately retained:
`windows-new-work-observe-1792404685729953400.json`.
Identity-bound stop succeeded and launcher exited 0.

These Windows clock/native/stream receipts do **not** prove continuous displayed
frames; the harness has no Windows rendered-frame counter. This is also not an
Android hardware test or CE handoff acceptance.

## Honest unsuccessful observations

- Attempt5 failed before AV with `STREAM_UNAVAILABLE` / HTTP503. Retained in
  `windows-new-work-select-1792404380336864300.json`; not attributed to fullscreen.
- New anime *Haibane Renmei* (2002), TMDb34164 S1E1, searched through the ordinary
  source UI but returned 0 cards and one failed/timed-out source. No anime playback
  was selected or certified. Initial harness `FIRST_CARD_NOT_OBSERVED` was an
  empty-result diagnosis, not a confirmed navigation fault.

## Diagnostic cleanup

Temporary resolver/native diagnostics were removed. Installed test native restored
to the frozen1903 executable, matching SHA256
`bc1626732359eaa267fb76abcef8ad64b889107de68b2ac7b40375ff1cb1ae9b`.
Native source restored to the original canonical patch; a clean non-diagnostic
Release relink follows before final1905 packaging. The fixed resolver remains in
the source component and will be part of the newly frozen inventory, not silently
inserted into the historical1903 release artifact.

## Subsequent 1905 investigation and bounded discovery repair

The clean frozen1905 installer had one further early failure: target video was
observed at 18:29:32.407 and fullscreen was denied at 18:29:32.449, without a
`WINDOW_CLOSE`, `REQUEST`, or `CONFIRM` stage. Its exact branch was not captured
and remains **unproven**. Do not equate this 42ms failure with an upstream network
problem, a native generation mismatch, or an insufficient AV delay. The actual
playback predicate already requires observed AV. Two subsequent logging-only
regressions passed; that is not an explanation of the preceding failure.
Failed frozen trial: `windows-new-work-select-1792405808708910300.json`.

Source review identified a separate provable hole in topmost-plus-cached-ID
discovery: if Kodi's busy overlay covers the resolver at both observations, no
owned resolver ID is found. Kodi21.3 explicitly reserves Python window IDs
13000..13099 (`xbmc/windows/WindowIDs.h`); the Python API exposes the topmost
modal, not this dialog's own protected native ID. The resolver now scans exactly
that bounded namespace and requires **one visible matching registered token**.
Duplicate visible ownership fails closed. The resident still independently
checks token/request/epoch/intent ownership before tracking closure.

An initial experimental scan incorrectly constructed `xbmcgui.Window(id)` for
empty slots. On the actual Windows host this produced the native exception
`Window id does not exist`, aborted the Python invocation and left shutdown
stuck. That regression is retained in
`windows-new-work-select-1792406765413113800.json`; it is **our experimental scan
failure**, not evidence about the original42ms failure. After `Application.Quit`
returned OK but did not finish shutdown, only the validated isolated launcher
PID2888 was terminated; its job ended KodiPID32848. No unrelated Kodi or CE
process was stopped. Watcher exit4294967295 is an unsuccessful forced exit.

The corrected scan uses read-only `xbmc.getCondVisibility` and
`xbmc.getInfoLabel`, never `Window(id)` construction. Tests reject any attempted
wrapper construction and verify the official100-slot bound. Fixed reason-code
warnings distinguish discovery ambiguity/miss, selection loss, tracking refusal,
retirement timeout and lease refusal; no raw exceptions or credentials are logged.

The safe-label resolver was copied only into the isolated1905 test install;
native/core/service bytes remained frozen1905. Actual attempt5:

```text
18:53:04.856 WINDOW_CLOSE OWNED_LOADING_VISIBLE
18:53:05.062 REQUEST CONDITIONAL_NATIVE_COMMAND
18:53:05.104 CONFIRM NATIVE_INSTANCE_RECEIPT
```

`windows-new-work-select-1792407220410233700.json` records40seconds, with71
positive AV samples spanning35.078seconds, no observed stall/discontinuity/gap,
fullscreen12005,1920×1038HEVC,Persian AC3 3.0 448kbps and Chinese index1 enabled.
Its installation receipt explicitly lists `resolver_window.py` as an overlay;
this is **not frozen1905 or final1907 playback acceptance**. Repeated attempts
remain regressions of one work, not additional new-work coverage.

Follow-up `windows-new-work-observe-1792407264935149800.json` has31positive AV
samples spanning32.906seconds (playback47.223→79.936seconds), with the same
fullscreen12005 and no observed stall/discontinuity/gap. Identity-bound stop
succeeded in `windows-new-work-stop-1792407294817404900.json`; graceful quit then
completed with launcher exit0. No continuous rendered-frame guarantee is inferred
from clocks.

The resolver and authority suites have91passing cases. Together with24Android
repackaging transition cases, the targeted run has115passes. The Android guard
still rejects inventory changes by default. Its sole explicit opt-in permits
21→22 with only `plugin.video.bobbi.torrent` added and no removal, replacement,
extra addition, duplicate/case-alias ID, arbitrary approval or stale approval.
No version, frozen manifest, release key or native predicate changed here.
