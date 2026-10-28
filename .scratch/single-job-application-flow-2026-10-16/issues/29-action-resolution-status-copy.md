# 统一旧动作核验与重新接管状态文案

Type: task
Label: wayfinder:task
Status: closed
Priority: P1
Interaction: AFK
Assignee: 01a150ef/resolution_copy
Created: 2026-10-17
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [把单岗位五阶段流程接入 App 界面](07-app-workspace.md)、[恢复打开超时后仍保留的原页复核入口](21-retained-page-recovery.md)

## 当前契约定位 — 2026-10-20

准确区分已保存/已排队/已回读仍有用；“已核验但待再次接管”及所有旧按钮门禁不再是当前产品契约，37用一次继续替代。

当前产品规范与执行顺序分别见[单岗位流程](../../../docs/single-job-flow.md)和[统一开发计划](../../../docs/development-plan.md)。本票既有Status、Assignee、完成记录和收据不变；关闭仅证明当时范围，不证明新规范已实现。下方与现行规范冲突的旧审批、白名单、总时间窗及运行门槛保留为历史，由现有后继承接，不重开、不追认，也不据此执行真实申请。

## Question

如何消除“旧动作结果尚未核验”与“已记录当前匹配”同时出现的矛盾，并准确呈现保存、排队、回读和待提交阶段？

## Problem and priority

来源：[复盘 P11](../test-findings-2026-10-17.md)。现有 needs_recheck 原因文案与最新 resolution 不一致。P1：用户必须能判断还缺哪个动作，不能用错误文案要求重复核验。

## Work and reuse

- 复用既有 intent、最新 action_resolution、control、job.status 和 observations；不增加并行状态机。
- 已核验但尚未 recheck 时显示“旧结果已核验，待明确接管”；manual_stop 和无结论仍明确未知。
- 岗位邮箱更正记录、one-use 排队、实际字段回读、附件回读与 ready_for_review 分开；历史 queued 不应永远显示“尚未回读”。
- 只改展示和必要的现有派生字段；保存文案或本地答案不能恢复执行、清除 intent 或把暂停记成完成。

## Ownership

- `portal_static/application_flow.js`、必要的 `application_worker.py` snapshot 投影与现有界面测试。
- 23 的已落地字段是复用基础，不要求第 23 票真实验收先关闭；多人共享文件先协调。

## Acceptance criteria

- [x] 无结论、current_matches、not_applied、manual_stop 及历史结论被后继覆盖的界面用例均准确且互不矛盾。
- [x] 已核验的同一 intent 不再被文案称为未核验；待明确接管仍保留暂停和原 intent。
- [x] 本地保存、已排队、已程序回读、附件已核验和 ready_for_review 不能相互替代；手工核验与程序核验来源清楚。
- [x] 后续 verified fill 到来后，更正历史的文字仍真实；未知结果不会误显示成功或“从未应用”。
- [x] 所有按钮沿既有门禁；纯展示操作不恢复、不重填、不上传、不 Submit。
- [x] 真实浏览器界面的合成状态矩阵与受影响回归通过；当前安装版隔离显示核验通过。

## Verification and evidence

使用已有状态与具体合成场景验证可见文案和按钮行为；不新增只复述实现的测试。纯文案无需无关全套回归，若改共享状态按 CONVENTIONS 完整验证。

## Authorization and stop boundary

本次只建票。验收优先合成；不重开原申请或用真实写入来制造界面状态。

## Resolution comment

2026-10-17：新建未领取，不改变第 23 票原功能范围或既有核验历史。

2026-10-19：核验直接前置 07、21 均 closed 后领取。仅执行源码与合成可见状态验证；当前安装版隔离核验留待统一候选，未通过前不闭票。真实申请保持暂停。

2026-10-19 源码阶段记录：已按 tdd 完成旧动作结论与邮箱历史队列文案的可见行为 RED→GREEN。复用当前同 intent 的最后结论，current_matches/not_applied 展示“旧结果已核验，待明确接管”，无结论或后继 manual_stop 保留未知门禁；明确展示人工核验来源。邮箱仅保存与曾排入一次性答案队列分开，历史排队不声称当前字段、附件或 ready_for_review 成功。未增加后端字段，未修改按钮或命令语义。专属合成状态矩阵与受影响已有浏览器回归通过，focused Ruff 与 diff 检查通过。布尔证据见[源码与合成检查](../../action-resolution-status-copy-2026-10-19/source-synthetic-checks.json)。

