# 通用流程验证

2026-10-10。仅记录可公开的实现与合成证据。
个人岗位、URL、简历、来源及真实观察报告保存在选定私有运行目录。

## 实现

- 通用模式显式启用，并复用现有队列、答案库和写回机制。
- 原生控件标签、必填覆盖、单选组、组合框和匿名附件读取。
- 未验证 HTTP GET/POST 自动保存及 WebSocket 上行的阻止与岗位暂停。
- 已审查公开 JSON POST 的精确许可。岗位、请求 URL 与原始请求体必须全部匹配。
- 岗位简历默认从现有目录生成，已有 PDF 为可选例外。
- 来源引用验证、责任边界、设计与研究原文保持、私有 PDF 导出。
- 同一申请与来源输入复用已生成草稿。草稿核验先于真实填表。
- 既有只读 Codex 边界增加显式允许非仓库工作目录的选项；默认行为不变。

## 合成检查

| 检查 | 实际结果 |
| --- | --- |
| 全部离线测试，排除 worker_browser / live_model | 745 passed, 30 deselected |
| 通用、Lever、Greenhouse、托管 ATS、PDF 绑定浏览器回归 | 29 passed, 21 deselected |
| 最终 PDF 模板与 worker 内容绑定回测 | 1 passed, 4 deselected |
| 最终归属及 Codex 边界回测 | 18 passed, 1 skipped, 1 deselected |
| 公开 POST 许可的离线绑定检查 | 1 passed, 10 deselected |
| 增加许可后的通用与托管 ATS 浏览器回归 | 14 passed, 18 deselected |
| Ruff 检查、格式检查、worker.js 语法 | 通过 |

全量离线命令：

```sh
uv run --locked python scripts/run_pytest.py -q \
  -m 'not worker_browser and not live_model'
```

浏览器回归命令：

```sh
uv run --locked python scripts/run_pytest.py -q -m worker_browser \
  tests/test_generic_worker.py tests/test_application_resume.py \
  tests/test_hosted_ats.py tests/test_lever_worker_browser.py \
  tests/test_greenhouse_worker_browser.py
```

## 限制

合成页面通过不证明真实站点的自动保存或附件接收。
真实空表读取、真实填值、服务端保存、附件上传、人工提交与收到确认须分别报告。
引用检查只能核验来源存在与版本，不能自动证明所有改写语义正确。
未核验的 Skill、责任、资格和回答继续待确认，不以模型输出补齐事实。
本记录不宣告跨平台无人值守或职业图里程碑验收完成。
