# bobbi TV：版权、字体、音效与素材来源统一说明

整理日期：2026-10-21。本文件是字体、音效、皮肤素材及第三方代码版权说明的唯一维护入口，并随皮肤组件打包；不是对整个项目的统一重新授权。

## 当前状态

当前维护的是私人使用版本。早期公开原型“排除方正／Netflix／Font Awesome Pro、仅使用 HarmonyOS／Free、不带原音效”的结论，不适用于后续私人版。旧说明中的历史事实在本文保留，但不能覆盖本节的版本边界。

| 项目 | 当前来源及状态 | 许可边界 |
| --- | --- | --- |
| MiSans、方正标题字、Netflix Sans、Font Awesome Pro | 2026-10-19 从 AM6B 基线恢复，未修改字体二进制 | 恢复或私人托管不等于获得公开再分发授权；不能称全部是自由字体或仅凭“非商业”即可任意分发 |
| HarmonyOS Sans SC | 保留原字体及华为许可 | Copyright 2021 Huawei Device Co., Ltd.；按原协议随软件分发未修改字体，保留显著声明和协议，不单独销售／分发字体 |
| Font Awesome Free 6.7.2 Solid | 保留早期公开原型的原字体及通知，与 Pro 区分 | Fonticons, Inc.；字体适用 SIL OFL 1.1，SVG／JS 图标的许可另见原文 |
| Roboto、Roboto + Noto Sans CJK SC 等 | 来源、版权和随附许可分别保留 | 不用包装插件的许可替代字体本身的声明；具体许可原文见本节下方 |
| `resource.uisounds.bobbi-modern` | 原用户提供音效，共 8 个 WAV | 原声明明确未授予再分发许可；不宣称公开或商业使用已获授权 |
| Minsk／Confluence 皮肤代码 | 保留来源及原作者声明 | 沿用其原许可，不以本项目名称覆盖作者权利 |
| Arctic Fuse／jurialmunkey 及 Nara／CPM 衍生美术 | 沿用已记录的原始素材与组合 | CC BY-NC-SA 4.0，署名、非商业、相同方式共享；不能把美术整体改称 GPL 或 MIT |
| Jacktook 及其他第三方代码 | 各组件保留原版权、许可证与必要补充说明 | 新增代码的 GPL-3.0-or-later 声明不覆盖其他作者素材；独立目录模块等仍按自身声明 |

Juku（巨库）的研究来源、采用边界、协议分析和两个完整反编译包已统一迁往 [AM6B 的 Juku 研究说明](https://github.com/2223M1/am6b-community-baseline-v4/blob/juku-research-0.80-20261021/docs/JUKU-RESEARCH.zh-CN.md)，不在此复制研究正文。Juku 作者的研究／接入授权不能替代字体、音效或其他第三方的许可。

## 许可证原文与机器证据

下列原始许可证和机器清单已全部嵌入本文附录，旧文件不保留。构建工具校验字节、SHA-256 和原始换行后，将必需通知提取到生成的安装包；仓库不再维护第二份。记录存在不等于授权已齐备。

- [HarmonyOS Sans 原协议](#original-3b4f2007cc7a)
- [Font Awesome Free 原许可](#original-56cf4e8f617e)
- [Roboto 原许可](#original-5c7af4c96324)、[CJK 字体 OFL 原文](#original-eceb253430d9)、[其他字体随附文件](https://github.com/2223M1/bobbi-tv/blob/ee65742bfcbaf08831f70306faed11bd1f8d6cc6/addons/skin.bobbi.cinema/fonts)
- [Arctic Fuse 原许可](#original-177b95fedf87)、[Minsk／Confluence 原许可](#original-2c891aabfd94)
- [音效原声明](#original-94cab92daee1)
- [Jacktook 上游许可](#original-39e0468bfefb)、[共享核心来源说明](#original-c41966d4800d)
- [第三方基线证据清单](#original-b9d8a4de92d1)、[依赖锁定清单](#original-de8ff34d4a81)
- [私人版素材来源与逐文件哈希](#original-3da33a998688)：源提交为 `ff530e09c34c6285ccb05c1d4179140b097174fb`；本次未改其记录或任何字体、图像、音效字节。

目录索引、分享链接和提取码的整理／发布授权不等于影片、字幕的版权授权；不包含账号、登录态或签名私钥的发布许可。应用代码许可与服务条款、应用 Key 所有权也须分别判断。

## 版本与历史记录的阅读顺序

以下内容依次合并私人版恢复说明、素材来源、早期公开候选说明和历史总审计。它们保留各自当时的证据，**历史章节中的“current”“now”“排除”“已恢复”等均以该章节时点为准**。旧总审计对 `bencodepy`、目录模块授权等还保留了前后阶段记录，不应把早期未解决项直接当作当前实现状态。

本次仅整理说明、迁移 Juku 归档；未重新授予许可，未发布新安装包，未部署或操作盒子。原许可证继续随组件保留。若准备公开发布或商业分发，应先按实际发布清单重新核对缺失的授权，而非依赖本文件概括性放行。


<a id="private-restoration"></a>

## 个人版素材恢复

2026-10-19：从完整 CE 基线 ff530e0 恢复 MiSans、方正标题字、Netflix Sans、
Font Awesome Pro 及原有字体引用；键盘恢复与 Pro 字体对应的原字形。保留其余
字体与许可证。音效由 resource.uisounds.bobbi-modern 提供，共 8 个 WAV。

精确来源与 SHA-256：仓库 release/private-assets.json。未修改字体二进制。
sanitization-manifest.json 和 ASSET-PROVENANCE.md 中关于“仅 HarmonyOS/Free”
的叙述属于 0.1 公开原型的历史记录，本文件及恢复清单是当前状态。

私库限个人使用；不声称 Juku 作者授权自动覆盖第三方素材许可。
旧授权、远程执行、清库及更新脚本继续排除，不因素材恢复而启用。

<a id="upstream-assets"></a>

## Reused artwork

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

### Font

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

### Current typography — 波比TV

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

<a id="public-prototype"></a>

## bobbi TV review-candidate assets

The layout is inherited from the Minsk/Confluence-derived AM6B Cinema skin. Existing author credits and license files are retained; no blanket relicensing is asserted. Arctic Fuse-derived artwork remains CC BY-NC-SA 4.0 (noncommercial and share-alike), not GPL artwork.

All active font roles now reference unmodified HarmonyOS Sans SC Regular, Medium or Bold. Copyright 2021-2025 Huawei Device Co., Ltd. The accompanying fonts/LICENCE-HarmonyOS-Sans.txt permits unmodified bundling with software subject to its conditions. No font binary is modified, subsetted, merged or renamed. Keyboard icons use unchanged Font Awesome Free 6.7.2 Solid (Fonticons, Inc., SIL OFL 1.1 for font files), pinned to commit af620534bfc3c2d4cbefcfeec29603bbe7809e64. All nine required icon mappings are checked against its actual cmap; the full upstream license accompanies the font. Restricted Founder, Netflix and Font Awesome Pro fonts and unreviewed MiSans fonts are not included. Historical upstream provenance is retained separately under licenses/ and is not a claim about the current typography.

Private screenshots and all legacy local updater/authentication, network, firmware and device helpers are omitted. The standalone Kodi IME helper is retained. The candidate is not a certified release; other artwork provenance, native-host compatibility and device tests remain release gates.

<a id="historical-audit"></a>

## Third-party and private-data audit

### Public alpha disposition — 2026-10-19 (supersedes historical status below)

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

### Historical baseline review (not current implementation status)

Scope: committed AM6B candidate `a9189b5d157d886c814cf28c6748c97fc6825a35`,
explicit release inventory, seven addon roots and the UI overlay. No private
Git history, devices, remote accounts or files outside the inventory were
promoted. This records engineering evidence, not a blanket license clearance.

### Skin sanitation

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

### Other baseline findings

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

### Code license evidence and unresolved gates

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

## 原始许可证、通知及校验清单全文

每个代码块完整保留原文件文本，包括版权行和许可条款。元数据保存原路径、字节数、SHA-256 与换行格式；路径是历史身份，不是仍存在的文件。构建运行清单 `release/source-inventory.json` 不属于版权资料，仍由构建流程独立维护，避免对本文产生循环哈希。

<a id="original-94cab92daee1"></a>

### `addons/resource.uisounds.bobbi-modern/LICENSE`

<!-- provenance-file {"path": "addons/resource.uisounds.bobbi-modern/LICENSE", "bytes": 87, "sha256": "64741185bfb63f5a9c8fd1881cb8cdeb5db95ff5bcf2f2e76d7dd7bc20133c19", "newline": "lf"} -->
````text
Private user-supplied media. This repository does not assert a redistribution licence.

````
<!-- /provenance-file -->

<a id="original-c41966d4800d"></a>

### `addons/script.module.bobbi.core/LICENSES.md`

<!-- provenance-file {"path": "addons/script.module.bobbi.core/LICENSES.md", "bytes": 977, "sha256": "3b743828701a3d6afb35661287ed787aff6a96796c7042d718c4ec0d2ff2b3bb", "newline": "lf"} -->
````text
# Provenance and license declarations

This is a local, not-yet-released extraction of the existing AM6B modifications
from `plugin.video.bobbi`. It does not claim a new blanket license for other
authors' work. Original copyright notices and the source package's LICENSE are
retained. The upstream Jacktook source LICENSE is GNU GPL version 3 while its
addon.xml declares GPL-2.0-only. That inconsistency is recorded, not silently
resolved by changing an upstream author's notice.

The mechanical source-to-destination SHA-256 mapping and original files are in
the run's `evidence/068-shared-core-extraction` and
`snapshots/shared-core-before-extraction` directories. This module introduces
no replacement cloud database or resource ledger. The episode mapping resource
is copied byte-for-byte from the prior candidate with its existing provenance.

Public redistribution remains outside this implementation task and is not
authorized or declared license-cleared by this file.

````
<!-- /provenance-file -->

<a id="original-177b95fedf87"></a>

### `addons/skin.bobbi.cinema/LICENSE-Arctic-Fuse.txt`

<!-- provenance-file {"path": "addons/skin.bobbi.cinema/LICENSE-Arctic-Fuse.txt", "bytes": 303, "sha256": "95cc16779fa07b82bb7069b50fd6a788db75f3ab53426d0f3692c7be34d18b4c", "newline": "lf"} -->
````text
This work is licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 Unported License.
To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-sa/4.0/
or send a letter to Creative Commons, 171 Second Street, Suite 300, San Francisco, California, 94105, USA.

````
<!-- /provenance-file -->

<a id="original-2c891aabfd94"></a>

### `addons/skin.bobbi.cinema/LICENSE.txt`

<!-- provenance-file {"path": "addons/skin.bobbi.cinema/LICENSE.txt", "bytes": 15419, "sha256": "89931c1fb1f3716694175763cf3221cfcd63d6935031cf6b4512d17ffe5d9860", "newline": "lf"} -->
````text

 You may use, distribute and copy Kodi under the terms of GNU General
 Public License version 2, which is displayed below.

-------------------------------------------------------------------------

		    GNU GENERAL PUBLIC LICENSE
		       Version 2, June 1991

 Copyright (C) 1989, 1991 Free Software Foundation, Inc.
                       59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
 Everyone is permitted to copy and distribute verbatim copies
 of this license document, but changing it is not allowed.

			    Preamble

  The licenses for most software are designed to take away your
freedom to share and change it.  By contrast, the GNU General Public
License is intended to guarantee your freedom to share and change free
software--to make sure the software is free for all its users.  This
General Public License applies to most of the Free Software
Foundation's software and to any other program whose authors commit to
using it.  (Some other Free Software Foundation software is covered by
the GNU Library General Public License instead.)  You can apply it to
your programs, too.

  When we speak of free software, we are referring to freedom, not
price.  Our General Public Licenses are designed to make sure that you
have the freedom to distribute copies of free software (and charge for
this service if you wish), that you receive source code or can get it
if you want it, that you can change the software or use pieces of it
in new free programs; and that you know you can do these things.

  To protect your rights, we need to make restrictions that forbid
anyone to deny you these rights or to ask you to surrender the rights.
These restrictions translate to certain responsibilities for you if you
distribute copies of the software, or if you modify it.

  For example, if you distribute copies of such a program, whether
gratis or for a fee, you must give the recipients all the rights that
you have.  You must make sure that they, too, receive or can get the
source code.  And you must show them these terms so they know their
rights.

  We protect your rights with two steps: (1) copyright the software, and
(2) offer you this license which gives you legal permission to copy,
distribute and/or modify the software.

  Also, for each author's protection and ours, we want to make certain
that everyone understands that there is no warranty for this free
software.  If the software is modified by someone else and passed on, we
want its recipients to know that what they have is not the original, so
that any problems introduced by others will not reflect on the original
authors' reputations.

  Finally, any free program is threatened constantly by software
patents.  We wish to avoid the danger that redistributors of a free
program will individually obtain patent licenses, in effect making the
program proprietary.  To prevent this, we have made it clear that any
patent must be licensed for everyone's free use or not licensed at all.

  The precise terms and conditions for copying, distribution and
modification follow.

		    GNU GENERAL PUBLIC LICENSE
   TERMS AND CONDITIONS FOR COPYING, DISTRIBUTION AND MODIFICATION

  0. This License applies to any program or other work which contains
a notice placed by the copyright holder saying it may be distributed
under the terms of this General Public License.  The "Program", below,
refers to any such program or work, and a "work based on the Program"
means either the Program or any derivative work under copyright law:
that is to say, a work containing the Program or a portion of it,
either verbatim or with modifications and/or translated into another
language.  (Hereinafter, translation is included without limitation in
the term "modification".)  Each licensee is addressed as "you".

Activities other than copying, distribution and modification are not
covered by this License; they are outside its scope.  The act of
running the Program is not restricted, and the output from the Program
is covered only if its contents constitute a work based on the
Program (independent of having been made by running the Program).
Whether that is true depends on what the Program does.

  1. You may copy and distribute verbatim copies of the Program's
source code as you receive it, in any medium, provided that you
conspicuously and appropriately publish on each copy an appropriate
copyright notice and disclaimer of warranty; keep intact all the
notices that refer to this License and to the absence of any warranty;
and give any other recipients of the Program a copy of this License
along with the Program.

You may charge a fee for the physical act of transferring a copy, and
you may at your option offer warranty protection in exchange for a fee.

  2. You may modify your copy or copies of the Program or any portion
of it, thus forming a work based on the Program, and copy and
distribute such modifications or work under the terms of Section 1
above, provided that you also meet all of these conditions:

    a) You must cause the modified files to carry prominent notices
    stating that you changed the files and the date of any change.

    b) You must cause any work that you distribute or publish, that in
    whole or in part contains or is derived from the Program or any
    part thereof, to be licensed as a whole at no charge to all third
    parties under the terms of this License.

    c) If the modified program normally reads commands interactively
    when run, you must cause it, when started running for such
    interactive use in the most ordinary way, to print or display an
    announcement including an appropriate copyright notice and a
    notice that there is no warranty (or else, saying that you provide
    a warranty) and that users may redistribute the program under
    these conditions, and telling the user how to view a copy of this
    License.  (Exception: if the Program itself is interactive but
    does not normally print such an announcement, your work based on
    the Program is not required to print an announcement.)

These requirements apply to the modified work as a whole.  If
identifiable sections of that work are not derived from the Program,
and can be reasonably considered independent and separate works in
themselves, then this License, and its terms, do not apply to those
sections when you distribute them as separate works.  But when you
distribute the same sections as part of a whole which is a work based
on the Program, the distribution of the whole must be on the terms of
this License, whose permissions for other licensees extend to the
entire whole, and thus to each and every part regardless of who wrote it.

Thus, it is not the intent of this section to claim rights or contest
your rights to work written entirely by you; rather, the intent is to
exercise the right to control the distribution of derivative or
collective works based on the Program.

In addition, mere aggregation of another work not based on the Program
with the Program (or with a work based on the Program) on a volume of
a storage or distribution medium does not bring the other work under
the scope of this License.

  3. You may copy and distribute the Program (or a work based on it,
under Section 2) in object code or executable form under the terms of
Sections 1 and 2 above provided that you also do one of the following:

    a) Accompany it with the complete corresponding machine-readable
    source code, which must be distributed under the terms of Sections
    1 and 2 above on a medium customarily used for software interchange; or,

    b) Accompany it with a written offer, valid for at least three
    years, to give any third party, for a charge no more than your
    cost of physically performing source distribution, a complete
    machine-readable copy of the corresponding source code, to be
    distributed under the terms of Sections 1 and 2 above on a medium
    customarily used for software interchange; or,

    c) Accompany it with the information you received as to the offer
    to distribute corresponding source code.  (This alternative is
    allowed only for noncommercial distribution and only if you
    received the program in object code or executable form with such
    an offer, in accord with Subsection b above.)

The source code for a work means the preferred form of the work for
making modifications to it.  For an executable work, complete source
code means all the source code for all modules it contains, plus any
associated interface definition files, plus the scripts used to
control compilation and installation of the executable.  However, as a
special exception, the source code distributed need not include
anything that is normally distributed (in either source or binary
form) with the major components (compiler, kernel, and so on) of the
operating system on which the executable runs, unless that component
itself accompanies the executable.

If distribution of executable or object code is made by offering
access to copy from a designated place, then offering equivalent
access to copy the source code from the same place counts as
distribution of the source code, even though third parties are not
compelled to copy the source along with the object code.

  4. You may not copy, modify, sublicense, or distribute the Program
except as expressly provided under this License.  Any attempt
otherwise to copy, modify, sublicense or distribute the Program is
void, and will automatically terminate your rights under this License.
However, parties who have received copies, or rights, from you under
this License will not have their licenses terminated so long as such
parties remain in full compliance.

  5. You are not required to accept this License, since you have not
signed it.  However, nothing else grants you permission to modify or
distribute the Program or its derivative works.  These actions are
prohibited by law if you do not accept this License.  Therefore, by
modifying or distributing the Program (or any work based on the
Program), you indicate your acceptance of this License to do so, and
all its terms and conditions for copying, distributing or modifying
the Program or works based on it.

  6. Each time you redistribute the Program (or any work based on the
Program), the recipient automatically receives a license from the
original licensor to copy, distribute or modify the Program subject to
these terms and conditions.  You may not impose any further
restrictions on the recipients' exercise of the rights granted herein.
You are not responsible for enforcing compliance by third parties to
this License.

  7. If, as a consequence of a court judgment or allegation of patent
infringement or for any other reason (not limited to patent issues),
conditions are imposed on you (whether by court order, agreement or
otherwise) that contradict the conditions of this License, they do not
excuse you from the conditions of this License.  If you cannot
distribute so as to satisfy simultaneously your obligations under this
License and any other pertinent obligations, then as a consequence you
may not distribute the Program at all.  For example, if a patent
license would not permit royalty-free redistribution of the Program by
all those who receive copies directly or indirectly through you, then
the only way you could satisfy both it and this License would be to
refrain entirely from distribution of the Program.

If any portion of this section is held invalid or unenforceable under
any particular circumstance, the balance of the section is intended to
apply and the section as a whole is intended to apply in other
circumstances.

It is not the purpose of this section to induce you to infringe any
patents or other property right claims or to contest validity of any
such claims; this section has the sole purpose of protecting the
integrity of the free software distribution system, which is
implemented by public license practices.  Many people have made
generous contributions to the wide range of software distributed
through that system in reliance on consistent application of that
system; it is up to the author/donor to decide if he or she is willing
to distribute software through any other system and a licensee cannot
impose that choice.

This section is intended to make thoroughly clear what is believed to
be a consequence of the rest of this License.

  8. If the distribution and/or use of the Program is restricted in
certain countries either by patents or by copyrighted interfaces, the
original copyright holder who places the Program under this License
may add an explicit geographical distribution limitation excluding
those countries, so that distribution is permitted only in or among
countries not thus excluded.  In such case, this License incorporates
the limitation as if written in the body of this License.

  9. The Free Software Foundation may publish revised and/or new versions
of the General Public License from time to time.  Such new versions will
be similar in spirit to the present version, but may differ in detail to
address new problems or concerns.

Each version is given a distinguishing version number.  If the Program
specifies a version number of this License which applies to it and "any
later version", you have the option of following the terms and conditions
either of that version or of any later version published by the Free
Software Foundation.  If the Program does not specify a version number of
this License, you may choose any version ever published by the Free Software
Foundation.

  10. If you wish to incorporate parts of the Program into other free
programs whose distribution conditions are different, write to the author
to ask for permission.  For software which is copyrighted by the Free
Software Foundation, write to the Free Software Foundation; we sometimes
make exceptions for this.  Our decision will be guided by the two goals
of preserving the free status of all derivatives of our free software and
of promoting the sharing and reuse of software generally.

			    NO WARRANTY

  11. BECAUSE THE PROGRAM IS LICENSED FREE OF CHARGE, THERE IS NO WARRANTY
FOR THE PROGRAM, TO THE EXTENT PERMITTED BY APPLICABLE LAW.  EXCEPT WHEN
OTHERWISE STATED IN WRITING THE COPYRIGHT HOLDERS AND/OR OTHER PARTIES
PROVIDE THE PROGRAM "AS IS" WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESSED
OR IMPLIED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.  THE ENTIRE RISK AS
TO THE QUALITY AND PERFORMANCE OF THE PROGRAM IS WITH YOU.  SHOULD THE
PROGRAM PROVE DEFECTIVE, YOU ASSUME THE COST OF ALL NECESSARY SERVICING,
REPAIR OR CORRECTION.

  12. IN NO EVENT UNLESS REQUIRED BY APPLICABLE LAW OR AGREED TO IN WRITING
WILL ANY COPYRIGHT HOLDER, OR ANY OTHER PARTY WHO MAY MODIFY AND/OR
REDISTRIBUTE THE PROGRAM AS PERMITTED ABOVE, BE LIABLE TO YOU FOR DAMAGES,
INCLUDING ANY GENERAL, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES ARISING
OUT OF THE USE OR INABILITY TO USE THE PROGRAM (INCLUDING BUT NOT LIMITED
TO LOSS OF DATA OR DATA BEING RENDERED INACCURATE OR LOSSES SUSTAINED BY
YOU OR THIRD PARTIES OR A FAILURE OF THE PROGRAM TO OPERATE WITH ANY OTHER
PROGRAMS), EVEN IF SUCH HOLDER OR OTHER PARTY HAS BEEN ADVISED OF THE
POSSIBILITY OF SUCH DAMAGES.

		     END OF TERMS AND CONDITIONS
-------------------------------------------------------------------------

````
<!-- /provenance-file -->

<a id="original-3b4f2007cc7a"></a>

### `addons/skin.bobbi.cinema/fonts/LICENCE-HarmonyOS-Sans.txt`

<!-- provenance-file {"path": "addons/skin.bobbi.cinema/fonts/LICENCE-HarmonyOS-Sans.txt", "bytes": 3352, "sha256": "327e0147d4a3ca2d89e81abce45b210576b0f9fe2b29d900f64b58039f12a102", "newline": "crlf"} -->
````text
License Notice
Copyright 2021 Huawei Device Co., Ltd.
HarmonyOS Sans Fonts Software is licensed under HarmonyOS Sans Fonts License Agreement.

--------------------------------------------------------------------------------
HarmonyOS Sans Fonts License Agreement

THIS HARMONYOS SANS FONTS LICENSE AGREEMENT ("AGREEMENT") IS A LEGAL AGREEMENT BETWEEN YOU (EITHER A SINGLE INDIVIDUAL, OR SINGLE LEGAL ENTITY) AND HUAWEI DEVICE CO., LTD.( "LICENSOR")FOR THE USE OF THE HARMONYOS SANS FONTS ACCOMPANYING THIS AGREEMENT.BY DOWNLOADING,COPYING OR OTHERWISE USING HARMONYOS SANS FONTS YOU INDICATE THAT YOU AGREE TO BE BOUND BY ALL OF THE TERMS OF THIS AGREEMENT. IF YOU DO NOT AGREE TO THE TERMS OF THIS AGREEMENT, YOU MAY NOT DOWNLOAD, COPY OR OTHERWISE USE THE HARMONYOS SANS FONTS, AND YOU SHALL PROMPTLY DESTROY AND DELETE ALL THE HARMONYOS SANS FONTS.

1.Definition
"HarmonyOS Sans Fonts" shall mean the collection of fonts software components provided by Licensor under this Agreement and clearly marked as "HarmonyOS¬ Sans".

"YOU" shall mean an individual or legal entity exercising permissions granted by this Agreement.

2.GRANT OF LICENSE

Subject to the terms and conditions of this Agreement, Licensor hereby grant YOU a non-transferable, non-exclusive, royalty-free, revocable, worldwide copyright license to use,copy, merge, embed, bundle, redistribute and/or sell unmodified copies of HarmonyOS Sans Fonts with any software except for fonts software，subject to the  following conditions:
1)YOU shall make a prominent notice in the software to state that HarmonyOS Sans Fonts are used.
2)YOU may not make any modifications to HarmonyOS Sans Fonts or any of their individual components.
3)Neither HarmonyOS Sans Fonts nor any of their individual components may be redistributed or sold in a stand-alone base. This limitation does not apply to any work created by using HarmonyOS Sans Fonts. You can freely distribute or sell your work, such as materials, logos, application software etc. created by using HarmonyOS Sans Fonts.
4)YOU shall retain the copyright notice and this Agreement in any copies of HarmonyOS Sans Fonts.

