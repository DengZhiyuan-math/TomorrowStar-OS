# 接通邮件处理设置与独立进度展示

Type: task
Label: wayfinder:task
Status: closed
Priority: P0
Triage: done
Interaction: AFK
Assignee: 01a15ee0/root
Created: 2026-10-21
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [从 Gmail 推荐邮件自动取得岗位与原 JD](14-gmail-recommendation-intake.md)

## Question

已有安全的邮件收录、标签/归档和进度接口，如何让默认原生入口使用用户保存的处理标签，并直接看清每一步实际进度？

## Scope

本图沿用执行扩展，本票只交付已确认 APP-01/02/15/16 的有限源码接线，不引入新产品偏好。其实现细节只在本票；原[增量保存邮件岗位后标记归档并延后取得JD](35-mail-capture-label-archive.md)继续持有邮箱后端、账号隔离、处理收据、历史兼容及整体验收，原[收敛默认入口与重复执行控制](41-consolidate-entrypoints-controls.md)消费本票界面。两原票身份、领取、验收和历史保留。

## Existing interface and ownership

- 复用 `ApplicationIntakeService(processed_label=...)` 及其已持久化的 mail_captured、mail_labeled、mail_archived、mail_needs_recheck 与 JD 进度。后端已覆盖先本地保存、未知结果先核对和账号隔离，不重写这一套。
- 本票拥有 `macos/App.swift` 的现有配置读写/参数、`macos/server.py`、`career_portal.create_server` 到 Intake 的可选参数接线，以及默认 `portal_static/application_flow.js` 邮件卡片进度与对应公开回归。多人实施先协调共享文件，不回滚他人修改。
- 无需新的邮件平台、状态库、设置中心或权限服务。设置使用原配置位置；不迁移私人目录，不修改真实配置或邮箱来开发。

## Acceptance criteria

- [x] 用户可在现有设置入口保存可选处理标签；Native → server → create_server → Intake 传入同一原值，重开继续使用该值。不预设或擅建真实标签。
- [x] 未配置时仍可读取资料和收录候选，不执行标签/归档；坏配置只影响相应邮件处理能力，不阻整个 App 或误报资料目录故障。
- [x] 默认邮件卡片分别显示本地收录、已标记、已归档、待核对和 JD 获取的真实状态；等待/失败不伪装完成，不把邮件处理进度当岗位推进状态。
- [x] 沿用现有保存及收据：完整收录落盘后才能标记/归档；未知结果先 inspect，不重复派发；保留账号、原邮件、候选和 cursor，旧无身份记录不批量归档。
- [x] 当前岗缺事实、暂停或等待时只继续 capture；设置/轮询/界面更新不启动下一岗、不丢焦点或覆盖未保存编辑。
- [x] 从真实启动参数/公开 HTTP 与默认浏览器入口补最小 RED/GREEN，覆盖配置原值、未配置、坏配置局部错误、重开、独立进度和未知结果不重发。使用合成邮箱，不改真实邮箱。
- [x] 按 CONVENTIONS 跑受影响回归；共享入口/存储变化按适用规则跑完整默认离线，记录实际输入及未覆盖范围。不得放宽既有超时或业务保护。
- [x] 交付配置/JSON 调用清单、用户操作说明及原票交接指针。本票的源码通过不关闭两原票、不证明安装/真实邮箱通过。

## Execution boundary

本轮只建票，未领取、实施或关闭。后续 AFK 源码按既有授权领取后推进；App 更新与真实申请仍暂停。安装/真实标签和归档、最终用户体验由原票与既有组合/真实验收承接。最终 Submit 始终人工。

## Audit basis

[本次源码审计](../../usable-first-wayfinder-audit-2026-10-21/functional-audit.md)定位到构造参数未接入生产启动及默认 UI 未消费现有进度字段。后端功能已存在；下一步先用公开入口失败用例复现接线缺口，不重复建设整个邮件系统。

## Implementation claim — 2026-10-21

源码与合成范围由 01a15ee0/root 领取；保留原验收和历史。App 更新、真实邮箱及真实申请仍暂停。

## Source delivery — 2026-10-21

有限源码/合成范围完成并关闭本票。Native配置/参数、server/create_server/Intake接线及默认卡片已交付；坏配置局部禁用标记/归档，资料与收录可用。独立复核发现并修复启动和设置sheet交错覆盖标签的两个竞态，无未解决发现。

完整默认离线4597通过、2跳过、561 deselected；811项输入前后相同。额外默认入口/Ashby/Submit合成浏览器43通过；Swift typecheck、Ruff和JS语法通过。两个skip是既有显式opt-in PDF性能/渲染benchmark；不宣称性能通过。各集合有重叠，不相加。两次review修正前的完整运行中断保留，不计通过。

[实现/配置/JSON调用及验证收据](../../mail-settings-implementation-2026-10-21/README.md)；[同一主App最小验收准备](../../mail-settings-implementation-2026-10-21/minimal-installed-journey.md)。源码关闭不关闭原35/41票，不证明安装版、真实邮箱标签/归档或用户体验接受。App未更新，真实申请继续暂停，最终Submit人工。原执行边界正文保留为建票时历史。
