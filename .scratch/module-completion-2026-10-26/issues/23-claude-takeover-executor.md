# MC-23：Claude 作为接管执行者

Type: task
Label: wayfinder:task
Status: open
Priority: P2
Interaction: HITL
Assignee: none
Created: 2026-10-28
Parent: [Module 剩余开发地图](../map.md)
Blocked by: [MC-10](10-t11-model-synthetic-page.md), [MC-22](22-product-native-assistance-policy.md)
Triage: needs-implementation

## 问题与范围

用户在 [MC-22 决定](22-product-native-assistance-policy.md#comments) 中要求接管执行者可选 Codex 或 Claude。按决定 4–9：设置中只选一个执行者，不自动换用；
Claude 经 Claude Code 命令行 `claude -p` 接入，复用现有执行者无关的交接、准入、撤权、停止与报告校验逻辑，只新写执行者专有部分（启动参数、传输、工具清单核对、报告捕获、中断）。

已查明（2026-10-28 只读调研）：Worker 只依赖适配器的 `start_takeover`、`progress`、`stop`、`service_readonly`、`close` 与进度字段；执行者专有代码约 550 行，执行者无关约 750 行。
`claude -p` 具备 `--tools ""`、`--mcp-config` + `--strict-mcp-config`、`--allowedTools`、`--json-schema`（结果在 `structured_output`）、`--max-turns`、`--system-prompt`、
`--setting-sources`、`--no-session-persistence`、`--safe-mode`；`system/init` 列出工具与 MCP 服务，可替代 Codex 的配置核对；SIGINT 正常结束一轮。

## 文件所有权与并行边界

新增 Claude 适配器；将执行者无关部分从 `application_codex_assist.py` 提到共享位置（替换，不复制）；设置与配置管道沿用 MC-22 的执行者字段。
共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [ ] 先写失败回归；执行者无关逻辑抽出后 Codex 行为不变（既有离线、浏览器与 native 证据复跑）。
- [ ] Claude 执行者：只暴露四个页面工具、无内置工具、`system/init` 核对工具清单与 MCP 服务，报告按同一 schema 校验，中断与停写语义与 Codex 一致。
- [ ] 隔离：专用 `CLAUDE_CONFIG_DIR`（如 `~/Library/Application Support/TomorrowStar/claude-home`）、`--safe-mode`、显式 `--system-prompt`；按条目名拒绝个人上下文；用户在该目录本人登录（HITL），不读取凭据。
- [ ] 版本固定：只接受经过验证的 Claude Code 版本，版本变化时接管停下并说明原因。
- [ ] 核实 MCP 代理的直接父进程是 Claude 执行者进程（`verify_native_handoff_recipient`），否则调整身份检查并复审。
- [ ] 无 turn id 时以 session/result 标识绑定 `native_turn_id`，相应报告与测试更新。
- [ ] 离线、受影响浏览器与 native 通过，独立审查 READY；真实 Claude 在合成页验收（同 MC-10 的 C0–C5 形式，需用户另行授权）。

## 既有证据与限制

不调用真实模型、不安装 App、不访问真实 ATS，除非用户另行授权。最终 Submit 手动。

## Comments

### 2026-10-29 用户决定：暂缓，不阻塞 MC-11（`claude-code-4ca66ce5/root`）

用户回复“跳过 MC-23”。本票保持 open、未领取，改为 MC-11 之后的后续工作；MC-11 不再以本票为前置。

