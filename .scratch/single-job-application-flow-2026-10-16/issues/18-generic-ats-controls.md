# 支持已观察到的通用 ATS 自定义必填控件

Type: task
Label: wayfinder:task
Status: claimed
Priority: P1
Interaction: AFK
Assignee: 01a15ab3/root
Created: 2026-10-17
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [构建并在安装版 App 验证单岗位合成流程](10-installed-app.md)、[独立限制最终Submit并退役请求批准](38-independent-submit-boundary.md)
Triage: bounded-navigation-followup

## 当前精简范围 — 2026-10-20

## Question

如何复用适配器与通用浏览器完成当前表单控件、普通导航与登录后的剩余填写？

规范：[产品规范](../../../docs/single-job-flow.md)；安排：[开发计划](../../../docs/development-plan.md)。本节是本次精简任务化后的当前范围，替代下方冲突的旧范围和验收。Status、Assignee和历史收据不变；本次不领取、实施或关闭。

最终动作限制及请求批准退役由[独立限制最终Submit并退役请求批准](38-independent-submit-boundary.md)拥有，本票消费其接口，不再重复实现独立授权体系。

当前验收：

- [ ] 公开读取、正常导航、草稿保存、字段和选项、动态问题可自主处理；缺适配或固定控件定义时使用通用路线，不因平台名单停止。
- [ ] 复用已有登录；真正需要本人登录/MFA/CAPTCHA时停当前岗，处理后一次继续。
- [ ] 经独立Submit限制的出口执行；普通Next可走、最终申请交用户。对应接口集成回归包含实际目标和字段回读，不复制请求grant或新的批准逻辑。
- [ ] 真实岗位覆盖仍由现有下游主线验收负责；实现关闭不反向等待组合票，重要未知事实与skip按当前规范。

以下保留原范围与历史证据，不将新期望追写为旧票未完成原因。

## Question

真实表单使用 readonly combobox、隐藏代理输入和带组标签的单选/复选时，能否正确识别、填写并逐项回读，保持未知结构停止？

## Work and reuse

- 仅复现已观察到的控件结构；公开回归用合成公司、问题及答案，不写真实表单身份。
- 复用 hosted_ats 的 DOM 快照和 Cua 精确语义控件填写，不加入第二套执行器。
- 最小修复必填标识、代理控件、单选组标签与唯一 resume 识别；隐藏输入不得误填，optional photo 不上传。
- 不放宽导航、写请求或最终 Submit 门禁；上传协议若确实另有缺口，单独记录并修复。
- 安装版在更新后重新核对实际加载版本、权限与原任务恢复；真实链由第 11 票续验。

## Ownership

- src/career_evidence_graph/hosted_ats.py
- tests/test_hosted_ats.py 或对应现有浏览器回归中的最小控件用例
- 必要的 cua_driver.py 修改须先与根执行者协调

不是唯一执行者；保留他人工作，不改其他责任文件。

## Acceptance criteria

- [x] 最小合成表单在修复前明确失败，修复后通过原执行路径识别、填写与回读。
- [x] 标签/代理关联不明确、未知必填控件、跨岗位或页面漂移仍停止。
- [x] 导航与请求门禁未放宽，最终 Submit 为零。
- [ ] 受影响测试及完整离线、当前安装版与真实岗位验收各有独立证据。

## 复盘后的优先级与验收范围

本票保留已有实现与历史证据，P1 的剩余工作是当前安装版真实控件验收；不重复实现已通过的解析器。直接前置新增第 30 票。

- [ ] 第 30 票的当前安装版最小合成验收通过，再在用户明确恢复许可下执行真实控件验证。
- [ ] 对真实原页已观察的学历选择、语言单选、日期和其他必填控件，逐项记录标签、已批准答案、实际值与有效性；只扫描成功或两个普通文本字段不能关闭本票。
- [ ] 缺答案、未知必填或歧义代理仍停止；隐私声明须用户具体确认，不能由材料批准代答。
- [ ] 全部受支持控件的真实填写与回读通过即可认定本票范围；附件及整体 ready_for_review 分别由 20、11 负责，避免反向依赖。

