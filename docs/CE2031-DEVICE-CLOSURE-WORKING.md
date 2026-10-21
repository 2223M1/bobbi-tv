# CE2031 实机收尾记录（未交付、未推送）

CE2030 `bdad0c8` 的 22 组件完整入口已在真实设备安装完成，sequence
`2026102030`，事务 `3b0327b592bc477bbd6bd2d9808389d7`。干净该提交阶段
3118 passed / 6 skipped / 1 strict xfailed。这些数目不是本次 CE2031 最终回归。
保留 CE2030 已签名产物，不覆盖或改名为新版本。

## 本次修复与证据

- 实机拼音第六个候选失败后，补齐 Ready / Code / Page 原子发布与点击条件；
  翻页也使用同一页守卫。独立复审 91 项通过。主代理实施、部署和实机操作，
  审查代理未修改源码。十个实际按钮 500–509 → 原生 400–409 全部选字成功：
  `ce2029-results-20261021/ce2031-keyboard/bobbi-keyboard-1792582487833429400`。
  最早第六轮失败和随后截图 pan-race 失败均保留；截图重试只接受明确的
  FRAMEBUFFER_MOVING，有界等待，不忽略内容或其他错误。
- 真实继续观看历史有 85 条原记录、31 条筛选结果，未修改用户记录。设备
  `07:43 PM` 被旧 RFC fallback 解析为 `07:43`，所以上午旧影片置顶。
  现为已知 12 小时历史格式作 locale 无关解析，午夜/中午/西语兼容和
  非法日期反例均覆盖。旧反例 5 failed / 10 passed 保存在
  `ce2031-history-before`；修后组合在 `ce2031-history-after`。
- library 实机验证位置字段、文件日期/大小、管理入口，并实际点击下一页
  进入第 201 个文件：`ce2031-library/bobbi-library-1792583138317296800`。
  这是本机临时片库，不冒充真实 SMB/NFS/WebDAV 验收。额外原生目录探针
  返回 InvalidParams，未据此认定 lastmodified 不支持；本机 metadata 实际
  来自本机扫描。仅移除了本轮临时 source 注册，没有改用户来源。
- 实际弹窗 smoke：账号假二维码、取消、自然结束选项、资料署名、增量选源
  七张卡片。5 次增量发布无 reset，选源和筛选保持；45 次静态卡片像素样本
  均一致。回执 `review-evidence/bobbi-ui-smoke-1792582620451991000`。
  使用合成候选证明 UI 行为，不算新作品搜索/播放验收。
- “我的”有历史时实际右转 9110、左回 9100；空列表时不再在后台加载对话框
  期间显示“没有内容”。空状态文案不再承诺直接 NAS 文件已经接入影院历史。

Claude 源 509 个允许导入范围文件独立重比与已导入快照一致，无新增 UI
需要复制；源工作树保持不动。CE2031 增量将走新完整签名载荷，而非只发布预览。

## 字幕结论与用户新目标

真实《降临》原 2160p PROPER Remux 流、同一双语 ASS SHA
`0496b805d0d6d301dcf1d31fb24ffffefbe316ac8e5d3094e34bd24512b7cd66`：
原字幕英文下缘余 2–3 px；mode5/offset3 余约 59 px；按用户“不要过高”
回到 offset1，94 秒同句截图实测英文 bbox `(429,1014,1491,1057)`，
1920×1080 GUI framebuffer 下缘余 **22 px**，两行完整。

用户最初目标为约 **10 px**。说明现有档位限制后，用户随后明确选择了
“使用现有最小档，约 21 像素”；本次约 **22 px** 实测符合这一最终选择，
不再新增原生细调。模式 5 最小档约 18.75 px 位移；无可靠半档。
独立源码审查发现的 styles=1/master=false
组合依赖两处总闸语义不一致，并有校准副作用，未采用。需要兼容原生细调
才能进一步接近 10 px，但用户已选择不做；未修改或替换 F9，不写成已经设为 10 px。

当前仍保留 mode5/offset1、原字体/样式/颜色；overrideass 和 overridefonts
保持 false。这是 GUI/subtitle 平面截图，不含 AMLogic 硬件视频，也不能排除
电视自身 overscan。双语字幕来自另一版本，布局通过不代表整片同步已验证。

## 仍未关闭

