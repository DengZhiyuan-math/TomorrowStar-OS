# 开放票并行执行分组 — 2026-10-20

> 当前规范与唯一执行计划（2026-10-20）：[产品规范](../../docs/single-job-flow.md) · [开发计划](../../docs/development-plan.md) · [系统审计](../../docs/system-audit-2026-10-20.md)。
> 本页转为历史分组记录，保留原实施分工和收据。当前计划只有docs/development-plan.md；产品严格线性一次一岗，先跑通再研究并发。下方“如何开始”、A-H组、118/18统计和原矩阵依赖均不再是当前指令；既有领取保持，依赖以票头替代范围和实时查询为准。 本次仅重规划，未改Status/Assignee、未执行真实申请。

初次重组覆盖19张未关闭票；随后本轮并发实现完成持久证据保全票。当前118张中100张closed/resolved，18张未关闭（16 open／2 claimed）。A组保留为本轮已完成上下文，其余开放票仍各归一组。这是执行导航；各票仍是状态、领取、依赖与验收的唯一事实源。已关闭数包含行政替代和规划结案，不是功能完成率。

## 如何开始

- **A组已按合成范围完成，当前无未领取且前置全满足的票。** 见[本轮并发实施记录](../parallel-implementation-2026-10-20/README.md)。B–E现有领取仍保留，人工与权限门槛不因回归通过解除。
- **原执行者可并行继续：B、C的原页观察、D、E的无权限依赖工程。** 它们技术前置已满足，但已有领取。先确认原会话及当前执行范围；缺少权限、原失败环境或原始证据时保持阻塞／unknown。
- **F和G是独立人审线。** 可与工程并行安排审核，但同一用户和安装界面逐项串行；不自动启动模型、编译或接受材料／清单。
- **H是下游集成与接受。** 可以准备清单和阅读已有代码，不把未满足的前置改成可领取；不重做已完成实现。

## 并行分组总表