真实后继直接沿用[第 31 票](31-bounded-execution-protocol.md)的预检、限时、首次未知结果即停止及阶段报告规则。当前停止决定不被本票更新撤销。

## Verification and evidence

使用 checkout launcher；先读 CONVENTIONS 与 diagnosing-bugs、tdd 技能。不得以测试通过代替真实第 11 票。私有数据与公开合成证据分开，保留原失败。

## Resolution comment

2026-10-17：在只读官方表单 DOM 核验中观察到 readonly combobox 与隐藏 required 代理、aria-hidden 原生 radio/checkbox、唯一 resume 与 optional photo；尚未填值或上传。先建立合成最小复现，不将源码预测写成已发生的外站失败。

源码及合成回归已冻结，独立审计结论与实际 RED/GREEN 见[源码验证](../assets/ats-controls-resume-source-verification-20261017.json)。第 18 票另修正两项审计发现的未知必填/跨组漏洞。完整离线与后继安装版仍待第 20 票冻结后执行；当前保持 open，不以源码结果代替真实链。

冻结源码完整默认离线 **1975 passed、188 deselected，245.94s**，Ruff/format/diff 通过。独立新包的搬移运行、签名、摘要、包内运行时、合成 PDF、Host/CSRF 和父管道退出均通过，见[统一离线与包验证](../assets/ats-fixes-offline-package-verification-20261017.json)。尚未以此关闭安装版/真实验收。

后继包已安装并核对全部字节、签名、当前状态与回退保留；两项权限对当前安装身份重新绑定后，实际原生宿主离线诊断通过，见[当前安装与宿主证据](../assets/native-ats-fixes-installed-host-20261017.json)。该诊断不含真实控件填写或 ATS 上传，真实业务仍待本票对应验收。

后继 CSS 必填语义修复已随新包安装并由新 worker 源清单确认加载；完整默认离线 **2072 passed、191 deselected，235.39s**，原时限原生专项 **44 passed，59.04s**，见[追加离线与包证据](../assets/bootstrap-controls-final-offline-package-addendum-20261017.json)。旧隔离浏览器已终止，目录与原始元数据在独占原 worker 锁后完整归档，不声明旧资源清理成功，也未采用旧 profile。新运行在权限检查处停止，尚未进入真实控件填写；当前安装身份需重新绑定已授权权限。本票保持 open。

后续公开结构核验发现，部分语义 checkbox 的必填星号只在自身 CSS `::after`，既不在原生 required 属性，也不在关联标签文字。补充合成用例实际 RED/GREEN 后，复用既有 `requiredLabel` 识别唯一标签关联的语义组；未映射或歧义的 CSS/ARIA 必填组继续拒绝。缺少确认答案时停在 `needs_input`，不勾选、不上传；不把资料批准推断为隐私同意。正向及未知组回归通过，独立审查 66 passed、23 deselected；组合与后继包仍分别留证。真实原表单随后已关闭，原进程链结束；不修改旧运行证据或声称旧进程热加载此修复。

2026-10-17 复盘后建票：用户仅要求修复分解，本轮未恢复业务。已补 Priority、后继依赖及具体剩余验收；原状态、责任人和历史记录保留，新修复票见执行导航。

## Parallel execution group — 2026-10-20

