# 语音输入法（script.voice.inputmethod）

CoreELEC / Kodi 的语音输入插件。按遥控器语音键说话，识别出的文字直接写入当前
Kodi 输入框。

本插件从 `script.voice.assistant`（AI 语音助手）中抽取语音识别部分独立而成，
去掉了意图解析、工具调用、对话窗口、语音播报等助手功能，只保留「录音 → 识别 →
写入输入框」这一条链路。

## 工作原理

```
语音键 (keymap global)
   └─ RunScript(script.voice.inputmethod,--voice)
        ├─ 记录当前焦点窗口 ID（判断是不是输入框）
        ├─ 录音        resources/lib/audio.py      ALSA 直采 16kHz 单声道 S16_LE
        │                                          SpeechGate 做音量门槛 + 静音断句
        ├─ 流式识别    resources/lib/streaming.py  采集线程 / 解码线程分离
        │   ├─ ncnn    ncnn_worker.py             独立子进程跑 sherpa-ncnn（本地离线）
        │   └─ doubao  doubao_worker.py            独立子进程 + WebSocket（联网）
        └─ 写入输入框  resources/lib/injection.py  JSON-RPC Input.SendText
```

两个引擎都走同一个子进程管道协议（`pcm_worker.py`）：父进程写「4 字节大端长度 +
PCM」，子进程回一行一个 JSON（`ready` / `result` / `error`）。

## 为什么本地识别必须放在独立进程里

豆包本来就要隔离网络和 TLS 依赖；本地 ncnn 则是**必须**隔离，否则会拖垮 Kodi：

* Kodi 在加载任何插件之前就已经链接了新版 ABI 的 `libstdc++.so.6`。
* 内置的 aarch64 `sherpa-ncnn` 是 pre-C++11 `std::string` ABI 的构建，两者会定义
  同名弱模板符号（`std::regex` 的内部类就是其中之一）。直接 `dlopen` 进 Kodi，
  我们的调用会被绑到 Kodi 那份新 ABI 的实现上，两边对象布局不一致，堆被写坏。
* 症状是整个 Kodi 进程死掉：`SIGABRT` 落在
  `ZipformerModel::InitEncoderInputOutputIndexes()`；用 `RTLD_DEEPBIND` 把这一处挡住
  之后，崩溃只是推迟到随后的 Python 异常处理里（`SIGSEGV` 落在
  `_PyErr_ExceptionMatches`）。两种都算进 CoreELEC 的崩溃环保护，累计 5 次就把
  `/storage/.kodi` 改名成 `/storage/.kodi.FAILED` 并进入安全模式。

放到独立进程后，最坏情况只是子进程死掉，父进程报一句「本地识别进程提前结束。」，
Kodi 不受影响。子进程的 stderr 会写到
`userdata/addon_data/script.voice.inputmethod/ncnn-worker.log`，原生库崩溃前的最后
输出就在那里。

（32 位 ARM 用户态下两个 ABI 并不冲突，但两条路径保持一致，避免只有一边被验证。）


## 关于 Input.SendText 的实测结论

Kodi 只向插件开放一个文字通道：JSON-RPC `Input.SendText`。在本机 CoreELEC 21.3
上实测（窗口 10103「虚拟键盘」）：

| 调用 | 行为 |
|---|---|
| `Input.SendText(text, done=false)` | **整体替换**输入框内容，输入框保持打开 |
| `Input.SendText(text, done=true)` | 整体替换内容，并关闭输入框（等同按确定） |

Kodi 没有「读取输入框当前内容」或「在光标处插入」的接口，所以**每次语音输入都会
覆盖输入框里原有的文字**。插件为此提供两种模式（设置 → 文字输出 → 识别出文字后）：

* `直接写入输入框并提交`（默认）：写入后立即等同按下键盘上的确定。搜索框这类场景
  说完就能直接出结果。
* `只写进虚拟键盘，按确定才生效`：文字只出现在**虚拟键盘的输入行**里，搜索框本身
  仍然是空的，要再按一次虚拟键盘的确定才会落进去。想先改一遍再提交时用这个。

## 语音按键绑定

设置 → 工具 → **绑定语音按键**，按一下遥控器上想用的键。

绑定要写两个地方，这一点很容易踩坑：

* `<global>` 段：平时生效。
* `<VirtualKeyboard>` 段：**虚拟键盘打开时只认这一段**。Kodi 键位映射的规则是
  `<global>` 只在「当前窗口段没有定义该按键」时兜底，而屏幕键盘对应的窗口段就叫
  `VirtualKeyboard`。只写 `<global>` 的话，一弹出键盘语音键就失效——恰恰是最需要
  语音输入的时候。

