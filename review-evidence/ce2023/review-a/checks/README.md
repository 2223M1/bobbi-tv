# Independent review checks

Run these scripts against the explicit `--repo` source tree with the repository's declared test dependencies installed. They read product files, use temporary local fixtures and write only the requested result file. They do not fetch release assets or contact devices.

| Script | Current b20e972 result | Boundary |
| --- | --- | --- |
| `reproduce_native_list_focus.py` | 3 pass / 2 fail / 0 errors | Actual renderer and session; explicit queued native-control double |
| `reproduce_native_monitor.py` | 3 pass / 2 fail / 0 errors | Actual product monitor / owner logic; controlled IO and timing boundary |
| `reproduce_clean_entry_audit.py` | 1 pass / 1 fail / 0 errors | Actual cleaner, audit and isolated bootstrap import; SignedBundle payload/signature boundary is a fixture |
| `reproduce_input_generation.py` | 4 pass / 1 fail / 0 errors | Actual packager and SignedBundle; real RSA signatures from temporary test trust, no production key |

Exit 0 means the harness assertions passed; exit 1 means recorded contract failures; exit 2 means harness execution errors. Do not count errors as product failures or convert a missing result into success.

`review_reference_commit` is the fixed review baseline, not a promise about a future checkout. `actual_checkout_commit` is null for a non-Git source snapshot; measured source hashes and the fixed tree identity records establish the actual input for this review. On a future checkout also preserve its commit/tree and dirty diff.

UI/native scripts are the unchanged counterexamples used for this review. A genuine implementation interface change may require an adapter; preserve the old script, adapter diff, behavior assertions and controls. Final closure requires the complete integration and actual package checks described in the Codex task file.
