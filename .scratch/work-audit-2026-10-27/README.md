# 全部票据整理 — 2026-10-27（Europe/Zurich）

只读整理。来源：`scripts/query_tickets.py --json`（[原始输出](tickets.json)）加各票票头。
未修改任何票据的 Status、Assignee、Blocked by 或正文。上一次整体审计是
[2026-10-20 工作审计](../work-audit-2026-10-20/README.md)。

## 总数

共 162 张：135 张已关闭或已解决（118 closed、17 resolved），**27 张未关闭**（20 open、7 claimed）。
查询器：0 errors、20 warnings（都是 `unknown_metadata`），机械前沿（`mechanical_frontier`）为 **0**。

27 张未关闭票分布在 6 张地图：Module 完成（10）、单岗位主流程（10）、Gmail 简历准备（2）、
浏览器效率（1）、Worker 稳定性（2）、Phase 8 职业清单研究（2）。

## 按“在等什么”分组

### A. 主线工程链（AFK，代码工作，可由 agent 推进）— 6 张

| 票 | 状态 | 等待 |
|---|---|---|
| [MC-06 T07 交付已绑定正文与附件](../module-completion-2026-10-26/issues/06-t07-bound-material-delivery.md) | claimed，实施中 | 无；剩源码冻结、候选构建、浏览器/native 验收、审查 |
| [MC-07 T08 可靠交回与填写完成](../module-completion-2026-10-26/issues/07-t08-return-and-completion.md) | open | MC-06 |
| [MC-08 T09 App 自动派发与统一控制](../module-completion-2026-10-26/issues/08-t09-app-dispatch-controls.md) | open | MC-07 |
| [MC-09 T10 新产品路径合成整链与故障验收](../module-completion-2026-10-26/issues/09-t10-synthetic-chain.md) | open | MC-08 |
| [MC-14 M5 收拢 Runtime 装配与 Portal 传输](../module-completion-2026-10-26/issues/14-m5-runtime-portal.md) | open | MC-08 |
| [MC-15 M6 后端投影、调用兼容与运行身份](../module-completion-2026-10-26/issues/15-m6-ui-compatibility-identity.md) | open | MC-14 |

这是当前唯一在动的链。MC-06 是整个 27 张里唯一正在实施的票。

### B. 需要用户另行授权的分层验收（HITL）— 4 张

| 票 | 等待 |
|---|---|
| [MC-10 T11.1 实际 Codex 与同一合成原页验收](../module-completion-2026-10-26/issues/10-t11-model-synthetic-page.md) | MC-09；需授权运行实际模型 |
| [MC-11 T11.2 唯一签名 App 新接管链验收](../module-completion-2026-10-26/issues/11-t11-signed-gui.md) | MC-10、MC-15；需授权更新/运行安装 App |
| [MC-12 T11.3 获授权真实 ATS 新接管链验收](../module-completion-2026-10-26/issues/12-t11-real-ats.md) | MC-11；需授权真实 ATS |
| [MC-16 最终 AC01–AC27 证据审计与整体验收](../module-completion-2026-10-26/issues/16-final-ac01-ac27-audit.md) | MC-09、MC-12、MC-15 |

### C. 旧地图的真实/安装验收与收尾（HITL，等用户真实操作）— 5 张

依赖链：Gmail 25 → 单岗位 11 → 浏览器效率 09 → 单岗位 12；Gmail 25 → Gmail 16 → 单岗位 12。

| 票 | 状态/负责人 | 等待 |
|---|---|---|
| [在安装版验收真实新岗位完整简历生成](../gmail-resume-preparation-2026-10-17/issues/25-installed-real-job-full-cv.md) | open，`01a15491/root` | 无开放前置；等用户在安装版做真实验收 |
| [接受准备版并记录剩余边界](../gmail-resume-preparation-2026-10-17/issues/16-release-closeout.md) | open | Gmail 25 |
| [通过 App 用 Gmail 真实岗位验证至人工提交前](../single-job-application-flow-2026-10-16/issues/11-gmail-real-job.md) | open，`01a146b9/root` | Gmail 25 |
| [确认浏览器速度与人工接管体验](../browser-efficiency-2026-10-17/issues/09-browser-efficiency-acceptance.md) | open | 单岗位 11 |
| [核对交付范围并关闭单岗位主流程地图](../single-job-application-flow-2026-10-16/issues/12-delivery-closeout.md) | open，`01a146b9/root` | 浏览器效率 09、Gmail 16、单岗位 11 |

整条链的源头是 **Gmail 25**，它没有开放前置，只等用户做真实验收。

### D. 旧单岗位地图的源码后续（AFK，前置都已关闭）— 7 张

