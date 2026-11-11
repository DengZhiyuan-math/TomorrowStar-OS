# 接通邮件到人工最终确认的后台流程

Type: feature
Label: wayfinder:task
Status: claimed
Priority: P1
Interaction: AFK
Assignee: 01a15926/root
Created: 2026-10-20
Parent: [申请主流程](../map.md)
Blocked by: [完成单岗位链路与故障恢复整体验证](09-integration-verification.md)、[独立限制最终Submit并退役请求批准](38-independent-submit-boundary.md)、[接通邮件处理设置与独立进度展示](42-mail-processing-settings-status.md)
Triage: awaiting-real-acceptance

## 当前精简范围 — 2026-10-20

## Question

如何将推荐、两库、共享材料、当前页执行及提交结果接入同一主控，完成持续线性投递？

规范：[产品规范](../../../docs/single-job-flow.md)；安排：[开发计划](../../../docs/development-plan.md)。本节是本次精简任务化后的当前范围，替代下方冲突的旧范围和验收。Status、Assignee和历史收据不变；本次不领取、实施或关闭。

本票是产品集成：消费[统一岗位主控并派生浏览器执行状态](39-single-orchestrator-derived-state.md)、[共享完整材料生成与自动检查](40-shared-complete-materials.md)及各专业模块。主控/状态重构、材料共享实现与[收敛默认入口与重复执行控制](41-consolidate-entrypoints-controls.md)的UI清理不再重复放在本票实现范围。先交付本票给入口清理和组合验收，不能反向等待它们。

当前验收：

- [x] 消费邮件全局处理记录，初始化/恢复采用已收录未处理项，持续只追加新项；无固定邮件/岗位总限额或1200秒总窗，不能只选最高分一岗后结束。
- [x] 复用既有匹配语义和用户路由：过低记因跳过，普通自动材料/填传至手动Submit，高价值且高匹配先完整初稿后提示精准调整，不臆造数值阈值。
- [x] 当前必需且重要的缺事实/冲突或未知结果停当前岗；答复入正确库后继续，不汇总未来问题或暗中做别岗。只有用户skip或明确完成结果才能推进下一岗；等待时邮件可收录。
- [x] 消费共享材料和指定当前岗接口；人工修改一次继续保留，提交由用户操作；观察明确结果后自动更新并续下一岗，不再要求例行“我已提交”/回执表单。
- [x] 已完成阶段和有效材料复用，skip保存进度可返回，正常重开与显式等待按现有模块结果处理；不再复制worker状态作恢复依据。
- [x] 同邮件周期的新候选可追加、去重并持久保存；首岗等待重要事实、冲突或未知结果时，当前执行岗仍为首岗，不分析、生成或填写后续岗，原页、材料、intent与历史保留。收录候选不等于激活下一岗。
- [x] 分别验证明确完成后激活下一岗、用户skip后激活下一岗及返回被skip原岗；跳过保留进度且不记为取消/成功，未知动作先核对、不重放。未skip且未明确完成时不切岗。
- [ ] 按上述行为校正旧追加用例，保留原batch_exists失败及旧断言的历史证据；不能以取消/替换活动批次、移除保护或仅改成接受batch_exists消除红灯。模拟整链与真实用户Submit→系统结果→下一岗分别留证，缺真实证据时仍标实际未验，不强迫用户为测试投递。
- [x] 列出本票仅持有的编排与路由调用；主控、材料和UI拆出后，不新增替代状态库或通用框架。

## 当前证据复核 — 2026-10-21，同一主App后继

按用户要求复用30号票、同一主App安装及隔离验收，不重跑旧矩阵。当前1—7及9按适用源码/模拟/安装分层证据满足，第8部分满足；Status继续claimed，原Assignee和依赖不变，Triage改为awaiting-real-acceptance。[逐项证据、调用清单与限度](../../ticket34-installed-reconciliation-2026-10-21/README.md)。上方“本次不领取、实施或关闭”保留原精简入票时点，本节记录后继核对。

