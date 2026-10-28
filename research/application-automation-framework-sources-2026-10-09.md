# 独立投递执行器：框架与源码资料

核验日期：2026-10-09。范围：公开官方文档、公开仓库默认分支的精确 revision、提交路径与模型发送路径。此次未安装框架、未调用模型、未运行真实 ATS、未投递申请。README 演示和覆盖率声明不能作为本机成功率证据。

## 判断

独立于 Codex 的本地浏览器执行器具有技术可行性。Playwright Python 可从普通 Python 进程启动 Chromium，并使用无界面模式。该基础能力不要求 Codex、云浏览器或 LLM。[官方库文档](https://playwright.dev/python/docs/library)

建议从 **Playwright Python＋限定 ATS 的确定性适配器＋串行任务列表**开始。先实现批量填写与暂停复核，再评估是否需要自动提交。遇到未知字段、登录、验证码或不确定结果时，应进入人工处理状态。队列、复核门、去重和回执语义属于产品实现责任；这些能力不会因引入浏览器框架而自动获得。

这是基于源码结构和现有 Python 项目的工程判断，尚不是独立执行器的实测结论。

## 当前 revision、许可证与兼容性

以下版本属于核验时的公开发行元数据或源码声明，不代表已在项目环境安装或通过兼容性测试。commit 日期是所核验 head 的 committer date，不等同于最后一次仓库活动日期。

| 项目 | 精确 revision / head 日期 | 许可证 | 版本 / 运行声明 | 判断 |
|---|---|---|---|---|
| Playwright Python | [`1764101120254f14dc7d856453b9073c251d772d`](https://github.com/microsoft/playwright-python/commit/1764101120254f14dc7d856453b9073c251d772d) / 10-08 | [Apache-2.0](https://github.com/microsoft/playwright-python/blob/1764101120254f14dc7d856453b9073c251d772d/LICENSE) | [PyPI 1.63.0](https://pypi.org/project/playwright/1.63.0/)；Python ≥3.10，明确列出 3.13；macOS 有 ARM64 与 universal2 wheel | 最小且成熟的基础；仍需匹配浏览器二进制 |
| browser-use | [`c75e8476e26d18b7617643bc2ae082fae8eae431`](https://github.com/browser-use/browser-use/commit/c75e8476e26d18b7617643bc2ae082fae8eae431) / 10-07 | [MIT](https://github.com/browser-use/browser-use/blob/c75e8476e26d18b7617643bc2ae082fae8eae431/LICENSE) | [源码 0.13.11](https://github.com/browser-use/browser-use/blob/c75e8476e26d18b7617643bc2ae082fae8eae431/pyproject.toml)，Python ≥3.11,<4；固定 Pydantic 2.13.5，含多个 provider SDK 与 macOS PyObjC | 可独立运行；依赖较多，不宜直接加入现有锁定环境 |
| Stagehand | [`2d605b099996e10c3e3ab0dcf293db8d482a2c97`](https://github.com/browserbase/stagehand/commit/2d605b099996e10c3e3ab0dcf293db8d482a2c97) / 10-08 | [MIT](https://github.com/browserbase/stagehand/blob/2d605b099996e10c3e3ab0dcf293db8d482a2c97/LICENSE) | [monorepo package 4.0.0 / Node ≥22.18](https://github.com/browserbase/stagehand/blob/2d605b099996e10c3e3ab0dcf293db8d482a2c97/package.json)；[Python SDK 源码 4.2.0 / Python ≥3.11](https://github.com/browserbase/stagehand/blob/2d605b099996e10c3e3ab0dcf293db8d482a2c97/packages/sdk-python/pyproject.toml) | 本地浏览器可选；v4 API 与旧 v3 配置不同 |
| Skyvern | [`94c7ee197fc539d150fcd3b95910fc5a2fa8f581`](https://github.com/Skyvern-AI/skyvern/commit/94c7ee197fc539d150fcd3b95910fc5a2fa8f581) / 10-09 | [AGPL-3.0](https://github.com/Skyvern-AI/skyvern/blob/94c7ee197fc539d150fcd3b95910fc5a2fa8f581/LICENSE) | [源码 1.0.55 / Python ≥3.11,<3.15](https://github.com/Skyvern-AI/skyvern/blob/94c7ee197fc539d150fcd3b95910fc5a2fa8f581/pyproject.toml)；包含本地/server extras | 可自托管；服务和依赖明显较重 |
| iknalos/ApplyPilot | [`0940d1d54e053f38273cff730b24ef379b8354d9`](https://github.com/iknalos/ApplyPilot/commit/0940d1d54e053f38273cff730b24ef379b8354d9) / 07-09 | 未找到许可证；[仓库 API 的 license 为 null](https://api.github.com/repos/iknalos/ApplyPilot) | [requirements](https://github.com/iknalos/ApplyPilot/blob/0940d1d54e053f38273cff730b24ef379b8354d9/agent/requirements.txt)：Anthropic ≥0.50、Playwright ≥1.45，未固定版本，未声明 Python 范围 | 适合读取设计；复制或改编需先解决许可 |
| geckguy/AutoApply | [`6c5fbc42833278acaa45981e86b5d99ae97d77a0`](https://github.com/geckguy/AutoApply/commit/6c5fbc42833278acaa45981e86b5d99ae97d77a0) / 09-14 | [MIT](https://github.com/geckguy/AutoApply/blob/6c5fbc42833278acaa45981e86b5d99ae97d77a0/LICENSE) | [Chrome 扩展 1.0.1](https://github.com/geckguy/AutoApply/blob/6c5fbc42833278acaa45981e86b5d99ae97d77a0/extension-chrome/manifest.json)；[后端 requirements](https://github.com/geckguy/AutoApply/blob/6c5fbc42833278acaa45981e86b5d99ae97d77a0/backend/requirements.txt) | 不依赖 Codex，但不是现成的无界面批量 worker |
| AbhishekMandapmalvi/AutoApply | [`053071ba1bba5733b522d78c3d645002d817e55a`](https://github.com/AbhishekMandapmalvi/AutoApply/commit/053071ba1bba5733b522d78c3d645002d817e55a) / 03-13 | [MIT](https://github.com/AbhishekMandapmalvi/AutoApply/blob/053071ba1bba5733b522d78c3d645002d817e55a/LICENSE) | [依赖声明](https://github.com/AbhishekMandapmalvi/AutoApply/blob/053071ba1bba5733b522d78c3d645002d817e55a/requirements.txt) | 有独立 ATS 代码；提交与成功确认逻辑不能直接采纳 |

## 浏览器与数据实际路径

本地浏览器、本地控制进程、本地模型、后台任务是四个不同维度。一个项目支持本地浏览器，不代表页面和个人数据不会发送到模型服务。

| 项目 | 独立 / 后台路径 | 模型与数据发送路径 | 最终动作边界 |
|---|---|---|---|
| Playwright | 普通 Python CLI 启动浏览器；默认 headless，可切 headed；有同步/异步 API | 框架不要求 LLM。浏览器访问 ATS，填写或上传可能即产生 ATS 网络请求 | 框架提供点击能力；产品必须约束可执行动作，不能将“禁止 Submit”写成唯一 prompt |
| browser-use | `Browser` 可启动本地浏览器，支持 headless、专用 profile、已有 CDP；云浏览器为另一配置 | 默认 Agent 在未显式指定 LLM 时使用 ChatBrowserUse。其默认 endpoint 为 `https://llm.api.browser-use.com/v1/chat/completions`。可选择其他 provider；本地模型需显式配置。匿名遥测默认开启，发至 `https://eu.i.posthog.com`，可禁用 | 提供通用 click/evaluate 与工具排除接口。域名白名单约束导航，不能替代本应用的逐动作与最终提交门 |
| Stagehand v4 | `localBrowser.launch` / Python `local_browser.launch` 支持本地无界面；也可 CDP attach 或 Browserbase launch | Model Gateway 仅支持 Browserbase 托管会话。本地浏览器推理必须给 provider key 或自定义 LLM callback；callback 的去向由应用决定 | 官方示例把填写和提交拆开，人工批准 exact values 后执行至多一次 Submit，并重查字段；需要应用保留该 code guard |
| Skyvern | 自托管方案可本地运行；Compose 包含 PostgreSQL、API、UI；也能连接本地 CDP | 自托管仍需配置 LLM。支持 OpenAI、Anthropic、Gemini 等云路径与 Ollama 本地路径。Skyvern Cloud 控制本地浏览器经 tunnel 是云控制模式 | 有任务/工作流与 job-application recipe，但 recipe 返回 run id 不代表已投递；需查询实际 run result |
| iknalos/ApplyPilot | 单 URL 的本地 Python Agent；硬编码 `headless=False`，使用 `input()` 等待复核/退出。没有现成 batch/headless 调度 | 完整 profile 放入 Anthropic system prompt；read_page JSON、tool results、可选页面截图随 conversation 发往 Anthropic | `--auto-submit` 只切换 prompt 文本；click 工具直接 `locator.click()`，没有 runtime Submit 拦截 |
| geckguy/AutoApply | 浏览器扩展＋本地 FastAPI 后端；auto-run 处理当前表单安全 Next 步骤；未找到独立任务队列 worker | 本地映射先执行；AI fallback 的 prompt 包含 profile、表单字段和上下文，发往所选 Gemini/OpenRouter/OpenCode Go。OpenCode Go 默认是云网关，不是因含“OpenCode”就本地 | filler 用控件 type、文案和表单归属过滤提交动作；只点明确安全 Next。适合参考该控制策略，不能等同于跨网站全局保证 |
| AbhishekMandapmalvi/AutoApply | 独立 ATS applier 函数；有 CAPTCHA/manual-required 分支 | 本次只核验 ATS adapter 提交逻辑，未完成全仓库模型/遥测路径审计 | Lever / Greenhouse 直接点 Submit。点后等待并检查错误元素，未见错误就 `success=True`；不是可靠回执判定 |

表格依据：

- Playwright：[库运行模式](https://playwright.dev/python/docs/library)、[BrowserType 与 persistent context](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context)。
- browser-use：[浏览器参数](https://docs.browser-use.com/open-source/customize/browser/all-parameters)、[Agent 默认模型](https://github.com/browser-use/browser-use/blob/c75e8476e26d18b7617643bc2ae082fae8eae431/browser_use/agent/service.py#L225)、[ChatBrowserUse endpoint/payload](https://github.com/browser-use/browser-use/blob/c75e8476e26d18b7617643bc2ae082fae8eae431/browser_use/llm/browser_use/chat.py#L97)、[遥测](https://github.com/browser-use/browser-use/blob/c75e8476e26d18b7617643bc2ae082fae8eae431/browser_use/telemetry/service.py)、[默认配置](https://github.com/browser-use/browser-use/blob/c75e8476e26d18b7617643bc2ae082fae8eae431/browser_use/config.py#L58)、[工具执行](https://github.com/browser-use/browser-use/blob/c75e8476e26d18b7617643bc2ae082fae8eae431/browser_use/tools/service.py)。
- Stagehand：[v4 浏览器](https://docs.stagehand.dev/v4/configuration/browser)、[模型路由](https://docs.stagehand.dev/v4/configuration/models)、[精确 revision 的批准提交示例](https://github.com/browserbase/stagehand/blob/2d605b099996e10c3e3ab0dcf293db8d482a2c97/packages/docs/v4/cookbooks/approve-form-submission.mdx)。v4 不应沿用旧 v3 的 `env: "LOCAL"` 初始化方式。
- Skyvern：[Compose 与模型选项](https://github.com/Skyvern-AI/skyvern/blob/94c7ee197fc539d150fcd3b95910fc5a2fa8f581/docker-compose.yml)、[自托管模型说明](https://www.skyvern.com/docs/developers/self-hosted/llm-configuration)、[本地/云控制模式](https://github.com/Skyvern-AI/skyvern/blob/94c7ee197fc539d150fcd3b95910fc5a2fa8f581/README.md)、[job application recipe](https://github.com/Skyvern-AI/skyvern/blob/94c7ee197fc539d150fcd3b95910fc5a2fa8f581/docs/cookbooks/job-application-filler.mdx)。
- ApplyPilot：[执行源文件](https://github.com/iknalos/ApplyPilot/blob/0940d1d54e053f38273cff730b24ef379b8354d9/agent/apply_agent.py#L165)。完整 profile、提交 rule、无校验 click、Anthropic messages 和 `input()` 均在该文件可见。
- geckguy/AutoApply：[扩展 manifest](https://github.com/geckguy/AutoApply/blob/6c5fbc42833278acaa45981e86b5d99ae97d77a0/extension-chrome/manifest.json)、[filler 控件过滤](https://github.com/geckguy/AutoApply/blob/6c5fbc42833278acaa45981e86b5d99ae97d77a0/extension-chrome/content/filler.js)、[AI prompt](https://github.com/geckguy/AutoApply/blob/6c5fbc42833278acaa45981e86b5d99ae97d77a0/backend/services/field_mapper.py#L155)、[provider factory](https://github.com/geckguy/AutoApply/blob/6c5fbc42833278acaa45981e86b5d99ae97d77a0/backend/services/llm_client.py)、[OpenRouter endpoint](https://github.com/geckguy/AutoApply/blob/6c5fbc42833278acaa45981e86b5d99ae97d77a0/backend/services/openrouter.py#L30)、[OpenCode Go endpoint](https://github.com/geckguy/AutoApply/blob/6c5fbc42833278acaa45981e86b5d99ae97d77a0/backend/services/opencode.py#L20)、[Gemini SDK 调用](https://github.com/geckguy/AutoApply/blob/6c5fbc42833278acaa45981e86b5d99ae97d77a0/backend/services/gemini.py#L69)。
- AbhishekMandapmalvi/AutoApply：[Lever](https://github.com/AbhishekMandapmalvi/AutoApply/blob/053071ba1bba5733b522d78c3d645002d817e55a/bot/apply/lever.py#L68)、[Greenhouse](https://github.com/AbhishekMandapmalvi/AutoApply/blob/053071ba1bba5733b522d78c3d645002d817e55a/bot/apply/greenhouse.py#L65)。

## Playwright 对最小实现的具体支持

| 需求 | 原生能力 | 限制 |
|---|---|---|
| 独立运行 / 后台浏览器 | Python sync/async API；`launch(headless=True)` | headless 不保证目标站接受自动化；也不负责排程 |
| 登录状态复用 | `launch_persistent_context(user_data_dir)` 或 storage state | 同一个 user data dir 不能并发启动多个实例；官方要求独立自动化 profile，不支持自动化日常 Chrome 默认 profile |
| 填写 / 上传 | label/role locator、fill、select、check、`set_input_files`、file chooser | 控件显示不同于服务器收到，必须读回并核验响应 |
| 自动等待 | locator actions 检查可见性、稳定性、可接收事件等 | 不等于业务流程成功或字段语义正确 |
| 诊断与证据 | screenshot、trace、DOM/network snapshots | 可能包含表单值、简历信息和会话资料，必须保存在私有运行目录 |
| 限制并发 | 每任务独立 context，串行起步；后续独立 worker | API 不保证线程安全；多线程须每线程独立 Playwright instance |

来源：[上传与控件动作](https://playwright.dev/python/docs/input#upload-files)、[locators](https://playwright.dev/python/docs/locators)、[auto waiting](https://playwright.dev/python/docs/actionability)、[trace viewer](https://playwright.dev/python/docs/trace-viewer)、[persistent context](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context)、[threading](https://playwright.dev/python/docs/library#threading)。

## 仍未证明的事项

- 独立执行器在本机 Python 3.13、当前 macOS、实际浏览器二进制上的安装与运行。
- 实际 ATS 成功率、耗时、每任务成本、验证码/邮件验证频率与维护成本。
- 所选模型的本地质量，以及显式关闭遥测后是否仍存在其他网络路径；需要运行期网络审计。
- 所有站点的 final Submit 识别和每个 endpoint 的请求门。通用按钮黑名单不充分，确定性 ATS 适配器仍需实际页面与请求核验。
- 多任务取消、异常恢复、已提交后丢失回执的去重行为。未知提交结果不能自动重试。

可下一步验证的最小范围：独立 Playwright 进程对现有合成 Lever / Greenhouse 页面执行串行批量填写，保留字段回读、未知答案暂停、最终动作零次和取消清理证据。该验证仍不会产生真实投递成功率。
