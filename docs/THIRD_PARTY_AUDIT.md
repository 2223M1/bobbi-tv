# Third-party and private-data audit

## Public alpha disposition — 2026-10-19 (supersedes historical status below)

- The reviewed, sanitized new skin is now adopted in `addons/skin.bobbi.cinema`.
  Proprietary Netflix/Founder/Font Awesome Pro fonts are excluded. Unmodified
  HarmonyOS Sans and Font Awesome Free notices accompany the actual binaries.
  Layout/focus style is retained; this is not an Android TV visual certification.
- `bencodepy` was removed; runtime imports use MIT flatbencode, with a canonical
  bencode round-trip test on the actual public source.
- Segno, torf, xmltodict and Jacktook full notices are included in installable
  packages, not only at repository root. Optional skin dependencies are pinned
  in `release/kodi-vendors.json` with original source and notices. Where an
  upstream module declares GPL but omits the standard text, the text is supplied
  as `LICENSE.bobbi-supplement`, not misrepresented as an upstream file.
- tmdbv3api 1.9.0 explicitly declares MIT and Anthony Bloomer in its original
  setup.py. Its upstream tag/wheel omit a standalone license file. That metadata
  is retained; a separately labeled standard MIT notice supplement accompanies
  the adapted code. This is not a recovered original LICENSE or independent
  legal clearance. The baseline manifest below intentionally records the
  original evidence gap instead of rewriting its history.
- The owner authorized redistribution of their catalogue-module code under its
  existing MIT declaration; notices are supplied. Curated databases are rebuilt
  using an explicit table/column allowlist, with no login/profile state or old
  SQLite pages. Catalogue indices are not licenses for third-party media.
- Inherited hardcoded application keys were removed from optional integrations.
  TMDb requires the installer's own key. Gitleaks is run on the public tree;
  allowlists are the literal Python package name `tmdbv3api.objs` in unmodified
  license evidence and verified 64-hex file digests in the two exact inventory
  JSON files, not credentials or broad source-path exceptions.
- Android release signing keys/passwords remain in ignored `.private`, never
  in sources or release assets. TorrServer is unmodified MatriX.147; binary
  checksums, upstream commit and build/source archive accompany the release.
- Public alpha can be distributed after source/package verification. Stable
  remains closed until real clean installation, playback and update/rollback
  acceptance. Artwork remains independently CC-BY-NC-SA-4.0 where applicable.

## Historical baseline review (not current implementation status)

Scope: committed AM6B candidate `a9189b5d157d886c814cf28c6748c97fc6825a35`,
explicit release inventory, seven addon roots and the UI overlay. No private
Git history, devices, remote accounts or files outside the inventory were
promoted. This records engineering evidence, not a blanket license clearance.

## Skin sanitation

Current user direction: retain the original UI/assets and authorize publication
of the catalog, share links and extraction codes. The sanitizer below is an
optional, unadopted review experiment, not the release asset policy and not a
deployed change. No original skin was edited. Font redistribution grants have
not been supplied by this direction alone; restricted binaries remain local
pending evidence. Account cookies, login tokens and personal credentials remain
excluded even where catalog/share publication is authorized.

`tools/sanitize_skin.py` reads ignored quarantine and writes a new separate
review candidate (`build/sanitized-skin` by default). It refuses existing output
and symlink inputs, validates before writing, and never edits quarantine.

- Font tables identify `BobiDisplay.ttf` and `fzltdhk.ttf` as Founder
  FZLanTingHeiS-DB1-GBK; no public redistribution grant was supplied.
- `BobiAF-Solid.ttf` identifies Font Awesome 6 Pro Solid, not Free. Netflix
  binaries identify Netflix copyright and a commercial EULA. They are omitted.
- MiSans has no bundled grant in this inventory; it is replaced, without
  asserting that the font is categorically nonredistributable.
