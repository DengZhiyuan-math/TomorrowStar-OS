# 补齐一个确有HTTP缺口的只读JD来源

Type: task
Label: wayfinder:task
Status: closed
Triage: resolved
Completion: conditional-no-browser-source-admitted
Priority: P2
Interaction: AFK
Assignee: 01a14a95/root
Created: 2026-10-17
Updated: 2026-10-18
Parent: [交付 DOM 优先的受控浏览器效率改进](../map.md)
Publication order: 23
Blocked by: [将候选转成可核验的完整岗位](../../gmail-resume-preparation-2026-10-17/issues/04-job-source-checkpoints.md)

**What to build:** 在一个已证实普通HTTP无法完整获取的来源上，用现有浏览器取得可核验JD；没有必要则明确不实施。

## Acceptance criteria

- [ ] 由完整JD切片提供具体缺口证据；不把所有来源统一改走浏览器。
- [ ] 同一用户入口可查看原文、公司/岗位身份、来源和获取时间；登录墙、JS延迟、摘要与错岗正确处置。
- [ ] 只读获取保留网络/URL边界，不复制登录凭据，不将不完整内容标成完整。
- [x] 不可用时已有完整JD仍能生成材料；不阻塞浏览器快速路径安装或其他来源批次。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Comments

### 2026-10-18 — Conditional resolution: no current concrete source gap

[必要性判断与验证](../../browser-efficiency-execution-2026-10-18/job-source/README.md)：前置source-gaps库存只有历史脱敏观察和合成失败，没有具体、当前的HTTP缺口URL。按What to build的“没有必要则明确不实施”分支，不新增浏览器适配器或通用回退；不是声称所有当前岗位HTTP均可取全。出现具体当前HTTP缺口即可重开并进行有界只读可恢复性探测，不要求先已有成功browser实现/完整捕获。

原生浏览器取源未触发，因此前三项描述新增获取行为的验收不适用，保留未勾选以免虚构实现。既有HTTP JSON-LD/窄静态HTML路径及完整JD继续工作；身份、全文/硬资格、时间来源、登录/JS-cookie墙、过期、网络/响应边界、失败岗位不丢已完成项与材料入口不启动填写器的现有回归共98 passed。没有生产改动、真实邮箱/岗位页请求或凭据复制；不可用来源不阻塞其他材料及浏览器快速路径。独立审查无阻断，条件性结案，真实申请继续暂停。

### 2026-10-18 — Execution claim

用户授权继续全部剩余票；前置已回读，由 `01a14a95/root` 领取。先以当前证据检验必要性和公共API；条件不成立时明确记录不实施，不引入推测性能力。只运行新归属合成资源，真实申请继续暂停。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/23-optional-browser-job-source.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/browser-efficiency-2026-10-17/issues/10-readonly-browser-job-source.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。
