# 在推荐列表中继续读取Gmail

Type: task
Label: wayfinder:task
Status: closed
Triage: done
Closure reason: completed
Completion: source-and-synthetic-verified
Priority: P0
Interaction: AFK
Assignee: 01a14a95/root
Created: 2026-10-17
Updated: 2026-10-17
Parent: [交付 Gmail 岗位筛选与专用简历稳定版](../map.md)
Publication order: 03
Blocked by: [打开独立材料准备入口](02-preparation-only-runtime.md)

**What to build:** 用户手动更新推荐，查看读取范围和进度，并在分页、限额或连接失败后继续。

## Acceptance criteria

- [x] 至少两页、重复消息、跨页去重、断连和限额都有合成端到端示例。
- [x] 账号、查询或时间窗口变化使旧cursor失效；消息内多岗位、正文截断及未读范围保留续点或明确待处理。
- [x] 列表显示完整、未完成与失败范围；断连不能显示为已读完或无岗位。
- [x] 只读邮件；正文、账号、cursor及私有URL不进入公开日志。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Comments

### 2026-10-17 — Resolution: source and synthetic continuation verified

推荐列表可手动指定并固定 UTC 范围，保存私有 cursor、已读消息、待取源候选和未完整／未读范围。续读先完成已保存候选，再读取后续页；跨页重复消息不重复计数，已完成岗位不重复取源。限额、断连和截断保留明确未完成状态，空后页不能抹掉前页未读范围。

每次邮件页之前，独立只读 profile 阶段核验实际 Gmail 身份，再允许搜索／读取。账号、查询、窗口或本地连接上下文变化时拒绝旧续点；账号变化清除旧 cursor，要求重新更新。查询使用 Unix 秒数表达 UTC，避免 Gmail 日期字符串的 PST 解释。UI 只接收范围、计数和核验布尔，不接收账号摘要或 cursor；原文、私有 URL、工具 trace 和消息标识保留在私有运行目录。

- [最终验证与源码指纹](../../gmail-source-continuation-2026-10-17/verification.json)：完整离线 **2209 passed / 200 deselected**；受影响 **374 passed**（包含在完整离线内）；新旧合成浏览器 **18 passed**。Ruff、JavaScript 语法、diff 和文档链接检查通过。
- [续读与恢复反例](../../../tests/test_intake_continuation.py)、[HTTP 权限／续点边界](../../../tests/test_intake_continuation_http.py)与[合成浏览器流程](../../../tests/test_intake_continuation_browser.py)覆盖两页、重复、断连、限额、多岗、截断、未读及账号切换。
- [独立审查](../../gmail-source-continuation-2026-10-17/review.json)发现的重定向队列、未读范围、来源身份和账号核验问题均已修复。UTC 修正先出现回归失败，再通过验证；中止的早期完整运行原件保留，未算作通过。

本票关闭范围为源码与合成验收。未读取真实邮箱、调用真实模型、取得真实岗位页面、启动真实 App、替换安装版或执行 ATS／上传／最终 Submit；没有 commit、暂存或远端写入。真实申请继续暂停，安装和真实质量验收仍属后继票。

### 2026-10-17 — Implementation claim

用户明确要求本轮完成 Gmail 续读与完整岗位取源两票，覆盖本图默认单票会话限制。已确认材料入口前置 closed；由 `01a14a95/root` 领取本票。采用合成邮件、页面与假连接器完成实现和验收，不执行真实邮箱、模型、ATS、申请或上传。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/03-gmail-continuation.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/gmail-resume-preparation-2026-10-17/issues/03-gmail-incremental-paging.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。
