# Greenhouse 接入与双平台回归

日期：2026-10-10。Greenhouse 已接入原独立 worker、答案库和现有门户。
本轮使用隔离合成申请记录及实际 Chromium，不读取私人配置、不访问真实 ATS、不调用模型。
这是双平台本地预览验证；真实页面、真实附件接收和完整首版验收仍需各自的证据。

## 复用范围

| 共用部分 | 平台差异 |
| --- | --- |
| 单个顺序执行进程、生命周期锁、暂停及控制失联 | `ats_forms.py` 中固定的表单、问题和附件状态选择器 |
| 同一个 Job Apply 答案库、国家／公司／岗位范围和内容 revision | Greenhouse 名、姓分别使用确认答案；不从完整姓名拆分 |
| 原记录检查、每岗位 PDF 摘要、上传前后断点与待同步重试 | Greenhouse 合成上传路径单独准入；不继承 Lever 的 POST 路径 |
| 集中补充、满足条件自动恢复、页面容量与人工交接 | Greenhouse 数值选项值与显示标签分开，按实际标签选择和回读 |

共享浏览器执行器从 `lever_worker.py` 移至 `application_worker_browser.py`。
旧模块保留导入兼容，调用同一个执行器。存储 schemaVersion 仍为 1；旧 Lever 岗位可从原 URL 确定平台。
没有增加依赖、数据库、第二套队列或第二份答案库。

合成字段模型参考[Greenhouse 官方 Job Board 文档](https://docs.greenhouse.io/job-board.html)：
名、姓、邮箱、文件及原生选择列表。官方字段文档不证明本地选择器或上传路径适用于真实托管页面。
本轮没有调用官方申请提交 API。

## 三轮新增主流程

| 轮次 | 岗位实例 | 验证行为 | 记录 |
| --- | --- | --- | --- |
| 1 | Greenhouse 2 | 独立执行、分别确认的名／姓、数值选项回读、资格与担保分开、逐项 PDF 内容绑定、人工接管、暂停保留页面 | [greenhouse-round-1-complete.json](greenhouse-round-1-complete.json) |
| 2 | Greenhouse 2、Lever 1 | 两平台共用瑞士缺答项，美国独立；暂停后保存仅排队；继续后自动恢复；修改答案后两平台重新核验，附件不重传 | [greenhouse-round-2-shared-answers.json](greenhouse-round-2-shared-answers.json) |
| 3 | Greenhouse 1 | 上传后新增必填项进入补充等待；“仅本次”不保存；补充后不重复上传；worker 重启先暂停并要求核验 | [greenhouse-round-3-dynamic-recovery.json](greenhouse-round-3-dynamic-recovery.json) |

新增主流程共 5 个 Greenhouse、1 个 Lever 岗位实例，6 次合成附件上传。
三轮最终端点请求均为 0。第三轮报告 `needs_recheck` 是主动重启后的预期状态，不是填写失败或已接收。

另 5 个 Greenhouse 故障场景各包含一个故障岗位和一个正常岗位：
未选附件控件、未验证控件、上传摘要不符、上传服务报错、上传后岗位身份变化。
每项都让故障岗位等待核验，正常岗位继续；有上传意图时保留意图，不自动重发。
姓名反例另验证完整姓名不能解除未知名／姓的等待，补充后才继续。

## 验证命令

```sh
TS_WORKER_REPORT_DIR=validation/application-automation/2026-10-10/greenhouse-worker-preview \
  uv run --locked python scripts/run_pytest.py -q -m worker_browser \
  tests/test_lever_worker_browser.py tests/test_greenhouse_worker_browser.py
uv run --locked python scripts/run_pytest.py -q
uv run --locked ruff check .
uv run --locked ruff format --check .
node --check src/career_evidence_graph/portal_static/worker.js
```

浏览器测试连续两次通过：15 passed，分别为 66.28 和 66.33 秒。
15 项包含原 Lever 6 项及新增 Greenhouse 9 项。
最终全仓离线回归为 671 passed、16 deselected，112.93 秒；排除 15 项浏览器测试和 1 项 live 测试。
Ruff 全仓通过，155 个文件格式通过，两份 JS 语法通过。
范围修正前的完整回归也通过：669 passed、16 deselected，124.82 秒。
源码摘要见[source-manifest.json](source-manifest.json)；旧 helper 的固定摘要未改变。
原 Lever 的三轮在本目录重跑记录，原先的 [Lever 交付报告](../lever-worker-preview/README.md)保持不变。

系统共享范围回归还覆盖两平台最终请求守卫、错误岗位／平台上传路径、同名不同内容 PDF，
以及上传后结果保存失败。发现并修正了 OTHER 国家“仅本次”资格答案无法解除等待的问题：
临时答案现在绑定选定 application_id，不向其他岗位传播，也不保存到答案库。

## 界面验收

agent-browser 附加单独的临时 QA 浏览器，确认标题“求职进度 · TomorrowStar”及本机工作台地址。
从已有记录勾选 Greenhouse 的 Preview Lake、Lever 的 Preview Bay 和 Preview Alps，
分别选择合成 PDF 2、3、1，国家为 CHE、USA、CHE。
美国岗位完成，瑞士两个岗位共用一个担保补充项；Greenhouse 的当前工作资格另列为问题。

整批暂停后，分别确认资格和担保。一个问题保存后，另一个未提交的答案草稿仍保留。
两项仅进入队列，上传计数仍为 1。继续后全部待复核，上传计数为 3，各自文件摘要匹配。
原申请记录的下一步自动同步，状态保持 drafting。
接管 Greenhouse 后保留其实际表单，由用户操作；未点击任何最终 Submit。
接管后在 worker 运行期间修改名字段，回读保持人工修改；暂停后将合成字段恢复原值。
交付状态和计数见[人工接管检查](gui-handoff-probe.json)。

| 界面 | 证据 |
| --- | --- |
| 集中补充与跨平台等待 | [ui-waiting.png](ui-waiting.png) |
| 三个已准备的复核岗位 | [ui-review.png](ui-review.png) |
| 专用浏览器中的 Greenhouse 名、姓、资格、担保与所选 PDF | [greenhouse-page.png](greenhouse-page.png) |

后台 QA 窗口出现轮询延迟。界面新增原生 focus 与 visibilitychange 刷新入口。
有限控制宽限仍保留；后台浏览器节流可能导致保守暂停，用户回到工作台后可继续。
临时 QA 浏览器关闭，交付预览的独立 worker 和三个仍有效页面保留，整批暂停。

## 真实使用边界

- 真实 Lever / Greenhouse 在执行入口仍关闭。合成 DOM、上传确认和 SHA 回读不能证明真实招聘方接收。
- 只支持明确文本、原生单选列表、日期、PDF 文件。多选、额外附件和未验证控件停止该岗位。
- 同义复用仍采用固定已验证别名；模型等价判断及模型数据隔离未验收。
- 人工提交确认和用户核验接收来源仍分开；本轮没有真实或模拟人工提交。
- 未关闭整个 Codex 桌面进行验收，未验收系统睡眠、真实登录、CAPTCHA 或原生安装包。
- 外部编辑器不使用系统文件锁，最后 revision 检查与替换间仍有竞争窗口。

启动和操作见[双平台预览说明](../../../../docs/lever-worker-preview.md)。
可分别运行 `--platform greenhouse` 或 `--platform mixed`；所有预览使用独立的临时合成资料目录。
