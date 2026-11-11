# 复用两库事实并按影响保存更正与更新

Type: feature
Label: wayfinder:task
Status: claimed
Priority: P2
Interaction: AFK
Assignee: 01a15ab3/root
Created: 2026-10-20
Updated: 2026-10-22
Parent: [申请主流程](../map.md)
Blocked by: [建立分析与简历共用的真实资料快照](03-source-bundle.md)
Triage: bounded-impact-followup

## 第9项材料/PDF独立核对 — 2026-10-22

用户要求仅核对此次被分析省略来源更正的材料/PDF实际输入。[有界核对](../../ticket36-material-pdf-inputs-2026-10-22/README.md)已完成3项：原样完整材料前后均486355字节且prompt摘要不同，identity和原文档均消费Ruby/Rust；两边在128000字节上限前停止，材料模型/编译/新材料与PDF产出均0。分析原结果仍复用，不能将其等价扩为材料等价。

缩小retained对照分层记录：地点打印在页眉时出现Identity核对项且候选源归档变化；未打印时零新模型、归档/编译配置相同。两者旧PDF及manifest原字节保持，旧draft配新inputs均在编译前拒绝。本轮没有观察实际Flow无关重编译，未改生产代码；下一最小边界为“未打印地点且归档相同”的实际Flow继续/导出是否出现重复，而非直接放宽绑定。材料15精确源/PDF接受记录继续复用，不重复确认，也不扩成新事实接受。

原样和缩小场景分开，探针构造失败日志保留、不当产品RED。只跑3项有界验证，旧矩阵/全套不重跑；旧4672通过仍属原冻结证据。主App未更新/启动，Status/Assignee/依赖/全部勾选不变，第9部分满足；未知结果、fill intent和真实申请暂停保持。

## 第9项省略来源切片后继 — 2026-10-22

用户已授权先验证实际输入再只修明确无关重算。[有界RED/GREEN、源码与最终结果](../../ticket36-omitted-source-2026-10-22/README.md)已完成：更正被省略合成来源后，前后实际prompt126033字节及SHA相同，但原实现清空分析。现仅在同岗位/配置、原证据完整且确切prompt及有效来源相同时，创建标明reused_from的不可变采用记录，零模型调用，旧分析/快照/模型attempt及有效事实确认保持。事实依据变化不继承旧确认。

受影响200项通过，独立竞态2项通过；冻结825输入完整默认4672通过、2项既有性能skip、572 deselected，原时限和默认marker保留。全套后仅强化一条合成fixture的legacy路径隔离，对应节点复验通过，生产字节不变。旧失败、红绿及所有输入分别保留，不重跑旧安装证明矩阵。

本切片只完成已验证的分析无关重算修复，材料/PDF继续按完整来源独立判断，不自动沿用。已有worker、未知导出/准备及历史缺prompt证据仍按原保护处理；不回填旧报告、不重问未变事实。源码未更新到主App，旧安装证据不代表新代码已安装。Status、Assignee和第9部分满足保持；更广材料/JD合并另判，真实申请继续暂停，未知结果和fill intent不改。

## 当前核对结论 — 2026-10-22

已复用30、34、27、37及同一主App安装/隔离证据，当前1—8、10、11满足，第9部分满足；继续claimed，原Assignee、依赖和bounded-impact-followup保持。[逐项证据与最小剩余切片](../../ticket36-evidence-reconciliation-2026-10-22/README.md)。原规划及早期“尚未完成”保留当时时点，不再重复确认已交付事实或实现。

联系/资格/配置影响分离、两库更正和不可变历史、German A1/岗位B2/JD B2全链、同JD受影响分组合并及原页安全换版已有证据。第9未完整证明更广职业资料/JD变化的结果级消费影响与无关结果/PDF复用；现行分析仍绑定整来源快照。最小后继先证明某一被省略来源更正前后实际分析prompt不变，再核对分析复用；材料可能另行消费该来源，须独立判断。此为待验证切片，本轮没有伪称新失败复现。

