# Historical negative controls

Only the individual files exercised by the regression tests are retained here.
They are not installed or imported as production modules. Each compressed object
holds the exact unmodified bytes returned by `git cat-file blob COMMIT:PATH`.
The manifest records the full original commit, tree, path, Git blob ID and SHA-256.
Equal contents share a single object. CI checks both hashes before executing any
old code; a missing or altered object is a failure, never a skipped control.

To independently reproduce a record, resolve `COMMIT^{tree}` and `COMMIT:PATH`
in an archive containing the original commit objects. Compare the manifest and
the SHA-256 of the untransformed blob bytes. No historical branch, account,
deployment archive, download, or live Git repository is needed to run the tests.