插件同时会接管 Kodi 在 `<VirtualKeyboard>` 段里指向内置 `VoiceRecognizer` 的三个按键
（`browser_search`、`menu`、`play_pause`）。Kodi 本身不带语音识别实现，这三个键在
虚拟键盘里原本只打一条 `OnVoiceRecognition: No voice recognition implementation
available.` 的警告，等于按了没反应。本插件就是那个「语音识别实现」，所以直接接管。

绑定后会写 `<文件名>.voice-input.bak` 备份，并自动重载 keymap，无需重启。**重新绑定会先
把上一次绑定的按键删掉**，不会在文件里越攒越多（无关按键和别的窗口段一律不动）。

如果绑定日志里出现 `code=65534`，说明按下的这个键是 Kodi 的**未知键兜底码**
（见下面「遥控器语音键与 hwdb」一节）：能用，但遥控器上任何 Kodi 不认识的键都会一起
触发语音输入。更稳的做法是用 hwdb 把它映射成 `search`，插件本来就接管了
`browser_search`，映射完不需要再手动绑定。

## 遥控器语音键与 hwdb

很多 2.4G / 蓝牙遥控器的语音键走的是 **HID Consumer 页的 0x0CF（Voice Command）**。

较新的内核（CoreELEC 21/22 用的 Linux 6.x）其实认识这个 usage，会把它翻成
`KEY_VOICECOMMAND`（582）——所以这个键**是有按键事件的**，并不是「内核都传不上来」。
问题出在 Kodi：它的键盘表（`XBMC_keytable.cpp`）里没有 `KEY_VOICECOMMAND` 这一项，
于是把它归进**未知键**。

### Kodi 的未知键兜底码 65534（0xFFFE）

`CKeyboardStat` 对认不出来的符号只给 `XBMCK_UNKNOWN`（调试日志里是 `sym: 0x00`），
最终按键码固定为 **65534**。实测：内核报 `KEY_VOICECOMMAND`(582)、`KEY_MICMUTE`(584)、
`KEY_UNKNOWN`(240)、`KEY_FN`(464)，Kodi 一律给 65534；而 `KEY_SPACE`、`KEY_ESC`
这类它认识的键则各走各的绑定，不会误触发。

**所以「把语音键绑到 65534」确实能用，但代价是遥控器上任何一个 Kodi 不认识的键都会
一起触发语音输入。** 遥控器按键少时不容易察觉，插上 USB 键盘就容易误触发。

### 推荐：在 hwdb 里映射成 Kodi 认识的具名键

最合适的是 `search`（HID Consumer 0x221 AC Search → Linux `KEY_SEARCH` → Kodi
`sym: 0xaa` = `XBMCK_BROWSER_SEARCH`，是键盘表里的正经具名键）：

```
evdev:input:b0003v1915p1025*
 KEYBOARD_KEY_c00cf=search
```

（`c00cf` = usage page 0x0C、usage 0x00CF；`7002a` 这种 5 位十六进制是 page 0x07 键盘页。）

插件本来就接管了 `browser_search`（`<global>` 和 `<VirtualKeyboard>` 两段都写），
所以改成 `search` 之后**不需要再手动绑定**。

### 不要映射成 `tab`

Kodi 的屏幕键盘对话框会自己吃掉 TAB —— `GUIDialogKeyboardGeneric::OnAction()` 里：

```cpp
if (b == XBMCVK_TAB)
{
  // Toggle left/right key mode
  m_isKeyboardNavigationMode = !m_isKeyboardNavigationMode;
  ...
  handled = true;      // 动作到此为止，不再往下派发
}
```

`handled = true` 表示这个动作不再往下走，`<VirtualKeyboard>` 段里给 TAB 写的绑定
**永远轮不到**。症状就是「主界面按语音键好用，一弹出虚拟键盘就失灵」——而这恰恰是
最需要语音输入的时候。

### 让改动生效

```sh
systemd-hwdb update
udevadm trigger --action=add --subsystem-match=input
```

⚠️ **hwdb 会把目录下所有 `.hwdb` 文件都编译进去**，包括名字里带「副本」的备份文件。
同一个 usage 出现两条互相矛盾的规则时后加载的那条赢；只在主文件里删掉一行、却留着
副本文件，改动就是不生效。排查时先 `ls -la /storage/.config/hwdb.d/` 看看有没有多余副本。

### 验证映射是否生效

