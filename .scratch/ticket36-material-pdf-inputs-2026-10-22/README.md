# 36第9项：省略来源更正的材料/PDF实际输入核对

2026-10-22，Europe/Zurich。范围仅限上一轮合成 `profile.location: Ruby → Rust` 更正。复用[分析等价及修复证据](../ticket36-omitted-source-2026-10-22/README.md)，不重跑旧矩阵。**结论：材料输入变化，未复现明确的无关重生成；本轮不改生产代码。36继续claimed，第9仍部分满足。**

## 有界结果

[公开入口探针](test_material_pdf_inputs.py)复用现有fixture，经 `generate_for_task → generate_full_latex → _model` 的真实构造与128000字节上限；没有替换材料builder、删文档、降低上限或截短原大贡献。模型/编译只在缩小对照初始化时使用固定合成返回，不访问provider或本机编译器。

| 层次 | 实测 | 含义 |
| --- | --- | --- |
| 分析 | 来源更正后复用原结果，未新增分析调用 | 沿用上一轮结论，不重跑分析证明矩阵 |
| 原样完整材料 | 两边486355字节，prompt SHA不同；identity与原profile文档分别明确包含Ruby/Rust | 被分析省略不等于被材料省略，材料输入并非不变 |
| 原样材料运行 | 两边均`resume_latex_context_too_large`，`model_started=false` | 均在128000字节上限处停止；材料模型、PDF编译、材料/PDF产出均0 |
| 缩小对照：页眉打印地点 | retained更新零模型调用；Identity进入核对队列，新的草稿不再输出该未解决组，归档不同 | 此为相关内容与待核对边界，不能采用旧地点或把结果当完整可用材料 |
| 缩小对照：页眉未打印地点 | retained更新零模型调用；LaTeX归档与编译配置相同，无核对队列 | 证明此对照的物理编译输入相同；未执行后续Flow新导出，不宣称已证明无关重编译 |
| 两种缩小对照的旧PDF | 原源归档、PDF、manifest及全部旧版本文件字节保留；更正后新增编译调用0 | 原件可保留查看，不自动证明更正后当前采用关系有效 |
| 旧draft搭配当前新inputs | `resume_inputs_stale`，新导出目录未创建 | 拒绝发生在编译前，不修改旧接受或虚构新接受 |

[最终运行日志](bounded-success.log)：**3 passed in 1.28s**；[XML](bounded-final.xml)。重叠和中间运行不累加。本轮只有三个有界节点，不重跑完整默认离线、安装/TCC/worker/Submit矩阵；上一轮4672通过/2 skip仅为其原冻结版本证据。

原样前后真实构造数据及预检回执见 [observations/](observations/)，包括 `exact-before/after-input.json`、`model-input.json`、`model-result.json`、`project-preflight.json` 及[汇总](observations/exact-summary.json)。prompt摘要由真实模型边界预检写入；文件保留完整合成上下文，不凭摘要差异猜事实内容。两份`model-input.json`中identity.text和document_context的location都已逐项断言，故差异不只是analysis采用ID或revision。

两个缩小对照：[打印地点](observations/retained-printed.json)、[未打印地点](observations/retained-unprinted.json)。它们用于单独识别PDF输入与事实有效性，**不是原大场景已生成出可用简历或PDF的证明**。固定合成compiler只证明调用/归档边界，不证明真实编译、PDF视觉质量或人工接受。

## 失败及夹具适配

初次缺少tests导入路径，随后探针错误地未传Flow所用的材料联系人revision投影、将可缺source_kind当必填、将fake runner的version+exec调用误按绝对1计数；这些日志分别保留在 `bounded-first/second/third/fourth/final.log`、`binding-diagnostic.log`、`bounded-projected-library.log`、`bounded-result.log`。最初对打印地点的“新源仍相同”假设也被实际输出否定，现明确记录归档变化与核对项。它们是探针构造或断言假设失败，不是产品bug RED/GREEN，不据此改生产。

最终传入真实`material_information_library(application, library)`投影，保留所有生产guard；合成分析输出边界把提取岗位名与输入保持一致（无输入裁剪）。相同来源、JD、配置和材料底稿用于前后比较。全部新材料输入与对照均在临时合成工作区，未读取、复制或更改私人职业库/信息库、真实PDF或ATS。

## 接受记录和边界

复用[材料15已接受源/PDF保存绑定](../material15-accepted-binding-2026-10-19/README.md)及[真实批次结案](../material15-real-batch-2026-10-19/README.md)记录：精确源/PDF已接受且采用无重新编译，原未知尝试继续保留。此次仅读系统库中的公共结论，未重读私人PDF或要求用户重复确认。原接受不被撤销，也不扩成更正后新事实、新源或新岗位的接受。技术`stale`不能据此要求同版PDF重新接受。

本轮没有复现实际Flow里的无关重编译，故不修缓存、不放宽source/analysis/task绑定，不新增采用接口或批准流程。现存retained路径已可避免缩小对照中的模型重生成，不能把单独调用新export视为自动重复故障。

**真正未覆盖的最小边界：** 对未打印location、retained归档与编译配置确实相同的情况，仍须在实际Flow继续链核对是否会创建不必要的新export；若复现，再在核验原PDF、当前事实、接受父链及未知结果保护后处理同任务复用。本轮未执行这个新的完整Flow导出切片，不声称它一定有bug或已完成。更广JD变化/人工冲突合并仍由原第9项持有。

独立critical agent只读审核最终代码和证据，未再跑测试，认可上述分层和不修改生产的结论。主App未更新/启动。未知结果、非空fill intent、原worker/page与真实申请暂停均保持；真实填写、上传和Submit为0。

## 最终读回

[verification.json](verification.json)登记输入字节、票据metadata、旧接受/分析证据哈希与差异。旧文件不改写；只追加本轮记录及36/地图/统一计划的当前结论。