3.Termination
This Agreement will be automatically terminated if YOU breach any of this Agreement.

4.NO WARRANTY
YOU AGREE THAT THE HARMONYOS SANS FONTS ARE PROVIDED BY LICENSOR ON AN "AS IS" BASIS. LICENSOR MAKES NO WARRANTY, EXPRESSED OR IMPLIED OR STATUTORY, WITH RESPECT TO ANY OF THE HARMONYOS SANS FONTS, INCLUDING WITHOUT LIMITATION, ANY IMPLIED WARRANTIES OF MERCHANTABILITY, SATISFACTORY QUALITY, FITNESS FOR A PARTICULAR PURPOSE OR NON-INFRINGEMENT.

5.NO LIABILITY

IN NO EVENT SHALL LICENSOR BE LIABLE FOR ANY DIRECT OR INDIRECT, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES (INCLUDING WITHOUT LIMITATION, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) ARISING IN ANY WAY OUT OF THE USE OF OR INABILITY TO USE HARMONYOS SANS FONTS, WHETHER UNDER THEORY OF CONTRACT, TORT (INCLUDING NEGLIGENCE), STRICT LIABILITY OR OTHER LEGAL THEORY, EVEN IF LICENSOR HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

YOU EXPRESSLY ASSUME ALL LIABILITIES AND RISKS FOR USE OF HARMONYOS SANS FONTS. SHOULD THE HARMONYOS SANS FONTS PROVE DEFECTIVE, YOU ASSUME THE ENTIRE COST OF ALL NECESSARY SERVICING, REPAIR OR CORRECTION.


````
<!-- /provenance-file -->

<a id="original-f2c613623d11"></a>

### `addons/skin.bobbi.cinema/fonts/LICENCE-Heebo.txt`

<!-- provenance-file {"path": "addons/skin.bobbi.cinema/fonts/LICENCE-Heebo.txt", "bytes": 4346, "sha256": "6d13374a47f3db882aad98f5788620d425e0b44a2d7221bb14fb185e8425ae2d", "newline": "lf"} -->
````text
Copyright 2014 The Heebo Project Authors. 

This Font Software is licensed under the SIL Open Font License, Version 1.1.
This license is copied below, and is also available with a FAQ at:
http://scripts.sil.org/OFL


-----------------------------------------------------------
SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007
-----------------------------------------------------------

PREAMBLE
The goals of the Open Font License (OFL) are to stimulate worldwide
development of collaborative font projects, to support the font creation
efforts of academic and linguistic communities, and to provide a free and
open framework in which fonts may be shared and improved in partnership
with others.

The OFL allows the licensed fonts to be used, studied, modified and
redistributed freely as long as they are not sold by themselves. The
fonts, including any derivative works, can be bundled, embedded, 
redistributed and/or sold with any software provided that any reserved
names are not used by derivative works. The fonts and derivatives,
however, cannot be released under any other type of license. The
requirement for fonts to remain under this license does not apply
to any document created using the fonts or their derivatives.

DEFINITIONS
"Font Software" refers to the set of files released by the Copyright
Holder(s) under this license and clearly marked as such. This may
include source files, build scripts and documentation.

"Reserved Font Name" refers to any names specified as such after the
copyright statement(s).

"Original Version" refers to the collection of Font Software components as
distributed by the Copyright Holder(s).

"Modified Version" refers to any derivative made by adding to, deleting,
or substituting -- in part or in whole -- any of the components of the
Original Version, by changing formats or by porting the Font Software to a
new environment.

"Author" refers to any designer, engineer, programmer, technical
writer or other person who contributed to the Font Software.

PERMISSION & CONDITIONS
Permission is hereby granted, free of charge, to any person obtaining
a copy of the Font Software, to use, study, copy, merge, embed, modify,
redistribute, and sell modified and unmodified copies of the Font
Software, subject to the following conditions:

1) Neither the Font Software nor any of its individual components,
in Original or Modified Versions, may be sold by itself.

2) Original or Modified Versions of the Font Software may be bundled,
redistributed and/or sold with any software, provided that each copy
contains the above copyright notice and this license. These can be
included either as stand-alone text files, human-readable headers or
in the appropriate machine-readable metadata fields within text or
binary files as long as those fields can be easily viewed by the user.

3) No Modified Version of the Font Software may use the Reserved Font
Name(s) unless explicit written permission is granted by the corresponding
Copyright Holder. This restriction only applies to the primary font name as
presented to the users.

4) The name(s) of the Copyright Holder(s) or the Author(s) of the Font
Software shall not be used to promote, endorse or advertise any
Modified Version, except to acknowledge the contribution(s) of the
Copyright Holder(s) and the Author(s) or with their explicit written
permission.

5) The Font Software, modified or unmodified, in part or in whole,
must be distributed entirely under this license, and must not be
distributed under any other license. The requirement for fonts to
remain under this license does not apply to any document created
using the Font Software.

TERMINATION
This license becomes null and void if any of the above conditions are
not met.

DISCLAIMER
THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT
OF COPYRIGHT, PATENT, TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL THE
COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
INCLUDING ANY GENERAL, SPECIAL, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL
DAMAGES, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF THE USE OR INABILITY TO USE THE FONT SOFTWARE OR FROM
OTHER DEALINGS IN THE FONT SOFTWARE.

````
<!-- /provenance-file -->

<a id="original-589bb5cd74c6"></a>

### `addons/skin.bobbi.cinema/fonts/LICENCE-Mardoto.txt`

<!-- provenance-file {"path": "addons/skin.bobbi.cinema/fonts/LICENCE-Mardoto.txt", "bytes": 12044, "sha256": "5bd41e468075ebba75da768007d24166f67d4e9626e173ce562ab4a95ac4a01c", "newline": "lf"} -->
````text

   Copyright 2011 Google Inc. All Rights Reserved.

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
   
   -------------------------------------------------------------------------

                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

   1. Definitions.

      "License" shall mean the terms and conditions for use, reproduction,
      and distribution as defined by Sections 1 through 9 of this document.

      "Licensor" shall mean the copyright owner or entity authorized by
      the copyright owner that is granting the License.

      "Legal Entity" shall mean the union of the acting entity and all
      other entities that control, are controlled by, or are under common
      control with that entity. For the purposes of this definition,
      "control" means (i) the power, direct or indirect, to cause the
      direction or management of such entity, whether by contract or
      otherwise, or (ii) ownership of fifty percent (50%) or more of the
      outstanding shares, or (iii) beneficial ownership of such entity.

      "You" (or "Your") shall mean an individual or Legal Entity
      exercising permissions granted by this License.

      "Source" form shall mean the preferred form for making modifications,
      including but not limited to software source code, documentation
      source, and configuration files.

      "Object" form shall mean any form resulting from mechanical
      transformation or translation of a Source form, including but
      not limited to compiled object code, generated documentation,
      and conversions to other media types.

      "Work" shall mean the work of authorship, whether in Source or
      Object form, made available under the License, as indicated by a
      copyright notice that is included in or attached to the work
      (an example is provided in the Appendix below).

      "Derivative Works" shall mean any work, whether in Source or Object
      form, that is based on (or derived from) the Work and for which the
      editorial revisions, annotations, elaborations, or other modifications
      represent, as a whole, an original work of authorship. For the purposes
      of this License, Derivative Works shall not include works that remain
      separable from, or merely link (or bind by name) to the interfaces of,
      the Work and Derivative Works thereof.

      "Contribution" shall mean any work of authorship, including
      the original version of the Work and any modifications or additions
      to that Work or Derivative Works thereof, that is intentionally
      submitted to Licensor for inclusion in the Work by the copyright owner
      or by an individual or Legal Entity authorized to submit on behalf of
      the copyright owner. For the purposes of this definition, "submitted"
      means any form of electronic, verbal, or written communication sent
      to the Licensor or its representatives, including but not limited to
      communication on electronic mailing lists, source code control systems,
      and issue tracking systems that are managed by, or on behalf of, the
      Licensor for the purpose of discussing and improving the Work, but
      excluding communication that is conspicuously marked or otherwise
      designated in writing by the copyright owner as "Not a Contribution."

      "Contributor" shall mean Licensor and any individual or Legal Entity
      on behalf of whom a Contribution has been received by Licensor and
      subsequently incorporated within the Work.

   2. Grant of Copyright License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      copyright license to reproduce, prepare Derivative Works of,
      publicly display, publicly perform, sublicense, and distribute the
      Work and such Derivative Works in Source or Object form.

   3. Grant of Patent License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      (except as stated in this section) patent license to make, have made,
      use, offer to sell, sell, import, and otherwise transfer the Work,
      where such license applies only to those patent claims licensable
      by such Contributor that are necessarily infringed by their
      Contribution(s) alone or by combination of their Contribution(s)
      with the Work to which such Contribution(s) was submitted. If You
      institute patent litigation against any entity (including a
      cross-claim or counterclaim in a lawsuit) alleging that the Work
      or a Contribution incorporated within the Work constitutes direct
      or contributory patent infringement, then any patent licenses
      granted to You under this License for that Work shall terminate
      as of the date such litigation is filed.

   4. Redistribution. You may reproduce and distribute copies of the
      Work or Derivative Works thereof in any medium, with or without
      modifications, and in Source or Object form, provided that You
      meet the following conditions:

      (a) You must give any other recipients of the Work or
          Derivative Works a copy of this License; and

      (b) You must cause any modified files to carry prominent notices
          stating that You changed the files; and

      (c) You must retain, in the Source form of any Derivative Works
          that You distribute, all copyright, patent, trademark, and
          attribution notices from the Source form of the Work,
          excluding those notices that do not pertain to any part of
          the Derivative Works; and

      (d) If the Work includes a "NOTICE" text file as part of its
          distribution, then any Derivative Works that You distribute must
          include a readable copy of the attribution notices contained
          within such NOTICE file, excluding those notices that do not
          pertain to any part of the Derivative Works, in at least one
          of the following places: within a NOTICE text file distributed
          as part of the Derivative Works; within the Source form or
          documentation, if provided along with the Derivative Works; or,
          within a display generated by the Derivative Works, if and
          wherever such third-party notices normally appear. The contents
          of the NOTICE file are for informational purposes only and
          do not modify the License. You may add Your own attribution
          notices within Derivative Works that You distribute, alongside
          or as an addendum to the NOTICE text from the Work, provided
          that such additional attribution notices cannot be construed
          as modifying the License.

      You may add Your own copyright statement to Your modifications and
      may provide additional or different license terms and conditions
      for use, reproduction, or distribution of Your modifications, or
      for any such Derivative Works as a whole, provided Your use,
      reproduction, and distribution of the Work otherwise complies with
      the conditions stated in this License.

   5. Submission of Contributions. Unless You explicitly state otherwise,
      any Contribution intentionally submitted for inclusion in the Work
      by You to the Licensor shall be under the terms and conditions of
      this License, without any additional terms or conditions.
      Notwithstanding the above, nothing herein shall supersede or modify
      the terms of any separate license agreement you may have executed
      with Licensor regarding such Contributions.

   6. Trademarks. This License does not grant permission to use the trade
      names, trademarks, service marks, or product names of the Licensor,
      except as required for reasonable and customary use in describing the
      origin of the Work and reproducing the content of the NOTICE file.

   7. Disclaimer of Warranty. Unless required by applicable law or
      agreed to in writing, Licensor provides the Work (and each
      Contributor provides its Contributions) on an "AS IS" BASIS,
      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
      implied, including, without limitation, any warranties or conditions
      of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
      PARTICULAR PURPOSE. You are solely responsible for determining the
      appropriateness of using or redistributing the Work and assume any
      risks associated with Your exercise of permissions under this License.

   8. Limitation of Liability. In no event and under no legal theory,
      whether in tort (including negligence), contract, or otherwise,
      unless required by applicable law (such as deliberate and grossly
      negligent acts) or agreed to in writing, shall any Contributor be
      liable to You for damages, including any direct, indirect, special,
      incidental, or consequential damages of any character arising as a
      result of this License or out of the use or inability to use the
      Work (including but not limited to damages for loss of goodwill,
      work stoppage, computer failure or malfunction, or any and all
      other commercial damages or losses), even if such Contributor
      has been advised of the possibility of such damages.

   9. Accepting Warranty or Additional Liability. While redistributing
      the Work or Derivative Works thereof, You may choose to offer,
      and charge a fee for, acceptance of support, warranty, indemnity,
      or other liability obligations and/or rights consistent with this
      License. However, in accepting such obligations, You may act only
      on Your own behalf and on Your sole responsibility, not on behalf
      of any other Contributor, and only if You agree to indemnify,
      defend, and hold each Contributor harmless for any liability
      incurred by, or claims asserted against, such Contributor by reason
      of your accepting any such warranty or additional liability.

   END OF TERMS AND CONDITIONS

   APPENDIX: How to apply the Apache License to your work.

      To apply the Apache License to your work, attach the following
      boilerplate notice, with the fields enclosed by brackets "[]"
      replaced with your own identifying information. (Don't include
      the brackets!)  The text should be enclosed in the appropriate
      comment syntax for the file format. We also recommend that a
      file or class name and description of purpose be included on the
      same "printed page" as the copyright notice for easier
      identification within third-party archives.

   Copyright [yyyy] [name of copyright owner]

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.


````
<!-- /provenance-file -->

<a id="original-eceb253430d9"></a>

### `addons/skin.bobbi.cinema/fonts/LICENCE-OFL.txt`

<!-- provenance-file {"path": "addons/skin.bobbi.cinema/fonts/LICENCE-OFL.txt", "bytes": 4395, "sha256": "4bd805bb254c8b69c26addf1e100c745ec09e2737ec624b722bd509ea9ae240a", "newline": "lf"} -->
````text
Copyright 2011 Google Inc. All Rights Reserved.
© 2014-2019 Adobe (http://www.adobe.com/).

This Font Software is licensed under the SIL Open Font License, Version 1.1.
This license is copied below, and is also available with a FAQ at:
http://scripts.sil.org/OFL


-----------------------------------------------------------
SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007
-----------------------------------------------------------

PREAMBLE
The goals of the Open Font License (OFL) are to stimulate worldwide
development of collaborative font projects, to support the font creation
efforts of academic and linguistic communities, and to provide a free and
open framework in which fonts may be shared and improved in partnership
with others.

The OFL allows the licensed fonts to be used, studied, modified and
redistributed freely as long as they are not sold by themselves. The
fonts, including any derivative works, can be bundled, embedded, 
redistributed and/or sold with any software provided that any reserved
names are not used by derivative works. The fonts and derivatives,
however, cannot be released under any other type of license. The
requirement for fonts to remain under this license does not apply
to any document created using the fonts or their derivatives.

DEFINITIONS
"Font Software" refers to the set of files released by the Copyright
Holder(s) under this license and clearly marked as such. This may
include source files, build scripts and documentation.

"Reserved Font Name" refers to any names specified as such after the
copyright statement(s).

"Original Version" refers to the collection of Font Software components as
distributed by the Copyright Holder(s).

"Modified Version" refers to any derivative made by adding to, deleting,
or substituting -- in part or in whole -- any of the components of the
Original Version, by changing formats or by porting the Font Software to a
new environment.

"Author" refers to any designer, engineer, programmer, technical
writer or other person who contributed to the Font Software.

PERMISSION & CONDITIONS
Permission is hereby granted, free of charge, to any person obtaining
a copy of the Font Software, to use, study, copy, merge, embed, modify,
redistribute, and sell modified and unmodified copies of the Font
Software, subject to the following conditions:

1) Neither the Font Software nor any of its individual components,
in Original or Modified Versions, may be sold by itself.

2) Original or Modified Versions of the Font Software may be bundled,
redistributed and/or sold with any software, provided that each copy
contains the above copyright notice and this license. These can be
included either as stand-alone text files, human-readable headers or
in the appropriate machine-readable metadata fields within text or
binary files as long as those fields can be easily viewed by the user.

3) No Modified Version of the Font Software may use the Reserved Font
Name(s) unless explicit written permission is granted by the corresponding
Copyright Holder. This restriction only applies to the primary font name as
presented to the users.

4) The name(s) of the Copyright Holder(s) or the Author(s) of the Font
Software shall not be used to promote, endorse or advertise any
Modified Version, except to acknowledge the contribution(s) of the
Copyright Holder(s) and the Author(s) or with their explicit written
permission.

5) The Font Software, modified or unmodified, in part or in whole,
must be distributed entirely under this license, and must not be
distributed under any other license. The requirement for fonts to
remain under this license does not apply to any document created
using the Font Software.

TERMINATION
This license becomes null and void if any of the above conditions are
not met.

DISCLAIMER
THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT
OF COPYRIGHT, PATENT, TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL THE
COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
INCLUDING ANY GENERAL, SPECIAL, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL
DAMAGES, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF THE USE OR INABILITY TO USE THE FONT SOFTWARE OR FROM
OTHER DEALINGS IN THE FONT SOFTWARE.

````
<!-- /provenance-file -->

<a id="original-5c7af4c96324"></a>

### `addons/skin.bobbi.cinema/fonts/LICENCE-Roboto.txt`

<!-- provenance-file {"path": "addons/skin.bobbi.cinema/fonts/LICENCE-Roboto.txt", "bytes": 12044, "sha256": "5bd41e468075ebba75da768007d24166f67d4e9626e173ce562ab4a95ac4a01c", "newline": "lf"} -->
````text

   Copyright 2011 Google Inc. All Rights Reserved.

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
   
   -------------------------------------------------------------------------

                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

   1. Definitions.

      "License" shall mean the terms and conditions for use, reproduction,
      and distribution as defined by Sections 1 through 9 of this document.

      "Licensor" shall mean the copyright owner or entity authorized by
      the copyright owner that is granting the License.

      "Legal Entity" shall mean the union of the acting entity and all
      other entities that control, are controlled by, or are under common
      control with that entity. For the purposes of this definition,
      "control" means (i) the power, direct or indirect, to cause the
      direction or management of such entity, whether by contract or
      otherwise, or (ii) ownership of fifty percent (50%) or more of the
      outstanding shares, or (iii) beneficial ownership of such entity.

      "You" (or "Your") shall mean an individual or Legal Entity
      exercising permissions granted by this License.

      "Source" form shall mean the preferred form for making modifications,
      including but not limited to software source code, documentation
      source, and configuration files.

      "Object" form shall mean any form resulting from mechanical
      transformation or translation of a Source form, including but
      not limited to compiled object code, generated documentation,
      and conversions to other media types.

      "Work" shall mean the work of authorship, whether in Source or
      Object form, made available under the License, as indicated by a
      copyright notice that is included in or attached to the work
      (an example is provided in the Appendix below).

      "Derivative Works" shall mean any work, whether in Source or Object
      form, that is based on (or derived from) the Work and for which the
      editorial revisions, annotations, elaborations, or other modifications
      represent, as a whole, an original work of authorship. For the purposes
      of this License, Derivative Works shall not include works that remain
      separable from, or merely link (or bind by name) to the interfaces of,
      the Work and Derivative Works thereof.

      "Contribution" shall mean any work of authorship, including
      the original version of the Work and any modifications or additions
      to that Work or Derivative Works thereof, that is intentionally
      submitted to Licensor for inclusion in the Work by the copyright owner
      or by an individual or Legal Entity authorized to submit on behalf of
      the copyright owner. For the purposes of this definition, "submitted"
      means any form of electronic, verbal, or written communication sent
      to the Licensor or its representatives, including but not limited to
      communication on electronic mailing lists, source code control systems,
      and issue tracking systems that are managed by, or on behalf of, the
      Licensor for the purpose of discussing and improving the Work, but
      excluding communication that is conspicuously marked or otherwise
      designated in writing by the copyright owner as "Not a Contribution."

      "Contributor" shall mean Licensor and any individual or Legal Entity
      on behalf of whom a Contribution has been received by Licensor and
      subsequently incorporated within the Work.

   2. Grant of Copyright License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      copyright license to reproduce, prepare Derivative Works of,
      publicly display, publicly perform, sublicense, and distribute the
      Work and such Derivative Works in Source or Object form.

   3. Grant of Patent License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      (except as stated in this section) patent license to make, have made,
      use, offer to sell, sell, import, and otherwise transfer the Work,
      where such license applies only to those patent claims licensable
      by such Contributor that are necessarily infringed by their
      Contribution(s) alone or by combination of their Contribution(s)
      with the Work to which such Contribution(s) was submitted. If You
      institute patent litigation against any entity (including a
      cross-claim or counterclaim in a lawsuit) alleging that the Work
      or a Contribution incorporated within the Work constitutes direct
      or contributory patent infringement, then any patent licenses
      granted to You under this License for that Work shall terminate
      as of the date such litigation is filed.

   4. Redistribution. You may reproduce and distribute copies of the
      Work or Derivative Works thereof in any medium, with or without
      modifications, and in Source or Object form, provided that You
      meet the following conditions:

      (a) You must give any other recipients of the Work or
          Derivative Works a copy of this License; and

      (b) You must cause any modified files to carry prominent notices
          stating that You changed the files; and

      (c) You must retain, in the Source form of any Derivative Works
          that You distribute, all copyright, patent, trademark, and
          attribution notices from the Source form of the Work,
          excluding those notices that do not pertain to any part of
          the Derivative Works; and

      (d) If the Work includes a "NOTICE" text file as part of its
          distribution, then any Derivative Works that You distribute must
          include a readable copy of the attribution notices contained
          within such NOTICE file, excluding those notices that do not
          pertain to any part of the Derivative Works, in at least one
          of the following places: within a NOTICE text file distributed
          as part of the Derivative Works; within the Source form or
          documentation, if provided along with the Derivative Works; or,
          within a display generated by the Derivative Works, if and
          wherever such third-party notices normally appear. The contents
          of the NOTICE file are for informational purposes only and
          do not modify the License. You may add Your own attribution
          notices within Derivative Works that You distribute, alongside
          or as an addendum to the NOTICE text from the Work, provided
          that such additional attribution notices cannot be construed
          as modifying the License.

      You may add Your own copyright statement to Your modifications and
      may provide additional or different license terms and conditions
      for use, reproduction, or distribution of Your modifications, or
      for any such Derivative Works as a whole, provided Your use,
      reproduction, and distribution of the Work otherwise complies with
      the conditions stated in this License.

   5. Submission of Contributions. Unless You explicitly state otherwise,
      any Contribution intentionally submitted for inclusion in the Work
      by You to the Licensor shall be under the terms and conditions of
      this License, without any additional terms or conditions.
      Notwithstanding the above, nothing herein shall supersede or modify
      the terms of any separate license agreement you may have executed
      with Licensor regarding such Contributions.

   6. Trademarks. This License does not grant permission to use the trade
      names, trademarks, service marks, or product names of the Licensor,
      except as required for reasonable and customary use in describing the
      origin of the Work and reproducing the content of the NOTICE file.

   7. Disclaimer of Warranty. Unless required by applicable law or
      agreed to in writing, Licensor provides the Work (and each
      Contributor provides its Contributions) on an "AS IS" BASIS,
      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
      implied, including, without limitation, any warranties or conditions
      of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
      PARTICULAR PURPOSE. You are solely responsible for determining the
      appropriateness of using or redistributing the Work and assume any
      risks associated with Your exercise of permissions under this License.

   8. Limitation of Liability. In no event and under no legal theory,
      whether in tort (including negligence), contract, or otherwise,
      unless required by applicable law (such as deliberate and grossly
      negligent acts) or agreed to in writing, shall any Contributor be
      liable to You for damages, including any direct, indirect, special,
      incidental, or consequential damages of any character arising as a
      result of this License or out of the use or inability to use the
      Work (including but not limited to damages for loss of goodwill,
      work stoppage, computer failure or malfunction, or any and all
      other commercial damages or losses), even if such Contributor
      has been advised of the possibility of such damages.

   9. Accepting Warranty or Additional Liability. While redistributing
      the Work or Derivative Works thereof, You may choose to offer,
      and charge a fee for, acceptance of support, warranty, indemnity,
      or other liability obligations and/or rights consistent with this
      License. However, in accepting such obligations, You may act only
      on Your own behalf and on Your sole responsibility, not on behalf
      of any other Contributor, and only if You agree to indemnify,
      defend, and hold each Contributor harmless for any liability
      incurred by, or claims asserted against, such Contributor by reason
      of your accepting any such warranty or additional liability.

   END OF TERMS AND CONDITIONS

   APPENDIX: How to apply the Apache License to your work.

      To apply the Apache License to your work, attach the following
      boilerplate notice, with the fields enclosed by brackets "[]"
      replaced with your own identifying information. (Don't include
      the brackets!)  The text should be enclosed in the appropriate
      comment syntax for the file format. We also recommend that a
      file or class name and description of purpose be included on the
      same "printed page" as the copyright notice for easier
      identification within third-party archives.

   Copyright [yyyy] [name of copyright owner]

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.


