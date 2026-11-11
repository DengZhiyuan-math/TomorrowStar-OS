# 重开App后明确恢复准备进度

Type: task
Label: wayfinder:task
Status: closed
Triage: done
Closure reason: completed
Completion: source-and-synthetic-verified
Policy version: preparation-policy/v1.0
Priority: P0
Interaction: AFK
Assignee: 01a14a95/root
Created: 2026-10-17
Updated: 2026-10-17
Parent: [交付 Gmail 岗位筛选与专用简历稳定版](../map.md)
Publication order: 09
Blocked by: [完成可暂停的多岗位材料批次](07-bounded-batch-orchestration.md)

**What to build:** 退出或中断后，用户重开App能查看已保存结果与未决阶段，再明确选择继续。

## 当前契约定位 — 2026-10-20

保留恢复、历史与已存结果；一次继续按当前状态恢复，不因无关输入变化使全部失效，27/36/37承接。

当前产品规范与执行顺序分别见[单岗位流程](../../../docs/single-job-flow.md)和[统一开发计划](../../../docs/development-plan.md)。本票既有Status、Assignee、完成记录和收据不变；关闭仅证明当时范围，不证明新规范已实现。下方与现行规范冲突的旧审批、白名单、总时间窗及运行门槛保留为历史，由现有后继承接，不重开、不追认，也不据此执行真实申请。

## Acceptance criteria

- [x] 正常退出、后台退出、模型返回竞争和PDF失败分别有隔离合成记录。
- [x] 恢复不隐式重跑模型、不重做未知写入、不恢复旧填写器；未知状态显示核验办法。
- [x] 实际运行版本、任务身份和输入被核实；原资料与历史结果保留。
- [x] 当前恢复验证与历史原生根因分开，不能用新流程成功关闭旧调查。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Comments

### 2026-10-17 — Resolution: explicit preparation recovery and runtime identity verified

中断阶段追加恢复记录，绑定原阶段、尝试、输入代次、输入摘要、JD 和原因；重复读取或重开已经恢复／完成的阶段不增加记录、不排入执行。已保存分析、草稿、审阅、PDF、材料确认和历史快照保留。关闭和结果采用共用原应用锁，先完成检查点的结果保留，关闭边界后的晚返回不能采用；旧执行器仍活跃时保留 owner 锁，新实例不能自动接管重试。

分析／草稿中断须明确重试；排队未开始的 PDF 记为已知未开始，运行中或未知的 PDF 先只读核验原回执。已知导出失败保留有效草稿及审阅，只明确重试导出。批次继续暂停，故障岗位仍由手动重试恢复；材料确认停在等待申请结果记录，不自动下一岗、不恢复旧填写器。

页面显示当前服务会话、包／Python版本、已加载准备引擎及本会话实际返回的 UI 字节摘要，另显示任务、输入代次及 JD／资料／配置／政策绑定。运行身份启动时冻结；新服务识别已加载代码、稳定常量、默认参数与关键来源解析 getter 的变化，不用后来磁盘源码冒充已运行版本。该身份是限定准备引擎的诊断记录，不是整包签名或安装版接受。

- [最终验证](../../preparation-recovery-2026-10-17/verification.json)：完整离线 **2454 passed / 221 deselected**，沿用默认排除规则；针对性 **24 passed**，包含于完整离线；浏览器 **41 passed / 72 deselected**，新增2条真正重启服务的用户路径并保留39条既有路径。Ruff、252文件格式、JS语法及diff检查通过。
- [退出与恢复记录](../../preparation-recovery-2026-10-17/README.md)：实际隔离 Python 后端的父管道 EOF、SIGTERM、SIGKILL 和分析执行中强制退出分别验证；模型返回竞争、4种完成材料检查点及PDF已知／未开始／运行中故障另有新回归。两个浏览器重开场景分别验证已确认材料保持原版本、未知导出保留原尝试并先核验回执，均零隐式模型／导出，下一岗未启动。
- [当前后端退出故障诊断](../../preparation-recovery-2026-10-17/shutdown-diagnosis.json)：本轮SIGTERM两次复现 Python stdin `BufferedReader` 关闭锁错误；去掉任务与HTTP的最小差分仍复现。改为原始输入流读取后正常退出，保留内存输入夹具兼容；最终相关7项将线程警告视为错误仍通过。原始失败、最小差分和首次兼容警告均保留，不归因为旧Chrome或Cua事件。
- [独立审查](../../preparation-recovery-2026-10-17/review.json)最终无未解决阻断；运行常量、政策字段、默认参数及属性getter遗漏已修正。取消任务控件的初次报告经核对基线后撤销，没有为误报扩大旧路径改动。
- [冻结源码](../../preparation-recovery-2026-10-17/source-manifest.json)11项在最终验证期间未变，[182项既有文件](../../preparation-recovery-2026-10-17/preserved-baseline.json)保持原字节。[实际隔离服务身份回读](../../preparation-recovery-2026-10-17/runtime-readback.json)确认准备模式、Python 3.13.14、已加载引擎／UI身份和无填写worker。PDF模板及renderer未修改，原质量证据继续保留。

**关闭范围：** 源码与隔离合成恢复验证。没有启动或替换安装版App；完整候选冻结、安装窗口、真实样本与真实简历人审仍由后继票验收。本次不关闭任何历史原生调查。真实申请继续暂停；没有私人资料、真实邮箱／模型／岗位／ATS操作、上传、Submit、旧申请恢复、Git提交或远端写入。本次只关闭本票，不领取后继票。

### 2026-10-17 — Implementation claim under policy v1.0

用户授权继续下一张已解锁票。已核对「完成可暂停的多岗位材料批次」为 closed / source-and-synthetic-verified；本票由 `01a14a95/root` 唯一领取。按 `preparation-policy/v1.0` 验证退出、中断、恢复、版本和结果绑定，复用现有检查点与单一执行队列。

范围为源码及隔离合成验证；不读取私人资料或真实邮箱、不调用真实模型／岗位／ATS、不上传或Submit、不恢复旧申请／填写器、不启动或替换安装版App、不提交Git或写远端。真实申请继续暂停。历史原生崩溃调查与本次恢复验证分开；安装验收留后继票。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/09-preparation-recovery.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/gmail-resume-preparation-2026-10-17/issues/11-preparation-lifecycle-recovery.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。
