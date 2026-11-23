# Locked JackTorr test inputs

These three files are the existing release317 selector/subtitle adapter, not an
upgrade of JackTorr and not a second implementation. Upstream attribution:
https://github.com/Sam-Max/plugin.video.jacktorr (MIT; license included).

`exact_selection.py` imports the adjacent `episode_matching.py`.
`subtitles.py` is only the production compatibility alias to the current
`am6b_core.torrent_subtitles`; it does not freeze the current core's policy.

The SHA256 values are locked in `backend/baseline-maintenance-inputs.json`.
The selector pair was already in this review checkout. The subtitle alias was
added to close the missing sibling-addon dependency in `test_subtitle_pack.py`.
Tests use the real sibling when it exists and this exact fixture otherwise.

Run `python ui-redesign/tools/maintenance_inputs.py` at project root before the
offline regressions. No production addon, cloud account, or device state changes
are performed by that command. These fixtures are test inputs, not payload files
to deploy over the installed JackTorr addon.
