# CuaDriver 最小 worker 集成验收 — 2026-10-12

时区：Europe/Zurich。交付：checkout 源码；没有重新打包原生 App 或执行真实申请。

**已直接接入原生 Cua MCP，复用现有 WorkerStore、intent、确认答案、PDF 内容绑定、controller lease、发送守卫、页面回读和人工提交。Hermes 不作为运行依赖。**

## 实现

| 入口 | 交付 |
| --- | --- |
| [cua_driver.py](../../src/career_evidence_graph/cua_driver.py) | 标准库 MCP stdio transport、明确的超时/未知结果、精确窗口和唯一 tab 绑定、当前语义 ref、有限控件操作、独立标准权限 daemon 和驱动自建浏览器。 |
| [application_worker_browser.py](../../src/career_evidence_graph/application_worker_browser.py) | Cua 可选执行路径。每次点击前复用现有输入校验，补充当前许可与同一 DOM 控件核对。普通字段、附件与受限草稿保存沿用原路径。 |
| [application_worker.py](../../src/career_evidence_graph/application_worker.py)、[career_portal.py](../../src/career_evidence_graph/career_portal.py) | 传递显式 Cua 选项，保留原状态和 API。默认不开启 Cua；不增加 raw Cua 工具入口或 Submit 动作。 |
| [启用说明](../../docs/cua-worker.md) | `--worker-cua` / `--cua` 与显式点击路线、生命周期、验收和后台运行边界。 |

最小控件范围为 worker 已识别的非可编辑 `input[role=combobox]`。
Cua 只展开该控件并选择与确认答案精确对应的唯一主 frame 选项。不是任意页面操作或独立模型代理循环。

Playwright 在 Cua 浏览器中创建阻止 service worker 的隔离 context，原有 HTTP/WebSocket 守卫始终保留。
MCP 等待时只在 worker 所属线程泵送 Playwright 事件，读取 stdout 的线程不控制页面。
driver-owned、exact、mutation_allowed、唯一 URL/tab 都须成立；不设置 existing-profile grant。

## 当前通过的验证

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 完整默认离线套件 | **904 passed，96 deselected** | [日志](offline.log)、[JUnit](offline.xml)。该运行后只修正了一条被此模式排除的 browser 夹具输入；运行模块保持相同。 |
| 完整合成 browser 套件，显式启用原生 Cua | **95 passed，905 deselected** | [日志](browser.log)、[JUnit](browser.xml)。包含原有填表、附件、恢复、控制、交接与人工提交边界。 |
| 维护范围 Ruff lint / format | **passed；114 files formatted** | [lint](ruff-check.log)、[format](ruff-format.log)。没有格式化上游、历史 evidence 或无关 scratch。 |
| CLI 配置 | **passed** | worker 与 portal 的 help 显示 Cua 选项；配置回归拒绝 headless / 自定义 CDP 与 Cua 的不兼容组合及未启用的 DOM 路线。 |

全套 browser 的首次运行有 **94 passed、1 failed**。失败来自旧简历绑定夹具未声明当前必需的批量分流，错误为 `application_route_required`。
只补充合成输入 `application_strategy=batch`，没有修改生产分流守卫。
原 [失败日志](browser-red.log)、[失败 JUnit](browser-red.xml)、[夹具修改前指纹](resume-fixture-before.json)保留；修正后[单项回归](resume-fixture.log)和完整 browser 套件通过。

## 四个实际 Cua 场景

| 场景 | 实际观察 |
| --- | --- |
| [正常控件](native/native-review.json) | 系统 Chrome 中的只选不输入控件由真实原生 MCP 完成。字段回读通过，进入 `ready_for_review`，intent 清除，未进入人工接管。 |
| [非法 POST](native/native-blocked_send.json) | Cua 选项触发唯一测试 `/submit` POST，现有 guard 阻止请求；允许 POST 为零，岗位 `needs_recheck`，原 intent 保留且不重试。 |
| [重复选项](native/native-ambiguous_option.json) | 两个同名选项使岗位暂停。没有选择任何一个，没有成功填值证据，原 intent 保留。 |
| [真实独立 worker 进程](native/native-process.json) | 通过现有 launcher 启动 Cua worker。一个合成附件经过原有路径上传，自动最终提交为零。SIGTERM 后独立 socket、daemon 和浏览器进程均退出。 |

这些是合成场景。通用表单测试用 live-mode guard 检查完全离线拦截的 `.example.test` HTML；进程测试使用本地 fixture 服务。
没有真实 ATS、个人资料、模型/provider 调用，未修改 Hermes gateway、日常 Chrome 或共享 daemon。
实际版本为 CuaDriver **0.21.0**。二进制指纹与运行事实在 [native 记录](native/native-process.json)中；[系统 Chrome 安装信息](installed-browser.json)只代表安装元数据。
使用的点击路线为显式 `dom_event`，不是 trusted 点击验收；后台 trusted 拒绝没有触发静默降级。

## 其他边界回归

[test_cua_worker.py](../../tests/test_cua_worker.py)同时验证：

- 答案、PDF、暂停状态或控件在两次动作之间发生变化，下一次动作被拒绝，intent 保留。
- 外部 profile、启发式绑定、不允许变更的端点或重复 tab 不产生 Cua 点击。
- MCP 结果未知后不再次派发请求；不会通过自动重试或另一个执行方式掩盖结果。
- Cua 动作使用每次语义观察的新 ref，输入路线及执行者进入原有操作证据。

开发回归暴露并修正了退出问题：进程组 SIGTERM 会同时中断 Playwright/MCP，且重复信号可能打断清理。
现在信号只请求停止；Cua 生命周期负责关闭自身浏览器和独立 daemon，不再等待对已断开 CDP 的重复 close。
旧失败测试的精确收尾记录保留于 [daemon 清理](red-shutdown-cleanup.json)与 [卡住的测试 worker 清理](red-cdp-close-cleanup.json)。没有使用全局 kill 或关闭共享服务。

## 验收范围与后台问题

未验收真实 ATS、跨域 iframe、任意视觉点击、按钮型 combobox、效率收益、新模型循环或原生 App 安装包。
此前[原生原型](../cua-direct-probe-2026-10-12/README.md)已按原字节保留，它的其他能力不自动成为 worker 支持范围。

当前 worker 每次运行复用一个浏览器；测试为了隔离证据逐例重建，导致重复出现窗口。
目前没有实现隐藏启动或完全无窗口 Cua。推荐常驻隐藏同一浏览器，只在用户请求复核时显示，以保留原 DOM 与待提交附件。
隐藏窗口下的 Cua 绑定、启动不激活桌面和人工唤起仍需验证；当前没有再启动这类可见实验。

输入与产物完整性见 [verification-inputs.json](verification-inputs.json)、[artifact-check.json](artifact-check.json)和 [artifact-hashes.json](artifact-hashes.json)。
所属范围票为[确定通用表单支持等级与首批覆盖范围](../application-worker-next-stage/issues/04-coverage-contract.md)；本次最小实施不推定六个真实岗位已完成或完整覆盖合同已验收。
