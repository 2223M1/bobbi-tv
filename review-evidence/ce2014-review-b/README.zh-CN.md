# 波比TV PR #3 / CE2014 审查交付

审查日：2026-10-21。冻结：`c8de17ae9dabbe0f37753e1751b1d88107311316`，tree `cc12e00ccba0d7cb9a8b310306437e0e8ef84ae3`。增量对照为 PR #2 合并提交 `ee65742bfcbaf08831f70306faed11bd1f8d6cc6`。

## 结论

保留本轮通用 CE、恢复/标准播放、原生片尾、选源防闪和4:3修复。最终独立48个场景：42满足、6未满足、0执行错误。其中4项确认G01退出所有权仍不完整（P1）；另外2项是renderer局部条件用例G03（P3建议，不作为合并阻断）。满额焦点疑点G02接上真实SourceListSession后通过，已撤回。建议只集中收口G01，不回退整版、不引入机型限制。

本包是审查、反例、窄参考补丁和连续整改要求，不是已修好的波比TV安装包。没有操作设备、账号、VPS或远端写入。

## 阅读顺序

先看 `REVIEW.zh-CN.md`、`FINDINGS.json`，再看 `CLOSEOUT-PLAN.zh-CN.md`、`ACCEPTANCE.json`、`CODEX-ONE-SHOT.md`。`FOLLOW-UP-DISPOSITION.json` 区分已验证改进与遗留项。`SOURCE-PROVENANCE.json` 记录11份完整源码的Git blob与2份方法摘录的边界。

## 执行

解压到原仓库外。在包目录使用 Python 3.10+：

```powershell
python -I -B .\run_review.py --output ..\PR3-frozen-result
```

结果目录必须是包外的新目录。预期48项、42满足、6未满足，退出1。退出1表示正确行为仍未满足，不是“修复通过”。退出2表示完整性/执行问题。日志和每组原始JSON均保留。

测试新的候选（仅复制读取所列文件，不改仓库）：

```powershell
python -I -B .\run_review.py --candidate-repo "D:\实际候选工作树\bobbi-tv" --output ..\PR3-candidate-result
```

如果实现结构改变，边界夹具应对接实际新模块并公开diff，不能删除场景或改正确行为。此入口不是整仓测试、签名验包或实机认证。

## 实际证据

`evidence/independent-run1/` 是首次独立执行，包含后来排除的renderer-only疑点；不能用其UI初步结果代替最终结论。见evidence/REVIEW-CORRECTIONS.zh-CN.md。`evidence/final-run/` 是打包入口复跑，不重复累计覆盖。CI ZIP 为真正下载的 PR 集成测试工件，其SHA核对一致，JUnit合计2684通过、5跳过；不是本轮本机重跑全部测试。

`patches/0001-clear-retained-source-counts.diff` 只修G03，方法级测试通过；没有把G01冒充已修，G02已排除。未经真实仓库集成与回归，不直接部署。

继续遵守产品目标：通用CE，未知型号无警告无白名单，原画质/手动字幕意图/账号代际保留。其它设备未实测不是安装或内测门槛。Android/Windows不在本轮。
