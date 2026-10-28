# 诊断原生会话中断并验证阶段恢复

Type: task
Label: wayfinder:task
Status: closed
Priority: P1
Interaction: AFK
Assignee: 01a150ef/bounded_protocol
Created: 2026-10-17
Updated: 2026-10-21
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [将单岗位流程设为原生 App 默认运行方式](08-native-runtime.md)、[完成单岗位链路与故障恢复整体验证](09-integration-verification.md)
Triage: done
Closure reason: completed

## 当前精简范围 — 2026-10-20

## Question

在单一岗位主控和各阶段真实记录下，如何恢复同一任务、产物与原页而不重复已完成或结果未知的动作？

规范：[产品规范](../../../docs/single-job-flow.md)；安排：[开发计划](../../../docs/development-plan.md)。本节是本次精简任务化后的当前范围，替代下方冲突的旧范围和验收。Status、Assignee和历史收据不变；本次不领取、实施或关闭。

本票只负责恢复/保存采用竞争，消费[统一岗位主控并派生浏览器执行状态](39-single-orchestrator-derived-state.md)；不再重写选岗调度或独立维护worker状态副本，人工交接由对应交接票负责。

当前验收：

- [x] 正常运行退出/重开按断点和当前结果自动继续，主动暂停/待用户保持等待；保存task、attempt、产物、历史、人工修改与可用原页。
- [x] 明确已完成或未执行的步骤复用/继续；外部结果不明先核对，仍不明才问，不用进程中断一概判定未知或盲重放。
- [x] 保留原子保存、晚到结果归属及保存/采用竞争；不新增逐attempt批准、全局proof或第二套恢复调度。
- [x] 具体操作超时/无进展有明确原因；无整轮10/20分钟停止。受影响阶段离线/安装证据分别记录，不要求先找齐历史唯一根因。
- [x] 原页所属执行者和未决动作不为恢复重构而重启、取消或被新controller抢占。

## 当前结论 — 2026-10-21，同一主App证据复用

票首当前5项按适用源码、实际存储/进程竞争及同一主App安装层次满足，按当前恢复范围结案。[逐项映射与保留限度](../../ticket27-installed-reconciliation-2026-10-21/README.md)。原Assignee和依赖保持；上方“本次不领取、实施或关闭”保留原精简入票时点，本节记录后继核对。

G3实际证明显式暂停后同runtime/Page/document/字段/附件/PDF及空intent重开保留；正常恢复自动续行、非空unknown intent及保存/采用竞争由适用源码/进程测试支持，不冒称在原生逐项重演。4项真实子进程/存储竞争使用固定PDF复制器，未新测当前安装版真实编译器在途及已保存未采用两时序。当前条款要求分层记录，未要求每种竞争重跑native；不沿用下方旧实验方案或“历史唯一根因”作为新总门槛。

本轮无新增代码、测试、App或真实申请动作，不重跑旧矩阵。30实际worker完整映射已有，旧null及总体readiness/旧compatibility的unknown保持；历史flow_interrupted唯一根因仍unknown。未知结果、fill intent、旧owner、原材料及历史正文/旧勾选不改。34及真实接受不被覆盖，真实申请继续暂停，最终Submit人工。

以下保留原范围与历史证据，不将新期望追写为旧票未完成原因。

## Current scope and next verifiable slice — 2026-10-20

已具备原生退出／父EOF日志、旧安装候选部分恢复及源码级保存竞争证据。源码中真实子进程复制固定合成PDF的竞争测试，不是当前安装版真实PDF编译／浏览器进程证据；历史中断根因仍未知。

下一项独立切片是：在全新隔离合成工作区，通过实际安装入口启动真实PDF导出，在可观察且有期限的在途子进程时点触发退出，重开后核验同一任务、attempt、历史、采用状态与无自动重跑。先确认精确进程归属，只作用本轮自建资源；无法可靠绑定触发时点就停止并记录未验，不靠猜测点击或放宽超时通过。实际在途PDF中断与“结果已保存、尚未采用”的竞争分别结论，前者不冒充后者。

原根因、保存／采用竞争和完整安装恢复门槛保持；不因这一切片通过自动关闭本票、重新批准材料或恢复真实申请。

## Question

简历生成期间发生的 flow_interrupted 是哪一层退出造成，恢复后如何保留原结果而不重复工作？

## Problem and priority

