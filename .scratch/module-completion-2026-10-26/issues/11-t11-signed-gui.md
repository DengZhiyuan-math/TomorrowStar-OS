# MC-11：T11.2 唯一签名 App 新接管链验收

Type: verification
Label: wayfinder:task
Status: open
Priority: P2
Interaction: HITL
Assignee: none
Created: 2026-10-26
Parent: [Module 剩余开发地图](../map.md)
Blocked by: [MC-10](10-t11-model-synthetic-page.md), [MC-15](15-m6-ui-compatibility-identity.md), [MC-20](20-worker-role-coverage.md), [MC-21](21-app-codex-home.md), [MC-22](22-product-native-assistance-policy.md)
Triage: awaiting-authorized-layered-acceptance

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
- [ ] MC-10 交接：安装版随附 native driver successor-r2（SHA256 `eb298be3…`，与产品固定哈希一致）；Codex 请求超时足以覆盖实测约 5 s 的 thread/start。
- [ ] 实际未运行项与失败明确记录，第一层模型验证不外推 GUI；旧安装票的原成果与负责人保持。

## 既有证据与限制

[T11 第二层](../../../docs/module-interfaces-and-migration-design.md#t11-实际-codex签名-gui-与安装身份分层验收)。当前任务只建票，不授权或执行安装。

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

