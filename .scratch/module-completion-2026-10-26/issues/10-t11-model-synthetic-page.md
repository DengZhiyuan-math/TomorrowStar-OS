# MC-10：T11.1 实际 Codex 与同一合成原页验收

Type: verification
Label: wayfinder:task
Status: claimed
Priority: P2
Interaction: HITL
Assignee: claude-code-367f651f/root
Created: 2026-10-26
Parent: [Module 剩余开发地图](../map.md)
Blocked by: [MC-09](09-t10-synthetic-chain.md)
Triage: awaiting-authorized-layered-acceptance

## 问题与范围

在适用真实模型运行授权内，验证本产品专用 app-server 的实际工具策略、结构化页面信息消费和同一 loopback Page 的闭环。不会因票进入机械 frontier 自动调用模型。

## 文件所有权与并行边界

使用 T01–T10 的真实实现与临时合成原页，私有记录不进入公共票；只改查明的必要配置。可在 MC-14/15 前对已冻结 checkout 验证；改动后受影响证明需更新。

共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [ ] 先只读及无副作用负例验证实际有效工具集合与旁路拒绝，不用配置声明、本聊天工具或空闲握手代证。
- [ ] 真实 Codex 不用截图，依据脚本返回的结构化页面信息（控件、状态、可见性/遮挡），通过同一产品工具操作 Worker 持有的原合成页；原 Page/线程/文档及材料身份可核对。
- [ ] 活动 turn 中断、实际页面动作在途排空及后端失联拒派发均有真实模型证据；无自动最终提交。
- [ ] 结果单独记录版本、运行范围、失败/限制；实际运行未获授权或无法执行时保留 open，不标通过。

## 既有证据与限制

[T11 第一层](../../../docs/module-interfaces-and-migration-design.md#t11-实际-codex签名-gui-与安装身份分层验收)。R6 零真实模型调用，不能填补本票证据。

需求以[正式设计](../../../docs/module-interfaces-and-migration-design.md)为准。R6 只证明原冻结源码与合成测试范围；本票如有新实现，
须记录实际改动、对应回归和审查，不能复用 R6 关闭新行为。未知结果、人工内容、原页、
原 journal 和历史记录保留，最终 Submit 手动。

## Comments

### 2026-10-28 认领（仅规划，Europe/Zurich）

按用户指示由 `claude-code-367f651f/root` 认领并先做计划。**尚无真实模型运行授权**：计划阶段不调用模型、不读取凭据、不安装 App、不访问真实 ATS；
实际运行须用户在了解范围、数据与费用后另行明确授权。最终 Submit 手动。

### 2026-10-28 用户决定 D1：不用截图

用户判断：由脚本返回 HTML 控件信息和位置信息比截图更可靠。验收条件 b 改为“不用截图，依据结构化页面信息操作原页”。
现有代码已如此：交接 `page_context`（id/name/role/label、校验错误、文档绑定）与驱动 `semantic_v2` refs（角色、名称、值、状态、可执行动作、
可见/遮挡/屏外）。位置由驱动内部计算并用于遮挡判断与按 ref 点击，不以坐标交给模型。计划见
`.scratch/remaining-tickets-2026-10-26/mc10-live-model/PLAN.md`。其余授权（版本固定、隔离 Codex 目录、真实运行次数）仍待用户决定。

### 2026-10-28 用户授权（按推荐）

用户回复“按推荐授权”，范围为：
1. 产品接受的 Codex 版本改为本机 `codex-cli 0.165.0-alpha.1.2`，先离线核对 app-server 协议（`generate-json-schema`，空 HOME）并重跑受影响的离线与受控原生测试；
2. 使用单独的干净 Codex 目录（无 AGENTS.md/skills/memories），由用户本人在其中登录；Claude 不读取凭据；
   正式 App（`macos/server.py` 使用 `Path.home()`）的同类问题记入 fog，本票不改；
3. 最多 6 次真实 Codex 会话（C0–C5，每次至多一轮，不自动重跑），只用本机合成 loopback 页面，允许连接模型服务商及已接受的 Chrome 后台连接；
4. 重跑须逐例另行同意。先完成离线部分，跑 C0 前提醒用户登录。最终 Submit 手动。

### 2026-10-28 暂停：真实运行由用户稍后统一进行

用户决定暂时跳过 Codex 真实测试，之后由用户统一测试。**未进行任何真实模型调用。** 已完成：
- 0.165 协议离线核对（`mc10-live-model/protocol-0.165-check.md`），版本固定改为 `0.165.0-alpha.1.2`；
- 修复：发给模型的交接文本不再包含后台进程路径（`backend_authority`，含用户名）；
- 测试侧防泄露检查、隔离目录检查、门控的 C0–C5 真实运行测试（默认不运行）；
- 空的隔离 Codex 目录 `~/Library/Application Support/TomorrowStar/mc10-codex-home`（尚未登录）。
未完成：真实运行测试的审核问题清单（见 `mc10-live-model/acceptance-s1/README.md`），真实运行 C0–C5，结案审核。票保持 claimed。

测试交接说明：`.scratch/remaining-tickets-2026-10-26/mc10-live-model/LIVE-TEST-GUIDE.md`（三个未解决问题与 C0–C5 测试内容）。
