# MC-08：T09 App 自动派发与统一控制

Type: task
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: claude-code-367f651f/root
Created: 2026-10-26
Parent: [Module 剩余开发地图](../map.md)
Blocked by: [MC-07](07-t08-return-and-completion.md)
Triage: closed-source-synthetic

## 问题与范围

依赖链覆盖 T05–T08。技术阻塞才请求一次接管，Pipeline 协调暂停、取消、Skip/Return 和材料编辑前停写；保留日常 App 入口。

## 文件所有权与并行边界

application_pipeline.py、application_flow.py、career_portal.py、application_material_edit.py，必要时 macos/server.py 和前端投影。使用当前装配即可，不依赖 MC-14 Runtime 重构；与 MC-13 共享文件串行集成。

共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [x] M2 取消与编辑排空门槛已落地，旧 /api/flow/cancel 经 Pipeline 协调整岗。
- [x] 默认链自动发出一次接管请求，无用户 claim/会话选择或重复审批；脚本处理不了的情况（含不认识的控件、页面结构、登录/验证、结果未知）都交给 Codex，仅事实缺失走信息库提问（2026-10-27 用户修订，原条件为“事实缺失、登录/验证和 unknown 不误判技术阻塞”）。
- [x] 所有入口共用所属控制；取消不换岗、等待仅收录邮件，重复控制与迟到结果不恢复已撤写权。
- [x] App/Portal 编辑先经 Pipeline 确认停写，再让 Flow 保存候选；采用前保护旧绑定，Continue 复用原 journal 与原页。
- [x] 能力失败保留现场和具体原因，不重生成材料、不改全局工具设置；受控合成自动接线回归通过，产品默认开关仍关闭。

## 既有证据与限制

