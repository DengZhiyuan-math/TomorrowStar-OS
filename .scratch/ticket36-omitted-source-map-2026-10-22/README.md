# 36号票：人工省略后的来源更新与影响映射 — 2026-10-22

按用户授权补齐本切片，保留现有改动、人工内容、负责人和接受历史。以实际TeX核对内容；成功编译即默认PDF可用，不要求单独PDF审核。App未更新或启动，真实申请继续暂停。

## 已实现

- 人工省略组不再打印后，后继稿仍保留最小来源ID/名称关联，仅用于判断变化是否已有来源覆盖。该记录不含旧正文/行段，不进入模型待合并分组，不恢复删除内容。
- 采用组的影响判断仍依据其当前来源；省略组与采用组共享来源时，只更新受影响的采用组。模型对无关组的改写仍忽略。
- 当前人工来源改绑覆盖旧关联，重新纳入后重新按采用组判断。多轮来源事实更正、原始上下文变化和省略来源删除均保留人工TeX。
- 复用已有不可变父稿谱系，记录v2规则并核验最小映射。旧v1稿缺少映射时，从已核验的实际父谱系恢复来源关联，不恢复正文。当前映射缺失/伪造和历史父稿损坏均拒绝。
- 未映射的新上下文、采用来源缺失、未捕获的外部修改等真实不确定性仍保留原稿并停止。此次没有放宽未知来源保护或建立通用依赖图。

## 验证与失败历史

本轮新增17项回归（16项存储/生成器，1项公开Flow）。公开Flow先保存人工措辞和删除完整组，再刷新JD、连续更正省略来源并导出；各次TeX逐字一致，模型没有额外材料调用，旧稿不变。共享来源、人工改绑、重新纳入、删除、原始上下文、合法未知profile上下文、旧谱系与篡改由生成器回归覆盖。

- [生成器RED](omitted-red.log)复现首次刷新丢失省略关联后，后续来源更新被误判未映射；[首条GREEN](omitted-green.log)通过。
- [公开Flow RED](flow-01-red.log)复现JD刷新后省略来源更新失败；[首条GREEN](flow-01-green-first.log)通过。
- [扩展初次运行](omitted-expanded.log)中一个未知profile测试使用不合法字段，未得到有效profile上下文；后继改为合法research links fixture，不放宽生产保护。
- 最终[生成器16项](omitted-final-regression.log)通过；先前[相关5模块58项](omitted-module-regression.log)通过，集合重叠不累加。
- [独立探针](independent-probes.py)及[日志](independent-probes.log)：7项通过，覆盖多轮更新、共享来源、改绑、旧谱系及映射损坏。7层读取次数为18、26、34、42、50、58、66，保持线性增长。
- [受影响集合初次命令](affected.log)因误写不存在的测试文件名而退出4，无测试执行；修正命令后另存[最终受影响日志](affected-v2.log)和[XML](affected-v2.xml)。不覆盖旧失败。

完整默认测试与最终静态、冻结输入及工单读回结果在结束后追加本记录。所有测试使用合成临时工作区和假模型/编译器；不等同于真实材料质量、安装或ATS接受。

## 工单与剩余边界

36保留claimed、原负责人01a15ab3/root及依赖，第9项其余较广影响映射仍按原票保留部分，不据本切片关闭整票。此次只追加原票正文，不改状态、勾选、负责人或旧记录。所有其他工单保持。

旧PDF与接受记录保留；本切片不扩展PDF缓存/版本确认。未操作真实职业资料、模型提供方、邮箱、ATS、上传或Submit。未知结果及原fill intent不改。


## 冻结前最终核对

最终受影响集合 **266 passed，66.77秒，exit0**，包含新增17项及运行身份、readiness和安装写入准入的源码回归。Ruff通过，457个文件格式检查通过，git diff检查通过；分别见[静态日志](ruff-final.log)、[格式日志](format-final.log)、[差异日志](git-diff-final.log)。首次写错文件名的退出4没有执行测试，保留在affected.log。

独立最终复审未发现阻断问题，[9项探针](independent-final-probes.py)通过（[日志](independent-final-probes.log)，4.33秒），包含分组后继稿伪造映射并重算integrity仍拒绝。[运行身份探针](independent-identity.log)确认controller/preparation身份有效，新helper和分组校验代码变化会改变指纹，恢复后身份一致。新v2读取保持线性；人工构造的多层旧v1首次迁移有二次回溯成本，迁移到v2后停止，未为此扩大实现。

[运行前冻结](inputs-frozen.json)包含856项，[本轮差异清单](delta-files.json)和[补丁](task-delta.patch)只列相对本轮开始的变化，保留所有更早未提交工作。完整默认命令保留默认marker和原时限，见[命令](full-run-command.txt)。


## 最终读回

完整默认离线回归 **4753 passed、2 skipped、572 deselected，1078.30秒，exit0**；XML记录0 failures、0 errors。见[原日志](full-default.log)、[XML](full-default.xml)及[结果](full-result.json)。两项跳过均为既有显式opt-in本地渲染/性能benchmark，未计为通过；默认marker与原时限保持。

[运行后856项输入](inputs-after.json)与[冻结清单](inputs-frozen.json)逐份相同，源码、测试及文档在完整运行期间未变。[最终核对](verification.json)确认128张工单metadata完全相同，其他127张票字节不变，36只追加本轮证据且保留原字节前缀。HEAD仍为e4a26d0c24311d014d478f7f92e58a88e6709b4b，既有未提交改动保留，无提交或推送。

本轮指定切片已完成。36仍claimed、Assignee=01a15ab3/root，未宣称第9项全部完成；无法定位的新上下文等较广范围仍保留原保护。以TeX实际内容和人工修改为准，仅更新受影响部分。App未更新或启动，真实申请继续暂停。
