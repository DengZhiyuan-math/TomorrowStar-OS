# 31 号：限时执行与真实阶段报告合成演练

日期：2026-10-19（Europe/Zurich）。责任：`01a150ef/bounded_protocol`。
范围：[31 号票](../single-job-application-flow-2026-10-16/issues/31-bounded-execution-protocol.md)。
规则：[限时执行与停止规则](../../docs/single-job-flow.md#限时执行与停止规则)。

仅执行已有离线夹具、实际本地存储/门禁和固定 stdio 子进程。未启动 App、浏览器、
真实服务或真实申请；未读取个人资料；未修改全局配置。公开结果不含私人状态、路径或测量。
原字节、确切命令、UTC/墙钟、逐动作日志、合成快照和六阶段停止报告由执行者在任务独立临时证据目录保留。

| 核验项 | 结论 |
| --- | --- |
| 预检 10 分钟、同起点总窗口 20 分钟、用户明确覆盖优先 | 规则已落实 |
| 累计时间/故障跨重开与交接保留；不以修复票重置 | 规则已落实；补充演练沿用原起点 |
| 冷启动预检缺失/未核验 helper 时拒绝执行与 fallback | 合成通过 |
| 两次读取另一合成岗位的 URL 后停止，无第三次读取或字段点击 | 合成通过 |
| 首次未知结果保留 needs_recheck，重开不重放；合成传输只 dispatch 一次 | 合成通过 |
| 缺材料/资格/国家/发送确认时阻断，不推定同意 | 合成通过 |
| 停止报告含真实阶段、未决动作、最后有效证据、保留类别及继续条件 | 已核对 |
| 18/20/23/11 与 workflows 链接同一规则；用户中止优先 | 已核对 |
| 文档、命令及本地链接检查 | 通过 |
| 真实申请恢复/外站填写/上传/Submit | 未执行 |

复用的命令选择（在仓库根目录；缓存使用任务临时目录，离线运行）：

```sh
UV_CACHE_DIR=/private/tmp/ts-ticket31-cache UV_OFFLINE=true uv run --locked python scripts/run_pytest.py -q tests/test_cua_owned_runtime.py::test_app_never_executes_or_falls_back_from_a_bad_bundled_driver tests/test_application_flow.py::test_worker_reference_retains_unknown_outcome_without_retrying_external_actions tests/test_application_flow.py::test_worker_preparation_requires_current_materials_country_send_and_hard_facts tests/test_cua_worker.py::test_mcp_unknown_result_does_not_dispatch_again
```

另外实际调用现有 `CuaDriver.fill` 两次，将唯一 tab URL 固定为另一合成岗位：
两次均在只读归属检查处抛 `cua_binding_ambiguous`，没有发出点击；执行者随后停止。
另对真实 `ApplicationFlowService.observe_worker` 注入错误 batch 两次，均被拒绝且保存字节不变。
这是可执行操作契约的受控演练，不是新增调度器或自动计时实现，也不声称产品会自动执行本规则。
10/20 分钟上限没有被等待耗尽；它们是操作限制，不是性能测量或用户接受的 SLA。

冷启动演练验证候选门禁，未复现历史原生 Chrome 崩溃；未知字段演练使用合成状态/传输，
未观察真实外站。等待确认测试中的后续批准只属于固定夹具，不能算用户批准。
真实 18/20/23/11 验收及材料人审均保持原门禁。

途中问题：默认 uv 用户缓存目录被沙盒拒绝；用任务临时缓存并保持离线后完成。
该问题不要求用户处理，也未通过扩权或改全局设置解决。