[H — 组合回归、真实验收与交付](../../open-ticket-parallel-plan-2026-10-20/README.md#h-integration)。跨票顺序、共享文件及原生实验串行约束见统一分组导航；本票状态、原领取、依赖与验收仍按上文执行。本次仅重组导航，不领取或扩大执行许可。

## Comments

### 2026-10-20 精简方案入票

当前实现职责和前置依赖按本次方案收敛；原Status、Assignee及历史验收未改。原依赖如下，仅作历史，不参与当前前沿查询：

原 Blocked by: [构建并在安装版 App 验证单岗位合成流程](10-installed-app.md)


## Continuation handoff — 2026-10-20

用户明确要求继续本票，先核对原负责人以免重复劳动。已只读查看原子任务 `01a1492d-de8a-7233-baed-e7f4617de4d6`：最后一轮已 completed 并冻结，当前 notLoaded；根聊天“完成单岗位申请流程 tickets”亦 notLoaded，最后仅规划后继修复。没有向其他聊天发送消息或恢复其业务。

原 Assignee `01a146b9/ats_controls` 的既有控件实现与 RED/GREEN、CSS必填、后继包/宿主记录继续保留；本次由 `01a15ab3/root` 接续当前 2026-10-20 新范围，不重写已完成解析器。旧真实路线仍暂停。先补明确普通 Next、多步阶段、动态问题关联和登录后一次继续；复用已关闭的独立Submit出口，不恢复逐请求grant。新实现只在合成/离线环境验证；真实组合验收仍由既有主线承接，最终Submit由用户操作。

开始前恢复副本：`/private/tmp/tomorrowstar-ats-continuation-20261020/before-src-tests-ticket.tgz`。保留现有脏工作与人工修改；原材料、页/附件和未决动作不清理。

## 接续软件增量 — 2026-10-20

已在既有解析器和执行路径上增加：无原生代理的明确语义按钮组合框、动态插入/重排时的控件稳定身份、同表单显式阶段普通 Next、原页验证完成后一次 Continue，以及最终复核对当前隐藏附件字节的核验。复用现有 intent/attempt/run/page、执行所有权和独立 Submit 限制；未新增请求批准、执行器或平台名单。已保存原负责人核对、恢复副本和独立审查发现的 RED/GREEN。

当前增量及证据见[接续实施记录](../ats-controls-continuation-20261020.md)。Status 保持 claimed，当前综合验收不整体打勾：明确同文档阶段以外的导航、未识别草稿/登录协议、真实 SSO/MFA/CAPTCHA 网络链路仍须继续处理；不能把模拟登录后的继续写成真实登录成功。安装版及真实组合验收仍归既有下游主线，旧真实路线继续暂停。最终 Submit 由用户操作。

最终回归：浏览器 **178 个不同用例通过**；新增登录继续/导航 checkpoint **24 项**随完整默认运行通过，独立受影响默认收据为 **176 passed**。完整默认结果为 **4025 passed、1 failed、2 skipped、424 deselected、125 errors**；唯一断言失败为原有批次追加 `batch_exists`，125 项错误全部为临时 Swift 夹具编译超时，未进入业务断言。原失败、精确源码指纹、范围限制和恢复副本均留在实施记录及证据目录，不把局部通过改写为全套或真实验收通过。

## 请求诊断接续 — 2026-10-20

用户明确要求继续本票，先复用既有诊断定位跨页导航和登录相关未知请求。已核对实际留存、合成反例及本地官方客户端素材；可定位的真实阻断属于既有公开初始化专项，未取得完整跨页/登录协议，不重复实现其职责，也不以缺失记录证明历史行为未发生。

本次复用原请求诊断补齐导航/主 frame、发生时页面及等待状态，以及拒绝重定向的响应事实和脱敏目标。相同 guard、持久 checkpoint 与隔离浏览器回归验证缺口；不改放行、接管、结算或重放判定。详见[诊断接续记录](../ats-request-context-20261020.md)。原始请求指针、指纹及日志仅保存在独立私有证据目录。

本轮单元、受影响浏览器、Ruff 与格式检查通过。完整默认套件未整体通过，唯一失败仍为既有批次追加 `batch_exists`；其实现与测试未改，原失败继续保留。此前 Swift 夹具超时未在本轮复现。已核对冻结源码、历史材料及票据元数据，均保持预期范围。

Status 继续 claimed，综合 criteria 保持未整体完成。原材料、进度及人工修改保留；真实申请继续暂停，最终 Submit 由用户操作。


## Notes — 必要材料、路由与恢复后继 2026-10-21

必要附件按当前字段、draft path、材料类型和 attempt 保存；同 SHA 的简历与附稿分别核验。必填状态以当前页面为准，已变为可选或不存在的旧 required 记录不继续阻断。未知材料意义、多文件控件和来源冲突保持等待。

完整默认离线：4440 passed, 2 skipped, 460 deselected in 718.67s (0:11:58)；受影响离线 1097 项、本地浏览器 164 项均通过。[工程记录、失败历史及冻结输入](../../product-completion-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 原页材料安全更新后继 2026-10-21

简历更新核验当前字段、材料类型、exact attempt 与 SHA，并保留人工字段和其他附件。Ashby 不能借旧同名 attachment id 背书新材料；相同 SHA 也须核验当前材料身份。未知结果先核验原 attempt，不自动重传。 Workable 原 Runner 在新 intent 下仅获当前完整意图绑定的旧附件 GET 只读核验；不借此放宽上传或提交请求。

完整默认离线：4450 passed, 2 skipped, 497 deselected in 727.15s (0:12:07)；受影响离线 1358 项、本地浏览器 217 项均通过。[工程记录、失败历史及冻结输入](../../bound-material-update-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 精准等待前必要材料与人工附稿修复 2026-10-21

精准等待前原 Page 只观察与允许的语义读取，不 fill/upload/Next/Submit。JD-only 要求使用独立 requirement_id 与 quote/span/hash，未知真实附件缺失继续等待；多个 JD 要求与实际字段须双向唯一映射，不能按材料 kind 合并。

完整默认离线：4462 passed, 2 skipped, 532 deselected in 968.76s (0:16:08)；受影响离线 1370 项、本地浏览器 252 项均通过。[工程记录、失败历史及冻结输入](../../precision-material-preparation-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 浏览器、材料与默认入口后继 2026-10-21

原Runner/run/Page新增有界跨文档普通Next/Continue，严格保留岗位query和同源同路径GET、intent、字段身份及未知结果；仅同文档本人验证后一次继续。任意JS/POST、跨源/路径、完整reload/SSO、冷启动绑定和真实ATS仍未完成。

完整默认离线：4487 passed、2 skipped；本地合成浏览器：372 passed。受影响集合已包含在最终完整默认/浏览器运行，重叠结果不累加。[工程、原日志与最终冻结输入](../../browser-material-entry-engineering-2026-10-21/README.md)。早期统一失败、独立审查和修复均原样保留。Status、Assignee、依赖和既有验收勾选不变，不新增或关闭票。App未更新或启动，真实申请继续暂停，最终Submit始终人工。


## Notes — 可用优先重排 2026-10-21

已有控件与有界Next不重做；新reload/跨路径/SSO须先有具体可复现路径，不承诺所有平台。

Priority/Triage/票头依赖按本次重排更新；旧边与原字节见[审计及变更账本](../../usable-first-wayfinder-audit-2026-10-21/README.md)。原 Status、Assignee、Interaction、既有验收勾选及全部旧正文保持，不领取、不关闭、不替用户接受。源码接口依赖不等于安装或真实操作许可；App 未更新，真实申请继续暂停。

## 2026-10-26 本轮 Module 后继导航

本票继续负责原通用控件、导航及登录后继续；新专用 app-server 的有限视觉 intent、观察/文档绑定与提交守卫由 [MC-05 / T06](../../module-completion-2026-10-26/issues/05-t06-visual-actions.md) 承接。旧控件回归不证明新工具链通过。

本次仅追加范围导航，原 Status、Assignee、Blocked by、勾选及历史结论不变；未领取、实施或关闭本票。