- 新作品《虫师》S01E01 block 和 progressive 的启动观测均失败；progressive
  原生 AV 提早约 4.475 秒，但缓存持续约 14.431 秒、解码计数停进约 10.469 秒。
  严格同文件/transport 关联已证明它边读边交付，不可再套用 block 整块零交付
  原因。已恢复 block 并保持 native SHA、账号和码流不变。需继续定位原生缓存
  转换/队列/读取/呈现链路，不能调低画质或放宽失败阈值。
- 《降临》启动也有 buffering；当前只关闭了双语布局证据缺口，不关闭其播放
  起播问题。旧 ODDTAXI 双模式、Eizouken、Perfect Days 等记录继续保留。
- CE2031 干净提交 `c216bb3e5684cbc6f41e4ee7907818b2e6b79239`、tree
  `e56473566c5912820958e3ec64471f23cb2e814d` 已完成 2170 + 789 + 177 =
  3136 passed、6 skipped、1 strict xfailed；22 组件双构建哈希一致。
  独立 UI 复审 106 passed，396 个皮肤库存文件完整匹配。
  已走实际入口完成 sequence2026102031，tx `983fc4fac73c4744a44cb6ac2c5ab470`，
  安装后1153个自有程序文件与完整签名包相符。入口SHA
  `31066db7cf76e0eab786b4180f0afb1d8320b6b8167216fdf763d5495fd7b427`。
  独立审查指出个人页测试工具的身份/进度/首项/未完成加载判据缺口，由主代理修正。
  安装后完整键盘十轮再次通过。
- 续播组合回归和起播缓冲仍待闭合。10 px 新增细调由用户明确选择不做。
  现在不声称所有日常观看问题已解决，
  因而不推送为最终完成版。CD2、挂载、Yatse、代理、固件/SYSTEM/eMMC 未改。

外部证据根：`D:/AM6B-Project/ce2029-results-20261021`。

## 个人页测试事故与恢复（必须随报告保留）

加强版测试工具中 `Window(10025).getControl(50)` 用临时 Window 取得借用控件，
下一句 `selectItem(0)` 在 Window 生命周期结束后调用。4份实际崩溃的 fault thread
调用地址均为 `0x00490700`；精确 F9 符号定位到 Python ControlList.selectItem
虚调用绑定。20:09:23 为 SIGBUS，其余三份 SIGSEGV。不是其他线程的图片读取
导致已证根因，也不是普通脚本“超时而退出”。原始 timeout/传输失败与 crashlog
已保留；原始日志在外部私有取证目录，不复制凭据或签名媒体URL进安装包。

CoreELEC 因频繁崩溃进入 SAFE，将原配置保存在 `.kodi.FAILED`。这是本轮新增
测试脚本引发的事故，不能把此前 3136 项通过说成已覆盖这个宿主借用对象风险。
扫描产品 addons/third_party 没有同样的临时 Window.getControl 链式调用；
测试工具改为正常 GUI 动作，但 **没有再运行**，CLI 与远端脚本均已显式停用
personal probe。不以未经复测的新工具方案冒充实机修复通过。

主代理按系统已检查的退出 SAFE 流程恢复，未编辑 boot.status 或手动删/换
原配置。新建安全模式配置约6.58MB/629文件，已先完整保留在：
`/storage/.local/share/bobbi-safe-recovery/1792585704374678400/temporary-safe-profile`。
CoreELEC 的正常恢复用原 `.kodi.FAILED` 替换了这份临时配置，临时配置可从备份找回。

恢复回执：`ce2031-safe-recovery/safe-recovery-1792585704374678400.json`，
boot.status=OK，sequence2031、观看数据库/程序记录哈希未变，原F9未变。
guisettings由Kodi正常启动保存，整文件哈希变化；只读复核皮肤仍为
skin.bobbi.cinema、mode5/offset1、原字体与样式覆盖关闭，未强行覆盖整份设置。
恢复后以正常导航截图实测“我的”首卡为降临、已看1%，排序修复生效：
`ce2031-recovered-personal/screenshot-20261021T123148Z-e6fc1410.png`。
较早 `122939` 截图是在隐藏列表尚未完成加载时的空态，保留但不作为首卡通过证据。
恢复后未再运行个人页危险探针，没有播放影片，仍不推送为整体完成版。
