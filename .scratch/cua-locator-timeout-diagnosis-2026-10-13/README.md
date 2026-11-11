# Cua 冷启动定位超时：后继诊断与最小修复

日期：2026-10-13。范围：checkout、离线合成页面、临时自有 Chrome 与 bounded Cua MCP。
真实 ATS 请求 **0**；新增真实模型调用 **0**。没有更新已安装 TomorrowStar.app。

## 结论与边界

原失败位于 combobox 已展开后、选择选项前的身份检查。
定位器已找到可见控件，但重复获取 `ElementHandle` 的操作没有在 4000 ms 内完成。
这不是“启动时没有找到控件”的证据。

已移除这一次重复句柄获取。当前实现用 `Locator.evaluate_all` 在主执行上下文比较保存的节点。
节点必须仍连接；当前选择器必须只匹配一个节点；该节点必须与保存的节点相同。
答案、PDF、批次、controller lease、运行身份、问题形状及发送守卫保持有效。
没有增加未知动作重试，没有延长定位期限，也没有忽略定位错误。

**没有确认并行负载导致原超时。也没有排除负载放大稀有停滞的可能。**
新采样未自然复现该定位超时；历史没有底层 CDP RPC 轨迹。
因此，能确认的是失败检查边界与可产生同一症状的句柄转换机制，不能确认历史停滞的具体 RPC 或操作系统原因。
受控故障注入不是原始事件的自然重现。

## 原失败与时序

原[16 场景基线](../worker-measurement-baseline-2026-10-13/README.md)仍为 15 passed、1 failed。
`cua-cold-3` 的[原错误](../worker-measurement-baseline-2026-10-13/baseline-final-v2/cua-cold-3/synthetic-error.log)
记录已展开的可见 `hosted-3-0` input。
它保留待确认 fill 意图；五次岗位 MCP 调用已有回执；第六次选项点击未发出。

最后一次检查扫描在 09:53:53.886963 UTC 完成，仅耗时 2.776 ms。
失败步骤在 09:53:57.902715 UTC 结束。
离线套件的 JUnit 时间推算结束时间为 09:53:56.715190 UTC。
两者有时间重叠；重叠本身不能证明因果关系。详见[历史时序](historical-timeline.json)。

## 假设与证据

| 排名 | 可证伪预测 | 结果 |
|---|---|---|
| 1. 定位成功后的句柄提取 / 跨上下文转换停滞 | 只延迟此转换，应出现同一日志；直接节点比较应避开该路径 | 支持该故障机制。缩小场景与完整原生 Cua 场景均由红转绿。历史具体 RPC 未记录。 |
| 2. 并行负载争用 | 相同源码和输入在增加负载后更容易发生定位超时 | 新自然采样没有同类超时；样本不足以否证稀有影响。另出现一次不同的启动核验阻断。 |
| 3. 控件替换或标记变化 | 身份变化应在点击选项前阻断 | 原合成页面没有替换行为；现有替换回归继续以 `question_changed` 停止。历史节点级轨迹不足。 |
| 4. 事件泵 / 外层期限干扰 | 应观察到外层期限触发或 MCP 结果未知 | 原五次 MCP 均有回执；失败步骤远短于 35 s 外层期限。没有证据指向外层期限。事件泵内部影响未独立证明。 |

## 自然冷启动对照

每次使用全新 profile。控件、PDF 导出、固定 résumé 替代、网络拦截和 4000 ms 默认期限相同。
“单独运行”仅指没有本实验新增的离线负载，不能断言整台机器空闲。
负载复用完整离线 pytest 命令；子进程在采样结束时仍运行，随后按所属进程组停止。
负载日志是部分执行记录，不是完整回归通过证据。

| 源码 | 增加的负载 | 次数 | 结果 |
|---|---|---:|---|
| 修复前 | 无 | 4 | 4 passed（含首次原场景复验） |
| 修复前 | 采样前启动离线套件 | 3 | 2 passed；1 次启动窗口核验阻断 |
| 修复前保存副本 | 离线套件已运行 83 s | 1 | 1 passed |
| 修复后 | 无 | 3 | 3 passed |
| 修复后 | 采样前启动离线套件 | 3 | 3 passed |
| 修复后 | 离线套件已运行 83 s | 1 | 1 passed |