当前安装版隔离显示核验尚未执行，29 保持 open；真实申请继续暂停。用户转回材料 15 的人工逐项复核后，本次只作该最小源码收尾。后续实际邮箱程序回读仍须独立核验，不能从 queued 推断。

### 2026-10-19 — Installed successor native display checks

同一已验证包在隔离合成状态中，经原生界面验证无结论、current_matches 与后继 manual_stop。保存匹配结论后显示“旧结果已核验，待明确接管”，不再同时称同一 intent 尚未核验；后继停止结论覆盖此前显示，重新接管按钮恢复禁用。核验来源明确标为合成本地展示，无真实 ATS 原页、字段写入或上传。

回读确认只有 action_resolutions 追加，其他 job 字段、原 intent、runtime、paused 与空队列不变；未点击恢复或重新接管，未再启动 worker。原生与后端正常退出记录保留。此前实际包内浏览器矩阵通过仍保留；尚在独立核对整票矩阵及程序回读后的文案，不据此次局部安装显示提前关闭。

### 2026-10-19 — Program readback after queued correction

独立审查指出原矩阵只到 staged/queued，尚未覆盖本票第 4 项。已新增只读 snapshot 派生：最新更正对应完整排队绑定、同一 run/page/field、一次性答案指纹和当前 answer_ref 均匹配，且排队后出现已核验 fill，才显示历史程序字段回读。UI 明确这是采集时刻的记录，不证明当前字段、附件或服务端保存。原按钮与命令语义保持。

先得到缺少程序回读显示的 RED，再通过含正常及答案／字段／页面／运行／缺队列反例的浏览器矩阵；ready_for_review 缺完整保存回执时仍不宣称附件挂接，取得匹配 PDF 的独立回执后才显示。新增就绪面板与本票受影响文案合计 18 项浏览器测试通过，原生/程序核验来源分开，观察不产生 POST、spawn 或 store 变化。独立纯内存审查另验证顺序倒置、后继排队、值变化和异常时间等反例。

新派生改变共享 snapshot 契约，须在统一源码稳定后跑完整默认离线，再冻结新候选做安装邮箱阶段矩阵；旧安装字节的显示证据仍保留但不替代新候选验收。29 继续 open。

## Resolution — 2026-10-20

用户授权持续推进全部剩余票并集中保留人工审核/权限事项。本会话补齐工程展示验收，经独立critical逐项审查，六项均通过，按AFK软件/展示范围关闭；原Assignee作为来源保留，不表示其正在执行本轮操作。

当前未修改独立安装候选 `TomorrowStar Chrome PDF Verified.app` 经实际WKWebView完成11个状态场景：保存/排队/程序回读/缺保存回执/匹配保存回执，以及六种旧动作结论/后继覆盖。夹具状态均明确为合成注入，不是用户真实审核或实际远端读写。补齐夹具preview_url后重验五个邮箱场景，旧夹具和失败/局部证据保留。

每场景显式刷新后flow/worker字节保持；暂停、原intent和空命令队列保持，没有恢复/重填/上传/Submit。两轮原生20890/25913与后端20895/25926正常Quit/EOF关闭后退出，未出现申请worker/Chrome子进程。安装包1463清单项、strict/deep签名及原主App/连接配置保持。

最新受影响真实浏览器回归20通过/86.79秒，原始日志留存。共享snapshot源码与3512项完整默认离线基线/最终候选/安装包一致，相关UI函数与基线一致，不重复无关全套；四条其他错误文案不改变本票语义。工具首次取得窗口状态延迟334.753秒单列，不作为App启动时限或冷启动通过证明。

逐项审查与全部AX/回读/来源限制见[安装显示证据](../../autonomous-engineering-2026-10-20/native-status-display/README.md)和[独立验收审查](../../autonomous-engineering-2026-10-20/native-status-display/independent-review.json)。本票关闭不解除24/25/26/27/28/30及真实申请暂停；不宣称真实字段、附件、材料或人工接受通过。
