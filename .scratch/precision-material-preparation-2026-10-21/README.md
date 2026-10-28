# 精准等待前必要材料与人工附稿修复 — 2026-10-21

本轮源码、公开回归、受影响及完整默认离线已完成验证。原票和地图只追加 Notes，不新增或关闭票。Status、Assignee、依赖及既有勾选保持。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。

## 最终验证

| 范围 | 本轮结果 | 原始证据 |
| --- | --- | --- |
| 完整默认离线（不覆盖 marker） | **4462 passed, 2 skipped, 532 deselected in 968.76s (0:16:08)** | [日志](full-offline-v1.log)、[JUnit](full-offline-v1.xml)、[运行收据](full-offline-v1-run.json) |
| 受影响默认 | 1370 passed | [日志](affected-v2.log)、[JUnit](affected-v2.xml)、[运行收据](affected-v2-run.json) |
| 受影响本地浏览器 | 252 passed | [日志](affected-browser-v2.log)、[JUnit](affected-browser-v2.xml)、[运行收据](affected-browser-v2-run.json) |
| 先前超时的 native web bridge | 21 passed，沿用原60秒编译与缓存策略 | [XML摘要与跳过原因](full-v1-xml-summary.json) |
| Ruff / 格式 / diff | 通过 | [Ruff](ruff-check-final-v2.log)、[格式](ruff-format-final-v2.log)、[diff](diff-check-final-v2.log) |
| 独立只读复核 | 限定范围未再确认可复现P2；不是独立重跑 | [限定审查](review/final-v1.md)、[最后继续请求delta](review/continuation-delta-v2.md) |

所有最终运行绑定同一份 **783** 项输入，前后无变化：[冻结v2](frozen-candidate-inputs-v2.json)、[全套前](suite-inputs-before-v1.json)、[全套后](suite-inputs-after-v1.json)。在当前脏工作区执行，不是独立checkout，也没有穷尽间接引用的历史fixture。默认排除live/live_model/worker_browser；受影响浏览器集合另以隔离Chromium、loopback HTTP与合成临时工作区运行。模型/编译器边界用明确合成结果；没有真实邮箱、模型、ATS或App接受。

## 修复后的行为

- 手工精调岗位先在唯一原 Worker/run/Page 发现并准备完整CV及已知必要cover/motivation，再进入第一次precision_adjustment。此前零填写、上传、Next或Submit。缺失真实证书保持等待，不能生成假证明。
- 一次Continue复用原Page、授权、生成attempt与当前材料。确实没有旧远端简历时走首传；相同PDF字节也首传一次，不捏造旧handle/replaces。Workable仅input.files为空不够，未知远端view link/文件名会阻断本地采用及后续填写。
- JD要求保留独立requirement_id及原文quote/span/hash，出现真实唯一字段后复用原稿。两个要求不能挤入同一字段；没有实际目的字段或语义歧义时等待mapping_required，不冒称已发送。显式句式解析是有界规则，空列表不证明任意JD需求完备。
- 附稿可查看正文、核验PDF及保存独立人工版本。保存不填写、不写答案库、不再调用模型；cover只复用本地PDF导出。旧源、PDF与材料历史保留，actor=user、human_reviewed=false；当前明确人工正文优先旧可复用答案，原页人工值仍优先。
- 本地未保存稿、正在制作或needs_recheck阻断Continue。丢失回包只读确切receipt；双窗口冲突保留两份文字并需明确重基。导出不持应用写锁，pause/skip先停止；返回原岗只能核验完整已导出候选，缺失/改写候选不重做导出或模型。
- 排队Continue后pause/cancel/skip撤销旧命令且不复活。已bound事务以后使用新用户Continue id，保留旧事务、候选、取消记录、授权与预算；不会重生成或重复上传。

源码变化只计本轮：[14文件delta与前后SHA](source-delta-v2.json)、[恢复基线差异](source-delta-v2.diff)、[backend接口与限制](backend-handoff.md)、[JD有界解析证据](jd/README.md)。没有新增依赖。原无Worker精准路线测试按真实新契约适配；真实原页正向接受由公开浏览器回归证明，未伪造precision_ready。

## RED与中间失败保留

[后端逐项记录](backend-progress.md)与[最终交接](backend-handoff.md)保留首次wait、一次Continue、真首传、JD-only、真实缺件、双向映射和停止竞态的RED/GREEN。人工附稿UI最终组合 [11 passed](ui-editor-final-v1.log)，有独立的查看、保存、cover、回包丢失、旧答案覆盖与冲突RED。skip返回候选恢复 [RED](ui-candidate-readback-red-v1.log) 后，[首次实现](ui-candidate-readback-green-v1.log)实际8pass/1fail（误用了雇主显示名）；固定本地letter.pdf后[单项通过](ui-candidate-readback-green-v2.log)，最终扩大集合再次验证。任何名为green的中间失败日志均未改写为通过。

最终继续恢复 [RED 1fail](bound-pause-recontinue-red-v1.log) → [GREEN 1pass](bound-pause-recontinue-green-v1.log)，[最小补丁](bound-pause-recontinue-fix.patch)前像与旧v1指纹精确匹配。[v1冻结](frozen-candidate-inputs-v1.json)、[旧受影响1370通过](affected-v1.log)、[core219默认/51浏览器](backend-handoff.md)均保留，最终接受使用v2源。报告中的集合存在重叠，不相加当新增覆盖。

## 票据和历史保全

[最终读回](final-readback.json)确认：127条解析票据与起点完全相同，仍24未关闭；128份原票/地图保留全部原字节前缀，仅13份追加本轮Notes。1333份历史资产、93份安装文件SHA不变。HEAD仍为 `e4a26d0c24311d014d478f7f92e58a88e6709b4b`，没有提交、push、安装或真实申请操作。[Notes链接](notes-link-readback.json)、[票据前](tracker-before.json)、[票据后](tracker-after.json)、[证据清单](evidence-manifest.json)。

前轮 [4450通过](../bound-material-update-2026-10-21/README.md)、原三P2 [4204通过](../p2-regression-fixes-2026-10-21/README.md)、最初 [4171通过/21项Swift超时未验](../ticket-progress-2026-10-21/implementation.md)保持各自原结果；本次通过不倒推历史运行通过，也不确定旧超时唯一原因。两项默认跳过仍是显式opt-in的PDF性能基准，本轮未启用。

安装版、真实材料质量/PDF视觉、真实ATS完整配送、宿主中断后冷启动恢复和人工Submit接受仍待原票与原依赖。本轮软件证据不关闭票或整个长期目标。
