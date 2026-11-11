# 打开独立材料准备入口

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
Publication order: 01
Blocked by: None (can start immediately)

**What to build:** 用户可从App打开材料准备页，查看已有材料及邮箱、模型、资料、PDF就绪情况；缺少填写器或Cua时仍可工作。

## Acceptance criteria

- [x] 页面与准备状态可保存、读回；必要的账号、岗位、资料、政策、模型配置与草稿身份有明确失效边界。
- [x] 使用已有完整JD或合成候选演示入口；缺依赖显示可处置原因，不把未就绪显示成空结果。
- [x] 不创建填写worker、不接管旧owner、不恢复暂停申请；测试覆盖入口隔离和输入变更。
- [x] 只做本切片需要的最小状态边界整理，复用现有分析与导出能力，不先建通用编排框架。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Comments

### 2026-10-17 — Resolution: source and synthetic entry verified

默认原生装配改用独立 `material-preparation` 目录，复用现有 flow、分析与简历服务；不构造填写 worker、不观察旧 owner、不恢复旧申请。保留显式 `--single-job-flow` 与旧诊断／交接模式。准备页显示六项就绪检查，支持已有 JD 选入、任务保存、材料预览与重开。

输入身份绑定 JD、资料、模型、待确认政策标记、职业目录和本地连接上下文；变更后须明确同步，旧版本保留。本地连接只检查登录／配置文件元数据及凭据环境摘要，不读取凭据文件内容，不能证明远程 Gmail 账号身份。邮箱登录、模型调用和 PDF 依赖发现均与实际成功分开。政策决定仍由对应 HITL 票确认。

独立审查发现并修复两项恢复问题：上次推荐读取失败不能永久禁用明确重试；PDF 无效须禁止确认但允许明确重生成，不能与输入过期混成死循环。

- [最终验证与源码指纹](../../preparation-entry-2026-10-17/verification.json)：完整离线 **2129 passed / 196 deselected**；合成浏览器新旧流程 **15 passed**；原生后端／参数 **49 passed**（包含在完整离线内）；Ruff、JavaScript 语法、Swift 全文件类型检查及 diff 检查通过。
- [完整离线 JUnit](../../preparation-entry-2026-10-17/offline.xml)与[运行日志](../../preparation-entry-2026-10-17/offline.log)。
- [合成界面截图](../../preparation-entry-2026-10-17/preparation-synthetic.png)。

本票仅关闭入口的源码与合成验收。未构建、替换或启动真实 App，真实邮箱／模型／ATS／上传／最终 Submit 均为零。批次、筛选政策、完整准备链、安装版验收与真实材料人审仍归后继票；原申请继续暂停。没有 commit、暂存或远端写入。

### 2026-10-17 — Implementation claim

用户调用 implement 并要求开始执行。已回读 open、未领取、无前置状态，由 `01a14a95/root` 领取本票；本轮只实现独立材料准备入口，采用合成资料验证，真实邮箱、模型与申请仍不执行。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/01-preparation-entry.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/gmail-resume-preparation-2026-10-17/issues/02-preparation-only-runtime.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。