不把“未选入简历”当成无影响，也不因跨JD没有启用同JD确定性合并就声称人工底稿丢失。缺引用/未映射已消费上下文/组歧义继续停当前材料；不靠删除来源绑定或新增通用依赖图凑全绿。

本轮未改代码、运行测试/旧矩阵或App，未重问、改写两库私人事实。未知结果、fill intent、旧owner、材料和接受记录保持；34真实闭环仍未验，真实申请继续暂停，最终Submit人工。无需恢复真实申请才能继续第9项工程核对。

## Question

如何让申请直接复用两库适用事实、将明确更正写回正确的库，并只更新实际受影响的内容？

## 当前范围

依据[规范](../../../docs/single-job-flow.md)的 APP-04/05/07/15/17/18 和[统一计划](../../../docs/development-plan.md)。职业经历库存经历、学历、证据及责任归属；信息库存申请事实、联系方式、偏好和答案。系统先检索两库与历史任务，直接复用适用事实，补充后按正确作用范围入库。重要歧义或真实冲突才询问；动机、为什么加入公司和motivation letter等低影响内容可自主撰写，但不编造个人事实。不把未知标签、资料新版本或普通信息补充变成人工批准流程。

## 精简职责分工

本票只拥有事实、来源、适用范围与影响判断；[共享完整材料生成与自动检查](40-shared-complete-materials.md)消费其结果，负责生成/编译共享实现。本票不另写生成器或第三套资料库。所有直接职业补充及申请答案按已确认分工保存，不重复问设计。本次仅更新规划，未领取或执行。

## Acceptance criteria

- [x] 复用现有CareerCatalog、答案/profile存储和来源记录，明确两库字段职责；不引入第二套事实真相或重复信息库。
- [x] 问用户前检索适用来源、已存答案和当前岗位记录；同一事实回答一次后按国家/雇主/岗位等实际作用范围复用，不重复确认未变学历或联系方式。
- [x] 用户明确补充/更正职业事实时直接写职业经历库，保存来源和修改历史；申请答案和其他零碎可复用信息写信息库，不另要求批准入库。项目归属不清或重要歧义才问。
- [x] 单条来源不清只标记实际受影响内容，其他分析和资料仍可使用；未知不是否定，不臆造能力、责任、资格或提交状态，不使全库停止。
- [x] 遇到当前操作所需且重要的事实确实不明确时，立即停当前岗提示，答复按作用范围保存后继续；不汇聚未来步骤问题，不为收集一批问题继续其他岗位。用户可选择skip。普通可确定工作不增加组审核或逐版材料确认。
- [x] 更正能区分全局事实更新与岗位例外，23复用该职责；原答案、材料与已完成动作保留历史，人工页面编辑不被旧答案覆盖。
- [x] 岗位分析、资格筛选、prepare、浏览器动作前核对及字段解析使用同一适用事实选择和当前岗位上下文；已确认岗位例外优先于更宽范围，其他岗位仍用其适用事实。不可比较范围的不同值保持真实冲突，不按插入顺序选值，也不以全局语言门槛覆盖已采用的岗位例外。
- [x] 合成回归贯通岗位语言例外到筛选、prepare和动作前核对，覆盖全局German=A1、当前岗位例外=B2、JD要求B2的一致结果，以及其他岗位、不可比较范围冲突和重开复用；不得仅以分析lookup或字段resolve的单独通过证明整链一致。
- [ ] 资料/JD变化只重算实际受影响字段、分析或材料；模型配置变化不自动废弃已完成有效结果。人工调整后的材料作为更新基础，系统判断影响并合并，重要冲突才问；无关结果和原PDF继续复用，不因全局revision变化一律作废。
- [x] 职业图Skill/mastery和研究清单语义接受仍独立；普通事实入库不修改已封存研究结论，也不要求先封存完整职业图才能申请。
- [x] 合成用例覆盖相同事实复用、岗位例外、真实冲突、无关更新、相关材料变化、人工更正及重开；原子写失败不丢旧记录。

## Ownership and reuse

`application_information.py`、`career_portal_data.py`、`application_worker.py` 的答案库接口、`application_flow.py` 的更新失效路径及现有测试。与23协调具体邮箱字段，与34协调等待/继续；不重写整个职业图模型，不改真实私人记录。