````
<!-- /provenance-file -->

<a id="original-ba4adef5823f"></a>

### `addons/skin.bobbi.cinema/fonts/README.txt`

<!-- provenance-file {"path": "addons/skin.bobbi.cinema/fonts/README.txt", "bytes": 797, "sha256": "05eb4a16bfca6f591e8ed38be8441c57dee0c80dd9e5aa06df81ac16e2102cd3", "newline": "lf"} -->
````text
   Copyright 2011 Google Inc. All Rights Reserved.

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

------------------------------------------------------------------------

This directory contains the fonts for the platform.

Source: https://github.com/google/fonts/tree/master/apache/roboto

````
<!-- /provenance-file -->

<a id="original-56cf4e8f617e"></a>

### `addons/skin.bobbi.cinema/fonts/fontawesome-free-6.7.2-LICENSE.txt`

<!-- provenance-file {"path": "addons/skin.bobbi.cinema/fonts/fontawesome-free-6.7.2-LICENSE.txt", "bytes": 7427, "sha256": "9b914eae88817d63b576eab5aafde7068c7a1abae125d7cdfb034f1da43a9afc", "newline": "lf"} -->
````text
Fonticons, Inc. (https://fontawesome.com)

--------------------------------------------------------------------------------

Font Awesome Free License

Font Awesome Free is free, open source, and GPL friendly. You can use it for
commercial projects, open source projects, or really almost whatever you want.
Full Font Awesome Free license: https://fontawesome.com/license/free.

--------------------------------------------------------------------------------

# Icons: CC BY 4.0 License (https://creativecommons.org/licenses/by/4.0/)

The Font Awesome Free download is licensed under a Creative Commons
Attribution 4.0 International License and applies to all icons packaged
as SVG and JS file types.

--------------------------------------------------------------------------------

# Fonts: SIL OFL 1.1 License

In the Font Awesome Free download, the SIL OFL license applies to all icons
packaged as web and desktop font files.

Copyright (c) 2024 Fonticons, Inc. (https://fontawesome.com)
with Reserved Font Name: "Font Awesome".

This Font Software is licensed under the SIL Open Font License, Version 1.1.
This license is copied below, and is also available with a FAQ at:
http://scripts.sil.org/OFL

SIL OPEN FONT LICENSE
Version 1.1 - 26 February 2007

PREAMBLE
The goals of the Open Font License (OFL) are to stimulate worldwide
development of collaborative font projects, to support the font creation
efforts of academic and linguistic communities, and to provide a free and
open framework in which fonts may be shared and improved in partnership
with others.

The OFL allows the licensed fonts to be used, studied, modified and
redistributed freely as long as they are not sold by themselves. The
fonts, including any derivative works, can be bundled, embedded,
redistributed and/or sold with any software provided that any reserved
names are not used by derivative works. The fonts and derivatives,
however, cannot be released under any other type of license. The
requirement for fonts to remain under this license does not apply
to any document created using the fonts or their derivatives.

DEFINITIONS
"Font Software" refers to the set of files released by the Copyright
Holder(s) under this license and clearly marked as such. This may
include source files, build scripts and documentation.

"Reserved Font Name" refers to any names specified as such after the
copyright statement(s).

"Original Version" refers to the collection of Font Software components as
distributed by the Copyright Holder(s).

"Modified Version" refers to any derivative made by adding to, deleting,
or substituting — in part or in whole — any of the components of the
Original Version, by changing formats or by porting the Font Software to a
new environment.

"Author" refers to any designer, engineer, programmer, technical
writer or other person who contributed to the Font Software.

PERMISSION & CONDITIONS
Permission is hereby granted, free of charge, to any person obtaining
a copy of the Font Software, to use, study, copy, merge, embed, modify,
redistribute, and sell modified and unmodified copies of the Font
Software, subject to the following conditions:

1) Neither the Font Software nor any of its individual components,
in Original or Modified Versions, may be sold by itself.

2) Original or Modified Versions of the Font Software may be bundled,
redistributed and/or sold with any software, provided that each copy
contains the above copyright notice and this license. These can be
included either as stand-alone text files, human-readable headers or
in the appropriate machine-readable metadata fields within text or
binary files as long as those fields can be easily viewed by the user.

3) No Modified Version of the Font Software may use the Reserved Font
Name(s) unless explicit written permission is granted by the corresponding
Copyright Holder. This restriction only applies to the primary font name as
presented to the users.

4) The name(s) of the Copyright Holder(s) or the Author(s) of the Font
Software shall not be used to promote, endorse or advertise any
Modified Version, except to acknowledge the contribution(s) of the
Copyright Holder(s) and the Author(s) or with their explicit written
permission.

5) The Font Software, modified or unmodified, in part or in whole,
must be distributed entirely under this license, and must not be
distributed under any other license. The requirement for fonts to
remain under this license does not apply to any document created
using the Font Software.

TERMINATION
This license becomes null and void if any of the above conditions are
not met.

DISCLAIMER
THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT
OF COPYRIGHT, PATENT, TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL THE
COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
INCLUDING ANY GENERAL, SPECIAL, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL
DAMAGES, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF THE USE OR INABILITY TO USE THE FONT SOFTWARE OR FROM
OTHER DEALINGS IN THE FONT SOFTWARE.

--------------------------------------------------------------------------------

# Code: MIT License (https://opensource.org/licenses/MIT)

In the Font Awesome Free download, the MIT license applies to all non-font and
non-icon files.

Copyright 2024 Fonticons, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in the
Software without restriction, including without limitation the rights to use, copy,
modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
and to permit persons to whom the Software is furnished to do so, subject to the
following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

--------------------------------------------------------------------------------

# Attribution

Attribution is required by MIT, SIL OFL, and CC BY licenses. Downloaded Font
Awesome Free files already contain embedded comments with sufficient
attribution, so you shouldn't need to do anything additional when using these
files normally.

We've kept attribution comments terse, so we ask that you do not actively work
to remove them from files, especially code. They're a great way for folks to
learn about Font Awesome.

--------------------------------------------------------------------------------

# Brand Icons

All brand icons are trademarks of their respective owners. The use of these
trademarks does not indicate endorsement of the trademark holder by Font
Awesome, nor vice versa. **Please do not use brand logos for any purpose except
to represent the company, product, or service to which they refer.**

````
<!-- /provenance-file -->

<a id="original-fc0639e1062d"></a>

### `assets/fonts/LICENCE-HarmonyOS-Sans.txt`

<!-- provenance-file {"path": "assets/fonts/LICENCE-HarmonyOS-Sans.txt", "bytes": 3352, "sha256": "327e0147d4a3ca2d89e81abce45b210576b0f9fe2b29d900f64b58039f12a102", "newline": "crlf"} -->
````text
License Notice
Copyright 2021 Huawei Device Co., Ltd.
HarmonyOS Sans Fonts Software is licensed under HarmonyOS Sans Fonts License Agreement.

--------------------------------------------------------------------------------
HarmonyOS Sans Fonts License Agreement

THIS HARMONYOS SANS FONTS LICENSE AGREEMENT ("AGREEMENT") IS A LEGAL AGREEMENT BETWEEN YOU (EITHER A SINGLE INDIVIDUAL, OR SINGLE LEGAL ENTITY) AND HUAWEI DEVICE CO., LTD.( "LICENSOR")FOR THE USE OF THE HARMONYOS SANS FONTS ACCOMPANYING THIS AGREEMENT.BY DOWNLOADING,COPYING OR OTHERWISE USING HARMONYOS SANS FONTS YOU INDICATE THAT YOU AGREE TO BE BOUND BY ALL OF THE TERMS OF THIS AGREEMENT. IF YOU DO NOT AGREE TO THE TERMS OF THIS AGREEMENT, YOU MAY NOT DOWNLOAD, COPY OR OTHERWISE USE THE HARMONYOS SANS FONTS, AND YOU SHALL PROMPTLY DESTROY AND DELETE ALL THE HARMONYOS SANS FONTS.

1.Definition
"HarmonyOS Sans Fonts" shall mean the collection of fonts software components provided by Licensor under this Agreement and clearly marked as "HarmonyOS¬ Sans".

"YOU" shall mean an individual or legal entity exercising permissions granted by this Agreement.

2.GRANT OF LICENSE

Subject to the terms and conditions of this Agreement, Licensor hereby grant YOU a non-transferable, non-exclusive, royalty-free, revocable, worldwide copyright license to use,copy, merge, embed, bundle, redistribute and/or sell unmodified copies of HarmonyOS Sans Fonts with any software except for fonts software，subject to the  following conditions:
1)YOU shall make a prominent notice in the software to state that HarmonyOS Sans Fonts are used.
2)YOU may not make any modifications to HarmonyOS Sans Fonts or any of their individual components.
3)Neither HarmonyOS Sans Fonts nor any of their individual components may be redistributed or sold in a stand-alone base. This limitation does not apply to any work created by using HarmonyOS Sans Fonts. You can freely distribute or sell your work, such as materials, logos, application software etc. created by using HarmonyOS Sans Fonts.
4)YOU shall retain the copyright notice and this Agreement in any copies of HarmonyOS Sans Fonts.

3.Termination
This Agreement will be automatically terminated if YOU breach any of this Agreement.

4.NO WARRANTY
YOU AGREE THAT THE HARMONYOS SANS FONTS ARE PROVIDED BY LICENSOR ON AN "AS IS" BASIS. LICENSOR MAKES NO WARRANTY, EXPRESSED OR IMPLIED OR STATUTORY, WITH RESPECT TO ANY OF THE HARMONYOS SANS FONTS, INCLUDING WITHOUT LIMITATION, ANY IMPLIED WARRANTIES OF MERCHANTABILITY, SATISFACTORY QUALITY, FITNESS FOR A PARTICULAR PURPOSE OR NON-INFRINGEMENT.

5.NO LIABILITY

IN NO EVENT SHALL LICENSOR BE LIABLE FOR ANY DIRECT OR INDIRECT, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES (INCLUDING WITHOUT LIMITATION, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) ARISING IN ANY WAY OUT OF THE USE OF OR INABILITY TO USE HARMONYOS SANS FONTS, WHETHER UNDER THEORY OF CONTRACT, TORT (INCLUDING NEGLIGENCE), STRICT LIABILITY OR OTHER LEGAL THEORY, EVEN IF LICENSOR HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

YOU EXPRESSLY ASSUME ALL LIABILITIES AND RISKS FOR USE OF HARMONYOS SANS FONTS. SHOULD THE HARMONYOS SANS FONTS PROVE DEFECTIVE, YOU ASSUME THE ENTIRE COST OF ALL NECESSARY SERVICING, REPAIR OR CORRECTION.


````
<!-- /provenance-file -->

<a id="original-b9d8a4de92d1"></a>

### `licenses/THIRD-PARTY.json`

<!-- provenance-file {"path": "licenses/THIRD-PARTY.json", "bytes": 10839, "sha256": "674a45a88273af7221de3a18076828be44b633f76694564ea8d7501f296e91a1", "newline": "lf"} -->
````json
{
  "schema": 1,
  "scope": "Dependency notices for the public bobbi TV fork; not blanket code or asset clearance",
  "baseline": "a9189b5d157d886c814cf28c6748c97fc6825a35",
  "policy": {
    "licenses_are_component_specific": true,
    "original_ui_and_catalog_intended": true,
    "optional_sanitized_skin_not_adopted": true,
    "catalog_and_share_codes_user_authorized": true,
    "account_credentials_excluded": true,
    "restricted_font_binaries_require_grants": true,
    "metadata_is_not_a_full_license_notice": true
  },
  "documents": [
    {
      "id": "segno-license",
      "kind": "full-license",
      "file": "licenses/vendor/segno-1.6.6-LICENSE.txt",
      "repository": "heuer/segno",
      "commit": "9b67a3f2914be966c35dd8f00bef19d01b9ec68e",
      "source_path": "LICENSE",
      "source_url": "https://raw.githubusercontent.com/heuer/segno/9b67a3f2914be966c35dd8f00bef19d01b9ec68e/LICENSE",
      "git_blob_sha": "b80a6f00a80131459a91e9389c52dafaeea066bc",
      "sha256": "de6c85fccf5d52902aa13dfe2dc6d2a2a106fc3419ed438f3460f0d4b76a6935",
      "bytes": 1503
    },
    {
      "id": "xmltodict-license",
      "kind": "full-license",
      "file": "licenses/vendor/xmltodict-0.13.0-LICENSE.txt",
      "repository": "martinblech/xmltodict",
      "commit": "096db4ad337e4168ef891551814cdd829716192b",
      "source_path": "LICENSE",
      "source_url": "https://raw.githubusercontent.com/martinblech/xmltodict/096db4ad337e4168ef891551814cdd829716192b/LICENSE",
      "git_blob_sha": "a462778cff0f3fef0d450d05413f047a759ff950",
      "sha256": "d66d5eb8f83a0ba21d3dd04318b8817588e8764daabea852d1035e3f07ffda55",
      "bytes": 1085
    },
    {
      "id": "torf-license",
      "kind": "full-license",
      "file": "licenses/vendor/torf-4.2.0-LICENSE.txt",
      "repository": "rndusr/torf",
      "commit": "8eaeee7871eeb52c76a03558b183d60aa806a6d3",
      "source_path": "LICENSE",
      "source_url": "https://raw.githubusercontent.com/rndusr/torf/8eaeee7871eeb52c76a03558b183d60aa806a6d3/LICENSE",
      "git_blob_sha": "f288702d2fa16d3cdf0035b15a9fcbc552cd88e7",
      "sha256": "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986",
      "bytes": 35149
    },
    {
      "id": "flatbencode-license",
      "kind": "full-license",
      "file": "licenses/vendor/flatbencode-0.2.1-LICENSE.txt",
      "repository": "acatton/flatbencode",
      "commit": "f445a7eee6b6cd8bf5911f869014c805f3df5d62",
      "source_path": "LICENSE",
      "source_url": "https://raw.githubusercontent.com/acatton/flatbencode/f445a7eee6b6cd8bf5911f869014c805f3df5d62/LICENSE",
      "git_blob_sha": "db9cf41cfd1192ed9209b4db7198e27347ebf4e1",
      "sha256": "65f3400a83066b1e82f6114df0b64028880860e8d89d6da4237e0f31e0066dbd",
      "bytes": 1082
    },
    {
      "id": "jacktook-license",
      "kind": "full-license",
      "file": "licenses/vendor/jacktook-upstream-LICENSE.txt",
      "repository": "Sam-Max/plugin.video.jacktook",
      "commit": "2e70c70ed6c20006eda99fd557108d31c75cb953",
      "source_path": "LICENSE",
      "source_url": "https://raw.githubusercontent.com/Sam-Max/plugin.video.jacktook/2e70c70ed6c20006eda99fd557108d31c75cb953/LICENSE",
      "git_blob_sha": "e62ec04cdeece724caeeeeaeb6ae1f6af1bb6b9a",
      "sha256": "605e9047a563c5c8396ffb18232aa4304ec56586aee537c45064c6fb425e44ad",
      "bytes": 35129
    },
    {
      "id": "tmdbv3api-metadata",
      "kind": "metadata-evidence-not-license",
      "file": "licenses/vendor/tmdbv3api-1.9.0-setup-evidence.txt",
      "repository": "AnthonyBloomer/tmdbv3api",
      "commit": "c5e96af23494b6b5506e84ed3b0be626ee25cb26",
      "source_path": "setup.py",
      "source_url": "https://raw.githubusercontent.com/AnthonyBloomer/tmdbv3api/c5e96af23494b6b5506e84ed3b0be626ee25cb26/setup.py",
      "git_blob_sha": "d9afbee25fedab8e8b032b833bcc082a488be0a7",
      "sha256": "42fde0503d50bc327052cd3efd323a724326cd503b4058023791f46b79e045ee",
      "bytes": 2316
    }
  ],
  "components": [
    {
      "id": "segno",
      "version": "1.6.6",
      "upstream_ref": "1.6.6",
      "license": "BSD-3-Clause",
      "documents": ["segno-license"],
      "status": "full-upstream-license-retained-local-modifications",
      "baseline_evidence": {
        "path": "plugin.video.bobbi/lib/vendor/segno/__init__.py",
        "sha256": "d6fec9545c9e5f4738f56d74940d4874dfaa78b2bb8180d463035679284995ae",
        "upstream_path": "segno/__init__.py",
        "upstream_sha256": "e436a1f5aa93f7ac7fa3be1f0ea98e04a792d218dfec385f595adb88dc43d2e6"
      },
      "notes": "Vendored __version__ is 1.6.6, but this is not a byte-identical package: formatting/import/export ordering changes and removed convenience functions were observed. Original per-file 2016-2024 copyright notices remain; upstream tag's full license also contains 2016-2025 attribution. No whole-tree equivalence claim."
    },
    {
      "id": "xmltodict",
      "version": "0.13.0",
      "upstream_ref": "v0.13.0",
      "license": "MIT",
      "documents": ["xmltodict-license"],
      "status": "full-upstream-license-retained-local-modifications",
      "baseline_evidence": {
        "path": "plugin.video.bobbi/lib/utils/parsers/xmltodict.py",
        "sha256": "1850a53148146bb6bcd87a9b3d4c599827d2ef23a4340cba19959d285ea0127f",
        "upstream_path": "xmltodict.py",
        "upstream_sha256": "578a76d3737a2c01d93156df140189e8e3dab03ba5e8c02746bc515a7200fd0a"
      },
      "notes": "Vendored version/author/license declarations identify upstream. Local code also changes item_depth/whitespace behavior and integer-indent handling, so do not call it an unmodified upstream release. Retain Martin Blech and contributor notices."
    },
    {
      "id": "torf",
      "version": "4.2.0",
      "upstream_ref": "v4.2.0",
      "license": "GPL-3.0-or-later",
      "documents": ["torf-license"],
      "status": "full-upstream-license-retained",
      "baseline_evidence": {
        "path": "plugin.video.bobbi/lib/vendor/torf/__init__.py",
        "sha256": "7e259f4a8c8f95275fee64d2769ceabcb84ae970c718ee286d44b7a86063c12e",
        "upstream_path": "torf/__init__.py",
        "upstream_sha256": "66a331b5996c6ab28bf8f1725c86abc2759289708d2b10bcb20d661d7f128ada"
      },
      "notes": "Explicit per-file GPL version 3-or-later grant retained. __init__ AST matches upstream with quote formatting changed; no unverified whole-tree equivalence assertion."
    },
    {
      "id": "flatbencode",
      "version": "0.2.1-derived",
      "upstream_ref": "v0.2.1",
      "license": "MIT",
      "documents": ["flatbencode-license"],
      "status": "full-upstream-license-retained-replacement-candidate",
      "baseline_evidence": {
        "path": "plugin.video.bobbi/lib/utils/torrent/flatbencode.py",
        "sha256": "0fe508ff298c29f3af9e5d15d216407c1b018da69e7ba8412c676278db322b66",
        "upstream_path": "flatbencode.py",
        "upstream_sha256": "e557cb61db1d2448be6ed6725989edee72396162a1ae03eb853d27112112830b"
      },
      "notes": "Derived from Antoine Catton's MIT code. Observed differences: formatting, __all__ order, dictionary-key iteration and f-string conversion. This is a licensed replacement candidate for bencodepy, not evidence that the runtime import has already been switched or behavior validated."
    },
    {
      "id": "tmdbv3api",
      "version": "1.9.0-reference-with-local-adaptations",
      "upstream_ref": "1.9.0",
      "license": "MIT (upstream metadata declaration; full notice not found)",
      "documents": ["tmdbv3api-metadata"],
      "status": "unresolved-full-upstream-notice-missing",
      "baseline_evidence": {
        "path": "plugin.video.bobbi/lib/api/tmdbv3api/__init__.py",
        "sha256": "5732e752ff0837a4fc34287b7de70a869a13dc6a4bb81fba022ac531c60ebf66",
        "upstream_path": "tmdbv3api/__init__.py",
        "upstream_sha256": "5732e752ff0837a4fc34287b7de70a869a13dc6a4bb81fba022ac531c60ebf66"
      },
      "notes": "__init__.py matches official 1.9.0 bytes, but API objects/transport are locally adapted; exact package-wide version not proved. Official tag tree has no full LICENSE/NOTICE; setup.py and PyPI declare MIT. Official 1.9.0 wheel has no license/notice entries. Do not fabricate a complete MIT text with guessed attribution or present setup.py as a license grant. Obtain full upstream notice/clarification or replace before claiming notice closure.",
      "pypi_wheel_sha256": "2bcd8c6e8902397860715a71045f200ecc3ee06804ecf786cb4c1e09b2deeba8"
    },
    {
      "id": "jacktook-derived-code",
      "version": "baseline-1.20.0+am6b.317",
      "license": "upstream GPL version 3 LICENSE; conflicting GPL-2.0-only addon metadata",
      "documents": ["jacktook-license"],
      "status": "original-license-preserved-metadata-discrepancy-recorded",
      "baseline_evidence": {
        "path": "plugin.video.bobbi/LICENSE",
        "sha256": "605e9047a563c5c8396ffb18232aa4304ec56586aee537c45064c6fb425e44ad",
        "upstream_path": "LICENSE",
        "upstream_sha256": "605e9047a563c5c8396ffb18232aa4304ec56586aee537c45064c6fb425e44ad"
      },
      "notes": "The pinned upstream LICENSE is identical to baseline's and upstream addon.xml itself also declares GPL-2.0-only. Preserve source/credits and explicitly document public-fork metadata correction based on the GPL3 source grant. Do not blanket-relicense independently licensed dependencies, fonts, or CC artwork. The pinned upstream commit proves license content, not whole baseline source equivalence. Extracted shared core retains inherited source notices."
    },
    {
      "id": "bencodepy-legacy",
      "version": "unresolved-vendored-copy",
      "license": "BitTorrent Open Source License version 1.1 (vendored header)",
      "documents": [],
      "status": "unresolved-remove-or-review-before-distribution",
      "notes": "Baseline actively imports lib.vendor.bencodepy in torrserver_utils. Its header is not MIT and must not be relabeled. Full provenance/compatibility is not established by this audit. Prefer separately verified flatbencode after explicit import replacement and behavioral tests."
    }
  ],
  "release_gates": [
    "tmdbv3api full upstream notice/clarification remains unresolved",
    "Confirm removal/replacement of legacy bencodepy before claiming a GPL-clean aggregate",
    "Retain inherited shared-core source notices and resolve optional-module ownership separately",
    "Arctic Fuse artwork remains CC-BY-NC-SA-4.0 independently of code license",
    "Original proprietary font binaries need evidence of redistribution grants; user intent alone is not a grant",
    "Bundled TorrServer binaries need their own corresponding-source/build provenance closure",
    "Notices do not certify third-party media rights, stock Kodi playback, or Android device behavior"
  ]
}

