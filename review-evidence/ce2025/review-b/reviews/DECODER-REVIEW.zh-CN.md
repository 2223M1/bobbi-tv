# 解码器通道计数独立复核

## 结论与优先级

**信息丢失确定存在，建议列 P2「多通道解码器诊断计数被最后一个通道覆盖」。这是上一轮已存在、本轮用实际回执确认的遗留缺陷，不是 CE2024 新引入的回归。**

当前 `tools/ce_trial_remote.py:298–300` 读取完整 `/sys/class/vdec/vdec_status`，随后把所有通道的同名计数写入一个字典。字典后写值覆盖前写值，输出既没有通道身份，也不保留被覆盖值。本轮实际保留文本的 channel 0 / `dvbldec` 有 `drop count = 8`、`fra err count = 8`、`hw err count = 8`，channel 1 / `dveldec` 对应值均为 0；实际解析函数处理全文后只留下后者的 0。

此问题影响后续诊断和验收证据的完整性，宜修复后再依赖结构化计数作“无解码错误”等结论。它不代表播放器本身新增了错误，也不证明错误数 8 来自后续 30 秒观察窗口，更不能据此认定启动卡顿根因。作者仍保留启动失败结论，不能描述成作者借这些 0 把启动失败关闭。

## 使用的真实材料与执行范围

- 当前固定 head：`c4e0baca6acefa58f031979bff71e7cd1028efdf`。
- 上一轮固定 head：`b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2`。
- 原始回执：`review-evidence/ce-new-work-grand_budapest-observe-1792551462588057300.json` 的 `result.decoder` 文本。
- 当前源码、旧源码和回执原始文件均校验了 Git blob，与各自固定 tree 对应项一致；详细散列在 `decoder-verified.json`。
- 通过 AST 载入实际完整 `sample()` 与 `request_status()` 函数，函数体未改写。仅将设备状态、JSON-RPC、系统文件读取替换成离线边界；没有执行远端脚本顶层操作，没有连接设备，也没有把自己重写的正则当作产品解析器。

## 最小对照结果

| 输入文本 | frame count | drop count | fra err count | hw err count |
|---|---:|---:|---:|---:|
| 原始 channel 0 单通道块，对照 | 1755 | 8 | 8 | 8 |
| 原始完整文本，channel 0 后接 channel 1 | 1755 | **0** | **0** | **0** |
| 相同两个原始通道块，仅反转排列顺序 | 1755 | **8** | **8** | **8** |

三个输入均调用当前实际 `sample()`。仅改变两个通道块的顺序就改变结果，证明它保留的是最后出现的通道，而不是与通道顺序无关的完整设备诊断。

相同三组输入调用旧版本实际 `sample()` 得到完全相同结果。当前计数字典 AST（299–300 行）与旧版 AST（294–295 行）完全一致；源码 diff 的行号差来自新增作品清单。因此不应把它列为 CE2024 新回归。

真实回执还有四个结构化 sample，frame count 分别为 1027、1269、1512、1755，三项错误/drop 数值均为 0。末尾原始 decoder 快照含 channel 0 的 8。**这些采样与末尾快照不是经证明的同一时刻，不应反向补写历史四个 sample 的计数，也不能计算本观察窗口新增错误为 8。** 本次直接证明的是：保留下来的真实多通道文本经当前解析器处理会丢失 channel 0 非零值。

## 建议修复与验收边界

按 `channel_id` 保存独立记录，同时保留设备名与原始计数。需要展示汇总时，明确汇总定义，并保留原始分通道值；不能简单相加双通道 frame count 后声称解码帧数。既有健康分析需要选取与当前播放对应的通道时，必须明确绑定依据；无法绑定时保留 unknown，不能默选最后一个通道。

观察窗增量只能比较同一通道、同一会话/计数周期的前后快照。计数器回退、通道变化或读取缺失应单独记账，不得当作 0 错误或把累计值归属给本窗口。保留旧证据并补充解释，不能据新解析器重写无法恢复的逐样本历史数据。

最少回归包括：单通道不变、多通道值都保留、通道排列顺序不影响按通道输出、重复通道/缺失字段处理，以及同通道增量与重置边界。修复诊断工具不需要改变画质、播放选择或底层解码策略。

## 复现产物

- `decoder-reproduce.py`：可重复执行的离线诊断探针，用于确认历史信息丢失行为。**它不是代码修复后的验收回归**；修复后的正式回归必须断言各通道计数保留、通道排列顺序无关，不能把本探针观察到的错误值作为长期期望。
- `decoder-verified.json`：实际来源散列、三个当前/旧版对照结果、AST 等同性和证据限制。

```sh
python decoder-reproduce.py \
  --repo /path/to/current-source \
  --fixed-source /path/to/current-fixed-source.json \
  --receipt /path/to/ce-new-work-grand_budapest-observe-1792551462588057300.json \
  --output /path/to/decoder-verified.json \
  --old-repo /path/to/previous-source \
  --old-fixed-source /path/to/previous-fixed-source.json
```

前四个参数是必需项，不依赖工作区目录命名。最后两个参数可一起省略，此时仅验证当前源码与原始回执，不输出“旧版已存在”的验证结论；提供旧版比较时必须同时给出 `--old-repo` 和 `--old-fixed-source`。

源码：[当前计数解析](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/tools/ce_trial_remote.py#L298-L300)、[旧版相同逻辑](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/ce_trial_remote.py#L293-L295)、[原始观察回执](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-evidence/ce-new-work-grand_budapest-observe-1792551462588057300.json)。
