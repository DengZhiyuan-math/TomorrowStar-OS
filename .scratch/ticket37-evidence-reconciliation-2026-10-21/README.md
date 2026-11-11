# 37号票：一次继续、人工交接及结果观察核对

2026-10-21，Europe/Zurich。**当前8项工程/合成验收均满足，按本票范围结案。** 复用30、34、27及同一主App安装与隔离验收。没有发现必须补代码或重跑测试的具体缺口。依赖和原`Assignee: none`保留，没有补造领取人。

本轮只读取既有源码、回执、XML和文件指纹，更新本报告、37勾选及导航。没有运行测试、旧矩阵、App、浏览器、worker、权限探针、模型、邮箱或真实申请；正式配置、旧owner、未知结果、fill intent、原页、材料和接受记录没有改动。

## 当前8项逐项核对

| 项 | 结论 | 证据及适用范围 |
| --- | --- | --- |
| 1 人工介入/暂停停写，一次继续先读现状 | 满足 | Worker当前岗Continue先校验当前岗、原run/Page和暂停状态，再读取原页；同request幂等。`test_one_continue_reads_existing_page_and_preserves_manual_fields_and_attachment`及默认控件13项中的一次Continue/skip/return证明不要求保存来源→接管→resume三连。原页人工交接停止自动写入；pause及关闭门不能被排队Continue清除。G3实际显式暂停重开保留现场。 |
| 2 人工字段/材料及进度保留，只补缺项 | 满足 | `test_continue_process_preserves_manual_value_over_library_and_keeps_verified_file`使用旧库值反例，人工值和已核验文件保留，零fill/select_file；暖恢复读取人工字段/附件。材料更正复用原Page及既有绑定更新，重要联系事实由23/36处理，不用Continue抹除冲突。G3实际邮箱更正未重传、原PDF和其他字段/附件保持；未新注入真实用户人工编辑。 |
| 3 独立Submit限制及原页人工实际提交 | 满足，合成接收端范围 | 历史22项已通过的真实浏览器/本地接收器节点：自动button/Enter/requestSubmit/form.submit/HTTP/GraphQL最终出口均不达接收端；普通Next/上传可执行。原页保留人工字段与文件，测试动作代表用户唯一Submit点击，接收端实际收到1次、上传仍1次。该点击不属于产品自动动作，不是向真实雇主投递。37只消费38，不重写分类/grant。 |
| 4 自动观察结果、持久记录来源并交34续岗 | 满足，工程/模拟范围 | Pipeline在ready_for_review/observing_result且handoff完成时周期派发只读结果观察，不要求提交声明或回执表单。Runner验证原Page/run/target和本次人工最终request/response，保存`submission_observation`及来源；成功同步原ApplicationStore后才允许34完成当前岗。sync_error/pending_status仍等待。明确拒绝保留观察与停止原因，不记applied、不续岗。真实Flow/Worker/Runner认证HTTP的success/rejected/unknown组合均通过；只证明下一来源选择，不声称第二worker已完整填传。 |
| 5 未知先只读核对，仍未知等待，不重放 | 满足 | Continue保留非空intent；未知人工Submit不能被Continue解锁，旧请求成功响应不能归给新请求，切到另一岗位不记本岗成功。历史接收器lost/late上传节点不重传；未知结果仍保留原页及原动作。本地HTTP200、成功文字或表单消失单独均不能证明雇主接收。30实际原页观察只读、填写/上传/Submit为0；不冒称结算旧未知动作。 |
| 6 skip保存进度并可返回，不取消或成功 | 满足 | `test_skip_append_return_keeps_original_job_intent_pdf_and_owner`及Pipeline/真实Flow跨第二来源return组合：原task/Page/PDF/答案/人工修改/停止及未决intent保持，原claim不清除。skip才允许34选择后岗，return同一原任务并保持暂停直到一次Continue；仅收录候选不激活后岗。G1实际skip/return原task/PDF保持。页面容量有界，不新增长期占页门槛。 |
| 7 正常重开续可确定工作，显式等待保留，原页失效准确停 | 满足，复用27 | 27当前5项已结案；现有暖恢复在原owner锁/run/Page回读后续行，无历史页/副作用的未开页队列才可启动新owner。主动暂停、重要事实、本人认证、最终人工确认和unknown保持等待；失原owner不凭URL另开假装恢复。G3实际同runtime/Page/document/字段/附件/PDF及空intent重开。冷重开/异常及非空intent行为来自源码/进程测试，不冒称原生逐项新测。 |
| 8 合成组合、只有明确成功或skip才下一岗、无并发 | 满足 | 当前默认XML覆盖人工编辑Continue、结果success/rejected/unknown、skip/return及恢复；当前浏览器默认控制13项；历史22项Submit接收端补零自动最终动作与人工原页提交。Pipeline只在成功已落本地或显式skip后离开当前岗，拒绝/unknown不推进，保留页不参与其他岗自动写。不同层次组合复用，没有将全部场景写成一个新原生整链。 |

