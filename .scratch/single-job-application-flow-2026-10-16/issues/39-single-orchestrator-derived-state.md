# 统一岗位主控并派生浏览器执行状态

Type: task
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: 01a15926/root
Created: 2026-10-20
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [将单岗位流程设为原生 App 默认运行方式](08-native-runtime.md)、[完成单岗位链路与故障恢复整体验证](09-integration-verification.md)、[独立限制最终Submit并退役请求批准](38-independent-submit-boundary.md)
Triage: done

## Question

如何让默认投递只有一个模块决定选岗、等待及下一岗，并取消参与恢复判断的重复worker状态副本？

## Scope

依据[产品规范](../../../docs/single-job-flow.md)、[精简方案](../../../docs/development-plan.md)和[本轮审计](../../../docs/system-audit-2026-10-20.md)。本地图Notes沿用实施任务扩展；本次只发布票据，不领取、实施或关闭。已确认设计不再另设HITL批准。 本票负责主控职责及状态归属的重构；[接通邮件到人工最终确认的后台流程](34-email-to-review-pipeline.md)在其上集成真实推荐与匹配分流，不在本票重做整条产品功能。

## Acceptance criteria

- [x] ApplicationPipeline唯一决定默认投递的当前岗、运行/等待及下一岗；worker只执行明确指定的当前岗，不自行扫描整批jobs选岗，UI切页与心跳不另起业务调度。
- [x] Flow保留分析/生成/导出执行队列、attempt、产物采用和历史；worker保留跨进程命令队列、真实页面、intent和观察。不能把这两类不同用途的队列误删或合成万能status。
- [x] 页面执行状态由worker写入，Flow/task视图派生展示；不再由task.status和worker_ref.status可写副本共同决定恢复。产品运行意图、材料阶段、人工拥有页面、填写/上传及最终结果仍各有明确含义。
- [x] MaterialBatch与pipeline当前按模式互斥；对备用材料入口复用已有阶段执行与必要控制，不继续复制默认申请的选岗/提交规则。不能声称现有两种模式正在并发争抢同一页。
- [x] 复用现有文件锁和岗位占用记录；旧active/PID/目录单纯存在不证明仍活跃，实际同岗单执行者及未决动作继续受保护。不以batch变更夺取旧owner。
- [x] 用现有读取入口按task/application/worker引用最小兼容旧记录，不批量搬目录或双写新旧状态；旧原页、附件、人工编辑和未决动作不为重构而重启、覆盖或取消。
- [x] 模拟执行验证同一时刻仅指定岗可动作，必要事实等待阻止别岗，skip保留进度可返回，阶段已完成不重做；不将填写完、用户已提交和接收结果合并。后续集成由主编排票承担。
- [x] 给出删除的重复决策、可写状态副本及调用约束清单，以公开行为回归证明收敛；不另建总控、数据库或工作流框架。

## Ownership and handoff

拥有ApplicationPipeline与ApplicationFlowService/MaterialBatch的调度职责、worker指定当前岗接口及重复状态展示；不负责邮件归档、完整材料生成器共享或人工交接产品功能。阶段恢复票和交接票消费本票的当前任务与状态接口。实际实施需协调共享文件，不回滚他人修改。

## Out of scope

岗位并发、重写全部历史状态、强制新枚举、研究图状态迁移、清空旧活动记录。


## Notes — 持续主线源码后继 2026-10-21

使用既有持久队列激活当前首岗，未推进其他候选 JD 或分析；旧 source-chain 保留兼容。取消旧总运行窗，健康本地阶段重开继续，显式暂停和未知结果仍等待。完整指定岗执行接口、Submit 结果消费、skip / 返回仍按原范围继续。

完整默认离线：4263 passed, 2 skipped, 428 deselected in 661.45s (0:11:01)；[工程记录与原日志](../../automatic-mainline-2026-10-21/README.md)。旧三项 P2 的独立冻结记录及全部失败历史保留。Status、Assignee、依赖、既有勾选均不变，不新增票、不关闭本票；App 未更新，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 当前岗继续与事实材料后继 2026-10-21

当前岗指针统一调度及授权；旧保留页不作为当前执行岗，切岗后发送前再次核验，原未决intent保留。空队列主动暂停后一次Continue恢复原邮件等待；真实Worker重启仍保守核验，本条不声称其所有恢复或主控工作已完成。

完整默认离线：4349 passed, 2 skipped, 432 deselected in 676.79s (0:11:16)；[本轮工程、复核与原日志](../../linear-continuation-2026-10-21/README.md)。初轮完整运行因发现缺陷主动中止，旧失败/修复/绿色结果分别保留。Status、Assignee、依赖与原勾选不变，不新增票、不关闭本票。App未更新，真实申请继续暂停，最终Submit始终人工。


