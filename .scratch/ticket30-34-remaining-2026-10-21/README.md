# 30/34剩余验收与Continue恢复后继

2026-10-21，Europe/Zurich。开始时核对814项登记输入与G1/G2的4632/2完整默认基线完全一致。旧候选和全部失败收据不覆盖；[本轮逐项验收核对](acceptance.md)区分源码、组合、安装和真实接受。

## 实际工程

1. 修复缺申请国家的Continue死路。此前固定邮件入口已完成分析、简历和PDF，却未保存可恢复等待，Continue返回409 pipeline_exists。现在复用既有wait_reason/resume_status、start/continue和同一Flow任务；未补事实时200回到原等待，既有材料不重做。公开PATCH明确地点后，一次Continue通过Flow.update_inputs→analysis重新采用真实变化的JD输入，旧PDF字节和历史保留；旧材料不冒称仍适用。没有新增country字段、信息库协议、审批按钮或状态库，国家未知时的行为没有放宽。

   旧记录兼容也已补齐：没有两个恢复标记的旧材料等待，重开后直接继续或先PATCH地点再继续均走同一恢复接口；显式其他等待或只有部分标记不冒充该历史状态。
2. 补齐真实Flow参与的公开HTTP组合：Runner收到模拟人工提交的传输/页面事实后，success才选择下一推荐；rejected/unknown保持当前岗和原页，不重放。另验证skip→选中第二来源→返回原岗，PDF、未知intent及原Page保持。复用现有backend/http_backend/Intake/Pipeline/Flow/Worker/Runner，只模拟IO，不复制调度或材料实现。

本轮只改3个源码/测试文件：[最终差异](source-delta-v2.json)。没有改生产Flow、Runner、Gmail或最终Submit守卫。组合只到下一来源被选择，未宣称第二worker已填写上传；也未宣称自然人工Submit闭环。

## 证据与结果

- [国家等待切片](country/)：真实隔离server --synthetic-mail的RED/GREEN。首切片150通过；旧记录重开2个RED均为409，兼容后2通过，最终含明确其他等待/部分标记负例的相关回归154通过；包括旧材料base与语言等待恢复。地点PATCH测试在重新分析后停止backend，没有启动浏览器。
- `manual-result-first.log`：原始测试错误地要求完成和下一来源选择分属不同tick，实际同tick已正确选择；修正测试预期，没有改生产逻辑。`manual-result-green.log`为success通过，`manual-result-boundaries.log`为success/rejected/unknown共3通过。
- `skip-return-first.log`新增组合第一次即通过；如实记录已有实现可复用，没有为制造RED改业务。
- 统一最终受影响：309 passed、1 deselected（105.39s），814项输入无变化。完整默认full-v1因补旧country等待记录兼容主动中断（exit2，输入未变化），部分日志与中断说明保留；最终full-v2为4641 passed、2 skipped、562 deselected，905.00s；814项输入前后不变。两项skip仍是既有显式opt-in PDF性能/渲染benchmark，不宣称性能已验收；不借用上一轮4632数字覆盖新源码。
- Ruff检查和格式通过。最终源码候选v2为425项：`preparation-candidate-a569cf8dd0bb73d33b216ed88532082045f1b75656964c3f350f1904d7d91e23`；原v1保留为兼容修复前的阶段候选。最终候选不是安装包或独立完整测试checkout。

## 未完成与集中确认

详细8+9项见[验收表](acceptance.md)。30仍有唯一App实际加载/原生组合和旧worker交接；34仍有真实邮件到人工Submit结果及下一岗闭环。39的重复状态副本收敛与40/41的共享/退役清单继续由原专业票持有，不以本轮组合通过宣称完成。

现在无需用户为本轮源码逐步确认。用户后续需要决定何时恢复两类已暂停工作：唯一主App更新及安装验收；真实推荐/填写上传体验验证。当前均继续暂停。本轮未构建、更新、启动App，未读写真实配置、邮箱或ATS；最终Submit始终人工。30/34负责人、依赖、全部旧验收和历史保持，不关闭整票。

[最终候选清单](source-candidate-v2/manifest.json)、[候选读回](candidate-verify-v2.json)、[最终受影响原日志](affected-v2.log)、[完整默认原日志](full-v2.log)。

[共享/兼容/退役调用及39剩余位置](calls-and-remaining.md)。

[最终读回及剩余事项](final-readback.json)。