| 分组 | 当前可推进范围 | 顺序及产物边界 |
| --- | --- | --- |
| [A — 持久证据保全](#a-evidence) | 已完成合成保全及持久重开；真实App与历史基线不追认。 | 先复用冻结清单和复制工具，验证保全→复制后字节／权限核验→清理工作副本→持久入口重开。供其他组复用；不新增硬依赖。 |
| [B — 启动与历史故障归因](#b-startup) | 技术前置已满足，但已有领取。原执行者可分别继续有界调查；root历史领取须先定位，不能由新会话夺取。 | 两票保留不同机制：SIGABRT原条件因果／同条件GREEN，与窗口前置拒绝及Dock上游来源。共用原始证据索引，不合并根因或相互替代验收。 |
| [C — 原页观察与请求诊断](#c-observation) | 原页观察前置已满足且已有领取；请求诊断等待原页观察结案。 | 组内按原页观察→请求／intent诊断推进。可提前只读整理已有失败和合成反例设计；不得提前执行依赖原页观察结果的修复／验收，也不恢复真实原页。 |
| [D — 原生退出与阶段恢复](#d-recovery) | 技术前置已满足且已有领取；原执行者继续隔离工程，原生实验另遵循既有许可。 | 核对退出因果、真实PDF子进程的完成／中断竞争、同任务版本和历史保留。与身份交接分开实现，交叉合成场景最后统一验收。 |
| [E — 宿主身份、权限与后台附着](#e-identity) | 两票技术前置已满足且已有领取；获权正例受当前实际宿主证明限制，历史root领取须核实。 | 身份／nonce／配置／跨版本兼容矩阵与完整后台附着分别保留结论。可并行分析、准备负例；真实GUI宿主／Cua附着和权限正例串行核验，不借其他宿主授权。 |
| [F — 新岗位材料与准备版接受](#f-materials) | 现有草稿等待用户逐组审核，已有执行者；整体接受等待本组前票。不是重新生成任务。 | 复用已绑定草稿及未变事实→用户逐组审核→适用授权下真实编译→新PDF接受→普通批次停点／冷重开→准备版整体接受。不能代答HITL或自动重生成。 |
| [G — 职业清单后继接受与封存](#g-inventory) | 历史领取未核实，不能领取；现成后继技术绑定已完成，当前等待准确语义接受。 | 先核实历史领取，再接受现成准确后继，核对当前Phase 7绑定后按原契约封存。无需重建proposal，不改首次接受版本，不推断Skill能力。 |
| [H — 组合回归、真实验收与交付](#h-integration) | 当前全部有未关闭前置；不作为可立即实施的独立前沿。真实路线继续暂停。 | 组合回归等待观察／诊断、启动、恢复和身份票。通过后控件与邮箱更正可分支验收；上传等待控件。真实单岗验收完成后，浏览器体验接受与交付核对可分支推进，但各自保留人工／全子票完成门槛。 |

## 共享文件与运行资源

| 资源 | 协调规则 |
| --- | --- |
| `macos/App.swift`、`macos/server.py`及共享portal UI／请求门禁 | B/C/D/E跨组修改前声明具体文件或函数所有权；同文件改动由一个集成执行者顺序合入。独立测试、诊断脚本和只读证据核对可并行。 |
| 浏览器owner、Cua transport、worker与Page绑定 | C/E及后续控件、上传可能共享模块。不得起第二owner或接管旧profile；同一运行的观察、命令和清理串行。 |
| 主安装App、签名、配置、权限证明、Chrome／Space实验 | B/C/D/E/F/H共用本机；每次只运行一个改变这些条件的原生实验，其他组做离线工作。冻结版本、时间窗和资源归属后再运行。安装替换及系统权限变更仍按已有许可。 |
| 持久证据与合成工作目录 | A使用独立测试输出，不移动或修正其他组旧证据。其他组各自保留命令、结果及字节；先采用适用保全规则，再清理本次资源。A不是其他票的新阻塞。 |
| 用户审核与真实外部系统 | F/G及H人工接受逐项进行；真实申请、填写、上传和Submit继续暂停，不从并行分组推定恢复。 |

## 各票归属、当前阻塞与接续

下表保留本轮19张票，其中A组已完成，其余18张开放；每票仅归入一组。只列未关闭的直接前置；“无未关闭前置”不表示无权限、所有权或人工门槛。

<a id="a-evidence"></a>
### A — 持久证据保全

已完成合成保全及持久重开；真实App与历史基线不追认。

先复用冻结清单和复制工具，验证保全→复制后字节／权限核验→清理工作副本→持久入口重开。供其他组复用；不新增硬依赖。

| 规范票据 | 状态／原领取 | 未关闭直接前置 |
| --- | --- | --- |
| [持久化验收与回退证据](../single-job-application-flow-2026-10-16/issues/32-durable-acceptance-and-rollback-evidence.md) | closed / 01a1586d/root/evidence | 无未关闭前置 |

<a id="b-startup"></a>
### B — 启动与历史故障归因

技术前置已满足，但已有领取。原执行者可分别继续有界调查；root历史领取须先定位，不能由新会话夺取。

两票保留不同机制：SIGABRT原条件因果／同条件GREEN，与窗口前置拒绝及Dock上游来源。共用原始证据索引，不合并根因或相互替代验收。

| 规范票据 | 状态／原领取 | 未关闭直接前置 |
| --- | --- | --- |
| [复现并修复 Chrome 原生启动崩溃](../single-job-application-flow-2026-10-16/issues/26-native-chrome-startup-crash.md) | open / 01a155fd/root | 无未关闭前置 |
| [调查 Cua 冷启动前置窗口阻断](../application-worker-stability/issues/07-cold-start-prewindow-investigation.md) | open / root | 无未关闭前置 |

<a id="c-observation"></a>
### C — 原页观察与请求诊断

原页观察前置已满足且已有领取；请求诊断等待原页观察结案。

组内按原页观察→请求／intent诊断推进。可提前只读整理已有失败和合成反例设计；不得提前执行依赖原页观察结果的修复／验收，也不恢复真实原页。

| 规范票据 | 状态／原领取 | 未关闭直接前置 |
| --- | --- | --- |
| [在 App 中可靠观察所属原申请页](../single-job-application-flow-2026-10-16/issues/24-owned-page-observation.md) | claimed / 01a150ef/root | 无未关闭前置 |
| [定位未批准请求并恢复受控字段核验](../single-job-application-flow-2026-10-16/issues/25-request-diagnostics-readback.md) | open / none | [在 App 中可靠观察所属原申请页](../single-job-application-flow-2026-10-16/issues/24-owned-page-observation.md) |

<a id="d-recovery"></a>
### D — 原生退出与阶段恢复

技术前置已满足且已有领取；原执行者继续隔离工程，原生实验另遵循既有许可。

核对退出因果、真实PDF子进程的完成／中断竞争、同任务版本和历史保留。与身份交接分开实现，交叉合成场景最后统一验收。

| 规范票据 | 状态／原领取 | 未关闭直接前置 |
| --- | --- | --- |
| [诊断原生会话中断并验证阶段恢复](../single-job-application-flow-2026-10-16/issues/27-native-interruption-recovery.md) | open / 01a150ef/bounded_protocol | 无未关闭前置 |

<a id="e-identity"></a>
### E — 宿主身份、权限与后台附着

两票技术前置已满足且已有领取；获权正例受当前实际宿主证明限制，历史root领取须核实。

身份／nonce／配置／跨版本兼容矩阵与完整后台附着分别保留结论。可并行分析、准备负例；真实GUI宿主／Cua附着和权限正例串行核验，不借其他宿主授权。

| 规范票据 | 状态／原领取 | 未关闭直接前置 |
| --- | --- | --- |
| [核验当前安装身份与在途版本交接](../single-job-application-flow-2026-10-16/issues/28-installed-readiness-version-handover.md) | open / 01a150ef/bounded_protocol | 无未关闭前置 |
| [调查 CuaDriver 0.35 后台浏览器附着拒绝](../application-worker-stability/issues/10-cua-035-background-attach.md) | open / root | 无未关闭前置 |

<a id="f-materials"></a>
### F — 新岗位材料与准备版接受

现有草稿等待用户逐组审核，已有执行者；整体接受等待本组前票。不是重新生成任务。

复用已绑定草稿及未变事实→用户逐组审核→适用授权下真实编译→新PDF接受→普通批次停点／冷重开→准备版整体接受。不能代答HITL或自动重生成。

| 规范票据 | 状态／原领取 | 未关闭直接前置 |
| --- | --- | --- |
| [在安装版验收真实新岗位完整简历生成](../gmail-resume-preparation-2026-10-17/issues/25-installed-real-job-full-cv.md) | open / 01a15491/root | 无未关闭前置 |
| [接受准备版并记录剩余边界](../gmail-resume-preparation-2026-10-17/issues/16-release-closeout.md) | open / none | [在安装版验收真实新岗位完整简历生成](../gmail-resume-preparation-2026-10-17/issues/25-installed-real-job-full-cv.md) |

<a id="g-inventory"></a>
### G — 职业清单后继接受与封存

历史领取未核实，不能领取；现成后继技术绑定已完成，当前等待准确语义接受。

先核实历史领取，再接受现成准确后继，核对当前Phase 7绑定后按原契约封存。无需重建proposal，不改首次接受版本，不推断Skill能力。

| 规范票据 | 状态／原领取 | 未关闭直接前置 |
| --- | --- | --- |
| [Reconcile Ambiguous, Excluded, and Unresolved Career Items](../phase-08-career-experience-inventory/issues/07-reconcile-ambiguous-excluded-and-unresolved-items.md) | claimed / 未知（保留Claim state） | 无未关闭前置 |
| [Seal the User-Accepted Inventory Revision](../phase-08-career-experience-inventory/issues/09-seal-the-user-accepted-inventory-revision.md) | open / 未知（保留Claim state） | [Reconcile Ambiguous, Excluded, and Unresolved Career Items](../phase-08-career-experience-inventory/issues/07-reconcile-ambiguous-excluded-and-unresolved-items.md) |

<a id="h-integration"></a>
### H — 组合回归、真实验收与交付

当前全部有未关闭前置；不作为可立即实施的独立前沿。真实路线继续暂停。

组合回归等待观察／诊断、启动、恢复和身份票。通过后控件与邮箱更正可分支验收；上传等待控件。真实单岗验收完成后，浏览器体验接受与交付核对可分支推进，但各自保留人工／全子票完成门槛。

| 规范票据 | 状态／原领取 | 未关闭直接前置 |
| --- | --- | --- |
| [扩充安装版最小合成验收覆盖本轮故障](../single-job-application-flow-2026-10-16/issues/30-installed-minimal-regression.md) | open / none | [在 App 中可靠观察所属原申请页](../single-job-application-flow-2026-10-16/issues/24-owned-page-observation.md)；[定位未批准请求并恢复受控字段核验](../single-job-application-flow-2026-10-16/issues/25-request-diagnostics-readback.md)；[复现并修复 Chrome 原生启动崩溃](../single-job-application-flow-2026-10-16/issues/26-native-chrome-startup-crash.md)；[诊断原生会话中断并验证阶段恢复](../single-job-application-flow-2026-10-16/issues/27-native-interruption-recovery.md)；[核验当前安装身份与在途版本交接](../single-job-application-flow-2026-10-16/issues/28-installed-readiness-version-handover.md) |
| [支持已观察到的通用 ATS 自定义必填控件](../single-job-application-flow-2026-10-16/issues/18-generic-ats-controls.md) | open / 01a146b9/ats_controls | [扩充安装版最小合成验收覆盖本轮故障](../single-job-application-flow-2026-10-16/issues/30-installed-minimal-regression.md) |
| [支持当前岗位已确认邮箱的更正](../single-job-application-flow-2026-10-16/issues/23-current-job-email-correction.md) | open / 01a146b9/root | [扩充安装版最小合成验收覆盖本轮故障](../single-job-application-flow-2026-10-16/issues/30-installed-minimal-regression.md) |
| [支持 Workable 普通简历字段的受控上传与回读](../single-job-application-flow-2026-10-16/issues/20-workable-resume-upload.md) | open / 01a146b9/workable_upload | [支持已观察到的通用 ATS 自定义必填控件](../single-job-application-flow-2026-10-16/issues/18-generic-ats-controls.md)；[扩充安装版最小合成验收覆盖本轮故障](../single-job-application-flow-2026-10-16/issues/30-installed-minimal-regression.md) |
| [通过 App 用 Gmail 真实岗位验证至人工提交前](../single-job-application-flow-2026-10-16/issues/11-gmail-real-job.md) | open / 01a146b9/root | [支持已观察到的通用 ATS 自定义必填控件](../single-job-application-flow-2026-10-16/issues/18-generic-ats-controls.md)；[支持 Workable 普通简历字段的受控上传与回读](../single-job-application-flow-2026-10-16/issues/20-workable-resume-upload.md)；[支持当前岗位已确认邮箱的更正](../single-job-application-flow-2026-10-16/issues/23-current-job-email-correction.md) |
| [确认浏览器速度与人工接管体验](../browser-efficiency-2026-10-17/issues/09-browser-efficiency-acceptance.md) | open / none | [通过 App 用 Gmail 真实岗位验证至人工提交前](../single-job-application-flow-2026-10-16/issues/11-gmail-real-job.md) |
| [核对交付范围并关闭单岗位主流程地图](../single-job-application-flow-2026-10-16/issues/12-delivery-closeout.md) | open / 01a146b9/root | [通过 App 用 Gmail 真实岗位验证至人工提交前](../single-job-application-flow-2026-10-16/issues/11-gmail-real-job.md) |

## 下游分支顺序

1. 「在 App 中可靠观察所属原申请页」→「定位未批准请求并恢复受控字段核验」。
2. 上述两票及「复现并修复 Chrome 原生启动崩溃」「诊断原生会话中断并验证阶段恢复」「核验当前安装身份与在途版本交接」结案后，进入「扩充安装版最小合成验收覆盖本轮故障」（其余已关闭直接前置继续有效）。
3. 组合回归通过后，「支持已观察到的通用 ATS 自定义必填控件」和「支持当前岗位已确认邮箱的更正」可并行验收；「支持 Workable 普通简历字段的受控上传与回读」仍等待控件票。
4. 控件、上传、邮箱更正及其他原前置满足后，真实单岗验收仍须明确恢复许可。完成后浏览器体验接受与交付核对可分支推进；交付核对还要求全子票证据齐备。
5. 材料准备和职业清单两线各自推进，不新增到旧ATS链的硬依赖，不用人审等待阻塞独立工程。

## 初次重组保全与后继执行

初次重组不合并或重编号票，不移动canonical文件，不改Status、Assignee、Claim state、Triage、Blocked by、Parent、验收勾选或历史回执。分组以共同工作上下文组织，不把不同根因或HITL结论合并结案；初次重组没有领取或实施。后继用户明确授权implement后，A组已结案，D/E追加源码支持，其余原状态／领取／依赖保留；本轮未启动原生App／真实模型／外站或变更系统权限。

[完整分组清单](groups.json) · [整理前tracker](tracker-before.json) · [整理后tracker](tracker-after.json) · [核验结果](verification.json)

维护时先运行 `UV_CACHE_DIR=/private/tmp/tomorrowstar-wayfinder-uv-cache uv run --locked --offline --no-sync python -B scripts/query_tickets.py --json`。开放集合或依赖变化时重新核对分组，历史快照不替代当前票头。