修复后 **7/7 自然冷启动采样通过**。这些是本次合成后继样本，不替换原失败分母。
常规对照固定顺序为 idle、load、load、idle、idle、load；分别在修复前后执行。
末段补充实验的点击前扫描位于负载年龄 109.811 s / 107.489 s，历史为约 112.857 s。
这匹配了近似运行时长，未匹配 CPU 利用率、套件进度或所有系统后台负载。

[逐次结果](cohort-results.json)、[修复前日志](replay-before-v2.log)、[修复后日志](replay-after.log)、
[末段负载日志](late-load.log)保留全部结果。
保存副本通过独立诊断模块加载，不回退生产文件。
其常规 admission manifest 仍描述当前 checkout，完整执行差异由
[显式执行副本与 hash](late-load-original-execution.json)补充；不能把普通 manifest 当成该试验的全部执行来源。

### 独立启动失败

修复前 `load-2` 在 `managed_hidden_chrome` 的 `list_windows` 核验中观察到 `is_on_screen`，
以 `cua_visibility_unknown` 停止。它没有进入定位检查，没有岗位结果 summary。
该失败保留于[原始日志](replay-before-v2.log)与 `before/load-2/diagnostic.json`，不改算通过。
本轮没有修复这一不同的启动现象；之后的通过不消除该失败，也不证明启动全过程零帧可见。

## 受控复现与回归

安装的 Playwright 1.63.0 实现会先解析 selector，再提取节点，并经
`DOM.describeNode` / `DOM.resolveNode` 将句柄转到主执行上下文。
诊断仅在临时驱动副本中，对已展开且带 worker 标记的节点，延迟 `DOM.resolveNode` 前的转换 4500 ms。
安装依赖保持原 hash；来源与 Apache-2.0 记录见[探针来源](adoption-probe-provenance.json)。

| 核验 | 修复前 | 修复后 |
|---|---|---|
| 缩小检查 + 完整原生 Cua 场景，转换阶段故障注入 | [2 failed](adoption-red.log)，均出现原 4000 ms 日志，保留意图 | [2 passed](adoption-green.log)，省去会被注入停滞的重复转换 |
| 外部 Playwright 边界故障回归 | [1 failed](regression-red.log)，岗位等待复核 | [5 passed](regression-green.log)，含答案变更、暂停、节点替换、PDF 变更 |
| Cua 模块与计量模块的最终针对性回归 | — | [29 passed](targeted-final.log)，0 skipped；含 5 项真实原生 MCP 合成测试 |
| Ruff 检查与格式检查 | — | 通过 |

最终原生测试覆盖确认选项、未知 POST 阻断、选项歧义停止、原页与 File 交接、后续批次、私有运行时退出。
四个表单场景共用一个隔离窗口，人工复核仅显示一次。
这不是实时 ATS 验收、收益比较、真实模型成本测量或已安装应用的新版本验收。

快速回归命令（checkout launcher，离线）：

```sh
PLAYWRIGHT_BROWSERS_PATH=0 uv --cache-dir /private/tmp/ts-measurement-uv run --locked \
  python scripts/run_pytest.py -q tests/test_cua_worker.py \
  -k 'continues_without_reacquiring or rechecks_authority_between_native_actions' \
  -m worker_browser
```

## 保存与复核

- [最小代码与回归差异](change.diff)。生产执行源码只修改 `application_worker_browser.py` 的身份比较；没有新增依赖。
- [核验索引](verification.json)包括初次诊断脚本的导入失败，没有删除失败记录。
- 修复后 [126 个执行输入](fixed-execution-inputs.json)与[采样后指纹](fixed-execution-inputs-after.json)相同。
- [历史前核验](historical-check-before.json)与[历史后核验](historical-check-after.json)：原计量包 371 文件、两份旧 Cua 包 135 文件，合计 **506 文件原字节保持**。
- `debug_*.py` 为明确标记的诊断工具，仅显式调用。故障钩子只进入临时 Playwright 副本；`src/`、`tests/`、`docs/` 中没有 `[DEBUG-cua...]` 钩子。
- 原封存包不包含本轮产物；本目录以新的 `artifact-hashes.json` 封存。没有改写原 16 场景结果。
