# 28 号票：运行核对精简的源码后继

范围：按原票顶部 2026-10-20 当前精简要求推进源码，保留原票和历史证据。仅使用隔离合成数据与本地浏览器；未更新或启动安装 App，真实申请仍暂停，最终 Submit 人工。本批不领取、关闭票，不改负责人、依赖或验收勾选。

当前状态：统一完整离线、受影响集合和浏览器回归通过；最终读回见 [final-readback.json](final-readback.json)。原票保持 open，安装/真实申请边界不变。

## 本次改动

1. 失效、过长或无法展开 home 的显式 Codex CLI 路径只使模型步骤不可用。资料读取、更正、历史及流程状态继续可用，不回退执行 PATH 中其他 CLI。共用验证保留原始异常链；模型配置描述只在自身路径处理处隔离同类故障。
2. 默认启动忽略未选用的 preparation_root。显式材料准备模式仍严格检查类型、绝对路径、链接与目录。只有实际工作区故障显示目录修复指示。Swift 仅源码修改与 typecheck，没有构建 App。
3. 普通单岗位动作、直接 Worker 恢复和子执行器启动不再枚举当前职业全库或重算模型/研究 benchmark。仍核对任务摘要、绑定引用、当前 JD/URL、材料更新 journal、联系方式、资格及同岗占用。authorize 与 dispatch 均保留当前选择、pause/hand-off、真实 owner/锁、精确 intent 和未知结果不重放。
4. 联系事实包含信息库及 career profile 中的 name/title/location/links。使用现有已认证历史 source snapshot 为锚点，当前只读固定 profile 来源和相关字段；无关 research/site 字段损坏不阻普通操作。没有新增索引、缓存或状态库。仍会读取历史 snapshot，不宣称无历史 I/O 或未测量的性能收益。
5. 材料采用与上传继续核验当前 career/JD/contact、adopted lineage 和精确 PDF/附件。完成分析保留原模型配置与 benchmark 修订；无关研究状态变化不废弃原完成材料。真实岗位或职业事实变化仍触发过期保护。

Flow 的显式 Continue/准备仍是事实与材料采用边界，可能扫描职业库。本次不声称每条 resume/prepare 路径零扫描。旧包/epoch/短 lease 门禁退役与 measurements.track 诊断隔离已在本次基线实现，本次复用相关回归，不冒称新增；诊断 nonce/sequence/责任链、实际 Browser/CUA 能力检查和业务检查点失败停止均保留。

## 候选与差异

- [最终冻结输入](frozen-inputs-v3.json)：808 项，完整默认与受影响集合使用 v2，最终浏览器使用 v3；各自读前/读后核对。两者只差未被默认选中的浏览器单测试同步，见 [变化证明](browser-synchronization-migration-v3.json)。
- [本批源码差异](source-delta-v3.diff)及[路径与摘要](source-delta-v3.json)：相对本批起点 16 文件，8 生产文件、5 原测试调整、3 新回归文件。不是相对 Git HEAD 的既有脏工作总差异。
- [原始源码清单](source-before.json)及[source-before.tar.gz](source-before.tar.gz)保全本批起点 805 项原字节。
- [源码交付候选](source-candidate-v3/manifest.json)：419 项，candidate `preparation-candidate-548f80f504d1a11cf2516bf54182fe6f306594b4b53b2e5804bcebe6462f9e88`。这是公开源码和合成输入交付，不是 App，也不是独立完整测试 checkout。

## 分项验证与独立复核

