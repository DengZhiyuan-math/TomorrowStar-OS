# 复用岗位分析生成并确认专用简历

Type: task
Label: wayfinder:task
Status: closed
Interaction: AFK
Assignee: 01a146b9/source_bundle
Created: 2026-10-16
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [建立分析与简历共用的真实资料快照](03-source-bundle.md), [接通 Codex 岗位分析与可解释匹配评分](04-match-analysis.md)

## 当前契约定位 — 2026-10-20

复用选材、来源与PDF生成。普通岗不再逐版人工确认材料，高价值初稿后精准人工；后继34及材料25承接。

当前产品规范与执行顺序分别见[单岗位流程](../../../docs/single-job-flow.md)和[统一开发计划](../../../docs/development-plan.md)。本票既有Status、Assignee、完成记录和收据不变；关闭仅证明当时范围，不证明新规范已实现。下方与现行规范冲突的旧审批、白名单、总时间窗及运行门槛保留为历史，由现有后继承接，不重开、不追认，也不据此执行真实申请。

## Question

如何把本次匹配分析选出的经历直接交给现有简历生成器，并把用户确认绑定到具体 PDF 内容？

## Work and reuse

- 复用 tailor_resume、HTML/PDF、source_index 校验、职责边界、缓存和内容 hash，不重建导出引擎。
- 解除 ApplicationResumeStore 对 worker 存在及 prepare_application_task 外部投递条件的提前依赖；材料阶段检查 JD/资料版本，外部填写门禁留给填写入口。
- 把分析选择的贡献/来源传给简历，展示采用与未采用的材料、来源文本、改写及缺口；不重新独立按关键词选出互不相干材料。
- 提供具体版本预览、修订/重生成与确认。用户确认后生成内部绑定，不要求下载再选择 PDF。
- 保留所有历史 PDF 与来源；JD/来源/PDF 更改使旧确认失效，不重复已完成外部上传。

## Ownership

- `src/career_evidence_graph/application_resume.py`
- `src/career_evidence_graph/application_flow.py`
- `src/career_evidence_graph/career_portal.py`
- `tests/test_application_resume.py`
- `tests/test_application_flow.py`

以上为责任范围，不表示必须修改每个文件。多人同时工作时不得回退他人修改；共享接口按已完成依赖契约衔接，必要时先协调文件所有权。

## Acceptance criteria

- [x] 无 URL、worker 未启用时可生成并预览专用简历；明确缺失个人资料时停在可处理状态。
- [x] 分析→改写→PDF 全程 source/责任/版本可追溯；不得把设计、模拟或团队成果写成个人完成事实。
- [x] 修订和缓存失效测试通过；有效 PDF 字节可供 worker 直接绑定，超过既有上传限制有明确反馈。

## Verification and evidence

- tests/test_application_resume.py（含现有 PDF→worker 绑定场景）
- 先执行受影响的有意义测试；涉及共享流程/存储时按 CONVENTIONS 完成完整离线验证。浏览器合成与真实 ATS 分开记录。
- 关闭前将实际修改、所用版本、检查结果与限制写入本票 Resolution comment，并链接资产；不能用通过数或历史报告代替本票当前输入验收。
- 真实资料与私有衍生信息只保存在私有位置。本地图中的报告仅使用合成/脱敏状态，不嵌入真实字段、附件、岗位 URL 或私有指纹。
- 自动最终 Submit 保持为零。未知外部动作不自动重试。源码通过、安装版通过、真实填写、人工提交和雇主接收分别报告。

## Resolution comment

2026-10-17：03、04 已关闭，01a146b9/source_bundle 核对依赖并领取。当前执行无 URL 的分析选材→简历生成 tracer，后续验证来源、版本、缓存和 PDF 字节保护；尚未声称票据验收完成。

2026-10-17 简历模块实现移交，等待根执行者整合及完整离线 gate 后关闭：

