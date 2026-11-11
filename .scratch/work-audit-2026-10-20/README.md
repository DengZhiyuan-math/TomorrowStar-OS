# TomorrowStar 当前工作审计

审计时点：2026-10-20 23:46:11 Europe/Zurich。基准分支 `master`，HEAD `e4a26d0c24311d014d478f7f92e58a88e6709b4b`。
本报告是状态与证据快照；执行顺序继续以[统一开发计划](../../docs/development-plan.md)为准，不新增另一套计划。

## 当前结论

- 实时127张票：86 closed、17 resolved、18 open、6 claimed；合计24未关闭。已关闭统计包含不同范围和3项行政替代关闭，不能当产品完成率。
- 独立最终Submit出口38已关闭；18、35、36已有软件增量但整票仍claimed。主控、材料共享、人工结果观察及主编排集成仍未完成。
- 本轮聚焦回归126 passed、1 failed、36 deselected。失败仍为旧的`batch_exists`追加用例；该用例自身与当前等待语义冲突，见下文。未重复整套约16分钟的默认回归。
- 当前工作区与唯一安装版有14份运行源码/界面文件不同。安装包签名完整性通过，不能据此称最新源码已安装或原生能力已实际验证。
- 真实已有邮件→JD→分析→PDF证据；真实新岗填传及自然手动Submit→结果记录→下一岗闭环仍未通过。真实申请继续暂停。
- 研究Phase9仍进行中；首版清单的历史接受保留，pending后继尚未精确接受或封存。工程测试不代替能力评审、职业图确认或三份真实JD研究验收。

## 确认的发现

### P2：岗位语言例外没有进入实际筛选和准备门槛

当前[共用答案选择](../../src/career_evidence_graph/application_information.py)与`WorkerStore.resolve`采用更具体的岗位例外。
但[WorkerStore.language_levels](../../src/career_evidence_graph/application_worker.py)第574–600行仅取`scope == {}`的全局语言记录；实际prepare第1928行、浏览器`check_inputs`第630行及pipeline筛选仍消费此结果。

纯合成复现：全局German=A1，当前岗位的已确认例外=B2，JD要求German B2。分析返回`supported`、字段解析返回B2，但公开prepare报`job_requirement_mismatch`。同一组事实在不同阶段得出相反结论，可错误排除或拒绝当前岗。

[复现脚本](assets/language-scope-probe.py)及[输出](assets/language-scope-probe.log)已保存。脚本禁止启动worker/browser，仅用临时合成记录；岗位入队0、PDF写入0。退出码0表示缺陷被复现，**不表示产品行为通过**。这属于[36号](../single-job-application-flow-2026-10-16/issues/36-information-reuse-impact-updates.md)既有适用范围职责内的集成缺口，未证明是本轮新引入的回归。修复应复用现有`applicable_answers`，不再另造优先级规则。

### P2：旧追加用例与当前等待规范矛盾

[test_single_application_worker.py](../../tests/test_single_application_worker.py)第204–229行先将首岗设为`needs_input`、保留打开页面，未执行skip或确认完成就准备第二岗，最后要求`serial_application_id`指向第二岗。当前生产源码尚无该字段。

[APP-03/14](../../docs/single-job-flow.md)和[34号当前范围](../single-job-application-flow-2026-10-16/issues/34-email-to-review-pipeline.md)要求首岗等待时不做别岗；34的另一个验收项却仍要求此旧用例通过。当前prepare第1896–1897行实际以`batch_exists`拒绝；这**不是已发生越岗执行的证据**。

先校正验收契约：可以追加候选而保持首岗等待；另测明确完成或用户skip后的下一岗激活。不得通过取消旧批次、覆盖原页或隐式切岗消除红灯。原失败日志保留。本次未改生产代码、测试或票据。

### 交付缺口：当前源码、冻结收据和安装版属于不同版本

38关闭时完整默认结果为4126 passed、1 failed、2 skipped、367 deselected；其三份冻结边界源码中，当前browser与hosted_ats已被18号后继修改，ashby_drafts仍相同。旧绿色选取和38关闭范围不能作为当前所有字节的证明。

