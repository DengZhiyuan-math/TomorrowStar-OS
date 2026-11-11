# 核对保留任务占用并确定安全接续位置

Type: task
Label: wayfinder:task
Status: closed
Priority: P1
Interaction: AFK
Assignee: none
Created: 2026-10-22
Parent: [交付分经历简历生成并接续实际使用](../map.md)
Blocked by: none
Triage: deferred-to-real-use
Closure reason: deferred_to_usage

## 当前处理决定 — 2026-10-22

用户明确将“操作结果不明时如何继续”移入后续真实使用过程测试，再据反馈决定是否修改设计。移出本轮生成与安装交付范围，取消对安装同步的阻塞；本票关闭仅表示范围调整，不表示旧任务已恢复、旧动作已结算或问题已修复。

本轮不再主动核验旧页面、开发恢复机制或要求用户决定旧任务。使用中实际遇到时记录动作、网页现状、可核验结果和处理方式，再决定是否需要后续工程。旧私有状态、人工修改和intent保持，不以延期为由清空或重放。

下文问题、事实及接受条件保留为调整前记录，不再作为本轮交付门槛。

## Question

当前blocked及保留原页来自真实在途任务、未决操作，还是可确认结束的历史记录？如何保留已有材料和人工修改，确定Codex实际使用的下一步？

## Current facts

此前读取到pipeline.status=blocked，当前Flow任务resume_ready，通知要求先核验已有申请任务或保留原页。仅凭这些字段不能断言是活锁、程序缺陷或可删除的陈旧记录。尚无本问题的生产修复或原页接续完成证据。

本轮只读细查：当前任务分析与简历均complete、worker_ref为空；旧worker对应另一岗位，paused/needs_recheck，reason=checkpoint_unavailable，page_open=false，仍保留旧fill intent，命令队列为空且无提交回执。当前没有原页活性证据。新源码application_worker.py的check_new_current_job遇旧格式无current_job_id时仍走_check_legacy_prepare，旧未结算job触发batch_exists；这是保留任务的准入保护，不是本轮已证实需要删除的锁或简历生成失败。具体私有定位不写入本票。

一次Continue与skip/return已有[工程及合成结案](../../ticket37-evidence-reconciliation-2026-10-21/README.md)，未结算上述旧真实操作；[当前岗位邮箱更正](../../single-job-application-flow-2026-10-16/issues/23-current-job-email-correction.md)源码已交付，但本地更正不证明页面已改。下一步读取原页实际状态，再决定沿旧任务继续或按现有skip保留返回；不清空JSON或删除intent。

## Acceptance criteria

- [ ] 核对当前任务、worker job/run、owner、intent及可观察原页；PID/目录/心跳或旧page_open不能单独证明活性。
- [ ] 明确报告已知状态、未知项、最后明确动作及安全下一步；敏感定位保留在私有证据，不写公开票。
- [ ] 先核对已执行操作，不自动重传、重填、清锁或删除状态；保留材料和人工修改。
- [ ] 如确证代码缺陷，先留准确场景与回归；若只是恢复核对，不人为追加自动化改造。
- [ ] 实际恢复由Codex接续具体岗位，最终Submit人工；可区分只读核对完成与页面操作已完成。

本票可以独立于生成实现开始核对；安装前的状态保全消费该结果，但不要求真实投递才可维护。
