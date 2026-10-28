# 确定同岗并发写作与局部恢复

Type: grilling
Label: wayfinder:grilling
Status: closed
Priority: P1
Interaction: HITL
Assignee: Codex /root
Created: 2026-10-25
Parent: [简历与 Cover Letter 同岗并发生成接入规划](../map.md)
Blocked by: [确定 Cover Letter 正文契约与材料身份](01-content-contract.md)
Triage: resolved

## Question

同一岗位的简历与 Cover Letter 两路写作由谁启动、持有和恢复，怎样证明实际并发，
同时确保每一路结果独立采用且不覆盖人工修改？

需要基于前置正文契约明确：

- 现有 Flow 单队列、外部 Codex 作者 handoff 和 Cover Letter 单作者如何组合。
  不能把两个任务串行排队称为并发，也不另造岗位调度器。
- 共同固定输入与各自 attempt 的绑定；模型调用在锁外运行，结果在短事务内按
  当前 attempt 合并，不整体覆盖另一材料或最新人工版本。
- 已有简历可复用、仅需补求职信，或反过来只需改简历时，如何只启动必要分支。
- 成功、已知失败、正在运行、未知结果、暂停、取消和 skip 后迟到结果如何处理；
  重启后谁接回运行，哪些情形可以继续，哪些必须核对而不能盲重放。
- 取消一个分支和停止整个岗位如何区分；当前同岗执行占用如何复用。
- 未来怎样用两个受控作者调用的重叠区间／同步屏障证明并发，并证明暂停、重启及
  局部失败不会重跑成功分支。此处只设计验证，不运行实际作者。

完成时记录最小调度拓扑、状态转换及事件表、锁与保存归属、恢复规则和验证方法。
既定的同岗并发及跨岗位顺序处理不再作为开放选择。

## Source locators

- [application_pipeline.py](../../../src/career_evidence_graph/application_pipeline.py)：Pipeline._materials。
- [application_flow.py](../../../src/career_evidence_graph/application_flow.py)：start／_run_tasks。
- [career_portal.py](../../../src/career_evidence_graph/career_portal.py)：generate_flow_resume。
- [application_experience_latex.py](../../../src/career_evidence_graph/application_experience_latex.py)：作者 handoff。
- [codex_cli.py](../../../src/career_evidence_graph/codex_cli.py)：run_codex_exec。

## Comments

尚未领取或解决。本轮只建图；新决定记录为 resolution，不能把问题中的候选行为当作已实现。

### Resolution — 2026-10-25 源码实施

Flow 的 `cover_letter` 是独立持久分支；简历保留原 stage 和既有分经历内容交接。
`application_resume_author.execute_content_generation` 消费原 configure/writer/submit/assemble/review/adopt
Interface，实际执行所缺作者；求职信由独立线程执行单一整封作者，两路调用在应用锁外运行。
写作输入绑定同一已采用分析和固定交付。外部交接模式仍可显式保留。
短锁仅保留尝试、采用与合并。成功分支不重写；已知失败可局部重试；未知结果仅核验原回执。
取消/skip 不采用迟到结果；已开始调用的未知结果不能被 skip 绕过。
新的调用在 admission 时检查停止状态，暂停后一次 Continue 继续所缺简历作者。
重启不盲重放；已完成本地回执可接回。队列仍只持有一个岗位。
同步屏障测试覆盖实际简历 scoped model runner 和整封求职信 runner 的重叠，
不将两个排队任务或 handoff 创建的重叠称为实际作者执行证据。
实际远程作者仍未在本轮运行。见 [实施记录](../implementation.md)。
