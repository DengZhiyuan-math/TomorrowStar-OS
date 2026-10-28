# 两处缺陷修复与 TeX 编译规则 — 2026-10-22

Europe/Zurich。按用户授权先修两个已复现问题，保留现有改动与原工单负责人。后续明确以 TeX 核对事实、措辞、学历及人工修改；编译无错就默认 PDF 可用，不增加独立 PDF 审核或确认。主 App 不更新，真实申请继续暂停。

## 已完成源码

- 资格确认：只有非空且与当前事实一致的 qualification_basis 才能跨复用分析继承；缺绑定的非语言/legacy 确认保留原历史，但不作为新分析的资格放行。原分析、attempt、有效语言确认继续保留。
- 取源重试：当前岗明确 failed 且等待用户时，一次新的 Continue 可授权一次现有队列重试。请求幂等、暂停、运行中和邮件收录中的待派发均有覆盖。needs_recheck 和派发未知不降级为可重试失败，旧入口仍不可绕过 Pipeline。
- 自动材料：TeX 负责内容核对，成功编译即默认 PDF 可用。export_for_draft 和 read_export 的 automatic_materials 路径不再调用独立 PDF inspector。现有编译成功回执、原子保存和防重复执行保护保留。未新增缓存、版本采用或接受对象；历史明确接受不被改写。

## RED / GREEN

- 资格 [RED](qualification-red.log)准确复现 supported≠needs_input；[GREEN](qualification-green.log)12通过，含 Ruby→Rust 与 legacy 缺绑定，以及未变语言确认继承。
- 重试 [首症RED](source-retry-red.log)、[派发未知RED](source-retry-unknown-red.log)及 source-retry-* 后继日志保留；相关8模块160通过。测试覆盖当前岗、同request幂等、再失败须新Continue、运行中/邮件收录、未知不重放；旧内部 acquire 绕过测试改为公开 Continue。
- TeX [RED](tex-build-red.log)准确复现额外PDF检查阻断成功编译；当前受影响回归、最终静态和完整默认结果另行追加。

## 用户转向后停止的切片

曾用实际 Flow 确认：未打印地点更正后 retained TeX 归档相同，模型调用不增，但导出仍会再次编译。[原始重复编译反例](pdf-refresh-red-v2.log)及[探针](deferred-pdf-refresh-probe.py)保留；首次[导入错误](pdf-refresh-red.log)是探针错误，不算产品RED。

用户随后明确要求不纠结 PDF 缓存与版本绑定。因此未实施该优化，临时新测试已移入本证据目录，不作为默认测试或交付门槛；只撤销了本轮为该探针添加的fixture参数，原fixture字节保持。没有以旧PDF替代新事实，没有删除已有缓存或接受记录，也不把这一优化宣称已完成。

## 剩余工作

36第9项继续以 TeX 实际内容与人工底稿为基础处理更广职业事实/JD更新；该项仍部分，保持原负责人。18/20的平台准确场景和33/35的适用接受仍按原票推进。34真实人工Submit→明确结果→下一岗仍未验，真实申请继续暂停。

[本轮前输入](inputs-before.json)、[源码/文档原件](before/)、[原工单快照](tracker-before.json)均保留。最终验证记录将在本目录追加。旧审计和已接受历史不改写。

## 最终统一结果

| 范围 | 结果 | 原始证据 |
| --- | --- | --- |
| 完整默认离线 | **4680 passed、2 skipped、572 deselected，981.50秒，exit0** | [日志](full.log)、[XML](full.xml)、[结果和跳过原因](full-result.json)、[命令](full-command.json) |
| 资格与分析复用 | 12 passed | [日志](qualification-green.log) |
| 当前岗重试及相关8模块 | 160 passed | [日志](source-retry-green.log) |
| TeX/自动导出/人工底稿与旧接口兼容 | 79 passed | [日志](tex-build-affected.log) |
| 静态检查 | Ruff通过；448文件格式通过；git diff --check通过 | [Ruff](ruff-final.log)、[格式](format-verified.log) |
| 独立只读复审 | 三处生产patch未发现新确证问题；独立35项通过 | [审查摘要与会话证据限度](independent-review.json) |

集合有重叠，不相加。两项跳过仍为显式opt-in性能benchmark，不计通过。本轮按默认marker运行，未覆盖marker选择，未跑旧安装矩阵或真实申请。首次格式缺空行的结果保留于format.log，修正后再冻结；全套运行期间[845项输入](full-inputs-before.json)与[读后输入](full-inputs-after.json)完全一致。

[实际差异](source-delta.json)和[补丁](source-delta.diff)记录三份生产模块、回归及文档变化。没有增加依赖、缓存系统、PDF采用接口或批准对象。原128张工单逐字保持，Status/Assignee/依赖和负责人未改变；36仍claimed、第9部分，34真实闭环仍待验。既有接受记录保留，主App未更新或启动，真实申请仍暂停。

最终[读回回执](verification.json)记录工单、输入和导航检查。本报告只声明源码交付与离线证据；不把它扩成安装、新材料真实编译或实际ATS接受。