39/40/41源码收尾和30实际worker完整加载映射已完成，不再列为本票缺口。第4、7项的工程/模拟范围已验证；真实自然人工Submit→系统明确结果→下一岗仍实际未验，归第8项，不以标注未验冒充整票完成。仅在用户恢复真实申请后取得相应实际证据；本轮不要求恢复、不强迫为测试投递。

本轮无产品源码、测试或App操作，不改正式unknown结果、fill intent、owner、原材料与已接受PDF记录。总体readiness/旧compatibility诊断unknown继续保留；不清除旧回执，不恢复日常证明门槛。下方原历史正文与旧勾选字节保持，早期“源码未完成/未安装/worker loaded null”不再作当前缺口。

以下保留原范围与历史证据，不将新期望追写为旧票未完成原因。

## User contract

读取 email 推荐 → 计算匹配 → 基于已存事实生成岗位专用简历 → 填写和上传 →
提示用户到原网站最终确认，是系统固有流程。不能靠逐阶段按钮串联，最终 Submit 由用户操作。
一次启动授权本轮已有事实及系统生成 PDF 的发送，不伪造逐岗材料人审。

## Acceptance criteria

- [x] 后端持久推进本轮有边界的邮件、匹配、简历、填写与上传，不依赖界面轮询。
- [x] 仅消费本轮邮件来源；旧推荐、来源冲突、重复申请及已保存排除偏好不混入。
- [x] 复用匹配公式和分数排序；没有臆定分数阈值或新的人工评价表。
- [x] 发送绑定本轮授权、具体岗位、国家、资料与 PDF；保留锁内权限和版本复验。
- [x] 后端维持自己的填写控制权；不抢占手动控制，不覆盖旧原页或重放未知动作。
- [x] 补充缺失事实保存入库后可继续确定的填写，不加重复“恢复”确认。
- [x] 保存完成或问题通知，主 App 在后台也可提示；最终 Submit 不在自动操作集合。
- [ ] 唯一主 App 固定身份构建、安装及随机不同真实岗位验收分别留证。

## Current limits

用户已明确授权关闭未填写、未上传的失败页并更新主 App。唯一主 App 已以原固定身份更新，
正常入口及安装版与签名候选一致性已核验；原未知动作、回滚副本和材料均保留。
实际一轮已自动完成三封真实邮件、十个完整 JD 读取及首项匹配；第二项分析归属校验失败，
v5 已将精确已知内部分析失败逐岗保留并跳过，后续岗位已在同一批次自动继续。
v6 包内212项检查通过，两轴增量审查无遗留；原邮件运行、授权和截止时间保持不变。
实际十个 JD 均处理完毕，八个保存分析、两个明确输出校验拒绝留存跳过；系统已自动为
选中的真实岗位生成绑定 PDF。原生后台权限及责任链实际复验通过。
当前材料门禁因历史执行器仍有未知填写动作而停止，该原记录字节保持不变。
新任务无 worker_ref，未填写、上传或最终提交；真实新页面验收仍未完成，保持 claimed。
33 的真实表单初始化阻塞不会因流程编排存在而消失。
离线单元及 API 检查只证明软件行为，不代替真实字段、附件及原页待复核验收。
不引入 Gmail 定时全量同步、收件箱修改、自动联系招聘者或自动最终提交。

上述七项勾选限于实现和离线接口／原生协议检查；不是实际雇主页面验收。
固定源码、包内检查、两轴审查及完整默认编译超时边界见
[本轮证据](../../automatic-mail-pipeline-2026-10-20/README.md)。

## Comments

### 2026-10-20 精简方案入票

当前实现职责和前置依赖按本次方案收敛；原Status、Assignee及历史验收未改。原依赖如下，仅作历史，不参与当前前沿查询：