````
<!-- /provenance-file -->

<a id="original-90145fd1f1a6"></a>

### `licenses/vendor/flatbencode-0.2.1-LICENSE.txt`

<!-- provenance-file {"path": "licenses/vendor/flatbencode-0.2.1-LICENSE.txt", "bytes": 1082, "sha256": "65f3400a83066b1e82f6114df0b64028880860e8d89d6da4237e0f31e0066dbd", "newline": "lf"} -->
````text
The MIT License (MIT)

Copyright (c) 2016, Antoine Catton

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

````
<!-- /provenance-file -->

<a id="original-b34ef5bd2689"></a>

### `licenses/vendor/fontawesome-free-6.7.2-LICENSE.txt`

<!-- provenance-file {"path": "licenses/vendor/fontawesome-free-6.7.2-LICENSE.txt", "bytes": 7427, "sha256": "9b914eae88817d63b576eab5aafde7068c7a1abae125d7cdfb034f1da43a9afc", "newline": "lf"} -->
````text
Fonticons, Inc. (https://fontawesome.com)

--------------------------------------------------------------------------------

Font Awesome Free License

Font Awesome Free is free, open source, and GPL friendly. You can use it for
commercial projects, open source projects, or really almost whatever you want.
Full Font Awesome Free license: https://fontawesome.com/license/free.

--------------------------------------------------------------------------------

# Icons: CC BY 4.0 License (https://creativecommons.org/licenses/by/4.0/)

The Font Awesome Free download is licensed under a Creative Commons
Attribution 4.0 International License and applies to all icons packaged
as SVG and JS file types.

--------------------------------------------------------------------------------

# Fonts: SIL OFL 1.1 License

In the Font Awesome Free download, the SIL OFL license applies to all icons
packaged as web and desktop font files.

Copyright (c) 2024 Fonticons, Inc. (https://fontawesome.com)
with Reserved Font Name: "Font Awesome".

This Font Software is licensed under the SIL Open Font License, Version 1.1.
This license is copied below, and is also available with a FAQ at:
http://scripts.sil.org/OFL

SIL OPEN FONT LICENSE
Version 1.1 - 26 February 2007

PREAMBLE
The goals of the Open Font License (OFL) are to stimulate worldwide
development of collaborative font projects, to support the font creation
efforts of academic and linguistic communities, and to provide a free and
open framework in which fonts may be shared and improved in partnership
with others.

The OFL allows the licensed fonts to be used, studied, modified and
redistributed freely as long as they are not sold by themselves. The
fonts, including any derivative works, can be bundled, embedded,
redistributed and/or sold with any software provided that any reserved
names are not used by derivative works. The fonts and derivatives,
however, cannot be released under any other type of license. The
requirement for fonts to remain under this license does not apply
to any document created using the fonts or their derivatives.

DEFINITIONS
"Font Software" refers to the set of files released by the Copyright
Holder(s) under this license and clearly marked as such. This may
include source files, build scripts and documentation.

"Reserved Font Name" refers to any names specified as such after the
copyright statement(s).

"Original Version" refers to the collection of Font Software components as
distributed by the Copyright Holder(s).

"Modified Version" refers to any derivative made by adding to, deleting,
or substituting — in part or in whole — any of the components of the
Original Version, by changing formats or by porting the Font Software to a
new environment.

"Author" refers to any designer, engineer, programmer, technical
writer or other person who contributed to the Font Software.

PERMISSION & CONDITIONS
Permission is hereby granted, free of charge, to any person obtaining
a copy of the Font Software, to use, study, copy, merge, embed, modify,
redistribute, and sell modified and unmodified copies of the Font
Software, subject to the following conditions:

1) Neither the Font Software nor any of its individual components,
in Original or Modified Versions, may be sold by itself.

2) Original or Modified Versions of the Font Software may be bundled,
redistributed and/or sold with any software, provided that each copy
contains the above copyright notice and this license. These can be
included either as stand-alone text files, human-readable headers or
in the appropriate machine-readable metadata fields within text or
binary files as long as those fields can be easily viewed by the user.

3) No Modified Version of the Font Software may use the Reserved Font
Name(s) unless explicit written permission is granted by the corresponding
Copyright Holder. This restriction only applies to the primary font name as
presented to the users.

4) The name(s) of the Copyright Holder(s) or the Author(s) of the Font
Software shall not be used to promote, endorse or advertise any
Modified Version, except to acknowledge the contribution(s) of the
Copyright Holder(s) and the Author(s) or with their explicit written
permission.

5) The Font Software, modified or unmodified, in part or in whole,
must be distributed entirely under this license, and must not be
distributed under any other license. The requirement for fonts to
remain under this license does not apply to any document created
using the Font Software.

TERMINATION
This license becomes null and void if any of the above conditions are
not met.

DISCLAIMER
THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT
OF COPYRIGHT, PATENT, TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL THE
COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
INCLUDING ANY GENERAL, SPECIAL, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL
DAMAGES, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF THE USE OR INABILITY TO USE THE FONT SOFTWARE OR FROM
OTHER DEALINGS IN THE FONT SOFTWARE.

--------------------------------------------------------------------------------

# Code: MIT License (https://opensource.org/licenses/MIT)

In the Font Awesome Free download, the MIT license applies to all non-font and
non-icon files.

Copyright 2024 Fonticons, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in the
Software without restriction, including without limitation the rights to use, copy,
modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
and to permit persons to whom the Software is furnished to do so, subject to the
following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

--------------------------------------------------------------------------------

# Attribution

Attribution is required by MIT, SIL OFL, and CC BY licenses. Downloaded Font
Awesome Free files already contain embedded comments with sufficient
attribution, so you shouldn't need to do anything additional when using these
files normally.

We've kept attribution comments terse, so we ask that you do not actively work
to remove them from files, especially code. They're a great way for folks to
learn about Font Awesome.

--------------------------------------------------------------------------------

# Brand Icons

All brand icons are trademarks of their respective owners. The use of these
trademarks does not indicate endorsement of the trademark holder by Font
Awesome, nor vice versa. **Please do not use brand logos for any purpose except
to represent the company, product, or service to which they refer.**

````
<!-- /provenance-file -->

<a id="original-39e0468bfefb"></a>

### `licenses/vendor/jacktook-upstream-LICENSE.txt`

<!-- provenance-file {"path": "licenses/vendor/jacktook-upstream-LICENSE.txt", "bytes": 35129, "sha256": "605e9047a563c5c8396ffb18232aa4304ec56586aee537c45064c6fb425e44ad", "newline": "lf"} -->
````text
GNU GENERAL PUBLIC LICENSE
                       Version 3, 29 June 2007

 Copyright (C) 2007 Free Software Foundation, Inc. <https://fsf.org/>
 Everyone is permitted to copy and distribute verbatim copies
 of this license document, but changing it is not allowed.

                            Preamble

  The GNU General Public License is a free, copyleft license for
software and other kinds of works.

  The licenses for most software and other practical works are designed
to take away your freedom to share and change the works.  By contrast,
the GNU General Public License is intended to guarantee your freedom to
share and change all versions of a program--to make sure it remains free
software for all its users.  We, the Free Software Foundation, use the
GNU General Public License for most of our software; it applies also to
any other work released this way by its authors.  You can apply it to
your programs, too.

  When we speak of free software, we are referring to freedom, not
price.  Our General Public Licenses are designed to make sure that you
have the freedom to distribute copies of free software (and charge for
them if you wish), that you receive source code or can get it if you
want it, that you can change the software or use pieces of it in new
free programs, and that you know you can do these things.

  To protect your rights, we need to prevent others from denying you
these rights or asking you to surrender the rights.  Therefore, you have
certain responsibilities if you distribute copies of the software, or if
you modify it: responsibilities to respect the freedom of others.

  For example, if you distribute copies of such a program, whether
gratis or for a fee, you must pass on to the recipients the same
freedoms that you received.  You must make sure that they, too, receive
or can get the source code.  And you must show them these terms so they
know their rights.

  Developers that use the GNU GPL protect your rights with two steps:
(1) assert copyright on the software, and (2) offer you this License
giving you legal permission to copy, distribute and/or modify it.

  For the developers' and authors' protection, the GPL clearly explains
that there is no warranty for this free software.  For both users' and
authors' sake, the GPL requires that modified versions be marked as
changed, so that their problems will not be attributed erroneously to
authors of previous versions.

  Some devices are designed to deny users access to install or run
modified versions of the software inside them, although the manufacturer
can do so.  This is fundamentally incompatible with the aim of
protecting users' freedom to change the software.  The systematic
pattern of such abuse occurs in the area of products for individuals to
use, which is precisely where it is most unacceptable.  Therefore, we
have designed this version of the GPL to prohibit the practice for those
products.  If such problems arise substantially in other domains, we
stand ready to extend this provision to those domains in future versions
of the GPL, as needed to protect the freedom of users.

  Finally, every program is threatened constantly by software patents.
States should not allow patents to restrict development and use of
software on general-purpose computers, but in those that do, we wish to
avoid the special danger that patents applied to a free program could
make it effectively proprietary.  To prevent this, the GPL assures that
patents cannot be used to render the program non-free.

  The precise terms and conditions for copying, distribution and
modification follow.

                       TERMS AND CONDITIONS

  0. Definitions.

  "This License" refers to version 3 of the GNU General Public License.

  "Copyright" also means copyright-like laws that apply to other kinds of
works, such as semiconductor masks.

  "The Program" refers to any copyrightable work licensed under this
License.  Each licensee is addressed as "you".  "Licensees" and
"recipients" may be individuals or organizations.

  To "modify" a work means to copy from or adapt all or part of the work
in a fashion requiring copyright permission, other than the making of an
exact copy.  The resulting work is called a "modified version" of the
earlier work or a work "based on" the earlier work.

  A "covered work" means either the unmodified Program or a work based
on the Program.

  To "propagate" a work means to do anything with it that, without
permission, would make you directly or secondarily liable for
infringement under applicable copyright law, except executing it on a
computer or modifying a private copy.  Propagation includes copying,
distribution (with or without modification), making available to the
public, and in some countries other activities as well.

  To "convey" a work means any kind of propagation that enables other
parties to make or receive copies.  Mere interaction with a user through
a computer network, with no transfer of a copy, is not conveying.

  An interactive user interface displays "Appropriate Legal Notices"
to the extent that it includes a convenient and prominently visible
feature that (1) displays an appropriate copyright notice, and (2)
tells the user that there is no warranty for the work (except to the
extent that warranties are provided), that licensees may convey the
work under this License, and how to view a copy of this License.  If
the interface presents a list of user commands or options, such as a
menu, a prominent item in the list meets this criterion.

  1. Source Code.

  The "source code" for a work means the preferred form of the work
for making modifications to it.  "Object code" means any non-source
form of a work.

  A "Standard Interface" means an interface that either is an official
standard defined by a recognized standards body, or, in the case of
interfaces specified for a particular programming language, one that
is widely used among developers working in that language.

  The "System Libraries" of an executable work include anything, other
than the work as a whole, that (a) is included in the normal form of
packaging a Major Component, but which is not part of that Major
Component, and (b) serves only to enable use of the work with that
Major Component, or to implement a Standard Interface for which an
implementation is available to the public in source code form.  A
"Major Component", in this context, means a major essential component
(kernel, window system, and so on) of the specific operating system
(if any) on which the executable work runs, or a compiler used to
produce the work, or an object code interpreter used to run it.

  The "Corresponding Source" for a work in object code form means all
the source code needed to generate, install, and (for an executable
work) run the object code and to modify the work, including scripts to
control those activities.  However, it does not include the work's
System Libraries, or general-purpose tools or generally available free
programs which are used unmodified in performing those activities but
which are not part of the work.  For example, Corresponding Source
includes interface definition files associated with source files for
the work, and the source code for shared libraries and dynamically
linked subprograms that the work is specifically designed to require,
such as by intimate data communication or control flow between those
subprograms and other parts of the work.

  The Corresponding Source need not include anything that users
can regenerate automatically from other parts of the Corresponding
Source.

  The Corresponding Source for a work in source code form is that
same work.

  2. Basic Permissions.

  All rights granted under this License are granted for the term of
copyright on the Program, and are irrevocable provided the stated
conditions are met.  This License explicitly affirms your unlimited
permission to run the unmodified Program.  The output from running a
covered work is covered by this License only if the output, given its
content, constitutes a covered work.  This License acknowledges your
rights of fair use or other equivalent, as provided by copyright law.

  You may make, run and propagate covered works that you do not
convey, without conditions so long as your license otherwise remains
in force.  You may convey covered works to others for the sole purpose
of having them make modifications exclusively for you, or provide you
with facilities for running those works, provided that you comply with
the terms of this License in conveying all material for which you do
not control copyright.  Those thus making or running the covered works
for you must do so exclusively on your behalf, under your direction
and control, on terms that prohibit them from making any copies of
your copyrighted material outside their relationship with you.

  Conveying under any other circumstances is permitted solely under
the conditions stated below.  Sublicensing is not allowed; section 10
makes it unnecessary.

  3. Protecting Users' Legal Rights From Anti-Circumvention Law.

  No covered work shall be deemed part of an effective technological
measure under any applicable law fulfilling obligations under article
11 of the WIPO copyright treaty adopted on 20 December 1996, or
similar laws prohibiting or restricting circumvention of such
measures.

  When you convey a covered work, you waive any legal power to forbid
circumvention of technological measures to the extent such circumvention
is effected by exercising rights under this License with respect to
the covered work, and you disclaim any intention to limit operation or
modification of the work as a means of enforcing, against the work's
users, your or third parties' legal rights to forbid circumvention of
technological measures.

  4. Conveying Verbatim Copies.

  You may convey verbatim copies of the Program's source code as you
receive it, in any medium, provided that you conspicuously and
appropriately publish on each copy an appropriate copyright notice;
keep intact all notices stating that this License and any
non-permissive terms added in accord with section 7 apply to the code;
keep intact all notices of the absence of any warranty; and give all
recipients a copy of this License along with the Program.

  You may charge any price or no price for each copy that you convey,
and you may offer support or warranty protection for a fee.

  5. Conveying Modified Source Versions.

  You may convey a work based on the Program, or the modifications to
produce it from the Program, in the form of source code under the
terms of section 4, provided that you also meet all of these conditions:

    a) The work must carry prominent notices stating that you modified
    it, and giving a relevant date.

    b) The work must carry prominent notices stating that it is
    released under this License and any conditions added under section
    7.  This requirement modifies the requirement in section 4 to
    "keep intact all notices".

    c) You must license the entire work, as a whole, under this
    License to anyone who comes into possession of a copy.  This
    License will therefore apply, along with any applicable section 7
    additional terms, to the whole of the work, and all its parts,
    regardless of how they are packaged.  This License gives no
    permission to license the work in any other way, but it does not
    invalidate such permission if you have separately received it.

    d) If the work has interactive user interfaces, each must display
    Appropriate Legal Notices; however, if the Program has interactive
    interfaces that do not display Appropriate Legal Notices, your
    work need not make them do so.

  A compilation of a covered work with other separate and independent
works, which are not by their nature extensions of the covered work,
and which are not combined with it such as to form a larger program,
in or on a volume of a storage or distribution medium, is called an
"aggregate" if the compilation and its resulting copyright are not
used to limit the access or legal rights of the compilation's users
beyond what the individual works permit.  Inclusion of a covered work
in an aggregate does not cause this License to apply to the other
parts of the aggregate.

  6. Conveying Non-Source Forms.

  You may convey a covered work in object code form under the terms
of sections 4 and 5, provided that you also convey the
machine-readable Corresponding Source under the terms of this License,
in one of these ways:

    a) Convey the object code in, or embodied in, a physical product
    (including a physical distribution medium), accompanied by the
    Corresponding Source fixed on a durable physical medium
    customarily used for software interchange.

    b) Convey the object code in, or embodied in, a physical product
    (including a physical distribution medium), accompanied by a
    written offer, valid for at least three years and valid for as
    long as you offer spare parts or customer support for that product
    model, to give anyone who possesses the object code either (1) a
    copy of the Corresponding Source for all the software in the
    product that is covered by this License, on a durable physical
    medium customarily used for software interchange, for a price no
    more than your reasonable cost of physically performing this
    conveying of source, or (2) access to copy the
    Corresponding Source from a network server at no charge.

    c) Convey individual copies of the object code with a copy of the
    written offer to provide the Corresponding Source.  This
    alternative is allowed only occasionally and noncommercially, and
    only if you received the object code with such an offer, in accord
    with subsection 6b.

    d) Convey the object code by offering access from a designated
    place (gratis or for a charge), and offer equivalent access to the
    Corresponding Source in the same way through the same place at no
    further charge.  You need not require recipients to copy the
    Corresponding Source along with the object code.  If the place to
    copy the object code is a network server, the Corresponding Source
    may be on a different server (operated by you or a third party)
    that supports equivalent copying facilities, provided you maintain
    clear directions next to the object code saying where to find the
    Corresponding Source.  Regardless of what server hosts the
    Corresponding Source, you remain obligated to ensure that it is
    available for as long as needed to satisfy these requirements.

    e) Convey the object code using peer-to-peer transmission, provided
    you inform other peers where the object code and Corresponding
    Source of the work are being offered to the general public at no
    charge under subsection 6d.

  A separable portion of the object code, whose source code is excluded
from the Corresponding Source as a System Library, need not be
included in conveying the object code work.

  A "User Product" is either (1) a "consumer product", which means any
tangible personal property which is normally used for personal, family,
or household purposes, or (2) anything designed or sold for incorporation
into a dwelling.  In determining whether a product is a consumer product,
doubtful cases shall be resolved in favor of coverage.  For a particular
product received by a particular user, "normally used" refers to a
typical or common use of that class of product, regardless of the status
of the particular user or of the way in which the particular user
actually uses, or expects or is expected to use, the product.  A product
is a consumer product regardless of whether the product has substantial
commercial, industrial or non-consumer uses, unless such uses represent
the only significant mode of use of the product.

  "Installation Information" for a User Product means any methods,
procedures, authorization keys, or other information required to install
and execute modified versions of a covered work in that User Product from
a modified version of its Corresponding Source.  The information must
suffice to ensure that the continued functioning of the modified object
code is in no case prevented or interfered with solely because
modification has been made.

  If you convey an object code work under this section in, or with, or
specifically for use in, a User Product, and the conveying occurs as
part of a transaction in which the right of possession and use of the
User Product is transferred to the recipient in perpetuity or for a
fixed term (regardless of how the transaction is characterized), the
Corresponding Source conveyed under this section must be accompanied
by the Installation Information.  But this requirement does not apply
if neither you nor any third party retains the ability to install
modified object code on the User Product (for example, the work has
been installed in ROM).

  The requirement to provide Installation Information does not include a
requirement to continue to provide support service, warranty, or updates
for a work that has been modified or installed by the recipient, or for
the User Product in which it has been modified or installed.  Access to a
network may be denied when the modification itself materially and
adversely affects the operation of the network or violates the rules and
protocols for communication across the network.

  Corresponding Source conveyed, and Installation Information provided,
in accord with this section must be in a format that is publicly
documented (and with an implementation available to the public in
source code form), and must require no special password or key for
unpacking, reading or copying.

  7. Additional Terms.

  "Additional permissions" are terms that supplement the terms of this
License by making exceptions from one or more of its conditions.
Additional permissions that are applicable to the entire Program shall
be treated as though they were included in this License, to the extent
that they are valid under applicable law.  If additional permissions
apply only to part of the Program, that part may be used separately
under those permissions, but the entire Program remains governed by
this License without regard to the additional permissions.

  When you convey a copy of a covered work, you may at your option
remove any additional permissions from that copy, or from any part of
it.  (Additional permissions may be written to require their own
removal in certain cases when you modify the work.)  You may place
additional permissions on material, added by you to a covered work,
for which you have or can give appropriate copyright permission.

  Notwithstanding any other provision of this License, for material you
