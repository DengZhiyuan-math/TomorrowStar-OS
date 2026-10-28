# 36号票：两库事实、更正及按影响更新核对

2026-10-22，Europe/Zurich。**当前1—8、10、11满足；第9部分满足。** 保持claimed、原负责人`01a15ab3/root`、原依赖及`bounded-impact-followup`。不以已有材料/安装绿色推导全部影响判断已完成。

复用30、34、27、37及同一主App现有证据。本轮仅读取记录、XML、指纹与源码并更新本报告、36当前勾选及导航。没有运行测试/旧矩阵、App、浏览器、worker、权限探针、模型、邮箱或真实申请；没有读取后重复询问私人事实，没有改两库、旧unknown结果、fill intent、owner、原页、材料或接受记录。

## 当前11项逐项结果

| 项 | 结果 | 可复用证据及范围 |
| --- | --- | --- |
| 1 两库字段职责及已有存储 | 满足 | CareerCatalog持有职业源、学历、经历/证据及责任；原答案/profile库持有申请信息、联系方式、偏好和有作用域答案。修改历史是原库的来源记录，不另建事实真相或生成器。 |
| 2 先检索、按作用域复用、不重问固定事实 | 满足 | `applicable_answers`共享选择；已确认岗位例外优先，其他岗仍取适用事实，重开复用。固定教育由既有文档直接复用，联系方式取当前适用库值；同事实不增加例行批准。 |
| 3 明确更正直接保存到正确库并留史 | 满足 | `CareerCatalog.update_evidence`原位更正普通职业源，保存原字节、actor/source及请求/应用历史；`put_information_answer`包裹原答案库答复、更正、撤回，保留原answers字节和作用域。公开HTTP与Worker入口均有通过节点；不把generated材料写成用户confirmed事实。 |
| 4 来源未知局部处理，不当否定、不使全库停止 | 满足，有界范围 | 来源快照为不可用单文档记录available=false/unknown；其他可用文档继续。责任、资格、学历及提交结果不由未知推造。已被材料消费却无法安全映射的上下文会停当前材料，保留原稿，不表示全部资料失效。 |
| 5 当前重要缺事实/冲突才停，按范围入库后继续 | 满足 | 语言/国家/必要答案及认证组合；答案→一次Continue仍同Page/PDF。34等待时仅收录，后岗不分析/生成/填写；显式skip才离开。普通材料不引入组审核/逐版确认。 |
| 6 全局更正与岗位例外、历史及人工值 | 满足 | 全局与application/company/country作用域分开；信息库更正/撤回及23当前页邮箱一次性更正保留旧答案、PDF和完成动作。37的一次Continue以有效人工值/附件优先，旧库值不覆盖人工页。 |
| 7 分析/筛选/prepare/动作/字段同一适用选择 | 满足 | 分析资格与Pipeline路由、Worker语言检查、Single/Runner实际操作前校验及resolve共享适用记录与当前岗位上下文。不可比较范围不同值保留冲突；岗位例外不被全局门槛覆盖。 |
| 8 German A1→当前例外B2/JD B2整链 | 满足 | 当前`test_language_scope`6节点实际走条件判断→公开prepare→Runner.check_inputs→字段resolve；公司/国家/岗位例外、降低例外、其他岗、不可比较冲突及动作前新冲突有反例。Pipeline、Worker/HTTP和信息库的后继组合及重开复用共同支持，不以lookup单点代替整链。 |
| 9 只更新实际影响、人工底稿合并、无关PDF复用 | 部分满足 | 联系资料只影响材料，保留分析；资格实时核对不废弃未消费该事实的分析/PDF；模型/研究benchmark无关变化保留完成结果。同JD可核验的职业更正只替换受影响组，其他人工文字逐字保留，原源/PDF及attempt历史保留。**更广职业资料/JD变化的结果级消费影响与无关结果复用尚未完整证明**，详见下一节。 |
| 10 普通事实与研究Skill/封存独立 | 满足 | research/sealed/schema对象写保护，普通职业源/profile更正不改封存研究结论，不要求先封存职业图。内部工具归属仍留证，雇主简历不披露AI/editor来源；固定教育不按JD改写。 |
| 11 合成组合及原子失败保全 | 满足 | 两库复用、更正/撤回、作用域冲突、无关变化、相关材料更新、人工底稿及重开节点已有；职业/答案原子替换失败保留旧字节和待核对历史。27/37恢复、39只读派生及原页保全直接复用。 |

## 第9项：已完成与真正未覆盖

以下不再列待做：联系方式与分析输入分离；资格live核对；无关答案/模型配置/研究benchmark不全局作废完成PDF；同JD确定性页眉更新及受影响分组更新；人工底稿、原材料与历史保留；已绑定原页的一次Continue安全换版。这些实现和合成回归已随包安装，G3还实际证明本岗邮箱更正不重传、原页/附件/PDF及空intent重开保持。

