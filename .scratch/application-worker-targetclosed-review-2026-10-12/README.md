# TargetClosedError 诊断独立审查

2026-10-12，Europe/Zurich。范围为本轮诊断包，见[固定范围](fixed-point.json)及[文本快照](review.diff)。没有审查或修改整个脏工作区。

**存在可达的复验证据覆写风险。未发现新的历史生产误归因。** 历史关闭发起方仍未知，生产恢复仍未验证。本轮仅新增此审查包。

## 重点证据核对

| 边界 | 核对结果 | 结论限制 |
| --- | --- | --- |
| 历史入口 | 保留 main 的 AST 匹配恢复参考；保留 250 ms Page timer 和 Playwright 作用域外的错误处理 | 当前 Store、合成 Runner 及 trace 导出包装会改变完整执行。只能证明入口传播路径，不能证明原长期进程的完整重放 |
| 生产与合成 | 原日志只支持错误类型和 timer 文本。合成 trace 支持 openScope 拒绝及作用域清理。26 项检查包含预期故障断言 | 原生合成 trace 仍是合成证据。没有用它补造生产 stack、源码身份、退出事实或恢复成功 |
| 初始 SIGTERM | 探针源码调用 os.kill，facts 保存 requested_signal，并记录本次创建的 Browser PID | stderr 没有直接记录初始 SIGTERM；不能把请求信号字段当成生产观测 |
| 后续 SIGKILL | 同一 PID 的 stderr 记录 graceful close → kill → will force kill → native SIGKILL；固定 SDK 的清理源码调用 process.kill(..., SIGKILL) | 最终 SIGKILL 属于本次受控试验的清理事实，不能反推原生产发起信号 |
| 退出码 143 | 六份既有 SIGTERM 材料中，四份为 native exitCode=143，两份为清理后 native signal=SIGKILL | worker 的 returncode=2 与 Browser 的退出事实是两个进程的记录，不互相替代 |
| OS 记录 | crashpad handler 报告中的时间元数据不完全一致，但各时刻均不绑定目标故障窗口；进程与父进程身份也不绑定原 worker | 未把它当作目标 Browser 的崩溃证据；附近系统活动也不能建立关闭原因 |

[静态入口核对](static-entrypoint-comparison.json)和[同 PID 信号核对](signal-order-audit.json)保留本轮结果。信号核对只读取六份既有材料，没有新增原生试验或相加通过数。

原诊断 [README 第 64 行](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-targetclosed-2026-10-12/README.md:64>)的“先后保留在原始流中”应限定为源码、facts 和 stderr 的关联。stderr 直接记录的是后续清理与最终退出。这个措辞需要更精确，但没有形成新的生产误归因。原说明未改写。

## Standards

独立报告见 [standards.md](standards.md)。发现两处可达的规范违规。

- **[P2] 红测复验会覆写封存附件。** [test_poll_reproduction.py:24](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-targetclosed-2026-10-12/test_poll_reproduction.py:24>)至 28 行在断言前无条件写回固定 stdout、stderr、facts 和 trace。原 README 第 114 行指向此入口。即使末尾按预期失败，初次红测附件也已替换。违反 [CONVENTIONS.md:19](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/CONVENTIONS.md:19>)的不可变证据规则及第 44 行的历史失败保留规则。应新增复验入口，将输出保存到新目录并拒绝已有目标；保留原脚本和附件。
- **[P2] matrix 默认或重复前缀会覆写旧轮次。** [test_diagnostic_matrix.py:16](</Volumes/Codex-Workspace/live/home/zhdeng/Documents/TomorrowStar OS/.scratch/application-worker-targetclosed-2026-10-12/test_diagnostic_matrix.py:16>)默认前缀为空；第 26 至 40 行直接写入已有名称。普通 pytest 调用会替换初轮矩阵；重复前缀也会替换该轮次。README 的新前缀提醒没有保存层保护。违反同一不可变证据规则。新入口应要求新输出目录并拒绝覆盖。

[无浏览器保存探针](static-overwrite-probe.json)用假 subprocess 和临时合成附件确认两条路径。原诊断附件未写入。未发现需要报告的 heuristic smell。保留 main 的 AST 一致性不建立原长期进程源码身份。现有报告已披露当前 Store、合成 Runner 和方法级 pump 的限制。

## Spec

独立报告见 [spec.md](spec.md)。本轴保留独立计数。

“继续定位历史生产 TargetClosedError 根因”仍为部分完成：传播机制已复现，历史关闭发起方未确定。现存原日志缺少堆栈、生命周期顺序和受管退出事实。报告诚实保留这一边界；未发现漏掉可绑定的退出证据。入口等价性成立于历史 main 的控制流程，不成立于完整生产执行。

未发现范围扩张。“不能把合成 crash 通过当生产恢复验证”得到遵守。没有新增真实 ATS、模型或生产浏览器执行。

- **[P2] 复验入口不满足失败证据保留要求。** 规格要求“保留现有验收、失败记录及 04、06 状态”。红测固定归档路径和 matrix 空默认前缀均能覆盖历史失败输出。新 pytest 临时目录不会隔离这些归档目标。[独立临时材料探针](offline-archive-overwrite-result.json)确认两种路径。应新增复验入口，要求新输出目录并拒绝覆盖；旧包保持原样。

未发现信号误归因。SIGTERM 与清理 SIGKILL 的先后来自源码、facts 和同一 PID 的 stderr 共同关联，不能理解成 stderr 直接记录了两种信号。stdout、stderr、facts 未发现对不齐。OS 报告的不一致元数据不足以绑定目标 Browser，现有结论没有依赖这种绑定。

## 本轮验证与保留

两个独立审查均只运行 AST 提取的保存函数，替换 subprocess.run，在临时合成哨兵文件中核对覆写。没有执行原复验脚本，没有启动原生 Browser。这些探针验证保存路径的可达性，不增加产品验收通过数。

[保留核对](preservation-check.json)：1176 个公开受保护文件、8 项原诊断执行输入均无变化。私有原证据及诊断包另做字节、元数据和哈希核对，均未改写。04、06 仍为 closed。现有验收、失败记录、运行代码及票状态保持原状。

新离线探针的 Ruff 与格式检查通过。新报告的相对链接和 scoped diff 检查通过。没有运行全套产品回归，因为本轮没有产品代码变更。没有提交或推送。

Spec 探针的[首次执行源码](probe_archive_overwrite.executed.py.txt)另存。封存前，仅把新审查探针的结果写入改为独占创建；首次结果不变。[重复执行核对](review-probe-output-guard.json)确认当前两个探针均拒绝覆写已有审查结果。这不修改被审查的原诊断脚本。

Standards：2 项发现，最高 P2。Spec：1 项发现，最高 P2。