| 票 | 状态/负责人 | 与 Module 新链的关系 |
|---|---|---|
| [支持已观察到的通用 ATS 自定义必填控件](../single-job-application-flow-2026-10-16/issues/18-generic-ats-controls.md) | claimed，`01a15ab3/root` | Module 地图声明平台控件仍归本票 |
| [支持 Workable 普通简历字段的受控上传与回读](../single-job-application-flow-2026-10-16/issues/20-workable-resume-upload.md) | open，`01a146b9/workable_upload` | MC-06 明确不覆盖 Workable 上传限制 |
| [支持当前岗位已确认邮箱的更正](../single-job-application-flow-2026-10-16/issues/23-current-job-email-correction.md) | open，`01a146b9/root` | 无重叠 |
| [核验 Ashby 公开初始化读取的精确请求边界](../single-job-application-flow-2026-10-16/issues/33-ashby-public-bootstrap-review.md) | claimed，`01a15ee0/root/ashby_bootstrap` | 源码已核，等真实验收 |
| [接通邮件到人工最终确认的后台流程](../single-job-application-flow-2026-10-16/issues/34-email-to-review-pipeline.md) | claimed，`01a15926/root` | 真实自然 Submit 闭环；与 MC-08/09 相邻 |
| [增量保存邮件岗位后标记归档并延后取得JD](../single-job-application-flow-2026-10-16/issues/35-mail-capture-label-archive.md) | claimed，`01a15ab3/root` | 无重叠；最后更新 10-21 |
| [复用两库事实并按影响保存更正与更新](../single-job-application-flow-2026-10-16/issues/36-information-reuse-impact-updates.md) | claimed，`01a15ab3/root` | 资料影响更新仍归本票 |

### E. 延期诊断（AFK）— 3 张

| 票 | 负责人 | 备注 |
|---|---|---|
| [调查 Cua 冷启动前置窗口阻断](../application-worker-stability/issues/07-cold-start-prewindow-investigation.md) | root | deferred-diagnostic，10-21 后无更新 |
| [调查 CuaDriver 0.35 后台浏览器附着拒绝](../application-worker-stability/issues/10-cua-035-background-attach.md) | root | 等 App 更新 |
| [复现并修复 Chrome 原生启动崩溃](../single-job-application-flow-2026-10-16/issues/26-native-chrome-startup-crash.md) | `01a155fd/root` | deferred-diagnostic，10-21 后无更新 |

### F. 研究线 Phase 8（HITL，需要用户本人）— 2 张

| 票 | 状态 | 等待 |
|---|---|---|
| [Reconcile Ambiguous, Excluded, and Unresolved Career Items](../phase-08-career-experience-inventory/issues/07-reconcile-ambiguous-excluded-and-unresolved-items.md) | claimed（历史 owner 未核实），grilling | 无开放前置；需用户参与 |
| [Seal the User-Accepted Inventory Revision](../phase-08-career-experience-inventory/issues/09-seal-the-user-accepted-inventory-revision.md) | open | 上一张 |

两张都明确不阻塞申请产品。

合计：A 6 + B 4 + C 5 + D 7 + E 3 + F 2 = 27。

## 发现的问题

1. **机械前沿为 0，但有 11 张票没有开放前置。** 原因是它们要么已被认领/指派，要么是 HITL。
   所以除了 MC-06 的负责人，没有任何 agent 能按规则自动接手工作。
2. **疑似过期的认领：** D 组 7 张、单岗位 26、Gmail 25、单岗位 11/12，共 11 张票挂在旧会话 ID 下
   （`01a146b9`、`01a15ab3`、`01a15ee0`、`01a15926`、`01a155fd`、`01a15491`），最近更新在 10-21 至 10-26。
   这些会话是否还在运行没有核实；如果已结束，它们会一直挡住前沿。
3. **Phase 8 和两张旧地图的票头字段查询器不认识**（20 条 `unknown_metadata`：Phase 8 10 条、
   Worker 稳定性 6 条、候选技能 harness 4 条）。Phase 8 07 写着 `claimed` 但没有 Assignee。
4. **MC-06 票的“文件所有权”不全**：实际还改了 `cua_driver.py`、`application_codex_assist.py`、`ashby_drafts.py`。
5. **`module-completion-2026-10-26/current-handoff.md` 已过时**：仍写 MC-06“尚未开始实现”。
6. **旧地图收尾全挂在一张 HITL 票上**：单岗位地图、Gmail 准备地图、浏览器效率地图都要等 Gmail 25 的真实验收才能关。

## 建议的整理动作（需用户决定，本记录未执行）

1. 核实第 2 条中的旧会话；已结束的，把票改回 `open`/`none` 并在 Comments 记录释放原因，让它们回到前沿。
2. 判断 D 组是否并入 Module 新链（尤其 20 Workable、34 自然 Submit），还是继续作为独立票保留。
3. 让查询器认识 `Type`/`Claim state` 字段，或统一这三张地图的票头格式。
4. 同步 MC-06 文件所有权和 `current-handoff.md`。