- [启动切片](startup/README.md)：共用 CLI 路径验证、实际 loopback HTTP 资料更正/历史/模型局部失败、PATH fallback canary、Swift Foundation 启动 harness 及 typecheck。最终相关集合 98 通过；早期 159、44 等集合有重叠，不累加。
- [普通操作切片](operation-scope/README.md)：新增 25 节点及相关集合 331 通过。真实 Worker/Runner 入口验证普通动作零当前 catalog 枚举；upload 保持当前来源、lineage 和精确文件核对。
- [独立最终审计](boundary-audit/final-review.md)：6 节点通过，包含 intent 落盘后的 contact/owner/PDF 变动拒绝、benchmark-only 公开 prepare POST，以及 long/unknown-home CLI；未发现新的未闭合安全问题。
- 根新增 `test_runtime_material_configuration.py`：benchmark-only 保持原完成材料的真实 HTTP 回归，以及 JD/职业事实变化仍停止的反例。原 contact-impact benchmark 断言迁移到当前产品行为，JD/career 过期语义保留。

分项结果有重叠，不与统一结果相加。统一结果如下；这些集合有重叠，不相加。

## 失败与历史保留

- startup 的 missing/long/unknown-home 原失败及中间 GET 状态读取失败均保留，最终局部修复见其 README。
- operation-scope 的普通动作全库拒绝、profile 联系事实漏检及无关字段误拦均先 RED 后 GREEN；旧相关断言迁移、拼错路径导致未运行、静态格式中间错误均分开记录。
- 根 `benchmark-red-v1.log` 是 benchmark-only 导致 409 的业务 RED。`benchmark-after-flow-v1.log` 已返回 200，但后置约束错误包含正常新增的 .execution claim；最终只比较原申请笔记/公开列表，原失败日志不删除。`benchmark-guards-v1.log` 的参数顺序错误属于测试问题，v2 三项通过。
- 独立审计中“prepare 必须零全库扫描”的探索期望强于票首对普通字段的要求，保留为探索历史，不列为必须转绿验收。成功 prepare 后整个 applications 目录不变的错误约束也已说明。
- 初次 browser collect 的过高 quiet 参数只输出分文件计数，不能作精确节点清单。修正工具输出后以 browser-collection-v2.log 收集 372 个独立节点，不修改产品源码或测试输入。

## 统一 v1 失败与测试迁移

首次统一冻结 v1 的生产代码与最终 v2 完全一致，只有两个正式测试文件变化，见 [输入差异](test-only-migration-inputs.json)。

- `affected-v1`：1709 passed / 1 failed，失败为旧 HTTP benchmark-only 断言要求 409；[独立 RED](legacy-benchmark-http-red-v1.log)定位到该行。迁移为重复 start 返回 200，原 analysis_id/inputs/artifacts 与历史比较保持，模型不重跑；当前 JD/career 变化拒绝的原测试仍保留。根组合 `benchmark-http-green-v1` 149 通过。
- `full-v1`：同一旧 HTTP 断言失败后主动中断，原日志、JUnit、exit 2 和 [确切 PID 中断记录](full-v1-interruption.json)保留，不能当完整默认验收。中断前 2895 passed / 1 failed；不是生产故障修复后复用旧绿色，最终从头运行 full-v2。
- browser A v1：186 通过；browser B v1：185 通过 / 1 失败，丢入队回执后客户端自动真实读回已成功，使瞬态 unknown 提示在观察前被覆盖。独立单节点也复现，不能归为压力或直接接受成功文本。
- 仅在测试路由中保存 POST 前真实 GET 快照，使 unknown 窗口可观察，保留原 scope 按钮、stale_reads >= 1、精确 receipt、单 POST、原队列/无 Worker/无模型断言；Observe 前放行真实读回。没有改产品或延长超时。正式单节点 1 通过，原失败与 scratch 探针保留在 operation-scope。
- [独立迁移复核](boundary-audit/test-migration-review-v1.md)及[最终正式文件回读](boundary-audit/test-migration-final-v2.md)确认两项最小修改合理。v1 失败后启动 v2 的完整默认与两个浏览器分片；v2 浏览器的后续计数竞态及最终 v3 见下节，不拿旧绿色替代最终浏览器验收。

## 浏览器 v2 的计数时序与最终同步修正

browser A v2 的 186 项通过。B v2 同一测试失败的准确断言是 `stale_reads == 0`；unknown 提示与其他排队入口断言已通过，是同步 Python 断言早于自动旧状态 GET。不能把这次失败写成“已核验提示覆盖 unknown”。

