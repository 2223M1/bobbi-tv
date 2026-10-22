# bobbi TV

Owner decision 2026-10-22: source may remain public and installers may be freely
distributed. This does not certify a stable release or authorize publishing
credentials. Preserve existing licenses and credits; distribution permission
does not confer new third-party rights. Owner confirmed document-only cleanup
on 2026-10-21. Follow tools/delivery_policy.py; do not restore standalone notice
documents as a build prerequisite.
Do not copy account state, device backups or signing secrets into installers.
Curated resource catalogues are authorized; rebuild from whitelisted tables,
never copy login state or unexamined database pages.

- Product-owned identifiers use `bobbi`. Reuse compatible upstream add-ons
  unchanged under their original IDs and author/Kodi update channels; do not
  rename or fork them merely for branding. Keep cinema-specific adapters thin.
  Preserve upstream credits and documented native `Player.Bobi*` protocol names.
- Kodi 21 / Python 3.8+ runtime, stdlib-first. Android 8+ without root.
- No default private hosts, proxy tunnels, login tokens or shared cloud accounts.
- Build from an explicit inventory. Unit tests are not device certification.
- Keep stable releases closed until clean-install, update/rollback and real
  playback gates pass. Do not silently switch the private AM6B update channel.
- Preserve source selection, original language and full-quality media. No
  transcoding, lowering resolution, or switching release identities on errors.
- Use apply_patch for authored source edits. No secret output in diagnostics.
- This task authorizes narrow native player candidates and CE add-on deployment,
  not firmware/SYSTEM/eMMC flashing. Android boot requires proven remote return.