## Notes — 必要材料、路由与恢复后继 2026-10-21

默认编排消费既有匹配路由、必要材料、恢复回执和当前岗状态，不另造调度器。未知结果按实际 Flow/Pipeline 目标隔离；不能以旧岗未知结果锁住新岗，也不能用失效读取启用当前岗写操作。

完整默认离线：4440 passed, 2 skipped, 460 deselected in 718.67s (0:11:58)；受影响离线 1097 项、本地浏览器 164 项均通过。[工程记录、失败历史及冻结输入](../../product-completion-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 原页材料安全更新后继 2026-10-21

原页材料更新复用既有 Pipeline、Flow、Single 与 Runner，候选制作、原页核验和绑定恢复沿当前任务推进，不另建调度器。未保存当前任务源时阻止继续使用旧稿；无关任务的查看与安全暂停保持可用。

完整默认离线：4450 passed, 2 skipped, 497 deselected in 727.15s (0:12:07)；受影响离线 1358 项、本地浏览器 217 项均通过。[工程记录、失败历史及冻结输入](../../bound-material-update-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 精准等待前必要材料与人工附稿修复 2026-10-21

精准材料准备和人工附稿沿既有 Pipeline/Flow/Worker 推进，不建立并行调度器。未保存文本、正在制作或 needs_recheck 阻断继续；排队 Continue 遇 pause/cancel/skip 不复活；安全停止与原岗恢复保持可用。

完整默认离线：4462 passed, 2 skipped, 532 deselected in 968.76s (0:16:08)；受影响离线 1370 项、本地浏览器 252 项均通过。[工程记录、失败历史及冻结输入](../../precision-material-preparation-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 浏览器、材料与默认入口后继 2026-10-21

默认新岗统一入既有Pipeline队列；HTTP实际分派前及写入锁内限制旧独立执行入口，保留关闭、observer错误优先级及安全暂停/查看。没有增加第二业务主控；全部状态副本和旧实现退役仍待。

完整默认离线：4487 passed、2 skipped；本地合成浏览器：372 passed。受影响集合已包含在最终完整默认/浏览器运行，重叠结果不累加。[工程、原日志与最终冻结输入](../../browser-material-entry-engineering-2026-10-21/README.md)。早期统一失败、独立审查和修复均原样保留。Status、Assignee、依赖和既有验收勾选不变，不新增或关闭票。App未更新或启动，真实申请继续暂停，最终Submit始终人工。


## Notes — 可用优先重排 2026-10-21

状态副本是真源码收尾；依赖已具备运行保护契约，不等待安装/在途交接整票。

Priority/Triage/票头依赖按本次重排更新；旧边与原字节见[审计及变更账本](../../usable-first-wayfinder-audit-2026-10-21/README.md)。原 Status、Assignee、Interaction、既有验收勾选及全部旧正文保持，不领取、不关闭、不替用户接受。源码接口依赖不等于安装或真实操作许可；App 未更新，真实申请继续暂停。


## Claim — 源码收尾 2026-10-21

用户已明确要求继续本票源码工程，本轮由01a15926/root领取。复用现有Pipeline、Flow、Worker与材料实现；源码接口前置可消费，不等待其安装/真实接受整票。原依赖、历史与既有验收保留。App更新和真实申请继续暂停，不新增审核点。原票字节见[本轮基线](../../ticket39-41-source-2026-10-21/)。


## Delivery — 源码结案 2026-10-21

本票按当前源码范围结案，逐项证据见[验收矩阵](../../ticket39-41-source-2026-10-21/state-and-acceptance.md).复用现有实现，不新增审核点；保留原依赖、owner、页、附件、人工编辑、未决动作及历史。

最终冻结v2：4656 passed, 2 skipped, 572 deselected in 931.45s (0:15:31)；本地浏览器：86 passed in 224.40s (0:03:44)；受影响集合：476 passed, 1 deselected in 101.73s (0:01:41)。集合有重叠，不累加。820项输入在各轮前后均未改变；首轮8项失败及修复日志、旧候选v1均保留。[交付记录、候选与原日志](../../ticket39-41-source-2026-10-21/README.md)。

这仅关闭本票源码工程，不替代主App安装组合、真实材料内容/版式或真实申请验收。下游原票继续持有这些范围。App未构建、更新、安装或启动，真实邮箱和申请未操作，最终Submit仍由用户完成。