18号接续首轮完整结果为4025 passed、1 failed、2 skipped、424 deselected、125 errors；125项来自Swift夹具编译超时，不是已通过断言。后继[请求诊断记录](../single-job-application-flow-2026-10-16/ats-request-context-20261020.md)说明后续未复现Swift超时，但完整套件仍有旧追加失败；精确后继原始收据在其私有目录，本次未导出或将其数字补作当前全量通过。

本轮直接比较安装包`Contents/Resources/system/src`：75份文件相同，14份源码/JS不同；忽略未打包的`.DS_Store`。差异清单在[安装比较](assets/installed-source-comparison.json)。这说明新改动尚未全部进入安装版，不说明既有安装损坏。`codesign --verify --deep --strict`通过仅证明包签名完整性；未新测有效OS权限、运行worker加载版本、真实页面或真实ATS。

### 整理项：开发计划的状态摘要落后于票头

整理前计划仍有38 claimed/open、18旧owner以及35/36 open/none，并列出102已关/25未关的旧快照。本次按实时票头修正计划摘要和表格，保留原统计的历史标识；README和STATE已链接本审计。未领取、关闭或转派任何票。

### 交接风险：HEAD不能复现当前工作区

审计开始时Git短状态有49项tracked修改、470项untracked条目（目录可能合并显示，不等于文件数）。`git diff --stat`仅覆盖49份tracked文件；另有292份未跟踪的src/tests/scripts/macos文件，其中53份Python源码、191份Python测试。只发HEAD或tracked diff会遗漏实现。

本次保留所有脏工作，未暂存、提交、推送、清理或重装。后续交接应按既有owner切分准确文件与依赖，并绑定验证字节；不应为获得干净工作区批量删除或提交无关材料。

## 本轮直接验证

| 检查 | 实际结果 | 范围 |
| --- | --- | --- |
| checkout tracker | 127总票，24未关闭，依赖errors=0 | 快照见[tracker.json](assets/tracker.json) |
| 邮件capture/HTTP、信息库、Submit边界、登录继续、阶段观察、请求诊断及旧追加用例 | 126 passed、1 failed、36 deselected，3.00秒，exit 1 | [完整聚焦日志](assets/focused-tests.log)；唯一失败为上述旧追加契约 |
| 语言scope合成探针 | 复现不一致；无浏览器、无外部请求、无PDF | [探针输出](assets/language-scope-probe.log) |
| Ruff check | 通过 | [日志](assets/ruff-check.log)，排除历史.scratch、禁用cache |
| Ruff format --check | 393 files already formatted | [日志](assets/ruff-format.log) |
| git diff --check | 通过 | [空错误输出](assets/diff-check.log) |
| 主App签名完整性 | exit 0 | [空错误输出](assets/signature-check.log)，未修改App或权限 |

运行采用`uv run --locked --offline --no-sync`及checkout launcher，保持默认marker，未添加`-m`。
[355个观察文件的检查前指纹](assets/source-before.json)与检查后逐项一致；新写内容只有本审计记录与导航/计划文档。受影响测试组不与历史重叠组相加，也不以本次聚焦测试代替全量、安装或真实验收。

## 各层实际完成范围

| 层次 | 已有依据 | 仍未接受/完成 |
| --- | --- | --- |
| 源码工程 | 38独立出口；35先保存后标签归档切片；36作用域/配置复用切片；18控件、同页Next、登录后继续及诊断增量 | 35默认接入、36完整事实更新、18跨页/真实登录、28运行检查、39单主控、40完整材料共享、37结果消费与34集成 |
| 安装与原生合成 | 唯一主App及历史原生观察/POST/保活/正常重开等有界记录 | 最新源码尚未整体安装；正常重开不等于在途异常恢复；空附件不证明真实上传 |
| 真实材料与申请 | 历史一轮三封真实邮件、十个JD、八份分析及自动PDF；另有真实完整LaTeX草稿 | PDF质量与新路由编译、真实新页面填写上传、自然手动Submit后的结果记录与下一岗 |
| 研究 | Phase7/8首次cutoff与三层访谈实现、合成试验 | 现成pending successor的精确语义接受/封存；私人readiness与能力校准；职业图确认、三份真实JD及Phase14判断 |

