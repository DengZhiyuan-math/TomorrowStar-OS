# 申请 worker 计量

当前产品流程以[单岗位规范](single-job-flow.md)为准，实现调整见
[开发计划](development-plan.md)。先线性跑通逐岗流程，再研究并发；计量不建立调度或审批流程。

计量合同由[确定效率基线、人工干预与模型成本的测量口径](../.scratch/application-worker-next-stage/issues/05-measurement-contract.md)定案。
实施与基线见[2026-10-13 记录](../.scratch/worker-measurement-baseline-2026-10-13/README.md)。

当前 checkout 在显式私人 worker 目录追加 `measurements.jsonl`。
简历生成与 worker 使用同一测量目录；页面通过不含个人信息的 measurement_id 关联准备过程。
独立使用 ApplicationResumeStore 时，记录默认保存在其既有私人目录。
使用现有 checkout 启动器即可记录。计量不新增依赖、后台监控服务或模型调用。

## 记录和汇总

[MeasurementLog](../src/career_evidence_graph/worker_measurement.py)提供 `read()` 和 `summary()`。
已有 WorkerStore 可通过 `store.measurements.summary()` 取得汇总。
汇总含私人关联标识，应留在私人目录；不得直接公开真实记录。

- UTC 用于关联；同一时钟的单调时间用于耗时。跨 run / clock 总耗时记 unknown。
- 初次等待开始属于正常用户等待；共享初始化在岗位时间线上属于排队，初始化成本另记一次。
- 显式 pause、运行中断、未知时段和自动步骤分开；嵌套自动步骤不重复累计。
- `ready` 要求完整可人工复核且同步完成。页面先就绪、同步失败和未结 intent 保留各自事实。
- 既有记录可按等价问题分组统计；实际用户操作另计。统计分组不要求集中处理其他
  岗位，当前岗的重要问题仍须当场等待。人工主动时长默认 unknown。
- 模型入口调用与 synthetic 替身分开。服务请求数和费用不能从入口调用推定；usage / fee 缺失保持 unknown。
- Cua 入口尝试与 `acknowledged / not_sent / unknown` 分开。收到 RPC 回执不等于业务动作已核验。
- 原有 intent 的 `upload` 名称不证明远程上传；须联合已有 select_file、传输和附件挂接观察判断结果等级。

计量写入失败、损坏行和无法关联的记录会使计量不完整。
有效的已开始过程及原始坏行仍保留。计量不清除业务 intent、不授权重传，也不改变业务检查点的权力。
`measurement_incomplete` 是诊断字段，不是新的业务状态。
重要事实缺失、实际冲突或结果不明时，当前岗位的等待单独计量；只有用户选择跳过
才进入下一岗。等待期间可收录新推荐邮件，不把处理其他岗位算作已授权的后台进度。
不设全轮 20 分钟、邮件数或岗位数的硬上限。超时用于识别某次操作无进展，
耗时、记录缺失、成本未知和版本诊断本身不触发新的用户批准。

## 验证边界

合成夹具可验证计时、分组与守卫。它不能建立真实 ATS 覆盖、模型费用或用户真实操作时长。
模型替身延迟不是模型推理延迟。不同浏览器和控件条件的结果分别报告，不做速度排名。
真实运行原始答案、JD、路径、prompt、截图、附件和模型正文不进入公开计量。
用户、雇主和原申请记录仍按[数据边界](data-boundaries.md)管理。

本轮修改交付在 checkout 中。已安装应用和现有运行实例的来源以其自身启动记录为准。
