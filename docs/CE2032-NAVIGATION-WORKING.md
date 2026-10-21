# CE2032 navigation and idle preparation — working receipt

Scope: selected-work catalogue/navigation and the existing source picker. No
native player, codec, bitrate, CD2, account, Yatse or subtitle position changes.
The user accepted the existing minimum subtitle setting, measured 22 px in the
prior bilingual GUI-plane capture. Startup buffering remains an acknowledged
non-blocking issue for private review delivery, not a reason to hide completed
UI/backend work. No claim of a fully certified stable release.

## Product changes

- Reuse the selected work's full details; no second season-page details/IMDb
  lookup. Numeric idle IDs and string route IDs share the detail cache/lease.
- Single actual regular season (including animation) enters episodes directly
  when no movies have been confirmed. Future/zero-episode later seasons and
  validated production-season order remain visible. Enabled specials and an
  explicit unknown/retry status remain reachable; unknown is not “no film”.
- Related films are actual film cards that enter manual movie source selection,
  never TV episode identities. Discovery follows provider pagination, validates
  relation/identity, preserves partial results, and no longer takes the first
  five candidates. Candidate 101 is reachable even when the first 100 fail the
  relation check. Up to 100 verified films are displayed; truncation is not
  claimed complete. The wall-time budget can leave discovery incomplete.
- Movie canonical details include alternate titles; old successes are upgraded
  once without erasing their successful year/identity fallback.
- Source setup reuses one metadata object and cached artwork. Optional RPDB and
  Fanart network requests are no longer in its admission/first-provider path.
- Existing StartupPreloader owns background preparation: focus stable ≥2 s,
  one selected work, then at idle ≥12 s up to three unfinished recent works.
  It warms full details and first/latest or selected season pages, not entire
  libraries. It resolves no playable URL, creates no transfer, fetches no video,
  and refreshes no browsing directory. Existing home refresh also yields to
  audio, video, modal work and interaction.
- Actual preparation peak is eight I/O calls (nested language/film stages), not
  three. AM6B+ is the performance reference, with memory/temperature/load
  headroom. Eight seconds is a cooperative budget, not forced OS/DNS abortion.
- Cancellation is monotonic across workers; it cannot publish a negative order
  cache or poison foreground retry cooldown. Failed season dictionaries cannot
  be counted as prepared. Background errors cannot kill the preload thread.

## Tests and artifacts

- Saved initial 3 failing navigation counterexamples in external results.
- Stable primary suite: 2176 passed, 6 skipped, 1 strict xfailed. The xfail is the
  previously acknowledged type-evidence gap, not newly waived.
- Targeted baseline + metadata/decoder checks: 838 passed (overlaps primary).
- Preparation suite: 177 passed. Counts are not device certification.
- An initial primary run had three Windows locale decoding failures plus an
  inventory mismatch while implementation was still changing; the encoding was
  made explicit UTF-8, inventory refreshed, and the stable suite rerun.
- CE2032: 22 signed components, sequence 2026102032. Entry 0.2.23 is 95,966,727
  bytes, SHA256 a4e0021bba56bf763d111338835b2ef6bca6a92ab02ea96bdcfe267dec54207e.
  The exact entry/bootstrap/embedded-payload audit passed. Original CE2031
  artifacts have not been replaced. Actual entry installation completed as
  tx 0360b0cc15a544779adca6b9228afb80; all 1155 owned installed files matched.
  The existing long-lived host had not yet been restarted at this observation.

Independent reviewers remained read-only; primary agent implemented fixes and
alone operated the box. Their reports are in the external results directory.
An additional user report of very slow/missing anime posters arrived after the
  navigation package was built. Image-path/cache/scheduling diagnosis is ongoing;
the then-live CE2031 predates the new idle warmer, so that report cannot be
attributed to the not-yet-installed warmer.

Real directory RPC for previously untested Samurai Champloo (TMDb 1063): old
CE2031 returned a season+placeholder hub in 7.657 s; new CE2032 returned 26
episode actions directly in 14.044 s on first preparation, then 2.8 s warm.
These are different amounts of work, not a like-for-like latency speedup claim.
The unnecessary empty-film retry exposed a real TMDb boundary: zero hits may
report total_pages=1. CE2033 accepts either zero or one empty page, with the
captured provider evidence and both regression cases retained.

External evidence: D:/AM6B-Project/ce2029-results-20261021.
Package directory: D:/AM6B-Project/CE2032-Delivery-20261021.
Private GitHub identity verified as 2223M1/bobbi-tv using only a process-local
existing HTTP proxy; no global proxy changes. Nothing pushed this turn yet.