- Text Font.xml roles use unchanged HarmonyOS Sans SC fonts.
  The retained agreement explicitly permits unmodified bundling with software,
  with copyright/license retention and prominent notice. Font sizes, control
  positions, navigation IDs and UI layout remain unchanged. Nine keyboard icon
  glyphs use near-equivalent Font Awesome Free 6.7.2 Solid glyphs, with actual
  cmap coverage checked. The unmodified font (not Pro) is pinned to upstream
  commit af620534bfc3c2d4cbefcfeec29603bbe7809e64 and distributed with its full
  SIL OFL 1.1 notice. Android setup uses the same licensed text fonts and palette.
- All legacy local scripts except the standalone Kodi keyboard IME helper are
  omitted. In particular `record.py` embeds encoded authorization credentials,
  retrieves a purchase/authorization database and remote executable code, and
  disables TLS verification. No credential values are reproduced here.
- Local helper invocations, install/updater commands and platform power/exec
  operations, including CoreELEC/LibreELEC system-settings launchers, are removed.
  The one retained helper must match its reviewed SHA-256. Validation rejects
  credential-bearing HTTP URLs without including their values in errors.
  Private mount defaults become ordinary Kodi media
  browsers. Native `Player.Bobi*` names remain exact; only addon IDs are mapped.
- Private screenshots and metadata references are omitted. Original license
  files and upstream provenance are retained, with a current provenance notice.

Inherited Arctic Fuse artwork remains CC BY-NC-SA 4.0: public noncommercial
sharing subject to attribution/share-alike is not the same as an unrestricted
commercial grant. It is not relabeled GPL. Minsk/Confluence code keeps its
inherited declarations. Other artwork/source attribution and actual Kodi UI
rendering remain review gates; this sanitizer does not certify all assets.

## Other baseline findings

- User-supplied sound addon expressly asserts no redistribution grant; omit it.
- QQDocs catalog database includes share codes/extraction passwords and
  user-supplement provenance/file evidence. MDSub contains a catalog snapshot.
  Publication of these catalogs and share codes is now explicitly authorized by
  the user; this authorization is not a grant for third-party copyrighted media
  itself and does not authorize publishing cloud account credentials. Captured
  private UI screenshots/previews still require separate review.
- Shared core CD2 contains a private default endpoint. OpenSubtitles defaults to
  a named private proxy policy. Both need explicit public configuration work.
- Trakt application settings and Stremio host match public upstream exactly;
  they were not established as personal credentials. OpenSubtitles records
  upstream public application-key provenance; service terms/key ownership are
  separate from source-code licensing. Do not call every application key a
  leaked personal account token, and do not publish actual private credentials.

## Code license evidence and unresolved gates

Jacktook's LICENSE is byte-identical to upstream GNU GPL version 3 at
`Sam-Max/plugin.video.jacktook@2e70c70ed6c20006eda99fd557108d31c75cb953`:
SHA-256 `605e9047a563c5c8396ffb18232aa4304ec56586aee537c45064c6fb425e44ad`.
Upstream's addon metadata also says GPL-2.0-only. Preserve the original grant
and author notices; document a public-fork metadata correction instead of
claiming this mismatch prohibits every redistribution or relicensing all code.
The extracted shared core inherits its source terms and is not blanket MIT.

Vendored torf states GPL-3.0-or-later. Vendored bencodepy instead states
BitTorrent Open Source License 1.1 and is actively used by torrserver_utils;
compatibility must be resolved or the component replaced before claiming a
GPL-clean combined distribution. Full component license notices for Segno,
tmdbv3api, xmltodict and bencodepy must be restored from exact upstream versions,
not inferred from package names or replaced by a project-wide license.
MDSub/QQDocs metadata declares MIT but lacks complete standalone grant text;
only actual rights holders can supply grants for their own code. The independent
OpenSubtitles integration declares GPL-2.0-or-later and retains its NOTICE.

Font Awesome official license reference: `https://fontawesome.com/license`.
HarmonyOS source/license evidence is retained in the input asset provenance and
`fonts/LICENCE-HarmonyOS-Sans.txt`; the fonts are not modified by the sanitizer.
Stable release remains closed pending source/asset review, clean installation,
update/rollback and real Android/Kodi playback verification.
