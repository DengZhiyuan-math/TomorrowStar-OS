# 复核已接受材料的限定真实试点

Type: task
Label: wayfinder:task
Status: closed
Triage: done
Closure reason: completed
Completion: bounded-real-pilot-dedup-and-accepted-material-batch-verified
Priority: P1
Interaction: HITL
Assignee: 01a150ef/root
Created: 2026-10-17
Updated: 2026-10-19
Parent: [交付 Gmail 岗位筛选与专用简历稳定版](../map.md)
Publication order: 12
Blocked by: [在安装版运行完整合成准备流程](14-installed-preparation-acceptance.md)、[核对当前安装候选的完整材料准备链](19-current-candidate-journey.md)

**What to build:** 在原批准单样本范围内复用既有事实与精确源／PDF接受，验证固定范围双读去重及已接受材料暂停批次的建立、幂等和冷重开。

## Completion scope — 2026-10-19

本票继续closed／done，原领取、完成标识、勾选项及完成证据不变。结案不覆盖新岗位自动完整CV、真实新源编译或普通后续批次生成；这些由正式后继[在安装版验收真实新岗位完整简历生成](25-installed-real-job-full-cv.md)承接。已有事实及同一PDF的用户接受直接复用，不重新审核、不修改原unknown。后续普通准备版整体接受仍由[材料16](16-release-closeout.md)负责。原标题及目标保存在[发布前原文](../../ticket-successors-2026-10-19/before/.scratch/gmail-resume-preparation-2026-10-17/issues/15-real-preparation-pilot.md)。

## Acceptance criteria

- [x] 用户实际确认账号/资料范围、试用样本与每份PDF的内容，不由代理推断接受。
- [x] 无全文、待确认及失败均计入试用结果；重复更新不重复生成。
- [x] 验证后续批次可按已记录办法使用；需要开发者介入的例外明确保留。当前验证限已接受材料的批次建立、复用、幂等和冷重开；新岗位自动生成及普通后续批次保持未验。
- [x] 保持邮箱只读、真实申请暂停；本票不授权发送、上传或最终提交。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Comments

### 2026-10-19 — Bounded real pilot completed

按用户本轮明确要求，复用已有事实与精确 PDF 的真实接受记录，完成固定范围、有限真实邮件页的双次读取去重。推荐身份及来源保留，未新增申请、任务、生成或编译；无全文、失败及未知结果均留在私人清单。当前 Gmail 字段兼容问题已修复，首次失败原件保留。

安装版已将原用户决定登记为独立材料接受回执，并直接建立已接受材料的暂停批次。同请求与新重复请求都复用原批次；冷重开后任务、接受回执、请求、批次及 PDF 相同，不恢复读取或执行。未重复确认事实或同一 PDF。

本票按原批准单样本的限定真实试点结案。后续可用性只证明既有已接受材料的建立／复用／幂等／冷重开；未读邮件页、新岗位自动 CV 及普通后续批次生成链未验。原未知导出继续硬性阻止执行，例外已明确保留。材料16与浏览器HITL继续开放，真实申请、填写、上传及Submit继续暂停。见[真实试点结案](../../material15-real-batch-2026-10-19/README.md)。

### 2026-10-19 — Exact PDF accepted, saved and bound

用户明确接受此版 PDF 内容和排版，并要求保存、绑定 App／Prism。精确版本和原答复已保存在私人审核包；安装版已采用相同源的严格审阅快照，回读 PDF 字节与接受版本一致。此次采用不重新生成或编译。原未知导出与旧暂停记录保持原字节，复用采用单独回执；技术路径的待审核字段不代替本次独立保存的真实人工接受，也不要求重复确认同一材料。

