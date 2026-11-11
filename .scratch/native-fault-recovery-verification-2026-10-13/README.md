# 真实故障恢复验证 — 隔离执行记录

2026-10-13，Europe/Zurich。所属票：
[验证真实故障恢复](../application-worker-stability/issues/08-native-fault-recovery-verification.md)。

**五类隔离故障均有通过证据。首轮原 crash 回归的两次失败仍未解释，票保持 open。**
本轮未修改 production 源码、原期限或恢复规则。不能把后续 passed 覆盖到失败分母。

## 实际故障与结果

复用 `tests/worker_preview_support.py` 的独立 worker、专用 Chromium profile、
loopback ATS、临时岗位、答案库和合成 PDF。使用当前 checkout launcher。
新增探针见 [debug_fault_recovery.py](debug_fault_recovery.py)。

| 实际故障 | 观察结果 | 关键核验 |
| --- | --- | --- |
| 当前 Page 原生关闭 | passed | 只停止该岗位；另一岗位继续上传；原页交接和仅同步后仍是同一 DOM、字段值、File 对象 |
| 当前 renderer 通过原 CDP 导航入口崩溃 | passed | 收到实际 crash 事件；约 0.47 s 完成诊断；另一岗位继续，原页与附件保留 |
| worker 在上传前 `SIGKILL` | passed | intent 已落盘但尚未执行浏览器上传命令；ATS 上传账本为 0；旧 attempt 保留 |
| ATS 已收到附件、响应未返回时 worker `SIGKILL` | passed | 接收账本及内容摘要核验为 1；未知 intent 保留；重启和明确继续后仍为 1，无重传 |
| 相同时点浏览器主进程 `SIGKILL` | passed | `browser_disconnected`、整批暂停、当前页面不可声明有效；不自动重连；未知上传仍只有 1 次 |

进程通过 PID、父子关系、启动时间和唯一 profile 绑定。worker 故障仅向该
`Popen` 子进程发送 `SIGKILL`；浏览器故障在启动身份重新匹配后发送信号。
不从同名进程、旧 PID 或 `TargetClosedError` 推定归属。
逐阶段检查点、实际进程身份和请求账本见 [process trials](process-trials/)
及 [process summary](process-summary.json)。五类不是五个统计独立的生产样本。

发送前探针在 production `authorize()` 成功落盘后，用测试专用 rendezvous
阻止浏览器命令，再真实杀死 worker。它不是异常回调模拟。
接收后探针复用 ATS 原处理器：先记录收到的真实 HTTP body，再扣留响应。
故障后关闭该连接，不向浏览器交付成功响应。这里的“收到”只指合成 ATS 账本。

## 检查点恢复与原页边界

三种进程故障后的新运行均保留旧 run、intent、attempt 和核验记录，且保持暂停。
heartbeat 和仅同步均不触发浏览器动作。未解决 intent 的 `recheck` 被
`action_unresolved` 拒绝。错误 PDF 版本被 `file_changed` 拒绝，旧 intent 不丢失。
结论先保存；独立输入核验后才清除活动 intent；批次仍须明确 `resume`。

新页没有历史 DOM、JS 标记或 File。首次继续时，已有核验结果在新页不可见，
因此停在 `recovered_result_not_visible`。本轮没有宣称恢复了退出进程中的原页。
脚本随后只在新建合成页填入已核验字段，再明确 recheck：

- 发送前故障已证明旧上传未发生，下一必要上传执行一次，使用新的 attempt。
- 接收后故障已证明附件收到；新页附件不可见时继续停止，上传次数仍为 1。
- 原 attempt 始终保存在 action resolution 中，没有改写为新动作。

人工交接接口的观察由合成脚本执行，未冒充真人操作或人类 Acceptance。
未知 autosave 的补充回归只证明发送守卫阻断并保留原页；本轮真实服务器故障
发生在附件上传路径，不能推导其他 ATS 写入路径已得到真实故障覆盖。

## 回归、失败与中止

