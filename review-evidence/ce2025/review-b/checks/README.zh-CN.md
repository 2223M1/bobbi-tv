# 独立检查：执行方法与预期结果

## 1. 准备输入

需要完整源码checkout，固定HEAD为 c4e0baca6acefa58f031979bff71e7cd1028efdf；不要用只有patch的目录运行完整构建。维护环境可使用项目CI的Python3.11及requirements-test.txt。项目产品兼容性不等于测试依赖可装在所有旧Python上。

下列为Linux/macOS shell示例。全部目录改为本机绝对路径；输出选择新的独立目录。Windows用户使用等价环境变量与路径分隔符，或在Linux维护环境运行真实loopback三控。

~~~bash
REVIEW_REPO=/absolute/bobbi-tv-fixed-checkout
REVIEW_PACKAGE=/absolute/BobbiTV-CE2024-Independent-Review-20261021
REVIEW_OUTPUT=/absolute/ce2024-independent-replay
REVIEW_ENTRY="$REVIEW_REPO/review-packages/ce2024/script.bobbi.start-0.2.15-ce2024.zip"
mkdir -p "$REVIEW_OUTPUT"
export PYTHONDONTWRITEBYTECODE=1

git -C "$REVIEW_REPO" rev-parse HEAD
git -C "$REVIEW_REPO" rev-parse 'HEAD^{tree}'
python -m pip install -r "$REVIEW_REPO/requirements-test.txt"
~~~

身份应为 head c4e0baca6acefa58f031979bff71e7cd1028efdf / tree bb4256d63465fefb9c5820f3ce1ec9cca33ff546。固定身份验证器只用于此基线；修复分支的行为回归可把REVIEW_REPO改为新源码，但必须另存其真实身份和结果。

## 2. 原始实际入口核验

~~~bash
python "$REVIEW_PACKAGE/checks/verify_actual_entry.py" \
  --repo "$REVIEW_REPO" \
  --fixed-source "$REVIEW_PACKAGE/evidence/source/FIXED-TREE.json" \
  --entry "$REVIEW_ENTRY" \
  --output "$REVIEW_OUTPUT/actual-entry.json"
~~~

预期exit=0。校验真实入口SHA/Gitblob、内嵌payload、产品验签、独立RSA验签、全22组件、1349个Git文件、唯一应用配置输入和17个外层成员。配置内容不输出。不安装设备，不需要生产私钥。

生产新候选须使用新身份输入和相应验证记录，不能把此脚本固定pin移除后还声称复核了CE2024旧包。

## 3. F02/F03旧反例

~~~bash
python "$REVIEW_PACKAGE/checks/reproduce_native_list_focus.py" --repo "$REVIEW_REPO" --output "$REVIEW_OUTPUT/f02.json"
python "$REVIEW_PACKAGE/checks/reproduce_native_monitor.py" --repo "$REVIEW_REPO" --output "$REVIEW_OUTPUT/f03.json"
~~~

预期各5/5、exit=0。F02是原脚本；F03只适配新timeout形参及保持相同语义边界的EOF注入次序，原行为断言不变。

## 4. R24-01字幕身份

~~~bash
python "$REVIEW_PACKAGE/checks/reproduce_subtitle_scope.py" \
  --repo "$REVIEW_REPO" --output "$REVIEW_OUTPUT/subtitle-scope.json"
~~~

原CE2024预期：20项、14通过、6错误放行、exit=1。错误项是其他季自然标签和特别篇/OVA文件。provider网络I/O为确定性夹具，实际rank/正文检查/publish执行；不连接网络或电视。

修复后应在不修改原20项期望的前提下exit=0。可另传旧b20e972 checkout重放基线；旧版会拒绝6个错误文件，但也不支持3个新版正控，不能把旧版能力差异算当前回归。

## 5. R24-02实际交付依赖与真实HTTP三控

先从真实入口提取五个原版Python依赖，脚本固定校验入口及payload哈希，只写新输出目录：

~~~bash
REVIEW_DEPS="$REVIEW_OUTPUT/entry-dependencies"
python "$REVIEW_PACKAGE/checks/extract_delivery_dependencies.py" \
  --entry "$REVIEW_ENTRY" --out "$REVIEW_DEPS"

