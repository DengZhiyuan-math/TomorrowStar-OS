# M1/M2、Prism 人工后继与信件契约并发实施

日期：2026-10-26，Europe/Zurich。状态：**三票已按源码/合成范围结案。**

最终统一冻结为 665 文件。完整默认离线 **7,722 passed、2 skipped**（554.46 秒），
随后相关隔离合成浏览器 **89 passed**（205.67 秒）；零失败/错误。JUnit 精确覆盖
两个不相交清单，源码运行前后不变；最终审查的 11 个变更路径与受验摘要一致。
Ruff、格式、Git diff 及包含未跟踪文件的精确差异空白检查通过。
机器结论见[final-verification.json](final-verification.json)。

两项跳过是未启用的显式 PDF 性能基准，不作性能通过声明。以下首次/第二次中断
和所有 RED 记录继续保留，不混入最终通过数。完整 Module 迁移仍未完成。

用户调用 implement，授权本轮并发执行三张票。原页直接接管由原负责人继续，本轮
不认领该票。Prism 上游更新按用户决定搁置，仅当具体 Prism 特有缺陷与上游差异
相关时重新评估；不作为本轮前置。

| 票据 | 本轮责任 | 共享文件规则 |
| --- | --- | --- |
| [核对并补齐 M1/M2 剩余职责迁移](../module-completion-2026-10-26/issues/01-m1-m2-remaining-ownership.md) | `m1_m2` 先逐项审计、复用证据，只修真实缺口 | 修改 Flow/Worker/MaterialEdit 前先由父会话分配方法区域 |
| [修复映射导入材料的 Prism 人工后继](../module-completion-2026-10-26/issues/02-mapped-import-prism-successor.md) | `resume_successor` 独占 Resume/Versions 的模板与人工后继 | 不改 Flow/Portal 或纯 reconcile 规则来迎合错误调用 |
| [收拢 CoverLetter 与材料一致性契约](../module-completion-2026-10-26/issues/04-letter-material-contracts.md) | `letter_contracts` 独占 Letter/Materials/Consistency 及信件 Supplemental 区域 | Portal 四个信件闭包由其接线；Worker 接线留父会话集成 |

三票的 Resolution 评论记录最终答案和逐条验收；地图只维护结论索引。
「收拢 Resume 准备、版本和 PDF 生命周期」现解除硬阻塞，保持未领取。
未完成的原页控制与准备调度已在 T09/M4 原票明确承接。

变更前 666 文件的源码/测试/运行配置指纹及归档分别保存在
`before-source-sha256.json` 和 `before-source.tar.gz`，用于区分本轮与既有未提交工作。
不从当前 Git HEAD 猜测本轮差异，不覆盖无关编辑。

每项按公开行为逐条 RED→GREEN。子任务只运行受影响离线回归。父会话完成集成与
独立审查后统一冻结，执行完整默认离线，再执行相关隔离合成浏览器；运行前后核对
同一快照。源码、隔离替身、真实服务和安装版结论分别记录。

本轮不提交或发布，不更新或重启 Prism/主 App，不操作真实模型、ATS 或最终 Submit。

## 独立审查与首次统一批次

Resume 与信件独立审查及跨票规范审查未发现需修改项。M1/M2 审查发现候选内容
未与原预留人工正文严格绑定的问题，反例与原报告保存在
[归属审查](reviews/mc01-review.md)。已停止首次完整离线批次，再修复和重新冻结；
原批次、37 项已完成分组及中断输出全部保留在 `verification/offline/`，
[中断记录](verification/offline-interrupted-for-review.json)明确不作最终通过声明。
没有在这批运行中修改受验源码。

P2 修复后的独立复验 44 项通过。增量规范复核随后指出协调器与 Worker 重复维护
候选重建规则；已停止第二批 `verification/offline-final/`，先将恢复路径统一交所属
校验，再最终冻结。[第二次中断记录](verification/offline-r2-interrupted-for-review.json)
同样不作最终通过声明；两批均在停止后才允许修改受验文件。

## 最终审查和验收

- [Prism 人工后继独立审查](reviews/mc02-review.md)：34 项独立专项通过，无需修复项。
- [信件独立审查](reviews/mc04-review.md)：56 项独立回归通过，无需修复项。
- [M1/M2 最终正确性复核](reviews/mc01-final-review.md)：原反例和公开恢复组合 51 项通过，P2 已修复。
- [最终规范复核](reviews/standards-final-review.md)：重复规则已移除，无剩余实质问题。
- 完整默认离线：`verification/offline-final-r3/`；相关隔离浏览器：`verification/browser/`。
  两组从 collect-only 清单、互斥分组到 JUnit 精确核对，最终脚本重新检查当前源码与审查摘要。

实施细节和局部运行分别见 [M1/M2](mc01/implementation.md)、
[Prism 后继](mc02/implementation.md)、[信件](mc04/implementation.md)。
完整本轮源码差异为 [final-implementation.diff](reviews/final-implementation.diff)，
基准是实施前归档，保留此前用户与其他会话的未提交工作。

最终命令：

```sh
UV_CACHE_DIR=/private/tmp/tomorrowstar-uv-cache uv run --locked --offline --no-sync python -B .scratch/mc01-mc02-mc04-implementation-2026-10-26/verify_offline.py
UV_CACHE_DIR=/private/tmp/tomorrowstar-uv-cache uv run --locked --offline --no-sync python -B .scratch/mc01-mc02-mc04-implementation-2026-10-26/verify_browser.py
UV_CACHE_DIR=/private/tmp/tomorrowstar-uv-cache uv run --locked --offline --no-sync python -B .scratch/mc01-mc02-mc04-implementation-2026-10-26/finalize_verification.py
```

这些一次性脚本拒绝覆盖已有证据目录；本轮实际日志和结果已保留，不应在原目录重跑。
本轮结案不声明真实模型、Prism 服务、安装版 GUI 或真实 ATS 验收；最终 Submit 仍手动。