不用按遥控器，直接问内核。先确认设备节点——consumer 接口通常不是键盘接口那个，
用 `cat /proc/bus/input/devices` 看 `Name="… 2.4G USB …"` 的几条记录
（本机 Consumer Control = event5、System Control = event6）：

```sh
python3 -c "
import fcntl, struct, os
fd = os.open('/dev/input/event5', os.O_RDONLY)
buf = struct.pack('=BBHI32s', 0, 4, 0, 0, (0x0C00CF).to_bytes(4,'little') + b'\0'*28)
print(struct.unpack('=BBHI32s', fcntl.ioctl(fd, 0x80284504, buf))[3])
"
```

| 返回值 | 含义 |
|---|---|
| `582` | `KEY_VOICECOMMAND`（没有 hwdb 条目时内核的默认值）→ Kodi 当成未知键 |
| `217` | `KEY_SEARCH` → Kodi `browser_search`（推荐） |
| `15` | `KEY_TAB` → **虚拟键盘里会被 Kodi 吃掉** |
| `EINVAL` | 没生效 |

有些遥控器的语音键直接走 **Consumer 0x221（AC Search）**，内核默认就映射成
`KEY_SEARCH`，对应 Kodi 的 `browser_search`。Kodi 在 `<global>` 里把它写成空动作、在
`<VirtualKeyboard>` 里指向内置 `VoiceRecognizer`，两条路都是按了没反应。

插件因此**两个键都接管**：绑定键 + `browser_search`（两个段都写），
另外在 `<VirtualKeyboard>` 段里再接管 `menu` / `play_pause`。

## 自检

设置 → 工具：

* **识别自检**：用内置的 AISHELL 中文测试音频跑一遍识别引擎，弹窗显示识别结果。
  期望结果：`甚至出现交易几乎停滞的情况。`
* **输入自检**：往当前输入框写入 `语音输入测试 ABC123`，用来单独验证注入通道。
  需要先打开一个输入框再点。
* **全链路自检**：把内置测试音频当作麦克风输入，走完整的「采集 → 语音门槛 →
  识别 → 写入输入框」链路。同样需要先打开一个输入框。这条不需要真人说话，
  是验证语音键链路最直接的方式。

## 内置资源

一个安装包同时带两套用户态的原生库，运行时按**解释器指针宽度**选目录（`ctypes`
直接报 4 位还是 8 位）。不能用 `uname`：64 位内核既能跑 aarch64 用户态，也能跑
32 位 ARM 用户态。

* `resources/native/linux_armv7l/ncnn/`：sherpa-ncnn C API（CoreELEC 21 ng 等 32 位用户态）
* `resources/native/linux_aarch64/ncnn/`：sherpa-ncnn C API（CoreELEC 22 no 等 64 位用户态）
* `resources/native/<架构>/cmcc/`：移动高清遥控的 Siren 解码封装
* `resources/native/<架构>/nanosic/`：腾讯极光遥控的 WNVC-320 解码器
* `resources/native/<架构>/r22/`：华为 R22 遥控的 mSBC 解码封装
* `resources/models/`：两个中文流式模型（与架构无关）
  * `sherpa-ncnn-streaming-zipformer-small-bilingual-zh-en-2023-02-16`（均衡，中英）
  * `sherpa-ncnn-streaming-zipformer-zh-14M-2023-02-23`（快速，中文）
* `resources/vendor/websocket/`：豆包识别子进程使用的 WebSocket 客户端

扫码配置相关（纯 Python，无额外依赖）：

* `resources/lib/qrcodegen.py`：二维码编码器（Project Nayuki，MIT）
* `resources/licenses/qrcodegen-build.json`：来源与校验值
* `resources/lib/configuration/`：`server.py`（HTTP + 配对 + 设置读写）、
  `ui.py`（生成二维码 PNG、显示对话框）；网页用的表单描述来自 `settings.py` 的
  `web_schema()`，每个设置项在那里声明 `section`（网页分 tab 用）、`visible`
  （条件显示）、`minimum`/`maximum`，所以新增设置项时网页会自动跟着出现，不用改 HTML
* `resources/web/index.html`：配置网页（单文件，内联 CSS/JS，无外部资源）
* `resources/skins/Default/1080i/ConfigureVoiceInput.xml`：电视上显示二维码的对话框

二维码 PNG 是自己拼的（`zlib` + `struct` 手写 PNG 分块），不引入 Pillow，省掉一个
几十 MB 的原生依赖；生成在插件 profile 目录下、权限 `0600`，对话框关闭时删除。

蓝牙遥控的两个解码器两套用户态都有，文件名带所链接的系统 FFmpeg 版本，同一目录下
只会存在一个：

