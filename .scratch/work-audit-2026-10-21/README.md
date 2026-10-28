# TomorrowStar 工作进度与审计 2026 年 10 月 21 日

截至苏黎世时间 12:12，申请产品已具备较完整的源码与合成验证，但尚未交付到当前主 App，也未完成真实线性闭环。职业能力研究仍处于 Phase 9。下一步应核对剩余浏览器能力、主控入口与影响更新，再准备唯一主 App 的组合验收；不应重复开发已有后继实现。

本次新增审计记录与快照，没有修改源码、测试、原票、计划或既有证据。没有更新或启动 App，没有访问真实邮箱、调用模型、上传或投递。真实申请继续暂停，最终 Submit 保持人工。

## 当前进度

| 工作线 | 当前已实现及验证 | 尚未完成的接受 |
| --- | --- | --- |
| 邮件与串行队列 | 持续分页收录、去重、先保存后标签/归档；等待时只收录；完成或 skip 后续岗 | 真实 Gmail、安装组合与实际归档未知结果核对 |
| 普通与精准路由 | 普通自动推进、低路由跳过；精准岗在首次精调前准备 CV 和当前已知必要附稿 | 真实模型质量、真实 JD 需求覆盖及用户体验 |
| 两库与材料 | 事实/答案更正历史、完整源编辑、独立人工版本、原页 CV 换版、附稿编辑、一次 Continue；保留旧材料和人工字段 | 职业事实细粒度影响与合并全面性；真实编译及 PDF 视觉 |
| 页面与 Submit | 已知控件、同页阶段、必要材料映射；最终动作阻断；合成手动提交结果归属消费 | 通用跨文档路线、真实登录与 ATS；自然手动 Submit 后结果及下一岗 |
| 恢复与 skip | 原 owner/run/Page 暖恢复、取消迟到命令、skip/return、候选只读回收、未知结果停止 | 独立进程和宿主冷重开；失去 owner 的旧 Page 仍需核验 |
| 默认界面与主控 | 开启/暂停/继续/skip、编辑焦点及版本冲突保护；Pipeline 指定当前岗 | 39/41 入口与状态归属完整收敛、旧活动兼容、安装体验 |
| 职业能力研究 | Phase 7/8 的首版接受历史保留；通用三层访谈适配器已有工程实现 | Phase 9 质量试验及个人校准；后继清单精确接受；后续图与三份真实 JD 验证 |

最新实现依据为 [精准材料后继](../precision-material-preparation-2026-10-21/README.md)，其前一轮为[原页材料更新](../bound-material-update-2026-10-21/README.md)。较早的 product-completion、24 票地图与开发计划仍保留当时停点，须结合后继 Notes 解读。

## 当前验证

本次直接解析原始 JUnit，并逐项重算最新冻结清单的当前 SHA256。结果见 [facts.json](facts.json)。本次没有重跑完整套件。

| 验证范围 | 核实结果 | 证据 |
| --- | --- | --- |
| 最新完整默认离线 | 4462 passed、2 skipped、532 deselected；0 failure、0 error | [原始日志](../precision-material-preparation-2026-10-21/full-offline-v1.log)、[JUnit](../precision-material-preparation-2026-10-21/full-offline-v1.xml)、[命令与输入](../precision-material-preparation-2026-10-21/full-offline-v1-run.json) |
| 最新受影响默认 | 1370 passed | [JUnit](../precision-material-preparation-2026-10-21/affected-v2.xml) |
| 最新受影响本地浏览器 | 252 passed | [JUnit](../precision-material-preparation-2026-10-21/affected-browser-v2.xml) |
| 当前文件与冻结输入 | 783 项，0 漂移 | [冻结清单](../precision-material-preparation-2026-10-21/frozen-candidate-inputs-v2.json)、[本次回读](facts.json) |
| 本次 tracker 回归 | 32 passed，10.38 秒 | `scripts/run_pytest.py -q tests/test_ticket_query.py`，locked/offline/no-sync |
| 本次差异空白检查 | 通过 | `git diff --check` |

受影响集合有重叠，不能与完整套件相加。两项跳过是显式 opt-in 的实际模型/渲染性能基准。默认排除 live、live_model、worker_browser；另跑的浏览器集合使用隔离本地页面和合成边界。它们不证明真实模型文案、LaTeX 排版、真实 ATS 或安装版行为。

旧 4171 passed / 21 项 Swift 超时是历史失败。最新完整运行的 21 项原生桥已通过，原 60 秒时限保留；不能据此倒推旧运行通过或确定唯一超时根因。

## 审计发现

### 新实现尚未进入安装版

最新冻结清单中 92 项 `src/` 输入与唯一主 App 磁盘包比较：67 相同、22 不同、3 缺失。缺失的是 `application_bound_materials.py`、`application_material_edit.py`、`application_materials.py`。当前源码的材料更新和附稿能力不能视为已安装。比较清单在 [facts.json](facts.json)，不代表实际运行 worker 已加载的版本。

下一步由 28/30 消费冻结输入，通过既有 `macos/main_app.py` 维护流程准备主 App 组合。先完成当前可做工程与候选，不新增 App 身份，不将本次审计视作安装或恢复真实申请的许可。

### 浏览器与材料覆盖仍有明确边界

