# 对增量选源焦点竞态的独立交叉核查

根代理提出的疑点：Python `ControlList.addItems` 异步重新绑定完整列表，随后同步读旧焦点导致跳过恢复，GUI 队列后来处理绑定时回到首行。此次核查专门尝试查找 DelayedCallGuard、GuiLock、WindowXML 或 GUI 队列提供的同步屏障；没有发现足以反驳的保证。

## 官方 Kodi 21.3-Omega 的调用语义

1. `Control.cpp:1243–1275`：addItems 为所有已保留对象构造 `GUI_MSG_LABEL_BIND`，param1=0，`SendThreadMessage` 入队。
2. `Control.cpp:1313–1329`：getSelectedPosition 在 DelayedCallGuard/GuiLock 内直接调用 pGUIControl->OnMessage(GUI_MSG_ITEM_SELECTED)，读取当前控件状态。它不从待处理的绑定消息读取结果。
3. `interfaces/python/LanguageHook.cpp:43–52`：DelayedCallOpen/Close 仅释放/重新取得 Python GIL；并不处理 GUI 队列。
4. `interfaces/legacy/AddonUtils.cpp:21–39`：GuiLock 仅调用 LockFrameMoveGuard/UnlockFrameMoveGuard。
5. `application/Application.cpp:1795–1807`：该 guard 取得/释放 m_frameMoveGuard 和 graphics context 锁，没有 dispatch/flush。
6. `guilib/GUIWindowManager.cpp:1530–1578`：SendThreadMessage 仅复制消息入队；DispatchThreadMessages 必须在主线程按队列顺序执行。
7. `interfaces/legacy/Window.cpp:313–319`：XML 的 list/wraplist/fixedlist/panel 均包装成同一个 ControlList，没有为 WindowXML 使用另一个同步的 addItems 实现。

上述新核对的七份源码已按 Git blob SHA 校验，文件与来源见 `kodi-ui-crosscheck/PROVENANCE.json`；Control.cpp 与 GUIBaseContainer.cpp 为根代理已固定的同一版本源码。

## 一个具体、合法的调度

`CApplication::Process` 在3214行先 dispatch GUI thread messages，随后在3225行临时释放 frame guard，以处理脚本调用。此时可以发生：

- Python 在本轮 dispatch 之后把新增列表绑定入队。
- Python 取得刚释放的 frame guard，同步读取原先的非零选中位置。
- 产品判断“已经在保留位置”，没有发出 selectItem。
- 主线程随后处理已排队的 LABEL_BIND，容器 Reset/UpdateLayout(true)/SelectItem(0)。

该次序不要求任何 API 违反已声明语义。释放 GIL 可能给 GUI 主线程机会，但不是必须完成此消息的屏障。因此不能因代码用了 GuiLock 就排除此调度。

## 报告与测试应如何限定

它是合法竞态，不意味着每次追加都必然跳首行，也不是已经在电视上实测出某个发生概率。实际 SourceSelect 反例应使用明确建模的 Kodi 入队/排队后读取/主线程处理语义，并保留同步处理和首行焦点的正控。

本PR现有设备测例只停留首行焦点；绑定后回到0仍是原位置，故 `selected_key_retained=true` 和 `focus_commands=0` 并不能排除此场景。70次采样只覆盖首卡静态ROI，无法补上非首行焦点行为证据。

修复验收应观察队列处理完成后的选中source_key，覆盖追加、删除前方行与BT→云端精确替代，并覆盖用户在消息入队前后主动移焦。不要用一次立即读取代替已完成的GUI更新。仅统计Python reset()/selectItem()次数不足以证明原生容器未重绑。

## 来源

- [Control.cpp](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/legacy/Control.cpp#L1243-L1329)
- [GUIBaseContainer.cpp](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/guilib/GUIBaseContainer.cpp#L484-L492)
- [Python LanguageHook.cpp](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/python/LanguageHook.cpp#L43-L52)
- [AddonUtils.cpp](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/legacy/AddonUtils.cpp#L21-L39)
- [Application.cpp locks](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/application/Application.cpp#L1795-L1807)
- [Application.cpp message/script order](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/application/Application.cpp#L3211-L3228)
- [GUIWindowManager.cpp](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/guilib/GUIWindowManager.cpp#L1530-L1578)
- [Window.cpp](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/legacy/Window.cpp#L313-L319)
