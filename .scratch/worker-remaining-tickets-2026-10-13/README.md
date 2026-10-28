# 申请 worker 剩余决策与最小实现

2026-10-13。仅 checkout 交付；本轮没有重装应用、提交、推送或真实岗位操作。

## 结果

| 票 | 用户决定 | 交付边界 |
|---|---|---|
| [04 支持范围](../application-worker-next-stage/issues/04-coverage-contract.md) | 三等级，六个不同企业/岗位槽位 | 真实槽位 0/6 执行；最终 Submit 人工 |
| [06 效率边界](../application-worker-next-stage/issues/06-efficiency-contract.md) | 本轮止于缓存正确性修补 | 严格 revision；新优化先做至少五对可比运行并超过重复波动 |
| [07 故障交接](../application-worker-next-stage/issues/07-recovery-handoff-prototype.md) | A 双栏；原页停在故障点等人工核验 | 原页可用则保留 DOM、值与文件；定位不刷新、重开或重传 |
| [08 阶段验收](../application-worker-next-stage/issues/08-stage-acceptance.md) | 采纳四切片开发与停止条件 | 决策地图关闭表示规格齐备，全阶段真实验收仍未完成 |

现有 `review` 定位并交接原页。自动层保持停止，核验结论不等同于继续。
未知动作没有具体结论与来源时，重新接管按钮禁用。已报告崩溃或当前页面不可核验时进入历史核验流程。
仅同步不重做浏览器动作；保存答案不恢复暂停批次。后台协议与 Cua 执行代码复用，没有新增恢复系统。

缓存只增加 PDF 字节校验、导入时生成模块摘要/默认请求配置匹配、自定义生成器实例隔离。
旧缓存缺少新策略或摘要时，下次明确生成会 miss 并新建草稿；旧目录保留，没有后台重生成。
源码摘要保守地覆盖整个生成模块。模型 alias 的实际 snapshot 仍 unknown。
没有新增缓存索引、性能抽象、模型、并行 worker、依赖或常驻控制循环。

## 验证

| 验证 | 结果 | 证据 |
|---|---|---|
| 完整离线 | 930 passed，116 deselected；17 分 22 秒 | [日志](offline.log)、[JUnit](offline.xml) |
| 最终离线专项 | 141 passed，28 deselected | [日志](affected-final.log)、[JUnit](affected-final.xml) |
| 最终工作台/原页回归 | 11 passed，0 skipped | [日志](browser-copy-final.log)、[JUnit](browser-copy-final.xml) |
| 最终渲染与原页定位 | Chromium 153.0.8010.12；无脚本错误，观察到的请求均为 loopback | [报告](handoff-render-final.json)、[桌面](workbench-A-unknown.png)、[窄屏](workbench-A-mobile.png)、[退出状态](workbench-A-exited.png) |
| 当前代码 Ruff / 格式 | passed，166 文件格式通过 | [Ruff](ruff-active-copy-final.log)、[格式](format-active-copy-final.log) |
| JS 语法 / 命名文件空白检查 | passed | [JS](js-syntax-copy-final.log)、[空白检查](named-diff-check.json) |
| 原封存包 | 六份，1,672 文件及原清单原字节保持 | [执行前](historical-check-before.json)、[执行后](historical-check-after.json) |

完整离线之后只修改工作台 JS/CSS 和 opt-in 浏览器回归。Python 运行实现，包括最终缓存模块，保持同一源码摘要。
每轮验证冻结 126 个输入，执行后全部匹配；各代清单分别保存，不将后续字节冒充前一轮执行输入。
见 `offline-inputs-*`、`final-inputs-*`、`final-copy-inputs-*` 与[改动](changes.diff)。
默认未选用例不计入 passed，也不称为 skipped。930 和 141 有重叠，不相加为独立用例数。
11 项浏览器回归均使用合成页面。部分 UI 控制标志使用 live 分支，独立 worker 仍绑定隔离 fixture origin；真实 ATS 为零。
本轮没有重新执行原生 Cua，不能据此宣称隐藏启动全过程零闪现。

全仓原始 Ruff 扫描未通过：192 项均位于 `.scratch` 的历史重建、探针或保留副本；格式扫描列出 25 个历史文件。
原始失败日志保留于 [Ruff](ruff-final.log) 和[格式](format-final.log)。当前代码另以 `--extend-exclude .scratch` 完成全范围检查。
没有改写封存证据来消除这些错误。辅助渲染脚本随后加入；原扫描结果保留其原执行时范围。

## 原失败和本轮失败保留

原 [16 场景基线](../worker-measurement-baseline-2026-10-13/README.md)仍为 15 passed / 1 failed。
冷暖条件同时改变，不建立缓存因果收益、并行负载因果或真实模型时延结论。

PDF 错字节、旧策略、自定义生成器串用、暂停 toast、缺少交接摘要、暂停原因文案分别保留 red 日志，再做最小修补。
工作台定位测试最初在异步记录出现前取字段，保留失败并改为有界等待；不是生产交接失败。
截图脚本最初缺父目录，其后被仓库外数据边界拒绝；两份错误日志保留，再改用仓库外临时目录。
旧原型和第一轮截图分别保留在 [prototype-original.html](prototype-original.html) 与 `render-v1/`。当前原型只保留 A。

## 用户再次报告 Chrome 弹窗

原附件 SHA-256 保持。报告中的 Chrome for Testing 为 151.0.7922.71，应用注册阶段 SIGABRT；与受管 Cua Chrome 155 不同。
同一时间窗仅找到 chat “Merge frontend PR 173”的匹配启动命令和 exit 134；命令输出没有 OS PID，首次精确 PID 归因仍有限。
随后六份报告的父 PID 为 agent-browser daemon 71061；这是重复失败的直接父进程证据。
只读核对显示该 daemon 与六个 Chrome PID 均已退出。本轮没有启动该 Chrome、给其他 chat 发消息或终止其他 chat 的进程。
具体 macOS 拒绝规则尚未确认；不能把退出或其他版本浏览器通过当成规则根因证明。
末次目录扫描未见同名报告，原提取元数据仍保留；不据此推断未来不会发生。
见 [首次归因](crash-attribution.json)、[重复报告元数据](latest-chrome-reports.json)、[进程核对](repeated-crash-process-check.json)。

## 保留的边界

真实 ATS 0，新增真实模型调用 0；合成上传与生成替身另计，不建立真实发送、费用或人工效率结论。
六个真实槽位、因果效率收益、真实人工可用性、历史前置窗口阻断根因和实际模型 snapshot 均未验收。
完整离线套件耗时只属于套件，不作为岗位效率收益。
本轮只修改指定实现、回归、工作流文档和所属决策票；职业图三张私有/HITL 后继票及其未提交工作保留。
测试 worker 与渲染浏览器已通过自身句柄退出。仅保留供用户查看的静态合成原型服务器 `127.0.0.1:57431`。

封存包的 `artifact-hashes.json` 记录包内文件摘要；活动 tracker、规格与最终源码在 `delivery/` 保存副本。
后续变更需新建后继包，不改写本包。
