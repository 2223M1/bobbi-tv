# CE2042 自然 BT 接力 UNSUPPORTED：原生 schema 构建漏项

范围：独立只读源码、冻结原生构建物、已保存实机回执和维护树 Ninja dependency 查询。
只在外部结果目录编写测试/报告；未改产品或构建实现，未操作设备、重发 capture、
执行 STOP/CONT 或运行候选二进制。修复由 root 指派的实现者负责。

## 实际失败与定位

`ce2042-heavenly-raw2/kodi.log:679` 起，同请求
`404628222c014400a772c13066c6681d`：

- 07:44:16.486：sequence 16，VERIFY_READY。
- 07:44:16.722：sequence 18，CAPTURE_REQUEST，距 ready 233 ms。
- 07:44:16.778：sequence 19，CAPTURE_REPLY，state=UNSUPPORTED。
- 同时 sequence 20 CAPTURE_REJECTED；07:44:17.930 sequence 21 RECOVERY_REJECTED。

`bobbi_core/transport_handoff.py` 的 UNSUPPORTED 唯一分支是在通过文件/账号/owner
前置校验、构造 capture grant 之后，`authority.native.control(handoff_capture)`
抛 ValueError；该分支清空 continuation，不发 Stop。`KodiNative.rpc` 将 JSON-RPC
-32700/-32600/-32601/-32602 合并为这个 ValueError。其他协议错误进入 RuntimeError，
未知结果保留为 pending；因此本日志不能归因为权限、片源身份或原生 capsule 的
手动音轨/字幕/延时执行拒绝。仅凭该异常本来无法区分四个协议错误码，下面独立取证
证明实际二进制的 schema 不具备这个入口。

## 同一制品中的 actor 与接口描述不一致

冻结 run：`D:/AM6B-Project/ce2038-native-original-audio-20261022/run-1792612141766198431`。
独立重算 `candidate.bin` SHA256：
`8bb2a99e2154432a4403ac55a81e3c253d7ab74f0e15369b85085f1a8bf4fd14`。

| 证据层 | BobiControl 参数 | action 枚举 |
| --- | --- | --- |
| 冻结 methods.json 和生成 ServiceDescription.h | 12 项，包含 5 个 handoff 参数 | stop/pause/resume/handoff_capture/handoff_stop |
| 8bb2 二进制内唯一完整 BobiControl JSON | 旧 7 项 | stop/pause/resume |
| ce2042-runtime-contract2.json 实机 introspect | 同旧 7 项 | 同旧 3 项 |

缺失的 5 项为 request_id、expected_subtitle_intent、expected_audio_intent、
child_request_id、handoff_token。二进制检验按 NUL 分段提取以
`"Player.BobiControl": {` 开头的完整 JSON 并解析，不以裸 handoff 字符串存在冒充
接口支持。Actor 本身已有这些字符串，所以仅 strings/symbol 检查会漏掉本问题。

同一实机回执的 current 仍是原请求、原 native instance
`33d527cd-0df3-4b46-8686-3365790839d4`、AV_STARTED、audio_intent=2、subtitle_intent=3，
并报告 handoff_protocol=1。因此单看 actor capability=1 不能证明 RPC schema 可达。
后续 `ce2042-native-runtime-hash1.json` 只读确认实际运行映像 SHA 也是该 8bb2，
排除了本次“只审到不同路径二进制”的疑问。完整 binary method 提取为 184 项，
与冻结 methods.json 方法集合一致、无缺失/额外/重复，唯一内容差异就是 BobiControl。

## 确切构建漏项，不是已查 depfile 的 include 优先级

冻结 `JSONServiceDescription.cpp.o.d` 指向本 run 的
`candidate/generated/ServiceDescription.h`；该 TU 确实读取新头，不能归为它被
`-iquote` 旧文件抢先解析。

但实际 schema 注册在维护源 `xbmc/interfaces/json-rpc/JSONRPC.cpp`：第 14 行 include
ServiceDescription.h；第 104～107 行遍历 JSONRPC_SERVICE_METHODS 并调用
AddBuiltinMethod。维护源 SHA256：
`b94dae82ab3d5b2b0390be2359112f51f15df4a953d4fe8fa1145e99bc83e7bb`。

独立只读 `ninja -t deps` 查询得到该生成头恰好两个消费者：

- `build/interfaces/json-rpc/CMakeFiles/jsonrpc_interface.dir/JSONRPC.cpp.o`
- `build/interfaces/json-rpc/CMakeFiles/jsonrpc_interface.dir/JSONServiceDescription.cpp.o`

