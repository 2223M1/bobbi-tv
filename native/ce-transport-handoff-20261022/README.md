# F9 same-file transport handoff candidate

Isolated descendant of the installed `8962740e718a7978acadbf2ae7ad55b0cd0742f6d0db162e9c1a1d8645ef834b`.
Firmware, SYSTEM/eMMC, codecs, audio/video quality and the historical subtitle ABI are unchanged.
The previously rolled-back Directory candidate is **not** included.

**Superseded candidate; original-audio regression confirmed on 2026-10-22.**
The frozen 632 binary lacks the native `bobitv.original_audio.*` consumer that
exists in the real 896 baseline. The retained `original/` source was restored
after an earlier build and is not functionally equivalent to its retained
objects. A successful 896 relink proves object identity, not source parity.
See `../ce-original-audio-handoff-20261022/` for the replacement candidate and
its explicit source/header dependency audit. Keep this 632 freeze and its
failed playback evidence intact; do not use it as a feature-complete baseline.

`candidate/` is the exact source freeze used by the isolated build; `original/`
contains the corresponding on-disk translation units/schema, with the source/
object mismatch described above. `build_isolated.py`
queries the pinned WSL build without modifying it. Consult `PROTOCOL.md` before
using the instance-bound capture/stop/restore API.

Candidate binary, full build logs, prior failed builds and registry test runs
remain under `D:/AM6B-Project/ce2035-native-handoff-20261022` until actual device
acceptance. Local state-machine checks are not whole-player device certification.

The current source freeze is
`D:/AM6B-Project/ce2035-native-handoff-20261022/run-1792604146028135531/source-candidate`.
Its adjacent `candidate.bin` has SHA256
`632758f5d1ca5494e9b049446d3908bead70589b4d18640bb5d06e830a2b57eb`.
This freeze also preserves the complete prior automatic-subtitle receipt proof
(`subtitle_file_applied` plus its validated SHA256) across handoff. The earlier
`a74ebd175225b9682e8b5ed16e7defbfa864e989871bb675b84dad77f5077e81`
freeze and its failed cross-layer regression are retained as evidence; that
earlier candidate must not be substituted for the current one.

## Re-run the capsule harness

This is a Linux host test, not a Windows executable or an ARM device test. It
compiles the real `BobiHandoff.h` with Kodi's real `Variant.cpp` and
`VideoSettings.cpp`; those types are not test doubles. Python 3.8+ and a host
C++17 compiler are required. The tested host is WSL distro
`AM6B-F9-Build-20260905`, with `g++ 12.3.0` on Ubuntu 22.04.

The necessary unmodified **fmt 10.2.1** headers (`core.h`, `format.h`,
`format-inl.h`) and their MIT license are included under `tests/includes/fmt`.
Their upstream tag, local provenance and SHA256 values are recorded in
`tests/dependencies.json`. This harness does not need a fmt binary library.

The maintained F9 Kodi source tree remains an external dependency. Its default
location inside that WSL distro is:

```text
/opt/am6b-maintainable-r10-20260922/build.CoreELEC-Amlogic-ng.arm-21/build/kodi-e0614d7a6713369bbcfe42152223f1cdaec3dbf1
```

The runner verifies actual Kodi source/header dependencies against
`tests/dependencies.json` before compiling. A clean upstream Kodi checkout is
not equivalent: the maintained tree also supplies `BobiGuiGate.h`. A copy at
another Linux path can be supplied with `--kodi-source`, provided every pinned
dependency matches. This directory is not a complete Kodi source/build
distribution and is not self-contained on another machine.

From Windows PowerShell:

```powershell
wsl -d AM6B-F9-Build-20260905 -- python3 /mnt/d/AM6B-Project/bobbi-tv-ce2029-selfaudit-20261021/native/ce-transport-handoff-20261022/tests/run_registry_test.py --output-dir /mnt/d/AM6B-Project/ce2035-native-handoff-20261022/registry-replays
```

From a shell inside the same WSL distro:

```sh
python3 /mnt/d/AM6B-Project/bobbi-tv-ce2029-selfaudit-20261021/native/ce-transport-handoff-20261022/tests/run_registry_test.py --output-dir /mnt/d/AM6B-Project/ce2035-native-handoff-20261022/registry-replays
```

Each invocation creates a new `run-<time_ns>` directory containing the host test
executable and `registry-test-result.json`, including compiler version, command,
dependency hashes and test results. Exit status zero and `state=PASSED` indicate
the capsule harness passed. The runner does not write Kodi sources or frozen
candidate binaries. `--candidate-root` may point to a build's `source-candidate`
directory; the manifest still requires its expected capsule header hash.

## Re-run the isolated ARM build

The full build additionally requires the already built maintained F9 tree,
its original archives/objects, `build.ninja`, and the associated ARM toolchain
at the paths pinned by `build_isolated.py`. The host harness does not require
that ARM toolchain. The builder only queries Ninja for commands and writes a
fresh run beside itself; it does not edit the original Kodi build directory.

From PowerShell (omit `wsl -d ... --` when inside this distro):

```powershell
wsl -d AM6B-F9-Build-20260905 -- python3 /mnt/d/AM6B-Project/bobbi-tv-ce2029-selfaudit-20261021/native/ce-transport-handoff-20261022/build_isolated.py
```

This recompiles the candidate and independently relinks the original baseline.
Use `--compile-only` for compilation without relinking. To reuse the previously
verified baseline artifact, add:

```text
--baseline-proof /mnt/d/AM6B-Project/ce2035-native-handoff-20261022/run-1792601381159946071/build-result.json
```

That JSON and its adjacent `baseline.bin` must remain available; the builder
checks original input hashes and the baseline binary hash. Do not supply
`--directory-archive` for this candidate: the old Directory patch is excluded.
A rebuild is a new artifact with its own reported hash. Successful compilation
does not authorize changing a maintenance profile pin or deploying a binary.
