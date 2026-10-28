# 接通受版本约束的单岗位自动填写

Type: task
Label: wayfinder:task
Status: closed
Interaction: AFK
Assignee: 01a146b9/task_contract
Created: 2026-10-16
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [建立单岗位任务契约与持久恢复](01-task-contract.md), [复用岗位分析生成并确认专用简历](05-tailored-resume.md)

## 当前契约定位 — 2026-10-20

复用目标/文件绑定、执行记录和答案库；逐岗发送批准、唯一一岗批次及复杂恢复准入不再是产品默认，34/37承接。

当前产品规范与执行顺序分别见[单岗位流程](../../../docs/single-job-flow.md)和[统一开发计划](../../../docs/development-plan.md)。本票既有Status、Assignee、完成记录和收据不变；关闭仅证明当时范围，不证明新规范已实现。下方与现行规范冲突的旧审批、白名单、总时间窗及运行门槛保留为历史，由现有后继承接，不重开、不追认，也不据此执行真实申请。

## Question

怎样直接用当前任务已确认的材料启动一个岗位的 worker，而不要求人工伪造匹配或分流字段？

## Work and reuse

- 在现有 WorkerService prepare/start 中最小扩展 single workflow：只接收一个岗位、当前分析/简历绑定、明确国家和具体材料发送确认。
- 不自动写 application_strategy=manual，不伪造 precision_reviewed。保留旧 batch/precision 行为与既有调用兼容。
- 复用岗位身份、状态、deadline、重复、语言/资格、PDF、执行占用检查和 controller；模型报告不自动成为申请答案。
- 生成 PDF 在服务端按批准版本传入 worker，不要求用户从磁盘找文件；个人答案仅复用 confirmed 且适用范围一致的记录。
- 复用 needs_input、needs_recheck、原页回读、暂停/接管、只同步重试和人工 Submit。新任务不得覆盖旧任务/页面/未完成 intent。

## Ownership

- `src/career_evidence_graph/application_worker.py`
- `src/career_evidence_graph/application_flow.py`
- `src/career_evidence_graph/career_portal.py`
- `src/career_evidence_graph/job_screening.py（仅必要入口适配）`
- `tests/test_application_worker.py`
- `tests/test_application_execution.py`

以上为责任范围，不表示必须修改每个文件。多人同时工作时不得回退他人修改；共享接口按已完成依赖契约衔接，必要时先协调文件所有权。

## Acceptance criteria

- [x] 已有当前材料的 single 模式不依赖人工评分/分流字段，且只能准备一个岗位。
- [x] 缺链接、资格冲突/必要答案、重复投递、过期材料及已有 owner 时不能绕过检查。
- [x] 生成 PDF 字节与实际附件绑定一致；故障/重开/刷新不会重复填表或上传。
- [x] 自动最终 Submit 动作及替代最终投递请求保持为零，旧 batch/precision 与恢复回归通过。

## Verification and evidence

- tests/test_application_worker.py
- tests/test_worker_recovery_regressions.py
- tests/test_worker_attempt_completion.py
- tests/test_application_routing.py
- 先执行受影响的有意义测试；涉及共享流程/存储时按 CONVENTIONS 完成完整离线验证。浏览器合成与真实 ATS 分开记录。
- 关闭前将实际修改、所用版本、检查结果与限制写入本票 Resolution comment，并链接资产；不能用通过数或历史报告代替本票当前输入验收。
- 真实资料与私有衍生信息只保存在私有位置。本地图中的报告仅使用合成/脱敏状态，不嵌入真实字段、附件、岗位 URL 或私有指纹。
- 自动最终 Submit 保持为零。未知外部动作不自动重试。源码通过、安装版通过、真实填写、人工提交和雇主接收分别报告。

## Resolution comment

尚未领取或执行。后续执行者先填写 Assignee，再在此追加事实与证据；本段不是完成结论。


2026-10-17 执行与关闭：

- 复用现有 worker 新增严格单岗位 single 工作流：当前材料可以直接准备，不写人工分流/precision 标记；只允许一个岗位，保留状态、截止、重复、语言/资格、PDF、执行占用和人工 Submit 门禁。prepare 保持 paused，明确 resume 才启动。
- 服务端读取已确认 PDF，冻结 JD、全量来源、分析与采用材料链、简历配置、实际附件字节、目标 URL、国家和用户发送确认。独立只读校验跨进程持久化，覆盖动作授权、网络发送及人工接管复核；旧记录、原页和未决 intent 不自动重建。未知硬条件只能用本任务用户事实澄清，保留原分数；已知冲突不能绕过。
- 旧 handoff/worker/pending 仅在明确根目录只读核验，不初始化旧控制器。审计复现后修复同一暂停准备的 exact claim 恢复，以及准备结果未知时取消未停 worker 的缺陷；无法核验时不宣称取消成功。独立真实 WorkerService 合成 guard 复核通过。
- 受影响 worker/恢复/占用/绑定回归最终 **198 passed、34 deselected，7.19s**。默认完整离线 **1896 passed、145 deselected，228.80s**；完整运行启动后新增的单行 review 绑定检查及其反例由前述最终受影响集覆盖。后续整体验证将重新固定最终源码，不把该完整运行外推成安装版验收。
- HTTP tracer 验证直接绑定批准字节、拒绝客户端替换材料、prepare 不 spawn、显式 resume、错误岗位拒绝和取消先停执行。root adapter 有界审计共 **8 passed、125 deselected**，绑定专项另通过；Ruff、format 与 diff 检查通过。
- 未执行真实模型、真实表单、真实附件发送或最终 Submit；合成浏览器与安装版由后继票分别验收。
