# Reused artwork

The independent skin is a derivative of the supplied Minsk / Confluence runtime.
Original license and attribution files remain included.

`media/am6b/cinema-hero-fade.png` is an unmodified copy of
`media/common/gradient-box.png` from the user's CE archive
`skin.arctic.fuse.3.nara-cpm-3.1.13.zip`, component
`skin.arctic.fuse.3.nara-omega.cpm` (Arctic Fuse / jurialmunkey and its supplied
Nara/CPM derivative). It is tinted and flipped by the Kodi XML renderer only.
The supplied archive licenses this work under CC BY-NC-SA 4.0:
https://creativecommons.org/licenses/by-nc-sa/4.0/
The corresponding Cinema composition reusing this artwork is shared under
the same license. Original Minsk components retain their existing licenses.
See `LICENSE-Arctic-Fuse.txt` for the exact supplied attribution notice.

No other CE skin's service code or dependencies have been imported.

The refined home additionally uses 17 unmodified Arctic Fuse PNGs under
`media/am6b/cinema/`: gradients, nine-slice rounded surfaces/outlines/shadows,
navigation icons and action icons. Exact source paths, SHA-256 values and pixel
dimensions are recorded in `implementation/cinema/results/visual-assets.json`.
These remain under the same CC BY-NC-SA 4.0 artwork terms and supplied attribution.
Combined PNG size is 85,098 bytes; raw RGBA pixel storage totals 3,895,552 bytes
before renderer overhead/mipmaps. This is an asset budget, not a runtime-memory
or performance benchmark. Kodi tinting, nine-slice scaling and visibility only;
no image generator or runtime blur service is installed.

## Font

`fonts/RobotoCJKSC-Regular.ttf` is copied without modification from
`3.resource.font.robotocjksc-0.0.1.zip` in the supplied CE folder.
Embedded family name: `Roboto + Noto Sans CJK SC`.
Embedded copyright: Copyright 2011 Google Inc. All Rights Reserved;
© 2014–2019 Adobe (http://www.adobe.com/).
The font's embedded license explicitly declares SIL Open Font License 1.1
(https://scripts.sil.org/OFL), despite the wrapper addon's Apache-2.0 label.
The embedded font declaration is preserved; a copy of the OFL text is provided
in `fonts/LICENCE-OFL.txt`. The font is not sold separately or modified/renamed.
This earlier prototype font is retained as an inactive legacy asset; it is no
longer referenced by the current Font.xml.

## Current typography — 波比TV

All Chinese and mixed-script UI uses unmodified `HarmonyOS_SansSC_Regular.ttf`,
`HarmonyOS_SansSC_Medium.ttf` and `HarmonyOS_SansSC_Bold.ttf` from Huawei's official
design-resource download: https://developer.huawei.com/consumer/en/design/resource/
Archive: https://developer.huawei.com/Enexport/sites/default/images/download/next/HarmonyOS-Sans.rar
Archive SHA-256: `510274fbc12e80abe641d7b0d9bd4d2bb4fec111b7b710122364a7723fe12bd7`.
Copyright 2021 Huawei Device Co., Ltd. Included license:
`fonts/LICENCE-HarmonyOS-Sans.txt`. The font binaries are NOT merged, subsetted,
renamed or modified. Attribution is also displayed in the skin's system-info
window and addon description. They are bundled with the skin, not sold as fonts.

Netflix Sans is proprietary and contains no Chinese characters. Optional local
personal-use packages convert official WOFF2 to TTF for guaranteed Latin-only
labels, without claiming a redistribution license. Those binaries remain in the
ignored build directory. The repository package is self-contained with HarmonyOS
fonts, including its Latin-label fallback. `build_skin.py --local-typography`
records the exact device-specific overlay hashes separately. No font processing
or additional background service runs on the box. No playback subtitle font or
video/audio settings are changed.
