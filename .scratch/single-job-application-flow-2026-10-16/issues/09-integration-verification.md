# 完成单岗位链路与故障恢复整体验证

Type: task
Label: wayfinder:task
Status: closed
Interaction: AFK
Assignee: 01a146b9/root
Created: 2026-10-16
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [将单岗位流程设为原生 App 默认运行方式](08-native-runtime.md)

## Question

什么可重复的合成证据能证明新主流程接通，并且没有破坏旧运行、版本检查或人工最终提交边界？

## Work and reuse

- 各实现票已分别完成 TDD/针对性验证；本票聚焦跨模块整条链和故障，不把全部测试推迟到此时。
- 用固定合成 JD、职业资料、Codex double 和隔离 ATS，通过真实 HTTP/UI 跑完整流程。
- 覆盖重复启动、模型超时、资料漂移、PDF 确认失效、旧 owner 冲突、缺答案、暂停、进程中断、上传未知、仅同步重试。
- 运行 checkout 完整离线套件与 Ruff，显式单独执行需要的 worker_browser 合成测试；不以替换 marker 排除式误放真实调用。
- 记录实际加载源码/输入绑定；passed/failed/skipped/blocked 分列，不覆盖历史失败和 sealed 资料。

## Ownership

- `tests/test_application_flow.py`
- `tests/test_portal_workflow_browser.py`
- `现有相关恢复/HTTP/原生合成测试`
- `本地图的合成验证资产`

以上为责任范围，不表示必须修改每个文件。多人同时工作时不得回退他人修改；共享接口按已完成依赖契约衔接，必要时先协调文件所有权。

## Acceptance criteria

- [x] 完整合成链和关键故障矩阵有可复核结果，自动最终 Submit/替代最终请求为零。
- [x] 项目要求的完整离线 pytest、Ruff check/format 与 git diff --check 通过；异常明确保留。
- [x] 合成报告不含真实岗位、个人资料或私有指纹；明确未验证真实模型质量/真实 ATS。

## Verification and evidence

- CONVENTIONS.md 的 checkout 验证命令
- docs/validation-runs.md
- tests/test_worker_crash_injection.py
- 先执行受影响的有意义测试；涉及共享流程/存储时按 CONVENTIONS 完成完整离线验证。浏览器合成与真实 ATS 分开记录。
- 关闭前将实际修改、所用版本、检查结果与限制写入本票 Resolution comment，并链接资产；不能用通过数或历史报告代替本票当前输入验收。
- 真实资料与私有衍生信息只保存在私有位置。本地图中的报告仅使用合成/脱敏状态，不嵌入真实字段、附件、岗位 URL 或私有指纹。
- 自动最终 Submit 保持为零。未知外部动作不自动重试。源码通过、安装版通过、真实填写、人工提交和雇主接收分别报告。

## Resolution comment

2026-10-17：第 08 票关闭后领取。将在现有分段证据上补真实 single worker 子进程的隔离 ATS 上传和恢复贯通；保留默认 CLI/选材/材料绑定，仅使用离线合成 CLI 与明确 PDF exporter double。安装版原生业务仍由第 10 票执行。

冻结实现完整离线 **1972 passed、150 deselected / 214.26s**；复用浏览器回归组 **126 passed、21 skipped、292 deselected / 339.63s**，未启用原生 Cua opt-in，排除两个实际系统 Chrome PDF 用例。新单岗位实际子进程贯通 **1 passed / 5.26s**，生产校验器与生成材料上传 SHA 一致，三字段实际回读、暂停重开同任务/进程/页面不重传，零自动提交。独立审计通过，所属测试进程已回收。全仓 Ruff check/format 与差异检查通过。

详细范围、保留失败、故障矩阵及合成回执见[整体验证记录](../assets/integration-verification.md)。本票按合成范围关闭，不代表实际 PDF 视觉、真实模型质量、安装版宿主或真实 ATS 通过。

