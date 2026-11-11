# 原页材料更新后继 — 2026-10-21

当前最终冻结 v2 已通过：受影响默认 **1358 项**、本地浏览器 **217 项**；完整默认离线 **4450 passed / 2 skipped / 497 deselected，727.15 秒**。21 项原生桥接全部通过；778 项运行输入未变。旧 v1 失败、局部 RED、旧证据和安装版均保留。11 张受影响原票与地图已追加本轮 Notes，元数据与历史保全均经最终读回确认。App 未更新或启动，真实申请继续暂停。

目标：在既有邮件到人工 Submit 主线上，联系方式更正或完整人工源编辑后，保留同一 Flow、Worker、原页面、人工字段与其他附件，通过一次 Continue 更新实际受影响材料并续填。App 不更新或启动；真实申请继续暂停。既有票据仅在最终验证后追加 Notes，Status、Assignee、依赖与历史保留，不新增票。

## 起点与保全

起点是 [上一轮完整默认 4440 通过](../product-completion-2026-10-21/README.md)。本轮 [baseline](baseline.json)核验 770 项输入与上轮冻结 v4 完全相同，并保存精确源码恢复归档。[保全范围](preservation-before.json)登记 1067 份旧证据、93 份安装版文件、128 份票/地图文档。127 张票、24 张未关闭的 [原始票据记录](tracker-before.json)未变。

[24 票剩余接受地图](remaining-acceptance.md)区分当前源码、安装/真实接受与研究封存；[实现前不变量复核](review/design-invariants.md)和[UI独立审查](review/ui-editor-review.md)是只读判断，不是独立重跑结果。

## 当前公开回归

- 默认完整源编辑入口缺失：修复后保存同任务独立版本，原稿/PDF保留，未启动Worker。ui-editor-red-v2.log → ui-editor-green-v1.log；初次缺少夹具导入的 setup error 单独保留于 ui-editor-red.log。
- 保存回包丢失后版本门禁不能恢复：ui-unknown-save-red.log → ui-editor-green-v2.log。只读回读确切已保存文本，不重放 POST。
- 默认完整材料缺少现有 PDF 预览：ui-pdf-preview-red.log → ui-editor-green-v3.log。复用既有严格PDF读取与预览控件，不加材料批准。
- Pipeline独立转运行或状态不可读时仍可操作旧编辑区：ui-pipeline-edit-red.log → ui-editor-green-v4.log。状态恢复后保留待保存文字。
- 跨窗口源版本变化后永久禁用保存：ui-source-conflict-red-v2.log → ui-editor-green-v5.log。保留本地编辑，展示当前保存源，只有用户明确选择采用当前版本再继续保存；另一已存版本保留。初次 group 外版式变更被既有保护拒绝，原错误单列于 ui-source-conflict-red.log。

上述 UI 最后组合 6 项通过；真实原 Runner、原页面、阶段候选编辑与一次 Continue 的第7项组合仍待联调。后端 staged 保留旧 current 材料的公开 RED/GREEN 及后续事务原始日志见 implementation/。尚未执行本轮完整默认离线，不将当前局部绿色写成整体通过。

真实模型、真实编译排版质量、真实 ATS、安装版实际行为和人工 Submit 接受均未发生。所有新测试仅使用合成源、本地存储及隔离浏览器；不得据此关闭全部开放票。

## 后继公开界面与传输发现

新增两项只读状态组件回归验证：即使Pipeline暂停，服务报告材料制作中或结果未知仍不能编辑候选。该组件测试使用明确的readback替身，不充当真实后端事务证明。ui-pending-update-red.log → ui-editor-green-v6.log。

用户折叠源编辑区后，新的状态回读不得自动展开：ui-editor-collapse-red.log → ui-editor-green-v7.log。冻结前仍在联调同一任务连续两轮完整人工源编辑，不把10个旧绿色节点覆盖第11个后继断言。未保存当前任务源文时不能静默Continue使用旧稿；ui-unsaved-continue-red.log → ui-unsaved-continue-green.log（原Page两节点）。该限制只针对实际当前task，不锁住其他任务的查看和安全暂停。

