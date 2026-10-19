# Juku 0.80 显式字幕引用：协议证据及波比接入

本目录是 2026-10-19 的**静态研究证据**。`.c` 为 Ghidra 重建伪代码，
不是作者原始 Go 源码；`.asm` 为对应指令。没有启动第三方 daemon、运行群文件、
登录第三方账号或以此声称盒子实播已通过。

## 固定样本

| 项目 | ARM64 | AMD64 |
| --- | --- | --- |
| 官方包 | `plugin.video.juku-0.80-linux-arm64.zip` | `plugin.video.juku-0.80-linux-x64.zip` |
| 包 SHA-256 | `850414fb4829512b44086245e1889f4e9bb9ae44b9f42b3f6d7834c75e2950a0` | `0a384785f3cb9182513b0ea9f387675438217136df0ca751f6011c45ddeea9ca` |
| ELF 文件 | `daemon-linux-arm64` | `daemon-linux-amd64` |
| ELF SHA-256 | `e21cec4ba1f0411022a2d22061b1d27ac80d439606529ddc9cabec3060ca118b` | `fc7ba96b40f4da9d33c02b7c67f8617d26b0982166df515e429d94c97cba1433` |
| `ExtractSubFidsFromUrl` | `0x55a1c0` | `0x9e58e0` |
| `resolve115Subtitles` | `0x540c00` | `0x9c45a0` |
| 正则地址 / 长度 | `0xa1eaa4` / 51 字节 | `0xf475cf` / 51 字节 |
| 分隔符地址 / 长度 | `0xc0a5f0` / 1 字节 | `0x11331d8` / 1 字节 |

来源为用户提供的 `https://kodi.jukuku.xyz/zips/plugin.video.juku/` 官方包。
不是旧 0.20 ARM32 样本；未使用旧脚本中固定的旧地址作推断。

## 已恢复协议

两个架构传给 `regexp.MustCompile` 的 51 字节完全相同：

```text
(?i)[#?&/](?:sub_fid|sub_id|subtitle_id)=([^&#\s]+)
```

函数执行顺序在两个架构一致：

1. 对整个输入字符串执行 `FindAllStringSubmatch(..., -1)`。
2. 对第一个捕获组调用 `net/url.unescape(..., 2)`，即 `PathUnescape` 的
   `encodePathSegment` 模式；`+` **不**转为空格。
3. 百分号转义错误时保留原捕获串，而不是使用部分解码结果。
4. 以 1 字节 `,` 分割，然后 `strings.TrimSpace`、排除空值、保序去重。

证据：`arm64/0055a1c0.c`、`amd64/009e58e0.c` 及同名指令文件。
本目录 `.bin` 是按调用处长度读取的确切字节；未使用相邻 Go rodata 的
NUL 截断字符串拼接结果猜测参数名。

Go / RE2 的 `\s` 为 ASCII `[\t\n\f\r ]`；Python 即使开 `re.ASCII`
仍包含垂直制表符，适配代码显式转换该字符类。URL 的控制字符另由分享校验拒绝。
从 URL 读出的数字为字符串，保留前导零、不二次解码。波比额外限制为
**1–32 位 ASCII 数字、最多 16 个、输入最多 8192 字符**，不是声称上游也有这些限制。

例如：

```text
https://115.com/s/sabcdef?password=abcd#sub_fid=101%2C102&subtitle_id=102,103
→ ["101", "102", "103"]
```

只从已验证的 115 分享 `link.url` 读取这些确证键；不猜测其他 JSON 字段，
不接受个人直链。视频 key 不受字幕参数变化影响；同文件合并时保留去重后的
引用，SQLite 快照和 selected tuple 均保存此字段。

## 父目录外引用的依据和实现

`resolve115Subtitles` 先遍历传入字幕引用、去重，并调用
`get115WindowsShareDownurl`，失败再调用 `get115ShareDownurl`，随后才处理
父目录候选。见 `arm64/00540c00.c` 的第一段循环及
`amd64/009c45a0.c:177`、`:183`。这里没有要求显式字幕 FID 必须先在视频
父目录列表中找到。旧报告“参数键尚未恢复”由本次确切证据补全。