历史完整／无全文、待确认、已知失败与未知停点已计入私人清单；推荐身份去重有保存结果，但当前新版真实刷新不重生成和后续批次可用性仍未完成。显式重生成历史不能当成刷新重复故障。此票继续claimed／needs-info，保留同一领取人；材料16与浏览器HITL不自动关闭。见[保存、绑定及剩余范围](../../material15-accepted-binding-2026-10-19/README.md)。真实申请、填写、上传与Submit继续暂停。

### 2026-10-18 — Current ticket reconciliation

最新工程事实已由[统一审核清单](../../tomorrowstar-delivery-2026-10-17/review-queue.md)校正：完整 LaTeX／PDF 已导出，Prism 回读、变更提示、已有 LaTeX 技术导出和刷新优化均已有安装证据；下方“未导出”等是较早时点。技术核验不等于事实审核、材料确认或当前完整生成路径已交付。

本票只持有同一真实流程中的资格、来源、完整英文 CV 和具体 PDF 的用户审核；选岗比较范围与资料覆盖由[资料核验](17-source-coverage-and-job-selection.md)提供，完整 CV 产品路径由[审核契约](18-full-cv-review-contract.md)确定。可以先讨论或审阅已有材料；关闭须满足当前候选整链前置。真实 ATS 写入／附件回读仍只由[唯一真实单岗验收](../../single-job-application-flow-2026-10-16/issues/11-gmail-real-job.md)持有，不另建同义试点。保持 open／needs-info／none，用户接受仍延期。

### 2026-10-18 — Reuse confirmed records and validate one real workflow

用户要求复用既有简历、经历库和信息库，并参考既有简历样式。扩展核对发现已确认资料，纠正此前仅查所选问答库而误报事实缺失的问题；私人旧待补充记录保留为历史，当前以新来源核对为准。已打开真实岗位和真实ATS表单作只读核对，已生成逐来源英文草稿和HTML预览，首尾版式已检查；私人审核包已保存并读回核对。未导出PDF。没有个人字段填写、上传、同意隐私或Submit；没有恢复历史未知任务。用户要求三项HITL用同一条真实工作投递流程验收，合成检查只作工程回归证据。草稿内容、具体PDF与后续外部动作的接受仍待实际材料；本票保持open。

### 2026-10-18 — Read-only pilot preparation retained privately

在已确认范围内先查现有岗位/分析快照和App现有通用信息库，不启动真实邮箱、岗位来源、模型或申请。现有证据不足以确认跨岗位最高匹配及当前适用必需资格；待补充和历史来源定位已保存至所选私人职业资料reports。没有生成新真实简历/PDF，没有改写或恢复旧任务、复用历史材料批准；不把历史匹配区间当作当前或全局排名。私人细节不复制到公共tracker。本票继续open/needs-info/none，用户实际材料接受仍延期，见统一审核清单。

### 2026-10-18 — Pilot scope confirmed; review deferred

用户已明确确认：使用App当前已连接的邮箱和职业资料，先准备1个最匹配岗位的真实英文简历供审阅；邮箱只读、不投递，真实申请继续暂停。随后用户要求把审核内容统一留下，稍后统一审核，先继续完善功能。具体材料可按已授权范围准备；本票保持open／needs-info／Assignee none，不代替用户作内容接受。审核资产与未决事项统一登记在[待审核清单](../../tomorrowstar-delivery-2026-10-17/review-queue.md)。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/12-real-material-review.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/gmail-resume-preparation-2026-10-17/issues/15-real-preparation-pilot.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。

### 2026-10-19 — Human review started with retained real materials

用户明确要求开始本票，先展示已有真实推荐、资格依据及待审简历／PDF，并逐项核对确认，真实申请继续暂停。直接安装前置均已closed，原票未领取，由`01a150ef/root`领取并保留needs-info。先只读核对现存私人记录与精确材料版本，不刷新邮箱、不重新生成／编译、不修改原任务或复用旧批准；逐项用户答复及来源绑定仅保存在私人审核记录。当前尚无新的材料接受、资格确认或整票完成，原真实单岗及其他HITL保持原状态。
