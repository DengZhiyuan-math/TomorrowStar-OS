# 增量保存邮件岗位后标记归档并延后取得JD

Type: feature
Label: wayfinder:task
Status: claimed
Priority: P1
Interaction: AFK
Assignee: 01a15ab3/root
Created: 2026-10-20
Parent: [申请主流程](../map.md)
Blocked by: [从 Gmail 推荐邮件自动取得岗位与原 JD](14-gmail-recommendation-intake.md)、[接通邮件处理设置与独立进度展示](42-mail-processing-settings-status.md)
Triage: source-followup

## 当前范围

依据[规范](../../../docs/single-job-flow.md)的 APP-01/02/17/18 和[统一计划](../../../docs/development-plan.md)。复用原邮件解析、推荐记录、分页及 acquisition checkpoint；先可靠收录原邮件条目和链接，再加处理标签并归档，完整JD随后取得。34初始化/恢复时采用已有收录但未处理条目；持续扫描只追加新收录项，全局处理记录去重。已有任务由其原检查点继续，已完成项不重复收录，显式skip项等待用户返回。

## Acceptance criteria

- [ ] 通过已有入口分页收录，保存原邮件标识、适用原文、每个岗位条目、链接和可继续位置；不等待完整JD才能保存邮件。
- [ ] 本地收录完整且原子保存后，才执行用户指定的处理标签及archive；崩溃/重开不会把未收录条目的邮件当已处理。
- [ ] 标签/归档失败或结果不明时，保留本地条目并先核对邮箱实际状态；不重新分析、重复入队或丢失原邮件关联。
- [ ] 初始化/恢复把既有已收录未处理条目纳入主编排，持续仅追加新条目；同邮件重读、相同条目、重复链接与已完成岗位可靠去重，同公司不同岗位不误合并。
- [ ] JD延后抓取，单项失败保留链接和原因；恢复复用已保存内容。来源原文与摘要、完整JD与未取得内容明确区分。
- [ ] API分页大小可有界，但没有固定邮件/岗位总量或20分钟总轮上限；只有读完当前新收录范围、用户暂停或实际故障才结束该阶段。
- [ ] 界面分别显示本地收录、label/archive和JD获取的实际状态，失败只补做对应步骤；持续收录不禁用查看已存任务。
- [ ] 合成邮箱覆盖保存前失败、保存后未归档、归档结果不明、下一页中断、已有未处理条目恢复、重复读取和JD失败；测试不修改真实邮箱。

## Ownership and reuse

`application_gmail.py`、`application_intake.py` 及现有推荐存储/测试；不另造收件箱平台或申请状态库。34消费新增条目，36管理个人事实。多人修改先协调，不撤回现有工作。

## Publication boundary

本票是当前设计的待实施后继，不是已执行邮箱操作。Status=open、Assignee=none；本次只发布规划，不启动Gmail、模型或真实申请。标签名称取用户配置/规范，不能臆造新的业务偏好。

## Implementation started — 2026-10-20

用户已授权按当前spec开始系统精简。仅使用合成工作区实施与验证；保留既有材料、进度、人工修改和历史证据。最终Submit由用户操作。源码与测试恢复副本：`/private/tmp/tomorrowstar-simplification-20261020/before-source-tests-tickets.tgz`。

## Backend slice implemented — 2026-10-20

Status remains `claimed`; the complete ticket is not accepted.

- Added `ApplicationIntakeService.refresh(capture_only=True)`. It atomically imports mail and recommendation links before any JD fetch or extraction, automatically drains bounded API pages, persists cursors, detects repeated cursor cycles, and retains existing unselected recommendations for the orchestration consumer. Duplicate job IDs merge source associations across messages and scans.
- Optional constructor configuration `processed_label` supplies the user-selected label; no label name is invented. Separate durable message checkpoints track labeling and archive. Unknown outcomes first inspect the mailbox; successful operations are confirmed by readback. Archive removes only the captured message's `INBOX` label, so uncaptured messages in the same thread are not hidden.
- The connector adapter verifies actual tool traces and exact message/label arguments. Model completion claims alone do not prove a mailbox result. Local checkpoint failures stop further external operations. Incomplete bodies remain saved and are not labeled or archived.
- Snapshot progress exposes local captured-message, labeled, archived and needs-recheck counts separately from JD acquisition counts. Mail IDs and processing checkpoints remain private.
- Synthetic coverage includes save-before-import failure and retained-read replay, unknown archive outcome without repeated archive, pre-action checkpoint failure preventing subsequent external actions, next-page interruption with cursor recovery, preexisting pending jobs, duplicate recommendation sources, and incomplete bodies. Existing JD-failure/reconciliation regressions remain green.

