# MC-22：决定并接通产品中的自动接管开关

Type: task
Label: wayfinder:grilling
Status: closed
Priority: P2
Interaction: HITL
Assignee: claude-code-4ca66ce5/root
Created: 2026-10-28
Parent: [Module 剩余开发地图](../map.md)
Blocked by: none
Triage: closed-source-synthetic

## 问题与范围

MC-08 按 criterion 5“产品默认开关仍关闭”结案（见 [2026-10-28 工作审计](../../work-audit-2026-10-28/README.md) 问题 3）。
`macos/server.py` 与 `career_portal.py` 都不传 `native_assistance_policy`，只有 runner 的 `--native-assistance-policy` 与测试开启，
因此安装 App 中脚本处理不了时不会自动派发 Codex 接管。MC-08 criterion 2 与设计 T09 最小交付写的却是“默认链自动发出一次接管请求”，
MC-09 整链测试也是显式打开开关后通过的。目前没有任何票负责在产品中打开它。

策略含 `driver_sha256`，绑定具体驱动构建；产品开启方式因此与安装 App 随附哪个驱动（MC-11）相关。

要决定：产品何时、以何种形式开启（默认开、用户设置、仅在 MC-10 实际模型证据后开），策略和驱动哈希从何处取得，以及如何接通。

## 文件所有权与并行边界

`macos/server.py`、`career_portal.py` 的接管配置组装及其测试；不改已验收的驱动与策略校验。
须在 MC-11 更新安装 App 之前完成；与 MC-20、MC-21 不共享文件时可并行（MC-21 同改 `macos/server.py` 的相邻配置，须串行集成）。
共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [x] 用户决定开启时机与形式，并记录在本票 Comments。
- [x] 产品配置按决定传入经校验的策略，驱动哈希来自安装 App 实际随附的驱动；哈希不符时 fail closed 并显示原因。
- [x] 回归覆盖：开启时 App 当前任务链自动请求一次接管；关闭或策略无效时不派发且不影响脚本填写。
- [x] 离线与受影响隔离浏览器通过，独立审查 READY；MC-17 清单同步；MC-11 验收条件据此核对 GUI 中的自动接管。

## 既有证据与限制

[MC-08 结案](08-t09-app-dispatch-controls.md#comments)、[MC-09 结案](09-t10-synthetic-chain.md#comments)。
本票不安装 App、不调用真实模型、不访问真实 ATS。最终 Submit 手动。

## Comments

### 2026-10-28 用户决定（Europe/Zurich，grilling 记录，`claude-code-4ca66ce5/root`）

已认领。事实：策略完全由代码常量决定（`validate_native_assistance_policy` 只接受审查过的驱动哈希、固定四个工具与 `insert_text`），后端可据此构造；
安装 App 既不传 `--codex-assist`（接管适配器未配置），后端也不传 `native_assistance_policy`；真实模型证据（MC-10）尚无。用户全部按推荐决定：

1. **时机**：先过 MC-10（真实 Codex 在合成页 C0–C5），再随 MC-11 安装版更新一起打开。
2. **形式**：默认开启，App 设置中一个“自动接管”开关可随时关闭（保存在现有 App 配置，不做逐岗位设置）；关闭时脚本处理不了的岗位停下等用户。
3. **不可用**（驱动哈希不符、专用目录未登录、找不到执行者等）：当前岗位停下并显示具体原因，不重试；用户处理后一次 Continue 继续（沿用 MC-08）。
4. **Claude 执行者**另开票（MC-23），在 MC-10 之后、MC-11 之前（2026-10-29 用户改为 MC-11 之后，见 [MC-23](23-claude-takeover-executor.md#comments)）；本票设置写明“执行者”，目前只有 Codex。
5. **选择**：设置中选一个执行者，所有岗位都用它；不可用时按 3 停下，不自动改用另一个。
6. **隐私**：Claude 执行者与 Codex 同等隔离（专用配置目录、不读用户 `~/.claude`、在该目录单独登录），未隔离不得启用。
7. **Claude 接入**：Claude Code 命令行 `claude -p`（独立执行者进程、只给四个页面工具、JSON schema 报告、启动核对工具清单、可中断），复用现有交接/准入/撤权/停止逻辑。
8. **登录与计费**：用户 Claude 订阅登录于专用 `CLAUDE_CONFIG_DIR`（如 `~/Library/Application Support/TomorrowStar/claude-home`），以 `--safe-mode` 运行。
9. **版本**：执行者只接受经过验证的版本；版本变化时接管按 3 停下，重新核对后放行（与 Codex 现做法一致）。

本票剩余实施：设置开关（默认开、可关）与执行者字段；开启时 App 以 `--codex-assist` 启动、后端按代码常量构造并传入策略；不可用原因显示到岗位。
源码可现在实施；安装版随 MC-11（在 MC-10 之后）生效。术语“自动接管 / 接管执行者”已写入 `CONTEXT.md`。

### 2026-10-29 结案（Europe/Zurich，`claude-code-4ca66ce5/root`）

**Resolution：** App 设置“自动接管…”（`portal.json` 的 `automatic_takeover`，缺省为开、不可读为关；`takeover_executor` 目前只有 `codex`）在单岗位真实模式下传
`--automatic-takeover --takeover-executor=codex`；后端以 `cua_driver.reviewed_native_assistance_policy()`（替换 Worker 内原有的同样构造）配置 Codex 适配器并交给 Worker。
执行者不支持、找不到 Codex、专用目录不可用、未登录或无法核对登录时不配置接管，后端照常运行，原因交给 Pipeline；脚本受阻且接管本应处理的岗位
（`takeover_candidate(..., hypothetical=True)`，与 `technical_blocker` 同一规则）停下并显示“自动接管不可用：原因……处理后重新打开工作台，再点一次 Continue 继续”。
关闭开关时不传任何参数，岗位照旧停下等待。驱动哈希：策略只接受代码中固定的审查过的驱动哈希，派发时核对安装 App 实际随附的驱动，不符即按既有能力失败停下并显示原因、不重试。

**验收**（[记录](../../remaining-tickets-2026-10-26/mc22-takeover-switch/acceptance/README.md)）：冻结 `f00eaedb…`（1828 文件）离线 8443/3/0；浏览器 r2 1 例并行负载失败（单独 3/3 通过，已记录不计入），
r3 380/8 native opt-in skip/0；`swiftc -typecheck` 全量 `App.swift` 通过，Swift 设置经编译测试工具验证。审查 r1 NOT-READY（5 项）→ 全部修复 → r2 READY-TO-CLOSE。
MC-17 清单（`docs/codebase-responsibilities.md`、`docs/current-index.md`）与 `CONTEXT.md` 术语已同步；MC-11 已补充核对条件。

**生效与留存：** 代码里自动接管默认开启，但只在 MC-11 安装版更新时生效，而 MC-11 排在 MC-10 真实模型验收之后（决定 1 由安装顺序保证，代码中无 MC-10 门槛）。
审查 P3：未知执行者值只截断不去控制字符；两次核对之间目录变化会被报为“未登录”（几乎不可达）。未运行真实模型、native、安装 App 或真实 ATS。最终 Submit 手动。
