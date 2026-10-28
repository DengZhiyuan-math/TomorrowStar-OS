# 岗位筛选与平台评估验证

日期：2026-10-10。使用当前 checkout 的 Python 3.13 和锁定依赖。保留既有未提交工作；未提交、暂存、推送或发布代码。相关源码见 [SHA-256 清单](source-hashes.json)。

## 已实现

- AI / ML、量化标题和明确方向筛选；跨字段多词 AND 搜索；可选筛选优先排序。
- 只读展示平台兼容性、未知资格、截止日期、岗位重复和明确语言冲突。原求职状态保持不变。
- 复用原答案库的已确认全局 CEFR 信息。推断、冲突或范围限定的值不参与全局排除。
- 语言硬条件冲突时禁用批次勾选；后台在写入 PDF、创建批次和启动 worker 前重新检查。
- 其他平台只识别名称，不扩大执行权限。详见[筛选规则](../../../../docs/job-screening.md)与[平台评估](../../../../docs/worker-platform-assessment-2026-10-10.md)。

## 本次完成的检查

| 检查 | 结果 | 证据范围 |
| --- | --- | --- |
| 最终相关离线测试 | 136 passed，4.90 秒 | 筛选、信息库、批次准备与本机 HTTP；临时合成数据 |
| 最终全量离线回归 | 740 passed，21 deselected，139.94 秒 | 当前 checkout 离线测试；不包含真实模型或浏览器验收 |
| 本机浏览器回归 | 20 passed，16 deselected，73.32 秒 | 合成 Lever / Greenhouse、多轮答案复用、暂停恢复、附件和人工交接 |
| Ruff | check 通过；167 files already formatted | 当前 checkout |
| JavaScript | 两个改动脚本 `node --check` 通过 | app.js、worker.js |
| Git whitespace | `git diff --check` 通过 | 已跟踪修改；未跟踪文件另外通过语言检查 |
| 实际工作台界面 | 多词搜索、目标方向、可准备／排除筛选、优先排序通过 | 本机专用可见浏览器；读取少量原记录，未启动批次 |
| 小屏与桌面 | 390px、1280px 页面无水平溢出；筛选控件无内部溢出 | 小屏截图保存在私有 worker 目录，已目视核验 |
| 信息保存 | 两项用户本次确认的语言信息经 helper 保存并回读一致 | 只保存在真实私有答案库；本报告不复制值或个人路径 |

初次界面导航未完成 worker 脚本加载。重新载入后脚本请求、面板和岗位勾选正常；未改动启动机制，未将这次恢复归因为代码修复。随后服务重启以载入最终筛选规则，浏览器页面保留。

语言回归覆盖：明确 CEFR 下限、必须流利、可选／非必需、替代语言、其他语言等级、未知水平，以及“英语必须流利、德语基础即可”不误排除德语的情形。CEFR 值不会转成 Yes / No 流利答案。

## 可复现命令

```sh
UV_CACHE_DIR=/private/tmp/tomorrowstar-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_job_screening.py tests/test_application_automation.py tests/test_application_worker.py tests/test_career_portal_http.py
UV_CACHE_DIR=/private/tmp/tomorrowstar-uv-cache uv run --locked python scripts/run_pytest.py -q
UV_CACHE_DIR=/private/tmp/tomorrowstar-uv-cache uv run --locked python scripts/run_pytest.py -q -m worker_browser tests/test_lever_worker_browser.py tests/test_greenhouse_worker_browser.py tests/test_hosted_ats.py
UV_CACHE_DIR=/private/tmp/tomorrowstar-uv-cache uv run --locked ruff check .
UV_CACHE_DIR=/private/tmp/tomorrowstar-uv-cache uv run --locked ruff format --check .
node --check src/career_evidence_graph/portal_static/app.js
node --check src/career_evidence_graph/portal_static/worker.js
git diff --check
```

浏览器回归需要启动本机 Chromium，默认测试不运行该标记。合成浏览器回归在最后一次语言规则收窄前完成；最后一次修改只影响只读筛选，相关及全量离线测试随后通过。

## 未执行与限制

没有真实个人表单填写、简历上传、账号创建、最终 Submit 或招聘方接收验证。真实 worker 最终保持暂停，批次岗位为零。此前语言硬条件不匹配的目标从批次候选中排除，原记录仍为准备投递；其他未知资格继续待确认。

规则不推断完整资格，不保证识别所有 JD 语言表述，也不根据未知截止日期宣称岗位仍开放。企业自有站点、Ashby、SmartRecruiters、Workday、SuccessFactors、iCIMS、Taleo 和 LinkedIn 尚未新增执行适配。原生 macOS App 未重新打包。测试计数不代表真实投递成功率。
