# 把单岗位五阶段流程接入 App 界面

Type: task
Label: wayfinder:task
Status: closed
Interaction: AFK
Assignee: 01a146b9/source_bundle
Created: 2026-10-16
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [接通 Codex 岗位分析与可解释匹配评分](04-match-analysis.md), [复用岗位分析生成并确认专用简历](05-tailored-resume.md), [接通受版本约束的单岗位自动填写](06-single-worker.md)

## 当前契约定位 — 2026-10-20

五阶段展示可用；逐阶段启动、材料批准和分步接管不是当前主路径，34/37承接。

当前产品规范与执行顺序分别见[单岗位流程](../../../docs/single-job-flow.md)和[统一开发计划](../../../docs/development-plan.md)。本票既有Status、Assignee、完成记录和收据不变；关闭仅证明当时范围，不证明新规范已实现。下方与现行规范冲突的旧审批、白名单、总时间窗及运行门槛保留为历史，由现有后继承接，不重开、不追认，也不据此执行真实申请。

## Question

如何在同一个岗位工作区完成 JD、评分、简历、自动填写和最终复核，消除手动复制任务和重选 PDF？

## Work and reuse

- 与[推荐入口票](14-gmail-recommendation-intake.md)按稳定后台接口并行接线；该票的安装版读取验收需要本界面，因此不以其最终关闭作为本票开始条件。原生整体验收仍由第 10、11 票执行，不降低地图终点。
- 复用现有网页组件与原生窗口，新增最小 application_flow.js；不更换前端框架、不全面重做视觉设计。
- 按用户追加要求，主入口先从 Gmail 推荐取得岗位与原 JD，再进入匹配分析→专用简历→自动填写→最终复核；手动 JD 输入保留为备用，岗位列表继续保存历史。
- 后台任务短请求+快照轮询，展示处理中、错误、缺资料、需要回答、待核验、待最终复核；重开仅恢复观察。
- 展示分数依据、来源、PDF 预览和一次具体的材料确认；必要问题在本任务补充，最终提交跳到原页面。
- 手动 PDF/复制给 Codex 降为备用；运行版本、JSON、trace 等放诊断详情。新增和编辑控件应可用键盘与辅助功能定位。
- 用户已接受主流程，不重开泛化 UI 决策；新发现确需用户选择的行为单独登记，不以代理确认。

## Ownership

- `src/career_evidence_graph/portal_static/index.html`
- `src/career_evidence_graph/portal_static/app.js`
- `src/career_evidence_graph/portal_static/application_flow.js（新增）`
- `src/career_evidence_graph/portal_static/worker.js（复用）`
- `src/career_evidence_graph/portal_static/style.css（最小改动）`

以上为责任范围，不表示必须修改每个文件。多人同时工作时不得回退他人修改；共享接口按已完成依赖契约衔接，必要时先协调文件所有权。

## Acceptance criteria

- [x] 合成 UI 从粘贴 JD 到待最终复核全部在 App 工作区推进，不需外部聊天或手动查找 PDF。
- [x] 重复点击、刷新、后台失败、改 JD、缺答案和未知上传均可见且行为与服务端一致。
- [x] 原岗位搜索/编辑、证据和旧备用入口可用；关键控件可由辅助功能或键盘操作。

## Verification and evidence

- tests/test_portal_workflow_browser.py
- tests/test_career_portal_http.py
- tests/test_handoff_browser.py（保留旧模式）
- 先执行受影响的有意义测试；涉及共享流程/存储时按 CONVENTIONS 完成完整离线验证。浏览器合成与真实 ATS 分开记录。
- 关闭前将实际修改、所用版本、检查结果与限制写入本票 Resolution comment，并链接资产；不能用通过数或历史报告代替本票当前输入验收。
- 真实资料与私有衍生信息只保存在私有位置。本地图中的报告仅使用合成/脱敏状态，不嵌入真实字段、附件、岗位 URL 或私有指纹。
- 自动最终 Submit 保持为零。未知外部动作不自动重试。源码通过、安装版通过、真实填写、人工提交和雇主接收分别报告。

## Resolution comment

尚未领取或执行。后续执行者先填写 Assignee，再在此追加事实与证据；本段不是完成结论。

2026-10-17：`01a146b9/source_bundle` 完成第 07 票与第 14 票共享的 App 界面接线，移交根执行者核验。本票保持 open；本次不代替安装版或真实岗位验收。