真实原Page的候选源编辑先后暴露当前邮箱grounding和新源检查点问题，implementation/ui-source-save-v2.log保留失败；独立当前源版本修复后 implementation/ui-source-save-v3.log 两项通过。然后公开第二轮编辑分别暴露UI复用已完成候选和后端分组映射继承问题，ui-second-source-round-red.log、ui-editor-green-v8.log均保留；当前仍在处理，未声称整组合通过。

[传输回归](transport/README.md)保留Ashby旧同名attachment id错误背书新SHA的有效RED、core修复与GREEN。Workable使用同原Page的真实隔离Chromium与loopbackHTTP执行双版本presign/upload/download读回；测试夹具policy编码错误单独保留。该传输层结果不冒充完整Runner/真实ATS。

[默认控制调用图](default-control-callgraph.md)记录后继主控收敛前沿，未用rg命中宣称死代码或真实双重写入。README和ARCHITECTURE修正了已有持续收录/归档/正常恢复的陈旧描述；文档改前字节及哈希见 before-docs/ 和 documentation-before.json。本轮完整运行将额外绑定这两份文档。

## 冻结候选 v1

第二轮人工源编辑的分组映射问题已修复：当前输入未变化时直接导出已验证的不可变人工稿，不重新生成分组根。人工稿之后再更正联系方式时，只在新的独立版本规范化引擎 marker 注释，正文、固定教育实值和旧源字节保留。后端 `implementation/ui-second-source-v1.log`、`manual-contact-editor-v2.log` 与 `version-reuse-final-v1.log` 保留针对性 GREEN；root 的 `ui-editor-green-v9.log` 组合 **11 项通过（31.46 秒）**，包含原 Page 两轮编辑与未保存源 Continue 门禁。更早失败日志均保留，不被后继结果覆盖。

[frozen-candidate-inputs-v1.json](frozen-candidate-inputs-v1.json)记录 777 项当前输入；[精确本轮差异](candidate-delta-v1.patch)比较本轮开始时的源码恢复归档和独立文档备份，不将既有 dirty 工作误算为本轮新增。18 份变化文件中含 2 份文档、11 份生产/界面文件、5 份测试文件。完整 Ruff check、format check、JavaScript 语法与 git diff 空白检查均通过。集中受影响与完整离线结果仍以各 run JSON、原始日志和 XML 为准；此段不预写未完成的全套通过。

## 冻结后独立审查：两个待修 P2

v1 集中回归尚在运行时，独立源码审查发现两个现有局部绿色未覆盖的 provider 接续问题。v1 不作为最终候选，即使旧集合通过也须修复并重新冻结。

- Ashby A→B→A：旧 A 与新 A 的 SHA 相同，但上传 attempt 不同。refresh 遍历旧记录时按当前新附件校验旧 attempt，导致后继回读卡住。须只采用当前确切新附件 attempt 建立当前证据，全部旧记录保留。
- Workable 原 Runner：新上传 intent 建立后，旧远端附件的只读 GET 不符合现有 guard；adapter 层双版本测试不经过 Runner，不能证明此路径可用。须补同 Page、实际 Runner guard 的换版回归，并保持精确下载 URL/方法/原 owner 限制。

这两项是实际审查发现，不是对未知真实 ATS 行为的猜测。当前旧冻结运行完成前不改其正式输入；后继修复、RED/GREEN 与重新冻结分开记录。

v1 受影响默认结果：**1355 passed / 113 deselected，171.73 秒**；777 项运行输入未变。旧浏览器集合保留自然运行。尝试提前中断该集合的进程信号请求被自动审批拒绝，理由是未确认目标 PID；未继续发送信号或绕过审批，改为等待原运行自然结束。这不影响两项 P2 的后继修复授权。

v1 浏览器自然结束为 **210 passed / 1 failed / 1355 deselected，471.96 秒**，777 项输入未变。失败节点是 `tests/test_full_latex_http.py::test_complete_source_and_group_dispositions_are_readable_without_review_shortcut`：不具备 `group_session` 的旧完整源展示夹具仍出现 `flow-export-pdf` 控件。对照本轮起点归档确认该导出控件逻辑原已存在，本轮扩大浏览器选集才覆盖此旧断言。后端拒绝门未失效；root 以一条早退限制无分组会话时的导出显示，保留已绑定会话的导出及回执恢复逻辑。该节点与真实分组浏览器集合一并验证，不删旧断言。