add to a covered work, you may (if authorized by the copyright holders of
that material) supplement the terms of this License with terms:

    a) Disclaiming warranty or limiting liability differently from the
    terms of sections 15 and 16 of this License; or

    b) Requiring preservation of specified reasonable legal notices or
    author attributions in that material or in the Appropriate Legal
    Notices displayed by works containing it; or

    c) Prohibiting misrepresentation of the origin of that material, or
    requiring that modified versions of such material be marked in
    reasonable ways as different from the original version; or

    d) Limiting the use for publicity purposes of names of licensors or
    authors of the material; or

    e) Declining to grant rights under trademark law for use of some
    trade names, trademarks, or service marks; or

    f) Requiring indemnification of licensors and authors of that
    material by anyone who conveys the material (or modified versions of
    it) with contractual assumptions of liability to the recipient, for
    any liability that these contractual assumptions directly impose on
    those licensors and authors.

  All other non-permissive additional terms are considered "further
restrictions" within the meaning of section 10.  If the Program as you
received it, or any part of it, contains a notice stating that it is
governed by this License along with a term that is a further
restriction, you may remove that term.  If a license document contains
a further restriction but permits relicensing or conveying under this
License, you may add to a covered work material governed by the terms
of that license document, provided that the further restriction does
not survive such relicensing or conveying.

  If you add terms to a covered work in accord with this section, you
must place, in the relevant source files, a statement of the
additional terms that apply to those files, or a notice indicating
where to find the applicable terms.

  Additional terms, permissive or non-permissive, may be stated in the
form of a separately written license, or stated as exceptions;
the above requirements apply either way.

  8. Termination.

  You may not propagate or modify a covered work except as expressly
provided under this License.  Any attempt otherwise to propagate or
modify it is void, and will automatically terminate your rights under
this License (including any patent licenses granted under the third
paragraph of section 11).

  However, if you cease all violation of this License, then your
license from a particular copyright holder is reinstated (a)
provisionally, unless and until the copyright holder explicitly and
finally terminates your license, and (b) permanently, if the copyright
holder fails to notify you of the violation by some reasonable means
prior to 60 days after the cessation.

  Moreover, your license from a particular copyright holder is
reinstated permanently if the copyright holder notifies you of the
violation by some reasonable means, this is the first time you have
received notice of violation of this License (for any work) from that
copyright holder, and you cure the violation prior to 30 days after
your receipt of the notice.

  Termination of your rights under this section does not terminate the
licenses of parties who have received copies or rights from you under
this License.  If your rights have been terminated and not permanently
reinstated, you do not qualify to receive new licenses for the same
material under section 10.

  9. Acceptance Not Required for Having Copies.

  You are not required to accept this License in order to receive or
run a copy of the Program.  Ancillary propagation of a covered work
occurring solely as a consequence of using peer-to-peer transmission
to receive a copy likewise does not require acceptance.  However,
nothing other than this License grants you permission to propagate or
modify any covered work.  These actions infringe copyright if you do
not accept this License.  Therefore, by modifying or propagating a
covered work, you indicate your acceptance of this License to do so.

  10. Automatic Licensing of Downstream Recipients.

  Each time you convey a covered work, the recipient automatically
receives a license from the original licensors, to run, modify and
propagate that work, subject to this License.  You are not responsible
for enforcing compliance by third parties with this License.

  An "entity transaction" is a transaction transferring control of an
organization, or substantially all assets of one, or subdividing an
organization, or merging organizations.  If propagation of a covered
work results from an entity transaction, each party to that
transaction who receives a copy of the work also receives whatever
licenses to the work the party's predecessor in interest had or could
give under the previous paragraph, plus a right to possession of the
Corresponding Source of the work from the predecessor in interest, if
the predecessor has it or can get it with reasonable efforts.

  You may not impose any further restrictions on the exercise of the
rights granted or affirmed under this License.  For example, you may
not impose a license fee, royalty, or other charge for exercise of
rights granted under this License, and you may not initiate litigation
(including a cross-claim or counterclaim in a lawsuit) alleging that
any patent claim is infringed by making, using, selling, offering for
sale, or importing the Program or any portion of it.

  11. Patents.

  A "contributor" is a copyright holder who authorizes use under this
License of the Program or a work on which the Program is based.  The
work thus licensed is called the contributor's "contributor version".

  A contributor's "essential patent claims" are all patent claims
owned or controlled by the contributor, whether already acquired or
hereafter acquired, that would be infringed by some manner, permitted
by this License, of making, using, or selling its contributor version,
but do not include claims that would be infringed only as a
consequence of further modification of the contributor version.  For
purposes of this definition, "control" includes the right to grant
patent sublicenses in a manner consistent with the requirements of
this License.

  Each contributor grants you a non-exclusive, worldwide, royalty-free
patent license under the contributor's essential patent claims, to
make, use, sell, offer for sale, import and otherwise run, modify and
propagate the contents of its contributor version.

  In the following three paragraphs, a "patent license" is any express
agreement or commitment, however denominated, not to enforce a patent
(such as an express permission to practice a patent or covenant not to
sue for patent infringement).  To "grant" such a patent license to a
party means to make such an agreement or commitment not to enforce a
patent against the party.

  If you convey a covered work, knowingly relying on a patent license,
and the Corresponding Source of the work is not available for anyone
to copy, free of charge and under the terms of this License, through a
publicly available network server or other readily accessible means,
then you must either (1) cause the Corresponding Source to be so
available, or (2) arrange to deprive yourself of the benefit of the
patent license for this particular work, or (3) arrange, in a manner
consistent with the requirements of this License, to extend the patent
license to downstream recipients.  "Knowingly relying" means you have
actual knowledge that, but for the patent license, your conveying the
covered work in a country, or your recipient's use of the covered work
in a country, would infringe one or more identifiable patents in that
country that you have reason to believe are valid.

  If, pursuant to or in connection with a single transaction or
arrangement, you convey, or propagate by procuring conveyance of, a
covered work, and grant a patent license to some of the parties
receiving the covered work authorizing them to use, propagate, modify
or convey a specific copy of the covered work, then the patent license
you grant is automatically extended to all recipients of the covered
work and works based on it.

  A patent license is "discriminatory" if it does not include within
the scope of its coverage, prohibits the exercise of, or is
conditioned on the non-exercise of one or more of the rights that are
specifically granted under this License.  You may not convey a covered
work if you are a party to an arrangement with a third party that is
in the business of distributing software, under which you make payment
to the third party based on the extent of your activity of conveying
the work, and under which the third party grants, to any of the
parties who would receive the covered work from you, a discriminatory
patent license (a) in connection with copies of the covered work
conveyed by you (or copies made from those copies), or (b) primarily
for and in connection with specific products or compilations that
contain the covered work, unless you entered into that arrangement,
or that patent license was granted, prior to 28 March 2007.

  Nothing in this License shall be construed as excluding or limiting
any implied license or other defenses to infringement that may
otherwise be available to you under applicable patent law.

  12. No Surrender of Others' Freedom.

  If conditions are imposed on you (whether by court order, agreement or
otherwise) that contradict the conditions of this License, they do not
excuse you from the conditions of this License.  If you cannot convey a
covered work so as to satisfy simultaneously your obligations under this
License and any other pertinent obligations, then as a consequence you may
not convey it at all.  For example, if you agree to terms that obligate you
to collect a royalty for further conveying from those to whom you convey
the Program, the only way you could satisfy both those terms and this
License would be to refrain entirely from conveying the Program.

  13. Use with the GNU Affero General Public License.

  Notwithstanding any other provision of this License, you have
permission to link or combine any covered work with a work licensed
under version 3 of the GNU Affero General Public License into a single
combined work, and to convey the resulting work.  The terms of this
License will continue to apply to the part which is the covered work,
but the special requirements of the GNU Affero General Public License,
section 13, concerning interaction through a network will apply to the
combination as such.

  14. Revised Versions of this License.

  The Free Software Foundation may publish revised and/or new versions of
the GNU General Public License from time to time.  Such new versions will
be similar in spirit to the present version, but may differ in detail to
address new problems or concerns.

  Each version is given a distinguishing version number.  If the
Program specifies that a certain numbered version of the GNU General
Public License "or any later version" applies to it, you have the
option of following the terms and conditions either of that numbered
version or of any later version published by the Free Software
Foundation.  If the Program does not specify a version number of the
GNU General Public License, you may choose any version ever published
by the Free Software Foundation.

  If the Program specifies that a proxy can decide which future
versions of the GNU General Public License can be used, that proxy's
public statement of acceptance of a version permanently authorizes you
to choose that version for the Program.

  Later license versions may give you additional or different
permissions.  However, no additional obligations are imposed on any
author or copyright holder as a result of your choosing to follow a
later version.

  15. Disclaimer of Warranty.

  THERE IS NO WARRANTY FOR THE PROGRAM, TO THE EXTENT PERMITTED BY
APPLICABLE LAW.  EXCEPT WHEN OTHERWISE STATED IN WRITING THE COPYRIGHT
HOLDERS AND/OR OTHER PARTIES PROVIDE THE PROGRAM "AS IS" WITHOUT WARRANTY
OF ANY KIND, EITHER EXPRESSED OR IMPLIED, INCLUDING, BUT NOT LIMITED TO,
THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
PURPOSE.  THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF THE PROGRAM
IS WITH YOU.  SHOULD THE PROGRAM PROVE DEFECTIVE, YOU ASSUME THE COST OF
ALL NECESSARY SERVICING, REPAIR OR CORRECTION.

  16. Limitation of Liability.

  IN NO EVENT UNLESS REQUIRED BY APPLICABLE LAW OR AGREED TO IN WRITING
WILL ANY COPYRIGHT HOLDER, OR ANY OTHER PARTY WHO MODIFIES AND/OR CONVEYS
THE PROGRAM AS PERMITTED ABOVE, BE LIABLE TO YOU FOR DAMAGES, INCLUDING ANY
GENERAL, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES ARISING OUT OF THE
USE OR INABILITY TO USE THE PROGRAM (INCLUDING BUT NOT LIMITED TO LOSS OF
DATA OR DATA BEING RENDERED INACCURATE OR LOSSES SUSTAINED BY YOU OR THIRD
PARTIES OR A FAILURE OF THE PROGRAM TO OPERATE WITH ANY OTHER PROGRAMS),
EVEN IF SUCH HOLDER OR OTHER PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF
SUCH DAMAGES.

  17. Interpretation of Sections 15 and 16.

  If the disclaimer of warranty and limitation of liability provided
above cannot be given local legal effect according to their terms,
reviewing courts shall apply local law that most closely approximates
an absolute waiver of all civil liability in connection with the
Program, unless a warranty or assumption of liability accompanies a
copy of the Program in return for a fee.

                     END OF TERMS AND CONDITIONS

            How to Apply These Terms to Your New Programs

  If you develop a new program, and you want it to be of the greatest
possible use to the public, the best way to achieve this is to make it
free software which everyone can redistribute and change under these terms.

  To do so, attach the following notices to the program.  It is safest
to attach them to the start of each source file to most effectively
state the exclusion of warranty; and each file should have at least
the "copyright" line and a pointer to where the full notice is found.

    <one line to give the program's name and a brief idea of what it does.>
    Copyright (C) <year>  <name of author>

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.

Also add information on how to contact you by electronic and paper mail.

  If the program does terminal interaction, make it output a short
notice like this when it starts in an interactive mode:

    <program>  Copyright (C) <year>  <name of author>
    This program comes with ABSOLUTELY NO WARRANTY; for details type `show w'.
    This is free software, and you are welcome to redistribute it
    under certain conditions; type `show c' for details.

The hypothetical commands `show w' and `show c' should show the appropriate
parts of the General Public License.  Of course, your program's commands
might be different; for a GUI interface, you would use an "about box".

  You should also get your employer (if you work as a programmer) or school,
if any, to sign a "copyright disclaimer" for the program, if necessary.
For more information on this, and how to apply and follow the GNU GPL, see
<https://www.gnu.org/licenses/>.

  The GNU General Public License does not permit incorporating your program
into proprietary programs.  If your program is a subroutine library, you
may consider it more useful to permit linking proprietary applications with
the library.  If this is what you want to do, use the GNU Lesser General
Public License instead of this License.  But first, please read
<https://www.gnu.org/licenses/why-not-lgpl.html>.

````
<!-- /provenance-file -->

<a id="original-4a234f2b8884"></a>

### `licenses/vendor/segno-1.6.6-LICENSE.txt`

<!-- provenance-file {"path": "licenses/vendor/segno-1.6.6-LICENSE.txt", "bytes": 1503, "sha256": "de6c85fccf5d52902aa13dfe2dc6d2a2a106fc3419ed438f3460f0d4b76a6935", "newline": "lf"} -->
````text
Copyright (c) 2016 - 2025, Lars Heuer
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors
   may be used to endorse or promote products derived from this software
   without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

````
<!-- /provenance-file -->

<a id="original-d64306360b38"></a>

### `licenses/vendor/tmdbv3api-1.9.0-setup-evidence.txt`

<!-- provenance-file {"path": "licenses/vendor/tmdbv3api-1.9.0-setup-evidence.txt", "bytes": 2316, "sha256": "42fde0503d50bc327052cd3efd323a724326cd503b4058023791f46b79e045ee", "newline": "lf"} -->
````text
# -*- coding: utf-8 -*-

import os
import sys
from shutil import rmtree

from setuptools import setup, Command

with open("README.rst", "rb") as f:
    long_descr = f.read().decode("utf-8")

here = os.path.abspath(os.path.dirname(__file__))


class PublishCommand(Command):
    """Support setup.py publish."""

    description = 'Build and publish the package.'
    user_options = []

    @staticmethod
    def status(s):
        """Prints things in bold."""
        print('\033[1m{0}\033[0m'.format(s))

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        try:
            self.status('Removing previous builds…')
            rmtree(os.path.join(here, 'dist'))
        except:
            pass

        self.status('Building Source and Wheel (universal) distribution…')
        os.system('{0} setup.py sdist bdist_wheel --universal'.format(sys.executable))

        self.status('Uploading the package to PyPi via Twine…')
        os.system('twine upload dist/*')

        sys.exit()


setup(name='tmdbv3api',
      version='1.9.0',
      description='A lightweight Python library for The Movie Database (TMDb) API.',
      long_description=long_descr,
      url='https://github.com/AnthonyBloomer/tmdbv3api',
      author='Anthony Bloomer',
      author_email='ant0@protonmail.ch',
      license='MIT',
      packages=['tmdbv3api', 'tmdbv3api.objs'],
      keywords=['movie', 'tv' 'movie database', 'tmdb', 'wrapper', 'database', 'themoviedb', 'moviedb', 'api'],
      install_requires=[
          'requests'
      ],
      classifiers=[
          'Development Status :: 5 - Production/Stable',
          'Intended Audience :: Developers',
          "Topic :: Software Development :: Libraries",
          'Programming Language :: Python',
          'Programming Language :: Python :: 2.7',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.3',
          'Programming Language :: Python :: 3.4',
          'Programming Language :: Python :: 3.5',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: 3.7',
          'Programming Language :: Python :: 3.8',
      ],
      cmdclass={
          'publish': PublishCommand,
      },
      zip_safe=False)

````
<!-- /provenance-file -->

<a id="original-481e25f441b0"></a>

### `licenses/vendor/torf-4.2.0-LICENSE.txt`

<!-- provenance-file {"path": "licenses/vendor/torf-4.2.0-LICENSE.txt", "bytes": 35149, "sha256": "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986", "newline": "lf"} -->
````text
                    GNU GENERAL PUBLIC LICENSE
                       Version 3, 29 June 2007

 Copyright (C) 2007 Free Software Foundation, Inc. <https://fsf.org/>
 Everyone is permitted to copy and distribute verbatim copies
 of this license document, but changing it is not allowed.

                            Preamble

  The GNU General Public License is a free, copyleft license for
software and other kinds of works.

  The licenses for most software and other practical works are designed
to take away your freedom to share and change the works.  By contrast,
the GNU General Public License is intended to guarantee your freedom to
share and change all versions of a program--to make sure it remains free
software for all its users.  We, the Free Software Foundation, use the
GNU General Public License for most of our software; it applies also to
any other work released this way by its authors.  You can apply it to
your programs, too.

  When we speak of free software, we are referring to freedom, not
price.  Our General Public Licenses are designed to make sure that you
have the freedom to distribute copies of free software (and charge for
them if you wish), that you receive source code or can get it if you
want it, that you can change the software or use pieces of it in new
free programs, and that you know you can do these things.

  To protect your rights, we need to prevent others from denying you
these rights or asking you to surrender the rights.  Therefore, you have
certain responsibilities if you distribute copies of the software, or if
you modify it: responsibilities to respect the freedom of others.

  For example, if you distribute copies of such a program, whether
gratis or for a fee, you must pass on to the recipients the same
freedoms that you received.  You must make sure that they, too, receive
or can get the source code.  And you must show them these terms so they
know their rights.

  Developers that use the GNU GPL protect your rights with two steps:
(1) assert copyright on the software, and (2) offer you this License
giving you legal permission to copy, distribute and/or modify it.

  For the developers' and authors' protection, the GPL clearly explains
that there is no warranty for this free software.  For both users' and
authors' sake, the GPL requires that modified versions be marked as
changed, so that their problems will not be attributed erroneously to
authors of previous versions.

  Some devices are designed to deny users access to install or run
modified versions of the software inside them, although the manufacturer
can do so.  This is fundamentally incompatible with the aim of
protecting users' freedom to change the software.  The systematic
pattern of such abuse occurs in the area of products for individuals to
use, which is precisely where it is most unacceptable.  Therefore, we
have designed this version of the GPL to prohibit the practice for those
products.  If such problems arise substantially in other domains, we
stand ready to extend this provision to those domains in future versions
of the GPL, as needed to protect the freedom of users.

  Finally, every program is threatened constantly by software patents.
States should not allow patents to restrict development and use of
software on general-purpose computers, but in those that do, we wish to
avoid the special danger that patents applied to a free program could
make it effectively proprietary.  To prevent this, the GPL assures that
patents cannot be used to render the program non-free.

  The precise terms and conditions for copying, distribution and
modification follow.

                       TERMS AND CONDITIONS

  0. Definitions.

  "This License" refers to version 3 of the GNU General Public License.

  "Copyright" also means copyright-like laws that apply to other kinds of
works, such as semiconductor masks.

  "The Program" refers to any copyrightable work licensed under this
License.  Each licensee is addressed as "you".  "Licensees" and
"recipients" may be individuals or organizations.

  To "modify" a work means to copy from or adapt all or part of the work
in a fashion requiring copyright permission, other than the making of an
exact copy.  The resulting work is called a "modified version" of the
earlier work or a work "based on" the earlier work.

  A "covered work" means either the unmodified Program or a work based
on the Program.

  To "propagate" a work means to do anything with it that, without
permission, would make you directly or secondarily liable for
infringement under applicable copyright law, except executing it on a
computer or modifying a private copy.  Propagation includes copying,
distribution (with or without modification), making available to the
public, and in some countries other activities as well.

  To "convey" a work means any kind of propagation that enables other
parties to make or receive copies.  Mere interaction with a user through
a computer network, with no transfer of a copy, is not conveying.

  An interactive user interface displays "Appropriate Legal Notices"
to the extent that it includes a convenient and prominently visible
feature that (1) displays an appropriate copyright notice, and (2)
tells the user that there is no warranty for the work (except to the
extent that warranties are provided), that licensees may convey the
work under this License, and how to view a copy of this License.  If
the interface presents a list of user commands or options, such as a
menu, a prominent item in the list meets this criterion.

  1. Source Code.

  The "source code" for a work means the preferred form of the work
for making modifications to it.  "Object code" means any non-source
form of a work.

  A "Standard Interface" means an interface that either is an official
standard defined by a recognized standards body, or, in the case of
interfaces specified for a particular programming language, one that
is widely used among developers working in that language.

  The "System Libraries" of an executable work include anything, other
than the work as a whole, that (a) is included in the normal form of
packaging a Major Component, but which is not part of that Major
Component, and (b) serves only to enable use of the work with that
Major Component, or to implement a Standard Interface for which an
implementation is available to the public in source code form.  A
"Major Component", in this context, means a major essential component
(kernel, window system, and so on) of the specific operating system
(if any) on which the executable work runs, or a compiler used to
produce the work, or an object code interpreter used to run it.

  The "Corresponding Source" for a work in object code form means all
the source code needed to generate, install, and (for an executable
work) run the object code and to modify the work, including scripts to
control those activities.  However, it does not include the work's
System Libraries, or general-purpose tools or generally available free
programs which are used unmodified in performing those activities but
which are not part of the work.  For example, Corresponding Source
includes interface definition files associated with source files for
the work, and the source code for shared libraries and dynamically
linked subprograms that the work is specifically designed to require,
such as by intimate data communication or control flow between those
subprograms and other parts of the work.

  The Corresponding Source need not include anything that users
can regenerate automatically from other parts of the Corresponding
Source.

  The Corresponding Source for a work in source code form is that
same work.

  2. Basic Permissions.

  All rights granted under this License are granted for the term of
copyright on the Program, and are irrevocable provided the stated
conditions are met.  This License explicitly affirms your unlimited
permission to run the unmodified Program.  The output from running a
covered work is covered by this License only if the output, given its
content, constitutes a covered work.  This License acknowledges your
rights of fair use or other equivalent, as provided by copyright law.

  You may make, run and propagate covered works that you do not
convey, without conditions so long as your license otherwise remains
in force.  You may convey covered works to others for the sole purpose
of having them make modifications exclusively for you, or provide you
with facilities for running those works, provided that you comply with
the terms of this License in conveying all material for which you do
not control copyright.  Those thus making or running the covered works
for you must do so exclusively on your behalf, under your direction
and control, on terms that prohibit them from making any copies of
your copyrighted material outside their relationship with you.

  Conveying under any other circumstances is permitted solely under
the conditions stated below.  Sublicensing is not allowed; section 10
makes it unnecessary.

  3. Protecting Users' Legal Rights From Anti-Circumvention Law.

  No covered work shall be deemed part of an effective technological
measure under any applicable law fulfilling obligations under article
11 of the WIPO copyright treaty adopted on 20 December 1996, or
similar laws prohibiting or restricting circumvention of such
measures.

  When you convey a covered work, you waive any legal power to forbid
circumvention of technological measures to the extent such circumvention
is effected by exercising rights under this License with respect to
the covered work, and you disclaim any intention to limit operation or
modification of the work as a means of enforcing, against the work's
users, your or third parties' legal rights to forbid circumvention of
technological measures.

  4. Conveying Verbatim Copies.

  You may convey verbatim copies of the Program's source code as you
receive it, in any medium, provided that you conspicuously and
appropriately publish on each copy an appropriate copyright notice;
keep intact all notices stating that this License and any
non-permissive terms added in accord with section 7 apply to the code;
keep intact all notices of the absence of any warranty; and give all
recipients a copy of this License along with the Program.

  You may charge any price or no price for each copy that you convey,
and you may offer support or warranty protection for a fee.

  5. Conveying Modified Source Versions.

  You may convey a work based on the Program, or the modifications to
