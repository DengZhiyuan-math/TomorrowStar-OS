# 取得隔离原生Cua的真实操作证据

Type: task
Label: wayfinder:task
Status: closed
Triage: done
Closure reason: completed
Completion: isolated-native-helper-rpc-baseline-verified
Priority: P0
Interaction: AFK
Assignee: 01a14a95/root
Created: 2026-10-17
Updated: 2026-10-18
Parent: [交付 DOM 优先的受控浏览器效率改进](../map.md)
Publication order: 17
Blocked by: None (can start immediately)

**What to build:** 在新归属合成资源中核实原生Cua就绪，取得真实绑定、快照、点击与回读耗时。

## Acceptance criteria

- [x] 先核验上次未知请求及本轮资源；不盲重试，不接管或重开原申请。
- [x] 至少五个可比原生操作样本；权限、启动、绑定、观察、动作与回读分段，模拟数据单列。
- [x] 若启动仍unknown，保留阻断、原始失败与明确恢复条件，本票不虚报完成。
- [x] 历史根因仍归原票；发现具体共因或新根因后再建窄修复，不预设本票包办所有原生故障。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Comments

### 2026-10-18 — Resolution: isolated native helper operations measured

[本轮验证](../../browser-efficiency-execution-2026-10-18/native/verification.json)已核验原unknown的socket和父目录均不存在，保留历史closed=false、transport_failed=true及缺失的原profile/PID/RPC id，不重发原请求，也不把新成功作为旧根因修复。全新runtime、socket及driver-owned profile，固定已准入helper SHA f73a1529…、bounded许可仅about:blank与合成loopback，未调整TCC或访问日常浏览器。

[真实原生结果](../../browser-efficiency-execution-2026-10-18/native/run-01/result.json)：同一新runtime内5个独立页面均完成生产CuaDriver.fill、绑定和独立原节点／target／值回读。共5次binding、10次完整semantic snapshot、10次dom_event点击，全部acknowledged；权限和启动单列，startup约3603ms。binding中位78.81ms，semantic snapshot中位66.56ms，click中位130.27ms；5个fill为467.81–515.71ms。不是5次冷启动、trusted鼠标、视觉代理或整个worker/App耗时，不能与DOM周期直接作速度倍数。

只观测原RPC返回，不替换transport或固定哈希。结束后closed=true、transport_failed=false，socket与profile已消失，记录的Chrome和daemon PID均不再存在。独立只读审查无阻断。新可用性证据解锁局部Cua观察评估；旧历史调查保持原状态。真实邮箱／模型／ATS／上传／Submit及原页面操作均为0，真实申请继续暂停。

### 2026-10-18 — Execution claim under all-remaining-ticket authorization

用户要求持续推进全部剩余票，覆盖原每会话一票的限制。本票已回读当前状态与依赖，由 `01a14a95/root` 领取；允许隔离合成实现、测量与验证，真实申请继续暂停。保留原页面、附件、私人记录及未知结果；不读取真实邮箱／模型，不写真实字段／上传或Submit。共享模块按函数责任协调，不回退其他在途改动。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/17-native-cua-readiness.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/browser-efficiency-2026-10-17/issues/11-native-cua-baseline.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。
