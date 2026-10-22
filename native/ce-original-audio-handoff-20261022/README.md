# CE2038 original audio with transport handoff

Native hash: `8bb2a99e2154432a4403ac55a81e3c253d7ab74f0e15369b85085f1a8bf4fd14`.
This restores the reviewed audio314 original-language component on top of frozen
632 handoff sources. Local build and harness checks passed; device playback is
a separate gate. The builder/verifier/harnesses perform no device operations.

The actual 896 binary contains the original-audio consumer. The 632 binary
lost it because its on-disk `original/` source had been restored after an older
build and did not match retained objects. Relinking those objects reproduced
896 but did not prove source parity. Keep 632 and its failure evidence intact.

## Selection and layout

The existing four `bobitv.original_audio.*` properties are bound once to the
request, exact file identity and SHA256 of the actual `GetDynPath()`. Automation
only influences initial OPEN ordering with original-language preference and no
explicit saved/manual stream. Exact language matches exclude known commentary
names/flag. No match keeps ordinary ordering. The successful stream is retained
by full demux key, never ordinal. Manual selection revokes the plan; automatic
selection does not increase audio intent. Epoch changes, ambiguous/mutated
keys, or a late first selection cannot rerun the hint. A capsule-bearing child
always suppresses the hint and restores its captured audio key and delay.
No later global audio RPC is used. See PROTOCOL.md for the capsule contract.

VideoPlayer.h is the exact reviewed audio314 header, SHA256
`027aa817492d941216b7c77ff3e58346082a1fe213e4aaef3ea80fd45711ab6c`.
The helper retains the original state layout and adds a pure binding validator.
Ninja dependency enumeration requires exactly VideoPlayer.cpp,
ApplicationPlayer.cpp and PlayerCoreConfig.cpp as header consumers. All three
are rebuilt and depfiles must reference the frozen candidate header. The two
JSON-RPC TUs are also rebuilt. The maintained build tree is only queried/hashed.

## Enumerated verification

verify_artifact.py checks all baseline defined Bobi symbols and all four audio
properties in the real output. Every unmodified member of all four copied
archives is byte-identical to baseline, including VideoPlayerAudio.cpp.o;
other linked archives remain original and hashed. ApplicationPlayer and
PlayerOperations starting sources match the independent clock317 source audit;
PlayerCoreConfig is unchanged. All RPC methods remain, only Player.BobiControl
changes. ARM attributes/dynamic dependencies are unchanged; restripping the
recorded unstripped output reproduces the exact candidate. These checks cover
the stated contracts, not every historical behavior.

## Reproduce in WSL

Use distro AM6B-F9-Build-20260905 and the maintained F9 tree pinned in the builder.
Host tests require g++ C++17. Capsule tests use actual Kodi Variant/VideoSettings
and bundled fmt 10.2.1; tests/dependencies.json pins all dependencies.

From this directory inside WSL:

```sh
python3 tests/run_original_audio_test.py --output-dir /mnt/d/AM6B-Project/ce2038-native-original-audio-20261022/audio-tests
python3 tests/run_registry_test.py --output-dir /mnt/d/AM6B-Project/ce2038-native-original-audio-20261022/registry-tests
python3 build_isolated.py --output-dir /mnt/d/AM6B-Project/ce2038-native-original-audio-20261022 --baseline-proof /mnt/d/AM6B-Project/ce2035-native-handoff-20261022/run-1792601381159946071/build-result.json
python3 verify_artifact.py --build-result <new-run>/build-result.json
```

PowerShell: prefix with `wsl -d AM6B-F9-Build-20260905 --` and use full `/mnt/d/...`
script paths. Every build/test creates a new run. The verifier writes a new
artifact-verification.json; do not overwrite old evidence. `baseline_inputs`
equals the old proof inputs, `additional_inputs` holds the original header and
factory source/object, and `inputs` is exactly their union. Deployment pins the
whole new build report as well as its candidate.

## Frozen local result

Root: D:/AM6B-Project/ce2038-native-original-audio-20261022/.

- Binary/source: run-1792612141766198431/candidate.bin and source-candidate/.
- Build report SHA: 0c6069fe71c83c491dd48f363ca44efb3c2dbd775aa8fd0aaccc944c6aca52c9.
- Verification SHA: c0be45eeb70302f8a1b1ff93fffaefd4c8b1116fe4132d95ddd80651747f00ff.
- Audio harness: audio-tests/run-1792612141769841505/, passed.
- Capsule harness: registry-tests/run-1792612141803186810/, passed.

Audio tests compile the actual helper and extracted comparator, with explicit
settings/language service stubs. Cases: wrong request/file/URL, missing language,
commentary, no match, explicit saved stream, manual before/after AV and stale
open completion, epoch, stream reorder/mutation/ambiguity, new episode, capsule
suppression. Capsule tests cover real one-use/instance/epoch/file/intent state,
settings/delay and subtitle proof. Neither simulates full decoder timing or
substitutes for fresh Samurai playback and a real BT-to-115 handoff.
