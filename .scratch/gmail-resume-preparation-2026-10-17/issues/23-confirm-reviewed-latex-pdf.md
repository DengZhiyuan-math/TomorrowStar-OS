# 绑定完整源与新 PDF 并单独确认材料

Type: task
Label: wayfinder:task
Status: closed
Triage: done
Closure reason: completed
Completion: source-and-synthetic-reviewed-latex-pdf-verified
Priority: P1
Interaction: AFK
Assignee: 01a14fd0/root
Created: 2026-10-18
Updated: 2026-10-18
Parent: [交付 Gmail 岗位筛选与专用简历稳定版](../map.md)
Blocked by: [在 Prism 按经历审核并继承已核验未变组](22-prism-grouped-factual-review.md)

## 当前契约定位 — 2026-10-20

保留严格源/PDF版本与技术回执；普通岗不要求每版独立用户确认或重复不变事实；按影响更新而非全量失效，34/36承接。

当前产品规范与执行顺序分别见[单岗位流程](../../../docs/single-job-flow.md)和[统一开发计划](../../../docs/development-plan.md)。本票既有Status、Assignee、完成记录和收据不变；关闭仅证明当时范围，不证明新规范已实现。下方与现行规范冲突的旧审批、白名单、总时间窗及运行门槛保留为历史，由现有后继承接，不重开、不追认，也不据此执行真实申请。

## Question

怎样将经过分组事实审核的完整岗位源版本与其具体PDF绑定，让用户每次确认新的整份PDF，而不借技术导出继承旧材料批准？

## Contract and acceptance

规则来源为[确定完整 LaTeX 简历的生成与事实审核契约](18-full-cv-review-contract.md)，复用已有严格Prism导出、PDFKit、回执及材料绑定实现，不重建renderer。

- [x] 当前主文件、完整源归档、JD／资料版本、分组审核及具体PDF共同指向可核对的当前材料；核对失败或源在编译时变化时不采用。
- [x] 技术编译／预览与事实审核、具体PDF确认分别处理；旧existing_latex技术授权仍不能直接转为正式事实审核或申请许可。
- [x] 本版正文所用组均有本版审核或经过核验的合法继承；未核实陈述不入正文，未采用经历保持可解释和可恢复。仅文件存在、技术导出成功或机械差异扫描不构成事实接受。
- [x] 每个新PDF均由用户核对内容、版式及同源关系后单独确认；旧PDF批准不继承。分组审核、PDF变化或输入变化按契约使相应确认失效，保留历史。
- [x] 未知／中断编译保留原尝试与回执，先核验，不重复编译；采用回执不自动确认材料，不重放旧worker动作。
- [x] 合成工作区覆盖审核→严格导出→原PDF回读→明确确认、改源失效／重审、继承正确性及未知恢复；使用替身和允许的技术renderer，完成必要回归。源码通过不代表安装或真实材料接受。
- [x] 接入现有准备终点，保持worker禁用、当前岗完成／记录边界和所有真实申请暂停条件；最终Submit仍由用户操作。

## Ownership and boundaries

最小责任范围为现有 `application_flow.py`、`application_resume.py`、Prism／PDF回执接口、材料确认页面及相关测试。与前两票协调共享代码，复用原有版本与锁，不回退其他改动。

先领取再工作；真实材料接受只能由用户作出，合成测试不冒充人审。实际候选冻结、包内与加载一致性、冷恢复及安装补验仍由[核对当前安装候选的完整材料准备链](19-current-candidate-journey.md)负责。

## Resolution comment

已完成源码及合成验证，见[最终证据](../../full-latex-pdf-confirmation-2026-10-18/README.md)。本版逐组审核、完整源归档、严格预览与具体PDF共同绑定；每个新材料版本仍由用户独立确认。安装、真实人审及真实申请均未代办。

### 2026-10-18 — Grouped review prerequisite completed in source

前置[在 Prism 按经历审核并继承已核验未变组](22-prism-grouped-factual-review.md)已完成源码、实际存储合成整合、HTTP与隔离合成界面验证，见[交付证据](../../prism-group-review-2026-10-18/README.md)。可复用`group_session`、同源`group_preview`回执、`review_fingerprint`、任务`group_reviews`与追加`group_review_history`；继承记录有唯一ID及原回执定位。实际逐组确认由任务持有，不可变草稿本身仍pending。

本票保持open／none，直接前置已closed；下一步绑定同一完整源、合法逐组审核与具体新PDF，再由用户单独确认。技术预览回执可核验复用，但不能等同正式材料接受；未知读取继续只读核验，不重编。安装、真实人审及真实申请门槛不变。

### 2026-10-18 — Claim and execution scope

用户授权开始本票，核对前置已closed且未领取后由`01a14fd0/root`领取。复用完整源、逐组审核和严格Prism／PDF回执，仅用隔离合成资料实现与验证新PDF绑定和独立材料确认。保持读取、资格、版本和未知结果门槛；不读取私人材料、不启动真实模型／Prism、不安装App，也不恢复真实申请。

### 2026-10-18 — Source and synthetic completion

复用已有严格Prism捕获和PDF检查器，将该版完整源、编译回执、原PDF字节及精确逐组确认封存为独立正式导出。绑定不重复编译；源变化及保存后撤销阻止采用，历史回读继续核验原归档与原严格PDF。独立材料确认记录包含PDF版本／哈希、源、预览、草稿／分组审核／输入版本及内容、版式、完整源一致性的用户审核范围。

新导出、改组／源／输入均不继承材料批准；相同PDF哈希也不能跨新版本继承。正常无变化回读保留原确认；未知／中断回读先核验原回执，恢复有效组记录而不复活当前材料批准。已完成但损坏的副本可明确重新绑定，原严格预览仍须有效；未知结果不重编、不重放。

最终完整默认离线 **2877 passed / 279 deselected / 404.53s**；最终隔离合成界面 **1 passed / 6.30s**；存储／流程／HTTP及生命周期定向 **60 passed / 7.75s**。实际store整合覆盖七组确认、改一组／承接六组、原PDF回读及两次独立材料确认。独立复核、Ruff全仓检查和格式检查、JS语法与diff检查通过。审查发现的PDF审核范围、损坏副本入口、无变化回读及未知恢复均已修正并保留失败证据；两次主动中止的旧完整回归不作为最终通过证据。

准备模式仍无worker，材料批次确认后停在`waiting_application_record`；原`existing_latex`技术路径限制保持。原三项HITL和旧领取不变。当前候选整链票现为未领取frontier，仅解除本路径源码前置，不执行安装或真实人审。未读私人职业资料、未真实调用模型／Prism、未安装或恢复真实申请。