依据：[原生记录](../remaining18-resumed-2026-10-20/README.md)、[真实后台终点](../automatic-mail-pipeline-2026-10-20/README.md)、[研究交付](../../docs/interview-delivery-2026-10-08.md)、[研究STATE](../../.planning/STATE.md)。这些旧记录只在各自版本和范围内有效，研究的25%不是产品完成率。

## 未关闭票逐项清单

依赖列只显示尚未关闭的直接前置；空前置不等于未领取、无需用户接受或已获真实操作许可。编号须连同地图使用，材料25与单岗25不同。

| 票据 | 状态 | Assignee | 尚未关闭的直接前置 | 下一步 |
| --- | --- | --- | --- | --- |
| [稳定性07](../../.scratch/application-worker-stability/issues/07-cold-start-prewindow-investigation.md) | open | root | 无未关闭前置 | 保留原owner；历史冷启动因果对照，独立于产品主线 |
| [稳定性10](../../.scratch/application-worker-stability/issues/10-cua-035-background-attach.md) | open | root | 无未关闭前置 | 保留原owner；后台附着与宿主生命周期对照 |
| [浏览器09](../../.scratch/browser-efficiency-2026-10-17/issues/09-browser-efficiency-acceptance.md) | open | none | 单岗11 | 真实主线后取得用户体验结论 |
| [材料16](../../.scratch/gmail-resume-preparation-2026-10-17/issues/16-release-closeout.md) | open | none | 材料25 | 真实材料验证后汇总版本、质量与剩余边界 |
| [材料25](../../.scratch/gmail-resume-preparation-2026-10-17/issues/25-installed-real-job-full-cv.md) | open | 01a15491/root | 单岗40 | 复用原草稿，补真实编译与材料质量，不重复生成 |
| [研究07](../../.scratch/phase-08-career-experience-inventory/issues/07-reconcile-ambiguous-excluded-and-unresolved-items.md) | claimed | 未记录 | 无未关闭前置 | 核实历史领取；审阅现成pending successor并取得精确语义接受 |
| [研究09](../../.scratch/phase-08-career-experience-inventory/issues/09-seal-the-user-accepted-inventory-revision.md) | open | 未记录 | 研究07 | 07接受及当前Phase7输入核对后才封存 |
| [单岗11](../../.scratch/single-job-application-flow-2026-10-16/issues/11-gmail-real-job.md) | open | 01a146b9/root | 材料25, 单岗30 | 组合与材料通过后，按真实路线许可验证；APP-12另需自然手动Submit证据 |
| [单岗12](../../.scratch/single-job-application-flow-2026-10-16/issues/12-delivery-closeout.md) | open | 01a146b9/root | 浏览器09, 材料16, 单岗11 | 真实主线、材料与体验结果齐备后核对交付 |
| [单岗18](../../.scratch/single-job-application-flow-2026-10-16/issues/18-generic-ats-controls.md) | claimed | 01a15ab3/root | 无未关闭前置 | 续现有控件/诊断；补跨页及真实登录协议证据 |
| [单岗20](../../.scratch/single-job-application-flow-2026-10-16/issues/20-workable-resume-upload.md) | open | 01a146b9/workable_upload | 单岗18 | 消费18；验证实际附件上传、可靠保存结果及字段回读 |
| [单岗23](../../.scratch/single-job-application-flow-2026-10-16/issues/23-current-job-email-correction.md) | open | 01a146b9/root | 单岗36 | 消费36；更正当前字段并保留人工编辑/历史 |
| [单岗26](../../.scratch/single-job-application-flow-2026-10-16/issues/26-native-chrome-startup-crash.md) | open | 01a155fd/root | 无未关闭前置 | 保留历史Chrome失败条件的因果对照，独立于主线 |
| [单岗27](../../.scratch/single-job-application-flow-2026-10-16/issues/27-native-interruption-recovery.md) | open | 01a150ef/bounded_protocol | 单岗39 | 消费39；同任务阶段恢复及未知结果核对 |
| [单岗28](../../.scratch/single-job-application-flow-2026-10-16/issues/28-installed-readiness-version-handover.md) | open | 01a150ef/bounded_protocol | 无未关闭前置 | 协调原owner收敛实际能力检查；保留owner、intent与原子性 |
| [单岗30](../../.scratch/single-job-application-flow-2026-10-16/issues/30-installed-minimal-regression.md) | claimed | 01a15926/root | 单岗41 | 41后做唯一主App的组合与安装验收 |
| [单岗33](../../.scratch/single-job-application-flow-2026-10-16/issues/33-ashby-public-bootstrap-review.md) | open | none | 单岗18 | 消费18；核验Ashby真实公开初始化及未知请求恢复 |
| [单岗34](../../.scratch/single-job-application-flow-2026-10-16/issues/34-email-to-review-pipeline.md) | claimed | 01a15926/root | 单岗18, 单岗20, 单岗23, 单岗27, 单岗28, 单岗35, 单岗36, 单岗37, 单岗39, 单岗40 | 先校正等待/追加测试契约；集成既有专业模块，不取消旧批次绕过保护 |
| [单岗35](../../.scratch/single-job-application-flow-2026-10-16/issues/35-mail-capture-label-archive.md) | claimed | 01a15ab3/root | 无未关闭前置 | 完成pipeline、原生标签配置/UI、重开和旧断点接入 |
| [单岗36](../../.scratch/single-job-application-flow-2026-10-16/issues/36-information-reuse-impact-updates.md) | claimed | 01a15ab3/root | 无未关闭前置 | 统一语言例外到筛选/prepare；补职业更正、细粒度影响及人工稿合并 |
| [单岗37](../../.scratch/single-job-application-flow-2026-10-16/issues/37-manual-submit-observation-continuation.md) | open | none | 单岗18, 单岗39 | 一次继续、原页Submit结果观察、可返回skip |
| [单岗39](../../.scratch/single-job-application-flow-2026-10-16/issues/39-single-orchestrator-derived-state.md) | open | none | 单岗28 | 28后统一选岗主控与worker状态派生 |
| [单岗40](../../.scratch/single-job-application-flow-2026-10-16/issues/40-shared-complete-materials.md) | open | none | 单岗36 | 36后共享完整生成、编译、自动检查 |
| [单岗41](../../.scratch/single-job-application-flow-2026-10-16/issues/41-consolidate-entrypoints-controls.md) | open | none | 单岗34 | 34主线可用后退役重复入口及控制 |