来源：[复盘 E04](../test-findings-2026-10-17.md)与[真实岗位记录](11-gmail-real-job.md)。该次中断已留证，但根因未定；不等同 Chrome 启动崩溃。P1：消除阶段中断的盲区，保证更新或故障后状态可解释。

## Work and reuse

- 将原生退出、父控制管道 EOF、后端退出、CLI/PDF 子进程退出及阶段 checkpoint 按时序关联；正常退出与意外中断分开。
- 复用 flow 的 attempt、adopted 标识、artifact 历史和 close/recover，定位原事件再选择最小修复。
- 隔离验证用户正常退出、后端故障、生成完成与退出竞争；保持父 EOF 关闭机制，不通过保活所有子进程掩盖中断。
- 未采用结果保留但不变成当前材料；重开 App 不自动重跑模型、重新批准或恢复填写。

## Ownership

- `macos/App.swift`、`macos/server.py`、`application_flow.py`、`application_resume.py` 中经归因确认的最小调用点及其现有测试。
- 不修改已批准 PDF、原分析或私人资料；共享文件先与 26、28、30 协调。

## Acceptance criteria

- [ ] 原事件能说明触发退出的一层和关联依据；若缺证则明确未知，不以一次重启成功关闭修复范围。
- [ ] 正常退出和已复现的异常退出有独立用例及准确状态；原时限保留。
- [ ] 完成与中断竞争不丢已保存结果、不把旧/未采用 PDF 变成当前材料，不重复模型调用或上传。
- [ ] 恢复保留同一任务的版本与历史；只有用户明确重试才建立新的 attempt，材料批准按原绑定规则处理。
- [ ] 安装版隔离恢复通过，且提供阶段退出因果记录；真实原件和旧失败保持不变。
- [ ] 对已复现根因的修复及受影响/完整默认离线通过；无法归因时保持 open。

## Verification and evidence

使用合成 CLI、PDF 和临时工作区进行故障注入，不能在真实申请或旧进程上触发故障。只读日志与故障注入结果分别标注。

## Authorization and stop boundary

本次仅建票；当前 App、worker 和原申请均不因此重启。后续开发与隔离实验另行执行，真实恢复仍须单独获得用户许可。

## Resolution comment

2026-10-17：新建未领取；不将既有通用恢复测试当作本次原生中断的归因证据。

2026-10-19：核对 open/none 且 08/09 已关闭后领取。当前仅补原生/后端退出因果记录与合成 EOF/SIGTERM 验证，不修改 flow/resume 阶段契约；历史根因未知，保持 open，真实申请继续暂停。


2026-10-19 源码观察边界：原生 `App.swift` 在私有 diagnostics 下按独立运行保留
无正文 JSONL，记录 UTC、pid/ppid、正常退出请求/取消/批准、窗口关闭请求、父管道关闭请求、
后端启动，以及实际可取得的后端退出码或终止信号。2 秒 TERM、4 秒 KILL 的原有上限与
EOF 关闭机制保留；强制终止记录写成“请求”，不冒充已观察退出。
日志错误不改变关闭路径。未记录输入正文、凭证、命令参数或完整路径。

`macos/server.py` 抽出既有 `serve_with_parent_pipe`，在选定私有 runtime/diagnostics
逐运行写入后端启动、实际父管道 EOF/收到信号、首次 shutdown 原因与关闭完成/失败。
后续信号单独留证，不覆盖首次 shutdown 原因；读取父管道仍使用 raw stream，
shutdown 仍在独立线程调用，无新增保活子进程或通用事件框架。

[新合成回归](../../../tests/test_native_exit_causality.py)先得到缺观察边界的 RED，
随后 GREEN：真实 EOF、真实 SIGTERM 及日志目录为链接的失败反例均按期退出；
Swift 最小 logger harness 核验真实子进程 exit code/信号、保留历史、写日志失败不阻碍退出。
完整 App.swift typecheck、所拥有 Python 的 Ruff/format/whitespace 检查通过。
原字节、RED、合成结果、命令与墙钟在执行者任务独立临时证据目录保留。
未启动 App、Chrome、真实服务、模型或 ATS，未修改 flow/resume、已批准材料或历史失败证据。

限制：这些观察不能追溯补足旧事件的因果证据；原事件根因仍未知。父原生进程已结束后，
不能保证其 terminationHandler 继续写到子进程结果，缺失记录必须保持未知。
模型/PDF 子进程和阶段 attempt/checkpoint 关联尚未接入，当前安装版隔离恢复尚未执行。
源码和合成通过不关闭本票，全部整票验收项仍未勾选；真实申请继续暂停。