- [ApplicationResumeStore](../../../src/career_evidence_graph/application_resume.py) 新增 `generate_for_task(id, revision, *, source_snapshot, analysis, force_regenerate=False)`；复用既有测量、tailor_resume、source_index 校验、HTML、PDF 和私有版本目录。新路径只核验 CAS、非空 JD、完整来源快照、分析版本/配置及分析引用的个人 eligible 选材，不调用 URL/worker 投递准备门禁；旧 `generate` 保持原投递门禁。
- 新路径直接采用本次分析的 `selected_source_ids`，不再按关键词做第二次选材。已选、采用、已选未用与未入选材料分别返回，保留原文 `source_text`、改写、来源身份、责任与 Boundaries；不符合个人归属的材料保持 ineligible。设计文本禁止改成实施成果；注入的三参数 tailorer 也不能绕过该保护。
- 公开 `resume_configuration_revision(store=None, *, environment=None)` 与 `store.configuration()` 绑定已加载简历引擎、Codex 设置、实际 CLI 路径/文件 metadata 及具体 tailorer/model_runner 身份。默认生产配置稳定；注入回调的实例 nonce 防止跨服务误用缓存，替换回调会改变版本。已知 `partial(run_codex_exec, environment=...)` 按实际环境核验 CLI，配置不记录凭据。
- 模型调用前后及 PDF 导出后再次检查 JD、全部来源与实际生成配置。发生漂移即停止发布，原尝试目录及 `input.json`、`source-snapshot.json`、模型输出仍保留供核验。缺个人资料明确报告私有 `sources/profile.json` 的缺失或格式问题；不要求先建立公开网站。
- 缓存绑定语义 JD、完整来源 revision、分析配置/选材及实际生成策略。仅备注改变时复用原 PDF，响应使用当前 CAS，历史 manifest 字节不改；等价新分析可复用 PDF，同时返回当前 `analysis_binding` 与原生成的 `generation_analysis_binding`。显式 `force_regenerate=True` 生成新 UUID，保留原 PDF/来源清单。
- 输出 PDF 必须含 `%PDF-` 头且为 1..700000 字节，文件为 0600；不合格 PDF 留在原尝试目录，不能发布成功 manifest。响应含具体版本、`pdf_sha256`、`resume_configuration_revision` 与 worker 所需的文件名/base64；确认和 worker 绑定前的服务端再读由根执行者接线。
- [专项测试](../../../tests/test_application_resume.py) 新增 29 项场景，覆盖无 URL/worker、分析选材/归属、版本伪造、模型在途漂移、个人资料、语义缓存、原 PDF 变化、显式重生成、实例配置隔离、实际 CLI 环境及三参数 tailorer 兼容。最终联合命令：`UV_CACHE_DIR=/private/tmp/tomorrowstar-single-job-uv-cache uv run --locked python scripts/run_pytest.py tests/test_application_resume.py tests/test_career_portal_data.py tests/test_application_flow.py tests/test_application_match.py -q`，结果 **233 passed, 2 deselected**。两文件 Ruff check/format 与 `git diff --check` 通过。默认 marker 未运行真实 PDF 浏览器测试。
- 本次移交基线 HEAD `e4a26d0c24311d014d478f7f92e58a88e6709b4b` 加保留的 dirty 工作区。`application_resume.py` SHA256 `685bc9856a5ca605303d372141d7f20548302d9fc3c3aac4302e5db6fded3136`；专项 SHA256 `96c97883bab175ac9df73f5080fcfa172dcc17863ee8615e4605b56abc002f03`。后续根执行者的流程/HTTP/安装版证据另记，不能套用本次源码输入通过。
- 本次只使用合成资料、模型 runner 和 PDF exporter 替身，没有真实模型调用、浏览器启动、真实资料改写、附件上传或最终 Submit。源码保护通过仍不等于改写语义的人审或安装版/真实 ATS 验收。


2026-10-17 根执行者整合验收与关闭：

- HTTP tracer 验证无 URL/worker 时完成分析、生成、预览与具体 PDF 确认。服务端从当前分析读取选材；配置变化只使材料失效，保留有效分析。显式重生成保留历史并撤销旧确认；已有 worker 绑定时拒绝重生成。PDF 内容漂移在确认与执行绑定前拒绝。
- 独立审计复现后修复取消任务被资料更新复活的缺陷；两组反例先 RED 后 GREEN，flow 专项 17 passed，独立 guard 18 passed。整套默认离线验证 **1846 passed、140 deselected，229.54s**。Ruff check/format（199 文件）与 git diff --check 通过。随后 intake 的独立增量验证另属推荐票，不据此声称安装版或真实 ATS 通过。
- 本票材料闭环已完成源码与合成 HTTP 验收。真实模型改写的人审、安装版和实际附件回读留给后续明确票据；未执行自动最终 Submit。
