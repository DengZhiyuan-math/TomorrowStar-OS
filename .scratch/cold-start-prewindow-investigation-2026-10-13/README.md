# 冷启动前置阻断调查 — 首轮执行

2026-10-13，Europe/Zurich。所属执行票：
[调查 Cua 冷启动前置窗口阻断](../application-worker-stability/issues/07-cold-start-prewindow-investigation.md)。

## 当前结论

**本轮 12 次原生合成采样均通过前置守卫，没有自然复现历史阻断。根因仍未确认，票据保持 open。**

本轮改动仅在独立诊断目录、执行票和导航。production 启动流程、拒绝条件、
重试规则和发送守卫均未修改。现有私人状态/附件字节摘要及 worker/browser
启动身份回读保持。没有控制现有页面或浏览器；真实 ATS、模型和最终 Submit 为零。

## 执行票与复用

按用户要求在现有本地稳定性 tracker 建立两张执行票：

- [调查 Cua 冷启动前置窗口阻断](../application-worker-stability/issues/07-cold-start-prewindow-investigation.md)：root 已领取，本轮推进此票。
- [验证真实故障恢复](../application-worker-stability/issues/08-native-fault-recovery-verification.md)：open、Assignee: none，本轮没有启动。

复用[既有前置探针](../cua-prewindow-capture-2026-10-13/debug_prewindow_probe_final.py)
及现有 `managed_hidden_chrome` / `managed_cua_browser`。
既有 30 次对照和历史失败保持原字节；本轮不把新 passed 覆盖到旧失败分母。

## 已运行的反馈命令

```sh
PYTHONDONTWRITEBYTECODE=1 TS_CUA_NATIVE_TEST=0 uv --cache-dir /private/tmp/ts-cold-start-uv run --locked --offline python scripts/run_pytest.py -q -p no:cacheprovider -m worker_browser .scratch/cold-start-prewindow-investigation-2026-10-13/debug_prewindow_probe.py --junitxml=.scratch/cold-start-prewindow-investigation-2026-10-13/native-cohort.xml
```

实际执行结果：**12 passed，238.68 s**。日志见 [native cohort](native-cohort.log)，
用例结果见 [JUnit](native-cohort.xml)和[逐样本/分组统计](trial-summary.json)。
该命令通过真实原生启动进入目标前置守卫；同类 `cua_visibility_unknown`
会使样本失败。每个样本在 `BrowserType.connect_over_cdp` 调用点主动结束，
没有 CDP 连接、context 或 target 创建。

失败采集的注入回归另执行 **4 passed、21 deselected，0.53 s**，见
[guard regression](guard-regression.log)和 [JUnit](guard-regression.xml)。
它验证实际拒绝调用点的记录与清理顺序，是原生边界替身，不是历史窗口自然复现。

## 本轮采样变化

旧采样器先按 AppKit 的新应用列表筛选 PID，可能漏掉登记前的窗口。
本轮采样器仅从本次唯一 profile 的 `SingletonLock` 取得 Chrome PID，
直接按该 owner 过滤 WindowServer 元数据；不依赖 AppKit 登记才开始观察。
已有 Chrome/Cua 的 PID、标题、屏幕像素不进入本轮采样记录。

这项改动仅用于诊断。没有改变生产 launch、hide 或 `list_windows` 行为。
本轮在 4 个样本中观察到“profile PID 已出现、AppKit 尚未登记”的时间边界，
没有观察到该 PID 的屏幕窗口。见 [sampler source](debug_window_sampler.swift)。

| 新增离线负载 | 样本 | 目标前置拒绝 | 屏幕窗口观察 | 观察到登记前 PID 的样本 |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 4 | 0 | 0 | 2 |
| 1 | 4 | 0 | 0 | 0 |
| 2 | 4 | 0 | 0 | 2 |

一次只启动一个自有 Chrome/Cua，新增负载最多两个离线进程组。
相同 5 s warm-up 位于实验开始前，未给 production startup 增加等待。
各负载组交错执行。负载套件在样本结束时按自有进程组停止，部分日志计为中断，
不计为完整离线回归通过。“0 新增负载”不代表整台机器空闲。

实际平均采样率约 **34–64 Hz**，最大间隙约 **878 ms**。
登记前观察得到补充，但短于采样间隙的窗口仍可能漏采；取得 SingletonLock PID
之前的状态也未绑定。不能据此声称逐帧零闪现或排除稀有窗口。
本轮没有建立或否证并行负载的独立因果关系。

原生版本与实际 driver fingerprint 保存于 [runtime versions](runtime-versions.json)
和各样本 runtime/summary。当前 Chrome 155.0.8059.40，CuaDriver 0.21.0。
诊断代码、采样器与生产 Cua 模块固定在 [execution inputs](execution-inputs.json)。

## 准备失败与保全

首轮探针在采样器仍编译时启动，因二进制缺失退出，未进入 Chrome 启动。
这是一项工具准备失败，不是目标前置阻断。原日志和输入副本留在
[native smoke](native-smoke.log)、[preparation failure](preparation-failure.json)
及 `debug_prewindow_probe_before_build.py`。后续使用新的样本目录，没有覆盖失败。

沙盒首次拒绝只读 `ps`。随后在用户授权范围内，从沙盒外记录现有进程身份；
私人保护记录留在独立私有临时目录，不写入系统公开文档。
首次普通 Python admission import 生成的 bytecode 已保存在私有诊断输出，
并从旧包移除；旧清单和原文件不变。见 [cache cleanup](admission-cache-cleanup.json)。

自有 Chrome/Cua、负载和采样器均退出，见 [process check](process-check.json)。
前置专项的 runtime `closed=false` 来自主动在连接前结束；不把它当成完整启动成功。
`cleanup_complete`、sampler exit 和独立进程核对证明本次资源已清理。
未对被复用的 PID 或既有进程发清理信号。

production 源码、历史包、其他票据及现有资源的最终检查见 [postcheck](postcheck.json)。
本目录另行封存，不向历史诊断目录重跑。

## 下一步与停止边界

继续关注首次前置拒绝的原始 `windowless_before` 条目，连同 PID/启动代次、
hide 回执、AppKit 快照、WindowServer 时间边界和 Cua daemon 身份。
当前 production 失败采集保留首次 Cua 窗口字段、时间和启动身份；独立
WindowServer 采样仅在本次诊断入口中执行。下一次自然失败必须保留首次结果，
不能用失败后消失的窗口列表替代它。

当前没有自然失败可用于缩小场景、鉴别原因或验证修补。因此没有改动生产启动逻辑。
按 [diagnosing-bugs](../../../../.codex/skills/diagnosing-bugs/SKILL.md) 的
“Do not proceed until you have reproduced and minimised.”，本轮停在有界复现与采集，
不把未复现当作修复成功。冷启动票保持 open；真实故障恢复票保持未领取。
