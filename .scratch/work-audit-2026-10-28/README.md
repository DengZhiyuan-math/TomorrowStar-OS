# 工作进度整理与已完成工作审计 — 2026-10-28（Europe/Zurich）

只读整理与审计。来源：`scripts/query_tickets.py --json`（[原始输出](tickets.json)）、各票 Comments、
`.scratch/remaining-tickets-2026-10-26/` 下的验收证据，以及三路独立只读审查。
未修改任何票据的 Status、Assignee、Blocked by 或正文；未运行浏览器、native、真实模型、安装 App 或真实 ATS。
上一次整体整理是 [2026-10-27 全部票据整理](../work-audit-2026-10-27/README.md)。

## 进度：10-27 以来

共 165 张（+3：MC-17/18/19）：144 张已关闭或已解决（127 closed、17 resolved），**21 张未关闭**（14 open、7 claimed）。
查询器 0 errors、20 warnings（仍是 `unknown_metadata`），机械前沿仍为 **0**。

Module 完成地图在 10-27/28 由 `claude-code-367f651f/root` 连续结案 9 张：

| 票 | 结案 | 审计结论 |
|---|---|---|
| [MC-06 T07 交付已绑定正文与附件](../module-completion-2026-10-26/issues/06-t07-bound-material-delivery.md) | 10-27 | 有据，带保留 |
| [MC-07 T08 可靠交回与填写完成](../module-completion-2026-10-26/issues/07-t08-return-and-completion.md) | 10-27 | 有据，带保留 |
| [MC-08 T09 App 自动派发与统一控制](../module-completion-2026-10-26/issues/08-t09-app-dispatch-controls.md) | 10-27 | 有据，带保留（产品默认关闭） |
| [MC-09 T10 新产品路径合成整链与故障验收](../module-completion-2026-10-26/issues/09-t10-synthetic-chain.md) | 10-28 | 有据，带保留 |
| [MC-14 M5 收拢 Runtime 装配与 Portal 传输](../module-completion-2026-10-26/issues/14-m5-runtime-portal.md) | 10-28 | 有据，带保留 |
| [MC-15 M6 后端投影、调用兼容与运行身份](../module-completion-2026-10-26/issues/15-m6-ui-compatibility-identity.md) | 10-28 | **边缘**：复审 NOT-READY 后按“只改记录”结案 |
| [MC-17 登记核心 Module 公开入口与当前有效索引](../module-completion-2026-10-26/issues/17-public-entry-index.md) | 10-27 | 有据 |
| [MC-18 依赖棘轮测试](../module-completion-2026-10-26/issues/18-dependency-ratchet.md) | 10-27 | 有据；基线已按规则收紧至 18 对 / 85 项 |
| [MC-19 收回 Flow / Resume 的外部私有访问](../module-completion-2026-10-26/issues/19-narrow-flow-resume-surface.md) | 10-28 | 有据，带保留（大部分靠重新归类为 Module 内部） |

[MC-10 T11.1 实际 Codex 与同一合成原页验收](../module-completion-2026-10-26/issues/10-t11-model-synthetic-page.md)
已认领：离线准备完成（Codex 0.165 协议核对、交接文本去除后台路径、门控的 C0–C5 真实运行测试、空隔离 Codex 目录），
**真实运行由用户决定暂缓、稍后统一测试**，未发生任何模型调用。

其余 12 张旧地图未关闭票自 10-27 无变化（见“未关闭票”）。

## 审计方法

对每张结案票：列出票面验收条件 → 核对结案引用的证据文件存在且数字一致 → 核对审查结论 →
抽查所述代码/测试在当前源码中存在 → 找出票面文字与实际范围的差异。三路审查互相独立。
本次另在当前源码上运行静态检查与全量默认离线测试。

**证据真实性：** 所有引用的 offline/browser/native 结果文件都存在，数字与票面一致；
MC-08、MC-09 的 JUnit 由审查方重新计数一致；MC-08/09 的冻结哈希与票面一致；
`2374b341…` 可按 `mc15-mc19-joint/acceptance/verify_offline.py` 的算法从记录的 manifest 精确复现。
失败的中间运行（MC-07 offline-r1、MC-08 browser-r2、MC-09 browser-r1/r2）均保留并有诊断，未被计入。

## 当前源码核验（本次运行）

| 检查 | 结果 |
|---|---|
| `ruff check` / `ruff format --check`（排除 `.scratch`） | 通过；751 文件已格式化 |
| `git diff --check` | 通过 |
| 依赖棘轮 `tests/test_dependency_ratchet.py` | 6 passed |
| 全量默认离线 `scripts/run_pytest.py -q` | **8387 passed、3 skipped、0 failed**（670 deselected 为 opt-in 浏览器/native/live；29:53） |

