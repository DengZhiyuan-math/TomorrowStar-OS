# 让字段流程按忙闲状态调度

Type: task
Label: wayfinder:task
Status: closed
Triage: resolved
Completion: source-and-paired-browser-verified
Priority: P0
Interaction: AFK
Assignee: 01a14a95/root
Created: 2026-10-17
Updated: 2026-10-18
Parent: [交付 DOM 优先的受控浏览器效率改进](../map.md)
Publication order: 14
Blocked by: None (can start immediately)

**What to build:** 相同12字段流程减少无条件等待，同时保留事件分发、取消、保活和网络守卫。

## Acceptance criteria

- [x] 已有基线与三份研究为完成证据；只改忙闲调度，不同时修改缓存、动作或回读。
- [x] 采用现有公共接口；先检查条件、先订阅后触发，总deadline与finally清理明确，禁止把timeout=0当非阻塞等待。
- [x] 至少五对同输入完整生产循环交错比较，到同一字段核验终点；报告每轮、范围、CPU、停止响应、失败和未知。
- [x] 覆盖idle/paused/fault、事件在tick间到达、关闭/崩溃/断连、取消及lease；收益超过同版重复波动，不靠忙等。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Comments

### 2026-10-18 — Busy/idle scheduling verified

[完整证据](../../browser-efficiency-execution-2026-10-18/waits/README.md)：只在已持久核验字段/上传进度后请求5ms正值事件分发；其他idle/paused/needs-input/fault维持250ms预算，既有监听、deadline和清理保留。5对同输入12字段完整tick→pump流程中位3589.79→530.76ms，最小配对节约3052.86ms超过同版60.02/59.11ms范围；120 verified fills，0 unknown/error，独立目标回读与GET-only核验通过。Python CPU为进程口径，不冒充Chrome/系统CPU。

9个新浏览器回归与39个受影响现有回归通过；pause/cancel/事件/lease/请求守卫、idle/paused/fault每秒4轮及清理证据保留。原失败paired-01原样保存，不计入成功对照。[最终源码门槛](../../browser-efficiency-execution-2026-10-18/full-gate/verification.json)2516默认离线通过、245显式排除，静态检查通过、217源码文件无漂移。独立审查无阻断。结论限隔离DOM合成流程，安装/真实Cua及用户接受另验；真实申请继续暂停。

### 2026-10-18 — Execution claim under all-remaining-ticket authorization

用户要求持续推进全部剩余票，覆盖原每会话一票的限制。本票已回读当前状态与依赖，由 `01a14a95/root` 领取；允许隔离合成实现、测量与验证，真实申请继续暂停。保留原页面、附件、私人记录及未知结果；不读取真实邮箱／模型，不写真实字段／上传或Submit。共享模块按函数责任协调，不回退其他在途改动。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/14-busy-idle-browser-loop.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/browser-efficiency-2026-10-17/issues/05-bounded-waits-readback.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。
