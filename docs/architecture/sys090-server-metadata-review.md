# SYS-090 controlled server metadata review chain

This is a local cross-module checkpoint, not a real-server or device acceptance result. The existing 110 scenario objects, capability classifications, release versions and source inventory are unchanged.

## Source and implementation scope

Base product commit `1eb2e58b668916b950d332337486109184c48a18`, tree `4245e79c3c3087f0aa60ec6a20fe83cd236300bf`. Only a new test module and this record are added. No product implementation, metadata storage, credentials, installer, native binary or device state was changed.

`tests/test_server_metadata_review_chain.py` SHA256 is `359867354b02ed85b79b85fbe4539326a03d9847618a6b7d3aed376b3e5e27f7`. The tests reuse the existing three-provider `scene` fixture from `test_server_descriptions.py`. Plex and Jellyfin/Emby production adapters feed the real PanService, NativePort, CatalogService scan worker and SQLite MediaIndex. Review preview, apply, receipt retrieval, replay, undo and query use `CatalogService.dispatch`.

Remote response transport is synthetic. Provider replies and a raised `PanError` supply deterministic metadata and disconnection conditions; the tests do not substitute the adapter, scanner, SQLite transaction, supplement validation or review implementation. SQLite reads inspect persisted manual transaction tables; the tests do not directly repair or write those tables.

## Missing interactions added

Existing `test_server_descriptions.py` already proved manual mapping preservation across refresh, revocation fences, direct review undo and source-only description limits. Existing supplement tests separately covered parent revision/observation checks, label-only edits and historical undo. The new module joins these mechanisms at the public service boundary instead of repeating their unit tests.

| Controlled interaction | Cases across three providers | Observed contract |
|---|---:|---|
| Refresh between preview/apply, title-only refresh, provider episode/parent claims, manual extra-label edit, reparent and undo | 3 | Source candidates refresh, while manual titles, review authority and saved parent CAS evidence remain owned by review operations. Undo restores the previous user-selected parent, not the provider's claimed parent. Query projection retains manual parent titles. |
| Parent manual title revision or selected file-size change, then detach undo and source refresh | 6 | Historical relation retains its old evidence and stays `verification_required`. A label-only command carrying that stale evidence fails preview and apply; source metadata does not silently reconfirm it. |
| Failure before the first page, or after the real 20-item first page of a 21-item scan, then reconnect/re-enumerate | 6 | Committed source observations remain; unseen files are not inferred absent. Manual transaction rows and original receipts remain unchanged, source coverage is partial/recheck-required, and the same owner can complete a later scan without SQL repair. |

Every successful and failed review apply is checked against its original receipt and same-request replay. Preview and receipt/replay checks do not change the inspected manual transaction rows. The failed-page cases distinguish zero committed pages from one committed 20-item page; they do not discard the first page's valid source observations.

## Execution evidence

Evidence root is `D:/AM6B-Project/AM6B/tmp/bobbi-convergence-20261113/results`.

- `sys090-server-metadata-validated-20261114.xml`: Windows, 15 passed, zero failures/errors/skips. SHA256 `cf85a1913a521e6874c994112db57f465e828def30c0fc14eb12dc11e5c2daef`.
- `sys090-server-metadata-regression-20261114.xml`: Windows, 229 passed, zero failures/errors/skips. SHA256 `0ff3e10c6771759cc96ce860b6b1bab7ddcb9fef605776b00fa2444cfed72d34`. Includes the new 15 plus server descriptions/adapters, supplements/integrity/transfer, review atomicity, source observation and CatalogService suites.
- `sys090-server-metadata-linux-20261114.xml`: existing native Linux interpreter, same 15 cases passed, zero failures/errors/skips. SHA256 `663329e4945ff00cd4e3615f7cfb8e65c7666fb80f49514a1782083be9f7403e`.

These are overlapping executions, not 259 distinct functional cases. The 15 new cases are included in the 229-case regression result; their Linux execution is a second environment, not additional system coverage.

The initial receipt `sys090-server-metadata-initial-20261114.xml`, SHA256 `ebb876e71a10b1a4e5cd754ffab010b99964eefce45f031e066326741a6910ed`, is retained with 9 passed and 6 failed. All six failures were the test's `KeyError: present_count` after earlier preservation assertions passed. The public source-card summary deliberately removes present/absent counts; the corrected tests use its public `indexed_count` and read every file's public availability. No product change was needed or inferred from that test error.

## Remaining acceptance boundaries

This proves a bounded controlled chain for Plex, Jellyfin and Emby response shapes. It does not prove live credentials, remote HTTP/network behavior, server-version interoperability, real partial listings, TV/phone UI operation, reboot or power-loss durability, file-content identity, automatic matching, playback, server progress synchronization, transcoding or HLS lifecycle.

Server sources remain start-only. A provider title, episode number or parent label is never a playback grant or strong file-content proof. A failed or partial scan preserves previous membership observations; it does not establish that unseen files still exist remotely. SYS-090 and the other original system scenarios remain pending device/system acceptance.