| 执行 | 结果 | 性质 |
| --- | --- | --- |
| [当前 native 回归](reused-native.log) | 13 passed、2 failed | 页面关闭、共同故障、原页/File 保留及已完成上传恢复；两次 crash 失败保留 |
| [检查点回归](checkpoint-regression.log) | 79 passed | 当前源码的离线确定性检查 |
| [进程 cohort 01](process-cohort-01.log) | 1 passed、1 failed | 探针重复 spawn 的准备错误；尚未向该 worker 注入故障 |
| [进程 cohort 02](process-cohort-02.log) | 3 passed、1 failed | 浏览器故障已被观察；新运行提交前，探针误将旧错误判为失败 |
| [浏览器恢复复验](process-cohort-03.log) | 1 passed | 仅修正诊断观察条件；真实故障、暂停和恢复核验通过 |
| [renderer 复验](process-cohort-04.log) | 1 passed | 保留 1500 ms 事件及 2 s 诊断期限 |
| [原 crash 最小复验](crash-minimal.log) | 1 passed | 事件约 1.40 s，接近 1.5 s 期限 |
| [原 crash 追加复验](crash-original-followup.log) | 4 passed | 原两个时点、原断言；事件约 0.31–0.38 s；不替换首次失败 |
| [单页对照准备](crash-methods.log) | 4 setup failed | 默认浏览器缓存缺少 executable；未启动浏览器，未安装新依赖 |
| [已安装浏览器单页对照](crash-methods-bundled.log) | aborted | 导航分支 1 passed；直接 `Page.crash` 无事件并挂起，中止；其余 2 例未执行 |

JUnit 的已完成 testcase 统计不能代表中止 cohort 全部通过。
机器汇总见 [cohort summary](cohort-summary.json)，保留各执行的退出码及中止标记。
准备失败和诊断观察失败不计为产品修复，也不混入真实故障的通过分母。

首轮的两个 crash 失败分别为：1500 ms 内没有 crash 事件，以及结果被保留为
`browser_result_unknown` 而非 `page_crashed`。相关原始日志及 JUnit 保持原状。
最小复验和后续重复说明它们间歇发生，尚未确定原因。
导航入口延迟、命令期限与事件边界、worker 事件处理三个解释未形成充分鉴别。
没有据此修改 production handler、加启动等待、放宽期限或自动重试。

原反馈命令使用当前 launcher、明确 `worker_browser` marker、locked/offline 环境：

```sh
PYTHONDONTWRITEBYTECODE=1 TS_WORKER_REPORT_DIR=.scratch/native-fault-recovery-verification-2026-10-13/new-trace uv --cache-dir /private/tmp/ts-native-recovery-uv run --locked --offline python -B scripts/run_pytest.py -q -p no:cacheprovider -m worker_browser tests/test_worker_crash_injection.py
```

这是复现入口示例。封存后不得向本目录重跑；后续使用新的证据目录。
`debug_crash_methods.py` 是诊断输出，直接 crash 分支已出现挂起，不作为验收入口。

## 保全与输入

实验结束时，现有私人状态、附件与设置摘要一致，现有 worker/browser 启动身份均保留。
私有前后记录独立保存，未将私人内容或摘要写入此包。
所有本轮专用 worker/profile 已退出，见 [process check](process-check.json)。
128 个源码/测试/launcher 文件及 1030 个历史包文件无变化，见 [postcheck](postcheck.json)。
诊断脚本、失败版本和打包时输入摘要见 [execution inputs](execution-inputs.json)。
Chromium 153.0.8010.12；Python、已加载模块和依赖版本另存该输入文件。
诊断代码格式整理未更改 production 输入；之前探针失败的版本保存在 `input-versions/`。

真实 ATS、模型、自动最终 Submit 动作及最终提交请求均为 0。
系统 sleep/wake 为 **unobserved**。本轮没有对共享主机执行休眠、唤醒或主机级故障。
挂起诊断的首次只读定位检查审批超时；一次重试成功。该检查没有发送清理信号。

## 剩余工作

保留首轮 crash 失败，继续在新的隔离目录核对首次事件、CDP 命令交付、
命令中断和 worker 事件消费边界。当前没有证据支持根因或修复完成。
冷启动票保持原状态，本轮未续跑或修改其封存结果。