原 Blocked by: [增量保存邮件岗位后标记归档并延后取得JD](35-mail-capture-label-archive.md)、[复用两库事实并按影响保存更正与更新](36-information-reuse-impact-updates.md)、[支持已观察到的通用 ATS 自定义必填控件](18-generic-ats-controls.md)、[支持 Workable 普通简历字段的受控上传与回读](20-workable-resume-upload.md)、[支持当前岗位已确认邮箱的更正](23-current-job-email-correction.md)、[诊断原生会话中断并验证阶段恢复](27-native-interruption-recovery.md)、[核验当前安装身份与在途版本交接](28-installed-readiness-version-handover.md)、[一次继续人工交接并观察Submit结果和可恢复跳过](37-manual-submit-observation-continuation.md)

## Existing single-job append regression diagnosis — 2026-10-20

只追加诊断证据，不领取、不转派、不关闭本票；票头仍为 `Status: claimed` / `Assignee: 01a15926/root`。

当前源码单独复现 `tests/test_single_application_worker.py::test_same_email_cycle_appends_next_job_and_preserves_waiting_page`：`1 failed in 0.15s`，第二次 `prepare` 在 `WorkerService._prepare` 的既有活动批次保护处返回 `PortalDataError(batch_exists)`。首岗等待输入且原页保留时，现接口不允许把第二岗追加为同批次候选。

同一用例已在本轮初始恢复副本提取的完整旧 `src/` / `tests/` 中单独运行，确认实际加载旧 `application_worker.py`，得到相同的 `batch_exists` 失败：`1 failed in 7.01s`。日志：`/private/tmp/tomorrowstar-simplification-20261020/single-append-before.log`；当前全库相同失败保留在同目录 `full-offline-final.log`。验证恢复副本中的 worker/test 整文件与 `before-source-tests-tickets.tgz` 字节一致，且 `_prepare` 与该测试函数的源码在恢复前后均未改变；worker 的本轮事实复用修改仅位于 `resolve`，测试文件仅合并重复import。

此项为本票已有验收中的集成缺口，不是本轮35/36/38实现新增失败。后续应由本票负责人设计并实现同一邮件周期的候选追加/去重接口：保留首岗active/waiting、batch/job归属、原页、intent和历史，仅追加尚未执行候选；等待期间仍不得推进另一岗。不能通过取消或替换活动批次、删除保护、改变该测试为接受 `batch_exists` 来掩盖缺口。本次未修改生产代码或断言，未操作真实申请。

### 用户授权的验收修订 — 2026-10-21

[当前工作审计](../../work-audit-2026-10-20/README.md)确认旧追加用例存在验收契约冲突：首岗已设为needs_input且原页打开，未skip或明确完成便要求serial_application_id切到第二岗。当前生产源码尚无该字段；旧测试失败不是已发生越岗执行的证据。

本次按用户授权修订当前验收，区分候选收录、持久排队与当前岗激活，分别测试等待不切岗、明确完成后续岗、skip后续岗和返回原岗。旧要求“同邮件下一岗追加的batch_exists失败回归通过”保留为历史表述，不再解释为必须原样满足切岗断言；[原失败日志](../../work-audit-2026-10-20/assets/focused-tests.log)及上方诊断不改写。本次未改测试或运行代码，未宣称修复；Status、Assignee、Blocked by及既有历史勾选不变。

### 等待期间只收录候选的有界进展 — 2026-10-21

公开pipeline capture复用既有capture-only intake及RecommendationStore，先保存幂等收据，等待时收录/去重候选而不分析、生成或填写另一岗。当前task、原页、PDF、intent、worker与等待通知保留；普通JD读取不被替换。派发前保存失败不读取；派发结果未知、最终收据保存失败重开及跨周期重复请求均不重派。intake读取失败只显示明确局部错误，当前岗仍可见。

旧直接prepare追加第二岗的矛盾切岗断言已由worker保护负例和公开capture正例分别覆盖，原batch_exists失败和旧测试原文保留。真实capture后原岗语言Continue仍绑定原source-chain而不绑定最新intake run；原身份或顺序改变仍拒绝。受影响582项包含完整pipeline/收录110项，两者重叠不相加；完整默认离线待后继结果。见[工程进展](../../ticket-progress-2026-10-21/implementation.md)。

