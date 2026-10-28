# 36号票：两条主线核对与必要修复 — 2026-10-22

本轮只执行用户确认的S1、S2，不追加36目标。保留现有改动、原负责人01a15ab3/root、claimed状态、依赖和历史记录。App不更新或启动，真实申请继续暂停。

## S1：本次修订与两库、其他独立申请隔离

核对通过，未发现需要改生产代码的问题。新增公开入口回归覆盖：A保存人工措辞/省略，两库和原底稿字节不变；B使用公开Store从两库及原底稿独立生成，不带入A的局部修订或申请专属邮箱；A继续导出仍保留实际人工TeX，旧稿和旧导出不变。

首次[S1-first.log](S1-first.log)1 passed、1.45秒，格式后[S1-formatted.log](S1-formatted.log)1 passed、1.76秒。B没有启动第二个活动Flow；该核对不禁止已有适用材料的显式复用，也不声称完整第二岗调度已重新验收。

## S2：职业库明确更正学历后只更新相应内容

公开Flow首条复现失败：[S2-red.log](S2-red.log)。经CareerCatalog.update_evidence明确更正2020→2021后，系统仍把学历送入education_verification_required，重复要求确认已经明确的更正。首个修复后继续编辑/导出通过，见[S2-green-edit-export-v2.log](S2-green-edit-export-v2.log)。

修复仅根据已有、已应用的用户库更正及相应历史，对实际TeX中可唯一定位的旧学历字段作确定替换。当前纪录、旧稿来源和更正记录均需核验；历史稿与旧接受记录不改。未变学历和模型自行改写仍使用原固定保护，未知或不一致来源继续核对。无法唯一定位的特殊版式保留原稿，不将支持任意TeX格式追加成本票目标。

回归覆盖常规学历字段（包含在读/预计而非已获学位状态）、更正后再人工编辑及导出、模型乱改、无明确更正链或损坏记录继续阻止自动采用、同组两项学历只更新一项且旧接受manifest/receipt/captures保持、连续更正和冻结记录损坏。准确最终数量与独立复审结果另行追加，不累加重叠集合。

## 验证与保全

当前仅使用合成临时工作区、假模型和编译器，未调用实际提供方或真实申请。成功编译按现行规则视为PDF可用，不添加PDF内容/视觉审核或确认。旧失败日志、测试夹具修正及每轮结果均保留，不覆盖失败历史。

本轮开始保存858项输入及原文件、128张票据和状态。最终差异、冻结清单、完整默认与工单读回在检查结束后追加。两条主线完成后不再自动扩写新的分组、生成器、PDF或JD维护目标。


## 独立复核与失败分类

独立最终[S2三项探针](independent-S2-probes.py)全部通过（[日志](review36-education-final-independent.log)，3.74秒）。覆盖普通流程连续两次更正、中间人工编辑后继续，以及已有接受材料的两凭证组在先人工编辑/未先编辑两种情况下连续更正；未变凭证、工作措辞和旧记录保持。

独立复现另保留[accepted首次RED](review36-education-accepted-red.log)、[accepted第二轮RED](review36-education-accepted-second-round.log)、[先人工编辑RED](review36-education-accepted-manual-first.log)。三者属于同一S2的旧学历/历史整稿绑定误拦截，不扩为新目标。[独立日志索引](independent-log-index.json)保留各轮过程。

S2-green-first.log仍因旧original与当前学历的二次匹配进入核对，后继S2-green.log修复。S2-green-edit-export.log首次发现后续编辑保护不认识合法更正，后继v2通过。S2-accepted-first.log中的一次失败是合成模型响应缺少已有上下文判断字段，保留原保护并修正fixture，不放宽模型协议。S2-related-final-v2.log末段发生源代码条件精简，属于非冻结过程结果；根任务在所有源码交回并格式化后另启统一affected，后者才作为稳定受影响证据。所有过程结果不覆盖，也不累加重叠通过数。


## 冻结前统一结果

新增15项长期回归：S1一项、S2十四项。统一稳定[受影响集合](affected.log) **555 passed，174.36秒，exit0**，包括两条主线、职业库更正/历史、学历来源复用、人工编辑与合并、旧接受记录及运行身份/readiness/写入准入。命令见[affected-command.json](affected-command.json)，结果见[XML](affected.xml)。

静态[Ruff](ruff-final.log)通过，[格式](format-final.log)461个文件通过，[差异检查](git-diff-final.log)通过。[860项冻结输入](inputs-frozen.json)、[本轮差异](delta-files.json)、[补丁](task-delta.patch)和[原文件](before/)保留；完整默认命令见[full-run-command.txt](full-run-command.txt)。检查期间不再改源码、测试、文档或票据正文。


## 最终结果与保全读回

完整默认离线回归 **4803 passed、2 skipped、572 deselected，1108.83秒，exit0**；XML确认0 failures、0 errors。见[原日志](full-default.log)、[XML](full-default.xml)及[结构化结果](full-result.json)。两项跳过均为既有显式opt-in本地渲染/性能benchmark，不计入通过；没有覆盖默认marker或调宽原时限。

[运行后860项输入](inputs-after.json)与[冻结清单](inputs-frozen.json)逐份相同。全套运行期间源码、测试、文档和票据正文没有变化。[最终核对](verification.json)确认128张工单metadata完全相同，其他127张票字节不变，36只追加本轮证据并完整保留原字节前缀。HEAD保持e4a26d0c24311d014d478f7f92e58a88e6709b4b，未提交/推送，既有未提交改动和负责人保持。

**两条主线均已完成本轮核对。** S1无需生产修复；S2明确学历更正的重复核对和历史绑定误拦截已修复，并有相应回归。仅在可核验、可唯一定位的字段范围自动更正；未知来源、损坏记录或无法唯一定位的特殊版式仍保留原稿核对。没有追加第三项工程目标，36仍claimed、Assignee=01a15ab3/root；App未更新或启动，真实申请继续暂停。
