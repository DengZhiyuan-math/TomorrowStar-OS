# MC-09：T10 新产品路径合成整链与故障验收

Type: verification
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: claude-code-367f651f/root
Created: 2026-10-26
Parent: [Module 剩余开发地图](../map.md)
Blocked by: [MC-08](08-t09-app-dispatch-controls.md)
Triage: closed-source-synthetic-native

## 问题与范围

在各项自己的回归已经通过后，对实际 Worker Interface + 受控 app-server peer + loopback ATS 做新接管链整体验收。R6 为改动前基线，不是本票新链通过记录。

## 文件所有权与并行边界

既有 adapter/worker/生命周期与 fixture 测试；不新增通用测试框架。实现冻结后验收，不能与 MC-14/15 对受验代码的修改重叠；不同独占测试文件可并行编写。

共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [x] 完整覆盖启动、原页观察/动作、正文/附件、交回/完成、停止/恢复，记录实际新链节点及结果。
- [x] 在启动、工具、回报和最终保存注入丢响应/断线/保存失败；每个效果可核对或 unknown，无重放/第二页/第二写者/自动 Submit。
- [x] 保留旧 App/Codex 调用、人工编辑、取消和原页恢复兼容，不用旧 CUA 或外部 handoff 测试代替新链。
- [x] 完整默认离线与相关隔离浏览器按同一新快照覆盖，静态检查与独立审查通过，全部失败/跳过/中断如实保留。

## 既有证据与限制

[正式 T10](../../../docs/module-interfaces-and-migration-design.md#t10-产品路径的合成整链与故障验收)与[R6 基线](../serial-r6-verification-summary.md)。性能/native opt-in 不自动并入。

需求以[正式设计](../../../docs/module-interfaces-and-migration-design.md)为准。R6 只证明原冻结源码与合成测试范围；本票如有新实现，
须记录实际改动、对应回归和审查，不能复用 R6 关闭新行为。未知结果、人工内容、原页、
原 journal 和历史记录保留，最终 Submit 手动。

## Comments

### 2026-10-27 认领（Europe/Zurich）

`scripts/query_tickets.py` 核对：MC-08 已结案，本票为机械前沿，open/unassigned。按用户指示由 `claude-code-367f651f/root` 认领，
与 MC-09/MC-14 并行规划；尚无源码改动或测试运行。不扩展实际模型、安装 App 或真实 ATS 权限；最终 Submit 手动。

### 2026-10-27 用户决定与并行安排（Europe/Zurich）

计划见 [MC-09 计划](../../remaining-tickets-2026-10-26/mc09-chain/PLAN.md)，用户全部按建议确认：链路用固定合成材料（真实生成另有测试）；
以脚本处理不了、原生工具可操作的控件触发接管（`ambiguous_option` 的 `<select>` 或脚本结果未知的输入），都不可行则记为发现、不放宽原生点击策略；
原生范围 1 条链路 + 2 个链中故障；Ashby/Workable 早期上传与自定义下拉框仍在 fog。**MC-09 先冻结并验收，MC-14 的源码改动之后再落地**：
MC-14 在隔离副本 `/Volumes/Codex-Workspace/ts-mc14-work/` 中实施，主 checkout 在 MC-09 验收期间不接收 MC-14 改动。

### 2026-10-27 用户决定：原生测试浏览器的外部连接（Europe/Zurich）

原生开发运行观察到：候选驱动启动的 Chrome 未关闭后台联网，启动即连接 Google 服务；导航到合成地址 `jobs.lever.co/...` 时还会对真实主机
做 DNS 与 TCP 预连接（`:443` 连接保持到用例结束，很可能完成 TLS 握手/SNI；页面层面未发送任何 HTTP 请求或表单内容，页面内容全部由本机 loopback 提供；socket 采样无法证明零字节）。MC-07 原生运行很可能同样存在。
用户决定**接受并记录**为合成测试环境的已知情况：硬断言改为页面层面（所有请求由 loopback 提供或被拦截，无请求内容发往外部主机），
socket 采样保留为证据。从驱动层关闭（`--disable-background-networking` 与预连接）记入地图 fog，可另开票。

### Resolution（2026-10-28，Europe/Zurich）

同一冻结 1818 文件 `5a485944…`、候选 candidate-r2 `550d4621…`（未变）：完整默认离线 8314：8311 passed / 3 skipped / 0 failed；
受影响隔离浏览器 browser-r3 314：309 passed / 5 native opt-in skips / 0 failed（browser-r1 两次 2 s 计时、browser-r2 一次 workbench 竞争偶发失败保留不计，见诊断）；
实际 native 3/3 passed：两次自动接管的整链、链中工具结果未知、链中丢失最终保存后 Continue。独立证据与代码审查 READY-TO-CLOSE、无 P1：
[final-evidence-review](../../remaining-tickets-2026-10-26/mc09-chain/acceptance/final-evidence-review.md)；[验收记录](../../remaining-tickets-2026-10-26/mc09-chain/acceptance/README.md)。

整链证明（浏览器 + 原生）：真实邮件收录 → Pipeline → 脚本在真实页面填写 → 部分遮挡的 combobox 使脚本点击超时（`browser_result_unknown`）→ Pipeline 自动派发接管 →
真实原生输入 → 未知意图经读回结算（不重放）→ 交回脚本（`return_count 1`）→ 脚本自己填写 Phone → 第二个阻塞 → 第二次接管（`complete_remaining_fields`）→
`filling_complete` → `automatic_submit_wait`；提交 0、单一申请页、单写者。链中故障（离线）：取消、跳过后返回、第二次接管中暂停后一次 Continue、接管中编辑材料、后端关闭重开、启动回执丢失。

本票生产修复（均先写失败回归）：已证停写且不再匹配当前接管的运行句柄释放（`application_worker_browser.py` `_service_assistance_stop`）；
丢失最终保存后 Pipeline Continue 改走 Worker `resume` 解死锁（`application_pipeline.py`）；Adapter 只接受派发所引用的那一个未决意图（`pending_action_id`）；
同一会话第二次交接时忽略更早代次中已完成/未发送的历史调用、仍拒绝未决历史（`application_codex_assist.py` `_native_status`）。

证据边界（审查 P2）：**正文与附件交付**（条件 1）不在本链路中（链中仅脚本上传简历），沿用 MC-06 原生验收及本冻结 browser-r3 中的
`test_native_material_context_browser.py`、`test_material_batch_browser.py`；**报告丢失与 app-server 断线**未在整链中注入，沿用各自测试
（`test_adapter_codex_native.py`、`test_worker_assistance_return_service.py` 与 MC-07 原生）。

限制与后续（审查 P3）：运行句柄释放修复只有假 Adapter 证据（真实 Adapter 在原生状态缺失时报告未排空，最坏是停滞而非不安全）；同一浏览器会话中一次未决原生调用会拒绝其后所有接管（失败即关闭）；
`test_worker_stability` 的 2 s 预算在负载下三次偶发失败；native-dev 02-d1 一次接管前拒绝原因未记录、未复现；S10 人工编辑的原生证据来自 MC-07 冻结。
原生测试浏览器的外部连接按用户决定接受并记录（见上方决定与地图 fog）。未运行实际模型、安装签名 App 或真实 ATS；最终 Submit 手动；未提交 git。
