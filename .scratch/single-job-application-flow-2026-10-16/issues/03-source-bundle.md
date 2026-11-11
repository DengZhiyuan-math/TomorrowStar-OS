# 建立分析与简历共用的真实资料快照

Type: task
Label: wayfinder:task
Status: closed
Interaction: AFK
Assignee: 01a146b9/source_bundle
Created: 2026-10-16
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [建立单岗位任务契约与持久恢复](01-task-contract.md)

## Question

怎样复用职业资料目录及现有职责归属逻辑，为岗位分析与简历提供一致、可追溯且不过度裁剪的资料？

## Work and reuse

- 复用 CareerCatalog 和 draft_resume 的有效来源、Contribution 归属与 Boundaries 处理；仅提取必要共享接口，避免第二套私有资料库。
- 快照保留 source ID、revision、locator、可用性、责任归属和审核状态；用户/团队/他人/Codex 辅助区分不丢失。
- 匹配分析不能直接受简历的最多 40 个关键词候选或模型最多四条选材上限限制；有限上下文必须记录截断/未覆盖范围。
- 明确结构化个人资料的现有来源和缺失反馈；投递不得要求用户先完成公开网站。只在明确选择的私有目录读取，不自动扫描其他路径。
- 快照改变会使下游分析和简历确认失效；仅岗位备注等无关改动是否影响缓存按任务契约处理，不抹掉既有版本。

## Ownership

- `src/career_evidence_graph/application_resume.py（共享取材入口）`
- `src/career_evidence_graph/career_portal_data.py（尽量复用）`
- `tests/test_application_resume.py`
- `tests/test_application_flow.py`

以上为责任范围，不表示必须修改每个文件。多人同时工作时不得回退他人修改；共享接口按已完成依赖契约衔接，必要时先协调文件所有权。

## Acceptance criteria

- [x] 分析与简历引用相同来源身份；无效引用、无法读取或不明归属保持显式，不被静默改为本人贡献。
- [x] 缺 URL/未启用 worker 不阻止读取 JD 相关资料；缺个人资料说明具体需要，不能编造。
- [x] 合成测试覆盖内容变化、归属混合、来源不可用、无关备注不泄露模型、长资料覆盖披露。

## Verification and evidence

- tests/test_career_portal_data.py
- tests/test_application_resume.py
- 先执行受影响的有意义测试；涉及共享流程/存储时按 CONVENTIONS 完成完整离线验证。浏览器合成与真实 ATS 分开记录。
- 关闭前将实际修改、所用版本、检查结果与限制写入本票 Resolution comment，并链接资产；不能用通过数或历史报告代替本票当前输入验收。
- 真实资料与私有衍生信息只保存在私有位置。本地图中的报告仅使用合成/脱敏状态，不嵌入真实字段、附件、岗位 URL 或私有指纹。
- 自动最终 Submit 保持为零。未知外部动作不自动重试。源码通过、安装版通过、真实填写、人工提交和雇主接收分别报告。

## Resolution comment

2026-10-17：01a146b9/source_bundle 已核对当前依赖并领取。先恢复共享快照 tracer 的失败测试，再逐项完成来源保留、私有个人资料和简历复用；当前尚未完成验收。

2026-10-17 实现移交，等待 root 完整离线验证后关闭：

- [共享快照入口](../../../src/career_evidence_graph/application_resume.py) 新增 `career_source_snapshot(catalog)`。读取 CareerCatalog 既有 `reports`、`contributions`、`skill-graph`、`sources` 范围；保留完整文档、所有 Contribution 项、来源身份、revision、locator、归属、Boundaries 和 documentary/unknown 状态。快照本身没有 JD 过滤、40 条候选或四条模型选材限制。未改动 Catalog 的 2MB、三秒读取、云占位或符号链接边界。
- 每个条目以 `evidence_id:locator` 标识来源。无法读取的文档保留身份、失败码和 unknown 状态；未知归属、团队及他人实现不变成个人简历成果。有明确边界的 User 设计/Codex 实现继续分开记录，且设计文本不可改写。
- 私有 `sources/profile.json` 复用现有 `Profile` 验证；不需要启用公开网站。旧 `reports/public-site/site-content.json` 保持兼容。显式私有资料优先；格式错误不静默退回旧网站资料。缺失、无效和不可读分别报告，姓名缺失或空白不会补造。缺 profile 仍可生成分析快照。
- `draft_resume` 删除重复来源遍历，复用共享快照后保持原有 JD 排序与 40 条提取行为。草稿 `source_snapshot_revision` 及 `input_digest` 绑定完整快照；不相关但位于所选 Catalog 范围内的资料漂移也会改变输入版本。Catalog 外备注不进入快照或模型；完整长文保留，覆盖状态显式标为未截断，不可读文档列入未覆盖清单。
- [针对性测试](../../../tests/test_application_resume.py)：依照 tdd 逐项记录 tracer 缺接口、归属字段、不可读来源、私有资料入口、共享草稿、无效资料及未知责任的 RED→GREEN。最终执行 `UV_CACHE_DIR=/private/tmp/tomorrowstar-single-job-uv-cache uv run --locked python scripts/run_pytest.py tests/test_application_resume.py tests/test_career_portal_data.py tests/test_application_flow.py -q`，结果 **151 passed, 2 deselected**。默认 marker 排除了真实浏览器测试。受影响两文件 Ruff check/format 及 `git diff --check` 均通过。
- 输入基线：Git HEAD `e4a26d0c24311d014d478f7f92e58a88e6709b4b` 加现有保留的 dirty 工作区；Python `3.13.14`、Pydantic `2.13.4`。本次移交 `application_resume.py` SHA256 `75e44392020701030f9b5dec4bb15ee20ba57560a1ec2aefefc5be13d1426878`；`test_application_resume.py` SHA256 `a982a02beb959368136a39fa6ccd85825b3d423fd6735941002411e32d39771d`。这些是本次移交输入，后续票据修改不得套用为新版本验收。
- 此记录只证明 checkout 合成行为。没有启动或重启浏览器、运行模型、改写私有真实记录、上传或执行最终 Submit。安装版和 Gmail/真实 ATS 验收仍由后续票据分别记录。


根代理整合：服务端 `current_flow_inputs` 从当前 JD 和真实 Catalog 快照推导指纹；伪造指纹 HTTP tracer 已 RED→GREEN（接受伪造的 200 改为 409）。真实快照内容运行中变化会阻止采用旧模型结果；`update-inputs` 可省略客户端指纹，由 provider 推导当前版本，保持原任务 ID，更新本身不调用模型。当前合同/HTTP **114 passed in 8.74s**。完整离线命令 `uv run --locked python scripts/run_pytest.py -q` **1560 passed, 140 deselected in 204.45s**；此全套覆盖最终资料快照及此前 HTTP，随后可选 `update-inputs` 参数扩展由上述当前专项覆盖。全仓 Ruff check、format（187 files）和 `git diff --check` 通过。来源快照交付验收完成；真实模型、PDF 新链、安装版与 ATS 仍未验证。证据汇总见 [verification.md](../verification.md)。
