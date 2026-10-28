# MC-20：补齐 worker 运行身份对材料核验代码的覆盖

Type: task
Label: wayfinder:task
Status: open
Priority: P2
Interaction: AFK
Assignee: none
Created: 2026-10-28
Parent: [Module 剩余开发地图](../map.md)
Blocked by: none
Triage: needs-implementation

## 问题与范围

[MC-15 复审 r2](../../remaining-tickets-2026-10-26/mc15-mc19-joint/acceptance/review-mc15-r2.md) 留下的 P2，
MC-15 按“只改记录”结案并移入 fog（见 [2026-10-28 工作审计](../../work-audit-2026-10-28/README.md) 问题 2、4）。

worker 进程在填写时经 `store.material_inputs` / `store.verify_material`（`application_worker.py`）惰性导入
`application_match`、`application_resume`、`application_material_sources`，三者不在 worker 角色内，
worker 启动时记录的运行身份因此不覆盖材料核验代码。该缺口早于 MC-15。

同时：`application_preparation_fixtures`（合成模式由 `macos/server.py` 载入控制器）既不在角色内也未豁免；
`tests/test_loaded_role_coverage.py:233-235` 注释称 worker“从不加载”这些路径，说法过宽。

## 文件所有权与并行边界

`loaded_code.py`、`application_worker.py` 中材料核验的导入位置、`tests/test_loaded_role_coverage.py`。
须在 MC-11 更新安装 App 之前完成；与 MC-21、MC-22 不共享文件时可并行。
共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [ ] 先写失败回归：worker 实际执行材料核验后加载的模块都属于 worker 角色或有理由豁免。
- [ ] worker 启动时预加载上述三模块并纳入 worker 角色（或给出等价方案），启动身份覆盖材料核验代码。
- [ ] `application_preparation_fixtures` 按 `application_worker_fixtures` 同理豁免并写明理由。
- [ ] 改正 `test_loaded_role_coverage.py` 的过宽注释与文档字符串，使其只陈述测试实际证明的内容。
- [ ] 新冻结后完整默认离线通过，受影响隔离浏览器与 native 用例复跑通过，独立审查 READY；MC-17 清单与 MC-18 基线同步。

## 既有证据与限制

不改变产品行为与身份格式之外的契约。安装版 App 经 MC-11 更新后才生效；本票不安装 App。最终 Submit 手动。

## Comments
