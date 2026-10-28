# MC-22：决定并接通产品中的自动接管开关

Type: task
Label: wayfinder:grilling
Status: open
Priority: P2
Interaction: HITL
Assignee: none
Created: 2026-10-28
Parent: [Module 剩余开发地图](../map.md)
Blocked by: none
Triage: needs-user-decision

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

- [ ] 用户决定开启时机与形式，并记录在本票 Comments。
- [ ] 产品配置按决定传入经校验的策略，驱动哈希来自安装 App 实际随附的驱动；哈希不符时 fail closed 并显示原因。
- [ ] 回归覆盖：开启时 App 当前任务链自动请求一次接管；关闭或策略无效时不派发且不影响脚本填写。
- [ ] 离线与受影响隔离浏览器通过，独立审查 READY；MC-17 清单同步；MC-11 验收条件据此核对 GUI 中的自动接管。

## 既有证据与限制

[MC-08 结案](08-t09-app-dispatch-controls.md#comments)、[MC-09 结案](09-t10-synthetic-chain.md#comments)。
本票不安装 App、不调用真实模型、不访问真实 ATS。最终 Submit 手动。

## Comments
