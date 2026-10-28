# MC-15：M6 后端投影、调用兼容与运行身份

Type: task
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: claude-code-367f651f/root
Created: 2026-10-26
Parent: [Module 剩余开发地图](../map.md)
Blocked by: [MC-14](14-m5-runtime-portal.md)
Triage: closed-source-synthetic

## 问题与范围

后端装配稳定后迁移默认 UI 与 App/Codex 实际调用兼容，核对新文件打包与 loaded roles。GUI 实际安装验收留 MC-11，不倒置成实现前置。

## 文件所有权与并行边界

portal_static/application_flow.js 等必要 UI、career_portal.py 投影、loaded_code.py 和打包清单。UI 与 loaded roles 可明确文件后并行；同一集成快照与浏览器验收必须冻结。

共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [x] 默认 UI 消费后端业务投影，不自行判断准备/接管/未知/完成；两类实际 App/Codex 调用者均走所属 Interface。
- [x] 旧 snapshot/JSON/HTTP/CLI 兼容和历史任务恢复保持，保留人工修改及精确错误。
- [x] 新实现纳入对应真实 loaded role 和包清单，测量前加载约束正确；不以代码测量代替 GUI 或模型验收。
- [x] 新投影和兼容路径的离线/隔离浏览器回归、身份与打包检查通过，默认写入仍受实际验收门控。

## 既有证据与限制

