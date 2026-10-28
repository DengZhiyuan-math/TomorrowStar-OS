# 工作与代码审计 — 2026-10-22

Europe/Zurich。范围为当前工作区：HEAD `e4a26d0c24311d014d478f7f92e58a88e6709b4b` 加未提交及未跟踪源码。用户要求整理工作、审计代码和汇报进度。本轮只修正进度导航并保存审计证据，没有修生产代码、领取或关闭工单。App更新和真实申请继续暂停，最终Submit人工。

## 当前进度

| 范围 | 当前结论 | 下一步 |
| --- | --- | --- |
| 工单总览 | 128张；111 closed/resolved，17未关闭（11 open、6 claimed）；依赖错误0 | 按[17项清单](remaining-tickets.md)与原负责人推进 |
| 默认主流程、共享材料与入口 | 39/40/41已按源码范围结案；42邮件设置/进度已交付 | 消费既有接口；修复本轮确认的恢复入口缺陷，不重建主流程 |
| 30/27/28/37 | 既有安装、恢复及交接适用证据已完成各自范围 | 复用历史证据；不能扩成最新36源码已安装 |
| 36事实更新与结果复用 | 11项中10项满足，第9部分；省略来源分析复用已交付 | 先修本轮资格继承问题；再有界验证同归档Flow导出及更广JD变化 |
| 平台兼容 | 18导航、20 Workable autofill/附稿、33 Ashby真实初始化各留原范围 | 具体场景驱动；Workable附稿仍不能借resume端点发送 |
| 35真实邮箱 | 标签配置和进度源码已交付 | 账号隔离、先本地保存再label/archive的实际收据仍待验 |
| 34真实闭环 | 当前1—7/9满足，第8部分；人工Submit→明确结果→下一岗未验 | 保持暂停，未来由用户自然手动提交后观察，不强迫投递 |
| 独立职业图研究 | Phase 9执行中；后继inventory接受、Grill-Me评审及三JD研究仍待完成 | 不阻普通申请；研究25%是2/8阶段边界，不是产品完成率 |

实时字段和完整依赖见[tracker](tracker-before.json)。20项`unknown_metadata`警告主要属历史负责人/领取信息；未记录owner不推断。机械frontier为空、`execution_authorized=false`不表示源码工程没有下一步，也不授权真实执行。

## Standards

**1条确认问题，P2：默认流程在JD明确失败后缺少可用重试入口。**

触发：当前岗取JD返回明确失败（`failed`，不是`needs_recheck`）；用户已处理临时问题并点击一次Continue。