此切片没有完成持续自动收录、取消旧总窗/限额、全局未处理推荐串行激活、完成/skip续岗或返回原岗；不以局部绿色关闭本票或声称真实Submit闭环。原状态、负责人、依赖和历史证据不变。

### 后继完整运行结果 — 2026-10-21

V3完整默认4171 passed、2 skipped、425 deselected、21 errors；后继通知九项接口夹具问题未重现。剩余21项是原生Web桥共享Swift编译60秒超时，不是候选越岗或动作断言失败，也未记为通过。当前capture切片仍不等于持续线性编排，完成/skip续岗及返回原岗继续未完成。

完整输入、原始结果、独立核验及诊断见[工程记录](../../ticket-progress-2026-10-21/implementation.md)。本条只追加结果，原负责人、状态、依赖、历史勾选和证据不变；真实申请继续暂停。

### 三项 P2 后继修复及完整默认离线验证 — 2026-10-21

已修复capture替换尚未采用的原邮件结果：原读取及其主动暂停恢复窗口在采用前拒绝新收录，不变更原checkpoint、来源链或执行岗；采用后可收录。原start请求先去重；独立暂缓、低优先级、过期等排除先于语言询问。持续自动收录、去旧总窗/限额、全局串行激活、完成/skip续岗和返回原岗仍未完成。

新增12个回归节点，逐项保留RED/GREEN；受影响14模块557 passed，完整默认离线4204 passed、2 skipped、425 deselected，755.36s、exit0。原生Web桥21项本轮均通过；原夹具、60秒时限及缓存策略未改，旧4171/21-error结果与诊断不改写。747份登记输入前后相同；独立只读代码复核未发现新增问题，不冒称其独立重跑测试。

差异、原始日志、输入核对和剩余范围见[本轮工程记录](../../p2-regression-fixes-2026-10-21/README.md)。本条只追加证据，不勾选或关闭整票，不改变Status、Assignee、Blocked by、历史勾选或其他证据；App暂不更新，真实申请继续暂停。


## Notes — 持续主线源码后继 2026-10-21

已消费持久推荐队列并只处理当前岗：取得 JD、匹配、完整 LaTeX / PDF 检查、真实 Worker 准备。移除旧总时间窗；等待用户或 Submit 时只继续收录新邮件，保留原页和任务。明确来源未知或业务冲突仍停当前岗。完成 / skip 续岗与返回未因此完成。

完整默认离线：4263 passed, 2 skipped, 428 deselected in 661.45s (0:11:01)；[工程记录与原日志](../../automatic-mainline-2026-10-21/README.md)。旧三项 P2 的独立冻结记录及全部失败历史保留。Status、Assignee、依赖、既有勾选均不变，不新增票、不关闭本票；App 未更新，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 当前岗继续与事实材料后继 2026-10-21

同一Worker批次只执行明确当前岗；跳过保留原任务/页/PDF/claim/未知intent，返回恢复原岗。到最终确认时系统停止写入，用户直接在原页Submit；只消费具有当前岗归属的明确成功，未知或拒绝不推进。等待时持续收录保持原实现。

完整默认离线：4349 passed, 2 skipped, 432 deselected in 676.79s (0:11:16)；[本轮工程、复核与原日志](../../linear-continuation-2026-10-21/README.md)。初轮完整运行因发现缺陷主动中止，旧失败/修复/绿色结果分别保留。Status、Assignee、依赖与原勾选不变，不新增票、不关闭本票。App未更新，真实申请继续暂停，最终Submit始终人工。


## Notes — 必要材料、路由与恢复后继 2026-10-21

普通岗位沿既有 categorical route 自动推进，低路由记因并处理下一岗；精准路由完成完整简历后等待，一次 Continue 复用原稿或人工稿。暖恢复、主动暂停和未知结果继续绑定当前岗；精准初稿后的新必要附件由 Worker 后续发现生成，未宣称全部附件在首次精准等待前完成。