- 新增 `#flow` 工作区与经典 defer `application_flow.js`，复用 app.js 的 API、CSRF、状态、确认弹窗和编辑。Gmail 刷新与选岗均需明确点击；展示全文、摘要、登录、失效、既有申请、相似记录及保存待核验状态。选岗后读取最新申请版本再创建任务。手动 JD 与原有交接入口保留。
- 匹配展示下界、可能区间、覆盖、3:1 权重与部分支持 0.5、逐项来源和归属、硬条件及独立历史参考。硬条件在本任务记录用户事实说明，不改原数值。简历展示具体 PDF、采用和未采用来源、原文与改写；确认绑定版本与 hash，明确重生成撤销旧批准。重开后按服务端保存的批准显示当前 PDF 勾选状态，新版本仍须重新复核。
- 申请国家与资料发送另行确认；准备保持 paused/queued，只有明确开始才控制既有 worker。任务内提供暂停、当前岗位答案、旧动作核验、重新接管、仅同步、取消与原页交接。重开只观察；本页面明确 resume 成功后才维持自己的 controller，pagehide 对该 controller 暂停。未知保存与上传不自动重试。页面不调用最终 Submit。
- 新增 `tests/test_application_flow_browser.py`，最终当前版本 **10 passed in 61.00s**。覆盖只读重开、选岗幂等、分析与材料、硬条件、丢失响应、无 URL 手动 JD、显式资料同步与取消、发送批准、暂停问答、未知上传、最终复核及 pagehide 控制。仓库 Playwright 夹具仅访问 loopback，模型/PDF/worker spawn 使用替身，worker 完成回读为合成输入。
- 与 `tests/test_portal_workflow_browser.py`、`tests/test_handoff_browser.py` 联合 **24 passed in 81.93s**。之后仅修复批准勾选的重开显示，并将全部新 10 项重新跑绿。HTTP 专项 **110 passed in 10.72s**。Ruff check/format、`node --check`、`git diff --check` 通过。
- 联合命令：`UV_CACHE_DIR=/private/tmp/tomorrowstar-single-job-uv-cache uv run --locked python scripts/run_pytest.py tests/test_application_flow_browser.py tests/test_portal_workflow_browser.py tests/test_handoff_browser.py -m worker_browser -q -x -s`；最终修复重跑为相同命令仅选新专项。Bundled Chromium 在 sandbox 内启动 SIGABRT，同一正式合成测试在许可执行环境通过。未启动系统 Chrome、真实 ATS 或真实 PDF 导出浏览器。
- 已视检 1440 像素桌面与 390 像素手机合成截图，手机无横向溢出；长校验值和模型技术限制收进详情。最终截图仅含合成姓名与岗位，保存在系统临时目录 `/var/folders/13/jgb8c061583ggg622pgv9l0c0000gp/T/tomorrowstar-flow-ui-0jchiqrx/flow-desktop.png`、`flow-mobile.png`。未将真实材料写入仓库。
- 仅修改 index.html、app.js、application_flow.js、style.css 与新浏览器专项；未改 Python、worker.js 或 handoff.js。当前输入是保留的 dirty 工作区。index SHA256 `167157d98a1b0779be2833c01b79bcc9dab2296a4f24ad0ab872032b96dbb30d`；app `f6180134d5169c42ac49aff1e6644c9c7e06029a6c00263801ffcc21b93b5783`；flow `5db38a975789c4ccc68d491f60acfbb24fa7708526063a31eafa72e5983cd815`；style `38e7ea642aa42239d0194925f8d2d47809e68e2220a2737c2a920ff8b3f18900`；专项 `bc5199829e8e2686b0dee64cfcfd8984aa57ad453751273212ff7826484af8d0`。
- 原生安装、真实 Gmail/App 操作和真实岗位填写由后续票验收；本次 Submit 为零。代码与合成通过不代表原生、雇主接收或用户验收。


2026-10-17 根执行者关闭：已回读共享 UI 最终移交，当前完整新界面 **10 passed，61.00s**；旧 overview/handoff 联合 **24 passed，81.93s** 后的批准勾选显示修复，已由全部新 10 项重跑覆盖。HTTP **110 passed**，Ruff、格式、JS 语法及 diff 检查通过。合成[桌面截图](../assets/flow-desktop.png)与[手机截图](../assets/flow-mobile.png)保留。默认原生启动、真实 provider/PDF/browser 与安装版仍由后继验收，本票未声称真实填写或 Submit。
