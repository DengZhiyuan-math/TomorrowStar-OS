# 只读核验并保护旧版运行的岗位范围

Type: task
Label: wayfinder:task
Status: closed
Interaction: AFK
Assignee: 01a146b9/task_contract
Created: 2026-10-17
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [接通受版本约束的单岗位自动填写](06-single-worker.md)

## 当前契约定位 — 2026-10-20

保留重复申请与同岗占用判断；旧运行根、原包或其他岗位未知记录不应阻断所有新岗，34按准确任务范围衔接。

当前产品规范与执行顺序分别见[单岗位流程](../../../docs/single-job-flow.md)和[统一开发计划](../../../docs/development-plan.md)。本票既有Status、Assignee、完成记录和收据不变；关闭仅证明当时范围，不证明新规范已实现。下方与现行规范冲突的旧审批、白名单、总时间窗及运行门槛保留为历史，由现有后继承接，不重开、不追认，也不据此执行真实申请。

## Question

旧版运行没有 applications_root 时，怎样核验确切的岗位占用范围，同时保留其原件和所有未决动作？

## Work and reuse

- 安装前只读检查发现明确的旧 schema：运行没有新版目录字段，但各岗位已保存 application_id、整份原笔记 revision 和目标 URL。当前简单目录门禁无法区分可严格核验的旧记录与真正未知记录。
- 增加最小的旧版只读适配：仅字段缺失的 run.json 可尝试用全部非空岗位的 ID、当前完整笔记字节哈希和规范化目标同时核验；任何一项缺失、漂移、冲突或无法回读均继续拒绝填写。
- 这只建立确切岗位目标的占用核验范围，不推断原进程在何处写入，也不为旧 worker 补写目录、不恢复或接管旧运行。显式不同目录、符号链接、损坏、未知状态和未决动作仍保守拒绝。
- 沿用原有岗位状态、原页、intent 和共享 claim 规则。被旧运行占用的相同岗位继续停止；只有已核验的不同目标才能进入新流程。
- 原件、答案、附件、页面和历史回执保持字节不变；真实身份与校验指纹只保存在外部私有证据，不写本地图。

## Ownership

- `src/career_evidence_graph/application_single_binding.py`
- `tests/test_application_single_binding.py`

执行者不独占代码库，不回退他人修改。根执行者保留 App/HTTP/原生装配所有权。

## Acceptance criteria

- [x] 全部旧岗位的 ID、完整笔记哈希和目标均匹配时，可只读判定其占用范围；相同旧岗位仍阻止。
- [x] 缺 ID/哈希/目标、任一漂移、显式不同目录、损坏、符号链接和未决状态的反例保持拒绝。
- [x] 无旧记录改写、目录迁移、自动重启、页面重建、释放其他 owner 或最终 Submit。

## Verification and evidence

使用合成旧 schema 做 RED→GREEN，比较旧文件前后字节；受影响专项与当前整体验证分别记录。独立审计核验其条件足以确定目标范围，不能用岗位标签猜测私人目录。

## Resolution comment

2026-10-17：由安装前具体兼容边界建立并领取。尚未实现或声称验收。

后续实现与独立审计已完成：仅缺失目录字段的 `run.json` 可通过全部岗位 ID、当前整份笔记哈希和规范化目标确定只读占用范围；相同目标仍阻止。字段显式为空/不同、任一漂移、未知动作、损坏和符号链接均拒绝；未改写、迁移或释放旧记录。

专项 **52 passed**；相关回归 **228 passed、34 deselected**；独立审计与反例 **58 passed**。冻结后的完整离线结果 **1972 passed、150 deselected / 214.26s**，全仓 Ruff check/format 与差异检查通过。本票按只读范围关闭；私人实例及校验数据不写本票。
