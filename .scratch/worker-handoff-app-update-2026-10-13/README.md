# 故障原页与缓存修复 — 当前应用更新

2026-10-13。按用户授权更新 `/Users/zhdeng/Applications/TomorrowStar.app`。
应用未启动；现有 worker、浏览器未重启或接管。真实 ATS 和新增真实模型调用均为零。

## 安装范围

复用原包，只更新八个必要引擎文件：缓存生成模块、计量模块及其 worker/runner/portal 接入、Cua 诊断采集、工作台 JS/CSS。
原生窗口、Python、Playwright、pyee、greenlet 及其他依赖继续复用。原包缺少计量模块，不能仅替换缓存文件。
安装后的全部 53 个引擎摘要匹配。完整目录差异只有八个引擎文件及清单、资源签名、可执行签名三个文件。
见 [允许差异](installed-delta.json)、[实际依赖版本](dependency-readback.json)与[安装清单](installed-final-manifest.json)。

原应用完整备份：

`/Users/zhdeng/Applications/.TomorrowStar-backups/2026-10-13-155619-93d5193b/TomorrowStar.app`

备份的 1,420 个文件/链接与原包的字节、链接及文件权限记录一致，严格签名有效。
暂存包、安装包及原包备份均完成 `codesign --verify --deep --strict`。
替换前再次核对原包版本、暂停数据和进程身份；失败回滚路径保留。
见 [安装收据](installation.json)、[原包文件记录](original-app-files.json)与[执行日志](installation.log)。

## 针对性回归

| 运行 | 结果 | 实际输入 |
|---|---|---|
| 关键原页/附件回归 | 1 passed | 暂存 App 的引擎；[日志](original-file-tracer.log) |
| 包内离线专项 | 154 passed，57 deselected | 缓存、计量、worker、恢复、Cua、portal；[日志](package-offline.log)、[JUnit](package-offline.xml) |
| 包内合成浏览器 | 14 passed，0 skipped | 原页、未知动作、暂停答案、冲突同步及 Cua 交接替身；[日志](package-browser.log)、[JUnit](package-browser.xml) |
| 已安装引擎再回归 | 3 passed，0 skipped | 实际安装路径加载代码；[日志](installed-browser.log)、[JUnit](installed-browser.xml) |
| 原生包搬移与内置运行时 | passed | 仓库外合成数据，从 `/` 使用内置 Python；[报告](bundle-acceptance.json) |
| 当前代码 lint / 格式 / 空白 | passed | [Ruff](ruff-active-final.log)、[格式](format-active-final.log)、[空白](diff-check.log)；新交付脚本另有[检查](helpers-lint-final.log) |

实际包代码由显式 loader 加载，未使用 checkout 模块冒充包内结果。
[暂存来源](staged-execution-source.json)和[安装来源](installed-execution-source.json)记录模块路径、摘要与 manifest。
浏览器行为回归使用锁定 checkout 的 pytest/Python；实际包的内置 Python、依赖与服务器另由搬移验收覆盖。
两种 Python 均为 3.13.14，依赖版本逐项匹配。所有包内运行禁止写 `__pycache__`，验收后签名仍有效。

新增回归在文件已选定、字段已填写后，实际触发一个未经核验的保存 POST。发送守卫阻断请求，岗位进入 `needs_recheck`。
继续若干 worker tick 后，仍是同一个 `Page`、同一个 `document` 和同一个文件输入 `File` 对象。
姓名、邮箱、文件长度保持；没有自动 Submit、重填、刷新或重传。人工 `review` 后同样保持原文档和文件，岗位仍等待重新核验。
另覆盖未知上传 intent 保留、先记录结论再恢复、页面崩溃/退出提示、答案补齐后整批仍暂停以及冲突只同步。

全部浏览器测试为独立 headless、离线或 loopback 合成环境。Cua 交接使用替身，本轮没有重新显示系统 Chrome 的原生 Cua 窗口。
上述运行有重复覆盖，不相加为独立案例数；未选用例不计入 passed。
本轮没有新生产引擎行为修补；新增永久回归验证原有原页/文件保持保证，再交付前一轮已验证修复。

## 现有状态与进程

安装前、安装后和最终回归后，175 个状态、答案、PDF 文件的聚合摘要完全相同。
暂停 `run.json` 与 `portal.json` 的字节摘要保持；没有修改原批次、页面记录或附件。
既有 Chrome 主进程 PID 701、父 PID 和启动时间保持，未发任何控制信号或页面操作。
实际已有 App 未运行；检查点中的旧 worker PID 27607 已退出，未由本轮重启。
`page_open` 是历史记录，当前原页是否仍可用未做真实 ATS 核验；不能把历史记录当成当前 DOM 恢复。
见 [安装前保护记录](protected-before.json)、[安装收据](installation.json)及[回归后回读](protected-after-regression.json)。

所有测试 worker/浏览器只在隔离环境创建并由各自夹具关闭。没有操作现有 Chrome 或共享 Cua 会话。
下次由用户打开 App 才加载新代码；暂停批次仍须人工核验历史进度，再明确继续。

## 原证据与验收边界

七份原封存包合计 1,816 个文件及各自原清单保持；含上轮交付、16 场景基线与 Cua 失败/诊断。
原 16 场景的 15 passed / 1 failed 不改写。见 [历史核验](historical-check.json)。
零真实 ATS、零新增真实模型调用；合成上传和模型替身不建立真实覆盖、费用或人工效率结论。
六个真实槽位、因果效率收益、历史前置窗口阻断根因和原生 Cua 本轮视觉验收继续未验收。
没有提交、推送、扩大真实试点或改动职业图/私有 HITL 票。

本目录按 `artifact-hashes.json` 封存。后续改动需新建后继包；原应用备份继续保留。
