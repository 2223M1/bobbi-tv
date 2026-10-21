# CE2024 tested private entry

`script.bobbi.start-0.2.15-ce2024.zip` is the actual entry installed for this review, not a source-check stub. It contains the complete signed payload at:

`script.bobbi.start/resources/complete.bobbi-update.zip`

- Entry SHA-256: `cb355eb2a80b3974e985a9bc404fb74a8be1c98ab1319d30e4399eb503c06e9c`
- Embedded payload SHA-256: `d53bc3b6ad0c4dc905a831d1906575a7c53ad15c0e6a6d6d7b12188e0d33c096`
- Product commit: `d2fffa570fe59b90cd1d33499efcf7c6684b2647`
- Product tree: `380b4493b2eafcaa46efe63e0ebd8c5cd1686dc3`
- Sequence: `2026102024`

This private offline client includes the configured project application resource, but no signing key, cloud account or device backup. It is not a published Release or an anonymous update channel. See `docs/CE2024-DELIVERY.md` for actual test scope and unresolved playback failures. The source snapshot includes this signed installer as a review artifact; the application configuration is not checked in as a standalone source file.

The separate payload can be extracted from the entry without alteration. Verify it using the committed trust root and `tools/audit_ce_entry.py`; do not rebuild it with a different key and call it the tested package.
