# 材料准备稳定版执行导航

> 当前规范与唯一执行计划（2026-10-20）：[产品规范](../../docs/single-job-flow.md) · [开发计划](../../docs/development-plan.md) · [系统审计](../../docs/system-audit-2026-10-20.md)。
> 本目录票仍保持原状态/领取及原证据。当前产品采用普通自动材料、高价值精准人工、两库复用和按影响更新；逐份材料批准和旧批次预算只保留历史。下方旧路线不是第二套当前计划。 本次仅重规划，未改Status/Assignee、未执行真实申请。

2026-10-19 当前：材料26全量只读查询已结案，执行者01a15491/root保留；本图26张子票中2张开放，分别为25真实新岗生成验收及等待25的16整体接受。旧票领取、材料15／19结案与证据保持，真实申请继续暂停。使用[实时只读查询](../open-ticket-audit-2026-10-18/README.md#查询与检查)，详见[执行与保全记录](../complete-tracker-query-2026-10-19/README.md)。

## 本轮后继与执行顺序

26已完成查询修复，不阻塞材料25。25只在具体岗位、资料及模型／编译范围另获明确许可后执行，普通批次完成当前一岗即停在waiting_application_record，不自动下一岗。25通过后仍需用户对16整体准备版作决定；旧ATS及浏览器人审保持原独立门槛。

## 发布前审计时点

以下首段和历史记录保留新增两票前的时点；实时状态以子票和最新发布记录为准。

2026-10-19 最新：材料19安装合成整链和材料15限定真实试点均已closed。本材料线只剩[16准备版整体接受](issues/16-release-closeout.md)；浏览器09另待真实体验。已有事实与同一PDF接受直接复用，真实申请继续暂停。最新统计和归属见[当前工作审计](../work-audit-2026-10-19/README.md)。

## 历史执行记录

以下段落保留各自交付时点；其中“当前”“下一步”和旧三项HITL不作为实时状态。子票保持唯一状态来源。

2026-10-19 最新：[完整LaTeX独立安装整链验收](../material19-installed-journey-2026-10-19/README.md)完成，[材料19号](issues/19-current-candidate-journey.md)已结案。当前两线只剩原三项HITL；下一步为[真实推荐与材料复核](issues/15-real-preparation-pilot.md)的用户参与门槛，本轮不启动。旧段落保留各自时点状态，不能据其再次领取已结案票。真实申请继续暂停。

最新执行入口：[完整LaTeX安全合成入口源码交付](#2026-10-18-完整latex安全合成入口源码交付)。下方各次交付段落保留当时的前沿，实时状态以子票为准。

2026-10-17：用户批准的纵向拆分已正式发布。当前规范导航为[23张正式交付票](../tomorrowstar-ticket-consolidation-2026-10-17/README.md)，原子票路径与领取状态保留；以下直接链接各正式子票。

本路线父地图保持原字节，作为范围与历史保留。本轮只迁移票据，不执行开发，不恢复真实申请。

| 发布序号 | 正式子票（原身份） | 交互 | 直接前置 |
| --- | --- | --- | --- |
| 01 | [打开独立材料准备入口](issues/02-preparation-only-runtime.md) | AFK | 无 |
| 02 | [确认筛选与生成政策](issues/05-preference-grading-policy.md) | HITL | 无 |
| 03 | [在推荐列表中继续读取Gmail](issues/03-gmail-incremental-paging.md) | AFK | [打开独立材料准备入口](issues/02-preparation-only-runtime.md) |
| 04 | [将候选转成可核验的完整岗位](issues/04-job-source-checkpoints.md) | AFK | [打开独立材料准备入口](issues/02-preparation-only-runtime.md) |
| 05 | [查看单岗的解释性分级](issues/06-grading-projection.md) | AFK | [打开独立材料准备入口](issues/02-preparation-only-runtime.md)、[确认筛选与生成政策](issues/05-preference-grading-policy.md) |
| 06 | [生成并审阅单岗简历草稿](issues/08-source-bound-fact-findings.md) | AFK | [查看单岗的解释性分级](issues/06-grading-projection.md) |
| 07 | [导出可信PDF并单独重试导出](issues/09-draft-checkpoint-pdf-retry.md) | AFK | [生成并审阅单岗简历草稿](issues/08-source-bound-fact-findings.md) |
| 08 | [完成可暂停的多岗位材料批次](issues/07-bounded-batch-orchestration.md) | AFK | [在推荐列表中继续读取Gmail](issues/03-gmail-incremental-paging.md)、[将候选转成可核验的完整岗位](issues/04-job-source-checkpoints.md)、[导出可信PDF并单独重试导出](issues/09-draft-checkpoint-pdf-retry.md) |
| 09 | [重开App后明确恢复准备进度](issues/11-preparation-lifecycle-recovery.md) | AFK | [完成可暂停的多岗位材料批次](issues/07-bounded-batch-orchestration.md) |
| 10 | [冻结候选版本并验证整条准备链](issues/13-offline-batch-regression.md) | AFK | [重开App后明确恢复准备进度](issues/11-preparation-lifecycle-recovery.md) |
| 11 | [在安装版运行完整合成准备流程](issues/14-installed-preparation-acceptance.md) | AFK | [冻结候选版本并验证整条准备链](issues/13-offline-batch-regression.md) |
| 12 | [用真实推荐复核分级和简历](issues/15-real-preparation-pilot.md) | HITL | [在安装版运行完整合成准备流程](issues/14-installed-preparation-acceptance.md) |
| 13 | [接受准备版并记录剩余边界](issues/16-release-closeout.md) | HITL | [用真实推荐复核分级和简历](issues/15-real-preparation-pilot.md) |

## 2026-10-18 后继票

原批准23票保留身份与历史；新增的三票属于本材料图，当前状态以子票为准。

| 后继问题 | 交互 | 直接前置 |
| --- | --- | --- |
| [核验既有资料覆盖与单岗选择依据](issues/17-source-coverage-and-job-selection.md) | AFK | 无 |
| [确定完整 LaTeX 简历的生成与事实审核契约](issues/18-full-cv-review-contract.md) | HITL | 无 |
| [核对当前安装候选的完整材料准备链](issues/19-current-candidate-journey.md) | AFK | 前两票及契约决策后新增的必要实现票 |

[用真实推荐复核分级和简历](issues/15-real-preparation-pilot.md)新增当前候选整链前置；上表原依赖仅为批准时历史。
Prism／已有LaTeX／刷新优化均已有后继安装证据，不重复实现。此为初次整理时状态；完整CV契约已在下方结案记录中承接。
[全仓开放票与当前查询](../open-ticket-audit-2026-10-18/README.md)。

## 2026-10-18 来源核验后继

[核验既有资料覆盖与单岗选择依据](issues/17-source-coverage-and-job-selection.md)的来源、归属与比较范围核对已执行；私人明细保持私有。新补[按实际原因显示资料准备状态](issues/20-source-readiness-reasons.md)，承接有效profile仍被提示补齐资料的合成反例，并接到[核对当前安装候选的完整材料准备链](issues/19-current-candidate-journey.md)之前。以上三张是初次整理时的后继表；最新状态及新增依赖以子票为准。

## Wayfinding operations

本地文件为tracker，不创建远程issues。子票路径是身份，Parent指向地图，Blocked by使用标题链接且允许跨图相对路径；无原生blocking。
以唯一Assignee领取；open、none、所有直接前置closed/resolved且非superseded才进入机械frontier。Triage、HITL、暂停和动作授权仍须单独检查。
旧claimed或缺Assignee不得当成未领取。完成后在原票追加resolution再关闭，地图仅追加标题与摘要；本轮只修订规划、不领取或解决票。
[全仓查询](../open-ticket-audit-2026-10-18/README.md#查询与检查)适用于跨图依赖，取代只按同目录文件名判断的查询。

## 当前执行规则

状态和领取只保存在子票；读取Status、Triage、Assignee与Blocked by，全部实际前置完成且未领取才可开工。HITL必须由用户实际参与。superseded表示行政承接，不是工程完成，禁止作为已完成前置。

[迁移清单](../tomorrowstar-ticket-consolidation-2026-10-17/publication.json) · [批准前导航](../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/gmail-resume-preparation-2026-10-17/README.md) · [原父地图](map.md)。

整体预算参见[合并估算](../../research/tomorrowstar-combined-delivery-estimate-2026-10-17.md)：45–80主动小时，风险情景总计65–105，不与独立材料预算相加。真实申请继续暂停。

## 2026-10-18 原因提示修复完成

[按实际原因显示资料准备状态](issues/20-source-readiness-reasons.md)已完成源码修复、真实HTTP合成回归及完整默认离线验证；状态、读取限制和审核门槛保持。安装版未更新，组合／安装由[核对当前安装候选的完整材料准备链](issues/19-current-candidate-journey.md)持有。该时点完整CV契约尚待讨论；现已确认，见下方实现承接。真实申请继续暂停。[验证及范围](../source-readiness-reasons-2026-10-18/README.md)。

## 2026-10-18 完整CV契约结案与实现承接

[确定完整 LaTeX 简历的生成与事实审核契约](issues/18-full-cv-review-contract.md)已基于五轮实际用户答复结案；决定本身不接受任何具体材料。后继票已创建并依次连到当前候选整链：

| 实现票 | 直接前置 | 当前状态 |
| --- | --- | --- |
| [按 JD 从完整 LaTeX 底稿生成独立岗位版本](issues/21-generate-full-latex-job-version.md) | 已结案的完整CV契约 | open／none，可领取 |
| [在 Prism 按经历审核并继承已核验未变组](issues/22-prism-grouped-factual-review.md) | 完整岗位LaTeX生成 | open／none，等待前票 |
| [绑定完整源与新 PDF 并单独确认材料](issues/23-confirm-reviewed-latex-pdf.md) | Prism分组事实审核 | open／none，等待前票 |

[核对当前安装候选的完整材料准备链](issues/19-current-candidate-journey.md)以末票为新增直接前置，保留其原有依赖。新三票不改原批准23票的发布序号与身份。本轮只完成契约和建票，没有启动实现、安装或真实申请。

## 2026-10-18 完整LaTeX生成源码交付

[按 JD 从完整 LaTeX 底稿生成独立岗位版本](issues/21-generate-full-latex-job-version.md)已结案，见[最终验证](../full-latex-generation-2026-10-18/README.md)。上表为建票时快照；当前可领取票是[在 Prism 按经历审核并继承已核验未变组](issues/22-prism-grouped-factual-review.md)。[完整源与新PDF材料确认](issues/23-confirm-reviewed-latex-pdf.md)继续等待它，之后进入当前候选整链。各票仍以子票Status／Assignee／Blocked by为准。

本轮交付源码和合成验证，没有安装App或操作真实材料。来源、资格、事实、PDF及真实申请门槛保持，真实申请继续暂停。

## 2026-10-18 Prism分组审核源码交付

[在 Prism 按经历审核并继承已核验未变组](issues/22-prism-grouped-factual-review.md)已结案，见[源码与合成验证](../prism-group-review-2026-10-18/README.md)。当前可领取票为[绑定完整源与新 PDF 并单独确认材料](issues/23-confirm-reviewed-latex-pdf.md)，仍open／none；随后进入当前候选整链。旧建票表格继续作为时点快照。原三项HITL保持开放，安装与真实材料接受未代办，真实申请继续暂停。

## 2026-10-18 完整源与具体PDF确认源码交付

[绑定完整源与新 PDF 并单独确认材料](issues/23-confirm-reviewed-latex-pdf.md)已结案，见[最终交付证据](../full-latex-pdf-confirmation-2026-10-18/README.md)。当前可领取票为[核对当前安装候选的完整材料准备链](issues/19-current-candidate-journey.md)，保持open／none；前面的建票表和交付顺序保留为时点快照。原三项HITL仍须用户真实接受；本轮不安装、不启用真实模型／Prism、不恢复真实申请。

## 2026-10-18 当前候选核对与最小安装前置

[核对当前安装候选的完整材料准备链](issues/19-current-candidate-journey.md)已建立[证据矩阵](../current-candidate-journey-2026-10-18/README.md)，复用最新源码验证并检查现有安装包。安装完整链、实际加载与冷恢复仍未验证，原票保持open／none，等待新前置[补齐安装候选的完整 LaTeX 合成旅程入口](issues/24-installed-full-latex-synthetic-entry.md)。新票open／none，可领取；补完整底稿、替身schema、隔离Prism入口及加载身份覆盖，安装整链仍由原票验收。未更新App，原三项HITL与真实申请暂停保持。

## 2026-10-18 完整LaTeX安全合成入口源码交付

[补齐安装候选的完整 LaTeX 合成旅程入口](issues/24-installed-full-latex-synthetic-entry.md)已在源码及合成范围结案，见[冻结候选与验证](../installed-full-latex-synthetic-entry-2026-10-18/README.md)。当前可领取[核对当前安装候选的完整材料准备链](issues/19-current-candidate-journey.md)，保持open／none，直接前置均closed；仅需据新候选补实际安装组合、加载及测量缺口。固定PDF不证明实际编译，合成确认不代替用户接受；原三项HITL、旧owner及真实申请暂停保持。

