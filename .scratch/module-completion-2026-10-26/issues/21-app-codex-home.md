# MC-21：正式 App 的 Codex 使用专用目录而非用户本人 HOME

Type: task
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: HITL
Assignee: claude-code-4ca66ce5/root
Created: 2026-10-28
Parent: [Module 剩余开发地图](../map.md)
Blocked by: none
Triage: closed-source-synthetic

## 问题与范围

MC-10 规划时发现（见 [MC-10 计划](../../remaining-tickets-2026-10-26/mc10-live-model/PLAN.md) B2、
[2026-10-28 工作审计](../../work-audit-2026-10-28/README.md) 问题 4）：`macos/server.py` 组装 Codex 接管配置时
以 `"home": str(Path.home())` 作为 Codex `HOME`，用户 `~/.codex` 下的个人 AGENTS.md、skills、memories、rules、config.toml
可能进入模型上下文，违反只用申请所需数据的边界。MC-10 只在测试中改用隔离目录，正式 App 未改。

## 文件所有权与并行边界

`macos/server.py` 的 Codex 配置组装及其测试；必要时 `application_codex_assist.py` 的目录检查。
须在 MC-11 更新安装 App 之前完成；与 MC-20、MC-22 不共享文件时可并行。
共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [x] 正式 App 使用 `~/Library/Application Support/TomorrowStar/` 下的专用 Codex 目录（与 MC-10 的隔离目录约定一致或说明差异），不再使用 `Path.home()`。
- [x] 目录不存在或未登录时，接管按“能力不可用”停止并给出用户可执行的登录说明，不回退到用户本人 HOME。
- [x] 回归覆盖：配置中的 HOME 不是用户 HOME；专用目录中出现 AGENTS.md/skills/memories 等个人配置时按 MC-10 隔离检查处理。
- [x] 用户本人在专用目录中登录（HITL）；agent 不读取凭据。
- [x] 离线与受影响隔离浏览器通过，独立审查 READY；MC-17 清单同步。

## 既有证据与限制

测试侧隔离检查已在 MC-10 准备中实现（`tests/codex_live_guards.py`），可复用。本票不安装 App、不调用真实模型。最终 Submit 手动。

## Comments

### 2026-10-28 认领与用户决定（Europe/Zurich）

由 `claude-code-4ca66ce5/root` 按用户“继续推进 Module 主线”认领。只读核对发现：除接管适配器外，App 的普通模型调用
（`codex_cli.run_codex_exec`，简历写作、匹配等 6 处调用）也把用户真实 `HOME`/`CODEX_HOME` 传给 Codex，且未禁用 plugins/MCP/hooks。
**用户决定：两条路径都改用同一个专用目录**（`~/Library/Application Support/TomorrowStar/codex-home`），缺失或含个人上下文时停止，不回退到 `~/.codex`。

另查明（本机 `codex-cli 0.165.0-alpha.1.2`，空 HOME 下 `codex login status` → “Logged in using ChatGPT”）：登录来自系统钥匙串/ChatGPT 应用，
不在 `HOME/.codex`；改 HOME 隔离 AGENTS.md、skills、memories、rules 与 config，但不改账号，预计用户**无需重新登录**。
`memories` 为默认开启的稳定功能，App 自身运行会在专用目录积累记忆并进入后续岗位；本票同时在两条路径禁用 `memories`。

### 2026-10-28 更正与审查 r1 NOT-READY（Europe/Zurich）

**更正上条“无需重新登录”：错误。** 当时 shell 带有 `CODEX_HOME=<用户 ~/.codex>`，Codex 读到了用户本人的登录。去掉该变量后，空 HOME 为
“Not logged in”（独立审查与本会话复核一致）。登录存放在 HOME 下（`auth.json`），**用户须在专用目录登录一次**，criterion 4 必需。
同时更正“memories 默认开启”：新目录中该功能默认关闭，禁用参数无害。