## 修复并重新冻结 v2

两项 provider P2 均有有效公开 RED→GREEN：

- Ashby：`implementation/ashby-samehash-red.log`（2 failed / 1 passed）→ `ashby-samehash-green-v1.log`（7 passed / 2 deselected）。三代 A1/B2/A3 与其他附件历史全部保留；只用当前确切 attachment attempt 建立当前证据，缺失或错误当前 attempt 不能回退旧 A 记录。
- Workable：`implementation/workable-runner-red-v1.log`（1 failed）→ `workable-runner-green-v2.log`（6 passed / 37.07 秒）。真正的 canonical Pipeline、原 Worker/Page 与请求 guard 完成一次 Continue 换版；完整 intent 改变、暂停、未知人工提交、未知写结果及借只读 scope 发 POST 五项均被实际 guard 拒绝，未发生第二次上传或 Submit。
- 旧完整源无分组会话的导出显示：`affected-browser-v1.log` → `ui-group-session-green-v1.log`（4 passed / 2 deselected，11.97 秒），正常 group/reviewed-PDF 路径保留。

[最终候选 v2](frozen-candidate-inputs-v2.json)绑定 **778** 项输入，[本轮最终差异](candidate-delta-v2.patch)为 19 份文件（2 文档、11 生产/界面、6 测试）。[owner 16 项交接 SHA](implementation/frozen-owner-inputs-v2.json)逐项吻合。新增 Workable Runner 模块已加入受影响默认 57 文件和浏览器 69 文件选择。v2 完整 Ruff check、format check、JavaScript 语法和 diff 检查通过。当前集中运行采用新标签，旧 v1 原始失败与冻结记录保留。

v2 集中运行全部通过：[默认受影响](affected-v2.log) **1358 passed / 119 deselected，169.15 秒**；[本地浏览器](affected-browser-v2.log) **217 passed / 1358 deselected，516.02 秒**。两份 `*-run.json` 均记录 778 项输入无变化。最终 [限定只读复审](review/final-review-v2.md)确认两个 provider seam 和无会话 UI 门禁未发现仍可复现的 P2 及以上；该审查未独立重跑套件。完整默认离线采用 `full-offline-v1` 新标签单独运行，运行期间正式输入保持冻结，不放宽 Swift 60 秒编译门。

[后继精准材料只读计划](next-precise-material-plan.md)与[源码定位](precise-wait-frontier.md)保留下一工程前沿：精准岗第一次人工精调等待前完成全部已知必要附件。此处仅是计划和定位，没有实现、没有接受，不属于本轮绿色结论。

## 最终完整默认离线结果

[完整原始日志](full-offline-v1.log)、[XML](full-offline-v1.xml)、[命令与运行输入](full-offline-v1-run.json)记录 4450 通过、2 跳过、497 按默认标记排除；未使用 `-m` 覆盖默认完整离线选择。21 项原生桥接通过，保留原 Swift 60 秒编译策略，未以单独补测冒充本轮完整通过。两项跳过原因：

- `tests.test_pdf_reuse_full_entry_performance::test_full_http_entry_paired_preparation_to_viewable_pdf`：Explicit opt-in required for complete local rendering/model benchmark
- `tests.test_pdf_reuse_performance::test_offline_cold_warm_and_reuse_rendering_pairs`：Explicit opt-in for actual local Chrome rendering; semantic model remains offline

本地合成通过不代表安装版、真实文案／排版、真实邮箱／ATS、用户体验或研究接受。精准等待前全部已知必要附件仍按原票后继计划处理；Workable 未核验附稿契约仍保留，不关闭整个目标。

## 原票与历史最终读回

[最终读回](final-readback.json)与[Notes 链接核验](notes-link-readback.json)确认：11 张受影响原票及地图共 12 处追加 Notes；127 张票的解析元数据完全相同，24 张仍未关闭；128 份原文全部作为精确字节前缀保留，追加尾文也逐字节核对。1067 份旧证据、93 份安装版文件及 778 项冻结输入均未变。HEAD 保持 `e4a26d0c24311d014d478f7f92e58a88e6709b4b`，不新增或关闭票，不改负责人、状态、依赖或旧勾选。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。