## Publication boundary

仅发布待实施后继，Status=open、Assignee=none。没有读取或更改个人事实、接受材料、模型调用、邮箱修改或申请操作。

## Implementation started — 2026-10-20

用户已授权按当前spec开始系统精简。仅使用合成工作区实施与验证；保留既有材料、进度、人工修改和历史证据。最终Submit由用户操作。源码与测试恢复副本：`/private/tmp/tomorrowstar-simplification-20261020/before-source-tests-tickets.tgz`。

## Bounded implementation evidence — 2026-10-20

Status remains **claimed**. This is synthetic code verification, not private-data or live-application acceptance.

Implemented reuse of the existing answer store through one applicable-answer selector shared by information-library qualification lookup and `WorkerStore.resolve`. Explicit job exceptions override broader facts; strict scope refinements override generic facts. Incomparable applicable scopes with different values remain a conflict. Same-job exception reuse survives reopening, while another job still uses the global fact.

Completed analysis and material results retain the model configuration that originally produced them when no other input changed. Flow freshness, repeated creation, input update, user-facing explanation and single-job material binding share this rule. Adopted artifact input bindings and original PDF bytes remain unchanged. Relevant source/JD changes and nonconfiguration changes still use conservative invalidation; benchmark revisions are not ignored.

Verification from checkout, synthetic temporary workspaces only:

```text
UV_CACHE_DIR=/private/tmp/tomorrowstar-uv-cache uv run --locked --offline --no-sync python scripts/run_pytest.py -q tests/test_application_flow.py tests/test_application_information.py tests/test_application_worker.py tests/test_job_explanations.py tests/test_application_single_binding.py tests/test_job_explanations_http.py
212 passed in 15.27s
```

Ruff check and format check passed for the five touched source modules (`application_flow`, `application_information`, `application_worker`, `application_explanations`, `application_single_binding`) and their five directly touched test files. The default uv cache was not writable; the temporary cache above avoided that environment failure.

Remaining acceptance gaps: direct career-fact correction with source and history; complete source-level impact evidence and selective recalculation; merging relevant changes into manually edited materials; complete answer-correction history and atomic-failure acceptance. Completed PDF reuse after model-setting changes is covered, but pending resume generation after analysis-engine drift still has existing strict `current_flow_inputs` / `_task_current` checks. No career catalog/source documents, sealed research records, real applicant data, provider, mailbox, browser or Submit operation was changed. This slice does not close the ticket or establish overall APP-04/05/07/15 acceptance.

### Explicit regeneration follow-up — 2026-10-20

A synthetic follow-up found and fixed a configuration-retention edge case: an explicit retry of a completed resume now binds that new attempt to the current resume generator configuration. Passive reuse and ordinary input updates continue to preserve the original completed result. Original analysis configuration, prior artifact inputs and manual-source bases remain intact. The extended public regression first failed, then passed; it verifies the regenerated result uses the new resume configuration while the first two artifacts remain byte-equivalent as structured records. The same six-file focused test selection above passed again: **212 passed in 9.40s**. Ruff check and format check passed for the two files changed by this follow-up. Status remains claimed; the remaining acceptance gaps above still apply.

### HTTP contract alignment — 2026-10-20

Integrated verification found two HTTP tests still asserting automatic invalidation after a configuration-only change. Their assertions now follow APP-15 and verify completed analysis/PDF IDs, original inputs, adopted artifact records and PDF bytes are retained, with no new provider work. The independent benchmark-change branch still requires `flow_inputs_stale`. No production code changed in this follow-up. All four related HTTP parameter cases passed (**4 passed, 113 deselected in 2.62s**); Ruff check and format check passed for `tests/test_career_portal_http.py`.

### Retained-page review contract alignment — 2026-10-20

