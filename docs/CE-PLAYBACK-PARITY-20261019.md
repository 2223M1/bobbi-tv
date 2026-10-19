# CE playback parity audit — 2026-10-19

Scope: compare the private CE candidate with `AM6B-review-ui-anirss-20261018`
(`ff530e09`), concentrating on subtitles, fonts, original audio and continuation.
This report is local source/contract evidence, not device or audiovisual acceptance.
Only the root task controls the AM6B. No device or external-network test was run
by this subtask.

## Confirmed regressions and narrow fixes

### 1. Local preparation was incorrectly gated by cloud readiness

The old `runtime/preparation_service.py` gates only cloud `resolve` and
`catalog_resolve` (around lines 440–470); its idle font-byte work precedes the
readiness return (575–582). The migrated `preparation_host.Session.dispatch`
had instead rejected every operation while CD2 was unverified/unavailable.
Consequently durable local intake, its status, cached subtitles and local fonts
could fail even without any need for cloud IO.

`preparation_host.py:403` now preserves the account lease but gates only those
two cloud-resolve operations. Idle-only font-byte warming again precedes the
readiness return. Cloud submission still requires readiness in `tick`; this
does not bypass account verification or label queued work as cloud-ready.

The old player also contained a latent receipt-ordering defect: it marked
preparation sent before reading the returned request ID. The new broad gate
made that defect reachable with an unavailable reply. A local execution of
the original player method and real `Session.dispatch` reproduced one request,
`sent=True`, no ticket, and a `KeyError`, with subsequent calls suppressed.

`native_player.py:1923` and `:2022` now latch sent only after a matching, valid
local receipt. The existing bounded attempts/backoff are retained. After an
unknown result, retries query status; only an explicit matching `absent` receipt
allows the same idempotent local intent to be reaccepted. Timeout, unavailable,
empty, wrong-ID and null replies do not authorize replay. Null is defensive
coverage: the current standard IPC client already rejects non-dict responses.
Exhaustion reports that reselecting the same source can retry. Direct sources
that are not applicable do not consume this retry budget.

No second scheduler, new cloud retry policy or automatic duplicate cloud task
was added. Existing durable submission-uncertainty handling is unchanged.

### 2. Same-share continuation lost half its search budget

Old `direct_continuity._qqdocs` explicitly allowed six seconds for the selected
share read. The migrated call used the generic three-second runtime timeout,
although `Host.dispatch('share_search')` still gives the provider six seconds.

`direct_continuity.py:109` sets this one client call to 6.5 seconds. Its exact
current source, account, next-episode and release-envelope checks remain intact.
The regression test executes the production function, actual SQLite selection
cache and host dispatch with a fixture provider. It verifies both timeout
contracts and rejection of late cancellation/account mismatch; it does not
claim a measured real six-second network response.

### 3. Private subtitle candidates lost account scope before final application

The same-share fetch guarded account changes during IO, but its candidate
omitted scope; the final fallback treated unscoped candidates as public.
The preparation service's ready subtitle receipt had the same omission and
could remain cached after a logout.

`share_subtitles.py` now copies the captured authenticated scope into a result
and checks cancellation/account again after local publication. `Host.sidecar_candidate`
requires that scope and rechecks the account on return. `Session.dispatch('subtitle')`
attaches its own lease scope to successful cached-ready/candidate replies.
The underlying generic subtitle preparation service remains account-agnostic.
`KodiNative.subtitle_candidate_current` and `playback_authority.py:738` perform
a final current-account check before enqueueing an account-scoped subtitle.
Public candidates do not acquire artificial account ownership.

Boundary: this is a final pre-submit check, not an atomic account/native
transaction. We deliberately do not hold the account lock across potentially
blocking native JSON-RPC or introduce a new native account protocol. It cannot
revoke a subtitle already queued before an account transition. Existing native
playback identity/manual-intent checks remain responsible for video ownership.

## Preserved behavior and inherited limitations

- Normalized old/new inspection found no algorithmic rewrite of font cache,
  font preflight, subtitle font preparation, subtitle preparation or subtitle
  pack selection beyond namespace/path adapters and the specific host boundary
  fixed above. Immutable subtitle/font state migration remains in place.
- Original-audio selection remains; the additional accepted torrent adapter
  host is intentional. Exact playback does not run the older delayed global
  audio setter over the native original-language choice or manual selection.
- Manual subtitle choice/disable, playback-instance binding, same-release
  continuation and the preference for a qualified personal-115 MDsub next
  episode are retained. No quality downgrade or unrelated-source auto-switch
  was introduced.
- CE-specific CD2 mount/warm-path assumptions predate this migration; they were
  not changed into a new blocker by this subtask and were not redesigned here.
- Native file rendering, ASS visual styles, original-language audibility and
  actual EOF-to-next-episode transitions still require root's device tests.
  A selected track/queued command is not proof of visible subtitles or sound.

## Validation

Python: `D:/AM6B-Project/AM6B-B-FULL-execution/20260908-115110/venv/Scripts/python.exe`.
Run suites separately to avoid legacy Kodi-stub module pollution.

1. `-X utf8 -m pytest tests/test_ce_playback_parity.py tests/test_preparation_host.py tests/test_runtime_host.py tests/test_share_subtitles.py tests/test_share_subtitle_references.py tests/test_direct_continuity_transport.py tests/test_subtitle_prepared_scope.py tests/test_subtitle_runtime_paths.py -q`
   — **145 passed**.
2. `-X utf8 -m pytest tests/private_baseline/test_subtitle_external_owner.py tests/private_baseline/test_playback_authority.py tests/private_baseline/test_font_hardlink_verification.py tests/private_baseline/test_font_byte_warmup.py tests/private_baseline/test_cinema_font_cache.py tests/private_baseline/test_cinema_fonts.py -q`
   — **200 passed**.
3. `-X utf8 -m pytest tests/preparation_regression -q`
   — **177 passed**.

The new parity suite compiles the unchanged production player methods via AST
to avoid importing the full Kodi/debrid UI, then drives actual `Session`,
`Intake`, `Ledger` and `DirectQueue`; only UI/thread/transport fixtures are
substituted. It covers accepted-but-lost replies, requests never received,
explicit absence, unknown outcomes, local outage tolerance, idle-only fonts,
revocation and actionable retry exhaustion. The ready-subtitle regression
uses actual `Session` → `SubtitleLookup` cache → `KodiNative` → authority with
logout between cache publication and owner request.

Independent read-only review by the candidate-unification agent identified the
prepared-scope omission and null-sentinel ambiguity; both were addressed and
rechecked. The tracked files touched by this subtask pass
`git -c core.whitespace=cr-at-eol diff --check` (the wider dirty repository has
existing CRLF/trailing-whitespace output and was not mechanically reformatted).

Production edits are frozen for root's aggregate regression, signing and
deployment. No firmware, versions, native patch/hash, cloud account or mount
configuration was changed by this subtask.
