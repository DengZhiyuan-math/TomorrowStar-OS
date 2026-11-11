# 最小计量与 16 个合成场景基线 — 2026-10-13

时区：Europe/Zurich。决定已定案；最小计量已交付。正式基线为 `baseline-final-v2/`，所有结果保留。

## 结果与边界

- **16 个场景全部采集**，场景检查 **15 passed、1 failed**。共享补充场景含两个岗位，因此有 **17 个准备过程**。
- 准备结果：**14 ready、2 blocked、1 cancelled**。取消样本保留未结 fill intent；重启样本保留 `recovered_result_not_visible`。
- **16/17 时间线可完整计量**。重启样本跨两个 run，完整耗时为 unknown；已观察的单 run 时长仍保留。
- **真实 ATS 请求、新增真实模型调用、自动最终请求放行均为 0**。固定模型替身的 11 次准备入口另计；暖缓存预置的 6 次替身调用在 setup 日志中另存。
- 岗位范围有 **41 次 Cua 入口尝试，41 次收到 RPC 回执**。共享初始化、权限、发现、关闭等调用另记；回执不是字段/附件业务验收。
- 费用、真实模型延迟、真实 tokens 和用户主动操作时长仍未测得；费用字段均为 unknown。脚本模拟的等待与操作不代表人的工作量。

来源：[完整汇总](baseline-summary.json)、[正式基线日志](baseline-final-v2.log)、[JUnit](baseline-final-v2.xml)、[计量说明](../../docs/worker-measurement.md)。

## 分组耗时

下表是成功条件下从请求准备到完整 ready 的范围；失败保留在分母和逐例表中。

| 执行方式 / 初态 | 开始场景 | ready | ready 完整耗时范围 | 浏览器 |
| --- | --- | --- | --- | --- |
| 原生 worker / 冷 | 3 | 3 | 1.396–3.307 秒 | 153.0.8010.12 |
| 原生 worker / 暖 | 3 | 3 | 0.227–0.235 秒 | 153.0.8010.12 |
| Cua 混合 / 冷 | 3 | 2 | 16.909–28.698 秒 | 155.0.8059.40 |
| Cua 混合 / 暖 | 3 | 3 | 8.909–32.876 秒 | 155.0.8059.40 |

冷/暖同时改变缓存和运行初态；原生与 Cua 使用不同浏览器和控件。采样时还并行运行完整离线回归。
这些数据是当前有负载环境的描述，不能用于工具速度排名、缓存因果收益或真实岗位性能承诺。没有发布 P95 或改善百分比。

## 逐场景记录

| 场景 | 检查 | 准备结果 | 观察/ready 总时长（秒） | Cua 入口 / 回执 | 缓存 |
| --- | --- | --- | --- | --- | --- |
| [native-cold-1](baseline-final-v2/native-cold-1/summary.json) | passed | ready | 3.307 | 0 / 0 | miss |
| [native-warm-1](baseline-final-v2/native-warm-1/summary.json) | passed | ready | 0.235 | 0 / 0 | hit |
| [native-cold-2](baseline-final-v2/native-cold-2/summary.json) | passed | ready | 1.397 | 0 / 0 | miss |
| [native-warm-2](baseline-final-v2/native-warm-2/summary.json) | passed | ready | 0.235 | 0 / 0 | hit |
| [native-cold-3](baseline-final-v2/native-cold-3/summary.json) | passed | ready | 1.396 | 0 / 0 | miss |
| [native-warm-3](baseline-final-v2/native-warm-3/summary.json) | passed | ready | 0.227 | 0 / 0 | hit |
| [cua-cold-1](baseline-final-v2/cua-cold-1/summary.json) | passed | ready | 16.909 | 6 / 6 | miss |
| [cua-warm-1](baseline-final-v2/cua-warm-1/summary.json) | passed | ready | 8.909 | 6 / 6 | hit |
| [cua-cold-2](baseline-final-v2/cua-cold-2/summary.json) | passed | ready | 28.698 | 6 / 6 | miss |
| [cua-warm-2](baseline-final-v2/cua-warm-2/summary.json) | passed | ready | 14.264 | 6 / 6 | hit |
| [cua-cold-3](baseline-final-v2/cua-cold-3/summary.json) | failed | blocked | 34.012 | 5 / 5 | miss |
| [cua-warm-3](baseline-final-v2/cua-warm-3/summary.json) | passed | ready | 32.876 | 6 / 6 | hit |
| [shared-answer](baseline-final-v2/shared-answer/summary.json) | passed | ready, ready | 19.490, 12.169 | 0 / 0 | miss, miss |
| [unknown-send](baseline-final-v2/unknown-send/summary.json) | passed | cancelled | 43.043 | 6 / 6 | miss |
| [paused-answer](baseline-final-v2/paused-answer/summary.json) | passed | ready | 9.342 | 0 / 0 | miss |
| [restart](baseline-final-v2/restart/summary.json) | passed | blocked | unknown | 0 / 0 | miss |

