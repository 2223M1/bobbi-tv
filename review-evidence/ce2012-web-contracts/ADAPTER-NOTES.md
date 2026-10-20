# CE2011 Web contracts on CE2012

Original ZIP and unmodified baseline results are retained beside this directory.
Assertions and the 18 behavior contracts are unchanged. Two IO seams changed:

- The service-entry fixture's existing `host_started` event now answers the new
  owner-readiness request; enabled flags alone cannot answer it.
- The snapshot fixture explicitly rejects the newly added fallback inventory
  read as unavailable. The original assertion already allows aborting an
  unknown snapshot before any moves. Separate product tests cover successful
  fallback, absent components and persistent enumeration failure.

Run with `PYTHONUTF8=1` on Windows: the original trial fixture uses platform-default
`read_text()` on UTF-8 Chinese receipts. The initial GBK harness error is retained,
not counted as a product failure. No behavior expectation was relaxed.
