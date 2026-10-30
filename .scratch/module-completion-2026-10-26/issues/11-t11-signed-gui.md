# MC-11：T11.2 唯一签名 App 新接管链验收

Type: verification
Label: wayfinder:task
Status: open
Priority: P2
Interaction: HITL
Assignee: claude-code-4ca66ce5/root
Created: 2026-10-26
Parent: [Module 剩余开发地图](../map.md)
Blocked by: [MC-10](10-t11-model-synthetic-page.md), [MC-15](15-m6-ui-compatibility-identity.md), [MC-20](20-worker-role-coverage.md), [MC-21](21-app-codex-home.md), [MC-22](22-product-native-assistance-policy.md)
Triage: installed; awaiting-GUI-checks

## 问题与范围

单独验收本轮新接管链在唯一主 App 的实际 GUI 环境。实际模型证据 MC-10 与 Runtime/UI 交付 MC-15 均完成后才进入本层；GUI 验收不反向阻塞实现。

## 文件所有权与并行边界

macos/App.swift、macos/main_app.py、macos/build.py、loaded_code.py 仅查明缺口时联动；保持固定 bundle/signing/TCC 身份。不能和运行包的维护/安装改动并发，不创建第二个 .app。

共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [ ] 在已授权的维护/验收范围从 Finder/LaunchServices 启动，验证真实登录、工具宿主、原页与实际所需权限。
- [ ] 包身份和实际加载源码对应；新链的退出/重开、停写和原占用均实测，不用 shell 仿真或摘要吻合代证 GUI。
- [ ] 核对 MC-10 的实际模型/工具策略证据仍适用于本次最终候选；相关装配、配置、入口、工具或运行身份变化时补验受影响层，不能只凭 MC-10 已关闭跳过核对。
- [ ] 必要更新仅沿 main_app.py 的唯一主 App 流程，保留配置、私人资料、历史、回退；不例行重置 TCC。
- [ ] 自动接管（MC-22）：安装版“自动接管…”菜单开关默认开启；脚本受阻时自动接管一次；关闭后岗位停下等待；接管不可用时岗位显示具体原因。
- [ ] MC-10 交接：安装版随附单一 native driver successor-r3-signed（SHA256 `ba1541e7…`，脚本与接管共用，与产品固定哈希一致；2026-10-29 用户决定，取代原写的 successor-r2 `eb298be3…`）；`thread/start` 单独 15 s 上限（已实现）。
- [ ] 实际未运行项与失败明确记录，第一层模型验证不外推 GUI；旧安装票的原成果与负责人保持。

## 既有证据与限制