独立审查 r1 NOT-READY：P1 登录观察错误；P1 失败时用户得不到可执行的登录说明；P2 校验漏掉 `AGENTS.override.md`、`config.toml`
（developer_instructions、MCP）、`hooks.json`、`prompts`、`.codex`/`skills/.system` 符号链接，`exec` 未用 `--ignore-user-config`/`--ignore-rules`；
P2 `account_context_revision` 仍取用户 `~/.codex`；P3 拒绝目录时 `--codex-assist` 使整个后端退出、建目录失败亦然；`application_match_refresh` 参数上限证明会多算新参数。
首轮 offline/browser 门禁因需改源码而中止（`mc21-codex-home/acceptance/` 中保留，不计入）。

修正（均先 RED 后 GREEN）：校验补齐上述条目与符号链接；`exec` 加 `--ignore-user-config`、`--ignore-rules` 并禁用 memories/apps/plugins/hooks；
设置专用目录时 `exec` 先运行 `codex login status`，未登录即停止，错误信息给出登录命令并保留其输出（`match` 路径据此归为 `match_cli_auth_required`）；
`account_context_revision` 改读专用目录；后端在目录不可用时不配置接管、不退出，环境变量照常设置使模型调用在校验处停止；参数上限证明不计入新隔离参数。
`app-server` 不支持 `--ignore-user-config`，接管侧依赖校验拒绝 `config.toml`。界面仍只显示各步骤原有的通用失败文案，登录命令在错误记录与文档中。
`tests/codex_live_guards.py`（MC-10 所有）保留其独立检查，未改。

### 2026-10-28 审查 r2 NOT-READY 与修正（Europe/Zurich）

门禁 r2：离线 8399 passed / 3 skipped / **12 failed**（合成 mail/preparation），浏览器未运行；r3 因再改源码中止。均保留，不计入。
审查 r2 NOT-READY：P1 合成模式也设置专用目录，登录检查对只支持 `--version`/`exec` 的合成 CLI 失败；P2 接管无登录检查；
P2（推断）若目录中以后出现 `config.toml` 等，worker 启动时整体失败而非只停接管；P3 错误信息中的 `codex` 不在 PATH，应写实际可执行文件路径。
修正：专用目录只在真实模式设置（合成模式已替换 HOME、用合成 CLI 且禁止 `--codex-assist`）；后端在 `--codex-assist` 时启动核对一次登录
（`codex_cli.require_codex_sign_in`），未登录不配置接管；错误信息写出实际可执行文件路径。worker 启动时因目录被污染整体停止的情况作为已知限制保留
（fail closed；正常 `codex login` 只写 `auth.json`，交互式 `codex` 界面可能写 `config.toml`，因此登录说明只用 `login` 子命令）。

### 2026-10-28 晚：门禁状态与独立审计（Europe/Zurich）

审查 r3（同一审查者复核 r2 修正）READY-TO-CLOSE（仅余用户登录）。门禁：冻结 `76286ceb…`（1828 文件）离线 r4 **8413 passed / 3 skipped / 0 failed**；
浏览器 r4 1 个 setup error（`test_worker_stability…[release]`，单独重跑 3×4 通过，判为并行负载时序，见 `browser-r4-diagnosis/`）；
浏览器 r5 第三分区在 `test_supplemental_materials.py::test_old_required_material_does_not_block_current_optional_field[True]` 100% CPU 空转约 3 小时后停止
（现场与复现见 `browser-r5-hang/`；单独 20 次全部通过，按原分区顺序复现进行中）。浏览器门禁因此尚未通过，本票保持 claimed。