The retained-review parameter family reproduced one obsolete configuration-only rejection assertion; changed-source and stale-page parameters already passed. Updated only the configuration branch to permit explicit review using the already completed PDF and its original model binding. It verifies the returned task, retained flow bytes, PDF bytes and pending intent remain unchanged while the requested review handoff is recorded. Source and page failures still queue no review command. No production code changed. The entire `tests/test_flow_retained_review.py` passed: **37 passed in 16.61s**. Ruff check and format check passed for that file. Status remains claimed and overall ticket acceptance remains partial.

### Final delta audit — 2026-10-20

Independently compared current source/tests with the initial recovery archive and reconstructed the prior frozen patch before reviewing only later deltas. No source/test file was deleted; macOS archive resource metadata and Python bytecode are excluded from that statement. The late HTTP and retained-review changes are confined to APP-15 configuration reuse assertions and add explicit original input/artifact/PDF preservation checks. Independent source, benchmark and page checks remain. Late browser changes retain the actual blocked-request reason and inspect every repeated URL operation value; their separate receiver/default-offline evidence belongs to ticket38. No new production edit was made by this final audit. Acceptance boxes remain unchecked and Status remains claimed; earlier planning/publication-boundary text records the pre-implementation phase and is superseded for current status by the dated implementation entries above.

### 用户授权的验收修订 — 2026-10-21

[当前工作审计](../../work-audit-2026-10-20/README.md)确认本票职责内的语言作用域集成缺口：全局German=A1、岗位例外=B2且JD要求B2时，分析返回supported、字段解析返回B2，公开prepare却报job_requirement_mismatch。证据见[纯合成探针](../../work-audit-2026-10-20/assets/language-scope-probe.py)及[原输出](../../work-audit-2026-10-20/assets/language-scope-probe.log)。探针退出码0表示复现缺陷，不表示功能通过；未证明该缺口由首批改动新引入。

用户已授权把此项写入现有验收。修复应复用现有applicable_answers，覆盖pipeline筛选、WorkerStore语言门槛及浏览器核对，不另造作用域规则。本次仅修订待完成要求，未改代码或测试，未勾选验收；票头Status、Assignee、Blocked by及全部历史结果保留。

### 岗位语言作用域修复的有界进展 — 2026-10-21

用户授权继续推进后的源码切片已统一分析、资格筛选、prepare、浏览器动作前核对和字段解析的适用事实及当前岗位/公司/国家上下文。复用applicable_answers；岗位例外覆盖更宽事实，不可比较范围冲突保持needs_input，不回退全局门槛。补充后一次Continue重检原岗；新邮件收录不破坏原岗保留来源绑定。合成覆盖全局A1/岗位B2/JD B2、其他岗隔离、降低例外、冲突、明确国家和动作前新增冲突。

当前受影响582项回归通过，完整默认离线仍运行中；准确输入、先红后绿、静态复核、历史中止与剩余边界见[工程进展](../../ticket-progress-2026-10-21/implementation.md)。本条不证明全部事实更正/历史、选择性重算或人工材料合并完成，不勾选整体验收。原票头、负责人、依赖、历史勾选和失败保留，真实申请继续暂停。

### 后继完整运行结果 — 2026-10-21

语言/收录受影响582项通过；后继通知测试替身已补齐。V3完整默认4171 passed、2 skipped、425 deselected、21 errors；21项均在原生Web桥共享Swift夹具60秒编译超时处停止，未进入断言。相同原时限专项仍超时；源码类型检查及缓存复用编译只作阶段诊断，不代替全套通过。事实更正/影响重算等原未完项保持。

完整输入、原始结果、独立核验及诊断见[工程记录](../../ticket-progress-2026-10-21/implementation.md)。本条只追加结果，原负责人、状态、依赖、历史勾选和证据不变；真实申请继续暂停。

### 三项 P2 后继修复及完整默认离线验证 — 2026-10-21

已修复语言等待中的原始start请求重放：旧请求保持原等待与checkpoint，答案补齐后也须新的Continue意图；该Continue本身仍幂等。已明确暂缓或独立排除的岗位不再先要求消解语言冲突；其余合法岗位仍在实际语言冲突时等待。完整事实更正来源/历史、细粒度重算和人工材料合并仍为未完范围。