### 2026-10-19 — 保留安装版的两条阶段因果验证

在保留的独立安装版与两个全新合成材料目录，实际原生窗口验证：

- 固定分析 CLI 已进入且尚未启动响应子程序时，明确退出原生 App。
  原生日志记录退出批准和父管道关闭请求，后端实际观察 EOF 并完成关闭；
  同一任务、输入和 attempt 保留为 `flow_interrupted`。重开窗口显示明确重试入口，
  本次观察范围内没有新进入记录或新 attempt。
- 固定响应子程序的实际 `wait()` 返回失败值，岗位分析保存为模型不可用失败；
  失败时原生窗口与后端仍存活。重开保留同一任务和失败 attempt，无新调用。
  该场景把阶段子程序失败与原生/后端退出分开。

两次窗口均已退出，登记进程已确认不在，原包身份和严格签名保持。
原始 AX、截图、任务前后 checkpoint、子程序 wait、原生/后端日志与各自来源保留在
独立私人证据目录。wrapper 的退出请求不冒充外部取得的实际退出码；原生终止后
未能取得的后端终止回调保持未知。

这是保留旧安装字节的合成恢复证据，不能替代后继候选安装验收。
未生成或批准材料，未创建申请 worker。历史事件根因、PDF 保存/采用与退出竞争、
PDF 子进程归因仍未证明；本票保持 open，整票验收项不提前勾选。

同日补正常完成对照：在第三个独立合成目录，经保留安装版原生 UI 完成固定分析、
完整 LaTeX 草稿、固定同源预览、两组测试事实审核及 PDF 绑定。完成检查点之后正常
退出并重开，同一任务、采用历史及全部既有非诊断文件的字节和 mtime 保持；CLI 事件
相同，未出现新调用。PDF 继续待单独确认，`materials_confirmed=false`、`worker_ref=null`，
没有申请 worker 目录。登记进程已退出，完整签名命令/目标/时间/结果已另行保留。

此 PDF 来自进程内固定 SyntheticPrism 回放，不是实际编译器子进程证据；
“先完成、后退出”不覆盖反向完成竞争。仍是旧安装版的有界证据，不替代新候选验收。

## Supporting durable PDF completion/shutdown race — 2026-10-20

总目标下本会话补源码独立验收，原Assignee保持。新增 `tests/test_pdf_export_shutdown_race.py`：真实ApplicationFlowService与ApplicationResumeStore，实际有界子进程复制固定合成PDF，分别在子进程写入前、导出manifest持久保存后而callback返回前close/reopen。

两种时序均保留迟到PDF和complete manifest而不自动采用；同task/draft/attempt/recovery history保持，旧callback锁拒绝新重试；退出后未知结果仍要求明确核验，核验后采用同attempt且不重复模型/导出。未确认材料、worker_ref为空。子进程PID就绪读取和等待均有期限，正常退出及兜底清理有断言。新增2项及相关合计71项通过，Ruff/格式/diff通过。前两轮失败为合成fixture不完整，未记为产品RED。

本切片不是原生安装版退出/EOF或真实编译器归因，也不能补历史根因；整票保持open，原验收不提前勾选。实际原生及当前安装组合仍需独立证据。见[源码竞争验收摘要](../../autonomous-engineering-2026-10-20/pdf-shutdown-race/summary.json)。真实申请保持暂停。

## Approved ticket revision — 2026-10-20

按用户同意的审计修订发布：更新当前停点及剩余验收，不改原领取、历史回执或既有依赖；不追加真实运行授权。新增证据保全工作可独立推进，其产物供本票适用范围引用，不代替本票原验收。

## Parallel execution group — 2026-10-20