为提取准确 JUnit，中断已失败的 B v2；[中断记录](browser-shard-b-v2-interruption.json)、原日志及 XML 保留。中断后 pytest tmp_path 清理出现 KeyError，属于中断清理，不计新增产品缺陷或完整运行结果。

最终仅调整该测试：在 goto 前固定 POST 前真实 pipeline 快照；POST 开始后的 retained GET 响应用合成 header 标记，通过 `page.expect_response` 精确等待这次响应，再检查原 unknown、scope 按钮和 counter 断言。Observe 前放行真实读回。无 sleep、无产品或超时修改。[scratch v3 及根因](operation-scope/lost-admission-analysis-v2.md)、[独立方案审查](boundary-audit/test-readback-v3-review.md)及[正式最终回读](boundary-audit/final-scope-v3.md)保留。

最终完整默认 full-v2 已于本次修改前完成：4552 passed / 2 skipped / 556 deselected，808 项输入前后相同。2 项跳过均为显式 opt-in 的 PDF 性能/渲染 benchmark；本次不宣称性能收益。受影响 affected-v2 为 229 通过，其选中输入同样未被最终浏览器测试修改触及。最终浏览器在新冻结 v3 上重新跑全部 372 节点，旧 A 结果不替代新候选验证。

## 尚未运行的边界

未做安装 App 验收、实际 TCC/宿主权限、真实 ATS/SSO、在途原页/附件或版本组合交接。票首当前精简范围与旧历史矩阵分开保留，不用旧矩阵扩张当前任务；也不以本次合成绿色声明整票或真实申请已验收。原票保持 open、Assignee `01a150ef/bounded_protocol`，真实申请暂停。

## 原始保全

[tickets-and-maps-before.tar.gz](tickets-and-maps-before.tar.gz) 保存 135 份原票/地图；[历史清单](historical-before.json)保存本批目录外 20917 个既有证据文件；[App 清单](app-before.json)保存主 App 1465 个文件。本批最终仅向原 28 号票追加 Notes，原字节前缀和全部历史验收保留。统一回归通过后仅追加 Notes；原票前缀、元数据及其他历史文件读回保持，见 [notes-readback.json](notes-readback.json)。

## 统一最终结果

| 集合 | 通过 | 跳过 | 时间 |
|---|---:|---:|---:|
| 完整默认离线 | 4552 | 2 | 1031.10s |
| 受影响集合 | 229 | 0 | 71.23s |
| 本地合成浏览器 | 372 | 0 | 861.32s |

完整默认离线未改默认 marker，live/live_model 不运行；跳过原因见 final-readback.json。
浏览器372节点由两个186节点的不重叠分片执行；JUnit精确核对无缺失、重复、跳过或失败。分片覆盖见 [汇总](affected-browser-v3-run.json)及[节点清单](browser-selected-nodes-v3.json)。

[完整原日志](full-v2.log)、[完整JUnit](full-v2.xml)、[受影响原日志](affected-v2.log)、[浏览器A](browser-shard-a-v3.log)、[浏览器B](browser-shard-b-v3.log)均保留。完整默认与受影响集合在 frozen-inputs-v2 上前后808项无漂移；最终浏览器在 frozen-inputs-v3 上前后808项无漂移。两者仅差未被默认集合选中的 lost-admission 测试同步修正；所有生产、配置和默认选中测试均与完整运行相同，4554个默认节点不变。

Ruff check/format、git diff --check 与已有 Swift typecheck 通过；未增加依赖或构建App。[源码交付候选核验](source-candidate-verified.json)通过。

135份原票/地图保留原字节前缀；只向28号票追加说明。20917个既有历史文件除该明确追加外无变化。主App1465个已登记文件hash及文件集合保持；Git HEAD/master未移动。Tracker仍127票、24未关闭、0错误和原20警告；元数据逐项相同。