## 本票结案与34真实接受的区别

37第8项明确要求合成覆盖。本票不新增真实自然Submit或任意SSO作为结案条件；[34当前结论](../ticket34-installed-reconciliation-2026-10-21/README.md)仍为claimed/awaiting-real-acceptance，其真实人工Submit→系统明确结果→下一岗没有发生，实际未验。不会因37结案勾掉34第8项，也不为测试要求用户投递。

当前没有新的可复现reload/SSO交接缺陷。已支持的原Page跨文档普通步骤、同文档本人验证后一次Continue沿用对应浏览器证据；任意SSO、新跨源/弹窗、未知最终协议不推断支持。出现具体路径再归18/对应专业模块，不预造通用矩阵或另一套恢复调度。

## 复用证据与当前适用性

- [已有XML节点提取](reused-nodes.json)：v3默认8个相关模块114个通过节点，v3浏览器controls13项；历史28两份XML各11个Submit节点。只读取既有结果，没有执行；不同层次不相加为本轮运行数。当前v3浏览器86项不含Submit模块，不能说它重跑了旧22项。
- [历史Submit适用性](../ticket30-installed-reconciliation-2026-10-21/historical-submit-applicability.json)：测试、hosted_ats和Worker与v3相同；旧Runner除CLI main外AST相同，Pipeline/Flow后继由当前默认组合覆盖。[本次适用性](source-applicability.json)再次核对v3到当前Runner除main外AST相同；当前main仅增加30已验的角色导入。v3的820输入当前仅开发计划和该启动入口不同，30的7项后继输入匹配。
- [30实际worker加载和运行范围](../ticket30-worker-loaded-mapping-2026-10-21/installed-verification.json)：同一主App固定签名、实际PID/run完整worker角色映射匹配，manifest SHA为`1e7ca91bd194cedfe98d77eac77b70b2093115d202f69aa6a889b73213f3f462`。范围仅固定Ashby初始化、缺答案等待和暂停原页观察，不能扩写为人工Submit或恢复竞争。
- [同一主App安装事实](../main-app-maintenance-2026-10-21/final-readback.json)：G1实际skip/return及等待只收录；G3上传/回读各1次且PDF SHA匹配，邮箱更正不重传，显式暂停/同根重开保持原页。G3是兼容HTML/PDF路线，非自动完整LaTeX原生整链。原失败、回滚、配置误开事故及最终原字节恢复记录保留。
- [27恢复映射及限度](../ticket27-installed-reconciliation-2026-10-21/README.md)、[39状态派生](../ticket39-41-source-2026-10-21/state-and-acceptance.md)、[原Continue/结果接口交接](../linear-continuation-2026-10-21/pipeline-assets/HANDOFF.md)分别消费，不重新建设这些模块。旧交接里的未安装/源码待收尾只代表当时时点。

保留总体readiness/旧compatibility的unknown与can_fill诊断false，旧null回执不回填。G3非空未知intent安装恢复、活旧worker跨版本执行、真实人工新编辑及真实编译器原生在途故障注入未新测；历史中断根因仍unknown。它们不扩成37的旧证明矩阵前置。保全旧动作记录不表示历史页仍活着或真实动作已完成。

## 变更与读回

独立只读复核按本票现行8项确认工程/合成范围满足；未重跑测试或App。`before/`保存37、计划和地图原字节；`## Publication boundary`起的原发布声明及全部历史正文保持，仅当前票头、8项勾选和新增当前结论改变。原发布声明的open/none保留历史含义，不伪造领取。

[证据指纹](evidence-inputs.json)、[最终读回](verification.json)核对原证据、其他票据与34未验项不变，tracker和导航准确。真实申请继续暂停，最终Submit始终人工。
