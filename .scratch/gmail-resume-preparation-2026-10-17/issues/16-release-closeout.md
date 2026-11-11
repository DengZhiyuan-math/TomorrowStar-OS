# 接受准备版并记录剩余边界

Type: task
Label: wayfinder:task
Status: open
Triage: awaiting-real-acceptance
Priority: P2
Interaction: HITL
Assignee: none
Created: 2026-10-17
Updated: 2026-10-19
Parent: [交付 Gmail 岗位筛选与专用简历稳定版](../map.md)
Publication order: 13
Blocked by: [复核已接受材料的限定真实试点](15-real-preparation-pilot.md)、[在安装版验收真实新岗位完整简历生成](25-installed-real-job-full-cv.md)

**What to build:** 用户核对实际版本、材料质量与恢复办法，作出准备版接受或剩余问题决定。

## 当前产品计划定位 — 2026-10-20

保持产品质量接受及材料25直接前置。普通岗位依已有事实自动生成、技术检查和使用材料，不再要求逐组或每个新PDF人工批准；高价值岗位初稿后进入精准人工处理。用户可用同一真实流程评价材料质量、速度和恢复；其产品接受不等于逐份材料运行批准。旧接受/失败收据不改写，真实质量尚未通过不能自动代答。

以[当前产品规范](../../../docs/single-job-flow.md)和[唯一开发计划](../../../docs/development-plan.md)为当前执行依据；本节替代下方与之冲突的旧产品门槛，研究自身接受标准除外。Status、Assignee/未知owner、原依赖、历史勾选与收据均保留；本次只规划，没有执行或结案。

## Acceptance criteria

- [ ] 分开列出工程、合成、renderer、安装与真实人审证据。
- [ ] 记录用户实际接受的版本、限制和未完成问题，不能自动代替用户关闭。
- [ ] 材料15和19原结案有效且不重开；材料25完成当前新岗位正常生成、真实编译、具体材料人审及普通批次暂停／冷重开验证后，才对本票的日常自动生成范围作整体接受。不能用既有已接受材料导入代替该前置。
- [ ] 既有事实及同一PDF接受直接引用原回执，不要求重新确认；本次新材料仅按其准确源／PDF版本审阅。保留原同一真实流程的材料、速度、接管与恢复要求，ATS和浏览器体验仍由原票各自验收。
- [ ] 自动投递、历史原生根因和职业图接受仍独立；本次发布操作不修改或关闭父issue。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Current scope — 2026-10-19

材料15已在限定真实复用范围结案，材料19已在独立安装合成范围结案；下方旧“三项HITL”“尚未安装”是历史时点。本次按用户批准的方案将材料25接为正式前置，以补齐日常新岗位自动生成及普通批次证据。本票不因依赖发布而完成，仍open／needs-info／none。材料25不等待本票或旧ATS票，查询维护26不阻塞本票。

## Comments

### 2026-10-18 — Current ticket reconciliation

Prism 与已有 LaTeX 的后继工程已安装验证；下方“尚未安装”保留为历史。本票依据已核对的当前候选与用户真实材料接受作准备版决定，不把任何旧候选通过数当当前接受。三项HITL可在同一真实流程中分段审阅，各自记录结论；本图只关闭材料准备范围，浏览器体验和旧申请根因仍独立。若后继产品契约需要实现或补验，先完成[当前候选整链核对](19-current-candidate-journey.md)及其前置。

### 2026-10-18 — Acceptance uses the same real workflow

用户要求三项HITL基于同一条真实岗位到提交前复核的流程作判断。准备版接受须引用该真实流程的材料和实际安装版本，并记录速度、接管和剩余问题；不得以隔离合成通过替代用户体验或材料接受。参考样式已在源码适配，尚未安装。真实外部写入及最终Submit未执行，旧未知任务继续停止。本票保持open。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/13-preparation-acceptance.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/gmail-resume-preparation-2026-10-17/issues/16-release-closeout.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。

## Parallel execution group — 2026-10-20

[F — 新岗位材料与准备版接受](../../open-ticket-parallel-plan-2026-10-20/README.md#f-materials)。跨票顺序、共享文件及原生实验串行约束见统一分组导航；本票状态、原领取、依赖与验收仍按上文执行。本次仅重组导航，不领取或扩大执行许可。


## Notes — 可用优先重排 2026-10-21

材料接受仍由用户决定，不把产品接受变成逐份普通材料批准。

Priority/Triage/票头依赖按本次重排更新；旧边与原字节见[审计及变更账本](../../usable-first-wayfinder-audit-2026-10-21/README.md)。原 Status、Assignee、Interaction、既有验收勾选及全部旧正文保持，不领取、不关闭、不替用户接受。源码接口依赖不等于安装或真实操作许可；App 未更新，真实申请继续暂停。