**剩余集中在实际消费边界的影响判断。** 当前`career_source_snapshot()`摘要覆盖整个来源快照，`current_flow_inputs.sources_revision`采用它；`Flow.update_inputs`在该分析绑定变化后重置当前分析/材料引用，同时保留历史产物。不能据此宣布任意无关职业文档变化都已保留当前分析/PDF。

可执行的最小后继切片：

1. 使用现有分析预算与`included_source_ids/omitted_source_ids`，选一个明确省略的独立来源，只改变该来源的有界正文。
2. 比较前后**实际保存prompt/消费投影**，先证明当前分析的事实输入未变；再经现有公开Flow更新验证分析身份/历史复用，不发起真实模型。
3. 对材料单独判断影响。完整LaTeX的`document_context`可能仍消费该文档，不能把“分析省略”扩成“材料/PDF也无关”；无关才要求原PDF身份/字节复用，相关则更新已映射组，重要歧义保持等待。
4. 保留旧记录及人工底稿；不以删掉`sources_revision`或只看`selected_source_ids`绕过真实消费。不先建设通用依赖图，不跑旧安装/权限/Submit矩阵。

这条切片是明确的**待验证边界**，不是本轮已运行的失败复现。现有`test_long_sources_disclose_exact_omission_and_truncation_but_keep_complete_jd`已证明实际有省略来源，尚未覆盖“省略来源变化→原分析复用”。本次静态检查也发现来源预算与整快照绑定之间的范围差异，但没有据此捏造全链失败结果。

必须保留两点区别：

- 未选入简历不等于未被分析/材料模型消费。当前project6变化触发重分析回归不能单独证明错误失效；profile.title HTTP更正后人工正文未变仍重新分析/导出的回归，也没有证明其对所有结果无关。
- 同JD分组保留已有保证；跨JD时普通路径仍传`manual_latex_base`作底稿，`retained_career_draft=None`只表示不启用同JD确定性合并，不能称人工稿丢失。跨JD重要语义冲突合并的同等保证仍未验，不能泛称已完成。引用丢失、已消费未映射上下文或组归属歧义时停止，属于正确保护，不要求自动猜答案。

因此第9保持未全勾，36不关闭。无需用户重述既有事实，也无需恢复真实申请来补这项工程边界。

## 证据来源、版本与限度

- [当前默认XML节点](reused-default-nodes.json)：16个相关模块351个实际通过节点，另提取1个既有省略来源节点；[当前浏览器节点](reused-browser-nodes.json)42个通过节点。它们来自已有full-v3/browser-v3，不是本轮重跑，不相加为新运行数量。默认既有4661通过/2跳过、受影响221、浏览器86各守原范围。
- [两库更正及来源历史](../linear-continuation-2026-10-21/fact-assets/README.md)、[联系/资格/配置影响分离](../product-completion-2026-10-21/input-impact-assets/README.md)、[同JD职业影响合并](../browser-material-entry-engineering-2026-10-21/materials/README.md)、[原页材料安全更新](../bound-material-update-2026-10-21/README.md)。旧“后继尚未实现”按其时点保存，不能当作当前已交付部分的缺口。
- [输入适用性](source-applicability.json)：v3的820输入当前仅开发计划和worker CLI启动导入不同；相关事实、作用域、历史、影响实现与所选测试均相同。30的7项后继输入仍匹配；该启动差异由30既有48项及实际worker覆盖，不重复测试。
- [30实际worker证据](../ticket30-worker-loaded-mapping-2026-10-21/installed-verification.json)：同一主App固定签名、实际PID/run完整角色映射匹配；manifest SHA为`1e7ca91bd194cedfe98d77eac77b70b2093115d202f69aa6a889b73213f3f462`。实际范围仅固定Ashby初始化、缺答案等待、暂停原页观察，字段/上传/Submit均0；不是全套事实更正原生重演。
- [同一主App G1/G3](../main-app-maintenance-2026-10-21/final-readback.json)、[27恢复](../ticket27-installed-reconciliation-2026-10-21/README.md)、[37一次继续/交接/返回](../ticket37-evidence-reconciliation-2026-10-21/README.md)、[34当前分层结论](../ticket34-installed-reconciliation-2026-10-21/README.md)复用其各自范围。34真实自然Submit→结果→下一岗仍实际未验。

总体readiness/旧compatibility诊断unknown、can_fill诊断false、旧null回执、历史根因unknown继续保留。G3只新测显式暂停及空intent重开，非空未知intent安装恢复、真实人工新修改、活旧worker跨版本及真实编译器原生在途故障注入没有被补写为通过。旧unknown、fill intent、owner和接受PDF不清除、不重放、不重新确认。真实申请继续暂停，最终Submit人工。

独立只读审查确认10项满足/9部分，并明确区分影响覆盖缺口与尚未复现的bug；没有运行测试或App。`before/`保存36、计划和地图原字节，原`Publication boundary`起正文与历史不改。[证据指纹](evidence-inputs.json)及[最终读回](verification.json)记录其他票据、旧证据、接受记录和暂停状态保全。
