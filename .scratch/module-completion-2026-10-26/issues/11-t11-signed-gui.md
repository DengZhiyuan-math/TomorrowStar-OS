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

