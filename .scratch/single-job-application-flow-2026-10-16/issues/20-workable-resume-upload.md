# 支持 Workable 普通简历字段的受控上传与回读

Type: task
Label: wayfinder:task
Status: open
Priority: P1
Interaction: AFK
Assignee: 01a146b9/workable_upload
Created: 2026-10-17
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [接通受版本约束的单岗位自动填写](06-single-worker.md)、[独立限制最终Submit并退役请求批准](38-independent-submit-boundary.md)
Triage: source-followup

## 当前替代范围 — 2026-10-20

重写为正常简历/必要附件上传与结果回读。已有Workable签名协议保留作适配优化，HTTP/字段白名单、远端SHA及禁止正常autofill不再是所有平台的硬前置。

规范：[单岗位流程](../../../docs/single-job-flow.md)；执行顺序：[统一开发计划](../../../docs/development-plan.md)。本节替代下方与之冲突的旧范围、验收、时间窗和运行门槛。Status、Assignee、历史勾选和原始收据不变；新验收尚未实施。

原依赖（历史，已由票头当前依赖替代）：[接通受版本约束的单岗位自动填写](06-single-worker.md)、[扩充安装版最小合成验收覆盖本轮故障](30-installed-minimal-regression.md)、[支持已观察到的通用 ATS 自定义必填控件](18-generic-ats-controls.md)。

当前验收：

- [ ] 系统上传适用材料并核对当前岗位附件，平台可取得的可靠保存结果充分时继续；不能只以文件名或HTTP200自证。
- [ ] 正常解析/autofill可运行；按实际字段回读保留用户编辑，遇实际冲突才询问，不因解析改值一律要求手工恢复。
- [ ] 未知上传先识别当前结果，仍未知才问，不盲目重传；自动最终Submit/apply为零。
- [ ] 合成、安装与真实上传分别留证；本票不等待30集成结案，不重建已实现签名层。

以下保留原范围与历史证据，不将新期望追写为旧票未完成原因。

## Question

能否在有效批准材料和当前岗位 intent 下，只允许 Workable 的普通 resume 签名对象上传，并保留最终 apply 阻断？

## Work and reuse

- 原客户端可审查静态依赖明确区分普通 resume、autofill 和最终 apply；仅兼容普通 resume 路径，不复制上游实现或引入新依赖。
- 复用 worker 的 intent、版本/输入门禁、网络观察、暂停与 unknown/recheck，建立最窄协议：当前岗位的签名 GET、已验证签名对象地址及字段、一次批准 PDF multipart、当前表单附件链接和远端对象字节回读。
- 同一 intent 只允许一次实际上传派发；客户端自带 fallback 重传必须阻止，未知结果不自动重试。
- 拒绝其他岗位、字段、地址、额外字段、不同 PDF；不开放 autofill、候选人投递或一般 POST，不模拟最终提交。
- 先真实本地合成浏览器 tracer RED/GREEN，再边界回归；当前安装版和真实 ATS 由第 11 票独立验收。

## Ownership

- src/career_evidence_graph/application_worker_browser.py
- 必要的最小 Workable 协议模块
- 对应合成协议与浏览器回归测试

不得修改 hosted_ats.py、application_resume.py 或他人责任文件。不是唯一执行者，保留他人编辑。

## Acceptance criteria

- [ ] 批准 PDF 经精确岗位签名链、一次上传与远端 SHA 回读达到待复核。
- [ ] 重传、额外 multipart、跨岗位、伪造签名描述、未知/中断、暂停和输入漂移继续停止。
- [ ] 最终 apply、autofill、其他 POST 和替代投递请求为零。
- [ ] 受影响测试、完整离线和后继安装版/真实验收分别留证；未用静态代码阅读声称真实上传通过。

## 复盘后的优先级与验收范围

P1。保留上传实现及合成证据，真实上传仍为未尝试。新增 30 的安装版合成前置与 18 的真实控件前置；不重复开上传实现票。

- [ ] 当前安装版合成链与实际必填控件回读通过，取得用户新的恢复许可，并重新核对具体批准材料、目的地与原页归属。
- [ ] 一次实际上传绑定同一岗位、intent、文件字节、签名链和表单附件；HTTP 200、文件名出现或本地队列成功不能替代远端 SHA 与原页附件回读。
- [ ] 上传后重新观察全部必填字段，尤其用户已更正的邮箱；若 PDF 解析改回旧值则停止，不能自动重填或声称 ready。
- [ ] 未知结果立即暂停并保留一次派发记录；重开 App、明确 recheck 或客户端 fallback 都不能自动重传，最终 apply/Submit 为零。

沿用[31](31-bounded-execution-protocol.md)的限时、停止与真实阶段报告。关闭范围是本票上传及字段保全证据，不把它写成雇主接收。

## Verification and evidence

遵守 diagnosing-bugs、tdd、CONVENTIONS；公开 fixture 均为合成岗位与数据。业务运行只由安装版 App 启动；不得用聊天 API、脚本或新浏览器替代第 11 票。

