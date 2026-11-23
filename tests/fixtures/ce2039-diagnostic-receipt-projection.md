# CE2039 diagnostic receipt projection

This is a sanitized, reduced replay fixture, not the full device artifact and
not evidence of a new playback test. It replaces a mandatory test that could
only run on the maintainer's D drive.

Original basename: `ce2039-gattaca-open-range-result1.json`.
Original SHA256: `cf64a4caeb84f7171cde88ebcf92597158443929acec1c2875fe56484349de08`.
Projection SHA256: `8e4122f7f4726125c7a457e7ee51f8da06f0ac2db776d0a918aa8170e5ac49eb`.

Retained unchanged: schema, operation, run/request/native IDs, tool revision,
route/state, diagnostic/product/retry/open flags, URL hash and bound file
identity (hashes only), diagnostic mode/budget, owner boot/epoch/request, stop
and historical stop_state. Of 89 original samples, only the first and last
samples carrying native identity are retained; each is projected onto phase
and native request/instance/phase. No timings, stream URLs, track descriptions,
device paths, response bodies, credentials or account state are included.

The mandatory test checks a pinned fixture digest, the real diagnostic_scope
consumer, unchanged bytes and contradictory bindings. It does not overwrite
the original or relabel the historical stop_state as verified.

Optional verification of a retained original uses an explicitly supplied local
path and expected request:

```sh
python tools/check_diagnostic_receipt.py --receipt /path/to/original.json --request EXPECTED_REQUEST_ID
```

Missing input returns `not_run` (exit 2), invalid/changed input exit 1, verified
binding exit 0. This command performs no device or network operation; even a
verified historical receipt is not current-device acceptance.