新增12个回归节点，逐项保留RED/GREEN；受影响14模块557 passed，完整默认离线4204 passed、2 skipped、425 deselected，755.36s、exit0。原生Web桥21项本轮均通过；原夹具、60秒时限及缓存策略未改，旧4171/21-error结果与诊断不改写。747份登记输入前后相同；独立只读代码复核未发现新增问题，不冒称其独立重跑测试。

差异、原始日志、输入核对和剩余范围见[本轮工程记录](../../p2-regression-fixes-2026-10-21/README.md)。本条只追加证据，不勾选或关闭整票，不改变Status、Assignee、Blocked by、历史勾选或其他证据；App暂不更新，真实申请继续暂停。


## Notes — 持续主线源码后继 2026-10-21

原三项 P2 的语言 / 排除 / 请求幂等回归在本后继受影响组合继续通过；采用的分析和材料在保存准备结果前验证，避免 queued 后被子 Worker 拒绝。本条不完成完整事实更正历史、影响范围重算或人工材料合并。

完整默认离线：4263 passed, 2 skipped, 428 deselected in 661.45s (0:11:01)；[工程记录与原日志](../../automatic-mainline-2026-10-21/README.md)。旧三项 P2 的独立冻结记录及全部失败历史保留。Status、Assignee、依赖、既有勾选均不变，不新增票、不关闭本票；App 未更新，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 当前岗继续与事实材料后继 2026-10-21

职业文档更正与信息库答复/更正/撤回保存原字节及不可变历史；HTTP更正复用原位文档，research/sealed/schema对象不可改。完整材料只绑定适用联系方式，普通无关表单答案不使PDF失效；当前confirmed联系方式可替换历史页首旧值，职业/教育例外不放宽。细粒度职业影响重算和上传后材料合并未完成。

完整默认离线：4349 passed, 2 skipped, 432 deselected in 676.79s (0:11:16)；[本轮工程、复核与原日志](../../linear-continuation-2026-10-21/README.md)。初轮完整运行因发现缺陷主动中止，旧失败/修复/绿色结果分别保留。Status、Assignee、依赖与原勾选不变，不新增票、不关闭本票。App未更新，真实申请继续暂停，最终Submit始终人工。


## Notes — 必要材料、路由与恢复后继 2026-10-21

联系资料变化保留不受影响的分析与完整人工 LaTeX 底稿；资格答案在实际 Single 写入门实时核验，不再无故使未消费该答案的分析/PDF 失效。无 basis 的旧资格回执遇同范围撤回记录须重新核验，历史原件保留。只读 qualification_revision 兼容字段保留；已有 Worker 的实质 PDF 更换仍严格停写。