查询有20条metadata warnings：17项Assignee、2项Claim state、1项Blocked by未知，多数为历史已关闭票；研究07/09仍有实际owner/接受边界。未将未知补作none。脚本的`mechanical_frontier=[]`还受目录级`paused_route`等规则影响，`execution_authorized`固定为false；它们不是当前产品停工结论，也不代替真实路线许可。

## 下一步承接

1. 原owner继续18/35/36。36先补本次语言作用域缺口，并将更多后续工作接到共用事实选择；18真实协议仍按现有诊断获取证据。
2. 与28原owner协调运行检查精简，解锁39；36解锁40。随后37、34消费这些能力，34先按当前规范纠正追加/等待验收。
3. 34可用后做41入口收敛，再由30做唯一主App组合。保持原owner及旧任务、材料、页面、未决动作；历史Chrome根因独立推进。
4. 工程组合后才安排真实材料/主线验收；真实路线恢复需要其授权。自然手动Submit未发生时，明确APP-12仍未验，不为测试要求用户投递。
5. 研究独立核实07领取并审阅已存在的pending后继，不重新发现或生成；用户精确接受及当前Phase7输入核对后再做09封存。普通申请不等待研究mastery或整图接受。

本次范围：整理文档、读取现有证据、静态正确性审查、临时合成验证与签名完整性读取。没有运行真实App/浏览器、模型、邮箱或申请，也没有安装、改变TCC、修改个人资料或最终Submit。后续状态以票头实时查询为准。
