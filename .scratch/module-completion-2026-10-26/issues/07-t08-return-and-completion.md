# MC-07：T08 可靠交回与填写完成

Type: task
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: claude-code-367f651f/root
Created: 2026-10-26
Parent: [Module 剩余开发地图](../map.md)
Blocked by: [MC-06](06-t07-bound-material-delivery.md)
Triage: closed-source-synthetic-native

## 问题与范围

依赖链已包含 T04/T06/T07。仅在停写、工具排空及原页核对后交回可接续脚本；不能接续则持续处理到人工 Submit 前，保存真实完成证据。

## 文件所有权与并行边界

application_worker.py、application_worker_browser.py 的控制/报告/原页接续，Pipeline 仅消费执行投影。与 MC-13 的 Pipeline/Flow 常规准备迁移划分方法区域，所有接管控制归本票。

共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [x] 同页复杂控件后可靠交回、无法脚本接续时继续处理到 Submit 前两条路径均有新链证据。
- [x] 一句成功、仍在途或旧观察不能形成完成；填写完成与已提交分开保存。
- [x] 暂停/取消/Skip/材料变化后的迟到回报只留历史；停写/排空/原页核验顺序可审计，无第二写者。
- [x] App 同步或最终保存丢响应只核对/重存原结果，不重填、不重传；合成回归与审查通过。

## 既有证据与限制

[正式 T08](../../../docs/module-interfaces-and-migration-design.md#t08-可靠交回与填写完成结果)。T05 只读原页恢复仍为 paused/needs_recheck，不视为本票完成。

需求以[正式设计](../../../docs/module-interfaces-and-migration-design.md)为准。R6 只证明原冻结源码与合成测试范围；本票如有新实现，
须记录实际改动、对应回归和审查，不能复用 R6 关闭新行为。未知结果、人工内容、原页、
原 journal 和历史记录保留，最终 Submit 手动。

## Comments

### 2026-10-27 认领（Europe/Zurich）

`scripts/query_tickets.py` 核对：MC-06 已结案，本票为唯一机械前沿，open/unassigned。按用户指示由
`claude-code-367f651f/root` 认领。先复用[只读接缝图](../../remaining-tickets-2026-10-26/mc07-readonly-map.md)，并按 MC-06 结案后的
实际代码重新核对；尚无源码改动或测试运行，四项验收保持未勾选。不扩展实际模型、安装 App 或真实 ATS 权限；最终 Submit 手动。

### 2026-10-27 用户设计决定（Europe/Zurich）

计划见 [MC-07 计划](../../remaining-tickets-2026-10-26/mc07-return/PLAN.md)。用户确认：

1. **交回脚本仅在严格条件下进行**：同一文档、无跳转；无校验错误；每个改动字段都对应一次 Codex 已观察的原生操作；
   无未决或未知结果；且**接下来待填的字段脚本能处理**。否则 Codex 继续填到底（路径 B）。
2. **防止来回循环**：同一岗位**最多交回脚本一次**；交回后若脚本再需 Codex 接管，第二次由 Codex 填完剩余全部，不再交回。
   Codex 已完成并经核对的字段记为已完成，脚本跳过，不再重新识别；核对只看通用的有值/有效/归属，不要求脚本理解复杂控件。
3. **填写完成**需要 Codex 的结构化报告**加**程序独立只读核对（无校验错误、必填非空、所需材料已核实放好）；单句成功不算。
4. **核对不通过**：停下并标为需核对，原页与内容保留；自动再派 Codex 属 MC-08。
5. **结果存盘丢失**：Continue 后重新只读核对并重存同一份结果，不重填不重传；期间不得有暂停/取消/换岗等变化。
6. **Codex 与脚本之间往返的数据都用标准化、带版本的 JSON**：交接沿用 [T06 JSON 契约](../../../docs/module-interfaces-and-migration-design.md#codex-takeover-json-contract)；
   回报与交回/完成结果在同一节补充正式结构，两端严格校验，结构外的文字不作为回报。

### 2026-10-27 用户决定：存储故障后的 Continue（Europe/Zurich）

原设计（并发、全自动时期）在保存失败后永久拒绝 Continue。用户确认改为：仍保留“记录存不进去就不继续填”的保护，
但一次显式 Continue 会先把未改动的存档原样重写；写入成功才清除故障标记并继续（之后按 S6 只读核对并重存原结果，
不重填、不重传），仍写不进去则照旧拒绝且不改动磁盘。回归：`test_direct_resume_storage_stop_keeps_pause_error_stop_marker_and_claims`
（存储仍故障 → 拒绝、字节不变）与 `test_continue_lifts_a_storage_stop_once_the_checkpoint_is_writable`。

### Resolution（2026-10-27，Europe/Zurich）

同一冻结 1815 文件 `7f3a2366…`、候选 candidate-r2 `550d4621…`（未改动）：完整默认离线 8169：8166 passed / 3 skipped / 0 failed
（offline-r1 有一次未改动文件的计时偶发失败，保留不计，见诊断）；受影响隔离浏览器 286：281 passed / 5 native opt-in skips / 0 failed；
实际 native 6/6 passed（return_to_script、filling_complete、prose_only、pending_call、pause_during_report、lost_outcome_save）。
每例一次、无重试/信号、自动清理、源码不变。[验收记录](../../remaining-tickets-2026-10-26/mc07-return/acceptance/README.md)；
独立证据与代码审查 READY-TO-CLOSE、无 P1：[final-evidence-review](../../remaining-tickets-2026-10-26/mc07-return/acceptance/final-evidence-review.md)。

实现（均先写失败回归）：S0 回程 JSON 契约（`assistance-report/v1`、`assistance-outcome/v1`、`return_count` ≤1）写入设计；
S1 Adapter 按本 turn 捕获结构化最终消息；S2 `released`/`superseded`/report/outcome 校验与条件采用；S3 正常结束的停写原因、
停写后只读核对与会话收回；S4/S5 交回脚本与填写完成服务、ready tick/review 使用已核实结果；S6 存盘丢失后只重存同一结果；
存储故障标记经一次 Continue 的原样重写后解除（用户决定）。原生开发中另修 7 处生产问题（见 [native-dev](../../remaining-tickets-2026-10-26/mc07-return/acceptance/native-dev/README.md)）。

验收条件对应：1 = native 01（交回后脚本继续填写）/02（持续至手动 Submit 前）；2 = native 03/04 + 离线报告/完成门；
3 = native 05 + 离线 superseded/拒绝采用历史/顺序时间戳与释放后拒绝原生调用；4 = native 06 + 离线重存与同步重试。

限制（P2）：criterion 1 的“复杂控件”为合成的“输入即选定” input 型 combobox；原生点击策略不能从自定义列表中选选项，
已记入地图 fog，**不代表自定义下拉框可用**。审查 P3（不阻塞，留作加固）：同一 turn 中后到的文字消息不覆盖先前有效 JSON 声明；
`next_step.kind` 未校验；填写完成不因无法归属的改动而阻止（仅交回阻止）；ready/review 不在交接前再次读页；丢失重存的放宽只看
resume_serial 前进（仍会重新核对页面）；回程服务中非存储异常也报告为存储停止；prose/暂停路径保持原生会话为已交出（无第二写者）。
未运行实际模型、安装签名 App 或真实 ATS；最终 Submit 手动；未提交 git。MC-17 入口清单已同步，MC-18 基线未变（离线中通过）。
