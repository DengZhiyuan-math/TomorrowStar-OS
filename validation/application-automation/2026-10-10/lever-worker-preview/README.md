# Lever 独立 worker 本地预览验证

日期：2026-10-10。结果：本地合成预览已可操作。
实际独立 Python 进程、专用 Chromium、现有 HTTP 后端和文件存储参与执行。
这不是此前的 Codex 浏览器回放，也不是静态布局演示。
真实 ATS、模型判断、Greenhouse、安装包与真实接收仍未验收。

## 结果与复现

| 验证 | 最后完成结果 | 证据边界 |
| --- | --- | --- |
| 完整默认回归 | 669 passed，7 deselected；122.40 秒 | checkout 启动器；排除 6 项浏览器测试与 1 项 live 测试。随后重连实现调整另做下列定向检查。 |
| 三轮主流程与三项故障补测 | 6 passed；25.53 秒 | 独立子进程、实际本地 HTTP 页面及 Chromium；无真实招聘网站。 |
| 最后定向回归 | 88 passed；4.01 秒 | worker、门户 CLI 与 HTTP，包括上传后结果保存失败及 12 个并发系统写入者。 |
| 静态检查 | Ruff 全仓通过；148 个文件格式通过；两份 JS 语法通过 | 上游 helper 保持原字节，不重新格式化。 |
| 可见界面操作 | 1440 × 1000 与 390 × 844 检查完成；未见浏览器页面错误 | agent-browser 附加独立 CDP；现有记录勾选、逐项 PDF 选择、答案保存、暂停／继续及人工交接。 |

```sh
uv run --locked python scripts/run_pytest.py -q
TS_WORKER_REPORT_DIR=validation/application-automation/2026-10-10/lever-worker-preview \
  uv run --locked python scripts/run_pytest.py -q -m worker_browser tests/test_lever_worker_browser.py
uv run --locked python scripts/run_pytest.py -q \
  tests/test_application_worker.py tests/test_career_portal_cli.py tests/test_career_portal_http.py
uv run --locked ruff check .
uv run --locked ruff format --check .
node --check src/career_evidence_graph/portal_static/worker.js
node --check src/career_evidence_graph/portal_static/app.js
```

浏览器需先按[启动说明](../../../../docs/lever-worker-preview.md)安装。
本机受限执行环境无法正常启动浏览器；获准的沙箱外运行完成上述浏览器检查。
合成申请记录、答案及浏览器状态都在 checkout 之外；不扫描真实个人资料。
交付源码摘要见[source-manifest.json](source-manifest.json)，用于识别本次 checkout 的实现。

## 三轮主流程

| 轮次 | 岗位数 | 已验证行为 | 记录 |
| --- | --- | --- | --- |
| 1 | 2 | 完整填写、字段回读、同名不同内容 PDF 绑定、人工接管、暂停保留页面 | [round-1-complete.json](round-1-complete.json) |
| 2 | 3 | 两个瑞士岗位缺答仍允许美国岗位完成；两种已确认同义措辞合并；暂停时保存仅排队；继续后自动恢复；答案修改使相关复核失效 | [round-2-answer-loop.json](round-2-answer-loop.json) |
| 3 | 2 | 原笔记冲突只重试同步；明确重新核验；第二个进程不能取得执行锁；worker 重启先暂停；控制失联及取消停止后续执行 | [round-3-recovery.json](round-3-recovery.json) |

三轮共 7 个岗位实例、7 次合成附件上传。每轮最终端点请求均为 0。
这证明本地测试中的最终动作守卫；不代表真实 ATS 的自动投递成功率。
第三轮包含主动中断，报告中的 `filling` 是中断时的观察状态，不是完成声明。

另三项浏览器测试分别验证：页面容量上限与显式释放；动作前附件改变后不上传；
后端停止后控制失联暂停、重连保持相同 fixture origin 与原 worker PID、等待岗位恢复且事件记录保留。
确定性故障探针还在附件请求发出后让结果保存失败。保留上传意图、停止该岗位，下一轮不重复上传。

## 界面验收

从现有求职进度选择 Preview Lake、Preview Bay、Preview Alps。
逐岗位分别选择合成 PDF 2、3、1，国家分别选择 CHE、USA、CHE。
启动后，瑞士两项等待一个集中补充问题，美国一项到达待复核。
整批暂停后保存瑞士答案：两项仅转为 queued，上传总数仍为 1。
继续后，上传总数变为 3，各项附件摘要符合独立选择；原笔记自动更新下一步，状态仍为 drafting。
点击接管后，worker 撤销该页执行权并定位专用浏览器页面。
全程未点击最终 Submit，未模拟人工提交或接收回执。

| 画面 | 文件 |
| --- | --- |
| A 布局、集中补充与逐岗位复核 | [桌面截图](ui-desktop.png) |
| 窄屏单列；补充区在岗位区前 | [窄屏截图](ui-mobile.png) |
| 专用 Chromium 中的字段与所选 PDF | [浏览器截图](dedicated-browser.png) |

控制页标题为“求职进度 · TomorrowStar”。运行入口是本机 `/#applications`，
招聘页是另一 loopback origin。测试 UI 的临时浏览器关闭；交付预览的 worker 页面保留且批次暂停。

## 失败记录与限制

- 默认 CLI 回归曾因新增参数破坏既有启动 seam 而失败。修正为只在显式启用 worker 时传参，完整回归随后通过。
- 重连测试曾沿用 0.5 秒失联阈值，恢复后再次暂停。测试恢复默认宽限后通过；没有放宽 worker 的失联守卫。
- 一次直接 `pytest` 调用读取已安装包，使用了错误的 launcher 路径并失败。本仓库要求 checkout 启动器；最后记录均使用该入口。
- 上传内容回读由本地 fixture 返回 SHA-256。它不证明真实 Lever 接收附件或申请。
- 已验证固定同义别名；不确定语义等待用户。模型调用为 0，不据此宣称模型数据隔离已经验收。
- 实际退出整个 Codex 桌面、系统睡眠／唤醒、真实登录、CAPTCHA、动态或自定义控件没有本轮证据。
- 系统共享锁和 revision 检查已验证。外部编辑器不使用该锁，最后检查与替换之间仍有竞争窗口。
- worker 没有打入既有原生 App；旧 App 的签名和打包验收不适用于本次新增依赖。

当前交付是 Lever 合成可用预览。双平台首版及受控真实小样本按原开发顺序继续验收。
