# 确定效率基线、人工干预与模型成本的测量口径

Type: grilling
Label: wayfinder:grilling
Status: closed
Interaction: HITL
Assignee: root
Parent: [申请 worker 下一阶段：稳定性、普适性与效率决策地图](../map.md)
Blocked by: none

## Question

怎样分别衡量机器耗时、等待用户时间、人工干预次数和模型调用成本？哪些现有记录足够复用，哪些最小计量必须补齐，才能判断优化是否有效？

## Recommended default — pending decision

先采集基线，再优化。按筛选 / 资料读取、简历生成、PDF 导出、表单扫描、填值 / 保存、上传 / 挂接和记录同步分段计时。
用户等待时间单列。已确认答案不再重复询问；保存结果未知的人工核验不记成机器失败，也不从自动耗时中悄悄删除。
记录缓存命中、模型调用次数、可获得的 tokens / 实际费用和一次准备中的介入次数。费用不可获得时标记 unknown，不估成零。
小样本报告每例与范围；达到足够样本后才报告中位数和尾部耗时，不先承诺“提升 50%”。

## Evidence and assets

- [现有生成与缓存](../../../src/career_evidence_graph/application_resume.py)
- [现有轮询和状态展示](../../../src/career_evidence_graph/portal_static/worker.js)
- [当前测试日志](../../../validation/application-automation/2026-10-11/workflow-consolidation/README.md)：套件耗时不是单岗位耗时。

## Resolution requirements

确定统一计时起止、等待分类、失败 / 取消的保留方法和匿名可公开汇总。原始字段、答案、签名 URL 与 trace 保持私有。
给出最小字段表及基线测量方案。先复用当前 model-result、observations 和检查点，不引入监控平台。
计量可以在稳定性切片前开始；这不改变用户确认的优化实施顺序。

## Claim record

2026-10-13，Europe/Zurich：root 按用户指令领取本票，先核对现有记录并提出推荐方案。
本票保持 open；本轮不采集真实岗位基线、不运行模型或实施计量代码。

## Proposal comment

2026-10-13，root：已形成[效率基线、人工干预与模型成本 — 推荐方案](../assets/measurement-contract-proposal.md)。
推荐以请求准备到可人工复核且原记录同步完成为主终点；机器处理、排队、等待用户、暂停、中断与未观察时段分开。
复用现有 run/batch/intent、草稿缓存与 Codex 原始结果；补充单调时钟、状态时间线、介入分组和模型/工具用量记录。
主动人工时长和费用缺失均记 unknown，失败、取消和未结动作保留。首轮建议 16 个合成场景，零真实 ATS、零新真实模型调用。
本次只读核对公开源码并保存方案，没有实现或采样。本票保持 open，尚无 Resolution comment。

## Resolution comment

2026-10-13，用户明确指令：“按推荐方案定案这个 ticket，再实现最小计量并完成 16 个合成场景的基线采集，保持零真实 ATS、零新增真实模型调用。”

接受[推荐方案](../assets/measurement-contract-proposal.md)作为测量合同：完整可复核且记录同步完成为主终点；时间互斥分类，人工主动时间和费用缺失保持 unknown，失败、取消与未知结果保留。
本票的决定已完成，状态为 closed。随后实施与基线按本次授权执行，结果另存[实施和基线记录](../../worker-measurement-baseline-2026-10-13/README.md)；关闭决定不预先声明实施或采样通过。

## Implementation comment

2026-10-13：最小私有 JSONL 计量已接入 checkout。正式采集完整 16 个合成场景、17 个准备过程；
场景检查 15 passed、1 failed，准备结果 14 ready、2 blocked、1 cancelled。失败、取消、未结 intent 和跨 run 时间 unknown 保留。
真实 ATS、新增真实模型调用与自动最终请求放行均为 0。模型替身和暖缓存预置分别记录。
一个 Cua 冷启动定位超时留在正式基线中；全新 profile 的独立复验另存，不替换该失败或证明根因已修复。
完整结果、阶段耗时、介入、成本 unknown 与输入绑定见[实施和基线记录](../../worker-measurement-baseline-2026-10-13/README.md)。