独立审计（只读）NEEDS-WORK（非代码缺陷）：冻结与当前工作区逐字节一致；全部 App 模型调用经 `run_codex_exec` 继承环境，真实模式 worker 继承，接管只用配置 HOME，无回退路径。
另记：`build_codex_exec_argv` 为全局，**研究/校准 CLI**（`cli.py`、`scripts/run_interview_calibration.py`、`audit/decision.py`）也会忽略用户 config/rules 并禁用 apps/plugins/hooks/memories（仍用用户 HOME）；
检出版 `career_portal` 启动器不设置专用目录，仍用 `~/.codex`（本票范围为安装 App）；`account_context_revision` 切换后邮件入口会一次性重新绑定；
`tests/codex_live_guards.py`（MC-10）是较弱的重复校验，MC-10 宜改为调用 `validate_codex_home`；MC-10 的 `mc10-codex-home` 与本票 `codex-home` 是两个目录、需各自登录。
`application_preparation.py` 直接写常量名、`_EXEC_DISABLED` 定义在使用之后为小问题。上述 P3 与后端启动登录检查只捕获 `CodexCLIError` 一并留待下一次改动这些文件时处理。

关闭前仍需：浏览器门禁通过（或在新冻结上重跑）、用户在专用目录登录一次、最终审查、MC-17 清单核对。

### 2026-10-28 浏览器门禁 r6 通过（Europe/Zurich）

加固后的浏览器门禁 r6（单测 5 分钟栈转储、分区 40 分钟上限）在同一冻结 `76286ceb…` 上 **380 passed / 8 native opt-in skips / 0 failed**，运行前后无漂移
（[验收记录](../../remaining-tickets-2026-10-26/mc21-codex-home/acceptance/README.md)）。自动验收完成；本票仅待用户在专用目录登录一次，核对 `login status` 后结案。

### 2026-10-28 后续覆盖（Europe/Zurich）

脱敏工作改动了 `application_information.py` 与若干测试，本票冻结 `76286ceb…` 因此不再等于当前字节；脱敏门禁冻结 `5aedeec3…` 包含本票全部工作区改动，
离线 8428/3/0、浏览器 380/8 skip/0，覆盖本票当前字节。仍待用户在专用目录登录。

### 2026-10-28 结案（Europe/Zurich，`claude-code-4ca66ce5/root`）

**Resolution：** App 的全部 Codex 模型调用（`codex_cli.run_codex_exec`）与接管适配器共用专用目录 `~/Library/Application Support/TomorrowStar/codex-home`
作为 HOME（用户决定两条路径都改），不再读取用户本人的 `~/.codex`。`codex_cli.validate_codex_home` 按条目名拒绝个人上下文（AGENTS.md/AGENTS.override.md、
config.toml、hooks.json、prompts、skills 除 `.system`、memories、rules、`.agents`、符号链接）；`codex exec` 先核对该目录已登录，未登录即停止并在错误中给出含实际路径的登录命令，
并以 `--ignore-user-config`、`--ignore-rules` 运行、禁用 memories/apps/plugins/hooks；接管禁用 memories；后端在目录不可用或未登录时不配置接管而不退出；
合成模式不设置该目录；`account_context_revision` 改读专用目录。

**验收：** 冻结 `76286ceb…` 离线 8413/3/0、浏览器 r6 380/8 skip/0；其后脱敏冻结 `5aedeec3…`（含本票当前字节）离线 8428/3/0、浏览器 380/8 skip/0。
审查 r1/r2 NOT-READY → r3 READY；独立审计确认无回退路径。**用户已于 2026-10-28 在专用目录登录**：`login status` 为已登录，目录仅含 `.codex/{auth.json,log,tmp}`，
`validate_codex_home` 与 `require_codex_sign_in` 均通过；agent 未读取凭据内容。MC-17 清单（`docs/codebase-responsibilities.md`、`docs/data-boundaries.md`）已同步。

**范围说明与留存：** 界面仍显示各步骤原有的通用失败文案，登录命令在错误记录与文档中；研究/校准 CLI 也受新的 exec 参数影响但仍用用户 HOME；
检出版 `career_portal` 启动器不设置专用目录；后端启动登录检查只捕获 `CodexCLIError`（超时或启动 OSError 仍可能停止后端，仅在 `--codex-assist` 时）；
`tests/codex_live_guards.py`（MC-10）为较弱的重复校验，宜改调 `validate_codex_home`；MC-10 的 `mc10-codex-home` 需另行登录。这些已记入地图 fog。
未运行真实模型、native、安装 App 或真实 ATS。最终 Submit 手动。
