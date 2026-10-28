# 27号票：恢复证据复用与当前结案

2026-10-21，Europe/Zurich。**票首当前5项恢复验收均满足，按该范围结案。** 复用30及同一主App安装、隔离验收和既有恢复结果，不新增实验、不重跑旧矩阵。原负责人`01a150ef/bounded_protocol`和依赖保留。

本轮只读取既有记录、源码、XML与指纹，并更新27票首、计划及地图。没有运行测试、App、浏览器、worker、权限探针、模型、邮箱或真实申请；没有修改产品代码、正式配置、原页、材料、未知结果或fill intent。

## 当前5项逐项核对

| 项 | 结论 | 适用证据及覆盖层次 |
| --- | --- | --- |
| 1 正常重开按当前结果继续；主动暂停/待用户保持等待；保存任务、产物、修改及原页 | 满足，分层证据 | 当前默认XML中的`test_worker_backend_recovery`覆盖原owner读回后自动续行、显式pause/重要缺事实/本人认证/人工最终确认/非空未知intent保持等待；暖恢复先读人工值。G3实际安装验证暂停→正常退出→同根重开，runtime/PID/Page/document/字段/附件/PDF及空intent保持，没有重传/Submit。39页状态只读派生已随包安装。G3没有被描述为正常运行中自动续跑或非空intent原生注入。 |
| 2 完成/未执行步骤复用或继续；外部不明先核对，不盲重放 | 满足 | `test_preparation_recovery`、`test_pdf_export_flow/http`及ResumeStore回归区分queued未执行、明确失败、完整回执、无回执和采用保存不明，核对同一attempt而不重导出。G1实际归档丢回包后inspect、不重发；G1返回原task/PDF、G3原附件不重传是安装复用支持。不同业务的证据不互称对方故障注入。 |
| 3 原子保存、晚到归属、保存/采用竞争；无新批准或恢复调度 | 满足，竞争由实际存储/进程测试支持 | 四个当前默认通过节点：shutdown race写入前/完成回执保存后两个时序，backend SIGKILL时PDF复制子进程仍活着，以及完整回执已存但Flow尚未采用时SIGKILL。真实Flow/ResumeStore经过`export-intent.json→exporter→export.json→Flow采用`；无回执及迟到裸PDF保持unknown，完整回执经核对采用同attempt，不重复模型/导出。另有采用保存结果不明、材料更新journal和checkpoint失败保留旧记录。PDF子进程复制固定文件，不冒称真实编译器。 |
| 4 局部超时/无进展有原因；无整轮10/20分钟停止；离线与安装分别留证 | 满足 | native退出日志/实际父EOF、信号、阶段子程序失败、有限native调用及恢复读回超时均有原因；15秒恢复请求超时前后核验及迟到命令拒绝属于具体操作边界。Pipeline健康运行20分钟后继续、旧cycle deadline不停止健康worker，无UI heartbeat不使会话过期。G0—G3和30实际运行范围独立记录，不以诊断或一次重开推断历史根因。 |
| 5 原执行者/原页/未决动作不因恢复重构被抢占 | 满足 | 既有owner锁、run/Page、关闭门与恢复命令回归；丢原owner不凭URL另开旧页，晚到resume不能恢复写权限；仅无原页/历史副作用的未开页单岗队列可创建新owner。G3保留原worker/Page，正式四根及旧unknown/fill intent保全。当前聊天未触及这些资源。 |

## 为什么无需再跑旧实验

票首2026-10-20当前范围明确替代冲突旧范围。第3项要求保留保存/采用竞争，第4项要求离线/安装证据分别记录；没有要求每种竞争都在native进程再次注入。现有实际SIGKILL、文件持久化和Flow采用测试已覆盖生产恢复合同，实际安装证据补足安装身份、退出/同根重开及原页保留层次。

下方旧`Current scope`中的真实编译器PID/屏障两时序方案及旧“无法归因保持open”不再扩展当前验收。它们的历史记录保留，未执行的实验仍标未验。现行第4项也明确不要求先找齐历史唯一根因。本轮没有发现必须补代码或新增原生故障注入才能证明的当前语义。

## 保留的未知及未验范围

- 历史真实`flow_interrupted`的唯一根因仍unknown；新退出日志不能回填旧因果。
- **当前安装版真实Chrome/Prism编译器在途中断、完整回执已存而未采用时的原生故障注入未新测。** G0 PDF诊断没有任务/attempt恢复契约；G3已完成PDF后重开也不是在途竞争。四项固定PDF进程测试不被改名为真实编译。
- G3为显式暂停后、空intent重开；非空未知intent安装恢复、真实人工值新修改、活旧worker跨版本执行未新测。对应源码行为与安装限度分别保留。
- 丢失原owner或外部结果未知仍等待/先核对，不取消、不重放、不以`page_open=true`推断原页存活。旧owner、fill intent和未知结果保全不等于真实动作已完成或历史原页还活着。
- 30的`worker.package_mapping=verified`不代表总体readiness/旧compatibility诊断全绿；后两者unknown及can_fill诊断false保持。它们不重建逐操作证明门槛。
- 34真实人工Submit→结果→下一岗及其他真实材料/字段/附件、用户体验接受不因此完成。真实申请继续暂停，最终Submit人工。

以上是明确限度，不重新设为当前票前置。

## 复用来源与适用性

- [当前XML节点提取](reused-recovery-nodes.json)：读取既有`full-v3.xml`的23个相关模块451个通过节点，无执行。其中保存/采用竞争仅4节点，其他模块不与旧运行相加。完整既有默认4661通过/2跳过，受影响221、浏览器86分别保留；跳过不计通过。
- [同一主App安装及G0—G3](../main-app-maintenance-2026-10-21/README.md)、[原始分层回执](../main-app-maintenance-2026-10-21/final-readback.json)：G3同页重开及G1重开/丢回包核对直接复用。原失败、实际回滚、工具误开普通窗口及配置JSON重排后恢复原字节的事故说明均保留，不将维护说成全程未读正式配置。
- [30实际安装worker回执](../ticket30-worker-loaded-mapping-2026-10-21/installed-verification.json)：同一主App固定签名、实际PID/run和完整worker角色映射匹配。安装manifest SHA为`1e7ca91bd194cedfe98d77eac77b70b2093115d202f69aa6a889b73213f3f462`。实际范围仅固定Ashby初始化、缺答案等待及暂停原页观察，字段/上传/Submit均0，不扩大为恢复竞争。
- [本次输入适用性](source-applicability.json)：v3的820输入当前仅开发计划和worker CLI启动导入不同；恢复实现、原生退出代码及测试保持。30的7项后继输入仍匹配，其48项及实际安装worker证据覆盖该启动导入差异。本轮不重查权限或再构建安装包。
- [在途PDF源码修复及旧实验限度](../remaining18-recovery-2026-10-20/README.md)、[旧恢复证据分层](../native-acceptance-next-2026-10-20/recovery/README.md)、[原owner/关闭门实现](../product-completion-2026-10-21/README.md)、[39页状态派生](../ticket39-41-source-2026-10-21/state-and-acceptance.md)。旧报告未安装/未收尾是当时时点，不再作为当前缺口；不改写原报告。

独立只读复核按现行条款确认5项满足：实际编译器两时序旧方案不应提升为现行必须重演的门槛。未运行新实验。

`before/`保存票据/计划/地图原字节；[证据指纹](evidence-inputs.json)和[最终读回](verification.json)核对历史后缀/旧勾选、其他票据不变、tracker及本轮准确变更。
