# CE2033 artwork closure — historical working receipt

Final installation, tests and limitations supersede pending statements below:
see [CE2034 private delivery](CE2034-PRIVATE-REVIEW-DELIVERY.md).

The poster report was made while CE2031 was live. CE2032 navigation was installed
later; its new warmer cannot explain the earlier report. No private API/image
proxy is added and TLS/host validation remains intact.

## Evidence and implementation

- Old image server admitted four total HTTP requests and reset the fifth. A
  saved failing test held four cold misses and proved a cached fifth poster was
  reset. The fix separates 32 bounded HTTP handlers from six upstream miss
  leaders. Cached posters return directly, same-image followers coalesce, and
  overload has explicit 503/Retry-After instead of an unexplained reset.
- A second saved failure proved a normal service restart changed image URLs.
  A dedicated public-art endpoint now retains port/token across normal restarts;
  a port collision is explicit relocation. Old close may remove registration
  only when both port and token still match. Windows uses exclusive binding.
- Successfully TLS-verified official DoH addresses are reused within DNS TTL.
  A failed preferred address is removed without retrying around a TLS failure;
  the following request starts through the ordinary route again.
- Same-process visible-image activity preempts idle catalogue/art warm work.
  No new worker service or image-download daemon is introduced.
- Old local presentation URLs can be rebound only for the exact public TMDb
  image grammar; arbitrary loopback/control URLs are not relayed.
- Optional Fanart network failures were previously cached as successful default
  dictionaries for 24 hours. Two saved failing tests now pass: failed defaults
  are neither reused nor persisted; a subsequent success can populate cache.

Independent reviewers stayed read-only. Local pressure testing observed max six
upstream downloads, one transfer for a same-image follower, and a hot poster in
32 ms while cold downloads were held. This is not yet a device/network benchmark.

Live CE2032 evidence shows 40 sampled Home posters using the current loopback
endpoint at w342, not obsolete endpoints. The texture database contained 2514
old local URL keys across 58 older ports. This proves repeated cache-key churn,
not that the currently visible URLs were all invalid. The existing server's
already-cached 12-poster burst succeeded in 0.1 s; cold/slow-load verification is
still necessary. No texture database or user artwork was cleared.

## Package state

CE2033 first build (entry SHA cc806ae05a67dc717189f71b30eef0edf5f662bcfa359c8f314ca2717cba4c8c)
was never deployed. A late independent Fanart finding required rebuilding; it is
preserved at D:/AM6B-Project/CE2033-Preliminary-20261021, not silently overwritten.
The final package will be built at CE2033-Delivery-20261021 from the frozen source.
Full suite before the final Fanart patch: 2183 passed, 6 skipped, 1 strict xfailed.
After that patch the baseline suite is 820 passed. Final primary run, entry
installation, restart/readback, new-work tests and screenshots remain pending.

External evidence root: D:/AM6B-Project/ce2029-results-20261021.
Private review delivery must retain the startup-buffering limitations from CE2031
but those limitations no longer block delivery of completed UI/backend fixes.