produce it from the Program, in the form of source code under the
terms of section 4, provided that you also meet all of these conditions:

    a) The work must carry prominent notices stating that you modified
    it, and giving a relevant date.

    b) The work must carry prominent notices stating that it is
    released under this License and any conditions added under section
    7.  This requirement modifies the requirement in section 4 to
    "keep intact all notices".

    c) You must license the entire work, as a whole, under this
    License to anyone who comes into possession of a copy.  This
    License will therefore apply, along with any applicable section 7
    additional terms, to the whole of the work, and all its parts,
    regardless of how they are packaged.  This License gives no
    permission to license the work in any other way, but it does not
    invalidate such permission if you have separately received it.

    d) If the work has interactive user interfaces, each must display
    Appropriate Legal Notices; however, if the Program has interactive
    interfaces that do not display Appropriate Legal Notices, your
    work need not make them do so.

  A compilation of a covered work with other separate and independent
works, which are not by their nature extensions of the covered work,
and which are not combined with it such as to form a larger program,
in or on a volume of a storage or distribution medium, is called an
"aggregate" if the compilation and its resulting copyright are not
used to limit the access or legal rights of the compilation's users
beyond what the individual works permit.  Inclusion of a covered work
in an aggregate does not cause this License to apply to the other
parts of the aggregate.

  6. Conveying Non-Source Forms.

  You may convey a covered work in object code form under the terms
of sections 4 and 5, provided that you also convey the
machine-readable Corresponding Source under the terms of this License,
in one of these ways:

    a) Convey the object code in, or embodied in, a physical product
    (including a physical distribution medium), accompanied by the
    Corresponding Source fixed on a durable physical medium
    customarily used for software interchange.

    b) Convey the object code in, or embodied in, a physical product
    (including a physical distribution medium), accompanied by a
    written offer, valid for at least three years and valid for as
    long as you offer spare parts or customer support for that product
    model, to give anyone who possesses the object code either (1) a
    copy of the Corresponding Source for all the software in the
    product that is covered by this License, on a durable physical
    medium customarily used for software interchange, for a price no
    more than your reasonable cost of physically performing this
    conveying of source, or (2) access to copy the
    Corresponding Source from a network server at no charge.

    c) Convey individual copies of the object code with a copy of the
    written offer to provide the Corresponding Source.  This
    alternative is allowed only occasionally and noncommercially, and
    only if you received the object code with such an offer, in accord
    with subsection 6b.

    d) Convey the object code by offering access from a designated
    place (gratis or for a charge), and offer equivalent access to the
    Corresponding Source in the same way through the same place at no
    further charge.  You need not require recipients to copy the
    Corresponding Source along with the object code.  If the place to
    copy the object code is a network server, the Corresponding Source
    may be on a different server (operated by you or a third party)
    that supports equivalent copying facilities, provided you maintain
    clear directions next to the object code saying where to find the
    Corresponding Source.  Regardless of what server hosts the
    Corresponding Source, you remain obligated to ensure that it is
    available for as long as needed to satisfy these requirements.

    e) Convey the object code using peer-to-peer transmission, provided
    you inform other peers where the object code and Corresponding
    Source of the work are being offered to the general public at no
    charge under subsection 6d.

  A separable portion of the object code, whose source code is excluded
from the Corresponding Source as a System Library, need not be
included in conveying the object code work.

  A "User Product" is either (1) a "consumer product", which means any
tangible personal property which is normally used for personal, family,
or household purposes, or (2) anything designed or sold for incorporation
into a dwelling.  In determining whether a product is a consumer product,
doubtful cases shall be resolved in favor of coverage.  For a particular
product received by a particular user, "normally used" refers to a
typical or common use of that class of product, regardless of the status
of the particular user or of the way in which the particular user
actually uses, or expects or is expected to use, the product.  A product
is a consumer product regardless of whether the product has substantial
commercial, industrial or non-consumer uses, unless such uses represent
the only significant mode of use of the product.

  "Installation Information" for a User Product means any methods,
procedures, authorization keys, or other information required to install
and execute modified versions of a covered work in that User Product from
a modified version of its Corresponding Source.  The information must
suffice to ensure that the continued functioning of the modified object
code is in no case prevented or interfered with solely because
modification has been made.

  If you convey an object code work under this section in, or with, or
specifically for use in, a User Product, and the conveying occurs as
part of a transaction in which the right of possession and use of the
User Product is transferred to the recipient in perpetuity or for a
fixed term (regardless of how the transaction is characterized), the
Corresponding Source conveyed under this section must be accompanied
by the Installation Information.  But this requirement does not apply
if neither you nor any third party retains the ability to install
modified object code on the User Product (for example, the work has
been installed in ROM).

  The requirement to provide Installation Information does not include a
requirement to continue to provide support service, warranty, or updates
for a work that has been modified or installed by the recipient, or for
the User Product in which it has been modified or installed.  Access to a
network may be denied when the modification itself materially and
adversely affects the operation of the network or violates the rules and
protocols for communication across the network.

  Corresponding Source conveyed, and Installation Information provided,
in accord with this section must be in a format that is publicly
documented (and with an implementation available to the public in
source code form), and must require no special password or key for
unpacking, reading or copying.

  7. Additional Terms.

  "Additional permissions" are terms that supplement the terms of this
License by making exceptions from one or more of its conditions.
Additional permissions that are applicable to the entire Program shall
be treated as though they were included in this License, to the extent
that they are valid under applicable law.  If additional permissions
apply only to part of the Program, that part may be used separately
under those permissions, but the entire Program remains governed by
this License without regard to the additional permissions.

  When you convey a copy of a covered work, you may at your option
remove any additional permissions from that copy, or from any part of
it.  (Additional permissions may be written to require their own
removal in certain cases when you modify the work.)  You may place
additional permissions on material, added by you to a covered work,
for which you have or can give appropriate copyright permission.

  Notwithstanding any other provision of this License, for material you
add to a covered work, you may (if authorized by the copyright holders of
that material) supplement the terms of this License with terms:

    a) Disclaiming warranty or limiting liability differently from the
    terms of sections 15 and 16 of this License; or

    b) Requiring preservation of specified reasonable legal notices or
    author attributions in that material or in the Appropriate Legal
    Notices displayed by works containing it; or

    c) Prohibiting misrepresentation of the origin of that material, or
    requiring that modified versions of such material be marked in
    reasonable ways as different from the original version; or

    d) Limiting the use for publicity purposes of names of licensors or
    authors of the material; or

    e) Declining to grant rights under trademark law for use of some
    trade names, trademarks, or service marks; or

    f) Requiring indemnification of licensors and authors of that
    material by anyone who conveys the material (or modified versions of
    it) with contractual assumptions of liability to the recipient, for
    any liability that these contractual assumptions directly impose on
    those licensors and authors.

  All other non-permissive additional terms are considered "further
restrictions" within the meaning of section 10.  If the Program as you
received it, or any part of it, contains a notice stating that it is
governed by this License along with a term that is a further
restriction, you may remove that term.  If a license document contains
a further restriction but permits relicensing or conveying under this
License, you may add to a covered work material governed by the terms
of that license document, provided that the further restriction does
not survive such relicensing or conveying.

  If you add terms to a covered work in accord with this section, you
must place, in the relevant source files, a statement of the
additional terms that apply to those files, or a notice indicating
where to find the applicable terms.

  Additional terms, permissive or non-permissive, may be stated in the
form of a separately written license, or stated as exceptions;
the above requirements apply either way.

  8. Termination.

  You may not propagate or modify a covered work except as expressly
provided under this License.  Any attempt otherwise to propagate or
modify it is void, and will automatically terminate your rights under
this License (including any patent licenses granted under the third
paragraph of section 11).

  However, if you cease all violation of this License, then your
license from a particular copyright holder is reinstated (a)
provisionally, unless and until the copyright holder explicitly and
finally terminates your license, and (b) permanently, if the copyright
holder fails to notify you of the violation by some reasonable means
prior to 60 days after the cessation.

  Moreover, your license from a particular copyright holder is
reinstated permanently if the copyright holder notifies you of the
violation by some reasonable means, this is the first time you have
received notice of violation of this License (for any work) from that
copyright holder, and you cure the violation prior to 30 days after
your receipt of the notice.

  Termination of your rights under this section does not terminate the
licenses of parties who have received copies or rights from you under
this License.  If your rights have been terminated and not permanently
reinstated, you do not qualify to receive new licenses for the same
material under section 10.

  9. Acceptance Not Required for Having Copies.

  You are not required to accept this License in order to receive or
run a copy of the Program.  Ancillary propagation of a covered work
occurring solely as a consequence of using peer-to-peer transmission
to receive a copy likewise does not require acceptance.  However,
nothing other than this License grants you permission to propagate or
modify any covered work.  These actions infringe copyright if you do
not accept this License.  Therefore, by modifying or propagating a
covered work, you indicate your acceptance of this License to do so.

  10. Automatic Licensing of Downstream Recipients.

  Each time you convey a covered work, the recipient automatically
receives a license from the original licensors, to run, modify and
propagate that work, subject to this License.  You are not responsible
for enforcing compliance by third parties with this License.

  An "entity transaction" is a transaction transferring control of an
organization, or substantially all assets of one, or subdividing an
organization, or merging organizations.  If propagation of a covered
work results from an entity transaction, each party to that
transaction who receives a copy of the work also receives whatever
licenses to the work the party's predecessor in interest had or could
give under the previous paragraph, plus a right to possession of the
Corresponding Source of the work from the predecessor in interest, if
the predecessor has it or can get it with reasonable efforts.

  You may not impose any further restrictions on the exercise of the
rights granted or affirmed under this License.  For example, you may
not impose a license fee, royalty, or other charge for exercise of
rights granted under this License, and you may not initiate litigation
(including a cross-claim or counterclaim in a lawsuit) alleging that
any patent claim is infringed by making, using, selling, offering for
sale, or importing the Program or any portion of it.

  11. Patents.

  A "contributor" is a copyright holder who authorizes use under this
License of the Program or a work on which the Program is based.  The
work thus licensed is called the contributor's "contributor version".

  A contributor's "essential patent claims" are all patent claims
owned or controlled by the contributor, whether already acquired or
hereafter acquired, that would be infringed by some manner, permitted
by this License, of making, using, or selling its contributor version,
but do not include claims that would be infringed only as a
consequence of further modification of the contributor version.  For
purposes of this definition, "control" includes the right to grant
patent sublicenses in a manner consistent with the requirements of
this License.

  Each contributor grants you a non-exclusive, worldwide, royalty-free
patent license under the contributor's essential patent claims, to
make, use, sell, offer for sale, import and otherwise run, modify and
propagate the contents of its contributor version.

  In the following three paragraphs, a "patent license" is any express
agreement or commitment, however denominated, not to enforce a patent
(such as an express permission to practice a patent or covenant not to
sue for patent infringement).  To "grant" such a patent license to a
party means to make such an agreement or commitment not to enforce a
patent against the party.

  If you convey a covered work, knowingly relying on a patent license,
and the Corresponding Source of the work is not available for anyone
to copy, free of charge and under the terms of this License, through a
publicly available network server or other readily accessible means,
then you must either (1) cause the Corresponding Source to be so
available, or (2) arrange to deprive yourself of the benefit of the
patent license for this particular work, or (3) arrange, in a manner
consistent with the requirements of this License, to extend the patent
license to downstream recipients.  "Knowingly relying" means you have
actual knowledge that, but for the patent license, your conveying the
covered work in a country, or your recipient's use of the covered work
in a country, would infringe one or more identifiable patents in that
country that you have reason to believe are valid.

  If, pursuant to or in connection with a single transaction or
arrangement, you convey, or propagate by procuring conveyance of, a
covered work, and grant a patent license to some of the parties
receiving the covered work authorizing them to use, propagate, modify
or convey a specific copy of the covered work, then the patent license
you grant is automatically extended to all recipients of the covered
work and works based on it.

  A patent license is "discriminatory" if it does not include within
the scope of its coverage, prohibits the exercise of, or is
conditioned on the non-exercise of one or more of the rights that are
specifically granted under this License.  You may not convey a covered
work if you are a party to an arrangement with a third party that is
in the business of distributing software, under which you make payment
to the third party based on the extent of your activity of conveying
the work, and under which the third party grants, to any of the
parties who would receive the covered work from you, a discriminatory
patent license (a) in connection with copies of the covered work
conveyed by you (or copies made from those copies), or (b) primarily
for and in connection with specific products or compilations that
contain the covered work, unless you entered into that arrangement,
or that patent license was granted, prior to 28 March 2007.

  Nothing in this License shall be construed as excluding or limiting
any implied license or other defenses to infringement that may
otherwise be available to you under applicable patent law.

  12. No Surrender of Others' Freedom.

  If conditions are imposed on you (whether by court order, agreement or
otherwise) that contradict the conditions of this License, they do not
excuse you from the conditions of this License.  If you cannot convey a
covered work so as to satisfy simultaneously your obligations under this
License and any other pertinent obligations, then as a consequence you may
not convey it at all.  For example, if you agree to terms that obligate you
to collect a royalty for further conveying from those to whom you convey
the Program, the only way you could satisfy both those terms and this
License would be to refrain entirely from conveying the Program.

  13. Use with the GNU Affero General Public License.

  Notwithstanding any other provision of this License, you have
permission to link or combine any covered work with a work licensed
under version 3 of the GNU Affero General Public License into a single
combined work, and to convey the resulting work.  The terms of this
License will continue to apply to the part which is the covered work,
but the special requirements of the GNU Affero General Public License,
section 13, concerning interaction through a network will apply to the
combination as such.

  14. Revised Versions of this License.

  The Free Software Foundation may publish revised and/or new versions of
the GNU General Public License from time to time.  Such new versions will
be similar in spirit to the present version, but may differ in detail to
address new problems or concerns.

  Each version is given a distinguishing version number.  If the
Program specifies that a certain numbered version of the GNU General
Public License "or any later version" applies to it, you have the
option of following the terms and conditions either of that numbered
version or of any later version published by the Free Software
Foundation.  If the Program does not specify a version number of the
GNU General Public License, you may choose any version ever published
by the Free Software Foundation.

  If the Program specifies that a proxy can decide which future
versions of the GNU General Public License can be used, that proxy's
public statement of acceptance of a version permanently authorizes you
to choose that version for the Program.

  Later license versions may give you additional or different
permissions.  However, no additional obligations are imposed on any
author or copyright holder as a result of your choosing to follow a
later version.

  15. Disclaimer of Warranty.

  THERE IS NO WARRANTY FOR THE PROGRAM, TO THE EXTENT PERMITTED BY
APPLICABLE LAW.  EXCEPT WHEN OTHERWISE STATED IN WRITING THE COPYRIGHT
HOLDERS AND/OR OTHER PARTIES PROVIDE THE PROGRAM "AS IS" WITHOUT WARRANTY
OF ANY KIND, EITHER EXPRESSED OR IMPLIED, INCLUDING, BUT NOT LIMITED TO,
THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
PURPOSE.  THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF THE PROGRAM
IS WITH YOU.  SHOULD THE PROGRAM PROVE DEFECTIVE, YOU ASSUME THE COST OF
ALL NECESSARY SERVICING, REPAIR OR CORRECTION.

  16. Limitation of Liability.

  IN NO EVENT UNLESS REQUIRED BY APPLICABLE LAW OR AGREED TO IN WRITING
WILL ANY COPYRIGHT HOLDER, OR ANY OTHER PARTY WHO MODIFIES AND/OR CONVEYS
THE PROGRAM AS PERMITTED ABOVE, BE LIABLE TO YOU FOR DAMAGES, INCLUDING ANY
GENERAL, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES ARISING OUT OF THE
USE OR INABILITY TO USE THE PROGRAM (INCLUDING BUT NOT LIMITED TO LOSS OF
DATA OR DATA BEING RENDERED INACCURATE OR LOSSES SUSTAINED BY YOU OR THIRD
PARTIES OR A FAILURE OF THE PROGRAM TO OPERATE WITH ANY OTHER PROGRAMS),
EVEN IF SUCH HOLDER OR OTHER PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF
SUCH DAMAGES.

  17. Interpretation of Sections 15 and 16.

  If the disclaimer of warranty and limitation of liability provided
above cannot be given local legal effect according to their terms,
reviewing courts shall apply local law that most closely approximates
an absolute waiver of all civil liability in connection with the
Program, unless a warranty or assumption of liability accompanies a
copy of the Program in return for a fee.

                     END OF TERMS AND CONDITIONS

            How to Apply These Terms to Your New Programs

  If you develop a new program, and you want it to be of the greatest
possible use to the public, the best way to achieve this is to make it
free software which everyone can redistribute and change under these terms.

  To do so, attach the following notices to the program.  It is safest
to attach them to the start of each source file to most effectively
state the exclusion of warranty; and each file should have at least
the "copyright" line and a pointer to where the full notice is found.

    <one line to give the program's name and a brief idea of what it does.>
    Copyright (C) <year>  <name of author>

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.

Also add information on how to contact you by electronic and paper mail.

  If the program does terminal interaction, make it output a short
notice like this when it starts in an interactive mode:

    <program>  Copyright (C) <year>  <name of author>
    This program comes with ABSOLUTELY NO WARRANTY; for details type `show w'.
    This is free software, and you are welcome to redistribute it
    under certain conditions; type `show c' for details.

The hypothetical commands `show w' and `show c' should show the appropriate
parts of the General Public License.  Of course, your program's commands
might be different; for a GUI interface, you would use an "about box".

  You should also get your employer (if you work as a programmer) or school,
if any, to sign a "copyright disclaimer" for the program, if necessary.
For more information on this, and how to apply and follow the GNU GPL, see
<https://www.gnu.org/licenses/>.

  The GNU General Public License does not permit incorporating your program
into proprietary programs.  If your program is a subroutine library, you
may consider it more useful to permit linking proprietary applications with
the library.  If this is what you want to do, use the GNU Lesser General
Public License instead of this License.  But first, please read
<https://www.gnu.org/licenses/why-not-lgpl.html>.

````
<!-- /provenance-file -->

<a id="original-4618582b33e7"></a>

### `licenses/vendor/xmltodict-0.13.0-LICENSE.txt`

<!-- provenance-file {"path": "licenses/vendor/xmltodict-0.13.0-LICENSE.txt", "bytes": 1085, "sha256": "d66d5eb8f83a0ba21d3dd04318b8817588e8764daabea852d1035e3f07ffda55", "newline": "lf"} -->
````text
Copyright (C) 2012 Martin Blech and individual contributors.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

````
<!-- /provenance-file -->

<a id="original-de8ff34d4a81"></a>

### `release/kodi-vendors.json`