8bb2 的 build-result.recompiled_units 仅含第二个，不含 JSONRPC.cpp。
artifact-verification 还明确确认 JSONRPC.cpp.o 是保留旧对象，SHA256：
`bda05a83cefe51c195264c81d02a6203cd9f67ec6ca17d9ef85549f85e7f784e`。
旧 verifier 比较的是源 methods.json 的方法集合，并验证“未列为替换的成员不变”，
两者都不能发现注册 TU 本应重编却未列入清单。

## 可重复反例与后续独审门槛

外部 `test_independent_ce2042_native_schema.py` 保留冻结 8bb2，不改写旧制品。
`independent-ce2042-native-schema-before-v2.xml` 为 1 failed / 4 passed：唯一失败是
“实际二进制必须导出与冻结源完全相同的 BobiControl schema”，四项正控分别核对
实际运行 shape、生成头/depfile、新旧参数差和遗漏 TU/保留对象。
初版 v1 多一条 Windows 路径分隔符测试 harness 失败；已修复为 as_posix，原回执保留，
不把它当作产品缺陷。
追加全 184 方法和实际运行 hash 的正控后，v3 回执为 1 failed / 6 passed；唯一失败
仍是同一冻结制品缺陷，未修写 8bb2 历史证据。

继任候选独审需要冻结完整源及生成头，闭合枚举两个消费者，并验证每个消费者的对象
与依赖来源。Root 已批准最小对象继承方案：只重编/替换遗漏的 JSONRPC.cpp.o；
JSONServiceDescription.cpp.o 可复用已证实读取同内容生成头的 8bb2 对象，前提是新旧
生成头逐字节相同、其对象/源/原 depfile 证据完整，其余 8bb2 archive members 不变。
最终 binary 必须解析并精确比对完整 BobiControl，包括旧 stop/pause/resume；不能只比
源码、符号或裸 action 字符串。候选本地通过后仍需 root 实机 introspect、同源自然
BT→云 capture/stop/child/restored 回执与手动偏好恢复验收；本报告不是设备认证。

## 继任候选 ba0327 本地独审结果

冻结 run：
`D:/AM6B-Project/ce2042-native-jsonrpc-schema-20261022/builds/run-1792626905471062171`。

- candidate.bin SHA256：`ba03279546193a8a5e6299b257e1321833dbf5b7b3ecc087ba67ed7dd2eb1991`
- build-result.json SHA256：`30e1e3008b3a8fe86d7f2036039476c654237c9f5a93ced03418f0e327749074`
- artifact-verification.json SHA256：`db04c3a39dcdcd1e2732879ad71e235490cb86825a4fc6cdc013f8861ad172e0`

已完整读实现者外部 builder/verifier，未修改它们。独立外部测试
`test_independent_ce2042_native_successor.py` 不导入作者验证函数，直接解析 GNU ar
与最终 ELF 中的完整 JSON。回执 `independent-ce2042-native-successor-v1.xml`：6 passed。

独立确认：

- 继承的完整冻结源与 8bb2 全部逐项同 hash，仅增加已固定 SHA 的 JSONRPC.cpp。
- 四个 archive 的成员名/顺序一致，只有 jsonrpc_interface.a 内 JSONRPC.cpp.o 改变；
  其余全部成员逐字节不变，另外三个 archive 整文件也逐字节不变。
- 新 archive 的 JSONRPC.cpp.o 正是本次编译对象；JSONServiceDescription.cpp.o 正是
  8bb2 的已验证对象，原生原音/字幕/胶囊对象未替换。
- 两个生成头消费者闭合：新 JSONRPC depfile 指向新 run/generated；保留 JSONSD 的
  原 depfile 指向 8bb2/generated；两份头逐字节相同，未混入维护树旧生成头。
- 新 binary 的全部 184 个方法完整 JSON 等于冻结 methods.json，无缺失/额外/重复；
  相对 8bb2 唯一 method 内容变化为 BobiControl，12 参数、5 action，旧3 action保留。
- Link argv 除隔离 run 路径外与 8bb2 完全一致；替换前重链接精确复现 8bb2，最终
  unstripped 再 strip 精确复现新候选；构建、验证、二进制 SHA 相互一致。
- 独立只读 WSL 重算构建回执中的 278 项维护输入与 46 项前代冻结输入：均零 mismatch。

没有本地独审阻断。该结论仅覆盖冻结候选制品；不宣称已安装，也不宣称实机 capture、
终止旧实例、child AV/restored 或字幕/音轨/延时恢复通过。原 8bb2 失败和回执继续保留。
