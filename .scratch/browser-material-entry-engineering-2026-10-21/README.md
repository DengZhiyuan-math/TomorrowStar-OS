# 浏览器、材料更新与默认入口工程 — 2026-10-21

本轮按[当前工作审计](../work-audit-2026-10-21/README.md)推进源码和隔离合成回归。没有更新或启动安装 App，没有访问真实邮箱、模型、ATS 或申请。最终 Submit 仍人工。原票身份、状态、负责人、依赖、验收勾选和历史收据保留；不以源码测试关闭整票。

## 本轮结果

| 原票 | 已实现并补回归 | 保留边界 |
| --- | --- | --- |
| 18、37 | 原 Runner/run/Page 支持唯一明确的普通 Next/Continue 链接跨文档；保留岗位身份、原查询参数、intent 与未知结果，文档字段 ID 不重复。登录落页后可等待同文档验证，再一次继续。 | 仅同源、同路径、明确 step/stage/page 查询变化的 GET；任意 JS/POST、跨路径或跨源、完整 reload/SSO、冷启动重建仍不支持。 |
| 36、40 | 同 JD 的职业事实变化进入共享完整材料路径；核验历史完整人工底稿、来源快照和分析绑定，仅替换可确定受影响分组，其他人工措辞逐字保留。 | 未映射的已消费上下文变化、引用丢失、分组歧义明确停止；已消费分析输入变化仍重新分析。真实文案/PDF视觉质量和跨 JD 人工冲突未验。 |
| 34、39、41 | 默认推荐和手工岗位统一进入既有 Pipeline；接纳只保存队列，不切当前岗或创建 Flow。严格版本与幂等校验、既有推荐顺序、重开持久化和丢失回包精确读回均有回归。 | 独立 preparation 和未被接管的历史 standalone 兼容保留；全部状态副本和旧代码尚未退役。 |
| 39、41 | 默认 UI 撤下重复来源、分析、生成和 Worker 执行控制；HTTP 层同时限制旧执行入口，包括 export-pdf。安全暂停、只读查看、材料编辑和未知结果核对保留。 | 不接管旧 owner/Page，不自动重开申请；不代表安装版全部入口体验接受。 |

没有新增依赖或第二事实库/主控。本轮准确源码增量为 **10 个修改文件、6 个新增正式测试文件**，见[相对轮前精确归档的差异](source-delta-v5.diff)和[清单](source-delta-v5.json)。Git 本已有未提交工作，故不用整个 Git diff 冒充本轮增量。

## 验证

完整默认离线已完成：**4487 passed、2 skipped、556 deselected，1058.20 秒**，见[原日志](full-v1.log)、[JUnit](full-v1.xml)、[命令及前后输入回执](full-v1-run.json)。21 项原生桥均通过；两项跳过为明确 opt-in 的本地渲染/模型性能基准，见[解析结果](full-v1-summary.json)。805 项输入前后零漂移。

完整默认之后仅修改默认排除的 `tests/test_application_flow_browser.py`。最终浏览器/受影响默认使用[frozen-inputs-v4.json](frozen-inputs-v4.json)：805 项。与完整默认的 v3 比较，**所有生产和配置输入一致，默认选中的 4489 个节点也完全一致**；唯一差异是这份浏览器旅程文件，见[精确范围读回](full-to-final-scope-readback.json)。因此不重复已经通过且没有受影响的完整默认套件，也不声称其使用了后继测试文件。

最终浏览器按[372 个确切选中节点](browser-selected-nodes-v4.json)拆成两个互不重叠的 186 节点分组，各自记录相同 v4 输入的前后摘要、命令、JUnit 与原日志。最终汇总必须验证无重复、无缺失、无跳过或失败。最终浏览器已完成：**372 passed、0 skipped**，两组各 186 项通过。A 组 [日志](browser-shard-a-v1.log)/[回执](browser-shard-a-v1-run.json)，B 组 [日志](browser-shard-b-v1.log)/[回执](browser-shard-b-v1-run.json)；[汇总 JUnit](affected-browser-v3.xml)及[覆盖核对回执](affected-browser-v3-run.json)确认 372 个确切节点各执行一次，无重复、无缺失。两组的 805 项输入前后均零漂移。这是同一冻结版本的两个独立进程，不冒称单一串行运行。

最终受影响默认已完成：**1416 passed、316 deselected，262.95 秒**，见[原日志](affected-v3.log)、[JUnit](affected-v3.xml)、[回执](affected-v3-run.json)；805 项输入前后零漂移。

最终 Ruff [check](ruff-check-v4.log)、[format](ruff-format-v4.log)、[JavaScript 语法](javascript-v4.log)及[差异空白检查](diff-check-v4.log)均通过。

完整默认的 805 项输入被冻结为[frozen-inputs-v3.json](frozen-inputs-v3.json)。原 783 项加 6 个新增测试及 16 个补纳入覆盖的既有文档/许可证；这些文档不是本轮新增实现。每次统一测试保留命令、前后输入、JUnit、原日志和退出码。范围是当前 checkout 明列的源码/配置/测试与基线输入，不是所有间接历史夹具的穷尽闭包，也不是隔离 checkout。

[源码交接候选 v4](source-candidate-v4/manifest.json)经现有脚本创建并对当前源码核验；它不构建或安装 App，也不是可独立运行完整测试的 checkout。早期 v1/v2/v3 候选和清单保留历史含义。

