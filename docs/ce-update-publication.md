# CoreELEC 更新发布

源码推送不会改变电视的稳定更新。要发布安装包，先冻结同一提交的两次可复现构建、依赖许可、受信签名整包、安装入口和轨道。稳定包与预览包的签名轨道不能互换。

## 本轮候选的构建与升级前置检查

本轮修复了会阻断真实升级的两个问题：已发布的 `script.bobbi.start 0.2.123` 不能承载不同的 bootstrap 字节；也不能要求所有 CE2184 用户从官方 Kodi Omega 仓库升级到其中不存在的 HTTP 库版本。当前版本预检覆盖派生的启动器内容，运行库策略见 `release/http-runtime-policy.json`。保留已有 Kodi 依赖，新的离线安装仍使用捆绑版本，不覆盖上游目录或篡改 Kodi 的来源数据库。

以下命令从仓库根目录执行，使用 Python 3.11+。`OUT` 是仓库外一个新的绝对路径；已有文件保留，重试使用新子目录。`CANDIDATE` 必须是已测试、已提交的完整 SHA。实际的 `NEXT_TAG`、`NEXT_SEQUENCE`、`TRACK` 必须在重新读取 GitHub/GitCode 两条轨道、Release 列表与目标设备高水位后确定，不能直接沿用示例号或把“最新源码”当新发行号。

### 1. 固定来源、版本和运行库证据

先抓取远端分支与标签，并把当前线上 `current.json` 和对应 Release 元数据保存到 `OUT`。源码预检使用该新抓取的 feed；CI 的检查使用仓库内的已发布 feed 和对应 Git 标签，只负责防止重复使用已发布组件版本，不能代替发版时的在线复核。

```sh
git fetch origin --tags
python tools/check_release_versions.py \
  --published-feed "$OUT/published-stable-current.json" \
  --published-commit "$PUBLISHED_COMMIT"
python tools/check_http_runtime_matrix.py --fetch-floor \
  --output "$OUT/http-runtime-matrix"
```

离线运行库复核可将 `--fetch-floor` 换为 `--floor-archives /absolute/path/to/pinned-zips`。脚本校验两个官方 ZIP 的精确长度和 SHA256，分别启动加载官方下限与捆绑版本的进程，保存真实 `__version__`、`__file__`、Python 版本、JUnit 和日志。任一失败、跳过、加载错库或零测试均失败。这个矩阵证明被覆盖的生产消费者契约，**不宣称旧 HTTP 库所有裸 API 与新版安全等价**。

完成源码修改、组件版本调整、Home 生成检查后再刷新清单并提交。不要把刷新清单当作修复本身。最终提交上的离线全量测试、运行库矩阵、native 语义门、前端、Workers/D1 及设备验收分别保存结果，不将历史收据改写为新提交通过。

实体 Yatse 的输入来源已经由用户确认。验收不要求手机 ADB、手机 UI 自动化或截图证明；逐项执行真实操作并记录盒端的 UI/播放/事件/数据结果即可。单个场景没有执行时保留 `NOT_RUN`，输入来源确认不等于全部场景自动通过。

### 2. 冻结后进行可复现构建

```sh
git status --porcelain
git rev-parse HEAD
python tools/generate_home_rails.py --check
python tools/vendor_licenses.py
python tools/build_release.py --source-check --output "$OUT/source-first"
python tools/build_release.py --source-check --output "$OUT/source-second"
python tools/check_repository.py "$OUT/source-first" "$OUT/source-second"
```

第一个命令必须输出为空；第二个命令必须等于 `CANDIDATE`。源码检查产物有 `installable=false`，不签名、不安装。实际构建使用维护者已有的本地 TMDb 项目应用配置；缺配置时用 `tools/configure_tmdb_project.py` 的本机导入入口，不把账号或个人播放凭据混入构建。

```sh
python tools/build_release.py --output "$OUT/components"
python tools/build_release.py --output "$OUT/components-second"
python tools/check_repository.py "$OUT/components" "$OUT/components-second"
python tools/sign_private_bundle.py \
  --key "$SIGNING_KEY" --components "$OUT/components" \
  --profile coreelec --sequence "$NEXT_SEQUENCE" --track "$TRACK" \
  --output "$OUT/assets/BobbiTV-${NEXT_TAG_UPPER}.bobbi-update.zip"
python tools/build_ce_entry.py \
  --bundle "$OUT/assets/BobbiTV-${NEXT_TAG_UPPER}.bobbi-update.zip" \
  --output "$OUT/assets/script.bobbi.start-${ENTRY_VERSION}-${NEXT_TAG_UPPER}.zip"
python tools/audit_ce_entry.py \
  "$OUT/assets/script.bobbi.start-${ENTRY_VERSION}-${NEXT_TAG_UPPER}.zip" \
  --report "$OUT/entry-audit.json"
python tools/build_online_repository.py \
  --bundle "$OUT/assets/BobbiTV-${NEXT_TAG_UPPER}.bobbi-update.zip" \
  --output "$OUT/github-feed" --tag "$NEXT_TAG" --source github --track "$TRACK"
```

正式完整入口附件采用 `script.bobbi.start-<版本>-CE<编号>.zip`，以满足 GitCode Release 重定向允许的文件名；在线仓库内部生成的小启动器仍保持工具规定的版本化路径，不能连同它一起改名。

`NEXT_TAG_UPPER` 对应已确定标签的大写形式，例如 `ceNNNN -> CENNNN`；`ENTRY_VERSION` 来自本次已提交的启动器 addon.xml。使用已有、与 `release_trust.json` 匹配的签名密钥，不创建替代信任密钥。双镜像发布再用 `--source gitcode` 构建 `"$OUT/gitcode-feed"`。包的轨道、签名 channel、Release prerelease 标志必须一致；预览包不能仅修改 feed 文本升为稳定包。

