# 核验 Ashby 公开初始化读取的精确请求边界

Type: bug
Label: wayfinder:task
Status: claimed
Priority: P1
Interaction: AFK
Assignee: 01a15ee0/root/ashby_bootstrap
Created: 2026-10-20
Parent: [单岗位申请主流程](../map.md)
Blocked by: [定位未批准请求并恢复受控字段核验](25-request-diagnostics-readback.md)、[独立限制最终Submit并退役请求批准](38-independent-submit-boundary.md)
Triage: source-verified-awaiting-real-acceptance

## 当前替代范围 — 2026-10-20

重写为Ashby正常公开初始化兼容回归。问题是本地请求守卫阻断正常表单，不再建设逐Query人工grant审批。既有原始请求/未知open和失败收据保留。

规范：[单岗位流程](../../../docs/single-job-flow.md)；执行顺序：[统一开发计划](../../../docs/development-plan.md)。本节替代下方与之冲突的旧范围、验收、时间窗和运行门槛。Status、Assignee、历史勾选和原始收据不变；新验收尚未实施。

原票缺少Blocked by，本次在票头补齐当前依赖。

当前验收：

- [ ] 正常公开初始化、岗位/组织读取能够加载原申请表；查询名或正文版本变化不自动触发人工审批。
- [ ] 适配器不足走18通用浏览器，不为一般读取/草稿POST建立逐字节白名单。
- [ ] 系统先识别当前原页状态再恢复；结果仍不明才问，自动最终Submit保持零。
- [ ] 合成与真实初始化分别留证，不把旧失败原因追认成已证明。

以下保留原范围与历史证据，不将新期望追写为旧票未完成原因。

## Problem

用户要求使用随机不同的真实投递页验收。当前唯一主 App 的真实运行已成功启动浏览器，
但 Ashby 的岗位及组织 GraphQL 初始化 POST 被请求保护在发送前阻断，表单步骤随后超时。
原 open intent、同一 run/Page 和未知结果已保留；未进行字段填写、简历上传或 Submit。
这不是 Chrome 启动崩溃，也不能仅凭 operation 名将未知 POST 改成允许。

## Smallest next engineering work

复用既有 public-read-grants、请求诊断及原页只读观察。官方公开客户端中的两个操作已提取为
Query AST；原请求未保存正文或正文摘要，尚不能证明其字节与已审 Query 一致。
先核验完整 Query、传输序列化和岗位／组织变量边界，再决定最小配置或代码修复。
所有原始请求、Query、真实定位符与材料只放私有证据；本票不复制这些内容。

## Acceptance criteria

- [ ] 被阻断的请求可与精确用途、正文版本及原岗位／组织绑定，不依赖 operation 名自证只读。
- [ ] 仅接受已审公开 Query；其他岗位、额外变量、mutation、别名端点、重定向及未知写仍被拒绝。
- [ ] 不读取或发送个人信息来取得公开初始化资料，不放宽简历上传或最终 Submit 边界。
- [ ] 原未知 open 不因生成 grant 自动结算；不刷新、重开、清除 intent 或替换旧 Page 来制造恢复。
- [ ] 通过现有主 App 的真实页面后继验证表单内容，分别记录字段、附件及最终人工 Submit 边界。

## Evidence and limits

[只读诊断投影](../../source-first-intake-2026-10-20/real-ashby-open-diagnosis.json)
仅保留布尔结论；原始字节及来源保全在私有运行目录。
当前只有公开客户端 Query 的审查素材，没有旧请求字节匹配，没有建立 grant，也没有复发请求。

实际旧版本交接及运行恢复继续遵守 [28](28-installed-readiness-version-handover.md)
和 [31](31-bounded-execution-protocol.md)。本票不改变它们的验收，不添加到 30 的反向前置。
已有真实发送授权不等于可以重试未知外部结果。


## Notes — 可用优先重排 2026-10-21

公开组织读取在控件填写前，先用真实Runner合成失败用例确认与修复，不等控件整票。

Priority/Triage/票头依赖按本次重排更新；旧边与原字节见[审计及变更账本](../../usable-first-wayfinder-audit-2026-10-21/README.md)。原 Status、Assignee、Interaction、既有验收勾选及全部旧正文保持，不领取、不关闭、不替用户接受。源码接口依赖不等于安装或真实操作许可；App 未更新，真实申请继续暂停。

## Bounded implementation — 2026-10-21

本轮按当前替代范围领取：`open / none` → `claimed / 01a15ee0/root/ashby_bootstrap`。上节“不领取”属于原重排操作的历史记录；原验收与既有历史勾选不改。

已通过真实 `ApplicationRunner.tick()` 入口及离线合成 Chromium 先复现公开初始化失败，再最小修复原 Ashby 适配器。岗位与组织公开读取均支持官方已保留 AST 的 fragment 形状；查询名称、格式、返回字段及根别名变化无需请求批准。变量仍绑定当前岗位／组织，草稿、上传和最终 Submit 边界保留。合成表单加载、受影响回归与静态检查通过；未知 open 保留、不结算。

见[源码切片及布尔证据](../../ashby-bootstrap-2026-10-21/README.md)。官方 AST 仅在私有证据中离线核对，没有新增真实请求。本票保持 claimed；旧请求正文匹配、安装版及真实初始化验收未完成。App 更新和真实申请继续暂停，最终 Submit 仍由用户操作。

## 2026-10-26 本轮 Module 后继导航

本票继续持有 Ashby 初始化与其适用真实接受；新接管链的真实 ATS 分层验收由 [MC-12 / T11.3](../../module-completion-2026-10-26/issues/12-t11-real-ats.md) 承接并交叉引用。本票不因 R6 或新链低层证据自动关闭。

本次仅追加范围导航，原 Status、Assignee、Blocked by、勾选及历史结论不变；未领取、实施或关闭本票。