| 用户态 | CMCC | Nanosic | R22 | 链接的系统库 |
| --- | --- | --- | --- | --- |
| `linux_armv7l` | `libcmcc-siren-ffmpeg62.so` | `libnanosic-wnvc-avutil60.so` | `libr22-msbc-ffmpeg62.so` | `libavcodec.so.62` / `libavutil.so.60`（FFmpeg 8） |
| `linux_aarch64` | `libcmcc-siren-ffmpeg63.so` | `libnanosic-wnvc-avutil61.so` | `libr22-msbc-ffmpeg63.so` | `libavcodec.so.63` / `libavutil.so.61`（FFmpeg 9） |

32 位版本不能拿到 aarch64 用户态上跑：ELF32 目标无法载入 ELF64 进程，而且 CoreELEC
的 aarch64 用户态既没有 32 位加载器（`/lib/ld-linux-armhf.so.3`）也没有 32 位 libc。
aarch64 版本是用**同一份源码**针对 aarch64 重新编译的，两个 `.so` 本身不打包任何
FFmpeg 代码，只调用系统自带的库；若系统 FFmpeg 缺 Siren 解码器或主版本对不上，
加载时会报出具体的 `cannot open shared object file` 而不是静默走兜底。编译脚本见
仓库的 `tools/build_decoders.py`，构建记录见 `cmcc-build*.json` / `nanosic-build*.json` /
`r22-build*.json`。

模型来自 HuggingFace `csukuangfj/*`，来源与校验值见 `resources/licenses/ncnn-models.json`；
两套 sherpa-ncnn 原生库的来源与校验值见 `resources/licenses/ncnn-build.json` 和
`ncnn-build-aarch64.json`。

## 扫码配置（手机网页改设置）

设置 → 工具 → **扫码配置（手机打开）**，电视上弹出一个二维码。手机扫码即可在浏览器里
改全部设置、填豆包 API Key，不用在电视遥控器上一个个敲字。

也可以直接跑：

```
RunScript(script.voice.inputmethod,--configure)
```

### 为什么不是一个固定的网页地址

插件的 `service.py` 常驻监听一个 HTTP 端口，但**地址每次都不同，而且带一次性令牌**。
网页地址形如：

```
http://192.168.5.171:8768/#PxmXm14dkbuS3rG8IZV2x-QbPnoY7BECoxX-lGRQIDY
```

令牌放在 `#` 之后的 **fragment** 里。浏览器不会把 fragment 发给服务器，所以它不会
出现在盒子的访问日志、也不会通过 `Referer` 泄给第三方；但它足以证明「打开这个页面的人
就是看到了电视屏幕的人」。

* **端口**：从 8767 起依次尝试 8767–8771，被占用就往后让。盒子上装了别的常驻服务
  （例如 `service.ysp.live` 占着 8767）时插件会自动落到下一个，不需要手动改。
* **有效期**：入口 30 分钟后自动失效，或者插件重启即失效。电视上关掉二维码窗口**不会**
  立刻断开已经连上的手机——页面会提示「已连接」，直到过期。
* **每次重新打开二维码都会换一个新令牌**。手机 `sessionStorage` 里存的旧令牌随之作废，
  避免上一次的入口被留着长期使用。

### 电视上那个六位数字是什么

二维码下方显示的**配置码**（六位数字）。它只出现在电视上，网页接口的
`/api/state` 里**不含**这个值（有测试断言守着）。

它的用处是：在**电脑**上手动输入网址时，浏览器拿不到 fragment 里的令牌，此时需要输入
电视上的配置码来完成配对。手机扫码则是自动连上的，不用手输。

每个 IP 最多试 5 次，超过后即使输对也会被拒，必须重新打开电视上的二维码。

### 安全边界

| 检查 | 作用 |
| --- | --- |
| 令牌在 fragment | 不进服务器日志、不进 `Referer` |
| 30 分钟过期 + 重新打开即轮换 | 泄露的地址活不过一次会话 |
| 只接受私有 / 回环地址且同源的请求 | 外部网页无法跨站调用接口 |
| 配置码每 IP 限 5 次 | 防止在局域网内穷举 |
| 录音进行中拒绝保存 | 避免边录边改参数导致状态错乱 |

### 一个已知限制

Kodi 的插件设置窗口**打开时**，`setSetting()` 会被静默丢弃（不报错、也不生效）。所以
网页保存时会写完再读回来核对，不一致就提示「请先关闭 Kodi 插件设置窗口，再保存网页设置。」
先把电视上的设置窗口关掉就好。

## 豆包联网识别（可选）

