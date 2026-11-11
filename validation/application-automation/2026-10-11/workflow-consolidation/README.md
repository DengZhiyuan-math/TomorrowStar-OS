# 运行流程整理与优化回归

2026-10-11。历史证据已汇总到[当前运行流程](../../../../docs/application-worker-workflow.md)。
旧失败、分轮 JSON 和历史源码清单保持原样。
本轮使用合成资料；不调用模型，不填写或上传新的真实资料，不执行 Submit。

## 改动

- 通用平台的冲突同步使用已绑定的通用岗位 URL。保留外部笔记修改，检查新 revision；不触发浏览器动作。
- 主动释放或用户关闭页面后清理该页的草稿值、上传句柄、公开请求缓存和 guard 引用。其他页面、磁盘记录及答案库保持原有生命周期。
- 没有可自动执行的岗位时，工作台禁用开始／继续。显示人工接管和自动填写结束时的服务端核验；未知保存或上传结果有具体提示。
- worker 失联时标记页面状态来自历史记录。核验后 queued 的岗位仍可恢复，即使人工交接撤销命令尚未执行。
- README、工作流和平台历史评估链接到当前能力与证据入口。

## 回归

| 检查 | 结果 | 日志 |
| --- | --- | --- |
| 全量离线，排除 worker_browser / live_model | 777 passed / 37 deselected，141.44 秒 | [offline.txt](offline.txt) |
| 通用、Lever、Greenhouse、托管 ATS、PDF、Ashby 浏览器回归 | 36 passed / 47 deselected，133.55 秒 | [browser.txt](browser.txt) |
| 最终工作台失联与恢复按钮检查 | 1 passed，18.10 秒 | [ui-stale-green.txt](ui-stale-green.txt) |
| Ruff 检查 / 格式 | 通过，181 文件已格式化 | [检查](ruff-check.txt) / [格式](ruff-format.txt) |
| worker.js 语法、本地文档链接、diff 空白 | 通过 | 本轮命令检查 |

36 项浏览器回归在最后的失联提示细化前完成；最终 UI 用例又通过。
该 UI 用例已经包含在 36 项中，不能相加为 37 个独立用例。
离线排除项与浏览器排除项分别来自不同命令，不能当作通过或互相抵消。
机器可读结果见 [results.json](results.json)，最终源码清单见 [source-hashes.json](source-hashes.json)。

新增通用同步用例先因 `unsupported_platform` 失败，修正后通过。
新增合成页面释放用例先发现 `DraftSession` 未回收，修正后 5 个 Ashby 浏览器用例通过。
新增工作台用例先发现继续按钮仍启用，修正后通过；人工接管提示、页面保留及零最终提交均核验。
继续细化失联情况时，新增期望先失败；[原始失败](ui-stale-red.txt)保留。
修正后确认：worker 退出时不将历史 `page_open` 显示为实时证据；人工核验后恢复按钮可用。

## 当前真实运行

历史检查点保留，但旧 PID 和 9231 调试端口没有响应。
不能确认真实页面仍打开。服务端读取到旧检查点的 `TargetClosedError`；退出原因未确定。
本轮没有停止或重启旧招聘浏览器。只恢复 8769 工作台服务来读取原记录。
实际招聘浏览器没有启动；批次仍 paused，未新增人工提交确认或接收回执。
恢复服务后未恢复自动填写，旧运行不改写为新版本验收通过。

## 复验命令

```sh
UV_CACHE_DIR=/private/tmp/tomorrowstar-uv-cache uv run --locked \
  python scripts/run_pytest.py -q -m 'not worker_browser and not live_model'
UV_CACHE_DIR=/private/tmp/tomorrowstar-uv-cache uv run --locked \
  python scripts/run_pytest.py -q -m worker_browser \
  tests/test_generic_worker.py tests/test_application_resume.py tests/test_hosted_ats.py \
  tests/test_lever_worker_browser.py tests/test_greenhouse_worker_browser.py tests/test_ashby_drafts.py
UV_CACHE_DIR=/private/tmp/tomorrowstar-uv-cache uv run --locked ruff check .
UV_CACHE_DIR=/private/tmp/tomorrowstar-uv-cache uv run --locked ruff format --check .
node --check src/career_evidence_graph/portal_static/worker.js
git diff --check
```