Validation (checkout source, no live mailbox/model/browser/private-workspace calls):

```sh
UV_CACHE_DIR=/private/tmp/tomorrowstar-uv-cache uv run --locked --offline --no-sync python -B scripts/run_pytest.py -q tests/test_mail_capture.py tests/test_application_intake.py tests/test_intake_continuation.py tests/test_application_gmail.py tests/test_capture_intake_http.py
# 128 passed
UV_CACHE_DIR=/private/tmp/tomorrowstar-uv-cache uv run --locked --offline --no-sync ruff check --no-cache src/career_evidence_graph/application_gmail.py src/career_evidence_graph/application_intake.py tests/test_mail_capture.py tests/test_application_gmail.py
# All checks passed
```

Remaining acceptance work: native configuration must supply the label, the visible UI must render the separate progress states, ticket34 must adopt capture mode and defer JD acquisition to the current sequential job, and normal reopening must automatically resume a healthy capture checkpoint. Legacy `refresh()` retains its historical bounded fetch behavior until its callers migrate. Historical captures without the new mailbox checkpoint still need scoped migration/readback before archive. This backend/API slice does not establish installed-App or real-mail acceptance. Final Submit remains manual.

### Review corrections — 2026-10-20

Two synthetic review reproductions found concrete preservation defects; both were first reproduced with failing public-interface tests and then fixed:

- Mail checkpoints now use mailbox identity plus message ID. Active-account progress and cleanup select only that account's checkpoints. Identical IDs in another mailbox cannot inherit completion or an unknown outcome; previous-account checkpoints remain intact. Captured messages and source associations retain an optional validated mailbox digest, so same-ID/same-body mail from two verified accounts retains distinct original capture hashes. Historical unbound sources are not assigned an invented account.
- A summary-only recapture now preserves `documentary_fields` alongside the existing full JD, including deadline and employment type.

Expanded affected regression run (the prior command plus `tests/test_application_recommendations.py`): **198 passed**. Touched-file Ruff lint and format checks passed for the Gmail/intake/recommendation modules and their modified/new tests. These are offline synthetic checks only.


## Notes — 持续主线源码后继 2026-10-21

主线复用现有分页 capture 和 RecommendationStore，不再受首次三封 / 十候选总额限制；当前岗完整 JD 延后获取，等待时按现有轮询收录并去重。16 封 / 16 候选及等待页保持已有合成回归；真实邮箱标签 / 归档结果仍未验。

完整默认离线：4263 passed, 2 skipped, 428 deselected in 661.45s (0:11:01)；[工程记录与原日志](../../automatic-mainline-2026-10-21/README.md)。旧三项 P2 的独立冻结记录及全部失败历史保留。Status、Assignee、依赖、既有勾选均不变，不新增票、不关闭本票；App 未更新，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 必要材料、路由与恢复后继 2026-10-21

恢复核验 pending 和当前岗等待期间仍仅允许邮件收录，不推进下一岗或执行表单动作。本轮只使用合成 Intake/队列和本地存储，不读取真实 Gmail，不执行真实标签或归档。

完整默认离线：4440 passed, 2 skipped, 460 deselected in 718.67s (0:11:58)；受影响离线 1097 项、本地浏览器 164 项均通过。[工程记录、失败历史及冻结输入](../../product-completion-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 可用优先重排 2026-10-21

只把native标签配置与状态UI实现明确委托新源码子票，账号/保存/归档收据及原验收仍由本票持有。

本票继续持有邮箱后端及整体验收；配置与默认进度的唯一实施细节已委托[接通邮件处理设置与独立进度展示](42-mail-processing-settings-status.md)，不重复实现。完成该源码票不代表本票真实邮箱已接受。

Priority/Triage/票头依赖按本次重排更新；旧边与原字节见[审计及变更账本](../../usable-first-wayfinder-audit-2026-10-21/README.md)。原 Status、Assignee、Interaction、既有验收勾选及全部旧正文保持，不领取、不关闭、不替用户接受。源码接口依赖不等于安装或真实操作许可；App 未更新，真实申请继续暂停。

## Source handoff from 42 — 2026-10-21

[42号有限源码票](42-mail-processing-settings-status.md)已完成配置/启动接线、坏配置局部隔离与默认邮件独立进度；[交付与回归收据](../../mail-settings-implementation-2026-10-21/README.md)和[同一主App最小安装验收准备](../../mail-settings-implementation-2026-10-21/minimal-installed-journey.md)可直接消费。完整默认离线4597通过/2跳过；额外合成浏览器43通过。保留本票状态、负责人、原验收和历史；本票整体验收仍由原负责人承接。App更新、真实邮箱及真实申请继续暂停。