离线全绿覆盖当前字节（含问题 1 的 12 个文件），但不替代浏览器、native 复跑与独立审查。

## 发现的问题

按严重度排序。

1. **当前源码已偏离最后一次验收冻结。** 当前 manifest 哈希 `4c9d93fc…`（1828 文件）≠ 联合冻结 `2374b341…`。
   10-28 12:15–13:28 之间改动 12 个文件，全部属于 MC-10 准备：新增 `tests/codex_live_guards.py`、
   `tests/test_codex_live_guards.py`、`tests/test_worker_native_live_model_browser.py`；改动产品源码
   `src/career_evidence_graph/application_codex_assist.py`（协议版本固定改为 0.165、交接去除 `backend_authority`）及 8 个测试/peer 文件。
   这些改动没有对应的冻结、受影响浏览器/native 复跑或独立审查。MC-10 真实运行或 MC-11 前须重新冻结验收。
2. **MC-15 在复审 NOT-READY 后结案。** [review-mc15-r2](../remaining-tickets-2026-10-26/mc15-mc19-joint/acceptance/review-mc15-r2.md)
   给出的 READY 路径（改正 `tests/test_loaded_role_coverage.py:233-235` 过宽注释、豁免 `application_preparation_fixtures`、重新冻结）
   均未执行；结案采用审查所给“只改记录”选项，把 worker 角色覆盖缺口记入 fog，没有 r3 复审。票面 criterion 1 打勾，正文自述“部分满足”。
   [review-mc19-r2](../remaining-tickets-2026-10-26/mc15-mc19-joint/acceptance/review-mc19-r2.md) 的 NOT-READY 仅因一个未运行的浏览器文件，
   之后已补跑 6 passed，可视为已解决。
3. **MC-08 的自动接管在产品中默认关闭，且没有任何票负责打开。** `macos/server.py`、`career_portal.py` 都不传
   `native_assistance_policy`，只有 runner 的 CLI 参数和测试开启；安装 App 中不会自动派发。票面 criterion 5 允许“默认关闭”，
   但 criterion 2 与设计 T09 最小交付都写“默认链自动发出一次接管请求”。MC-09 整链测试显式打开开关（`tests/test_synthetic_takeover_chain_browser.py:312-349`）。
   MC-10/11/12/16 及地图 fog 都没有“何时、由谁打开”的记录。
4. **延后事项形成无人负责的链。** MC-14 审计补充 3（业务规则测试迁移）→ MC-19 → 地图 fog“未分配后续票”；
   MC-15 worker 角色覆盖缺口与正式 App 的 Codex `HOME=Path.home()`（个人 `~/.codex` 进入模型上下文）都标“建议在 MC-11 前处理”，
   但 [MC-11](../module-completion-2026-10-26/issues/11-t11-signed-gui.md) 与 [MC-16](../module-completion-2026-10-26/issues/16-final-ac01-ac27-audit.md) 票面都未提及。
   这几项问题已能精确陈述，按 wayfinder 规则应成为票而不是 fog。
5. **票面勾选与实际范围不一致（结案只在 Comments 披露）：**
   - MC-06 criterion 3“上传响应丢失先核对原 attempt”仍打勾；远程上传丢失部分已移入 fog，native case 08 skip，Ashby 早期上传 fail closed。
   - MC-07 criterion 1“复杂控件”实为输入即选定的合成 combobox；自定义下拉框选项选择不支持（fog）。
   - MC-09 criterion 1/2 的正文/附件交付和报告丢失、app-server 断开未在整链中注入，靠分组件测试。
   - MC-14 审计补充 criterion 3 打勾，Resolution 写“本票不做”。
   - MC-08 的“后继接口清点”补充（`application_bound_materials.inspect_request` 收回 Worker）未被结案或任一审查提及，代码仍直接 `worker.store.save`。
6. **多项 native 覆盖只是部分。** MC-06 的生成中等待、错岗/错版/过期拒绝、可选项失败只有离线证据；MC-07 的 Cancel/Skip/材料变更、
   App 同步丢失只有离线证据。均已在结案中披露，非虚报。
7. **审查 P3 未进入任何跟踪处。** MC-06（yielded-owner 全局跳过、缺“已让出且驱动失败”负例）、MC-07 P3-1~7
   （`next_step.kind` 未校验、非存储异常报为存储停止、Continue 放宽超出“仅存盘丢失”等）只存在于审查文件和结案文本。
