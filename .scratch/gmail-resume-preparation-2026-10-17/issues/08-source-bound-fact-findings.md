# 生成并审阅单岗简历草稿

Type: task
Label: wayfinder:task
Status: closed
Triage: done
Closure reason: completed
Completion: source-and-synthetic-verified
Policy version: preparation-policy/v1.0
Priority: P1
Interaction: AFK
Assignee: 01a14a95/root
Created: 2026-10-17
Updated: 2026-10-17
Parent: [交付 Gmail 岗位筛选与专用简历稳定版](../map.md)
Publication order: 06
Blocked by: [查看单岗的解释性分级](06-grading-projection.md)

**What to build:** 用户为一个合适岗位生成并审阅草稿，能查看原文与改写差异、事实提示和责任归属。

## 当前契约定位 — 2026-10-20

保留原文、改写、责任及来源；普通岗不强制逐组事实审核，重要缺失/冲突才问，高价值稿保留精准人工处理，34/36承接。

当前产品规范与执行顺序分别见[单岗位流程](../../../docs/single-job-flow.md)和[统一开发计划](../../../docs/development-plan.md)。本票既有Status、Assignee、完成记录和收据不变；关闭仅证明当时范围，不证明新规范已实现。下方与现行规范冲突的旧审批、白名单、总时间窗及运行门槛保留为历史，由现有后继承接，不重开、不追认，也不据此执行真实申请。

## Acceptance criteria

- [x] 默认生成英文草稿；岗位明确要求其他简历语言时先提示并等待单独处理，不静默沿用英文或自动改写其他语言。
- [x] 草稿绑定实际JD、资料和生成配置；生成结果有明确可审阅状态，并先持久化再进入导出。
- [x] 数字、日期、技术词及逐来源事实差异可见；用户、团队、他人、Codex辅助工作归属不升级。
- [x] 空选材诚实停在材料不足；不靠JD关键词或缺失事实生成不存在的经历。
- [x] 输入变化或晚返回不能把旧草稿重新采用；模拟模型与真实内容人审结果分开记录。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Comments

### 2026-10-17 — Resolution: independently reviewable single-job draft verified

准备模式现在复用当前已采用的岗位分析选材，默认生成英文草稿并先保存独立 `draft.json`，不自动导出 PDF。草稿具有 `draft_ready` 状态，绑定实际 JD、完整来源快照、分析、生成配置及本次准备输入；保存后可只读重开，不重复模型或导出。明确其他简历语言要求显示原句并暂停，等待单独处理；语言能力、文件格式与版式要求分别识别，纯英文或可任选英文的要求保持默认英文。语言识别是有界规则，真实岗位变体仍须真实试用复核。

页面逐来源对照原文、改写、责任归属、范围边界、已采用／未采用来源，以及数字、日期和技术词新增／遗漏。提示明确属于机械差异且术语扫描有限，不能冒充语义事实验证。已有归属与设计／实现保护继续生效；空选材、无合格个人来源或空模型内容停在材料不足，不回退为 JD 关键词重选或虚构经历。

显式“记录本版草稿审阅”绑定当前版本、确切字节、分析和输入，记录用户动作与模型环境，并追加审阅历史。同步输入、重新生成或更正资格使当前审阅失效，旧草稿与审阅记录保留。取消、资料／资格变化后的晚返回不能重新采用；损坏草稿、同时篡改草稿与其完整性文件、跨岗位串用均被拒绝。草稿审阅不确认 PDF、不授权投递，也不代表真实内容已通过人审。

- [最终验证与源码指纹](../../single-job-draft-2026-10-17/verification.json)：最终冻结版本完整离线 **2353 passed / 208 deselected**，沿用仓库默认排除规则；针对性 **157 passed / 2 deselected**（包含在完整离线内）；浏览器兼容 **26 passed**，最后仅语言规则修复后，受影响草稿路径再验 **4 passed**。后四项是前26项的子集复验，不合计为30个不同场景。Ruff检查、238文件格式、JavaScript语法、diff与文档链接检查通过。
- [来源绑定、语言和草稿检查点](../../../tests/test_resume_drafts.py)、[审阅历史与晚返回](../../../tests/test_draft_flow.py)、[真实loopback版本／完整性／跨岗位保护](../../../tests/test_draft_http.py)和[草稿用户路径](../../../tests/test_resume_draft_browser.py)已验证。旧申请 PDF 流程测试保持原字节；准备入口两例按本票的新草稿契约更新，旧 PDF 申请模式继续独立覆盖。
- [独立审查与修复](../../single-job-draft-2026-10-17/review.json)：语言声明漏判、格式误拦、复数／前置多语言列表和审阅历史保留均已修正；最后复核无尚未解决的必改项。
- [首轮版本不一致记录](../../single-job-draft-2026-10-17/loaded-version-diagnosis.json)：首轮全套启动后补了最后语言修复，长驻父进程与新子进程的引擎版本校验不一致，保留 **1 failed / 2350 passed** 的原始日志，未作为验收。冻结后该项单独复验及最终全套均通过，没有放宽版本保护。
- [本票基线、变更及证据导航](../../single-job-draft-2026-10-17/README.md)保存本票变更；最终15项源码指纹一致。

本票关闭范围为源码与合成验证。真实邮箱／模型／岗位页面／ATS／上传／Submit 均为零，未启动 TomorrowStar App，未替换安装版，未暂存／提交或远端写入，真实申请继续暂停。后继「导出可信PDF并单独重试导出」解除本前置，但本轮不自动领取；实际 renderer 质量、安装版及真实材料人审仍由各自票据持有。

### 2026-10-17 — Implementation claim

用户明确要求继续完成本票实现、验证和回写，真实申请继续暂停。已回读唯一前置「查看单岗的解释性分级」为 closed / source-and-synthetic-verified，由 `01a14a95/root` 领取。本轮复用现有单岗生成器，按 `preparation-policy/v1.0` 实现默认英文、其他明确简历语言要求先提示、来源绑定草稿、事实差异与责任归属审阅、空选材停止及旧结果隔离。

采用隔离合成资料、假模型及本机验证；不读取真实邮箱／私人资料，不调用真实模型或岗位页面，不启动真实 App／ATS，不上传／Submit，不恢复旧申请。可信 PDF 质量与导出重试继续由后继票持有。本票的合成通过不代替真实内容人审或安装验收；保留既有脏工作与封存证据。

### 2026-10-17 — Default-language policy confirmed; implementation not started

[确认筛选与生成政策](05-preference-grading-policy.md)的 P9 为默认语言及例外提示的唯一详细决策来源。该要求已加入本票验收；仍复用已有单岗生成器。此处只更新契约，Status、Assignee 与依赖不变，不领取或实现，不声明例外路径已有验收；真实申请继续暂停。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/06-reviewable-resume-draft.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/gmail-resume-preparation-2026-10-17/issues/08-source-bound-fact-findings.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。
