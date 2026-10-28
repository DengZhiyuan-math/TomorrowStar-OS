# 当前有效索引

更新：2026-10-28，Europe/Zurich（MC-17；MC-14 Runtime 行；MC-22 自动接管开关）。本页只做导航，回答“现在什么有效、契约在哪一节”；
不新增规则。被取代段落保留其历史含义，不删除。每张 MC 票结案时，若改变入口约定、契约位置
或取代关系，同步更新本页和[入口清单](codebase-responsibilities.md#public-entry-points)。

## 日常产品入口

**日常用户入口是 App**（唯一的 `~/Applications/TomorrowStar.app`）。用户从 App 启动和控制申请；
脚本遇阻时由 App 经 Worker 调用 Codex computer use 接管，可接续时交回脚本，否则处理到
Submit 前并返回“填写完成”。Codex 是 App 调用的执行能力，不是用户须先进入的入口。最终 Submit 手动。

依据：[Module 设计](module-interfaces-and-migration-design.md)文首“日常用户入口是 App”段（2026-10-26），
以及[已确认的设计决定](module-interfaces-and-migration-design.md#已确认的设计决定)的“用户入口”行。

实现现状：默认页面写入与自动接管仍关闭；App 自动派发与统一控制已由 MC-08（T09）在开关打开时实现，
产品中何时及如何打开由 MC-22 决定，状态见
[剩余开发地图](../.scratch/module-completion-2026-10-26/map.md#当前票据与硬依赖)。这是“约定已定、能力未全部启用”，
不表示回到 10-22 的使用方式。

### 10-22 与 10-26 两处入口说法以哪处为准

**以 2026-10-26 设计文档为准。** 该段明确写明“本次入口约定优先于历史‘由 Codex 配合工具使用’的
导航说明”，且日期更新。10-22 的两处段落记录当时“先使用、再调整”的执行方式，只在入口说法上被取代；
其中保留原页、人工修改与未知结果、最终 Submit 手动等保护与当前规则一致，继续有效。

## 各 Module 契约所在章节

“现在能调用什么”看[当前公开入口](codebase-responsibilities.md#public-entry-points)；
“应该变成什么”看设计各小节。设计中的 Interface 名称是目标表达，不代表已有同名方法。

| Module | 目标契约 | 当前入口与收回项 |
| --- | --- | --- |
| Pipeline | [设计 Pipeline](module-interfaces-and-migration-design.md#pipeline) | [入口清单](codebase-responsibilities.md#public-entry-points)；收回项见[计划收回](codebase-responsibilities.md#planned-withdrawals) |
| Intake | [设计 Intake](module-interfaces-and-migration-design.md#intake) | 同上 |
| Flow | [设计 Flow](module-interfaces-and-migration-design.md#flow) | 同上 |
| Worker | [设计 Worker](module-interfaces-and-migration-design.md#worker)；[Codex 接管与交回](module-interfaces-and-migration-design.md#codex-接管与交回)；当前交接契约 [T06 JSON](module-interfaces-and-migration-design.md#codex-takeover-json-contract) | 同上 |
| Analysis | [设计 Analysis](module-interfaces-and-migration-design.md#analysis) | 同上 |
| Resume | [设计 Resume](module-interfaces-and-migration-design.md#resume)；内容与模板见 [JSON 简历设计](json-resume-design.md) | 同上 |
| CoverLetter | [设计 CoverLetter](module-interfaces-and-migration-design.md#coverletter) | 同上 |
| MaterialConsistency、MaterialDelivery | [一致性](module-interfaces-and-migration-design.md#materialconsistency)、[交付](module-interfaces-and-migration-design.md#materialdelivery) | 未列入本轮入口清单 |
| Runtime | [设计 Runtime](module-interfaces-and-migration-design.md#runtime) | MC-14：[application_runtime.py](../src/career_evidence_graph/application_runtime.py) `open_runtime`/`ApplicationRuntime.close`；Portal 只保留 HTTP 映射，见[入口清单](codebase-responsibilities.md#public-entry-points) |

跨 Module 共用：[职责与状态所有权](module-interfaces-and-migration-design.md#职责与状态所有权)、
[Interface 共用契约](module-interfaces-and-migration-design.md#interface-共用契约)（身份、副作用、错误与等待、幂等）。
产品行为：[APP-01–18](single-job-flow.md)。票据状态：[剩余开发地图](../.scratch/module-completion-2026-10-26/map.md)，
以 `scripts/query_tickets.py` 为准。

## 已被取代的段落

| 被取代段落 | 取代它的段落 | 取代范围 |
| --- | --- | --- |
| [开发计划“当前执行方式：先使用，再按反馈调整 — 2026-10-22”](development-plan.md#当前执行方式先使用再按反馈调整--2026-10-22) | 设计文首“日常用户入口是 App”段（2026-10-26）及[已确认的设计决定](module-interfaces-and-migration-design.md#已确认的设计决定)“用户入口”行 | 仅入口说法 |
| [workflows“当前使用方式 — 2026-10-22”](workflows.md#当前使用方式--2026-10-22) | 同上 | 仅入口说法 |
| [设计“旧 T06 有限视觉动作、真实回读与提交守卫”](module-interfaces-and-migration-design.md#旧-t06-有限视觉动作真实回读与提交守卫)及文中自定义视觉动作、默认截图交接 | [T06 JSON 交接与 Codex 原页直接接管](module-interfaces-and-migration-design.md#codex-takeover-json-contract) | 设计文首已声明；旧实现证据保留原范围 |
| [设计“续轮判定：原页与可靠停止尚未具备（实施前记录）”](module-interfaces-and-migration-design.md#续轮判定原页与可靠停止尚未具备实施前记录) | [设计“2026-10-27 MC05 原 T06 限定验收完成”](module-interfaces-and-migration-design.md#2026-10-27-mc05-原-t06-限定验收完成) | 仅 MC05 受控 agent/合成原页/native 工具层 |
| [设计“R6 当时的未闭范围（历史截点）”](module-interfaces-and-migration-design.md#r6-当时的未闭范围历史截点)；[开发计划](development-plan.md#当前-module-迁移与-codex-接管主线--2026-10-26)主线中的票数统计 | [地图“当前票据与硬依赖”](../.scratch/module-completion-2026-10-26/map.md#当前票据与硬依赖) | 票据状态与剩余范围 |
| 用设计各 Module 小节的目标签名回答“现在调用什么” | [当前公开入口](codebase-responsibilities.md#public-entry-points) | 只回答当前可调用；目标契约不变 |