[M6 契约](../../../docs/module-interfaces-and-migration-design.md#迁移顺序)、[AC14 身份切片](../ac14-identity.md)。旧 41 号票原状态/负责人保留。

需求以[正式设计](../../../docs/module-interfaces-and-migration-design.md)为准。R6 只证明原冻结源码与合成测试范围；本票如有新实现，
须记录实际改动、对应回归和审查，不能复用 R6 关闭新行为。未知结果、人工内容、原页、
原 journal 和历史记录保留，最终 Submit 手动。

## Comments

### 2026-10-28 认领（Europe/Zurich）

`scripts/query_tickets.py` 核对：MC-14 已结案，本票为机械前沿，open/unassigned。按用户指示由 `claude-code-367f651f/root` 认领，
与 MC-15/MC-19 并行规划；尚无源码改动或测试运行。不扩展实际模型、安装 App 或真实 ATS 权限；最终 Submit 手动。

### 2026-10-28 用户决定（Europe/Zurich）

计划见 [MC-15 计划](../../remaining-tickets-2026-10-26/mc15-projection/PLAN.md)，用户全部按建议确认：页面状态投影放入新的小文件
`application_flow_view.py`，由 Runtime 装配；运行中的 Codex 接管不加 Dock 徽标，只在窗口内显示“已交给 Codex 接续”，不改 App 原生代码；
允许为合成测试模式新增两个可选启动设置；页面旧的本地规则与后端不一致时以后端为准并逐项记录；安装版 App 留待 MC-11 重建安装。
与 MC-19 在主 checkout 并行开发，最后同一冻结共同验收、分别独立审查；`docs/codebase-responsibilities.md` 与设计文档由 root 最后统一更新。

### 2026-10-28 验收与限制记录（结案前，供复审核对）

首轮联合冻结 `a179bbef…` 经独立审查 NOT-READY（P2：运行身份覆盖只证明了探测路径；开放点与页面差异未记入正式记录）。已先写失败回归修复并重新冻结：
1825 文件 `2374b341…`；完整默认离线 8368：8365 passed / 3 skipped / 0 failed；受影响隔离浏览器 382：374 passed / 8 native opt-in skips / 0 failed
（[联合验收](../../remaining-tickets-2026-10-26/mc15-mc19-joint/acceptance/README.md)，首轮审查 [review-mc15](../../remaining-tickets-2026-10-26/mc15-mc19-joint/acceptance/review-mc15.md)）。

修复：`tests/test_loaded_role_coverage.py` 新增 AST 静态扫描（含函数内延迟导入；控制器按本角色严格传递可达，worker 仅要求“属于某一角色”）——延迟导入的写路径模块
`application_experience_content`、`application_content_reconcile`、`application_material_packet`、`resume_template`、`chrome_registration` 与控制器进程内的
`application_form_state` 已入角色；`workspace`、`validation.store` 由豁免改为计量；`public_site`、`validation.models` 仍豁免并收紧理由（冻结模型 `__hash__`
闭包在 python-loaded-code/v1 中不可规范化，其契约作为导入模块的 `model_policy` 记录计量）。`tests/test_flow_view.py` 的恒真检查改为与改动前输出逐键顺序与取值比对。

**页面行为差异（用户决定 4：以后端为准、逐项记录）：**
1. 运行中的 Codex 接管：流程面板显示“已自动交给 Codex 接续原页”（此前通知为空、无显示）；App Dock 通知不变。
2. 活动状态来源：页面按后端 `preparation_activity` 判断“运行中/需核对”，与保存的 `task.stages` 不一致时以后端为准（当前后端规则相同，不会出现分歧）。
3. `preparation_activity` 缺失或属于其他任务时，页面按“需核对”处理：写入控件保持禁用、不显示运行中。
4. 等待通知文本不变但改从 `pipeline.notice` 读取；只带 `notification` 而无 `notice` 的响应将不在流程面板显示文本（当前后端不会如此）。
5. 概览卡（`app.js:316`）仍读取 `pipeline.notification`，因此**不显示**接管提示。

**仍由页面本地判断的规则（criterion 1 部分满足，留作后续）：**`application_flow.js` 816-818（自行查找首个 needs_recheck 阶段以命名）、708、794、195 与
819 起的 `task.status` 链，以及 741、746、779、784、786、821、824、830、831、1328、1360、1369、1438 处对具体阶段状态的直接读取（行号按冻结 `2374b341…`）；新增的 `state.progress` 暂无 UI 使用者。
可由后续票把“未决阶段名称”等投影字段补齐后替换。

**开放点（未分配后续票）：** App 不识别服务端错误码 `single-flow-required`（`--codex-assist` 在单岗流程外使用时显示通用 `invalid_ready_response`，修复需改 App.swift）；
`app.js` 概览卡改读 `notice`；`public_site`/`validation.models` 的规范化器支持；`--synthetic-mail` 的 LaTeX 基线路径只经 AST 检查间接覆盖；
`notice` 复制通知文本使 App 轮询体略增（App 拒收 >64 KiB，风险低）。安装版 App 未更新，变更经 MC-11 重建安装后生效。

### Resolution（2026-10-28，Europe/Zurich）

冻结 1825 文件 `2374b341…`：离线 8365 passed / 3 skipped / 0 failed；浏览器 374 passed / 8 native opt-in skips / 0 failed；补跑 `test_installed_readiness_browser.py` 6 passed。
复审 [review-mc15-r2](../../remaining-tickets-2026-10-26/mc15-mc19-joint/acceptance/review-mc15-r2.md)：首轮 P2 已解决（控制器角色覆盖、页面差异与开放点记录），
余下一项 P2 按审查给出的“只改记录”选项处理：**worker 角色覆盖缺口**——worker 进程在填写时经 `store.material_inputs`/`store.verify_material`
惰性导入 `application_match`、`application_resume`、`application_material_sources`，三者不在 worker 角色内，worker 启动时记录的身份未覆盖材料核验代码；
该缺口早于 MC-15。worker 覆盖检查只要求“属于某一角色”，`tests/test_loaded_role_coverage.py` 的文档字符串与注释所称“worker 从不加载”的说法过宽（冻结文件，未改动），
随后续修复一并更正。后续办法：worker 预加载并加入角色（需新冻结与原生/浏览器复核）。另：`application_preparation_fixtures`（合成模式由 `macos/server.py` 载入控制器）
未列入角色或豁免，应按 `application_worker_fixtures` 同理豁免。以上记入地图 fog。实现与验收要点见上方“验收与限制记录”；安装版 App 经 MC-11 更新后生效；未提交 git。