每例原始 JSONL 保留 stage、动作、状态分类、缓存、介入和调用。自动时段按区间并集计，不重复累加嵌套阶段。
初次待开始记为正常等待，共享初始化记为排队，显式 pause 独立计量。共享启动成本只记录一次。

## 未预期失败与独立复验

`cua-cold-3` 的第五次 RPC 已收到回执，后续定位检查 `Locator.element_handle` 在 4 秒内未完成。
worker 保留 fill intent 并转为 needs_recheck，没有继续发送或自动重试。原样保留[错误](baseline-final-v2/cua-cold-3/synthetic-error.log)和[计量](baseline-final-v2/cua-cold-3/measurements.jsonl)。
这是正式样本中的失败，不从耗时、完成率或覆盖分母删除。并行负载是环境事实；它是否导致超时尚未证明。

全新 profile 的单场景[独立复验](timeout-successor.log)为 **1 passed、15 deselected**，其[数据](timeout-successor/cua-cold-3/summary.json)另存。
复验不是原未知动作的重试，也不替换正式失败。底层超时根因未确认；后续由[确定通用表单支持等级与首批覆盖范围](../application-worker-next-stage/issues/04-coverage-contract.md)保留当前原生兼容性缺口。

## 实现与检查

- [worker_measurement.py](../../src/career_evidence_graph/worker_measurement.py)：标准库 JSONL、单调时钟、互斥分类、嵌套区间汇总、缺失与损坏标记。
- 复用既有 ResumeStore、WorkerStore、ApplicationRunner 和 CuaMcpClient 边界；原有权限、答案、PDF、发送守卫和同步行为保持。
- 简历生成关联到批次；缓存命中仍计读取。模型替身与真实入口分开；Cua 记录 ack / 未发送 / unknown。
- 计量失败或无效 measurement_id 不阻断业务检查点；有效开始记录与原始损坏行均保留。
- 不新增依赖、监控平台、并发 worker、自动提交或缓存优化。
- 重点回归 **46 passed**；[完整离线](offline-final-v2.log) **914 passed、114 deselected**；[受影响 browser 回归](browser-final.log) **50 passed、5 skipped、42 deselected**。五项原生 opt-in 跳过独立列出，没有升级为通过。逐项结果见[核验](verification.json)。
- [126 项输入前](final-v2-inputs-before.json)与[输入后](final-v2-inputs-after.json)相同。两个旧封存包的 135 个文件保持原字节。

## 保留的开发和采样历史

所有旧日志和包均保留；早期断言、初态和计时类别不替代当前正式基线。

- 首个 uv 运行受默认缓存目录权限限制；改用临时缓存，不改锁文件。
- 原生 PDF 夹具与主 Playwright 同步循环冲突；本地真实导出移至独立线程。
- 原生 select 的嵌套标签把选项文字并入问题；改用标准显式 label。共享问题采用原有 sponsorship / country 范围。
- 首版未知发送夹具已阻断 POST 且核验本地字段，未产生预期的未结动作；改为复用已有 Cua 发送守卫场景。
- 重启后的新 guard 覆盖了离线夹具路由；重新注册合成响应，仍保持 offline。随后验证到旧结果不可见的安全阻塞，保留原先错误的 ready 预期和失败。
- 首个完整 16 passed 包保留为 `baseline-final/`；其初次待开始/共享初始化分类由当前 v2 修正，不升级旧结果。

本轮没有读取真实个人资料、答案或申请，没有操作现有浏览器和安装包，也未提交或推送 Git。
职业图、真实人工能力校准及三个真实 JD 的主里程碑未因本轮计量推进而验收。
