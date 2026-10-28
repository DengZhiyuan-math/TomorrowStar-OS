# R04：正确判断文件字段是否接受 PDF

Type: bug
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: Codex / pdf_repairs
Created: 2026-10-25
Parent: [审计修复计划](../map.md)
Blocked by: 无
Triage: verified

## 已确认问题

审计身份：SP1。`image/*`、`text/*` 等子串被误认作 PDF 支持，可能产生错误材料和 ready 状态。先减少无效构建与交付。
证据以[原审计报告](../../work-audit-2026-10-25/README.md)为准，原实验补丁已撤回。

## 文件所有权与最小范围

`application_materials.py` 的文件需求消费；`test_cover_letter_delivery.py` 及相关材料交付测试。

在材料 Module 内按完整 accept 项判断，复用既有格式错误与必需／可选路由。支持类别以现有合同为准，不新增格式转换或新的通配符支持。

## 验收条件

- [x] 覆盖必需／可选 × 支持／不支持，拒绝 image/*、text/*、.pdfx 和 application/pdfx；拒绝前构建调用为零。
- [x] 覆盖 .pdf、application/pdf、大小写、空格及逗号分隔组合。
- [x] 空 accept 与既有其他通配符兼容单列核对；不能把 application/* 等候选冻结成新产品需求。
- [x] 拒绝时保留正文与人工修改；必需材料按原规则等待，可选材料显示原因，未知动作不被可选规则绕过。

## 状态与执行范围

建票时只规划、未领取、未实施；后续用户调用 implement 授权执行。技术前置依赖为无；共享文件由同一负责人串行集成。
实施时先补当前版本的失败回归，再验证最小修复。不能直接把已撤回的实验补丁或其绿测当成当前交付。
不改真实私人配置／材料，不运行真实模型、Prism 或 ATS，不更新 App；最终 Submit 保持手动。

## 本轮实施与验证（2026-10-25）

- `application_materials.py` 按逗号拆分、去空格及忽略大小写后比较完整 accept 项，保留 `.pdf`、`application/pdf`、空字段与现有完整 `*`、`*/*` 兼容路径。
- 不新增分类通配符支持；`image/*`、`text/*` 及 `application/*` 不据此宣称支持 PDF。不新增任何格式转换。
- `test_cover_letter_delivery.py` 新增 33 项默认离线回归，覆盖必需／可选、有效／无效项、大小写与组合、人工正文和未知结果保护。核心反例在原实现有 12 项失败；修复后 33 项通过。
- 与 R05 同一版本的受影响回归：168 passed、13 deselected。日志 `/private/tmp/tomorrowstar-audit-repairs-2026-10-25/r04-r05/`；最终组合回归和独立复审由 R07 记录。
- 仅源码和合成验证；没有真实 Prism、模型、ATS、App 更新、提交或发布。

## 最终收尾 — 2026-10-25

本票通过本轮源码验证及独立复审，随 R07 关闭。最终版本、组合回归、安装差异及真实验收边界见[实施与交接](../implementation.md)与[机器摘要](../verification.json)。原规划段落及中间状态保留为历史。