在同一候选上先完成目标 CE 的已有版本升级、干净安装、失败保留、恢复上一版本、恢复后再次升级；记录安装前后程序身份、实际加载的 HTTP 库路径/版本及用户数据哨兵。回滚保留防回放高水位，普通更新的复升必须使用更高 sequence 重新签名；恢复已保存候选只能记录为恢复，不等同普通新更新。可在同一已冻结源码上规划试装 A < 复升 B < 正式发行 S，验证后受校验恢复已发布程序并保留 B 水位，再从真实更新入口安装 S；不得清水位或把 A/B 的报告冒充 S 的安装结果。上一轮 AM6B+ 的 5 冷 5 暖和 CE2184 恢复属于历史本地报告证据，不能代替新补丁的设备验收。

## 发布与线上回读

进入已授权的发布阶段后，上传两个经审核的固定附件，再进行下面的 feed 提升。发布说明应明确本轮平台范围与未验收能力。不要使用已退役的 `tools/package_public.py`，也不要用 `--source-check` 产物代替完整包。

1. 将不可变附件（普通安装入口 `script.bobbi.start-*.zip` 与完整更新包 `BobbiTV-CE*.bobbi-update.zip`，不混放单组件压缩包以免干扰用户选择）上传到 GitHub `2223M1/bobbi-tv`（双镜像发布时同步上传 GitCode `BobbiZerri/bobbi-tv-updates`）的同名 `ceNNNN` Release；不复制签名密钥或账号数据，保存指向确切提交的 GitHub Release 元数据。
2. 用 `tools/ce_release_gate.py prepare` 生成收据。默认必须准备 GitHub、GitCode 双镜像；只在 GitHub 发布时显式使用 `--mirror-policy github-only`，不传 `--gitcode-feed`。此模式不宣称 GitCode 已同步。
3. 对所选镜像运行 `promote`，目标是各自仓库的 `repository/stable` 或 `repository/preview`。它先回读发布附件，拒绝较新或同序号不同内容的活动指针，再在本地准备新目录。保留旧版 ZIP，不在此步骤改动根目录旧入口。稳定版另运行 `python tools/ce_legacy_pointer.py --root repository --receipt <收据> --proof <promote报告>`，在同一次 GitHub 快进提交中同步旧客户端的六字段清单；预览不触碰它。
4. 按普通快进提交推送更改。若远端分支已前进，重新取回并检查，不要强推。随后用同一收据运行 `verify`，核对线上完整目录及附件；只有这份回读通过才能称为已上线。

CE2182 及更早的客户端经原有 GitHub 通道获取迁移版；不要把 GitHub 清单的下载地址改为 GitCode。新版优先 GitCode，无需登录或自建服务器。用户端在两个镜像间选可用的新版本；提醒不下载或安装，安装和重启仍要确认。

GitCode 的 `raw` 是源码预览服务，不能当任意 ZIP 的下载站。CE 读取其稳定 JSON、从 Release 下载完整包或组件；Kodi 自带的仓库插件继续从 GitHub 取索引和小启动器。验收分别核对真实 HTTP 入口和 GitCode 主分支中存档的目录文件，不把 Git 对象校验算作 HTTP 下载成功。

GitHub 单镜像发布可按以下命令准备与回读；双镜像发布删除 `--mirror-policy github-only`，增加 `--gitcode-feed "$OUT/gitcode-feed"`，并对两个本地仓库分别提升及正常推送。`github-release.json` 必须是上传后真实回读的 GitHub Release JSON，`target_commitish` 是确切 `CANDIDATE`，附件集合与冻结文件一致。

```sh
python tools/ce_release_gate.py prepare \
  --bundle "$OUT/assets/BobbiTV-${NEXT_TAG_UPPER}.bobbi-update.zip" \
  --entry "$OUT/assets/script.bobbi.start-${ENTRY_VERSION}-${NEXT_TAG_UPPER}.zip" \
  --github-feed "$OUT/github-feed" --mirror-policy github-only \
  --github-release "$OUT/github-release.json" --track "$TRACK" \
  --source-first "$OUT/source-first" --source-second "$OUT/source-second" \
  --output "$OUT/publication-receipt.json"
python tools/ce_release_gate.py promote \
  --receipt "$OUT/publication-receipt.json" --channel github \
  --target "repository/$TRACK" --report "$OUT/github-before-feed.json"
```

稳定轨道还需同步六字段旧入口；预览轨道不执行该命令：

```sh
python tools/ce_legacy_pointer.py --root repository \
  --receipt "$OUT/publication-receipt.json" --proof "$OUT/github-before-feed.json"
```

审查此时的 feed/launcher 差异，提交并快进推送；若远端已前进，重新合并和复核，不强推。线上回读与真实客户端检查是两个独立步骤：

```sh
python tools/ce_release_gate.py verify \
  --receipt "$OUT/publication-receipt.json" --channel github \
  --report "$OUT/github-live-readback.json"
```

回读通过后，在仍运行上一已发布版本的 CE 上使用真实 Yatse 打开「检查波比 TV 更新」，确认能发现正确轨道和序号、下载已验证附件、完成安装与重启，最后核对程序版本向量和数据哨兵。仅源码推送、仅 Release 上传、仅 feed 提升、仅 HTTP 回读均不能单独记为“用户升级成功”。保留旧版附件与恢复点，不修改已发布 ZIP 的内容。