8. **记录过期或互相矛盾：**
   - [`ACTIVE-HANDOFF.md`](../remaining-tickets-2026-10-26/ACTIVE-HANDOFF.md) 头部仍写“MC06 claimed、7 closed/12 open”，“Next owner”仍写“Root owns MC06 only”。
   - `mc06-bound-materials/acceptance/README.md` 仍写“Not an acceptance claim”“review pending”。
   - 地图 MC-08 行“App 内接管提示待 App 更新”与第 87 行 MC-15 摘要“接管提示在窗口内显示”不一致。
   - `docs/current-index.md` 最后更新于 10-27，未含 MC-15 的 `application_flow_view`。
   - 设计文档第 227 行旧签名 `open_runtime(config, …)` 与第 231 行新签名并存。
9. **沿用 10-27 的问题，均未处理：** 旧会话 ID 下的认领（`01a146b9`、`01a15ab3`、`01a15ee0`、`01a15926`、`01a155fd`、`01a15491`）
   10-21 至 10-26 后无更新；Phase 8 07 写 `claimed` 无 Assignee；20 条 `unknown_metadata`。
10. **自 2026-09-08 起无任何 git 提交。** 当前 944 条未提交项（50 modified、894 untracked），全部 10-27/28 结案工作都只在工作区中。

## 未关闭票（21）

| 组 | 票 | 状态 | 在等什么 |
|---|---|---|---|
| Module 主线 | MC-10 实际 Codex 合成原页 | claimed `claude-code-367f651f/root` | 用户统一安排真实运行；需先重新冻结（问题 1） |
| | MC-11 唯一签名 App | open | MC-10；问题 3、4 的前置项 |
| | MC-12 真实 ATS | open | MC-11 |
| | MC-16 AC01–AC27 整体验收 | open | MC-12 |
| 旧地图真实验收 | Gmail 25 → Gmail 16、单岗位 11 → 浏览器效率 09 → 单岗位 12 | open | 用户真实操作 |
| 旧地图源码后续 | 单岗位 18、20、23、33、34、35、36 | claimed/open，旧会话 | 认领是否仍有效未核实 |
| 延期诊断 | Worker 稳定性 07、10，单岗位 26 | open | 10-21 后无更新 |
| Phase 8 研究 | 07 reconcile → 09 seal | claimed（无 Assignee）/ open | 用户本人参与；不阻塞申请产品 |

## 已执行的整理（2026-10-28，用户同意后）

- 新建 [MC-20 worker 运行身份覆盖](../module-completion-2026-10-26/issues/20-worker-role-coverage.md)（AFK）、
  [MC-21 正式 App 专用 Codex 目录](../module-completion-2026-10-26/issues/21-app-codex-home.md)（HITL）、
  [MC-22 产品自动接管开关](../module-completion-2026-10-26/issues/22-product-native-assistance-policy.md)（HITL，需用户决定），
  均加入 MC-11 的 Blocked by；地图票表、依赖图与 fog 同步（对应 fog 项已移除，指向新票）。
- 查询器核对：168 张，0 errors；机械前沿由 0 变为 3（MC-20/21/22）。
- 同步过期记录：`ACTIVE-HANDOFF.md` 头部改为当前状态并把 MC06 实施期段落标为历史；MC-06 验收 README 加结案说明（原文保留）；
  地图 MC-08 行；`docs/current-index.md` 的自动接管现状。设计文档第 227 行是目标签名、第 231 行是实际签名，按索引约定不属过期，未改。
- 未执行：提交 git、MC-10 前重新冻结、旧会话认领核实。

## 建议的整理动作（需用户决定，本记录未执行）

1. **提交现有工作**到分支，至少把 MC-05 到 MC-19 的源码与证据落到 git。
2. **MC-10 真实运行前重新冻结**当前源码，复跑受影响离线/浏览器/native，并为 12 个文件做一次独立审查。
3. **把已能精确陈述的 fog 升为票**，挂在 MC-11 之前：worker 角色覆盖缺口（含 `application_preparation_fixtures` 豁免与过宽注释）、
   正式 App 专用 Codex 目录、产品打开 `native_assistance_policy` 的时机与方式。测试迁移剩余项是否开票按地图约定在 MC-16 前决定。
4. **同步过期记录：** `ACTIVE-HANDOFF.md` 头部与 Next owner、MC-06 验收 README、地图 MC-08 行、`current-index.md`、设计文档旧签名。
5. **核实旧会话认领**，已结束的释放回 `open`/`none` 并在 Comments 记录原因（10-27 已提出，仍待决定）。
