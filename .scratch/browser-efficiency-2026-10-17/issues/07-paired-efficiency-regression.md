# 验证已选浏览器候选的组合收益

Type: task
Label: wayfinder:task
Status: closed
Triage: ready-for-agent
Completion: frozen-composed-candidate-verified
Priority: P1
Interaction: AFK
Assignee: 01a14a95/root
Created: 2026-10-17
Updated: 2026-10-18
Parent: [交付 DOM 优先的受控浏览器效率改进](../map.md)
Publication order: 20
Blocked by: [让字段流程按忙闲状态调度](05-bounded-waits-readback.md)、[在派发前选择已支持的执行路线](06-hybrid-browser-routing.md)

**What to build:** 冻结包含调度与窄DOM路线的候选包，验证组合后更快且字段正确、失败可解释。

## Acceptance criteria

- [x] 基础候选固定为忙闲调度、窄DOM与派发前选路；观察缓存、原生Cua优化按完成证据另选，不是默认阻塞。
- [x] 若扩展候选，先补上相应真实依赖并完成候选自身验收，不得将未验证能力装入发布包。
- [x] 至少五对同输入组合对照，固定版本和独立oracle，目标/非目标值、动作计数和必要合成请求分别核验。
- [x] 记录成功、失败、部分完成与评估错误；离线重评不是新运行，禁止会改页的现场validator或动作回放。
- [x] 完成受影响及完整默认离线回归；失败/取消/unknown保留，不依赖全部公开benchmark或新增模型judge。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Comments

### 2026-10-18 — Frozen composition complete

[候选及验证](../../browser-efficiency-release-2026-10-18/README.md)、[组合验证记录](../../browser-efficiency-release-2026-10-18/composition-verification.json)、[独立逐臂审查](../../browser-efficiency-release-2026-10-18/review/composition-review-v1.json)通过。候选4809f867…固定245个公共文件，仅调度/DOM/选路及验收入口；没有扩展缓存/query/JD适配或新增依赖。完整默认离线2554、浏览器86及静态门槛对应同一245文件清单，正式比较后严格核验仍通过。

同一冻结harness五对AB/BA、十个独立进程使用各自完整runtime和真实固定helper f73a1529…；全部30字段及独立目标/非目标、原节点、File、CDP和native各自身份、真实动作/RPC/请求与清理核验通过。三字段完整流程中位2934.441→729.531ms，最小配对节省2123.262ms大于两臂range62.492/96.123ms。启动另计；不推广为真实ATS或全App速度，CPU仅child Python。

双方预检已知失败、部分完成后取消、unknown保持停止共6场景均通过。离线缺失expected文件明确evaluation_error，保留原执行成功、不增加运行或延迟样本、不改页面。早期warmup身份命名空间评估器错误与closed=false及独立退出记录原样保留，不混正式五对。没有重放未知动作、上传、Submit、真实邮箱/模型/岗位调用。安装与人工接受分别交08/09，真实申请继续暂停。

### 2026-10-18 — Execution claim and admitted scope

前置05/06已闭，root领取。候选仅调度、窄DOM、派发前选路及严格合成验收入口；02/04优化已明确不实施，10可选来源不是前置。不额外装入缓存/query候选。完整公共源245文件已通过本轮2554离线/86浏览器及静态门槛；冻结时逐项比对该源，未改代码则复用精确验证，避免把不同版本的绿色结果相混。原baseline有完整60个Python模块且199文件哈希匹配，但缺构建配置，不能当可安装checkout。比较各臂独立进程分别导入baseline/src与候选payload/src，所有career模块源必须属于该侧；共用锁定第三方依赖/纯fixture数据/外部harness，不混用current runtime。真实helper固定f73a1529…，显式dom_event；拒绝double冒充baseline原生速度。真实申请继续暂停。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/20-browser-release-regression.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/browser-efficiency-2026-10-17/issues/07-paired-efficiency-regression.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。