波比没有移植上游 daemon、Windows 认证或第二套账号。新增
`bobbi_catalog.api.Client.resolve_reference` 仅复用已有正式接口：

```text
GET https://proapi.115.com/os_linux/2.0/share/downurl
    share_code + receive_code + file_id + dl=1 + app_ver=36.2.28
```

响应必须满足 `fid == 引用 FID`，`fn` 为无路径/控制字符的有界文本字幕文件名，
`fs` 为正数且最多 2 MiB，`url` 在既有官方 CDN 范围。文件名/大小来自正式
分享响应，随后还要经作品/年份/季集/剪辑版本冲突检查及下载字节数核对；
它们不是目录预先证明的元数据。原有视频 `Client.resolve` 的
FID/名称/大小全等校验未被放宽。

`share_subtitles.fetch_candidate` 现在先解析最多 3 个显式引用；不需要
视频 parent，跨 parent 也不递归。候选可用则不再扫描目录；全部失败且有预算
时，才扫描当前父目录。总共最多下载 3 个文本文件，每个最多 2 MiB。
两条路径共用原 30 秒预算内的 10 秒子 deadline，不追加云任务、不读另一视频。
父目录分页仍受 100 项/页、1000 项总数限制，截断有状态。

发布前检查账号 epoch 和取消状态。明确错年份/季集、forced/commentary、
图片字幕、非法 CDN、短读均不发布；允许 generic 显式字幕名称，但不允许
与当前视频声明矛盾。质量按实际双语正文优先，不把文件名里的“双语”当证明。
允许时间轴偏移，仍只标记 `candidate`，由现有原生播放 owner 决定应用；
未宣称已验证同步。

## 可复现检查

使用 `tools/ExportJukuSubtitleProtocol.java`，Ghidra 12.1.4 / JDK 21，
对已导入的程序运行 `-readOnly -noanalysis`：

```text
analyzeHeadless <project-dir> juku080-arm64 -process daemon-linux-arm64
  -readOnly -noanalysis -scriptPath <repo>/tools
  -postScript ExportJukuSubtitleProtocol.java <output>/arm64 00a1eaa4:51 00c0a5f0:1

analyzeHeadless <project-dir> juku080 -process daemon-linux-amd64
  -readOnly -noanalysis -scriptPath <repo>/tools
  -postScript ExportJukuSubtitleProtocol.java <output>/amd64 00f475cf:51 011331d8:1
```

本地 Python 门禁：

```text
python -X utf8 -B -m pytest -q -o addopts= tests/test_share_subtitles.py
  tests/test_share_subtitle_references.py tests/test_juku_subtitle_protocol.py
  tests/test_juku_api_contract.py tests/test_juku_remediation.py
```

结果：**168 passed**（含后补的 Kodi `Cryptodome` 优先及 `Crypto` fallback 用例）。覆盖确切字面量、URL 多键/编码/异常/有界性、双路
row/SQLite 透传、官方请求 shape、响应字段和 CDN 校验、无 parent/跨 parent、
失败降级、候选与下载上限、年份/季集/剪辑冲突、字幕正文优先、短读、账号切换、
超时及真实 localhost 滴流 HTTP 的 deadline/取消。所有 HTTP 均为 mock/本机
fixture；不等于真实分享仍有效或设备实播通过。

Metadata 读取现已改为 `read1`、分块前后 deadline/取消守卫并更新当前 socket
剩余超时，持续滴流不能重置总读取预算；同时验证有界 Content-Length。
已知边界：系统 DNS / HTTPS 建连仍受 urllib 与 OS 能力限制，并非可强制
杀止的独立进程；不作 DNS 硬中断承诺。上层始终拒绝过期结果，正文已有独立
deadline I/O。