- **18/33：** 已有同页 Next 和本地 Ashby schema POST 允许、mutation 拒绝证据；真实初始化、跨文档导航、SSO 和未知旧 open 的恢复仍需核验。不能把“没有新 Notes”当作完全未实现，也不能用本地 schema 读取代表真实表单加载完成。依据：[18](../single-job-application-flow-2026-10-16/issues/18-generic-ats-controls.md)、[33](../single-job-application-flow-2026-10-16/issues/33-ashby-public-bootstrap-review.md)、`hosted_ats.py:190`、`test_precision_material_preparation_browser.py:450`。
- **20：** Workable 简历首传和换版已有本地真实 Chromium/loopback 传输回归；必要附稿的实际发送契约仍未核验，继续保持 `unsupported_attachment_transport`。不能借用简历端点发送附稿。依据：[票20最新范围与 Notes](../single-job-application-flow-2026-10-16/issues/20-workable-resume-upload.md)。
- **36/39/41：** 联系资料、人工稿和原页更新已实现；职业源仍整体进入分析输入，细粒度职业事实影响全面性未证。默认界面仍可直接选择推荐并创建 Flow，入口尚未完全收敛。这不等于已证明并发写入或后台越权。依据：`career_portal.py:249`、`portal_static/application_flow.js:412` 和 `:1626`、[调用图](../bound-material-update-2026-10-21/default-control-callgraph.md)。

下一步先用现有公开接口定位缺口，出现有效失败再修复。不要重建队列、事实库、材料生成器或另一套主控。

### 真实闭环和冷启动恢复仍待验收

最新后继仍明确保留安装、真实材料质量、真实 ATS、宿主中断后冷恢复和人工 Submit 的接受边界。APP-12 需要自然手动 Submit → 可归属结果 → 自动下一岗。仅到 Submit 前或模拟成功页不能完成它。失去原 owner 的旧 Page 保持 `needs_recheck`，不能用重开相同 URL 代替恢复。

真实申请当前暂停。18/20/23/27/28/30/34/37/40 的代码和安装组合可按原范围准备；真实 Gmail、真实字段/附件、人工投递和体验接受在相应原票中保留。本次没有出现需用户解锁的实际宿主权限错误。

### Git 尚未记录当前产品的大部分文件

HEAD 仍为 `e4a26d0c24311d014d478f7f92e58a88e6709b4b`，分支 `master`，49 个已跟踪文件有修改。当前 `src` 有 70 个、`tests` 有 228 个、`scripts` 有 16 个、`macos` 有 13 个文件尚未跟踪。普通 `git diff` 或仅从 HEAD 重建会遗漏现有产品的重要部分。

这不是已发生的数据丢失。已有冻结与恢复证据可保留当前工作，但冻结候选明确不是独立完整测试 checkout。后续交付应先审查完整文件清单与隐私/fixture 边界，再决定版本化范围；本次不暂存、提交或推送。

### Python 分发遗漏静态资源

对 `_career_evidence_build.py::_wheel_contents(editable=False)` 的内存结果核对：82 项中没有 `portal_static`，源码静态目录有 12 个文件。`_package_files` 只收集 Python 与 vendor license，sdist 复用同一收集器；Portal 创建服务会读取该目录。因此非 editable Python 分发不能完整提供该 Portal。

这是既有打包范围问题，本轮没有引入；正式 console script 当前面向研究 CLI。原生 App 构建在 `macos/build.py:309` 独立复制整个包，不能据此断言原生 App 缺静态文件。是否将 Portal 纳入 Python 分发支持应先明确，再按必要范围补资源和一个真实构建产物回归。定位：`_career_evidence_build.py:63`、`:164`、`career_portal.py:1087`。

## 票据与研究状态

实时查询：127 总票，103 closed/resolved，24 未关闭，其中 18 open、6 claimed。103 中含 3 项行政 superseded，不能直接作为功能交付率。依赖解析错误 0；20 条 warning 包括 17 条 Assignee、2 条 Claim state、1 条 Blocked by 元数据未知。2 张未关闭研究票的负责人仍未知；未知依赖警告属于已关闭的历史候选技能票。[原始快照](tracker.json)和[24票逐项清单](tickets.md)保留身份、状态、负责人、未关闭直接依赖及下一步。

研究 Phase 7/8 的首版完成与后继清单 07/09 仍开放并不冲突。07 是现成 pending successor 的精确语义接受，09 是其后继封存；不能重复生成 proposal 或替用户接受。Phase 9 的质量试验与个人校准仍待；2/8、25% 只表示研究阶段边界，不能表示申请产品完成率或假设验证程度。依据：[研究状态](../../.planning/STATE.md)、[路线图](../../.planning/ROADMAP.md)。

## 后续顺序

1. 核对 18/33 的跨文档及初始化、20 的附稿契约、36 的职业事实影响，分别保留已完成与未知范围。
2. 沿 28 → 39、18/39 → 37、36 → 40 的现有职责，补齐主控/入口及恢复的剩余回归；34 消费这些能力，41 完成默认入口收敛。
3. 准备完整交付清单和唯一主 App 的 30 组合验收，核对实际加载代码、原页字段/附件、一次 Continue、未知结果与零自动 Submit。
4. 真实申请获明确恢复后，由原 25/11 验收材料和真实主线；自然手动 Submit 后补 APP-12，再处理体验及交付关闭。当前不启动此步骤。
5. 研究 successor 与 Phase 9 继续独立排队，不阻塞日常申请资料复用。

本次为进度、证据与有限源码审计，没有逐行审查整个脏工作区。没有确认新的自动 Submit 越界或真实数据损坏；这一结论不能替代未完成的安装和真实验收。
