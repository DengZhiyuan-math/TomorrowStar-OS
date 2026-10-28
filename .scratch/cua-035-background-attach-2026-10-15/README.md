# CuaDriver 0.35.2 后台附着调查与启动准入修复

日期：2026-10-15，Europe/Zurich。执行人：root。
对应[执行票](../application-worker-stability/issues/10-cua-035-background-attach.md)。

**根因已定位，修复了注定失败的浏览器启动；完整后台附着尚未恢复，票保持开放。**
worker 创建的全新 profile 在 Cua 看来仍属于 externally created existing profile。
0.35.2 在发现端点之前检查前台风险，尚未取得独立 profile 授权就拒绝。
不是 MCP 关闭回归、权限缺失或错误 PID 引起的本次拒绝。

## 固定输入与准入条件

实际驱动为官方签名 **0.35.2**，二进制 SHA-256：
`20417e3c7168f3554bf97192e1f6d245844b4db694fb6d87c15b83f0609d94ad`。
合成 Chrome 为 **155.0.8059.40**。固定上游提交为
`ad694f82aaaa12e67257e4510837fc1f6cfc9484`，MIT；[源码副本](upstream/LICENSE.md)
未修改。[输入摘要](execution-inputs.json)绑定运行脚本、源模块和采样器。

- 实际 [browser_prepare schema](browser-prepare-schema.txt)说明后台拒绝条件。
- [原生实现](https://github.com/trycua/cua/blob/ad694f82aaaa12e67257e4510837fc1f6cfc9484/libs/cua-driver/rust/crates/cua-driver-core/src/browser/prepare.rs#L984)
  在端点发现前执行 `existing_profile_background_check`。
- macOS 仅在目标已为前台，或确认窗口在另一 Space 时允许该分支。
  Space 归属未知也不放行。本轮不改变 Space、不激活窗口、不请求 foreground。
- [端点访问分类](https://github.com/trycua/cua/blob/ad694f82aaaa12e67257e4510837fc1f6cfc9484/libs/cua-driver/rust/crates/cua-driver-core/src/browser/engine.rs#L176)
  要求独立的 existing-profile grant 或 driver-owned 生命周期；CDP 端口所有权本身不够。
- 驱动自有 `isolated_new` 会直接 spawn 并打开 `about:blank`，没有无窗口后台启动参数。
  它不满足本轮约束，因此未执行，未宣称安全。

## 可复现对照与保留失败

所有原生原始 RPC、stderr、身份、窗口/Space 采样和前后保全快照均位于
独立持久私有目录。见[原始文件绑定](private-raw-binding.json)。未使用临时目录作为原始证据存储。

| 检查 | 实际结果与边界 |
| --- | --- |
| 原实现最小复现 | `reproduce.py`：1 failed，6.89 秒；明确 `background_unavailable`，在原生附着前停止，零点击。源码输入为修复前模块。 |
| 同一 PID/window/Space 对照 | `control.py`：1 passed，7.87 秒；existing-profile 拒绝 → 被动检测 `already_prepared`、零副作用 → 绑定仍拒绝 `browser_consent_required`。 |
| 精确权限负对照 | 同一会话请求错误窗口或本次 harness PID，都被精确 manifest 拒绝；没有修改清单或全局授权。 |
| 准入回归 red | [测试输出](admission-red.log)：旧实现继续调用浏览器启动，新增测试失败。 |
| 准入回归 green | 最终相关回归 [23 passed / 12 deselected](affected-final.log)；包括原有关闭、分帧、未知结果不继续派发的测试。 |
| 真实驱动准入 green | [0.125227 秒](native-admission-green.json)，浏览器、daemon、socket、profile、临时目录均创建0个；写入明确私有诊断。 |
| 完整离线回归 | [940 passed / 119 deselected，125.40 秒](offline-full.log)。未选入的 browser/native 场景没有记为通过。 |

首轮 control 的端点、授权和负对照已经运行，但其测试把自有隐藏 anchor 误计为0页，
因此以 1 failed / 7.96 秒结束。原始日志和[原测试输入](inputs/control-first.py)保留；
在新空白目录修正为1个 `about:blank` anchor 后复跑，没有修改原失败或放宽守卫。
报告只将后继对照计为通过。

## 最小修复与未完成项

checkout 在读取真实 manifest 后，对已确认不兼容的 **0.35.2** 提前返回
`cua_background_unavailable`，记录 `admission=background_unavailable` 和无资源待清理的
`closed=true`。没有创建随后必然被拒绝的 Chrome。此版本判断只针对已验证版本；
其他版本不因此获得兼容性声明。

没有修改上游守卫、权限、发送守卫、MCP 转发或未知结果策略。没有尝试省略策略后继续操作，
没有前台 fallback、自动降级或会话重建重发。修改只在 checkout，已安装 TomorrowStar 和
CuaDriver 保持原样。

完整附着仍需要上游提供可证明的无前台副作用、driver-owned 后台生命周期，
或其他经过同等验证的受支持接口。当前版本未提供该条件，不能在本轮约束下将它算作已修复。
真实浏览器变更回执丢失、生产 ATS 和上游新版本兼容性均未验收。

## 保全、检查与复跑

[保全回读](preservation.json)核对全部3,736个旧封存文件、旧持久私有诊断、
现有 worker/浏览器/Cua 身份及私人页面/附件/设置摘要；检查全部自有 PID 与 profile/socket
父目录均已退出。所有三轮原生采样的活动 Space 保持一致，自有 Chrome 激活及上屏样本为0。
隐藏窗口的 Space membership 可能为空，不将其当作“已证明在另一 Space”。
这是离散采样，采样间隔上界见回读，不声称逐帧零闪现。

源码只改 `cua_driver.py` 和一条回归测试；其他源文件与已安装应用回读保持。
[最终 lint/格式](lint-final.log)通过；首轮 SIM117 样式失败保留在 `lint-first.log`。
完整 suite 使用的测试原字节另存 `inputs/test_cua_worker-fullsuite-input.py`；
之后只合并等价的 `with` 语句，最终测试文件重新通过相关23项回归。

复跑使用 checkout launcher，必须改为新的空白持久私有目录；本包封存后不写入。
原生对照需明确授权，仅操作自己创建的资源。原始红样本依赖修复前模块；
当前 checkout 的预检会在原生启动前停止。

```sh
uv run --locked python scripts/run_pytest.py -q tests/test_cua_worker.py tests/test_cua_mcp_lifecycle.py
```

真实 ATS、模型、上传、最终 Submit、现有运行控制动作均为0。