[T11 第二层](../../../docs/module-interfaces-and-migration-design.md#t11-实际-codex签名-gui-与安装身份分层验收)。建票时不授权或执行安装（2026-10-29 用户已授权并完成安装，见 Comments）。

需求以[正式设计](../../../docs/module-interfaces-and-migration-design.md)为准。R6 只证明原冻结源码与合成测试范围；本票如有新实现，
须记录实际改动、对应回归和审查，不能复用 R6 关闭新行为。未知结果、人工内容、原页、
原 journal 和历史记录保留，最终 Submit 手动。

关联历史范围：[原安装材料接受票](../../gmail-resume-preparation-2026-10-17/issues/25-installed-real-job-full-cv.md)；其原状态、负责人和接受结论保留。

## Comments

### 2026-10-28 新增前置（Europe/Zurich）

依据 [2026-10-28 工作审计](../../work-audit-2026-10-28/README.md) 问题 3、4，经用户同意，把原记在地图 fog、标“建议在 MC-11 前处理”的三项建为票并加入 Blocked by：
[MC-20 worker 运行身份覆盖](20-worker-role-coverage.md)、[MC-21 正式 App 专用 Codex 目录](21-app-codex-home.md)、
[MC-22 产品自动接管开关](22-product-native-assistance-policy.md)。原状态、认领与验收条件不变。

### 2026-10-29 依赖调整（`claude-code-4ca66ce5/root`）

用户决定“跳过 MC-23”：Claude 执行者不再阻塞本票，Codex 一条接管路线先装入安装版使用（一般场景先跑通、边用边优化）。
进入本票前先修 Codex 请求超时（thread/start 实测约 5 s，产品默认 2 s）。实际安装／更新 App 前另行取得用户授权。
- 前置已完成：`thread/start` 单独 15 s 上限（其余请求 2 s），离线 8473/3/0、浏览器 380/8/0、受控 native 25/1/0，审查 READY。安装时仍须核对 `codex --version` 冷启动是否超出 2 s。
- 2026-10-29 单一 driver（用户决定“只带新版 driver”）：安装版随附 successor-r3-signed `ba1541e7…`（release、keychain 补丁、固定私有身份签名），脚本与接管共用；
  `macos/build.py` 记录其来源。冻结 `ae37d4a9…`：离线 8475/3/0、浏览器 380/8/0、受控 native 25/1/0；审查 r1 NOT-READY（缺 keychain 补丁、ad-hoc 签名）→ r2 READY。
  脚本路径真实 driver：填写到 ready_for_review 成功；“最小化”断言新旧 driver 同样失败（测试期望过时）；worker 停止退出 >10 s（无旧基线）。安装时观察。

### 2026-10-29 安装版已更新（`claude-code-4ca66ce5/root`）

用户回复“授权构建并安装”。按 `docs/macos-app.md` 流程（主 App 运行前已确认退出；证据在私人 `~/Library/Application Support/TomorrowStar/maintenance-2026-10-29-mc11/`，不进仓库）：

1. `macos/build.py --cua-driver successor-r3-signed` → `builds.noindex/TomorrowStar.bundle-candidate`（构建时工作区与提交 `49924cd5` 一致、干净）。
2. `macos/verify.py`：exit 0；签名、重定位、捆绑运行时与入口、CSRF、父进程 EOF 关闭等全部 passed，未用个人数据；包内 driver 记录为 `ba1541e7…` 及后继来源。
3. `main_app.py check`：主 App 指定要求与固定身份均验证通过，未改 App。
4. `main_app.py update`：回退副本已验证、配置不变、权限未改、未启动 GUI，`main_app_updated: true`；安装版 driver 为 `ba1541e7…`，`codesign --verify --deep --strict` 通过。
5. `check_main_permissions.py`：exit 0；辅助功能、屏幕录制均为实际已授权，责任链验证通过，仅非提示检查，未建浏览器，进程全部退出。

本票剩余：从 Finder 启动后的真实使用核对（Codex 专用目录登录、自动接管开关默认开、脚本受阻时自动接管一次、关闭时停下、不可用时显示原因）、
退出／重开与停写实测；`codex --version` 冷启动 2 s 是否足够待观察。最终 Submit 手动。

### 2026-10-29 审计补记（`claude-code-4ca66ce5/root`）

已领取（此前已改 `macos/build.py` 并安装）。依[工作审计](../../work-audit-2026-10-29/README.md)：
- MC-10 的实际 Codex 运行全部用 debug driver `eb298be3…` 与源码 `c98544fe`；安装版的 `ba1541e7…`（release、keychain 补丁、签名）与 `0da8c1b6` 的 thread/start 改动只有受控 native（25/1/0）证据，
  尚无实际 Codex 运行。按criterion 3，GUI 实际使用中的接管即为其首个实际证据；若接管异常，先核对这一差异。
- MC-14 要求的“更新 App 前原生跑 `test_worker_native_chain_browser.py`”已满足：native-r10 的 01–03 在冻结 `ae37d4a9…`（= `49924cd5`）上通过。

### 2026-10-29 晚：安装版 driver 的首次实际运行（`claude-code-4ca66ce5/root`）

用户“提交并跑 C0+C1”。源码 `35acdbb9`（回报规则统一到 JSON Schema），driver `ba1541e7…`（与安装版相同字节）：实际 C0 r7、C1 r4 均通过；
服务接受新回报 schema，回报经 Adapter 留下且 Worker 采纳。补上了审计 E4 指出的“安装版 driver 无实际运行”缺口。
**安装版仍是 `49924cd5` 构建，不含 `35acdbb9` 的回报规则修正**；要生效需重新构建并更新（另需授权）。

### 2026-10-29 晚：安装版第二次更新（`claude-code-4ca66ce5/root`）

用户“授权更新 App”。同一流程（私人证据 `maintenance-2026-10-29-mc11-r2/`）：上次的候选包（与当时安装版相同）移入废纸篓后，以 `09f1249f`（代码同 `35acdbb9`）构建；
`verify.py` 全部通过、未用个人数据；`main_app.py check` 通过；`update` 成功（回退副本已验证、配置与权限未改、未启动 GUI）；`check_main_permissions.py` exit 0
（辅助功能、屏幕录制已授权，责任链验证，未建浏览器）。安装版现含回报规则修正（`application_codex_assist.py` `423b1aaa…`）与 driver `ba1541e7…`。
剩余：GUI 实际使用核对。

### 2026-10-29 GUI 试用发现：旧流程上“继续当前岗位”无效（`claude-code-4ca66ce5/root`）

用户试用报告：App 启动／退出／重开正常；自动接管默认开启、关闭后重开保留；点“继续当前岗位”两次均提示“请使用当前岗位操作”，流程未恢复。

- 核实：本机流程为 2026-10-20 建立的旧流程（`pipeline.json` 无 `queue_mode`，`blocked`／`paused`）。界面只要流程有 id 就调用 `continue`，
  而 `continue` 只接受队列流程（`_current_request` 要求 `queue_mode`）。旧流程应走 `start`（可重启时归档旧流程并开新队列流程，否则说明原因）。
- 修复（未提交）：`application_flow.js` 按 `pipeline.queue_mode` 选 `continue`／`start`；新浏览器测试 RED→GREEN；两个模拟队列流程的旧测试补 `queue_mode`。
  冻结 `d9c26e8f…`：离线 8494/3/0、浏览器 382/8/0。
- **另一真实阻塞（需用户处理，未改动其数据）**：只读查明 `single-job-worker` 中 2026-10-17 的岗位仍为 `needs_recheck／checkpoint_unavailable` 且带结果未知的动作；
  `_can_restart` 因此拒绝重启。修复后按钮会显示“原自动流程仍有记录，请先核验其进度”。（更正：并非任选结论即可解锁——`manual_stop` 只记录结论、保留未知 `intent`，重启仍被挡。）唯一现有路径须有证据：取消该岗位 → 为未知 `fill` 保存 `current_matches` 或 `not_applied` 及已核验来源 → “结算已取消岗位”（清除 intent、留作历史）→ 之后 `start` 归档旧流程并开始新周期（不续填旧岗位）。该岗位为 Workable 上的旧申请，原页已关闭、未人工提交；能否给出 `not_applied` 的证据由用户核验，不改 JSON、不宣称动作成功。
- 实际 Codex 接管、关闭后停写、不可用原因提示仍未测到。

### 2026-10-29 安装版第三次更新（`claude-code-4ca66ce5/root`）

用户“提交并更新 App”。修复提交为 `736116aa`；用户退出 App 后按同一流程更新（私人证据 `maintenance-2026-10-29-mc11-r3/`）：构建、`verify.py`、`main_app.py check`、
`update`（回退副本已验证、配置与权限未改、未启动 GUI）、`check_main_permissions.py` 均 exit 0。安装版 `application_flow.js` 为修复版（`d5042395…`），driver `ba1541e7…`。
下一步由用户：按证据处理 Workable 旧岗位（取消 → 有来源的结论 → 结算）后，用“继续当前岗位”开始新流程，再测实际接管。

### 2026-10-29 GUI 试用：Gmail 收录被 MC-21 的 `--disable apps` 挡住（`claude-code-4ca66ce5/root`）

用户试用报告（私人：`~/Library/Application Support/TomorrowStar/test-reports/2026-10-29-mc11-gmail-intake/`）：旧岗位按证据取消并结算（复用同一 intent 的历史 `current_matches`），
修复版“继续当前岗位”归档旧流程、新队列启动；随后 Gmail profile 返回 `unavailable / mailbox_identity_unavailable`，流程停在 `needs_input / mail_capture_incomplete`，后续接管用例未执行。

- 根因：`fdc403f1`（MC-21）让所有 `codex exec` 带 `--disable apps`；Gmail 调用经 `--config features.apps=true` 只开放其连接器，被后附的 `--disable apps` 覆盖，模型无 Gmail 工具。
- 修复（未提交）：`application_gmail.py` 三处相同的参数包装合并为 `_connector_argv`，插入连接器覆盖并去掉 `--disable apps`；其余调用仍关闭 apps，Gmail 调用仍关闭 memories／plugins／hooks。
  新测试 RED→GREEN（search 与 profile 两次 exec）；本地 `codex features list`（无模型）对照：修复后 apps true、其余 false。冻结 `babfa6d6…`：离线 8495/3/0、浏览器 382/8/0。
- 要生效需更新安装版；真实 Gmail 读取须在 App 中由用户重测。

### 2026-10-29 安装版第四次更新（`claude-code-4ca66ce5/root`）

用户“授权更新 App”。以 `380c5f43` 构建，用户退出 App 后更新（私人证据 `maintenance-2026-10-29-mc11-r4/`）：构建、`verify.py`、`main_app.py check`、
`update`（回退副本已验证、配置与权限未改、未启动 GUI）、`check_main_permissions.py` 均 exit 0。安装版 `application_gmail.py` 为修复版（`fed71921…`），driver `ba1541e7…`。
下一步由用户：在 App 中重新收录推荐邮件，确认 Gmail 身份核验与读取恢复；之后测实际接管、关闭后停写与不可用原因提示。

### 2026-10-29 GUI 重测：Gmail 通过，岗位选择被后台收录饿死（`claude-code-4ca66ce5/root`）

用户重测报告（私人：`~/Library/Application Support/TomorrowStar/test-reports/2026-10-29-mc11-gmail-retest/`）：真实 Gmail 账号核验通过，两轮各读 24 封推荐邮件至末页；
流程一直停在 `selecting_job`（候选 64，未选中岗位），后台又从首页开始新的收录；接管等用例未执行。

- 根因：`_tick` 先 `_poll_mail` 后 `_queue`。真实收录约 2.3 min，长于 60 s 轮询；收录刚完成进入 `selecting_job` 的同一 tick 里轮询已到期，立刻启动新收录，
  `_queue` 看到收录在跑就返回，选择永远轮不到。
- 修复（未提交）：`_poll_mail` 在 `selecting_job` 时不启动后台收录（选择是瞬时步骤；无新候选即进入 `waiting_for_mail`，轮询照常）。
  新测试 RED→GREEN（撤掉修复复核仍失败）；依赖棘轮：抽出 `poll_due` 辅助，此文件私有属性使用 11→9 并收紧基线。冻结 `7b181b4d…`：离线 8496/3/0、浏览器 382/8/0。
- 要生效需更新安装版；之后由用户“继续当前岗位”，从暂停的 `selecting_job` 恢复。

### 2026-10-29 安装版第五次更新（`claude-code-4ca66ce5/root`）

用户“授权更新 App”。以 `e4d89e3f` 构建，App 已退出（私人证据 `maintenance-2026-10-29-mc11-r5/`）：构建、`verify.py`、`main_app.py check`、`update`（回退副本已验证、
配置与权限未改、未启动 GUI）、`check_main_permissions.py` 均 exit 0。安装版 `application_pipeline.py` 为修复版（`da1f4a60…`），driver `ba1541e7…`。
下一步由用户：“继续当前岗位”从暂停的 `selecting_job` 恢复，确认选中岗位并进入 JD／匹配／材料／填写；再测实际接管、关闭后停写与不可用原因提示。

### 2026-10-29 GUI 试用：“继续当前岗位”后停在岗位选择（`claude-code-4ca66ce5/root`）

用户报告点击“继续当前岗位”后页面卡住。只读核对（App 启停诊断、intake runs）：App 23:38:21 启动时流程暂停在 `resume_status=selecting_job`，
3 s 后后台轮询从首页开始完整收录（每页 3 封、约 17 s，约 9 页）；继续后 `selecting_job` 等这次收录，界面无进度；用户 23:40:07 退出，收录在第 6 页中断。

- 根因：`e4d89e3f` 只排除状态 `selecting_job`，暂停时状态是 `paused`，轮询照常启动。
- 修复：`_poll_mail` 在 `resume_status` 为选择或取 JD 时也不启动后台收录；`reading_email` 的停止仍由下一次收录恢复（合成邮件测试覆盖，首版误排除后已收窄）。
  新测试 RED→GREEN（撤掉修复复核仍失败）。全量离线在收窄前 8495/3/2（两项失败均已修，所在文件 36 passed）；收窄后未重跑全量。
- 留存：岗位结束时若恰有收录在跑，选择仍最多等约 2.5 min；后台每 60 s 重读 7 天窗口（真实模型调用）；每页 3 封、页面无收录进度。

### 2026-10-30 安装版第六次更新（`claude-code-4ca66ce5/root`）

用户“提交并更新 App”。以 `1fce9463` 构建，App 已退出（私人证据 `maintenance-2026-10-30-mc11-r6/`）：构建、`verify.py`、`main_app.py check`、`update`（回退副本已验证、
配置与权限未改、未启动 GUI）、`check_main_permissions.py` 均 exit 0。安装版 `application_pipeline.py` 为修复版（`f0d57d19…`），driver `ba1541e7…`。
下一步由用户：打开 App 后“继续当前岗位”，确认很快选中岗位并进入 JD／匹配／材料／填写；再测实际接管、关闭后停写与不可用原因提示。


### 2026-10-30 GUI 重测：选岗通过，岗位分析 `job_brief_invalid` 无法继续（`claude-code-4ca66ce5/root`）

用户重测报告（私人：`~/Library/Application Support/TomorrowStar/test-reports/2026-10-30-mc11-selection-retest/`）：启动后选中真实岗位并进入岗位分析；
模型调用退出码 0，但应用校验拒绝（`job_brief_invalid`），流程 `needs_input / analysis_input_required`；点一次“继续当前岗位”提示不会自动重放，仍停在分析。
暂停选岗重开场景前置不符，未测。

- 根因一：某个分组 `jd_quote` 用换行连接了 JD 中三段不相邻的原文；`_canonical_groups` 要求单段连续原文。修复：分组引用可为多段，每行仍须逐字来自 JD
  （大小写与空白按 JD 恢复）；任一行不在 JD 中仍拒绝。要求项引用与提示词不变，已保存分析的哈希不变。真实输出用新代码回放通过。
- 根因二：流水线岗位的“继续”从不重跑被拒的分析，重试按钮又只对非流水线任务显示，岗位无路可走。修复：输出被校验拒绝（结果已知）时，一次“继续”即一次显式重试
  （保留失败 attempt，一次真实模型调用）；结果未知仍不重放，旧格式记录行为不变。
- 新测试 RED→GREEN；全量离线 8499/3/0，ruff、format 干净。

### 2026-10-30 安装版第七次更新（`claude-code-4ca66ce5/root`）

用户“提交并更新 App”。以 `d49e36ab` 构建，App 已退出（私人证据 `maintenance-2026-10-30-mc11-r7/`）：构建、`verify.py`、`main_app.py check`、`update`（回退副本已验证、
配置与权限未改、未启动 GUI）、`codesign --verify`、`check_main_permissions.py` 均 exit 0。安装版 `application_job_brief.py`（`762661b5…`）与
`application_pipeline.py`（`dbd68264…`）为修复版，driver `ba1541e7…`。
下一步由用户：打开 App 后点一次“继续当前岗位”，应重跑一次该岗位分析（一次真实模型调用）并进入匹配／材料／填写；再测实际接管、关闭后停写与不可用原因提示。

### 2026-10-30 GUI 试用：更新后“继续”仍报 `flow_inputs_stale`（`claude-code-4ca66ce5/root`）

第七次更新后用户点“继续当前岗位”，提示“JD 或职业资料已变化，请更新任务。”；任务未重试（attempt 0）。只读核对：任务在更新前建立，`analysis_configuration_revision`
含 `application_job_brief.py` 等引擎哈希与 codex 可执行文件元数据；App 更新（或 Codex CLI 更新）即令旧任务对分析过期，`flow.start` 的 `_fresh` 拒绝重试。

- 修复：继续重试被拒分析前先 `update_inputs` 绑定当前输入（同“更新任务”路径；输入有变时归档失败 attempt 并转为待分析，再 `prepare`）；输入未变仍 `start(retry=True)`。
- 新测试复现原报错（RED）→ GREEN；全量离线 8500/3/0，ruff、format 干净。

### 2026-10-30 安装版第八次更新与自测：重试停在 `match_resume_invalid`（`claude-code-4ca66ce5/root`）

用户授权由我直接测试。以 `9649beb9` 构建并更新（私人证据 `maintenance-2026-10-30-mc11-r8/`，各项 exit 0）。屏幕锁定，CUA 无法点击窗口，
改为向 App 本机服务发送与按钮相同的 `/api/pipeline/continue`。结果：任务重新绑定输入（旧失败 attempt 已归档）并开始分析，数秒后 `match_resume_invalid`，
流程按“结果未知”停住；新 attempt 目录为空，没有模型调用。

- 根因：新 attempt 从被拒的岗位解读接续，`_same_upstream_binding` 要求配置完全相同；App 更新改了引擎哈希，ChatGPT.app 内 Codex 13:04 更新改了可执行文件元数据。
- 修复一：解读被拒（`validation-failure.json`）且未采纳解读的 brief 阶段不复用任何上游决定，配置变化不再阻止接续；解读本身仍核对原拒绝记录后重新调用。
- 修复二：`match_resume_invalid` 归为已知拒绝（不调用模型，下次尝试重新核对记录），“继续”可重试。
- 修复三：持有该岗位执行锁时，最新 attempt 若目录为空即已结束且未调用模型，不再阻止新请求；同一请求本身仍不重放。
  `test_request_save_failure_never_dispatches_or_replays_an_unknown_intent[True]` 相应改为：原请求仍为 needs_recheck，新请求可执行。
- 新测试 RED→GREEN；真实记录副本上两处阻塞均通过；全量离线 8505/3/0，ruff、format 干净。
