# 36号票：待核对稿后续人工修改的自动合并 — 2026-10-22

用户授权补齐本项，保留既有改动、负责人和接受记录。以实际TeX、人工修改及固定学历为准；成功编译即默认PDF可用，无单独PDF审核。App不更新或启动，真实申请继续暂停。

## 实现范围

- 最新已保存人工稿成为更新基础，取消因存在后续人工修改而整体停止的旧保护；尚未捕获的外部源改动仍阻止覆盖。
- 当前TeX正文、前导、结尾与现有分组顺序保留。仅将最新待核对候选按确定的原分组锚点补入合成输入；不恢复人工删除或省略的组。
- 合成输入仅供模型和来源检查，实际base_checkpoint与原始归档仍绑定最新人工稿；输出记录不可变父稿ID、摘要及合并规则。读取时从该父稿重建并核验，不能仅凭新哈希绕过来源。
- 重评范围为待核对组、资料变化组、JD变化组的并集；范围外模型改写忽略。仍有真实冲突的组留在verification_queue，不进入导出正文，当前岗继续等待。
- 联系方式页首恢复后可再次编辑；固定学历继续使用历史接受和来源记录，消费侧定位不改写历史接受字段。恢复后的再次JD更新也保留该谱系。
- 单次递归读取仅复用已经成功验证的同一store/id/sha；未完成节点不得复用，最外读取结束清空，后续独立读取重新核验。标准库ContextVar隔离并发，不新增持久缓存。

## 验证记录

核心受影响285 passed（身份兼容修复前）、3 deselected，220.05秒（affected-final.log）；此前284通过属于修复递归读取前版本。静态Ruff、455文件格式及差异检查通过。独立7项探针通过（review-final-seven-probes.log），含新顶层读取对3类历史损坏重新拒绝。最终身份兼容及核心重叠回归119 passed，22.75秒。完整默认v1主动中止保留，v2完整通过，准确结果见下方最终读回。集合重叠不累加，所有运行使用临时合成工作区与假模型/编译器；不扩为真实材料质量、安装或ATS接受。

## 失败历史

- flow-01-red.log：旧保护在开始材料更新前直接拒绝后续人工稿；flow-01-green-first.log通过，含恢复原位置、保留人工措辞及导出。
- generator-red.log：直接采用待核对稿会遗漏不在TeX中的候选；后继生成器回归覆盖只重评影响并集。
- header-red.log、review-header-probe-red.log：页首恢复后再次prepare被旧实际基线行段误挡；header-green-first.log与独立探针修复后通过。
- flow-modes-first.log中两个失败是测试把仅preparation模式提供的group_edit/capture接口用于普通automatic模式；未据此扩产品接口。对应保存/组编辑/capture行为由各自公开有效入口覆盖，旧失败原样保留。
- 生成器删除/重排测试的首次失败是留下空marker块，被编辑器正确拒绝；改为删除完整组块。所有旧失败日志保留。
- review-retained-probe-red.log：固定学历带marker的实际内容行段和组行段不一致；消费侧精确定位修复，不改历史receipt。review-retained-refresh-red.log：恢复后再次JD更新时旧receipt压缩行段不匹配；后继延续已有谱系，首次未绑定生成仍严格。
- lineage-cost-red.log：连续3轮后单次读取21→70→217→658。修复后lineage-green-first.log为18→35→50→65，22项回归通过；历史损坏仍拒绝。此处只复用一次递归读取中已经验证的不可变记录。

## 工单与边界

36继续claimed、原Assignee=01a15ab3/root及依赖保持，只追加本轮正文证据，不重写原勾选或历史。本轮补齐待核对稿后续人工修改的自动合并；尚未保存/捕获的外部修改、来源缺失或无法定位等真实不确定性继续保留原稿并等待，不用整稿重生成覆盖。较广来源映射的其余第9项范围仍按原票保留，不据此关闭整票。

## 统一结果索引

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| 核心受影响集合（身份修复前） | 285 passed、3 deselected，220.05秒 | [日志](affected-final.log) |
| 本轮新增回归 | 23项，分别包含在各受影响集合中 | [生成器](../../tests/test_pending_tex_merge.py)、[公开Flow](../../tests/test_flow_pending_tex_merge.py)、[页首后续编辑](../../tests/test_pending_tex_header.py)、[多轮读取](../../tests/test_pending_tex_lineage.py) |
| 独立探针 | 7 passed，5.18秒 | [原始日志](review-final-seven-probes.log)、[复核范围](independent-review.json) |
| 静态检查 | Ruff、455文件格式及diff检查通过 | [Ruff](ruff-verified.log)、[格式](format-verified.log)、[diff](git-diff-check-verified.log) |
| 身份兼容及核心重叠回归 | 119 passed，22.75秒 | [日志](runtime-scope-green.log)、[新增身份回归](../../tests/test_loaded_runtime_identity.py) |
| 完整默认v1 | 主动中止，3181已执行/11失败，exit130 | [原日志](full-default.log)、[XML](full-default.xml)、[输入核对及结果](full-v1-result.json) |
| 完整默认v2 | **4736 passed、2 skipped、572 deselected，1471.77秒，exit0** | [日志](full-default-v2.log)、[XML](full-default-v2.xml)、[结果](full-result-v2.json)、[命令](full-run-command-v2.txt) |

[本轮前输入](inputs-before.json)、[最终v2冻结输入](inputs-frozen-v2.json)、[原件](before/)、[最终差异清单](delta-files-v2.json)、[最终补丁](task-delta-v2.patch)均保留。[工单读回](tickets-readback.json)确认127张票字节不变，36只追加正文并保留原字节前缀；128张metadata完全相同。

本轮验证了人工省略内容在合并时不恢复；连续更新已省略来源时的更广自动引用映射仍属36第9项后继范围，未据本次测试宣布完成。来源或插入锚点不能核验时保留当前TeX，不能以旧完整稿覆盖。

## 统一验证发现的运行身份兼容问题

完整默认v1发现11项失败，主动中止exit130；3181个已执行节点，854项输入运行前后相同。独立身份模块复现12失败/6通过；原因是新增ContextVar被大写全局常量扫描，无法归一化而使身份为None。新增公开身份回归先失败（runtime-scope-red.log），随后只在既有loaded_code._RUNTIME_VALUES精确排除application_resume._DRAFT_VALIDATION临时状态，未改_normalize、opaque-default或实际方法/策略指纹。119项相关通过；独立20项及子进程scope/方法替换探针通过，见review-runtime-identity-final.log和review-runtime-fingerprint-probe.log。

原v1冻结清单、补丁和日志保留；v2使用单独冻结清单与日志，不覆盖旧结果。

## 最终读回

完整默认v2：4736 passed、2 skipped、572 deselected，1471.77秒，exit0；0 failures、0 errors。2项跳过均为显式opt-in的实际本地渲染/性能benchmark，未计通过；默认marker选择未覆盖。[854项运行后输入](inputs-after-v2.json)与冻结v2逐份相同，源码和测试在运行期间未改。

[最终核对](verification.json)确认原127张工单字节不变、36原字节前缀保留且只追加正文、128张metadata与本轮前完全相同。36保持claimed和原负责人，不替用户关闭整票或接受真实材料；较广来源映射范围继续保留。现有改动及旧接受记录不回退。App未更新或启动，真实申请继续暂停。

最终静态结果为[ruff-final-v2.log](ruff-final-v2.log)、[format-final-v2.log](format-final-v2.log)、[git-diff-final-v2.log](git-diff-final-v2.log)。早期静态及完整默认失败原样保留，集合有重叠，不相加。
