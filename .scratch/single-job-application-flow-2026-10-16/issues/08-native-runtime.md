# 将单岗位流程设为原生 App 默认运行方式

Type: task
Label: wayfinder:task
Status: closed
Interaction: AFK
Assignee: 01a146b9/root
Created: 2026-10-16
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [接通受版本约束的单岗位自动填写](06-single-worker.md), [把单岗位五阶段流程接入 App 界面](07-app-workspace.md)

## Question

怎样让安装版 App 默认提供分析、简历与受管填写，而不要求用户从 Terminal 开实验入口？

## Work and reuse

- macos/server.py 选择单岗位主流程；Codex 与材料服务独立可用，填写依赖单独检查；打开 App 不自动启动真实浏览器或上传。
- 复用 Swift 管理的后端、配置、loopback、文件选择与退出生命周期；导航与默认页对应新流程。
- 保留现有 handoff/worker 双执行通道互斥，采用独立新运行目录；旧 handoff/worker 根、答案、原页和历史不迁移不覆盖。
- 旧 active/待释放/未知任务继续占用岗位；需要查看时复用只读历史或原模式，不能实例化另一可写控制器夺取任务。
- 复用经过校验的 Codex 绝对路径与现有浏览器运行时；清晰区分 CLI、材料、自动填写各自可用性。

## Ownership

- `macos/server.py`
- `macos/App.swift`
- `macos/build.py（仅必要打包清单）`
- `src/career_evidence_graph/career_portal.py`
- `tests/test_macos_portal.py`
- `tests/test_macos_build_scripts.py`
- `tests/test_handoff_http.py`

以上为责任范围，不表示必须修改每个文件。多人同时工作时不得回退他人修改；共享接口按已完成依赖契约衔接，必要时先协调文件所有权。

## Acceptance criteria

- [x] 打包默认配置可访问新流程，无需 --automation-lab；无浏览器能力时仍可分析并生成简历。
- [x] 旧配置和私有运行保留；打开 App 无自动恢复/发送，互斥及旧模式测试语义保留。
- [x] 真实 loopback readiness、Host/CSRF、EOF 退出和资源清单测试通过。

## Verification and evidence

- tests/test_macos_portal.py
- tests/test_handoff_http.py
- tests/test_worker_configuration_boundaries.py
- 先执行受影响的有意义测试；涉及共享流程/存储时按 CONVENTIONS 完成完整离线验证。浏览器合成与真实 ATS 分开记录。
- 关闭前将实际修改、所用版本、检查结果与限制写入本票 Resolution comment，并链接资产；不能用通过数或历史报告代替本票当前输入验收。
- 真实资料与私有衍生信息只保存在私有位置。本地图中的报告仅使用合成/脱敏状态，不嵌入真实字段、附件、岗位 URL 或私有指纹。
- 自动最终 Submit 保持为零。未知外部动作不自动重试。源码通过、安装版通过、真实填写、人工提交和雇主接收分别报告。

## Resolution comment

2026-10-17：当前实现及独立审计通过，按源码装配范围关闭；安装版与真实业务验收继续由后继票负责。

- 原生默认 `#flow`，使用独立 flow/worker 根。旧 handoff/lab 为显式模式；旧运行只读参加占用检查。打开 App 不运行模型、Gmail 或浏览器。
- 新 flow 禁止旧 worker 写接口与旧简历生成旁路。CLI、材料和填写能力分开显示；worker 结构/存储故障使用固定消息降级，保留资料界面。
- 退出先关闭 flow 写入入口，再暂停本次 worker；已排队继续请求不能在退出时重新启动。flow 检查点写失败也会释放适当资源并继续暂停，原页与未决动作保持。
- 为安装验收加入固定合成目录/CLI/配置的 `--synthetic-flow`，禁 Gmail 和非 loopback 外链，保留真实 App 宿主权限守卫。
- native 专项 **45 passed / 54.27s**；HTTP 与 flow **137 passed / 11.94s**；新界面 Chromium 回归 **10 passed / 42.84s**。三个独立审计发现的恢复缺陷均先 RED 后 GREEN，独立复验通过。Swift 完整类型检查、全仓 Ruff check/format、差异检查通过。
- 此前全量在 native 文件同时重写期间得到 **1926 passed、1 failed、150 deselected**；唯一失败为旧参数版本的桌面启动测试，保留该失败。随后冻结版本完整离线结果为 **1972 passed、150 deselected / 214.26s**，全仓 Ruff check/format 与 `git diff --check` 通过。
- 本票以上属于源码和合成检查；未声称安装版窗口或真实 ATS 通过。

