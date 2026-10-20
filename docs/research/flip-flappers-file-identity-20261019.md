# Flip Flappers filename-identity audit — 2026-10-19

## Deployment identity correction

The playback under review used sequence **2026101908**, deployment run
`20261019-205008`. An earlier statement identifying the current deployment as
1907 / run `20261019-211907` was incorrect: that receipt was historical, not
evidence of the active native generation.

Authoritative evidence is `review-evidence/ce-runtime-upgraded-1908-native.json`
and the matching 1908 release manifest/runtime health. Archive checks:

| Item | SHA-256 |
| --- | --- |
| 1908 CoreELEC update bundle | `483022c6d40738daec55ec800348d9cc14dc3a810039b630547a9418e7d52c5e` |
| Nested core 0.1.4 ZIP (matches `release.json`) | `a170b4165b132ba88fb0306f9365281473846e5cd508e57895e885a6e0c4678e` |
| Nested `share_stream.py`, 33,420 bytes | `49c3cc1edf71be7811832b6546220164c7dea7f721a57e2722ebdb2816ab00a1` |

The ShareStream comparison applies to these pinned bytes, not a subsequently
modified source checkout. This audit makes no new streaming-performance claim.

## Confirmed metadata and failure

`review-evidence/ce-torrent-flip1908-live2.json` captures all 40 files for hash
`12733bd6fadad8406d4cad55606e8734aefa0ef7`: 13 MKVs, 26 SC/TC ASS subtitles,
and one font archive. Episode 1 is file ID 3, length 411,570,230 bytes:

```text
[SweetSub&LoliHouse] Flip Flappers - 01 [WebRip 1920x1080 HEVC-yuv420p10 AAC].mkv
```

`review-evidence/ce-playback-log-1792417099818207100.json` connects request
`d311d0e008d84500b8d87a42e22e68fb` to this hash and the failure:
`TORRENT_EPISODE_FILE_IDENTITY_UNRESOLVED`, stage `filename_identity`, 40 total
files, 13 video candidates. Producer diagnostics report a present versioned
transport binding, available en-US catalogue and 11 aliases. They do not log
the aliases themselves.

The earlier URL-based request `1a9a98f27bb741faae85831a38767d0f` is a different
selection. Its identical file/candidate counts do **not** prove the same hash.
No such equality is assumed here.

## Diagnosis and narrow correction

The actual filename parses to `('flip flappers', None)` in `release_title`.
It is not the bilingual, bracketed display-card title. No title-parser or
catalogue-alias change was justified.

For a versioned `unscoped-range-v1` binding, `check_transport_episode_file`
also calls `check_file_tail`. The pinned 1908 `_TECH` grammar rejects
`HEVC-yuv420p10`, producing exactly the failure above. Replacing only the
in-memory grammar with its pinned 1908 expression while replaying the real
40-file metadata reproduces `filename_identity`, 40 files, 13 candidates.

The correction adds a closed planar-YUV grammar: 420/422/444 sampling, default
8-bit or explicit 9/10/12/14/16-bit depth, and optional endian suffix for the
explicit depths. It recognizes a standalone format or a format attached to
HEVC/AVC. It does not accept arbitrary codec suffixes, strip unknown words,
relax work/year/episode identity, or change media selection or quality.

## Verification and limits

`tests/test_anime_range_file_identity.py` reproduces all 40 captured IDs,
paths and lengths; an independent comparison against the evidence JSON found
them exactly equal. The test uses the production `get_jacktorr_url`, real
bundled TMDb 68272 → AniDB 12007 regular 1–13 mapping, binding validation and
`select_file`. Both BT and URL transport routes emit the restricted scope
and select original file ID 3. Catalogue details are an explicit test fixture,
not a claimed copy of the device's 11-alias cache.

Negative tests retain rejection of another work, another year, unknown title
suffix, wrong episode, multi-episode file, duplicate candidates and bonus
directories. Invalid pixel-format suffixes cannot consume those identities.

- Relevant new identity, torrent selector and adapter tests: **191 passed**.
- Private baseline suite plus preparation source-intent tests: **775 passed**.

These are local regression results, not native playback certification. Device
retest and the following release's deployment remain owned by the main task.
