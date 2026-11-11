# CuaDriver 0.35.2：真实 MCP 关闭修复复验

2026-10-15，Europe/Zurich。固定已升级的 CuaDriver 0.35.2 和已交付客户端源码 `06ca93a80f960a4f8b7dd16e999dc0ebef06b902fcc65da4a13877cd03180f4e`；本轮没有修改该源码或已安装 TomorrowStar 应用。

**纯传输后继4项通过。浏览器预检有1次失败，完整保留。** 不把只读传输通过推成浏览器变更回执丢失或新版完整 worker 验收。

## 执行账本

| 阶段 | 实际结果 | 未执行 / 未验证 |
| --- | --- | --- |
| 0.21.0 首轮原生记录 | 后端先退出2项通过，协议夹具 ref 绑定1项失败 | 丢失点击回执未执行 |
| 0.21.0 第二轮准备 | 用户要求升级前只建立准备目录 | 未启动该轮服务或浏览器 |
| 0.35.2 浏览器预检 | `browser_prepare` 拒绝，pytest 1 failed，8.97 s | 四项正文场景均未到达，点击未执行 |
| 0.35.2 纯传输后继 | 单个 pytest 中4项检查通过，1.12 s | 没有浏览器附着或真实变更 |

0.21.0 的首轮结果和执行输入保存在[前代目录](../cua-mcp-native-verification-2026-10-14/cohort-01/native-run.log)。它使用 query 的语义快照完整但 refs 为空；未猜测 ref 或点击。第二轮仅准备了取消只读 query 的对照，随后遵循用户升级要求，没有执行。

新版[浏览器预检失败](native-run.log)发生在创建 Cua 绑定时：驱动明确拒绝可能把 Chrome 带到前台的附着。没有把拒绝解释成 MCP 解码错误，也没有放宽后台策略。manager 的 success flag 为 false；[独立资源回读](resource-check.json)确认其私有 socket 与自有进程已退出，不能只凭该 success flag 推断进程仍活。

## 新版纯传输结果

[完整结构化收据](transport-only/verification.json)、[输出](transport-only/native-run.log)和[JUnit](transport-only/native.xml)记录：

| 真实原生场景 | 结果 |
| --- | --- |
| 原生 MCP 后端先退出，输出 EOF | 后端预期 SIGTERM exit=-15；close 0.000057 s，正常关闭 |
| 原生 MCP 后端先退出，另一输出写端仍开放 | 后端 exit=-15；close 0.099115 s；写端在断言后才释放 |
| 正常原生协议响应 | 4帧与 CuaDriver 实际输出逐字节一致；后端与实验 relay 正常退出0 |
| 成功只读回执被实验 relay 丢失 | 原生 `check_permissions` 请求只收到1次；再次派发与后续点击尝试均返回 `cua_result_unknown`；原生点击0次 |

真实 native MCP 命令保持 `cua-driver mcp --socket PRIVATE_SOCKET`。关闭场景直接启动原生可执行文件；持有额外输出写端是实验故障注入，不声称是驱动的自然异常。原生 Popen 子进程退出后保持父端 stdin 开放，再按原2秒期限检查 close；未发新的关闭请求，线程及流回收。

协议与回执丢失使用明确标记的实验 relay。它记录原生请求/响应字节，只在丢失场景吞掉一帧已成功返回的只读回执，再终止本轮原生 MCP 子进程。客户端在看到 EOF 后进入原失败状态；重复调用和新的变更尝试均未达到 relay 或驱动。该后继只验证通用 transport 的失败门，不验证真实点击或上传的副作用未知场景。

该后继服务只授权 `check_permissions / list_windows / end_session`，资源范围仅为本轮合成进程 PID。没有浏览器附着、截图、输入、页面或附件操作；没有真实 ATS 或模型调用。协议请求为正常 MCP 握手、工具列表与权限读取。[scope与真实权限](transport-only/native-scope.json)记录新 daemon 身份和授权；没有扩大服务工具许可来允许后续点击。

[执行输入](transport-only/execution-inputs.json)与[执行后回读](transport-only/input-readback.json)一致。[实验工具](transport-only/verify_transport.py)及[relay](transport-only/native_transport_tap.py)属于本轮诊断，不修改产品协议实现。[定向检查](transport-only/harness-lint.log)通过。

## 保全和留存限制

[保全回读](existing-protection-summary.json)确认当前复验期间原有进程身份、私人 worker/页面记录、附件与设置摘要保持。3,657个历史封存文件、44个前代新增记录和127个源码输入保持；TomorrowStar 应用1,419文件保持。CuaDriver 安装与回退包另按[升级回读](../cua-driver-upgrade-readback-2026-10-15/README.md)核验。

[资源核对](resource-check.json)确认所有本轮已记录原生 PID、独有 profile/socket 均无存活匹配。关闭的是本轮私有服务，没有停止现有 daemon、worker 或浏览器。

0.21.0 旧轮的原始私有临时目录在中断后已不可读取；当时结果、失败日志、输入脚本及公开摘要仍在。该缺口不通过新执行覆盖旧记录。本轮原始数据改存持久私有目录，[摘要绑定](private-evidence-binding.json)已核对。个人原始材料和原有附件未复制到系统仓库。

浏览器预检的拒绝由[独立兼容性票](../application-worker-stability/issues/10-cua-035-background-attach.md)继续跟踪；不修改旧冷启动根因结论。后继执行应新建目录，并使用新的专有 socket / 输出位置。本包封存后只读。