[正式 T09](../../../docs/module-interfaces-and-migration-design.md#t09-app-自动派发与统一控制接入)。旧 34 号票的真实自然 Submit 闭环不由本票替代。

需求以[正式设计](../../../docs/module-interfaces-and-migration-design.md)为准。R6 只证明原冻结源码与合成测试范围；本票如有新实现，
须记录实际改动、对应回归和审查，不能复用 R6 关闭新行为。未知结果、人工内容、原页、
原 journal 和历史记录保留，最终 Submit 手动。

关联历史范围：[原真实闭环票](../../single-job-application-flow-2026-10-16/issues/34-email-to-review-pipeline.md)；其原状态、负责人和接受结论保留。

## 后继接口清点 — 2026-10-26

并发「核对并补齐 M1/M2 剩余职责迁移」确认以下现有协调属于本票原定统一控制范围，
尚未实施迁移，不能用本轮材料条件提交的通过结论关闭它们：

- `application_bound_materials.inspect_request` 当前仍解释原页 mirror、创建
  `inspect-material-update` command 并保存 Worker；按所属 Worker 操作收回，保留
  原 request/update 身份、超时、owner/page/run 和 unknown。
- `application_bound_materials.advance` 的原 Continue/检查派发，以及
  `application_material_edit._edit_target` 与编辑预留/失败部分的停写/排空协调，
  纳入新接管下的统一控制。当前条件提交仍在动作处核对，后续不能绕过。

实际调用、范围判断及证据索引见[归属清点](../../mc01-mc02-mc04-implementation-2026-10-26/mc01/implementation.md#明确转交的后续协调)。
本补充只承接已确认范围，不改变本票状态、认领和硬依赖。

## 2026-10-27 架构审计补充

[架构审计](../../work-audit-2026-10-27/architecture-audit.md) D5：`ApplicationPipeline.request(action, payload)` 以字符串分派 8 种动作；Pipeline 内
`self.flow.applications` 出现 26 次、`self.flow.worker_action` 9 次。本票原验收保持不变，追加：

- [x] 本票触及的控制操作以设计中的命名方法提供（`pause`、`continue_current`、`skip_current`、`return_to`、
  `begin_material_edit` 等）；HTTP 路由可继续使用字符串，只在 Portal 内转换。
- [x] 新增控制不再经 `flow.applications` 或 `flow.worker_action` 穿透；保留的穿透逐项记录理由。
- [x] 新行为测试只经公开入口，不新增对 `pipeline._tick`、`flow._load` 等私有方法的依赖。

本补充不改变本票状态、认领和硬依赖。

## Comments

### 2026-10-27 认领（Europe/Zurich）

`scripts/query_tickets.py` 核对：MC-07 已结案，本票为唯一机械前沿，open/unassigned。按用户指示由
`claude-code-367f651f/root` 认领。先按 MC-07 结案后的实际代码制订计划，尚无源码改动或测试运行；验收条件状态不变。
不扩展实际模型、安装 App 或真实 ATS 权限；产品默认开关保持关闭；最终 Submit 手动。

### 2026-10-27 用户设计决定（Europe/Zurich）

计划见 [MC-08 计划](../../remaining-tickets-2026-10-26/mc08-dispatch/PLAN.md)。用户确认：

1. **脚本保持简单，处理不了就交给 Codex**：不认识的控件、页面结构认不出、需要登录/验证、结果未知都自动交给 Codex；
   **仅事实缺失**走信息库提问/补充流程。Codex 能做到哪一步（如密码、人机验证需用户）属 Codex computer use 能力，
   由其报告并停下等用户，不在脚本中预判。结果未知随交接 JSON 的 `pending_actions` 一并交付：先核实页面再决定，不盲目重做。
2. 每次显式 Continue 最多再接管一次，且该次必须填到底（不再交回）；不自动反复派发。
3. Codex 本身不可用（能力失败）不自动重试；Continue 只让脚本重新检查页面，同一阻塞仍停下。
4. 填写进行中修改简历/求职信须先经 Pipeline 确认停写；仅准备阶段的修改不受影响。
5. 旧的 `pipeline.request(string)` 暂留为薄映射，MC-14 再移除（技术默认）。

### Resolution（2026-10-27，Europe/Zurich）

第一轮冻结 `b5cc597a…`（离线 8282/3/0、浏览器 305/5/0）经独立审查 NOT-READY（P2：第二次接管请求 id 冲突致 Pipeline 空转、
缺少整链合成测试、穿透清单过时；P3：cua_unavailable 未派发、能力失败提示泛化、编辑门重复请求返回缓存 ready、新测试读私有状态），
全部先写失败回归后修复并重新冻结：1816 文件 `4c7da1b4…`，候选 candidate-r2 `550d4621…` 未变。完整默认离线 8293：8290 passed / 3 skipped / 0 failed；
受影响隔离浏览器 browser-r3 310：305 passed / 5 native opt-in skips / 0 failed（browser-r2 一次负载计时偶发失败保留不计，见诊断）。
复审 READY-TO-CLOSE、无 P1/P2：[final-evidence-review-r2](../../remaining-tickets-2026-10-26/mc08-dispatch/acceptance/final-evidence-review-r2.md)；
[验收记录](../../remaining-tickets-2026-10-26/mc08-dispatch/acceptance/README.md)。

实现：Worker `technical_blocker` 分类（脚本处理不了的控件/结构/登录验证/结果未知/无路由 cua_unavailable 派发，事实缺失走信息库）、
`takeover_candidate`/`request_takeover`（系统认领、按请求 id 幂等、每次 Continue 至多一次、第二次接管须填完）、Continue 归档已停接管、
未知结果以 `pending_intent_ref` 交付并在停写后独立回读结算；runner 自动启动一次、能力失败保留原页与具体原因不重试、暂停/失页转等待；
Pipeline 在需核对前自动请求接管、接管中保持心跳、命名控制与 Portal 路由表、材料（含简历）编辑先确认停写的 `begin_material_edit` 门；
穿透清单逐项记录保留理由（至 MC-14）。产品默认开关仍关闭（server 未传原生策略）。

验收对应：自动派发 = Pipeline/Worker/runner 合成测试 + `tests/test_pipeline_takeover_chain.py` 整链（自动接管→交回→第二阻塞→第二次接管→
filling_complete→手动 Submit 等待）；统一控制 = 命名控制与 HTTP 等价、重复控制不恢复写权；编辑门 = 未确认停写返回 409 且 Flow 字节不变、
Continue 复用原 journal 与原页；能力失败 = 具体原因、不重试、不重生成材料或改全局设置。未做原生运行（无驱动层改动；交接/交回原生证据见 MC-07）。

限制与后续（复审 P3）：整链测试中两次阻塞经 Worker store 注入、简历上传观察与最终 review 用桩，脚本在假页面上的继续执行未实际运行；
`cua_unavailable` 派发未要求路由决定晚于上次交回（理论上可能把交回后的真实 Cua 故障当作一次已允许的接管，失败会记录且不重试）；
“已交给 Codex 接续”提示目前只在接管请求记录中——App 状态守卫拒绝 filling 状态带通知，需改动并重装 App 才能显示。
未运行实际模型、安装签名 App 或真实 ATS；最终 Submit 手动；未提交 git。
