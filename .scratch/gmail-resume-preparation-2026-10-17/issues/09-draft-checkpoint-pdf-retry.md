# 导出可信PDF并单独重试导出

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
Publication order: 07
Blocked by: [生成并审阅单岗简历草稿](08-source-bound-fact-findings.md)

**What to build:** 用户从已验证草稿获得可审核PDF；渲染失败后可只重试导出，不再次生成内容。

## 当前契约定位 — 2026-10-20

保留独立草稿/PDF检查点和已保存结果复用；有完整可识别结果自动恢复，不因每次编译或版本变化要求重新批准，27/34承接。

当前产品规范与执行顺序分别见[单岗位流程](../../../docs/single-job-flow.md)和[统一开发计划](../../../docs/development-plan.md)。本票既有Status、Assignee、完成记录和收据不变；关闭仅证明当时范围，不证明新规范已实现。下方与现行规范冲突的旧审批、白名单、总时间窗及运行门槛保留为历史，由现有后继承接，不重开、不追认，也不据此执行真实申请。

## Acceptance criteria

- [x] 默认采用 A4 纸张并沿用当前模板，按已确认的默认语言政策处理；本票不擅自新增固定页数要求。
- [x] 非空材料与实际选材可追溯；文字提取、页数及像素布局检查使用实际renderer，模拟成功不算质量通过。
- [x] 显式导出重试不增加模型调用；损坏草稿、输入或配置漂移拒绝采用并保留旧版本。
- [x] 导出或manifest采用竞争、取消、晚返回均不假报成功；未知结果先核验。
- [x] 用户可以打开PDF及其原文/草稿进行审阅，不存在跨候选附件或审核串用。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Comments

### 2026-10-17 — Resolution: saved-draft PDF export and explicit export-only retry verified

准备模式增加独立 `export` 阶段：用户先审阅确切版本的已保存草稿，再用现有模板导出默认英文、A4 PDF，不增加固定页数限制。原文、草稿、责任边界与 PDF 同时可见；打开后明确确认的是本次已采用的具体 PDF，草稿审阅不被当作 PDF 确认或投递授权。

每次导出使用独立版本目录，先保存 intent 与待渲染 HTML 指纹，再保存完整 manifest，绑定草稿、输入、分析、来源、生成配置、渲染配置和确切 PDF／HTML／manifest 字节。导出失败可只重试 PDF，不调用内容模型；渲染配置独立于生成配置。损坏草稿、输入或配置变化拒绝采用；旧版本与审阅历史保留。PDF 损坏或渲染器变化不使仍有效的草稿被迫重新生成。

未知保存或执行结果先只读核验回执，不能盲目重试；核验后未完成的尝试允许明确重试，冲突或损坏记录保持待核验。重开时尚未准入的 queued 导出为已知未开始，running 导出继续待核验。取消后不能通过核验复活；取消、输入变化、配置变化或被替代的晚返回均不成为当前 PDF。预览只接受已采用且指纹一致的导出，两岗及相同 PDF 哈希的不同版本不会共享复核勾选或确认。

- [最终验证](../../pdf-export-2026-10-17/verification.json)：冻结版本完整离线 **2406 passed / 212 deselected**，保持默认排除规则；针对性 **53 passed**，包含于完整离线；浏览器兼容 **32 passed / 72 deselected**，其中新增4条用户路径，保留28条既有路径。Ruff检查、243文件格式、JS语法、diff与文档链接检查通过。
- [实际 renderer 质量](../../pdf-export-2026-10-17/pdf-quality.json)：通过真实准备流程，从确切保存的四条合成选材导出 **两页 A4**；全文提取完整，尺寸、非空页面、文字边界、像素边界及两页逐页视觉检查通过。一次合成内容生成，实际导出不增加模型调用。复制完整 PDF 的单元／界面夹具只验证传输与故障流程，不算 renderer 质量。
- [真实 renderer 配置修复](../../pdf-export-2026-10-17/renderer-metadata-diagnosis.json)：本机 Chrome 启动仅改变 executable ctime，内容 SHA、mtime、大小、权限与 inode 均不变，旧配置绑定因此误报漂移。排除该启动噪声，并绑定稳定 executable 属性及实际 Framework 版本路径、二进制和版本文件属性；真实身份变化仍拒绝采用。修复后的真实导出通过，失败日志保留。
- [独立审查](../../pdf-export-2026-10-17/review.json)发现并修复取消后核验复活、queued 恢复死角及渲染前 HTML 指纹绑定问题；最终无未解决阻断。[源码边界](../../pdf-export-2026-10-17/source-manifest.json)的14项在最终验证期间未变；[7个既有测试文件](../../pdf-export-2026-10-17/preserved-legacy-tests.json)保持原字节。
- [证据说明与保留失败](../../pdf-export-2026-10-17/README.md)：首次受限 Chrome 启动的 macOS 注册阶段中止、QA设置错误、原合同拒绝六条选材以及配置漂移的失败均单独保留；没有改写为通过，也不据此关闭旧申请或安装版故障。

**关闭范围：** 源码、隔离合成流程与实际本机 renderer 的合成质量验证完成。运行时 PDF 检查是有界文件结构及来源绑定检查，不代替完整 PDF 解析、语义事实判断或真实简历人审。安装版、真实邮箱／模型试用与真实内容人审继续由后继票验收。真实申请继续暂停；无真实邮箱读取／写入、模型调用、岗位抓取、ATS、上传、Submit、旧申请恢复、App启动、安装替换、Git提交或远端写入。本次只关闭本票，不领取多岗位批次后继票。

### 2026-10-17 — Implementation claim

用户明确要求继续完成本票的实现、验证和回写，真实申请继续暂停。已核对唯一前置「生成并审阅单岗简历草稿」为 closed / source-and-synthetic-verified，由 `01a14a95/root` 领取。

本票从实际保存并审阅的来源绑定草稿导出 A4、当前模板 PDF；显式只重试导出，不重新调用内容模型。验证采用隔离合成材料和实际本机 renderer，文字、页数、尺寸和逐页像素布局分别留证。模拟导出只用于故障／竞态回归，不代替实际渲染质量。

不读取真实邮箱或私人材料，不调用真实模型、岗位页面或 ATS，不启动 TomorrowStar App，不上传／Submit、不恢复旧申请、不替换安装版、不提交或远端写入。旧工作与封存证据保留；安装和真实材料人审验收保持独立。

### 2026-10-17 — A4 template policy confirmed; implementation not started

[确认筛选与生成政策](05-preference-grading-policy.md)的 P10 为默认 A4 及沿用当前模板的唯一详细决策来源；P9 确认默认英文与其他明确语言要求的提示边界。已加入本票验收；Status、Assignee 和依赖不变，本次不领取、不实现、不生成 PDF 或声称 renderer 质量通过。真实申请继续暂停。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/07-verified-pdf-retry.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/gmail-resume-preparation-2026-10-17/issues/09-draft-checkpoint-pdf-retry.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。
