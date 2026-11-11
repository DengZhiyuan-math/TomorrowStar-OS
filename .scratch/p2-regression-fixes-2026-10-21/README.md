# 三项 P2 回归修复 — 2026-10-21

用户授权修复当前审计发现的三项 P2、补回归测试并重跑受影响及完整默认离线套件。原票和地图只追加结果；不新增票，不改变状态、负责人、依赖或历史证据。App 暂不更新，真实申请继续暂停。

## 修复范围

只修改既有 `application_pipeline.py` 和两份既有测试文件，未添加依赖、状态库或新的业务入口。[本轮差异](assets/fix.diff)和[文件哈希](assets/source-delta.json)使用本目标起点的恢复副本作基线，不将此前脏工作计入本轮。

| 审计问题 | 最小修复 | 新增公开行为回归 |
| --- | --- | --- |
| 原邮件读取完成、pipeline 尚未采用结果时，capture 替换最新 intake run，导致健康流程中断 | 原始读取及其主动暂停的恢复阶段在采用结果前返回 `mail_capture_busy`，不保存新收据、不派发收录；采用后可以使用同一请求 ID 收录 | 运行中和主动暂停两种交接窗口：原 checkpoint、来源链、run、任务和 worker 保持；采用原结果后收录可用 |
| 原始 start 请求重放被当成语言 Continue | 先识别原 start 请求 ID，再进入任何恢复分支；新 ID 的 Continue 及其幂等性保持 | 仍冲突和答案已补齐两种情况：旧请求保持等待与 checkpoint 字节；显式新 Continue 才启动分析 |
| 语言冲突先于既有明确排除条件，要求处理本不应推进的岗位 | 独立排除条件优先；只有其他条件允许当前岗位推进时才等待语言解决 | hold、manual、低优先级、弱匹配、缺失证据、过期、已有投递状态、无效链接共八种情况：排除首岗并继续下一岗；原合法岗位语言等待用例保留 |

共新增 12 个参数化测试节点。每项先保留 RED，再做最小修复并验证 GREEN；未把旧失败日志改写成通过。

## 验证

| 验证 | 结果及证据 |
| --- | --- |
| 邮件结果交接窗口 | [RED](assets/capture-adoption-red.log)：2 failed；[GREEN](assets/capture-adoption-green.log)：2 passed |
| 原启动请求幂等性 | [RED](assets/start-idempotency-red.log)：2 failed；[GREEN](assets/start-idempotency-green.log)：2 passed |
| 排除条件优先级 | [RED](assets/exclusion-precedence-red.log)：8 failed；[GREEN](assets/exclusion-precedence-green.log)：8 passed |
| Pipeline、capture、HTTP | [122 passed](assets/pipeline-regressions.log) |
| 受影响 14 个模块 | [557 passed](assets/affected-regressions.log)，包含前述用例，不相加 |
| 全仓 Ruff / 格式 | [Ruff](assets/ruff-check.log)、[格式](assets/ruff-format.log)通过；禁用缓存并排除历史 `.scratch` |
| 独立代码复核 | [未发现新增问题](assets/independent-review.json)；只读静态复核，不冒称独立重跑测试 |
| 完整默认离线 | **4204 passed、2 skipped、425 deselected，755.36s，exit0**；[原日志](assets/full-offline.log)、[运行收据](assets/full-offline-run.json)、[JUnit 节点结果](assets/full-offline.xml) |

[受测输入](assets/suite-inputs-before.json)绑定当前源码、测试、脚本、macOS、validation、planning 文本输入及锁定配置。它不是独立 checkout，也没有穷尽测试间接引用的历史 `.scratch` 验收输入。完整套件在当前工作 checkout 执行。默认排除 live、live_model、worker_browser；未打开模型、真实邮箱或浏览器试验。没有修改 Swift 原生夹具、编译时限或缓存策略。

## 历史与未完成范围

[前次工程记录](../ticket-progress-2026-10-21/implementation.md)的 582 项通过、完整运行 4171 passed / 2 skipped / 425 deselected / 21 errors，以及旧 Swift 冷编译与缓存诊断保持原记录。新结果不覆盖或重新标记旧运行。

本次不完成持续自动收录、取消旧总窗和读取限制、全局串行岗位激活、完成/skip 后续岗、返回原岗、完整事实更正历史或人工材料合并。这些仍由[原 24 票盘点](../ticket-progress-2026-10-21/remaining-ticket-inventory.md)承接。安装、实际 worker 加载、真实字段/附件、用户手动 Submit 结果和产品质量接受仍分别未验，详见[集中待审](../ticket-progress-2026-10-21/review-queue.md)。

## 完整运行终态及输入回读

[运行前后核对](assets/suite-inputs-after-verification.json)确认 747 份登记输入全部相同。默认选中 4206 个节点，4204 通过、2 跳过，零失败、零错误；另有 425 个默认排除。两项跳过是需要显式 opt-in 的 PDF 复用性能基准，本轮没有开启对应模型或 Chrome 试验。

前次在共享 Swift 编译夹具超时的 `test_native_web_check_bridge` 21 个节点，本轮全部运行并通过。未修改原生源码、测试夹具、60 秒时限或缓存策略；这只记录本轮通过，不能倒推旧运行通过或据此声称已经确定前次超时的唯一原因。

三项 P2 的源码修复与本轮离线验证已完成。原票整体范围、其他未完工程、安装组合和真实/人工接受不因此完成；本次不关闭任何票或地图。旧日志和上游候选保持原物，App 未更新，真实申请继续暂停。最终票据、历史字节、链接与安装源码核对见[回读记录](assets/final-readback.json)。