## Resolution comment

2026-10-17：只读检查官方客户端静态依赖确认普通 resume 需先取签名描述，再向对象地址发 multipart，最终投递另用 apply。现有 guard 只支持其他已审查协议，不能开放一般 POST。尚未触发真实上传，先实现可核验的最小兼容层。静态源码只作协议依据，不是上传回执；真实存储地址、响应和对象字节由运行时严格核验。

官方匿名签名描述已作只读观察，字段、对象绑定及精确存储目标见[协议观察结论](../assets/workable-resume-protocol-observation-20261017.json)。未传输个人资料或 PDF；签名凭据不进入公开证据。该观察仅用于限定兼容范围，不是上传验收。

实现与安全审计已冻结，25 项合成浏览器及 96 项受影响离线通过；实际 RED、重定向零接收、未知恢复和精确字节回读见[源码验证](../assets/workable-resume-source-verification-20261017.json)。当前完整默认离线运行中；后继包、原生及真实发送尚未验收，保持 open。

冻结源码完整默认离线 **1975 passed、188 deselected，245.94s**，Ruff/format/diff 通过。独立新包的搬移运行、签名、摘要、包内运行时、合成 PDF、Host/CSRF 和父管道退出均通过，见[统一离线与包验证](../assets/ats-fixes-offline-package-verification-20261017.json)。尚未以此关闭安装版/真实验收。

后继包已安装并核对全部字节、签名、当前状态与回退保留；两项权限对当前安装身份重新绑定后，实际原生宿主离线诊断通过，见[当前安装与宿主证据](../assets/native-ats-fixes-installed-host-20261017.json)。该诊断不含真实控件填写或 ATS 上传，真实业务仍待本票对应验收。

2026-10-17 复盘后建票：用户仅要求修复分解，本轮未恢复业务。已补 Priority、后继依赖及具体剩余验收；原状态、责任人和历史记录保留，新修复票见执行导航。

## Parallel execution group — 2026-10-20

[H — 组合回归、真实验收与交付](../../open-ticket-parallel-plan-2026-10-20/README.md#h-integration)。跨票顺序、共享文件及原生实验串行约束见统一分组导航；本票状态、原领取、依赖与验收仍按上文执行。本次仅重组导航，不领取或扩大执行许可。


## Notes — 必要材料、路由与恢复后继 2026-10-21

共享 Worker 的材料记录和恢复上传现在区分字段、类型、材料 ID 与 SHA；不把一个附件的成功当作另一个成功。Workable 附稿仍无已核验发送契约，保持 unsupported_attachment_transport，不借用简历端点；未执行真实上传。

完整默认离线：4440 passed, 2 skipped, 460 deselected in 718.67s (0:11:58)；受影响离线 1097 项、本地浏览器 164 项均通过。[工程记录、失败历史及冻结输入](../../product-completion-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 原页材料安全更新后继 2026-10-21

新增真实隔离 Chromium 与 loopback HTTP 的原页双版本 resume presign/upload/download 回归，保留旧上传历史并核验新 SHA。该证据为本地传输契约，未执行真实 Workable 上传；未核验附稿仍不借简历端点发送。

完整默认离线：4450 passed, 2 skipped, 497 deselected in 727.15s (0:12:07)；受影响离线 1358 项、本地浏览器 217 项均通过。[工程记录、失败历史及冻结输入](../../bound-material-update-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 精准等待前必要材料与人工附稿修复 2026-10-21

首次上传前除空 input.files 外，核验原 resume 容器没有未知远端文件名或 view link；未知远端附件阻断原页填写与候选采用。只在原页确认为空时使用真实首传，不虚构 replaces 或旧上传凭据。既有精确 handle 换版验证保留，未执行真实 Workable 上传。

完整默认离线：4462 passed, 2 skipped, 532 deselected in 968.76s (0:16:08)；受影响离线 1370 项、本地浏览器 252 项均通过。[工程记录、失败历史及冻结输入](../../precision-material-preparation-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 可用优先重排 2026-10-21

普通resume已测；仅补正常autofill/目标确需附稿，消费已交付控件与Submit出口，不等通用控件整票。

Priority/Triage/票头依赖按本次重排更新；旧边与原字节见[审计及变更账本](../../usable-first-wayfinder-audit-2026-10-21/README.md)。原 Status、Assignee、Interaction、既有验收勾选及全部旧正文保持，不领取、不关闭、不替用户接受。源码接口依赖不等于安装或真实操作许可；App 未更新，真实申请继续暂停。

## 2026-10-26 本轮 Module 后继导航

本票继续持有原 Workable 平台适配缺口；新接管链的固定材料引用、懒构建和原上传回读由 [MC-06 / T07](../../module-completion-2026-10-26/issues/06-t07-bound-material-delivery.md) 承接。R6 合成测试与 T07 不替代本票真实站点接受。

本次仅追加范围导航，原 Status、Assignee、Blocked by、勾选及历史结论不变；未领取、实施或关闭本票。
