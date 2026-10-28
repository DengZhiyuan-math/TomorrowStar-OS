# 36号票：TeX资料/JD按影响更新 — 2026-10-22

以TeX实际内容、固定学历和人工修改为准，只更新受影响部分。成功编译即默认PDF可用，无单独PDF审核或确认。本轮只修改源码与合成测试，不更新或启动App，真实申请继续暂停；旧接受记录保持。

## 已实现

- 更新基础从“仅有明确人工标记的旧稿”扩为本任务最新已采用完整TeX；不重写无关正文。联系信息更正直接更新页首，无需材料模型；未打印资料字段更正可复用原正文。
- 新稿保存实际岗位上下文，并核验它与分析绑定相同。JD新增/删除要求及公司、职位、地点变化沿用现有一次生成调用，模型按实际TeX选受影响组。职业资料影响与JD影响取并集；只采用这些组，其余正文逐字保持。
- 不允许模型重新分组、错误索引、重复索引或更换来源引用来绕过更新边界。旧稿缺少可核验原JD正文时保留原稿并报明确错误。
- 更新后可继续人工修改并导出；本次采用的基础绑定保持严格校验。重要事实/责任冲突在导出前暂停当前岗；修正后一次Continue更新输入，必要时重分析，同一请求不重放，不启动下一岗。
- 待核对候选之后若又有人工修改，保留当前TeX并停止；未捕获的外部源编辑同样不被覆盖。仅marker准备不会误判成新增人工正文。

## 回归与复核

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| 受影响9模块 | 225 passed，67.66秒 | [日志](affected-final.log) |
| 新Pipeline公开编排 | 4 passed，包含在225项中 | [日志](pipeline-tex-recovery-tests.log) |
| 完整默认离线 | **4713 passed、2 skipped、572 deselected，984.13秒，exit0** | [日志](full-default.log)、[XML](full-default.xml)、[结果](full-result.json)、[命令](full-run-command.txt) |
| 静态检查 | Ruff、格式、git diff检查通过 | [Ruff](ruff-check-final.log)、[格式](ruff-format-final.log)、[diff](git-diff-check-final.log) |
| 独立只读复核 | 三个确证问题修复/保护后通过探针；最终小差异未见新增确证问题 | [范围与证据限度](independent-review.json)、[探针源](independent-probes/) |

集合重叠，不相加。测试均为临时合成工作区及假模型/编译器，不能扩为真实材料质量、App安装或ATS接受。完整默认运行不覆盖marker选择。

## 先红后绿与失败历史

- [未打印资料更正RED](flow-retention-red.log)：未编辑但已采用的完整TeX仍调用第二次材料模型；现在保留。
- [JD分组更新RED](merge-01-red.log)：新增JD要求没有更新受影响组；后续merge-*保留各阶段模型边界、旧JD完整性及错误输入测试。
- [重要事实冲突RED](flow-conflict-red.log)：待核对候选仍能进入导出；现在停等。
- [联系信息RED](flow-contact-red.log)：信息库修正丢失无关人工措辞；现在无额外模型调用并保留正文。
- [再次人工编辑RED](flow-repeat-edit-red.log)：JD更新后编辑导出出现flow_draft_mismatch；现在保留本次基础绑定。
- affected-first.log的2项失败属于旧测试仍要求调用模型；更新为直接TeX头部替换，并保留导出、历史、Worker绑定检查。flow-jd-green.log名字不代表通过，原6项失败保留：5项比较了带marker元数据而非实际TeX，1项是真实冲突未停等。flow-final-first.log的单失败是测试替身先改成大写后又按小写替换所致，后续修正测试替身。旧日志均未改写。

## 未完范围与下一步

36第9项仍部分，Status=claimed、Assignee=01a15ab3/root、原依赖和其他勾选不变。本轮覆盖已有完整TeX的可映射资料/JD更新。含未决组且之后又有人工修改的自动合并尚未实现，当前保留源并停止；来源新增/缺失/上下文无法映射到现有组、旧JD正文缺失等场景也保守保留原稿。后继应针对具体受影响组补齐恢复，不能用整稿重生成覆盖用户内容。没有另建资料库、生成器、PDF缓存系统或审批对象。

[原始输入](inputs-before.json)、[冻结输入](inputs-frozen.json)、[本轮差异](delta-files.json)、[补丁](task-delta.patch)、[原件](before/)均保留。原128张票metadata读前读后完全相同；36只追加正文，原字节作为前缀保留，其他票不改。850份冻结输入包括3个新增测试，并比基线清单额外登记两份.DS_Store元数据；这两份元数据不属于源码交付。

## 最终读回

[850份运行后输入](inputs-after.json)与冻结清单逐份相同。完整默认测试4713通过、0失败、0错误；2项跳过均是明确opt-in的完整渲染/性能benchmark，未计入通过。572项由默认marker排除，未更改选择规则。[最终核对](verification.json)记录准确HEAD、输入及操作边界；[工单读回](tickets-readback.json)确认127张票字节不变、36原字节保留且仅追加本轮正文，128张票metadata完全一致。所有原改动保留，无源码删除或新依赖；App未更新或启动，真实申请继续暂停。