- [Pipeline Continue](../../src/career_evidence_graph/application_pipeline.py#L648)仅恢复`acquiring_source`；[队列推进](../../src/career_evidence_graph/application_pipeline.py#L1279)再次见`failed`便回`needs_input`，没有调用重试。
- [默认界面](../../src/career_evidence_graph/portal_static/application_flow.js#L419)隐藏`failed`的“重试取得JD”按钮；旧`recommendations/acquire(retry=true)`又被[主流程准入](../../src/career_evidence_graph/application_pipeline.py#L224)拒绝。
- 合成loopback公开HTTP复现：Continue=200，随后仍同岗`needs_input`；acquire/fetch均1→1；显式旧重试接口409/`pipeline_entry_required`。UI条件为静态核对，本轮未新开浏览器。
- 违反CONVENTIONS的“Manual intervention ... needs one Continue”，及APP-13/14的断点恢复、返回后继续。已有`test_pipeline_current_job.py`通过内部`intake.acquire(...retry=True)`恢复，未覆盖默认公开入口。
- 修复方向：由当前Pipeline接受用户明确重试已知失败的取源；保留同岗归属、unknown不重放和单执行者保护。无需放开旧入口或加新调度器。

[探针](source-retry/test_source_retry.py)、[结果](source-retry/evidence.json)、[日志](source-retry/run-v2.log)。**1 passed表示缺陷被断言复现，不是功能修复通过。** 初次[日志](source-retry/run.log)是合成fixture缺git init，保留原失败，不算产品RED。

## Spec

**1条确认问题，P2：非语言硬条件在事实更正后仍继承旧确认。**

触发：人工确认“Residence in Ruby required”，依据职业库location=Ruby；该来源因上下文预算被分析省略。用户将location更正为Rust，实际分析prompt不变。

- [继承判断](../../src/career_evidence_graph/application_flow.py#L886)把两边`qualification_basis=None`当成依据未变；[事实绑定函数](../../src/career_evidence_graph/application_information.py#L157)只支持法/德语言，其余硬条件返回None。
- 实际`create_server → Flow.start → analyze_job → update_inputs`合成路径保留旧报告，创建新分析采用记录，并把旧人工确认搬到新analysis_id。更正后资格仍为`supported`。
- 断言核对：前后prompt各126033字节且SHA256相同，location Ruby→Rust，`inherited_from`指向旧确认，新采用ID不同，原分析目录字节不变，更新过程模型调用0。
- 违反APP-05/15/18，以及36切片“对应事实依据未变才继承”的承诺。模型输入等价只支持文档分析复用，不能证明人工资格确认继续有效。
- 修复方向：可核验且未变的事实依据才可继承。缺少绑定不能作为依据未变的证据；保留旧确认历史，对受影响的重要资格停等核对。

[独立探针](nonlanguage-probe.py)、[JSON结果](nonlanguage-probe.json)。exit0表示反例成立。其余本次指定边界未发现新的已证实问题：已有worker不进入新采用路径；未知生成/导出与pending准备先拒绝更新；原报告保留；确切prompt及隐藏引文来源均参与比较。

两条问题按两条审计轴分别报告，不互相抵销。没有把文件长度、抽象偏好或未验证猜测列为代码缺陷。本轮没有修改上述生产行为。

## 验证及证据适用性

| 证据 | 结果及限度 |
| --- | --- |
| 本轮有界回归 | [112 passed / 14.15s](affected.log)，[XML](affected.xml)。覆盖分析复用/guards、Worker派生视图、retained review、Submit限制、Pipeline continuity、tracker；未覆盖上述两个新反例 |
| 本轮静态检查 | [Ruff通过](ruff.log)、[447文件格式通过](format.log)、git diff --check通过 |
| 最新完整默认离线历史 | [4672 passed、2 skipped、572 deselected](../ticket36-omitted-source-2026-10-22/full-result.json)，969.82s；825项冻结输入，运行前后无漂移。本轮未重跑全套 |
| 该冻结与当前比对 | [4项差异](baseline-delta.json)：三份进度/票据文档与一处已记录的测试隔离参数；生产代码完全一致。新增两反例说明原绿测覆盖不足 |
| 36材料/PDF有界核对 | [3项通过](../ticket36-material-pdf-inputs-2026-10-22/README.md)。原样完整材料486355字节、前后prompt不同，均在128000上限前停止，材料模型/编译均0；未证实原样场景无关重生成 |
| 本轮安装包只读比较 | [120份checkout运行/支持文件](installed-comparison.json)：89相同、3不同、28未打包。3份不同是application_flow.py、application_match.py、career_portal.py；28份包括开发支持文件，不能当缺包bug。未启动App、读取实际worker或重测权限 |

两个性能benchmark明确opt-in而跳过，不计通过。集合有重叠，全部数字不相加。源码、安装、真实编译/视觉质量、邮箱/ATS操作、用户接受和招聘结果各守自己的证据范围。

原安装包worker启动文件及Pipeline源码与当前相同；最新分析复用相关的三份生产模块尚未进入现装包。本轮未改App、真实配置/事实库、邮箱、页面、附件、unknown结果或fill intent。两个探针仅合成临时数据与loopback，未调用provider或真实ATS。

## 整理结果和后续顺序

1. 已校正[当前开发计划](../../docs/development-plan.md)的日期与17项未关闭表，移除39/40/41的过期待做行；源码结案仍保留安装及真实接受边界。原计划字节见[整理前文档](baseline-documentation.json)。README增加本报告导航。
2. 先按当前owner协调修复本轮两个P2，并为公开Continue与非语言资格更正补精确反例；不抢占共享Pipeline/Flow文件。
3. 36第9项继续做同归档Flow导出的有界验证；18/20只推进准确目标所需平台切片，33/35保留适用真实接受。
4. 何时恢复同一主App更新、何时恢复真实申请仍集中待用户决定。本轮不要求确认、不启动这些操作；34与整体交付继续保留真实闭环门槛。

最终读回见[verification.json](verification.json)：工单身份/状态/负责人/依赖及原字节保持，825输入中的全部生产源码保持。工作区原有dirty内容未整理提交、清理或回退。
