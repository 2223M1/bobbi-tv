# Isolated native RPC schema registrar repair

This repository directory is an exact source/tool copy of the reviewed external
freeze (README aside). The binary, archives and raw compiler outputs remain at
`D:/AM6B-Project/ce2042-native-jsonrpc-schema-20261022/` for this local audit.
Run paths below identify that original freeze; the tools also accept their
repository location while still requiring the pinned external F9 build inputs.
No account data or signing key is part of this directory.

This is a new candidate, not a replacement of the frozen 8bb2/632 directories.
Only `JSONRPC.cpp.o` is newly compiled and replaced in copied 8bb2 archives.
The other 8bb2 sources, objects, original-audio selection, subtitles, handoff
capsule and Gate implementation remain unchanged. No device or deployment work
is performed by these tools. The maintained build tree is queried and hashed,
never built or patched; all outputs/depfiles/archive writes go to fresh runs.

## Frozen result

Run: `builds/run-1792626905471062171/`.

- `candidate.bin`: `ba03279546193a8a5e6299b257e1321833dbf5b7b3ecc087ba67ed7dd2eb1991`
- `build-result.json`: `30e1e3008b3a8fe86d7f2036039476c654237c9f5a93ced03418f0e327749074`
- `artifact-verification.json`: `db04c3a39dcdcd1e2732879ad71e235490cb86825a4fc6cdc013f8861ad172e0`

The unchanged 8bb2 source snapshot is copied into `candidate/`, with only the
maintained `JSONRPC.cpp` added. Its SHA256 is
`b94dae82ab3d5b2b0390be2359112f51f15df4a953d4fe8fa1145e99bc83e7bb`.
Each build freezes that complete ten-file snapshot in its own run.

`ServiceDescription.h` has exactly two actual consumers, checked independently
through Ninja dependencies and direct source includes. New `JSONRPC.cpp.o` uses
this run's generated header. Retained `JSONServiceDescription.cpp.o` is proven
to be the frozen 8bb2 object, with its original depfile pointing to the 8bb2
header; that header and the newly generated header are byte-identical. There
is no claim that the retained object's depfile points to the new run.

Before replacing the object, linking copied original archives reproduces exact
8bb2. After replacement, every other archive member is byte-identical to 8bb2;
the three untouched archives are also whole-file identical. All 184 complete
method JSON objects extracted from the real ELF equal `methods.json`, including
all twelve BobiControl parameter schemas and both handoff actions. The old
8bb2 ELF differs from that schema only in BobiControl.

## Reproduction

In WSL distro `AM6B-F9-Build-20260905`:

```sh
python3 -B /mnt/d/AM6B-Project/ce2042-native-jsonrpc-schema-20261022/build_isolated.py --output-dir /mnt/d/AM6B-Project/ce2042-native-jsonrpc-schema-20261022/builds
python3 -B /mnt/d/AM6B-Project/ce2042-native-jsonrpc-schema-20261022/verify_artifact.py --build-result <fresh-run>/build-result.json
```

Every build creates a new directory. Verification is once-only and will not
overwrite an existing restrip or receipt. Root coordinates successor-profile
integration and the fresh whole-generation runtime ABI gate; do not loosen the
older baseline branch or deploy this binary alone.

Windows parser regressions: `test_schema_verifier.py`, nine passed. Original
audio and actual capsule harness outputs are under `audio-tests/` and
`registry-tests/`, both passed using the unchanged candidate sources. The full
author handoff report is
`D:/AM6B-Project/ce2029-results-20261021/native-jsonrpc-schema-implementation-20261022.md`.

Local build/schema/object proofs do not certify real device handoff timing.
