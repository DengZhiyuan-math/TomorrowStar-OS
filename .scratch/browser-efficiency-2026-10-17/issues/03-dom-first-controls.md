# 让一个不可编辑下拉框走DOM完成选择

Type: task
Label: wayfinder:task
Status: closed
Triage: resolved
Completion: source-and-browser-verified
Priority: P1
Interaction: AFK
Assignee: 01a14a95/root
Created: 2026-10-17
Updated: 2026-10-18
Parent: [交付 DOM 优先的受控浏览器效率改进](../map.md)
Publication order: 15
Blocked by: None (can start immediately)

**What to build:** 一个已支持不可编辑下拉框可从字段识别、答案许可到准确选项操作和独立回读完整走通。

## Acceptance criteria

- [x] 普通字段已有实现，不重复开发；复用原字段身份与每动作动态重检。
- [x] 覆盖异步选项、重复文本、不可见项和重渲染；不靠first、模糊猜测或force冒充成功。
- [x] 保留独立intent、许可与结果回读；发出动作后unknown禁止改走Cua重做。
- [x] 从合成入口单独演示正确性和调用/时间记录；不能用模拟Cua耗时声称原生提速。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Comments

### 2026-10-18 — DOM slice verified

[证据](../../browser-efficiency-execution-2026-10-18/dom-combobox/README.md)支持显式aria-controls关联listbox的readonly input combobox，原control/option节点、精确唯一可见选项及每步动态许可/答案/文件/owner核验；不增加模糊、force或unknown后Cua重放。有效RED→GREEN及15个真实浏览器回归通过，当前源码兼容22 passed/5 native opt-in skipped。真实WorkerService prepare/resume演示1预热+5测量重复全部独立回读，字段周期中位538.18ms，原生填写0；不是native对照或安装速度。

[最终源码门槛](../../browser-efficiency-execution-2026-10-18/full-gate/verification.json)：2516默认离线通过、245 browser/native显式排除，Ruff/format/JS/diff通过，217源码文件前后无漂移。独立审查无阻断，owned浏览器清理通过。真实申请继续暂停，用户体验接受集中待审。

### 2026-10-18 — Execution claim under all-remaining-ticket authorization

用户要求持续推进全部剩余票，覆盖原每会话一票的限制。本票已回读当前状态与依赖，由 `01a14a95/root` 领取；允许隔离合成实现、测量与验证，真实申请继续暂停。保留原页面、附件、私人记录及未知结果；不读取真实邮箱／模型，不写真实字段／上传或Submit。共享模块按函数责任协调，不回退其他在途改动。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/15-readonly-combobox-dom.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/browser-efficiency-2026-10-17/issues/03-dom-first-controls.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。
