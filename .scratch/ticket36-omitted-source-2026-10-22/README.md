# 36第9项：省略来源更正的有界修复

2026-10-22，Europe/Zurich。仅处理用户指定切片：先证明被分析省略的来源更正不改变实际输入，再修明确的无关重算。材料/PDF影响独立，真实申请继续暂停。本轮源码修复未更新、安装或启动主App，原安装证据不被改称新修复的安装验收。

## 真实路径RED

新增公开回归经真实`create_server → Flow.start → analyze_job`，模型边界仅使用固定合成CLI返回。保持原128000字节预算，首个大贡献自然耗尽上下文预算，独立`profile.location`被明确列入`omitted_source_ids`。通过`CareerCatalog.update_evidence`将合成Ruby更正为等长Rust，没有私人事实或研究对象写入。

[RED日志](regression-red.log)及[原始输入证据](red-fixture/summary.json)证明：

- 前后实际prompt均126033字节，SHA256均`19bfceb7af631e25ba1b51a92321d378c3d0685d61a86c870ca17a8155860ecf`；[原prompt](red-fixture/before-prompt.txt)和[更正后prompt](red-fixture/after-prompt.txt)字节相同。
- 完整来源快照revision改变，仅`sources/profile.json`文档变更；被消费贡献及实际分析输入未变。
- `Flow.update_inputs`却把当前`analysis_id`清空、分析阶段变pending；原分析目录和历史仍在，未调用新模型。

排查区分整快照绑定、配置连带变化及更新误清结果。该案例配置/JD不变，明确原因是Flow按完整`sources_revision`重置分析。不是凭“未选入简历”推断无影响。

## 最小修复与记录含义

复用原Flow callback和分析目录，无新依赖、资料库、调度器或全局依赖图。

1. 新分析保存确切`context-input.json`，报告中的`context_revision`绑定实际prompt。重新从排序后的JSON拼prompt可能改变序列化顺序，不能替代实际输入；历史缺少此证据时仍走原保守路径。
2. 仅对未绑定worker、已完成分析、同岗位/同配置的来源更新尝试复用。核验原报告等于原artifact、原来源快照自摘要、原输入配置、确切prompt摘要；前后prompt及实际有效来源（含隐藏引文定位）必须相同。JD、配置或被消费内容变化均不复用。
3. 创建独立的**结果复用采用记录**和当前来源快照，`reused_from`指向旧分析及其摘要，明确`model_called=false`。score、requirements、选材和原model信息保持；当前coverage重新记录。不复制旧model-result冒充新执行，不改旧报告/快照/历史。
4. Flow追加注明reuse的adopted artifact，沿用原模型attempt；新的`analysis_id`是采用记录ID，不是新模型计算。材料仍按完整当前来源失效/重检，未宣布原PDF无关或自动复用。
5. 已确认硬条件只在原确认有效、对应事实依据未变时继承，保留原确认和`inherited_from`来源。依据变化不继承，不借旧确认放行。
6. 写入前绑定同次sources与resolved输入，写入后再次核验当前输入。错误或写失败保留旧Flow和原件，不fallback模型。未知生成/导出、pending准备及已有worker保护先于本路径。

## RED/GREEN与验证

- 原省略来源回归先RED后GREEN；随后有效硬条件确认因新采用ID失配的[RED](clarification-red.log)被修复，[GREEN](regression-clarification-green.log)保留。事实依据改变的反例不继承确认。
- [7项护栏](guards-consumed.log)：消费来源改变、JD/CLI配置改变、原context/来源快照损坏、新采用记录写失败、重复更新及冷Flow重开。各组原日志为`guards-*.log`；只读/写失败不变更旧记录，不调用模型。
- 首个受影响集合[191通过/2失败](affected-first.log)：旧注入analyzer只有报告没有原快照。修复为缺新context证据的旧报告先保守退出复用，不要求补造历史证据；[后继193通过](affected-second.log)。旧失败未改写。
- [最终受影响200通过](affected.log)覆盖新10项及分析、Flow、联系/职业影响、Single binding和解释接口；[XML](affected.xml)。其中新测试fixture导入排序随后仅作Ruff规范化，最终冻结的默认回归会再次覆盖它。
- 独立只读审查[记录](audit/review.json)确认同次来源观察竞态应保护；[独立探针](audit/test_adoption_snapshot_race.py)2项通过，捕获来源与保存结果后注入不一致均拒绝采用，原`flow.json`字节不变。未运行App或旧矩阵。
- [Ruff](ruff-final.log)、[格式](format-final.log)通过。第一次导入排序失败及修正日志保留。无debug生产日志遗留。

共享Flow/采用路径改变，因此对[冻结825输入](frozen-inputs.json)完成一次默认离线回归：**4672 passed、2 skipped、572 deselected，969.82秒，exit0**。[原日志](full.log)、[XML](full.xml)、[结果/跳过原因](full-result.json)、[原命令](full-command.json)及[825输入读后快照](full-inputs-after.json)均保留；运行前后完全一致。2项跳过仍为显式opt-in性能benchmark，不计通过。默认选中包含本轮10个节点及30已有startup回归，旧安装、Chrome/TCC、Submit证明矩阵不重跑。

全套后仅将新增测试中的临时信息库显式绑定到临时目录内不存在的legacy profile，避免将来测试环境读取home旧档；此次全套时home旧档本来不存在。该[单一fixture差异](post-full-test-isolation.diff)不改生产代码，[对应节点1通过](post-full-test-isolation.log)，Ruff/格式再次通过。未因这个测试隔离参数重跑全套；全套证据严格对应其825输入，当前生产字节与该冻结完全相同。

## 保留边界

- **材料/PDF单独判断。** 分析省略的文档可能仍被完整材料模型消费，不能直接宣布PDF可复用。此切片仍使材料阶段pending并保留旧PDF/人工底稿/历史；没有生成、编译、上传真实材料。
- 已有worker绑定不进入此新复用路径，保留原页与原unknown/fill intent；不为这次修复接管、取消、重启或替换旧执行者。
- 历史报告没有确切prompt绑定时不自动迁移或补写证据。重要事实变化、JD/配置变化、原证据损坏仍保持原拒绝/重算边界。
- 冷重开验证限`ApplicationFlowService`；不声称安装App冷重开新测。原30/27/37安装和隔离结果只是原版本证据，本次源码未安装。
- 36保持原负责人和claimed，第9不因这一个切片整体勾满；更广材料/PDF影响、跨JD重要合并仍另判。34真实自然Submit闭环仍未验，真实申请暂停，最终Submit人工。

原源码/测试/文档保全于`before/`及[source-before.json](source-before.json)；[最终源码差异](final-source-delta.diff)仅3个生产模块与2个新测试文件；冻结前的[source-delta.diff](source-delta.diff)原样保留。票据与计划更新另见[metadata-delta.diff](metadata-delta.diff)。原两库私人事实、接受PDF、正式unknown结果和fill intent未读写或重复确认。

最终票据/历史/输入读回见[verification.json](verification.json)。