1. 准备一个只含 API Key 的文本文件（或含 `api_key` 字段的 JSON）。
2. 设置 → 语音识别 → 语音转文字 = 豆包流式语音识别。
3. 在「豆包语音 apikey 文件」里选中该文件。

用扫码配置的话，第 3 步可以直接在手机网页上把 Key 粘进去，插件会把它写到
`userdata/addon_data/script.voice.inputmethod/doubao-api-key.txt`（权限 `0600`），
文件选择框也会自动指向它。网页上不显示已保存的 Key，留空保存不会覆盖原有的 Key。

## 蓝牙遥控支持

USB 麦克风 / 2.4G 遥控由脚本按需直接打开，不需要常驻服务。Ugoos UR01/UR02、
腾讯极光、移动高清、Homatics（B21/B25）这四类蓝牙遥控的麦克风走 GATT/HID，
需要 `service.py` 常驻持有并解码音频，脚本再通过 `userdata/addon_data/.../*.sock` 取流。
华为 R22 遥控走 BLE HID（按住说话，松开自动结束），同样由 `service.py` 常驻读取
hidraw 并解码。

## 调试入口

```
RunScript(script.voice.inputmethod,--settings)        打开设置
RunScript(script.voice.inputmethod,--configure)       扫码配置（电视上显示二维码）
RunScript(script.voice.inputmethod,--bind-voice-key)  绑定按键
RunScript(script.voice.inputmethod,--test-asr)        识别自检
RunScript(script.voice.inputmethod,--test-inject)     注入自检
RunScript(script.voice.inputmethod,--dictate-sample)  全链路自检
RunScript(script.voice.inputmethod,--voice)           执行一次语音输入
```

日志关键字：`[voice-input]`、`[voice-service]`。

排查「按了语音键没反应」时看这几条：

```
[voice-input] invoked with [...]            脚本有没有被跑起来（没有就是键位没绑上）
[voice-input] another invocation ...       上一次还在跑，这次被锁挡掉了
[voice-input] dictate start: target=...    录音前记下的焦点窗口，keyboard=True 才是输入框
[voice-input] deliver: target=... focused=...   交付时的焦点，和上面不一致就会丢
[voice-input] injected N chars ...         写入成功
[voice-input] no input dialog, ...         没找到输入框，退化成弹窗提示
```

绑定日志里的 `bind dialog saw action id=... code=...`：

```
code=65534                                  Kodi 未知键兜底码，会连别的键一起触发，建议改用 hwdb 映射
```

按了键却完全没有 `[voice-input] invoked`，且主界面能用、一弹虚拟键盘就失灵 —— 那是
TAB 被屏幕键盘吃掉了，见上面「不要映射成 `tab`」。

### 报「豆包识别超时」

先看 `userdata/addon_data/script.voice.inputmethod/last_session.json`：

```
audio_seconds    录到了多少秒音频
queued_seconds   排队送去识别的秒数
decoded_seconds  真正送进识别服务的秒数
peak_rms         录音峰值
```

`decoded_seconds` 远小于 `audio_seconds`（例如录了 3.3 秒却只有 0.1 秒）说明卡在
**传输/应答**上，和网络、Key、麦克风都无关。豆包服务**不是每包回一个 ACK**，而是
攒够音频能产出新的中间结果时才回一个，实测每两包回一个、恒定滞后两包；因此不能
按「一问一答」去等每一帧的应答，`DoubaoRecognizer` 已按这个节奏单独实现了
`accept()`。另外最终文字只在**关闭包**发出后才有，`finish()` 必须先发关闭包再等结果。

`peak_rms` 接近 0 才是麦克风没声音；正常说话通常在几千到一万以上。

如果日志里完全没有 `[voice-input] invoked`，但出现了
`OnVoiceRecognition: No voice recognition implementation available.`，说明按键被
Kodi 内置的语音识别动作抢走了，见上面「语音按键绑定」一节。

脱离 Kodi 单独验证识别引擎（用盒子的系统 python3）：

```sh
cd /storage/.kodi/addons/script.voice.inputmethod
python3 asr-selftest.py ncnn balanced           # 走独立进程，和 Kodi 内的路径一致
python3 asr-selftest.py ncnn balanced --direct  # 在本进程直接跑引擎，用来区分原生库问题
python3 asr-selftest.py ncnn fast               # 换「快速」模型
```

识别自检的结果同时会写进 Kodi 日志，方便在没有屏幕的盒子上确认：

```
[voice-input] asr self-test: engine=ncnn in 3.75s expected='甚至出现交易几乎停滞的情况。' actual='甚至出现交易几乎停滞的情况'
```