BOBBI_REVIEW_ROOT="$REVIEW_REPO" \
BOBBI_REVIEW_OUTPUT="$REVIEW_OUTPUT/lifecycle" \
PYTHONPATH="$REVIEW_DEPS/script.module.requests/lib:$REVIEW_DEPS/script.module.urllib3/lib:$REVIEW_DEPS/script.module.certifi/lib:$REVIEW_DEPS/script.module.idna/lib:$REVIEW_DEPS/script.module.chardet/lib:$PYTHONPATH" \
python -m pytest -q -p no:cacheprovider "$REVIEW_PACKAGE/checks/test_progressive_shutdown.py" \
  --junitxml="$REVIEW_OUTPUT/lifecycle.xml"
~~~

原CE2024预期：2 passed / 1 failed，约34秒；requests2.31.0/urllib3 2.2.3。真实loopback端口、真实15秒join，无外网。运行环境必须允许本机socket；EPERM须报告环境阻断，不得记产品失败。

三个场景：fast progressive正控、slow progressive反例、slow block阴性对照。所有测试线程最后清理。修复后保留相同不变量、相同生产等待预算，不以调整夹具来绕过反例。

## 6. R24-03真实Git仓库归属

~~~bash
BOBBI_REVIEW_ROOT="$REVIEW_REPO" \
BOBBI_REVIEW_OUTPUT="$REVIEW_OUTPUT/provenance" \
python -m pytest -q -p no:cacheprovider "$REVIEW_PACKAGE/checks/test_closure_gate_identity.py" \
  --junitxml="$REVIEW_OUTPUT/provenance.xml"
~~~

原CE2024预期：1 passed / 1 failed。脚本只建立临时本地仓库，调用真实closure_gate.run；没有远端仓库操作。修复后两项都应通过，另外补执行前后身份变化等正式门禁测试。

## 7. R24-04多解码通道历史行为探针

~~~bash
python "$REVIEW_PACKAGE/checks/decoder-reproduce.py" \
  --repo "$REVIEW_REPO" \
  --fixed-source "$REVIEW_PACKAGE/evidence/source/FIXED-TREE.json" \
  --receipt "$REVIEW_PACKAGE/evidence/decoder/grand-budapest-observe.json" \
  --output "$REVIEW_OUTPUT/decoder-probe.json"
~~~

预期exit=0表示成功确认历史信息丢失：channel0单块8/8/8、原顺序全文0/0/0、反序8/8/8。**这不是修复通过测试。** 它载入完整实际sample/request_status函数，只替换设备I/O；不会执行远端工具顶层或连接设备。

可选--old-repo和--old-fixed-source必须成对提供，才能重新证明旧版AST/行为相同。包内decoder-verified.json已保存本轮实际完成的旧版比较；省略旧版不会声称另做过比较。

修复后的正式回归应断言各通道保留、输出顺序无关、通道变化可识别，不能继续要求错误的0值。末尾累计8不归属于此前某个采样窗，不据此倒改历史回执。

## 8. 现有产品窄集

三套测试采用项目要求的进程隔离。以下只是本轮执行过的重点集合，修复影响其他路径时合理补齐；不把全部集合的数字与CI、重复复跑相加。

~~~bash
cd "$REVIEW_REPO"
python -m pytest -q tests/test_ce2023_delivery.py
python -m pytest -q tests/test_ce2024_gui_fence.py tests/test_ce2020_cooperative_stop.py tests/test_ce2015_shutdown.py tests/test_ce2012_recovery_ui.py
python -m pytest -q tests/test_ce2023_subtitle_episodes.py tests/private_baseline/test_ce2023_subtitle_scope.py tests/private_baseline/test_ce2015_list_binding.py tests/private_baseline/test_ce2015_monitor.py tests/private_baseline/test_ce2020_native_stop.py tests/test_share_stream_observations.py
~~~

本轮分别35、32、59个唯一用例通过。59项的初次3项socket环境阻断及后续13项重跑（其中10重复）原XML保留，不误计成69项。

## 9. 与后续新版本的关系

本包不含生产入口字节、私钥、应用配置明文或完整源码。执行者从已授权仓库取得固定入口及源码即可复现。只有实际包验证和解码历史探针对固定tree身份有硬约束；行为反例通过显式源码路径可用于修复分支。

请将新输出留在新的证据目录，记录新commit/tree，保留原失败。图像/主观字幕同步、视频平面、安装/回退、整集续播仍须独立设备验收，不能由本机脚本推出。