完整默认离线：4440 passed, 2 skipped, 460 deselected in 718.67s (0:11:58)；受影响离线 1097 项、本地浏览器 164 项均通过。[工程记录、失败历史及冻结输入](../../product-completion-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 原页材料安全更新后继 2026-10-21

联系方式更正只更新受影响页眉与字段，完整人工正文不重写；当前人工源直接导出，不再重新包根分组。后继独立版本仅规范化引擎 marker comments，旧源字节保留，固定教育实值与来源约束继续验证。一次 Continue 沿原 Worker/Page 更新材料。

完整默认离线：4450 passed, 2 skipped, 497 deselected in 727.15s (0:12:07)；受影响离线 1358 项、本地浏览器 217 项均通过。[工程记录、失败历史及冻结输入](../../bound-material-update-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 精准等待前必要材料与人工附稿修复 2026-10-21

本次确切字段的人工附稿优先于旧可复用答案，原网页人工值仍先保留。人工正文是同任务材料版本，actor=user、human_reviewed=false，保留父稿历史，不写入已确认事实或答案库。

完整默认离线：4462 passed, 2 skipped, 532 deselected in 968.76s (0:16:08)；受影响离线 1370 项、本地浏览器 252 项均通过。[工程记录、失败历史及冻结输入](../../precision-material-preparation-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 浏览器、材料与默认入口后继 2026-10-21

同JD职业事实变化可核验原完整人工底稿及原分析来源快照，只更新可确定的受影响分组，其他人工措辞逐字保留。已消费但未映射上下文、引用丢失和分组歧义停止；职业分析输入变化仍重新分析，不声称全面细粒度影响已完成。

完整默认离线：4487 passed、2 skipped；本地合成浏览器：372 passed。受影响集合已包含在最终完整默认/浏览器运行，重叠结果不累加。[工程、原日志与最终冻结输入](../../browser-material-entry-engineering-2026-10-21/README.md)。早期统一失败、独立审查和修复均原样保留。Status、Assignee、依赖和既有验收勾选不变，不新增或关闭票。App未更新或启动，真实申请继续暂停，最终Submit始终人工。


## Notes — 可用优先重排 2026-10-21

已有作用域与更正、原页材料更新不重做；更广事实影响以具体已消费文档切片，不挡现有主线。

Priority/Triage/票头依赖按本次重排更新；旧边与原字节见[审计及变更账本](../../usable-first-wayfinder-audit-2026-10-21/README.md)。原 Status、Assignee、Interaction、既有验收勾选及全部旧正文保持，不领取、不关闭、不替用户接受。源码接口依赖不等于安装或真实操作许可；App 未更新，真实申请继续暂停。


## Notes — TeX实际内容与人工修改的资料/JD更新 2026-10-22

以最新已采用的完整TeX为资料/JD更新基础，复用原分组与实际人工措辞。资料更正与JD影响按并集合并，仅采用受影响组；未打印资料字段变化可复用正文，联系方式更正直接修改页首，无关组字节保留。JD新增/删除要求、公司/职位/地点变化、连续更新和更新后再次人工编辑导出均有公开链路回归。重要事实冲突在导出前停止，当前岗修正后一次Continue更新输入并按需重新分析；重复请求不重放。

本票第9项仍为部分完成：含待核对组且之后又有人工修改的候选保留当前TeX并等待，尚未自动合并；旧稿缺少可核验原JD正文、来源缺失或无法映射等边界保留原稿，不回退覆盖人工修改。内容审核以TeX事实、措辞、学历和人工修改为准；成功编译即默认PDF可用，无新增PDF检查或确认。

受影响回归、完整默认离线结果、先红后绿及独立复核见[本轮工程记录](../../ticket36-tex-impact-2026-10-22/README.md)。只追加本条证据，票头Status、Assignee、依赖和既有勾选保持；已有接受记录及全部旧修改保留。App未更新或启动，真实申请继续暂停。


## Notes — 待核对稿后续人工修改自动合并 2026-10-22

本轮授权切片补齐待核对稿保存人工修改后的自动合并。最新实际TeX及人工修改始终作为底稿，只将最新未决候选补入非导出模型输入，按未决、资料变化、JD影响的并集重评。无关正文逐字保留，人工删除/省略不复活，新增/重排保持；来源不清或责任冲突仍在原岗等待，不伪造确认。新结果保存可核验的不可变父稿依据，实际base与旧归档保持，不另建批准或PDF采用对象。

恢复后可再次编辑和继续JD更新；联系方式页首和固定学历消费使用同一可核验合并依据，旧接受字段与原件不改。公开回归、先红后绿、独立探针、完整默认离线及冻结输入见[本轮工程记录](../../ticket36-unresolved-manual-merge-2026-10-22/README.md)。较广来源缺失/无法映射等第9项边界仍按实际不确定性停止并保留原稿，不据本切片勾选整项或关闭本票。

只追加本条证据；Status=claimed、Assignee=01a15ab3/root、依赖、原验收勾选和已有接受记录保持。现有工作未删除或回退；App未更新或启动，真实申请继续暂停。

本轮最终后继同时修复多轮历史核验的重复递归：单次读取内复用已成功核验的相同不可变记录，读取结束清空；下一次读取及历史篡改仍重新核验。四轮探针由21/70/217/658次读取降为18/35/50/65，不引入持久缓存、PDF版本采用或新批准对象。

统一验证初轮发现新增临时验证作用域与已加载身份常量扫描不兼容，主动中止并保留11失败/exit130及854项一致输入。已复用既有精确runtime-state排除规则，仅排除临时作用域；119项相关回归及独立身份探针通过，实际代码/策略变化仍改变身份，未知对象仍fail closed。最终完整默认v2及新冻结输入见本轮工程记录；原票头与历史不改。


## 人工省略后的来源更新与影响映射 — 2026-10-22

本轮按用户指令补齐已复现切片，Status=claimed、Assignee=01a15ab3/root、依赖和原接受项保持。完整记录与验证读回见[本轮报告](../../ticket36-omitted-source-map-2026-10-22/README.md)。

人工省略组在后继稿不再输出时保留最小来源ID/名称关联，只参与来源变化覆盖判断，不恢复省略正文、不加入模型分组。映射从已核验的实际不可变父稿派生；当前人工改绑/重新纳入优先于旧关联，多轮更新及旧v1谱系均可延续。共享来源仍触发被采用组更新；其余人工措辞、删除与顺序保持。映射缺失、伪造或父稿损坏拒绝；新增加的未映射上下文和采用来源缺失仍保留原稿停止，不用省略覆盖掩盖真实影响。

新增回归覆盖连续来源更新、JD刷新后再次更新、省略来源删除、共享来源、人工改绑、重新纳入、旧谱系和篡改拒绝；公开Flow贯通资料刷新和导出。准确结果以本轮报告及冻结日志为准，不将本切片扩大为第9项全部满足或整票关闭。以TeX实际内容为准，编译成功即默认PDF可用。保留现有改动、历史接受、未知结果及原fill intent；未更新/启动App，真实申请继续暂停。


## 新增未映射上下文的影响判断与合并 — 2026-10-22

按用户指令继续本轮切片，Status=claimed、Assignee=01a15ab3/root及原依赖、勾选和历史保持。[本轮报告](../../ticket36-new-context-2026-10-22/README.md)保存复现、回归、输入冻结及最终读回，不据本切片关闭整票。

新文档、未采用结构化来源及档案附加上下文变化交给现有材料模型，与实际人工TeX核对，要求明确受影响组和判断理由。无关可保持全文，有关只合并现有来源、待核对与JD影响并集；旧分组边界必须保持，其他人工措辞和省略逐字保留。新增引用限本轮未知上下文对应的当前合格来源，含正文不变但文档新增关联上下文的既有来源；不得借机移除原引用、重绑无关未变来源或恢复已知省略来源。原始文档/链接不升级成能力证据，判断理由不算事实确认。

重要冲突继续待核对；已采用来源缺失、来源/TeX谱系损坏、未知外部修改和生成期间输入变化仍停并保留原稿。本轮仅在现有可定位组内合并，需新增独立经历/学历组等范围不通过任意模型重分组写入。新增回归覆盖无关/相关上下文、合法引用、非法响应、档案附加链接与来源切换、影响并集、历史保留及公开Flow刷新/导出，准确结果见报告。不更新/启动App，真实申请继续暂停，最终Submit人工；以TeX为准，编译成功即默认PDF可用。


<a id="current-scope-realigned"></a>
## 当前管理纠偏：两库与本次申请分开 — 2026-10-22

此节是用户澄清后的当前工作安排；上方早期切片、失败和结论保留原时点。Status=claimed、Assignee=01a15ab3/root、原依赖及勾选不变。[当前统一计划](../../../docs/development-plan.md#ticket36-current-scope)和[本轮审计清单](../../ticket36-realign-2026-10-22/audit.json)为当前导航。

用户维护的是职业经历库/信息库；本次申请生成简历后可人工修订。本次修订留在本次材料，继续或相关更新以该稿为基础，不能静默回写成两库全局事实。明确的库事实补充/更正仍走正确库的显式路径与历史；适用的跨岗材料复用保持原规则，不将材料本身升格为全局事实。

| 工作 | 处理 |
| --- | --- |
| 两库复用/更正、作用域与历史 | 正确，保留；代码入口与本次TeX保存分开。 |
| 实际TeX、人工措辞/省略、局部影响合并、事实及学历保护 | 正确，保留；本轮未发现须回滚近期合并代码的确证。 |
| “用户要更新JD” | 纠正表述；JD由系统读取，仅保留变化兼容，不增加用户维护任务。 |
| “还缺新增整段内容” | 撤回为收尾结论；既有回归可追加段落，独立公开入口也能新增小节并保留其他人工文字。缺少的是内部新分组协议，原票没有独立该要求，不再列本票阻塞目标。 |
| 把36持续扩展为生成器/分组协议/PDF优化工作 | 停止扩张；本票负责事实、来源、适用范围、影响判断，40消费共享生成/编译。现有兼容实现保留，不改原票负责人。 |
| 每轮技术切片与全量数字代替主线收尾 | 修正管理；剩余项必须对应原接受条件和用户场景，复用旧证据，先复现才修。 |

仅保留两个待核对场景，均未复现为产品bug：

1. 本次修订隔离与继续：A生成/人工修订→两库事实字节不变→B从两库独立生成时不把A本次修订作为全局事实→A继续保持其稿。保持单岗顺序和显式材料复用规则。
2. 用户在职业库明确更正学历后，本次TeX能否只更新相关学历且不重复确认；未变学历和真实冲突保护保留。当前仅静态风险，不能据此放宽事实验证或任意回写。

下一步只为这两项补最小公开入口证据；失败则修对应路径，通过则按原11项归并收尾，不追加内部协议目标。当前编辑器对前导、学历及联系人事实更改有额外限制，本次没有宣布任意TeX/事实修订均已支持；若限制实际阻塞上述用户流程，再以具体复现判断。

本轮只整理管理/规范/导航并做只读审计；生产和测试字节未改。独立公开入口新增小节探针1项通过（0.69秒），首跑因测试比较内部marker包装失配，非产品失败，日志均保留。上一轮4788通过/2跳过结果仅复用，不伪称本轮新跑。App未更新或启动，真实申请继续暂停；历史接受、未知结果和fill intent保持。


<a id="two-mainlines-results"></a>
## 指定两条主线核对与必要修复 — 2026-10-22

按用户确认后的范围只执行S1/S2，不新增本票目标。原Status=claimed、Assignee=01a15ab3/root、依赖、接受项和旧正文保持。[本轮记录](../../ticket36-two-mainlines-2026-10-22/README.md)保存具体复现、回归、冻结及读回。

S1通过，无生产修复：本次人工措辞/省略不改变两库；B公开Store从两库与原底稿独立准备，不升格A局部修订或专属邮箱为全局事实；A继续导出保留其实际TeX。没有启动第二活动Flow，也不禁止适用材料的显式复用。新增1条公开入口回归。

S2确有问题并已修复：库内明确学历更正原先仍落待确认；已有接受来源还会用旧整稿绑定误拦先人工修改后的首次更正或后续更正。仅按已有已应用用户更正链、不可变父稿/来源及当前学历纪录作唯一确定替换。历史receipt/manifest/captures、旧稿、旧导出保持；未变学历和其他人工内容不改。新增14个回归节点覆盖常规字段与在读/预计状态、再编辑导出、未知/损坏更正记录、模型乱改、同组两学历只改一项、先人工修改/连续更正和冻结证据损坏。无法唯一定位的特殊TeX保留原稿核对，不扩展为新格式/分组协议目标。

本轮两条主线结果已归并到统一计划，不再自动开启第三项。准确受影响/完整默认及静态结果见本轮记录，不累加重叠集合为新通过数。旧失败与夹具修正分别保留。App未更新或启动，真实申请继续暂停；未知结果、fill intent、既有改动和历史接受记录保持。

## 2026-10-26 本轮 Module 后继导航

本票保持两库更正和材料影响更新原范围；Resume 生命周期职责迁移由 [MC-03](../../module-completion-2026-10-26/issues/03-resume-lifecycle-interface.md) 承接，合法映射导入的 Prism 后继缺陷由 [MC-02](../../module-completion-2026-10-26/issues/02-mapped-import-prism-successor.md) 修复。当前新票不把整体 Module 重构追加成本票收尾条件。

本次仅追加范围导航，原 Status、Assignee、Blocked by、勾选及历史结论不变；未领取、实施或关闭本票。
