# 36号票：新增未映射上下文的影响判断与合并 — 2026-10-22

用户授权继续此切片。保留现有改动、人工内容、工单负责人及接受历史；以实际TeX核对内容。App不更新或启动，真实申请继续暂停，最终Submit人工。

## 实现范围

新增或变化的文档、结构化来源和档案附加上下文不再仅因缺少旧组映射就整体停止。系统把本轮前后差异交给现有材料模型，与实际保留TeX及人工措辞一起判断具体受影响组；判断必须包含明确理由，允许无影响空名单。理由属于模型判断记录，不是事实确认或人工接受。

局部合并复用现有来源、待核对和JD影响并集。完整旧分组边界必须保持，只采用受影响组的候选，其他实际TeX逐字保留。相关新证据可补入所选组，但新增引用只能来自本轮未映射变化对应的当前有效来源（含正文未变、仅文档新增上下文的已有合格来源），原引用不能丢；原始附加上下文或链接不能直接升级成能力证据。已有资格、责任归属、字面值及固定学历检查继续执行。

人工省略内容不恢复，不引入新组插入协议或通用依赖图。本轮在已有可定位分组内合并；需要新增独立经历/学历分组时，不能靠任意模型重分组写入，仍保留TeX作为后续范围。已采用来源缺失、旧来源快照/谱系损坏、未捕获的外部TeX修改，以及生成期间资料/JD/配置漂移仍保留原稿并停止。真实事实冲突保持verify，不因新增资料自动视为已解决。

## 公开流程验证

- [Flow首条RED](flow-01-red.log)：旧逻辑把无关keyword附加上下文直接拦成failed，1 failed；[首条GREEN](flow-01-green-first.log)通过。
- [Flow两项](flow-02-first.log)：2 passed，4.17秒。无关变化保持人工TeX并导出；相关新来源只合并Project 1，保留Project 6人工措辞与Project 3人工省略，随后再次更正新来源并正常局部更新、导出。历史稿/PDF不变。
- 存储/生成器首条[RED](context-01-red.log)及[GREEN](context-01-green.log)保留，后继边界和最终集合结果另行追加。测试使用合成临时工作区和假模型/编译器，不扩为实际材料、安装、ATS或真实申请接受。

## 工单与边界

36保持claimed、Assignee=01a15ab3/root及原依赖。只追加本轮证据，不改原勾选、其他工单或旧接受记录，不据指定切片关闭整票。内容审核以TeX为准，成功编译即默认PDF可用，不增加PDF审核或确认。未知结果、原fill intent和所有更早未提交工作保留。


## 冻结前实现与回归读回

新增35项回归：生成器/存储33项、公开Flow2项。最终[相关3模块](context-10-final-related.log)58 passed，19.29秒，exit0。更早[57项集合](context-07-final-related.log)及[人工改绑省略来源单例](context-08-rebound-omission.log)保留，不累加重叠集合。

复审补齐两项窄边界：[既有合格来源仅新增关联上下文的RED](context-06-existing-relation-red.log)与[GREEN](context-06-existing-relation-green.log)验证可以建立来源关联；[身份引用混入工作组的RED](context-09-identity-red.log)与[GREEN](context-09-identity-green.log)验证新身份来源不进入工作组的新增引用。后者是引用归属限制，未据此声称曾放行虚假能力。

原有5个机械停止断言调整为“缺少有效影响判断仍拒绝”；人工改绑省略来源后，旧来源变化也须明确判断，无影响可保留全文及当前改绑。已采用来源丢失、未知/重复来源、丢掉原引用、集合不可比的无关引用、无效索引/理由/边界、未授权重分组等拒绝路径保留。

静态检查：[Ruff](ruff-final.log)通过，[格式](format-final.log)459文件通过，[diff](git-diff-final.log)通过。首次受影响集合命令因测试文件名拼写错误退出4（[日志](affected.log)），无测试执行；修正后单独保存[affected-v2.log](affected-v2.log)和[XML](affected-v2.xml)。

[858项冻结输入](inputs-frozen.json)、[开始前输入](inputs-before.json)、[差异清单](delta-files.json)、[补丁](task-delta.patch)及[原件](before/)均保留，最终完整默认结果另行追加。所有更早未提交改动和失败历史保持。


独立最终审查未发现阻断问题：[14项功能探针](independent-probes.py)通过（[日志](independent-probes.log)，4.38秒），[运行身份探针](independent-identity.py)1项通过（[日志](independent-identity.log)，1.09秒）。覆盖实际TeX保留、已有Scope新增raw关联、无关引用拒绝、无影响时恶意候选忽略、模型期间来源变化停止等。controller/preparation身份有效，新生成和模型协议代码变化会改变指纹，恢复后一致。

独立首跑[import收集错误](independent-import-first.log)及真实[raw关联漏映射RED](independent-raw-map-red.log)分别保留。身份字面值伪造尝试原有rewrite_allowed保护已经拒绝，不把该既有保护误写为新漏洞；新增identity排除只收紧引用归属。


统一受影响集合最终 **417 passed、1 deselected，126.07秒，exit0**，包含公开Flow、生成器、来源/省略/待核对谱系、固定学历、分组审核和运行身份/readiness/写入准入。默认marker未覆盖，原排除项不计通过。完整默认运行前再次核对858项输入无变化，命令与时间记录见[full-run-command.txt](full-run-command.txt)。


## 最终完整默认与保全读回

完整默认离线回归 **4788 passed、2 skipped、572 deselected，1099.23秒，exit0**；XML确认0 failures、0 errors。见[原日志](full-default.log)、[XML](full-default.xml)及[结构化结果](full-result.json)。两项跳过均为既有显式opt-in本地渲染/性能benchmark，未计入通过；默认marker与原时限保持。

[运行后858项输入](inputs-after.json)与[冻结清单](inputs-frozen.json)逐份相同。整个完整默认运行期间源码、测试、文档和36正文未变。[最终核对](verification.json)确认128张工单metadata完全相同，其他127张票字节不变；36仅追加本轮证据，原字节前缀完整保留。HEAD仍为e4a26d0c24311d014d478f7f92e58a88e6709b4b，无提交或推送，所有更早未提交改动保持。

本轮指定的现有分组内影响判断与合并已完成。新增资料是否相关仍属于依据实际TeX和前后上下文的模型判断；代码强制局部合并、来源引用和谱系约束。需要新增独立组的资料仍保留原TeX，不宣称任意新资料均能自动插入，也不据此关闭36或勾满第9项。36继续claimed，Assignee=01a15ab3/root。App未更新或启动，真实申请继续暂停。