完整默认离线：4440 passed, 2 skipped, 460 deselected in 718.67s (0:11:58)；受影响离线 1097 项、本地浏览器 164 项均通过。[工程记录、失败历史及冻结输入](../../product-completion-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 精准等待前必要材料与人工附稿修复 2026-10-21

同一邮件岗位/Flow/Worker/run/Page 先发现并准备完整简历和已知必要附稿，再进入首次 precision_adjustment。等待前零填写、上传、Next/Submit；缺失真实证书等保持等待；一次 Continue 复用已生成材料，无重复模型/编译。窄显式 JD 解析不代表任意自然语言要求全覆盖。

完整默认离线：4462 passed, 2 skipped, 532 deselected in 968.76s (0:16:08)；受影响离线 1370 项、本地浏览器 252 项均通过。[工程记录、失败历史及冻结输入](../../precision-material-preparation-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 浏览器、材料与默认入口后继 2026-10-21

默认推荐和手工JD统一调用既有Pipeline接纳，只持久化顺序待办，不创建Flow或替换当前岗；先有推荐顺序、暂停时接纳、幂等冲突和重开均覆盖。真实邮件、安装及APP-12完整真实闭环继续保留。

完整默认离线：4487 passed、2 skipped；本地合成浏览器：372 passed。受影响集合已包含在最终完整默认/浏览器运行，重叠结果不累加。[工程、原日志与最终冻结输入](../../browser-material-entry-engineering-2026-10-21/README.md)。早期统一失败、独立审查和修复均原样保留。Status、Assignee、依赖和既有验收勾选不变，不新增或关闭票。App未更新或启动，真实申请继续暂停，最终Submit始终人工。


## Notes — 可用优先重排 2026-10-21

已有编排/事实/材料/当前岗公开契约可消费；移除各票安装/真实尾项的整票等待，具体ATS限制记录在候选支持矩阵，不偷换整链验收。

删去整票等待只允许消费已交付接口、先准备有限可用旅程。原验收条目全部保留：状态副本收敛、完整组合、适用平台与真实接受未满足时，不得关闭整票或宣称 APP-01–18 全部验收。有限候选明确列支持路线和未支持项；具体缺陷仍交原专业票，不用“能停下来”冒充已自动完成。

Priority/Triage/票头依赖按本次重排更新；旧边与原字节见[审计及变更账本](../../usable-first-wayfinder-audit-2026-10-21/README.md)。原 Status、Assignee、Interaction、既有验收勾选及全部旧正文保持，不领取、不关闭、不替用户接受。源码接口依赖不等于安装或真实操作许可；App 未更新，真实申请继续暂停。


## Notes — 42/33集成与最小安装准备 2026-10-21

本轮已与原负责人01a15926/root协调：当前聊天交付真实Pipeline/Flow/Worker/Runner的7项组合回归，原负责人交付30的可执行场景矩阵、命令与恢复/实际加载读回准备。复用42的原值标签/局部错误/收据及33的Ashby公开初始化，不重写主流程。等待/未知动作/显式暂停时邮件收录、后台poll、archive回包丢失、服务重开、相同请求幂等与先inspect不重归档均保留原岗/页/材料/runtime；真实Flow skip/return保留未知intent，公开初始化不记申请成功，最终Submit继续阻断。

准备复测发现旧固定HTML fixture未实现当前guard所需bounded-fetch响应，导致public_read_result_unknown。新增4模式RED/GREEN，只补固定GET和既有严格参数的内存响应；没有改生产Runner、请求保护、材料或业务编排。原5浏览器失败已全部转绿，未放宽超时。

最终完整默认离线4608 passed、2 skipped、561 deselected，878.11s；812项输入前后相同。受影响197 passed，隔离浏览器18 passed，均有独立输入/原日志且重叠不累加。2个skip为原有显式opt-in PDF性能/渲染benchmark。独立增量审查无未解决发现，Ruff通过。

[统一交付、源码差异与冻结收据](../../ticket34-30-integration-preparation-2026-10-21/README.md)、[编排调用清单](../../ticket34-30-integration-preparation-2026-10-21/call-inventory.md)、[原负责人30准备](../../ticket34-30-integration-preparation-2026-10-21/owner30/README.md)。后继源码候选423项，不是安装包或独立完整测试checkout。

仍有G1合成Native邮件/设置桥与G2 Ashby安装场景未接入，不能把目标七步清单当成已可一次执行的原生整链；原负责人已约定在本轮冻结交接完成后串行接手这些共享入口。当前App未更新或启动，真实配置/邮箱/申请未操作，未验证实际加载worker、原生安装组合或自然人工Submit。Status、Assignee、依赖、原验收勾选与历史保留，本票继续claimed。


## Notes — G1/G2最小合成入口后继 2026-10-21

父任务4608/2完整默认结果和423项候选已完成冻结交接后，原负责人补齐G1固定 `--synthetic-mail` 与G2 `ashby-bootstrap` 源码入口。复用NativeLaunch、Intake、Pipeline、Worker与原Runner guard；没有新增业务状态库、重复审批或第二套流程。

G1隔离配置只保存标签，固定目录不变；两页推荐和持久模拟mailbox覆盖标签未配/有效/坏值、archive回包丢失、重开inspect且不重复archive。新入口实际后端可推进现有顺序队列，缺重要事实停当前岗，capture不创建第二岗。G2固定公开posting/organization各读取一次后原表单出现，缺答案保持等待；旧浏览器/上传场景保持，零自动Submit。

本后继完整默认离线4632 passed、2 skipped、562 deselected，936.66s；受影响434 passed、9 deselected，隔离浏览器19 passed、77 deselected。814项输入前后不变，重叠套件不累加。原生harness/Swift类型检查、Ruff及只读整合复核通过；两项skip仍为显式opt-in PDF性能/渲染benchmark。新源码候选425项，candidate `preparation-candidate-36f4e3ca0017eba829b90172b148984e7eb0a4b50a6510905b57f22424097868`，不是安装包或独立完整测试checkout。

[后继实现、历史失败、冻结输入与原日志](../../g1-g2-synthetic-entrypoints-2026-10-21/README.md)、[新入口命令及暂停边界](../../g1-g2-synthetic-entrypoints-2026-10-21/commands.md)。G1固定岗位故意缺申请国家，不宣称填写/上传整链；G2 headless仅是源码检查。实际包加载、原生安装组合和真实自然Submit仍未验证。App未构建、更新或启动，真实配置/邮箱/申请未操作。Status、Assignee、依赖和全部旧正文/勾选保持，本票仍claimed；App更新和真实申请继续暂停，最终Submit人工。


## Notes — 剩余验收核对与国家等待恢复 2026-10-21

逐项核对30的8项、34的9项当前验收，复用既有G1/G2、邮件/材料/当前岗模块。发现并修复缺申请国家的Continue死路：新记录与缺恢复标记的旧材料等待记录，重开后都可继续同一task。未补事实仍回原等待，不重做有效材料；公开PATCH明确地点后，经既有Flow.update_inputs→analysis重新采用变化输入，旧PDF/历史保留，不绕过_fresh。显式其他等待与部分标记不冒充这个已知旧状态。没有新增country字段、用户审批、状态库或平台审核点。

新增真实Flow/Pipeline/Worker/Runner的认证HTTP组合：模拟人工请求/页面结果只有success才选择下一来源；rejected/unknown保留原岗，不重填重传；skip→选第二来源→返回仍保留原task/page/PDF/未知intent。复用现有实现，不重做提交协议。此次只到下一来源选择，未宣称第二worker完成填写上传，更不代替真实自然Submit闭环。

最终完整默认full-v2：4641 passed、2 skipped、562 deselected，905.00s；受影响affected-v2：309 passed、1 deselected，105.39s；814项输入前后与最终一致。Ruff通过。首个full-v1因补旧记录兼容主动中断，1957 passed的部分结果、exit2及说明均保留，不当作完整通过；各局部RED与修复日志保留、不累加套件通过数。最终v2源码候选425项，candidate `preparation-candidate-a569cf8dd0bb73d33b216ed88532082045f1b75656964c3f350f1904d7d91e23`，不是安装包或独立完整测试checkout。

[逐项验收与集中确认队列](../../ticket30-34-remaining-2026-10-21/acceptance.md)、[实际共享/兼容保留调用及39剩余位置](../../ticket30-34-remaining-2026-10-21/calls-and-remaining.md)、[源码差异、原日志与最终收据](../../ticket30-34-remaining-2026-10-21/README.md)。默认完整材料/导出已共享，旧独立handoff/lab/材料审阅仍有兼容调用；39状态副本收尾与40/41取舍不在本轮伪称完成，不因原整票未关闭阻止已明确的集成修复。

App未构建、更新或启动，真实配置/邮箱/ATS未读写。30/34原负责人、依赖、Status、Triage及全部历史正文/验收勾选保持，继续claimed；安装加载/交接组合和真实自然提交到下一岗仍未验。用户后续集中决定何时恢复唯一App更新/安装验收、何时恢复真实申请；本轮不要求立即解除暂停，最终Submit始终人工。


## Notes — 同一主App维护与安装验收准备 2026-10-21

核对最新39/40/41冻结候选426文件及820项登记输入，当前读回均无变化；源码收尾不替代安装或真实接受。本轮形成[30/34剩余验收、更新/回滚及最小安装方案](../../ticket30-34-main-app-plan-2026-10-21/README.md)，逐项按本票顶部当前精简范围映射。修正旧回滚备份后缀及包内生成器命令假设，原历史命令与失败证据不改写。

只读原安装包严格签名核验通过，旧包与最新源码差异单独登记；进程枚举因当前沙箱限制未完成，实际worker/原页活性与交接仍未验。本轮未构建、更新、安装、启动App或权限探针，未触及真实配置、邮箱或ATS。集中决定仅为恢复App维护/隔离安装窗口、条件性在途交接安排、另行恢复真实申请的时机；当前暂停继续，最终Submit人工。Status、Assignee、依赖及所有旧勾选不变，不以本方案关闭本票。


## Notes — 授权主App维护与最小隔离安装 2026-10-21

用户在协调聊天后续明确授权后，原负责人已完成唯一主App的构建/备份/更新及G0—G3最小隔离旅程。首轮G1实际继续失败后已回滚，最小Pipeline修复经后继冻结、完整4661通过2跳过、受影响221及浏览器86通过，再安装v3。G1恢复/收录/skip返回，G2公开初始化缺答案等待，G3字段/一次PDF上传及远端SHA、同岗邮箱更正、暂停同根重开均有实际证据；Submit为0，真实申请未恢复。

[维护、事故/失败保全及最终回执](../../main-app-maintenance-2026-10-21/README.md)；[本票逐项覆盖与准确剩余](../../main-app-maintenance-2026-10-21/acceptance.md)。实际worker完整loaded_engine_revision为null，启动32文件匹配不能替代完整加载身份。原四正式运行根inventory、配置最终原字节、旧包备份及进程退出已核验；工具曾误开普通窗口并重排配置JSON，语义相同且原字节已恢复，事故原件保留。未新测活旧worker跨版本兼容、非空未知intent、所有路由真实材料质量或自然人工Submit续岗；不把局部安装接受等同整票结案。

原Status/Assignee/依赖/旧勾选不变；无新增审批或立即用户确认。本授权维护窗口已结束，真实申请继续暂停，后续恢复时机统一待用户决定。

## 2026-10-26 本轮 Module 后继导航

本票继续持有真实自然人工 Submit → 明确结果 → 下一岗接受；新接管的自动派发、合成整链和真实 ATS 分别由 [MC-08](../../module-completion-2026-10-26/issues/08-t09-app-dispatch-controls.md)、[MC-09](../../module-completion-2026-10-26/issues/09-t10-synthetic-chain.md)、[MC-12](../../module-completion-2026-10-26/issues/12-t11-real-ats.md) 跟踪，均不代替本票自然提交闭环。R6 不足以关闭本票。

本次仅追加范围导航，原 Status、Assignee、Blocked by、勾选及历史结论不变；未领取、实施或关闭本票。
