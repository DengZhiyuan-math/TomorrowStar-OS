# 冻结候选版本并验证整条准备链

Type: task
Label: wayfinder:task
Status: closed
Triage: done
Closure reason: completed
Completion: source-synthetic-and-renderer-verified
Policy version: preparation-policy/v1.0
Priority: P1
Interaction: AFK
Assignee: 01a14a95/root
Created: 2026-10-17
Updated: 2026-10-17
Parent: [交付 Gmail 岗位筛选与专用简历稳定版](../map.md)
Publication order: 10
Blocked by: [重开App后明确恢复准备进度](11-preparation-lifecycle-recovery.md)

**What to build:** 固定一个可交付候选，证明混合推荐批次可以完成或带着准确原因停住。

## Acceptance criteria

- [x] 覆盖分页、缺JD、资格冲突、资料漂移、取消及模型/PDF失败；未完成范围不漏报。
- [x] 完成受影响检查、完整默认离线验证及适用的真实renderer专项，证据绑定代码和配置版本。
- [x] 不修改邮箱、不产生ATS动作、不写Skill评估；可审核材料与失败结果均保留。
- [x] 本票验证已有切片的组合，不再次集中实现此前遗漏的整套工作台。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Comments

### 2026-10-17 — Resolution: frozen public source candidate and composed preparation chain verified

新增标准库候选冻结／只读核验命令，直接保存当前工作树的公共源码、静态UI、锁及配置、启动／构建源码、核心文档、许可证和选定合成测试，包含未跟踪源码。创建拒绝已有目标、符号链接、顶层及manifest路径穿越；拷贝中资料变化拒绝发布。核验检查准确清单、内容、配置和当前源码一致性，不执行候选或写入候选。

[最终候选](../../preparation-candidate-2026-10-17/candidate-v2/manifest.json)为 `preparation-candidate-027c7c7012bc3b4fb6d834f68ca12d72c10e42a59e22d8141150a0b397d319e6`，包含235个公共文件，最终检查前后均与checkout一致。配置、命令、JUnit／日志哈希、renderer及输出绑定在[最终验证记录](../../preparation-candidate-2026-10-17/verification.json)。早期候选因补充两个精确处置断言而成为前身，原包保留；[后继说明](../../preparation-candidate-2026-10-17/candidate-supersession.json)记录原候选源码比对正确拒绝漂移，没有覆盖旧包。

三条公共HTTP组合旅程复用真实intake、分析、草稿／PDF存储和工作流，仅替换外部边界：

1. 两页Gmail及跨页来源去重，保留4个候选和5条来源；缺JD、通用信息库German A2与岗位必需B2冲突、已知模型失败各自保存处置。明确取得JD、手动重试及恢复后，完整审阅草稿和具体PDF，停在等待申请记录；不重新读取Gmail，不漏报其他候选。
2. 生成中资料漂移时，真实store以 `resume_inputs_stale` 拒绝新结果，task为failed，对应批次行标为deferred并保留相同原因，解释显示输入过期。旧草稿字节和读取保留，取消未开始岗位后重开，零隐式重跑。
3. 已知PDF失败只隔离本岗，下一岗导出已保存但结果未知时全批停止；明确只读核验原回执，模型／导出次数均不增加。确认材料后第三岗仍pending，不预生成、不假报投递或记录完成。

- [最终验证](../../preparation-candidate-2026-10-17/verification.json)：完整默认离线 **2468 passed / 221 deselected**；针对性 **14 passed**，包含于完整离线；浏览器兼容 **41 passed / 72 deselected**。Ruff、255文件格式、JS语法和diff检查通过。
- [真实renderer质量](../../preparation-candidate-2026-10-17/pdf-quality.json)：使用当前模板，从确切保存的四条合成选材实际导出两页A4；全文、文字／像素边界及两页逐页视觉检查通过。[renderer绑定](../../preparation-candidate-2026-10-17/renderer-binding.json)核对最终候选中的引擎SHA、真实本机配置、harness和输出；旧PDF未改动。复制PDF的组合夹具只证明传输与流程，不算质量证据。
- [独立审查](../../preparation-candidate-2026-10-17/review.json)最终无未解决阻断。冻结器顶层路径穿越与manifest类型漏洞已修复；组合测试首轮字段／状态预期错误单独保留，未作为产品缺陷改运行时。
- [本票源码范围](../../preparation-candidate-2026-10-17/source-manifest.json)5项冻结后未变；[236项既有文件](../../preparation-candidate-2026-10-17/preserved-baseline.json)保持原字节。没有改运行时工作台或既有测试，也没有集中补建此前功能。

**关闭范围：** 公共源码候选、合成组合、完整默认离线、浏览器兼容和实际本机renderer专项完成。[安装票交接](../../preparation-candidate-2026-10-17/handoff.json)持有准确候选及核验要求；该源码快照不含全部历史测试资料，不是独立完整测试clone或安装包。安装窗口、真实推荐与真实简历人审仍由后继票验收。材料链不写Skill评估，完整离线领域测试仅用临时合成数据，不写用户Skill记录。

真实申请继续暂停；没有读取私人资料或真实邮箱、修改邮箱、调用真实模型／岗位／ATS、上传或Submit、恢复旧申请、启动或替换安装版App、提交Git或写远端。本次只关闭本票，不领取后继安装票。

### 2026-10-17 — Implementation claim under policy v1.0

用户明确授权执行本票；已核对「重开App后明确恢复准备进度」为 closed / source-and-synthetic-verified，由 `01a14a95/root` 唯一领取。复用已实现切片，冻结可复核的候选代码与配置，验证混合推荐、材料及准确停止原因，不重新构建工作台。

范围为隔离合成组合验证、完整默认离线、适用的真实本机renderer专项及候选证据回读。不读取私人资料或真实邮箱、不调用真实模型／岗位／ATS、不修改邮箱、不上传或Submit、不写Skill评估、不恢复旧申请，不启动或替换安装版App、不提交Git或写远端。真实申请继续暂停。安装与真实试用仍留后继验收。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/10-preparation-release-regression.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/gmail-resume-preparation-2026-10-17/issues/13-offline-batch-regression.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。