<!-- provenance-file {"path": "release/kodi-vendors.json", "bytes": 26263, "sha256": "f1d18e1f3c46f0935f0ca36ee0f967511d4dd248883764df849faa4be264b8a5", "newline": "lf"} -->
````json
{
  "script.skinvariables": {
    "repository": "https://github.com/jurialmunkey/script.skinvariables",
    "commit": "45be183640d4a3f1be96ad97c7d0032b2a174dcb",
    "archive_sha256": "06efb0ee57e28f7c0690bdf501cf588e85b1e0926efdd3d33da8df8071c7bb3b",
    "files": {
      "LICENSE.txt": "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986",
      "README.md": "8ff89fa2bb7c60032a5b9479209ee758d76f0c6541a451e035dcc006b81bde16",
      "addon.xml": "ac45fc06fbaef757e7df900d25f3d9bda9eca23d83b8bd546844483091297ee6",
      "fanart.jpg": "9a0caf108af5cb216478728f3bada3dc9ef1d4bf0560228875819c433c8a8a79",
      "icon.png": "26b1e74aaf7f144f24c8a9a07b93f6ea9e16add38e7bc49e6b0e45e4eb24a902",
      "plugin.py": "1c6c9cd20a334734b81096f54507a84b0325ad4e8970e925091359c18157250f",
      "resources/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "resources/language/resource.language.ar_sa/strings.po": "e1daf86aa5a7c84b9d0b0f647fa00320ecce96a9c3281a8e8cca30d049b4a20b",
      "resources/language/resource.language.de_de/strings.po": "438b2b4a799b674acff478f0c89e88204e8b82db87108729b97a92b5e29abc92",
      "resources/language/resource.language.en_gb/strings.po": "69bb7cbdcc1297f346ff6528bd74146d5c6f3022b63f2886a08a11be79ec6ee2",
      "resources/language/resource.language.es_es/strings.po": "7f3f66a9809d9e373d8246e5b9d46d0708e04d61c62dede2a6e9d04620ec1dbf",
      "resources/language/resource.language.fi_fi/strings.po": "b203af92c671c333d5905fca123e3cfeaa9990e2a8eb15978f3489542d135ea6",
      "resources/language/resource.language.fr_fr/strings.po": "5c8474268d07c93eedd766ffcb4edc77e9c86ecbee14f040a1b6fc752224fcc4",
      "resources/language/resource.language.hu_hu/strings.po": "58c792cba655f0a87835d80f8bd0382c88a40727916e314248f5daeb9d8d821b",
      "resources/language/resource.language.nl_nl/strings.po": "73c5601ddbc6ba93e2c5513b427c4497655c32a812dde997dfe6d0ec49ba5efa",
      "resources/language/resource.language.pl_pl/strings.po": "18091c33c9ab7d9adec93b9a6c07017769540da01f2baae2c5c2e4221783a548",
      "resources/language/resource.language.pt_br/strings.po": "b800e7fa1bb39526961a71cc3cec0d0617bd5fbec355fa1a27672eca98277407",
      "resources/language/resource.language.ru_ru/strings.po": "1eb84f1d0c46cb6d021777194bf414b789985511a05be193f08b93ae66cfa53d",
      "resources/language/resource.language.uk_ua/strings.po": "88545eefeabe83f9df2a55731c38a56348b2797c54b76c790215d9ddf6921c58",
      "resources/language/resource.language.zh_cn/strings.po": "1aded3e88239d74b1ea333c4090ffe2d4d5729c17c35dab396d09bef23dcb3a4",
      "resources/lib/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "resources/lib/filters.py": "5a36c2da1874fe194f64de8ba911e9d3cc812dc942ffbe1da1a26f5c875b6cac",
      "resources/lib/kodiutils.py": "acf3f9efc5227f8b6b8ef6cc7d6794497ed302e54f679117afb9a47f1220d5d9",
      "resources/lib/lists/filterdir.py": "44ce3ae87208cf8003f4a09e6f0351f1202a4ca4f3133e69b8b49b899ee0f5f4",
      "resources/lib/lists/koditools.py": "2d8055b20cd34d6fd0932cffea325ecf09d5c79529cdfc2408fdc075b1ec8f78",
      "resources/lib/lists/labelgetter.py": "4d83a792979cb1f5810d0a03fae7fb33175dac5c1ee1cacc71698d714fc7d25b",
      "resources/lib/lists/padpanels.py": "8cef99c5cc3039d0a9d0e22bfc6e86cff2f05306ee73492b824ea5a9e17ded83",
      "resources/lib/lists/playerstreams.py": "809be05545a20d27d0bb7eb5b69d655fc13c78e5cf6425b6014acdb268a7922b",
      "resources/lib/lists/quickstats.py": "7c0afeaa387d962a9466b403ae51d2f970df28ad902061c286e4468b0b604d6b",
      "resources/lib/lists/skinusers.py": "91ed36dfd877f2ba835de56a37189f8a74dd3622129af58d5b32960b8521ddc6",
      "resources/lib/lists/stackedbarstats.py": "2b1b99a54b4c8d828590bdd48008ec684bf01ae0373f0984253f458d12f20b45",
      "resources/lib/method.py": "03f8ee3b858c5e8a1422836fcf1b99c1cab8510b7e900e08dc783977b330d4f2",
      "resources/lib/operations.py": "ced50caec5ac071c133a6e5940a228f4e4646af8ef4e253c404f505447a8da64",
      "resources/lib/plugin.py": "3d51afd323fdc9e058d7c76bb6d794034f5fbc0439b4a3545f5d8150b9a40b07",
      "resources/lib/script.py": "5e71f9837b34f66429f9d2d1c8feda27d36eea400850d9d18260f43f1977900c",
      "resources/lib/shortcuts/browser.py": "da5ce3db293a43df8cd1e7648f15e2c9957787e6e4b5343869b8d5bb0fc71ee8",
      "resources/lib/shortcuts/common.py": "524f1aa0c3d14bfb6be9f8652da463e6097ae8be5eb3ef84a698c1969d12a911",
      "resources/lib/shortcuts/futils.py": "c4445b3ad6e5ff0686fe024078b69e2b7264049832df3fe3e8f609ddad16a8b6",
      "resources/lib/shortcuts/grouping.py": "be2c197f9b26b08b5b5a4a1754c62de8011ad966d112904bf4358f30f06f3aac",
      "resources/lib/shortcuts/jsonrpc.py": "59f42e6e89529204c8793345079194c1cb0570ac7880309c9441bcbf2b1b63af",
      "resources/lib/shortcuts/method.py": "ee4b68832a57db3e6c992f338202c5707709d542d70c54be45cd50d643b3e59e",
      "resources/lib/shortcuts/node.py": "fba35f3d978e504ca85a29aefbd59fa47dfa2f9288f88611931e90c396b0d93e",
      "resources/lib/shortcuts/skinshortcuts.py": "7f1eb35d581a78c49e232dc0667f14dc864ac110774bdf2ebca541dc3de5af54",
      "resources/lib/shortcuts/template.py": "9bcfd588ed7e7b03281f8fa4af01e27d0a8173bdd2fac313ae616bc1d9ebf275",
      "resources/lib/shortcuts/xmltojson.py": "bc39fc0fd53d01b0533bbf10926553ebfe8b41db1fb5b4af9958ff128004a73c",
      "resources/lib/skinvariables.py": "ba4fda22277c0e0a9815134f8963175e4a55f8135f327b842683687806077992",
      "resources/lib/viewtypes.py": "5c91feeb2c72080c6482baf88fc7ed485dd5c9ff90d5593d365b20ebe948a19c",
      "resources/lib/xmlhelper.py": "360e7886df50a6f2f8fb721d7b23a32c62bf4f5579d49e560254cfc9c284e8f3",
      "script.py": "bb394d50a46ddae48f24b7840c1826c55a3b6586eb2922ced91e14f3de98d3de"
    }
  },
  "script.module.jurialmunkey": {
    "repository": "https://github.com/jurialmunkey/script.module.jurialmunkey",
    "commit": "8f42fb5f4698f3e4552f38955964b2f3843dba69",
    "archive_sha256": "08d30ed4cbd628a2f743ce835934b676b53773bb1fc3de56775e983974d985a2",
    "files": {
      "addon.xml": "f355a2810c2022d1992e2ba52299092774b62c9ace40e7508d989e083e466175",
      "icon.png": "3fc0686ccbd5bf4f288816f5d4658a56b024ea388fc294f3899a3faa21899693",
      "resources/language/resource.language.en_gb/strings.po": "41a763e34664310ae241c7b05cebaabb78dcefd308a2e7fcaa944dd383ba3f8e",
      "resources/language/resource.language.fi_fi/strings.po": "88eebbd33169f758fae2f14e6a0a83fa9a3285ef06fb49db6a7230045ecf1ab0",
      "resources/language/resource.language.zh_cn/strings.po": "bcd24782b0cd768ad51afcb0a0e84d04e15c4e234adcc47c48fbbce3f7a7516f",
      "resources/modules/jurialmunkey/bcache.py": "ac33adaea4e62c408f7cdd8c6531a1cbdb85fc92eb4ea0d9b02b31a2c8532bb7",
      "resources/modules/jurialmunkey/checks.py": "ba5ed5e52467314febaeda22acef280713fb321ac5b2d61aff12bbee07bcf3da",
      "resources/modules/jurialmunkey/dialog.py": "7c0f3efd88d6083f79f7cc02aa5a8a0696da5176c8cccd91a3334a1cd37ae4f5",
      "resources/modules/jurialmunkey/ftools.py": "432e0f78260043572b1f0079dd15c0968a5ee469a7e91826cbd1cfd7e5d2523c",
      "resources/modules/jurialmunkey/futils.py": "b864c89f0645e464c0a4dbad1e65bf7a496ffc96dbced3fcd869b5afc8f36289",
      "resources/modules/jurialmunkey/jrpcid.py": "6e36cee5be672b1b2d58559612fe61af0b867a779fb3945a89c3ebcb3b884acb",
      "resources/modules/jurialmunkey/jsnrpc.py": "434c0fb9c409740f16f7b466fb4aec6a3cd53d34c263aa68555bb65e47d90774",
      "resources/modules/jurialmunkey/litems.py": "dfb7a13bcf2512d13203cb1242641028a2a79ed9901ea9c9565a9515ad8ea428",
      "resources/modules/jurialmunkey/locker.py": "82742e47ff2e56cdbb75330154597da8dd15ed33a0a6acd5a6aca8786f44ebf9",
      "resources/modules/jurialmunkey/logger.py": "1274269bf6fe307e52dd18b8e6b67eae8664040e34da2a5d1d64aeb54c266fcb",
      "resources/modules/jurialmunkey/modimp.py": "8a3c3060c965f0292a44067598e2fea9e5df529194b59cfd3212580ef3180bef",
      "resources/modules/jurialmunkey/parser.py": "db045079b6d4fa05227e7fb8a45a34facb9d20c9ca4f69ba8b312bc7410f75b1",
      "resources/modules/jurialmunkey/plugin.py": "2d96f85b5360aa06b69196a3958fed543dfed78ff2e1c35c775cd925d173ae5d",
      "resources/modules/jurialmunkey/reqapi.py": "19351bbe5a5aa7bf9c2f3f893a61ae7effb7ed70afa2d0118d59082e362d0367",
      "resources/modules/jurialmunkey/scache.py": "b5c54ff7468b7c6588a1224cbcfc16bac9ed16b3ab27169deb7fc5606f90ac1a",
      "resources/modules/jurialmunkey/thread.py": "509baac681757bd3ba760ed40f79e805469518259559239be5274f273a491479",
      "resources/modules/jurialmunkey/tmdate.py": "10052bf70d58c399f92c4687515006d9db369424ab05934e55c09fe20f87fea7",
      "resources/modules/jurialmunkey/window.py": "9f8bf242b206cac116c3a708c44c090757e0073241a8f514bb57d829fd9b54fa",
      "LICENSE.bobbi-supplement": "605e9047a563c5c8396ffb18232aa4304ec56586aee537c45064c6fb425e44ad"
    }
  },
  "script.module.infotagger": {
    "repository": "https://github.com/jurialmunkey/script.module.infotagger",
    "commit": "0118f53c9cf68a6625794d07af607cac1e920064",
    "archive_sha256": "88cc58ae6fdfce888775018e6e9ccf4d9370120b1886a9e27d467ff9f5e79939",
    "files": {
      "README.md": "887039dde4645c449f57c95e9211419a3be548c5181bccc6f5c41b1cff14231f",
      "addon.xml": "0810c77be8311cc2b7f703b8fb124ca1607722fc9d307899c9d1cd8eba94729a",
      "icon.png": "9a68876be1a6d21dbc00a4123426d763beeb1481f85d815aee9caa8b3a4eed76",
      "resources/modules/infotagger/listitem.py": "5d0dd6f7518790280eb44b888ff937b140e1366b9b44350d46992b3565f38594",
      "LICENSE.bobbi-supplement": "605e9047a563c5c8396ffb18232aa4304ec56586aee537c45064c6fb425e44ad"
    }
  },
  "script.module.requests": {
    "repository": "https://mirrors.kodi.tv/addons/omega/",
    "version": "2.31.0",
    "archive_url": "https://mirrors.kodi.tv/addons/omega/script.module.requests/script.module.requests-2.31.0.zip",
    "archive_sha256": "a5704f0fd7afb4154e1beea9b5f05a002bcd75fa581a1e5fd15ece39bf2bd38a",
    "archive_bytes": 67576,
    "license": "Apache-2.0",
    "upstream": "https://github.com/psf/requests",
    "files": {
      "LICENSE.txt": "09e8a9bcec8067104652c168685ab0931e7868f9c8284b66f5ae6edae5f1130b",
      "addon.xml": "7921891c05b4fbb1ddbc8fc9d78ecab2ce083b3a83015cd670427ea0ff4e950d",
      "resources/icon.png": "2fc540686b156482ff46bd1c8042f96c8bc0739ead44c9d1eadb5cb27ee1ead0",
      "lib/requests/sessions.py": "f8bbd3ceb3ed7ad493ad1ddbbb1bb85e176032b2452c1d6ae43ecffbe2f65e1c",
      "lib/requests/exceptions.py": "0e1bde1417255634d1c6145db95a4ef866cc60c203da09a374b7cd12a36923f5",
      "lib/requests/hooks.py": "0a2bb2b221c0dfd57951f702057148c7cdc8ac3a6ec1f37d45c4d482fdbc7ed4",
      "lib/requests/api.py": "abad71717ab8b668889abbdc4952d36c5c82883d85f8bffe8562866f3e32f2f8",
      "lib/requests/__version__.py": "b2c237133b7b3dac6090e5b8e4686dc0f51c968fd23bfca0b489b803be0839fc",
      "lib/requests/auth.py": "87e1cb955c7d8fcaca57985f480c9c3f60293928254f3efb474b73eea09b6c41",
      "lib/requests/adapters.py": "bff1668d4e4a67bea4f98b6d4a1658079469ac8ce184bf18df3816f69e1e050f",
      "lib/requests/structures.py": "f886e6855cf4e92fb968f499b94b6167afba0fd5ce8d1b935c739a6d8d38d573",
      "lib/requests/packages.py": "0d782ff852487336484e6bf4bc40408568f85bee4218220dfe4b2f811d7b0efb",
      "lib/requests/utils.py": "eacc765f7708540f018163a0f28771172fbf95b5831444d4f072387d4e119aac",
      "lib/requests/help.py": "80f5f977f1fb5ddf3c6830017a386a1a097d075545453b79066898bcbdcfcc84",
      "lib/requests/cookies.py": "903de43447028fe9b16ed7f97c9b12693f3a786a046290f75f4092829ce5ec13",
      "lib/requests/_internal_utils.py": "9cc4329abe21b37d93a95a3901b0ab99c24486f3d487bc57965bb2ab0b252e24",
      "lib/requests/status_codes.py": "16f1e64f9b87fbfba29ad473e611fd5426eded557e35e8b627dba96de8fa8fc8",
      "lib/requests/models.py": "f8394a8b4a2bf2014033a573bada1b5efbc15bfdb0ac9b8e17935f9dd4c875d0",
      "lib/requests/certs.py": "67d49be35d009efea35054f2b2cd23145854eb1b2df1cb442ea7f2f04bf6de0c",
      "lib/requests/__init__.py": "2ef98a863233f261da297b610b632fe72919d5df76be8c9fde826977e56e0228",
      "lib/requests/compat.py": "cb19ed54e4841c632b9fb14daffdf61046a6d5934074f45d484d77ff2687cd39"
    }
  },
  "script.module.routing": {
    "repository": "https://mirrors.kodi.tv/addons/omega/",
    "version": "0.2.3+matrix.1",
    "archive_url": "https://mirrors.kodi.tv/addons/omega/script.module.routing/script.module.routing-0.2.3+matrix.1.zip",
    "archive_sha256": "dc9110ffd2a5022feffafb22a710cd95aabe5722c52004f347d3a274f67d00f9",
    "archive_bytes": 25369,
    "license": "GPL-3.0",
    "upstream": "https://github.com/tamland/kodi-plugin-routing",
    "files": {
      "LICENSE.txt": "0ae0485a5bd37a63e63603596417e4eb0e653334fa6c7f932ca3a0e85d4af227",
      "README.md": "d016cab6fc6a4b1b0481e4f55431e8576f752c2427611aeef684ee29d7821435",
      "addon.xml": "cb1e56f8b08ccc617784144435a7fa77742cbbba885a95d5fdb6ffd01a50925f",
      "resources/icon.png": "2fc540686b156482ff46bd1c8042f96c8bc0739ead44c9d1eadb5cb27ee1ead0",
      "lib/routing.py": "5268e8efd42d0b4f016c0dfd61bb8008e3f02e8c49441af9e61cb9c60eae9144",
      "lib/tests.py": "b8f49c49ece2c5f83bdd9fb05f0360e359e5bcc9635c772695155849ab690f92"
    }
  },
  "script.module.certifi": {
    "repository": "https://mirrors.kodi.tv/addons/omega/",
    "version": "2023.5.7",
    "archive_url": "https://mirrors.kodi.tv/addons/omega/script.module.certifi/script.module.certifi-2023.5.7.zip",
    "archive_sha256": "c16d4cd2efe6e57dbb5e8d71a9beb3af213b1e3d717e8b0b24f0cbdc4c645070",
    "archive_bytes": 162689,
    "license": "MPL-2.0",
    "upstream": "https://github.com/certifi/python-certifi",
    "files": {
      "LICENSE.txt": "a02f6c638f9fb84d06f7764c3ab085d8af7eda5b93c166da54312479077c6fb0",
      "addon.xml": "186548abb00ea69b67b43bd23f988b1f68150332d9ca5698c9b48c4beffe0732",
      "resources/icon.png": "2fc540686b156482ff46bd1c8042f96c8bc0739ead44c9d1eadb5cb27ee1ead0",
      "lib/certifi/__main__.py": "c410688fdd394d45812d118034e71fee88ba7beddd30fe1c1281bd3b232cd758",
      "lib/certifi/__init__.py": "ab978fce795f3b0f97608395e914e7878e724bd85a37e35bd5dfffe105dcde0d",
      "lib/certifi/core.py": "9617b0cf4cc56f66f850bb10bab1259a5a18c10a1e7235b33ea63aecff13ee23",
      "lib/certifi/cacert.pem": "b301535dca491d9814ea28faa320ac7a19d0f5d94237996fa0a3b5a936432514"
    }
  },
  "script.module.chardet": {
    "repository": "https://mirrors.kodi.tv/addons/omega/",
    "version": "5.1.0",
    "archive_url": "https://mirrors.kodi.tv/addons/omega/script.module.chardet/script.module.chardet-5.1.0.zip",
    "archive_sha256": "d5010fc55a9523d86a306ae9e6a8dea0e3248fe079b9ed37280fe86110cd766a",
    "archive_bytes": 204491,
    "license": "LGPL-2.1",
    "upstream": "https://github.com/chardet/chardet",
    "files": {
      "LICENSE.txt": "6095e9ffa777dd22839f7801aa845b31c9ed07f3d6bf8a26dc5d2dec8ccc0ef3",
      "addon.xml": "73aa4e0b9f9ad26896a6d63df4321bb4dbb2eac5ebdc463c1c997902b6a3078b",
      "resources/icon.png": "2fc540686b156482ff46bd1c8042f96c8bc0739ead44c9d1eadb5cb27ee1ead0",
      "lib/chardet/codingstatemachinedict.py": "d066371e2daa219bc3ace389dc0b6aa6933546c631affeba111e041e3b8c88c7",
      "lib/chardet/utf8prober.py": "f26d3c51be78f741f88d0e8b617bc5cac1ad80aa0ab0751ddb31ff8bcfd39d5c",
      "lib/chardet/universaldetector.py": "c5806b838c7475df569d3f2a7257c00d50fda2776b50d92a3e6bed7b5a5ae76d",
      "lib/chardet/gb2312freq.py": "e3d3ab757cc3f875eac1abe4aa3a3c67b82fb39f2138d3730e103230434d92f6",
      "lib/chardet/hebrewprober.py": "f7a4ff2e3fce996f9f2bb26b487a23623c86ddfb0681bce4a13365799de47d81",
      "lib/chardet/langgreekmodel.py": "df032513343ca14d8c6eb2f6c4df2592e381d1d08c2c1856ea179e931baca1cd",
      "lib/chardet/mbcsgroupprober.py": "891a5a3418d5d0337060fbbfcfa4e21e0469c186a188cef3b48ff8919e14cfd0",
      "lib/chardet/enums.py": "4f3102899a0228d32a83053be9c3c278a58506a696bc074b31ebf9fdb0a4858f",
      "lib/chardet/utf1632prober.py": "a70d5ea4674c8f58431a20aed401eaab33847e35fc3157625bb3b50654fcf9e4",
      "lib/chardet/langhebrewmodel.py": "6544eabacc4cbd1fde6ab58fb39c3eac7d74c687b9b0f8ddf452ccbb50d422f1",
      "lib/chardet/euctwprober.py": "3716e935d06d5345452346ca7c67c39293fb4b6ffcffa1653bcedd547d28830b",
      "lib/chardet/euckrfreq.py": "de61ee46f5dfb2afd0710cac0d015bf2a4ae76f4e2a25ef50ba21cdb0e7bb4a3",
      "lib/chardet/__init__.py": "e7b47e1d2c63d0f5a620b30dd0616650da8431fac45526a65f28c3f96ebf7dbb",
      "lib/chardet/escsm.py": "02ac97a40d854050fb93e6ee06dcbfee2b461189219956bc5f4f4d2d1ba5dd03",
      "lib/chardet/jisfreq.py": "9a6f2d7ebc2a86939ddf0cd9292e0d26a91805055c0df4ccd89890e5a5bddf61",
      "lib/chardet/langrussianmodel.py": "eafed17192868f4547d3ceb8047ce2cca35c78061b1ef1adb36a74d227c2ef0e",
      "lib/chardet/johabfreq.py": "741a4e606df81915fa48bf24fcb6d2f6bc593cc8cb8e8325819d373f3e479aa7",
      "lib/chardet/eucjpprober.py": "e4a61a33d7ecc64458cf0d5be64d1f2fe8fff9ecc8c3e8a3f6bf7b6bd307c4b6",
      "lib/chardet/euckrprober.py": "862153eb0335ef8188c11bea0ec21cb8e73e743b2adae3ca30a6f257cfb55e77",
      "lib/chardet/sjisprober.py": "6aa42e7cccd1c38e99a45973998698793dbe9f398a6fe86672b029a6927ceb69",
      "lib/chardet/sbcsgroupprober.py": "81c808d1f39f830ff76130a5a5badafcc371c321322777945eb6a82c761be7d1",
      "lib/chardet/langbulgarianmodel.py": "6c6a11a71058b6b6d21daea65fa3e4100dbabf7d295a68438de9a17719a47b0f",
      "lib/chardet/mbcharsetprober.py": "5abd3858d2381775ff57112f7ab346f87db983bbbe3030ca94db7e2468fefee5",
      "lib/chardet/macromanprober.py": "f5a9dfce663a4c17d43c3c810ce758d3b92a9931e9675b4ad232fea7525670e6",
      "lib/chardet/big5prober.py": "94f31fc025fabf601a3e0bc587f7125997202c36d68850872d9fe9f5143dbb11",
      "lib/chardet/charsetgroupprober.py": "50a2b749a2190763c274a4884b4827bccb4b47d2495fad8cf9f649bb73a55b28",
      "lib/chardet/sbcharsetprober.py": "fa777717dd22ec6a572e37a12d51ea5411342a55b31af4143c44cb04d9f8a3a5",
      "lib/chardet/euctwfreq.py": "d9a9482c4d4b8797aa8852598f34643105e894d2511d8e6805077ebe66581453",
      "lib/chardet/big5freq.py": "96d71f3fedcf8e53470a8a397b86bb0b8cfed838414d745f63a8db31b07b3f7d",
      "lib/chardet/latin1prober.py": "a75e4412615b9905306ca2c2ee53895461c4670706e39b9b1196131aed352798",
      "lib/chardet/mbcssm.py": "854b4fbc3620583680d9d59d80bb2c85bc117e6dd0e5846546881d99e454350c",
      "lib/chardet/codingstatemachine.py": "2bb93af6cc378d8e439935e8489415b14b452102983d054e48926106e1afff21",
      "lib/chardet/langturkishmodel.py": "2e45c28d6846504cea297bdf6ac1cdd121418a0c0a277c5e58d559d04c88d240",
      "lib/chardet/jpcntx.py": "ba11eb61690bc44feb1793a41ca2279b41d4b2b8e02871d542fb6ddd472fa2d0",
      "lib/chardet/langhungarianmodel.py": "37e62d0b6122b30c92ed7b1489c08f47272b23344d8f8ed8d38f28769f6a3a8a",
      "lib/chardet/charsetprober.py": "2f7b7cff020ea2ff1e9bebd958e71b91db2bc1ee3737afe0a8d879a47ed63dde",
      "lib/chardet/resultdict.py": "7b3e0546f37929a4a8b09789d96cd4c8a743760df91c3cbf4922cf5ca09db793",
      "lib/chardet/gb2312prober.py": "28f101b9e6922d2bc1a4578834cbb40fa4e01dc47dd1ee4f6906b089fcc5e28d",
      "lib/chardet/version.py": "946b4973118ce38433e026e4e2b6db9ab2b19cdaf5fbded4db94da99e2de859c",
      "lib/chardet/escprober.py": "2a1a38f17eb9c44d2c705ca521d7898ccd9b71bbd1befd21d1651b316ac90f70",
      "lib/chardet/chardistribution.py": "d7707c5d41b8a170ee2dd5ef7db216c0b15e47e654db502a4d2d7371d38df1b5",
      "lib/chardet/cp949prober.py": "d2329157b7c40ae588d7aacd9e4b3464408a03589960220468ff00d59be35122",
      "lib/chardet/johabprober.py": "3b5430f67573467ba7eef669e1464cef0bc94aff56f78d66114f6e0cc9d8dc35",
      "lib/chardet/langthaimodel.py": "32bebbdd4f54f2b91015f503b4b3f4d69a7ed133ac976a3ab1bef96048efa5cb",
      "lib/chardet/metadata/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "lib/chardet/metadata/languages.py": "161bc121d645c5143e753c246ffd2669d44a815042694310cfd239c6a8c4e624",
      "lib/chardet/cli/chardetect.py": "ce26cc560e51a4a6fe304f7fec4606e1933649fd3b347710cd9d7653ead8261a",
      "lib/chardet/cli/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }
  },
  "script.module.idna": {
    "repository": "https://mirrors.kodi.tv/addons/omega/",
    "version": "3.10.0",
    "archive_url": "https://mirrors.kodi.tv/addons/omega/script.module.idna/script.module.idna-3.10.0.zip",
    "archive_sha256": "c4ff34dbfab2736e9214a374d331bd6f558d8b3fea8eb7902e210749509242b3",
    "archive_bytes": 73349,
    "license": "BSD-3-Clause",
    "upstream": "https://github.com/kjd/idna",
    "files": {
      "LICENSE.txt": "a59f0b0ef3635874109a4461ca44ff7a70d50696e814767bfaf721d4c9b0db0f",
      "addon.xml": "c250f4a73ac9f6e75d7539879fd59a864ea93e7f9d35bb586953abe6ab4376bd",
      "resources/icon.png": "2fc540686b156482ff46bd1c8042f96c8bc0739ead44c9d1eadb5cb27ee1ead0",
      "lib/idna/compat.py": "4732f2e90402765f7bf3868585bd845fd10a1822638343f73e294675e5d7731f",
      "lib/idna/__init__.py": "30fa8d0cb65b5ea19a35d5f1005862a853ca1105e3bb68cd42109ecbafb97893",
      "lib/idna/package_data.py": "ab9f52dce5ec739548f23eaf483d2c18133293acd9e2f58544413cf3208960ab",
      "lib/idna/uts46data.py": "aedf742bd278d20512c29a433c2ae18e08b9000ea958ceb974419149feab2213",
      "lib/idna/core.py": "60963200c9f089010f8d50b8f85aaefe9e0227ac8a2ae0c69a9a41350350a45b",
      "lib/idna/idnadata.py": "5b7d067081afb4e598c008d98f8663ba8b94bad0ba7df80dbb28c9cbb7d9fa5a",
      "lib/idna/intranges.py": "6a652d91d8587101bc66bf82a0c33f91545a731922bc2d568313756fadca29d5",
      "lib/idna/codec.py": "3c47b0dc8b70ce35b887299b6ac9edcb6376397bcd7201c1f898eb06ec473d86"
    }
  },
  "script.module.urllib3": {
    "repository": "https://mirrors.kodi.tv/addons/omega/",
    "version": "2.2.3",
    "archive_url": "https://mirrors.kodi.tv/addons/omega/script.module.urllib3/script.module.urllib3-2.2.3.zip",
    "archive_sha256": "740b2d63bb50eee9fb35f01c567ec8d3588c5bbd548e2b8d280932be30d82f53",
    "archive_bytes": 130842,
    "license": "MIT",
    "upstream": "https://github.com/urllib3/urllib3",
    "files": {
      "LICENSE.txt": "130e3a64d5fdd5d096a752694634a7d9df284469de86e5732100268041e3d686",
      "addon.xml": "9ee4d9805a67de90965bb7c69c0363983c9961ea6cce8545df5181b50ebc7426",
      "resources/icon.png": "2fc540686b156482ff46bd1c8042f96c8bc0739ead44c9d1eadb5cb27ee1ead0",
      "lib/urllib3/_request_methods.py": "2d30f11de9c43f95d7fad55604d904900822cc211191917424af85fb00b1ab02",
      "lib/urllib3/fields.py": "f2f8b43de468fe91397213e6240d3b2d9b4c91596ce14ac14b5936c4ce74ea33",
      "lib/urllib3/_version.py": "805ef333c02c74b46a860b5e5deb0d1dbeffb7cba4af6cf39289368359efbe10",
      "lib/urllib3/__init__.py": "24ca35b60d67215d40789daf10d0bf4f17e5d1ee61e86ce5f43195935ad645ba",
      "lib/urllib3/connectionpool.py": "e5f3c81f2a4fc256ca04048cb3a6c44931095441a5b23f45398f7f1865361a93",
      "lib/urllib3/poolmanager.py": "dbf2f6023543828434a819986d7f6ef50ab2535bb9277ef341bb6fffeb9e6500",
      "lib/urllib3/response.py": "352d2bab0466b705ad0bfe970ea80324dfeea3e8c4981573c7457a282b079708",
      "lib/urllib3/connection.py": "400c21395e4639576c16732f5f956fe9f43c7f8ec4cdfad138002b7f145d40e6",
      "lib/urllib3/_base_connection.py": "b47d1994ec562a291af92f4d5be32e22523f3cb1505149929e813ff4c7b2c243",
      "lib/urllib3/_collections.py": "686861f7309871ede8fb9156f433d251acba3bd2e31f1f33e93ef00ed761ae46",
      "lib/urllib3/filepost.py": "fbda894f5d5c3468cef5daa7236d3ea04ad9b93bcd68cd7cc5964f0a36526ce1",
      "lib/urllib3/exceptions.py": "4436a2b9db51eeba9b54a4caa4b4a064106dc1a22a57b799b5eaef655fe665a8",
      "lib/urllib3/http2/__init__.py": "c73ac0487ed1e4035190f24ea2de651a70133aadca2aec97cc8e36adc9f09aab",
      "lib/urllib3/http2/connection.py": "18d969f418c8dc399f48a7b55b46fd22a44178cf10d77c5dd8c03744e709ddd6",
      "lib/urllib3/http2/probe.py": "9e7024a9b8406a43a217be6bcfb5b4b9d677f047a1fee0fc7e357be0def71442",
      "lib/urllib3/util/timeout.py": "e1e4f5155799654ee1ee6603d49ab639735ee1fc5e91d36f868594919bac4690",
      "lib/urllib3/util/wait.py": "fe987c22b511deca8faa2d0ea29420254947e30ce419e3390a2c80ed7186b662",
      "lib/urllib3/util/url.py": "c07391869f344405f24e5008913a8b1734ab914ec9df8643c57fad37ae4c0599",
      "lib/urllib3/util/__init__.py": "faa792d1071e8af6b3bc110a0cd142008fba00271d0ce1384ccbe8ed22cd9404",
      "lib/urllib3/util/ssltransport.py": "c29ac1be19208dd76184cc3011b1f23f8972807a4fe924bee3912e87ba1ee3c9",
      "lib/urllib3/util/util.py": "8f795b64ad633f28b00f7e13f08809cdd5846554fee04fb4bd82098bd52378d0",
      "lib/urllib3/util/request.py": "52b676837cb7b2d1a91fcae6f92c7cfa896581e8a2288e3de83657442c316fda",
      "lib/urllib3/util/response.py": "bd013adfdba81218f5be98c4771bb994d22124249466477ba6a965508d0164e0",
      "lib/urllib3/util/connection.py": "d28efdfb935b45fa410f2a1e8463cb982039e38b024a25efc74985f71cb7186d",
      "lib/urllib3/util/ssl_match_hostname.py": "81a5aa8b1a18b50fc628ef1f7111858f755778ca2acb1410b944cf8167a22ff3",
      "lib/urllib3/util/ssl_.py": "58df1ae8a3cf72fba46d9d0c5250403a41a297c6d8298f0da0860ec3b41e38b2",
      "lib/urllib3/util/proxy.py": "b1e3fcf90e41e9b07474cb703e3f98719650df4bc7b8ba91bbeb48d096767f3b",
      "lib/urllib3/util/retry.py": "6e3fb6614a9b9712e5bfc4c78397f1c30f83339e1709b8e0657210ef55e2a026",
      "lib/urllib3/contrib/pyopenssl.py": "f623f88fc25a7c0e21aad5fd02027dcf1aea23e89ca211aba85a8032bca835d0",
      "lib/urllib3/contrib/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "lib/urllib3/contrib/socks.py": "fa26ab75ceb51b2a6c2730fa5bacae452eca542c9fa30710ae5ffbd7d1fb9483",
      "lib/urllib3/contrib/emscripten/fetch.py": "ca6c09947041bb0e964e92a03c7a5d9a6acd07196cafbe47aa80f8467dbb6179",
      "lib/urllib3/contrib/emscripten/__init__.py": "bba28d8338e51596ee0005daff26c247b810ef55491129c5f8821d0c0ef76ebc",
      "lib/urllib3/contrib/emscripten/request.py": "98bdbcb33cb52af137349856a2be633666aba7c830a650d4fbb8301996398344",
      "lib/urllib3/contrib/emscripten/response.py": "c046163c708bf89b200ada42a5f9d6198035f837230c6a451aa5825d92f06c76",
      "lib/urllib3/contrib/emscripten/connection.py": "91a05edad5aded8cbdbcd50544157b092c839df8426082c6c63bbd293663f12c",
      "lib/urllib3/contrib/emscripten/emscripten_fetch_worker.js": "0837d817ff420e86edc7694689dc89d738c312fc0d4f917e75c8665565c38741"
    }
  }
}

````
<!-- /provenance-file -->

<a id="original-3da33a998688"></a>

### `release/private-assets.json`

<!-- provenance-file {"path": "release/private-assets.json", "bytes": 12893, "sha256": "7768b7c3b0e07d706e176bbe1b112e219276a2616baa1d47782dfcfa0e57789b", "newline": "crlf"} -->
````json
{
  "schema": 1,
  "source_commit": "ff530e09c34c6285ccb05c1d4179140b097174fb",
  "distribution": "private-personal",
  "files": [
    {
      "source": "ui-redesign/backend/source/addons/resource.uisounds.am6b-modern/LICENSE",
      "target": "addons/resource.uisounds.bobbi-modern/LICENSE",
      "bytes": 87,
      "source_sha256": "64741185bfb63f5a9c8fd1881cb8cdeb5db95ff5bcf2f2e76d7dd7bc20133c19",
      "sha256": "64741185bfb63f5a9c8fd1881cb8cdeb5db95ff5bcf2f2e76d7dd7bc20133c19"
    },
    {
      "source": "ui-redesign/backend/source/addons/resource.uisounds.am6b-modern/addon.xml",
      "target": "addons/resource.uisounds.bobbi-modern/addon.xml",
      "bytes": 886,
      "source_sha256": "4c719ec44da9b86b7ea668fc17b886a8ef227356c6da6d134da5ddd46d111a38",
      "sha256": "532c393d948404f2e0761af9d1d63ea96b4be5ee02c192eda79ea8f10a4757f6"
    },
    {
      "source": "ui-redesign/backend/source/addons/resource.uisounds.am6b-modern/resources/back.wav",
      "target": "addons/resource.uisounds.bobbi-modern/resources/back.wav",
      "bytes": 296888,
      "source_sha256": "dc1de374a1758ef5d826bbd831e158b85ad2246678e40509df2040be42be3340",
      "sha256": "dc1de374a1758ef5d826bbd831e158b85ad2246678e40509df2040be42be3340"
    },
    {
      "source": "ui-redesign/backend/source/addons/resource.uisounds.am6b-modern/resources/error.wav",
      "target": "addons/resource.uisounds.bobbi-modern/resources/error.wav",
      "bytes": 119028,
      "source_sha256": "60644e664e7081dcbcb68b11aba8a0992c9a0ac708fa7c4e011542633098a217",
      "sha256": "60644e664e7081dcbcb68b11aba8a0992c9a0ac708fa7c4e011542633098a217"
    },
    {
      "source": "ui-redesign/backend/source/addons/resource.uisounds.am6b-modern/resources/navigate.wav",
      "target": "addons/resource.uisounds.bobbi-modern/resources/navigate.wav",
      "bytes": 96452,
      "source_sha256": "f87dd2e368ca065474de3ebe3e5f27d3b6987609528f002349dc953c19ec9bc0",
      "sha256": "f87dd2e368ca065474de3ebe3e5f27d3b6987609528f002349dc953c19ec9bc0"
    },
    {
      "source": "ui-redesign/backend/source/addons/resource.uisounds.am6b-modern/resources/notify.wav",
      "target": "addons/resource.uisounds.bobbi-modern/resources/notify.wav",
      "bytes": 430280,
      "source_sha256": "1194fb378b609b007a4af4d63d4f67ace578e3bdc35d471501e92ecc2ab98b1c",
      "sha256": "1194fb378b609b007a4af4d63d4f67ace578e3bdc35d471501e92ecc2ab98b1c"
    },
    {
      "source": "ui-redesign/backend/source/addons/resource.uisounds.am6b-modern/resources/open.wav",
      "target": "addons/resource.uisounds.bobbi-modern/resources/open.wav",
      "bytes": 232154,
      "source_sha256": "a627ae6ef3816f36ea00ae450838045722009c752b2cb1373f054bee6682a498",
      "sha256": "a627ae6ef3816f36ea00ae450838045722009c752b2cb1373f054bee6682a498"
    },
    {
      "source": "ui-redesign/backend/source/addons/resource.uisounds.am6b-modern/resources/out.wav",
      "target": "addons/resource.uisounds.bobbi-modern/resources/out.wav",
      "bytes": 329764,
      "source_sha256": "9b90d3747f70d3602d2143ab8c379602cf412fa6601ab278889fa49050532780",
      "sha256": "9b90d3747f70d3602d2143ab8c379602cf412fa6601ab278889fa49050532780"
    },
    {
      "source": "ui-redesign/backend/source/addons/resource.uisounds.am6b-modern/resources/select.wav",
      "target": "addons/resource.uisounds.bobbi-modern/resources/select.wav",
      "bytes": 232154,
      "source_sha256": "a627ae6ef3816f36ea00ae450838045722009c752b2cb1373f054bee6682a498",
      "sha256": "a627ae6ef3816f36ea00ae450838045722009c752b2cb1373f054bee6682a498"
    },
    {
      "source": "ui-redesign/backend/source/addons/resource.uisounds.am6b-modern/resources/slider.wav",
      "target": "addons/resource.uisounds.bobbi-modern/resources/slider.wav",
      "bytes": 50680,
      "source_sha256": "90d4c2fc9fa8c7b46b334c1c50196dfb88ff237b045d812522ded8edebbecf10",
      "sha256": "90d4c2fc9fa8c7b46b334c1c50196dfb88ff237b045d812522ded8edebbecf10"
    },
    {
      "source": "ui-redesign/backend/source/addons/resource.uisounds.am6b-modern/resources/sounds.xml",
      "target": "addons/resource.uisounds.bobbi-modern/resources/sounds.xml",
      "bytes": 952,
      "source_sha256": "6db6081fb8c1b8d3e136cbaff9945a86ab5cb3796301223447a8520aa797d39f",
      "sha256": "6db6081fb8c1b8d3e136cbaff9945a86ab5cb3796301223447a8520aa797d39f"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/BobiAF-Solid.ttf",
      "target": "addons/skin.bobbi.cinema/fonts/BobiAF-Solid.ttf",
      "bytes": 1003812,
      "source_sha256": "f960c6b83e1a6cc1eac4e6cbe0169b57dad4ce7ecc628664c326e4e6a4ca7904",
      "sha256": "f960c6b83e1a6cc1eac4e6cbe0169b57dad4ce7ecc628664c326e4e6a4ca7904"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/BobiDisplay.ttf",
      "target": "addons/skin.bobbi.cinema/fonts/BobiDisplay.ttf",
      "bytes": 6786084,
      "source_sha256": "6a2b0798f26d61427d73877fe026d4610cdc2e3df7d8baa3a213b29bef37a380",
      "sha256": "6a2b0798f26d61427d73877fe026d4610cdc2e3df7d8baa3a213b29bef37a380"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/HarmonyOS_SansSC_Bold.ttf",
      "target": "addons/skin.bobbi.cinema/fonts/HarmonyOS_SansSC_Bold.ttf",
      "bytes": 8379892,
      "source_sha256": "c215d8ab1cb6709fec2e063f8213e9af86d7587d345b56325e36b67d6b947d98",
      "sha256": "c215d8ab1cb6709fec2e063f8213e9af86d7587d345b56325e36b67d6b947d98"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/HarmonyOS_SansSC_Medium.ttf",
      "target": "addons/skin.bobbi.cinema/fonts/HarmonyOS_SansSC_Medium.ttf",
      "bytes": 8449140,
      "source_sha256": "7aa97804da2fc3802d116011b73ee25791303598718cc58dc49fedc9d63e5d2a",
      "sha256": "7aa97804da2fc3802d116011b73ee25791303598718cc58dc49fedc9d63e5d2a"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/HarmonyOS_SansSC_Regular.ttf",
      "target": "addons/skin.bobbi.cinema/fonts/HarmonyOS_SansSC_Regular.ttf",
      "bytes": 8483132,
      "source_sha256": "984cf609545acee8ef060780fb70fc3099b058c0553416331b6e863fdf7c26fa",
      "sha256": "984cf609545acee8ef060780fb70fc3099b058c0553416331b6e863fdf7c26fa"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/LICENCE-HarmonyOS-Sans.txt",
      "target": "addons/skin.bobbi.cinema/fonts/LICENCE-HarmonyOS-Sans.txt",
      "bytes": 3352,
      "source_sha256": "327e0147d4a3ca2d89e81abce45b210576b0f9fe2b29d900f64b58039f12a102",
      "sha256": "327e0147d4a3ca2d89e81abce45b210576b0f9fe2b29d900f64b58039f12a102"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/LICENCE-Heebo.txt",
      "target": "addons/skin.bobbi.cinema/fonts/LICENCE-Heebo.txt",
      "bytes": 4346,
      "source_sha256": "6d13374a47f3db882aad98f5788620d425e0b44a2d7221bb14fb185e8425ae2d",
      "sha256": "6d13374a47f3db882aad98f5788620d425e0b44a2d7221bb14fb185e8425ae2d"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/LICENCE-Mardoto.txt",
      "target": "addons/skin.bobbi.cinema/fonts/LICENCE-Mardoto.txt",
      "bytes": 12044,
      "source_sha256": "5bd41e468075ebba75da768007d24166f67d4e9626e173ce562ab4a95ac4a01c",
      "sha256": "5bd41e468075ebba75da768007d24166f67d4e9626e173ce562ab4a95ac4a01c"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/LICENCE-OFL.txt",
      "target": "addons/skin.bobbi.cinema/fonts/LICENCE-OFL.txt",
      "bytes": 4395,
      "source_sha256": "4bd805bb254c8b69c26addf1e100c745ec09e2737ec624b722bd509ea9ae240a",
      "sha256": "4bd805bb254c8b69c26addf1e100c745ec09e2737ec624b722bd509ea9ae240a"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/LICENCE-Roboto.txt",
      "target": "addons/skin.bobbi.cinema/fonts/LICENCE-Roboto.txt",
      "bytes": 12044,
      "source_sha256": "5bd41e468075ebba75da768007d24166f67d4e9626e173ce562ab4a95ac4a01c",
      "sha256": "5bd41e468075ebba75da768007d24166f67d4e9626e173ce562ab4a95ac4a01c"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/MiSans-Medium.ttf",
      "target": "addons/skin.bobbi.cinema/fonts/MiSans-Medium.ttf",
      "bytes": 8103840,
      "source_sha256": "b03e98374e971594b0b7a9706d0704241f76e1b88556cdda79c5039ef8a638d1",
      "sha256": "b03e98374e971594b0b7a9706d0704241f76e1b88556cdda79c5039ef8a638d1"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/MiSans-Regular.ttf",
      "target": "addons/skin.bobbi.cinema/fonts/MiSans-Regular.ttf",
      "bytes": 8122324,
      "source_sha256": "9c120f0a849bc0aa5048daae2a3c0f6eecd828b5b33fce682a9622833f5feea6",
      "sha256": "9c120f0a849bc0aa5048daae2a3c0f6eecd828b5b33fce682a9622833f5feea6"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/MiSans-Semibold.ttf",
      "target": "addons/skin.bobbi.cinema/fonts/MiSans-Semibold.ttf",
      "bytes": 8034980,
      "source_sha256": "77c23f31ae124867778344970155a0c8d34a89897dedaab81aeee82ff00a4ce6",
      "sha256": "77c23f31ae124867778344970155a0c8d34a89897dedaab81aeee82ff00a4ce6"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/NetflixSans-Bold.ttf",
      "target": "addons/skin.bobbi.cinema/fonts/NetflixSans-Bold.ttf",
      "bytes": 168116,
      "source_sha256": "e0edbbb8e0d12a575c29e76e4dfd7eb35f74858367c085453b8b09bfaf419177",
      "sha256": "e0edbbb8e0d12a575c29e76e4dfd7eb35f74858367c085453b8b09bfaf419177"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/NetflixSans-Regular.ttf",
      "target": "addons/skin.bobbi.cinema/fonts/NetflixSans-Regular.ttf",
      "bytes": 166844,
      "source_sha256": "77e036bc57d9b1fe761aad658947997c21fc785e532ef1a245dc436f9e39800a",
      "sha256": "77e036bc57d9b1fe761aad658947997c21fc785e532ef1a245dc436f9e39800a"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/README.txt",
      "target": "addons/skin.bobbi.cinema/fonts/README.txt",
      "bytes": 797,
      "source_sha256": "05eb4a16bfca6f591e8ed38be8441c57dee0c80dd9e5aa06df81ac16e2102cd3",
      "sha256": "05eb4a16bfca6f591e8ed38be8441c57dee0c80dd9e5aa06df81ac16e2102cd3"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/Roboto-Bold.ttf",
      "target": "addons/skin.bobbi.cinema/fonts/Roboto-Bold.ttf",
      "bytes": 254084,
      "source_sha256": "84c9d92e4300b4e836c9dacd61d8142f5691e3c18da6c8a37a5e02edcb240a10",
      "sha256": "84c9d92e4300b4e836c9dacd61d8142f5691e3c18da6c8a37a5e02edcb240a10"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/Roboto-Regular.ttf",
      "target": "addons/skin.bobbi.cinema/fonts/Roboto-Regular.ttf",
      "bytes": 254272,
      "source_sha256": "9e13e7dbe6f28b2730883209e6b98a7142f27fcc8d3e4bb1645c41cc978d853a",
      "sha256": "9e13e7dbe6f28b2730883209e6b98a7142f27fcc8d3e4bb1645c41cc978d853a"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/RobotoCJKSC-Regular.ttf",
      "target": "addons/skin.bobbi.cinema/fonts/RobotoCJKSC-Regular.ttf",
      "bytes": 13079512,
      "source_sha256": "f7ecc62f5657e8cff4375231322e9e73643d0e1f12e4b2dbacb0bc68cacbb66d",
      "sha256": "f7ecc62f5657e8cff4375231322e9e73643d0e1f12e4b2dbacb0bc68cacbb66d"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/fonts/fzltdhk.ttf",
      "target": "addons/skin.bobbi.cinema/fonts/fzltdhk.ttf",
      "bytes": 7675536,
      "source_sha256": "d11040a832f0256f7ac8b7dbbe5e9f75d41bd0735d6c1d3a5f0b0829381ce306",
      "sha256": "d11040a832f0256f7ac8b7dbbe5e9f75d41bd0735d6c1d3a5f0b0829381ce306"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/1080p/Font.xml",
      "target": "addons/skin.bobbi.cinema/1080p/Font.xml",
      "bytes": 6725,
      "source_sha256": "a1a9ce4e85ff55cfedfec7c4e7c8bed58adc8cbbee9dfba1684890ab106d231d",
      "sha256": "a1a9ce4e85ff55cfedfec7c4e7c8bed58adc8cbbee9dfba1684890ab106d231d"
    },
    {
      "source": "ui-redesign/source/addons/skin.am6b.cinema/1080p/Includes_Views.xml",
      "target": "addons/skin.bobbi.cinema/1080p/Includes_Views.xml",
      "bytes": 16310,
      "source_sha256": "49dc5e288fe5cd90583073915df2fcebcecc49207a6c2a704f8e94791b7617cb",
      "sha256": "a0e40874213c01847f2414a38c8d0948dc0723b690d1094930594522ea9e4726"
    }
  ],
  "rights": "Original notices retained; no blanket third-party redistribution grant asserted.",
  "excluded": "Legacy auth, remote execution, firmware, updater and library-clearing scripts remain excluded."
}

````
<!-- /provenance-file -->