## 独立复核及失败保留

- 浏览器负责人发现并修复材料两项 P2：research/masterThesis links 被过度过滤，以及历史 source-snapshot 未验证自身内容摘要和原分析绑定。[独立修后复测](navigation-review/material-fix-readback.md)两项通过，正式回归包含在最终候选。
- 材料负责人通过真实 loopback HTTP 复现 export-pdf 绕过默认主控；已加服务端限制与正式 HTTP 回归。
- 首次统一受影响集合为 **1413 passed、2 failed、316 deselected**，见[原日志](affected-v1.log)。两项真实回归是 HTTP wrapper 锁范围阻碍 shutdown，以及改变 observer 的原 flow_runtime_busy 返回。未修改原断言或 3 秒门限。后继使用 ContextVar 标记受限入口，在分派前和实际写入锁内短检查，保留原职责错误优先级，见[锁修复记录](entry/scope-successor.md)。原两项、50 项 HTTP/Flow 组合及 176 项入口组合均通过。
- 第二次统一受影响集合为 **1414 passed、2 failed、316 deselected**，见[原日志](affected-v2.log)；两项为新运行时 ContextVar 被加载版本测量当作政策常量，导致角色摘要无法计算。按既有 `_RUNTIME_VALUES` 精确排除每请求运行槽，函数代码及排除清单本身仍参与测量。修后[68 项 HTTP/Flow/加载探针](import-review/green.log)和[75 项加载版本、打包映射、计量](import-review/identity-green.log)均通过。[独立诊断](import-review/reproduce.log)保留原两项失败。旧浏览器 v1 在获知缺陷后中断，不计完整通过；最终浏览器另计 v2。
- 旧请求排队后新接纳先完成，旧 create 仍被拒绝；接纳成功但回包丢失，精确只读匹配 admission_requests，不重复 POST、不锁无关当前岗 Continue。正式 HTTP 和实际本地浏览器测试保留。
- [浏览器切片记录](browser/README.md)、[材料切片记录](materials/README.md)、[入口切片记录](entry/README.md)保留各阶段 RED、失败、修复与局部结果。入口旧报告中“Flow HTTP wrapper 持锁”的描述由[后继记录](entry/scope-successor.md)替代。局部重叠结果不累加成统一通过数量。
- 扩大后的浏览器组合 v2 在旧默认 select→Flow 旅程失败后中断，日志与[中断记录](affected-browser-v2-interruption.json)保留，不计完整通过。独立原件复现为[2 failed](entry/legacy-complete-review/original-first-two-red.txt)。其中两项退役的默认契约已迁为真实 capture/admit 和局部 unknown；其余 12 项的 Python assert/Playwright expect 经[独立 AST 复核](entry/legacy-complete-review/independent-review.md)完整保留。14 个节点没有增删；没有 skip/xfail 或超时放宽。材料/资格/编辑仅改用公开 HTTP 建立历史任务，未知范围 mock 延后到旧任务准备后，见[逐项映射和 6 项验证](entry/legacy-complete-review/README.md)。
- 原有 browser helper 依赖默认手动分析入口，已改为通过现有 standalone 公共 HTTP 初始化历史任务，再只读打开；后续原 Worker UI 断言保留。原失败日志不改写为通过。

## 后续原票范围

本轮没有证明任意 ATS 导航或真实 SSO，没有放行未知网络写入、未核验 Workable 附稿，也没有完成 APP-12 的真实结果/下一岗闭环。39 号的全部可写状态副本收敛仍待后续。安装版组合、冷主机行为、真实材料质量及真实申请接受继续由原票承接；本轮不启动这些操作。

## 保全和导航

轮前源码、票和地图分别保存在[source-before.tar.gz](source-before.tar.gz)与[tickets-and-maps-before.tar.gz](tickets-and-maps-before.tar.gz)。原 18,999 项历史文件与 1,465 项安装 App 文件都有轮前摘要，最终读回另存，不覆盖历史证据。原票仅允许追加本轮 Notes，不改变头部或既有验收项。

最终[保全读回](final-readback.json)与[Notes 追加记录](notes-readback.json)确认：

- 仅向 18/34/36/37/39/40/41 七张原票和主地图追加 Notes；135 个原票/地图文件的既有字节完整保留，其余文件不变。没有领取、新建或关闭票。
- tracker 解析前后一致：127 总票、24 未关闭、0 error、20 条既有 warning；未知负责人和历史元数据仍保留，不推断所有权。见[最终 tracker](tracker-after.json)。
- 原 18,999 项历史文件无非预期变化；只有上述 8 项获授权的 Notes 追加。旧审计、旧成功与失败日志均保留。
- 唯一安装 App 的 1,465 项普通文件清单与字节一致；没有更新或启动 App。
- 最终 805 项源码/配置/正式测试输入无漂移；最终 416 文件源码交接候选[测试后复验](source-candidate-v4-verify-after-tests.json)通过。
- Git HEAD 仍为 `e4a26d0c24311d014d478f7f92e58a88e6709b4b`，分支 `master`；本轮未暂存、提交或推送。真实申请继续暂停，最终 Submit 人工。

[轮前归档核对](before-archive-readback.json)证明源码恢复包与原 783 项逐字一致。`preservation-interim.json` 曾把 App 相对路径错误解析到 checkout，该诊断不代表 App 漂移；[正确 App 根目录复验](preservation-app-readback-v2.json)及最终保全读回均为零变化。