[D — 原生退出与阶段恢复](../../open-ticket-parallel-plan-2026-10-20/README.md#d-recovery)。跨票顺序、共享文件及原生实验串行约束见统一分组导航；本票状态、原领取、依赖与验收仍按上文执行。本次仅重组导航，不领取或扩大执行许可。

## Parallel implementation support — 2026-10-20

用户明确授权implement并发工程；本会话以01a1586d/root/recovery_boundary补充独立进程边界回归，不替换原领取。新增实际后端进程在完整合成PDF回执落盘、callback采用前被SIGKILL的反例。重开保留同任务、输入、草稿审核及attempt，先阻止重试，明确核验后采用原回执；无模型／导出重放，材料与worker许可未提升。相关检查通过；见[验证与限制](../../recovery-boundary-support-2026-10-20/README.md)。

固定PDF复制子进程在终止屏障前已退出；此结果不证明安装版原生退出、仍在运行的真实编译器中断或历史事件因果。本票保持open、原领取及未勾验收，整仓检查另见[并发执行记录](../../parallel-implementation-2026-10-20/README.md)。

### 2026-10-20 — 在途导出未知结果支持修复

真实终止合成后端且旧合成PDF子进程仍在途的回归发现缺少完成回执时过早允许重试；现改为保持needs_recheck。迟到裸PDF不自动采用。已覆盖已知失败的显式重试；原生屏障／进程代次／attempt关联及历史同因仍待原owner。 本次仅由01a1586d/root提供工程支持，不接管原领取，不更改Status、依赖或验收勾选。真实申请继续暂停。完整最终验证与集中待办见[本轮工程记录](../../remaining18-engineering-2026-10-20/README.md)。


## 实际主窗口重开支持 — 2026-10-20

本轮隔离原生合成任务完成真实Chrome PDF后遇到用户重启。日志记录原native正常Quit批准及父管道关闭，随后仅以相同合成根重开唯一主App；同task、resume与PDF摘要、未确认状态保留，没有重新分析、生成或导出，worker尚未prepare。此为完成阶段正常重开正例，不是在途导出、强杀/父进程异常或历史中断归因的验收，原勾选/领取/状态保持。[本轮原生验收](../../remaining18-resumed-2026-10-20/README.md)。

## Comments

### 2026-10-20 精简方案入票

当前实现职责和前置依赖按本次方案收敛；原Status、Assignee及历史验收未改。原依赖如下，仅作历史，不参与当前前沿查询：

原 Blocked by: [将单岗位流程设为原生 App 默认运行方式](08-native-runtime.md)、[完成单岗位链路与故障恢复整体验证](09-integration-verification.md)


## Notes — 必要材料、路由与恢复后继 2026-10-21

关闭后阻断已接收 legacy 请求及迟到恢复命令；暖恢复须核验原 owner 锁、run/Page 和当前值，15 秒截止在 Runner 读取前后均验证。重复关闭归档旧回执，旧命令不能恢复写权限；未开页冷恢复只限无历史副作用的单岗队列。遗失 owner 的历史 Page 保持 needs_recheck。

完整默认离线：4440 passed, 2 skipped, 460 deselected in 718.67s (0:11:58)；受影响离线 1097 项、本地浏览器 164 项均通过。[工程记录、失败历史及冻结输入](../../product-completion-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 原页材料安全更新后继 2026-10-21

材料绑定更新使用可恢复 journal；候选、Flow、Single 与 Worker 的中断点恢复须核验原材料及 attempt，不以迟到回包或取消结果重建已消费导出。原 owner/Page 读取与截止约束继续生效。只验证源码与合成 Runner，未启动安装 App。

完整默认离线：4450 passed, 2 skipped, 497 deselected in 727.15s (0:12:07)；受影响离线 1358 项、本地浏览器 217 项均通过。[工程记录、失败历史及冻结输入](../../bound-material-update-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 精准等待前必要材料与人工附稿修复 2026-10-21

排队 Continue 后 pause/cancel/skip 必须先停止，不被旧排队动作复活。附稿本地导出在应用写锁外执行；跳过/失联保留消费记录与独立候选，返回原岗只能核验确切已完成文件，缺失或改写候选继续 needs_recheck，不重做模型或导出。

完整默认离线：4462 passed, 2 skipped, 532 deselected in 968.76s (0:16:08)；受影响离线 1370 项、本地浏览器 252 项均通过。[工程记录、失败历史及冻结输入](../../precision-material-preparation-2026-10-21/README.md)。Status、Assignee、依赖及既有勾选均不变，不新增或关闭票。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 可用优先重排 2026-10-21

消费现有指定岗/owner/恢复源码，不等待状态副本清理整票。

Priority/Triage/票头依赖按本次重排更新；旧边与原字节见[审计及变更账本](../../usable-first-wayfinder-audit-2026-10-21/README.md)。原 Status、Assignee、Interaction、既有验收勾选及全部旧正文保持，不领取、不关闭、不替用户接受。源码接口依赖不等于安装或真实操作许可；App 未更新，真实申请继续暂停。
