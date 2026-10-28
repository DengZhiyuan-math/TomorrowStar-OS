# 接通 Codex 岗位分析与可解释匹配评分

Type: task
Label: wayfinder:task
Status: closed
Interaction: AFK
Assignee: 01a146b9/task_contract
Created: 2026-10-16
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [建立单岗位任务契约与持久恢复](01-task-contract.md), [确定岗位匹配评分与未知证据规则](02-match-policy.md), [建立分析与简历共用的真实资料快照](03-source-bundle.md), [以历史已投递与推进岗位审定匹配评分基准](13-historical-match-benchmark.md)

## Question

如何让 App 收到完整 JD 后在后台调用现有 Codex CLI，产生有来源、可复核且与当前输入绑定的匹配报告？

## Work and reuse

- 复用 run_codex_exec、可执行文件发现、结构化输出、错误/超时记录。新增匹配结果 Schema，不新接模型供应商或代理框架。
- Codex 提取岗位字段和逐条要求，提出证据对应与 gap/partial/supported/unknown 判断；总分由已确认规则计算，不能只信模型整数。
- 验证 source 引用和输入版本；保留公司/岗位提取的不确定项，允许纠正而不生成重复笔记。
- 只粘贴 JD、没有投递 URL 或 worker 不可用时，仍可完成分析。评分不修改个人能力图或投递状态。
- 阶段产物和缓存绑定 JD、资料快照、规则及实际模型配置；失效/失败不能回退成伪成功。

## Ownership

- `src/career_evidence_graph/application_flow.py`
- `src/career_evidence_graph/codex_cli.py（仅必要复用改动）`
- `src/career_evidence_graph/career_portal.py`
- `tests/test_application_flow.py`
- `tests/test_codex_cli.py`

以上为责任范围，不表示必须修改每个文件。多人同时工作时不得回退他人修改；共享接口按已完成依赖契约衔接，必要时先协调文件所有权。

## Acceptance criteria

- [x] 合成 Codex double 通过 HTTP→后台任务→匹配报告；无 URL/worker 场景可用。
- [x] 无效引用、Schema 错误、超时、CLI 未登录/缺失及处理中改 JD 均显示正确错误或过期状态，原 JD 保留。
- [x] 评分规则测试向量逐一通过；分数与未知/硬条件解释一致，Skill mastery 和已投递状态不变。

## Verification and evidence

- tests/test_codex_cli.py
- tests/test_jd_comparison.py
- 先执行受影响的有意义测试；涉及共享流程/存储时按 CONVENTIONS 完成完整离线验证。浏览器合成与真实 ATS 分开记录。
- 关闭前将实际修改、所用版本、检查结果与限制写入本票 Resolution comment，并链接资产；不能用通过数或历史报告代替本票当前输入验收。
- 真实资料与私有衍生信息只保存在私有位置。本地图中的报告仅使用合成/脱敏状态，不嵌入真实字段、附件、岗位 URL 或私有指纹。
- 自动最终 Submit 保持为零。未知外部动作不自动重试。源码通过、安装版通过、真实填写、人工提交和雇主接收分别报告。

## Resolution comment

尚未领取或执行。后续执行者先填写 Assignee，再在此追加事实与证据；本段不是完成结论。

2026-10-17：全部依赖已关闭；`01a146b9/task_contract` 领取独立 analyzer/scorer 模块。
根执行者负责 flow/HTTP 接线，当前尚未完成验收。仅使用合成模型响应，不运行真实模型或浏览器。

### Analyzer/scorer 实现与合成验证（待根执行者整合验收）

- 新增 [application_match.py](../../../src/career_evidence_graph/application_match.py)、[专项测试](../../../tests/test_application_match.py)；[政策向量](../../../tests/fixtures/application-match-v1.json)扩展至 13 个独立预期，包含硬条件部分支持、已支持及重复要求。
- 稳定 API：`calculate_match_score(requirements)`、`analyze_job(application, snapshot, directory, runner=run_codex_exec)`、`match_configuration()`、`match_configuration_revision()`。`directory` 必须尚未存在且位于明确外部私有目录，采用原子创建，结果 ID 为目录名。
- 评分执行已确认的 `documentary-match/v1`；未知区间与覆盖独立，硬条件 gap 为 `conflict`，partial/unknown 为 `needs_input`，硬条件全部支持为 `supported`，无硬条件为 `not_specified`。不设置填写分数阈值，不写 mastery、偏好或投递状态。
- 输出包含 JD/资料/配置版本、逐项要求及原始来源 metadata、确定性分数、`selected_source_ids`、岗位字段不确定项、覆盖范围、限制和模型身份记录。JSON schema 与运行时拒绝模型最终分数或审核状态升级；来源必须当前可用、revision 匹配、实际进入上下文，选材必须已被当前分析映射且属于可选原 item。
- 唯一 prompt 岗位输入为 company、role_title、location、完整 job_description；不传申请备注、策略或 next_action。Contribution 全文引用继承 item 归属边界，团队、他人及设计材料不能升级为个人实施；来源不充分保持 unknown。
- 上下文上限为 96,000 UTF-8 字节；完整 JD 超过 48,000 字节显式失败并保留原文。职业资料按实际字节预算裁剪，返回被遗漏的 source ID 及被截断来源的确切字符区间；不应用旧简历 40 候选或 4 条选材限制。42 项 Contribution 合成覆盖已验证。
- 私有目录保留 input、完整 source snapshot、schema、模型原始输出或失败记录、context coverage 和验证后的 analysis；CLI 缺失、未登录、超时及模型/引用错误只返回无私有内容的 `PortalDataError`。
- 配置摘要绑定已加载引擎、提示词版本、schema、requested model/reasoning/sandbox/executable。报告另保留实际 CLI/model metadata，并明确未固定模型 alias 的漂移限制，不虚构 immutable model snapshot。
- 当前专项 **37 passed in 1.49s**。随后运行 `tests/test_application_match.py tests/test_codex_cli.py tests/test_jd_comparison.py`，**101 passed, 1 deselected in 16.69s**。两个新增文件 Ruff check/format check 与 `git diff --check` 通过。
- 当前限制：待独立审计、HTTP→flow 后台整合及完整离线验证。未执行真实模型、浏览器、上传或自动最终 Submit；以上均为合成结果。

### 独立审计修复及引擎移交

- 独立审计复现：个人 Scope 的归属可被错误延伸至全文其他团队内容。新增 RED→GREEN 回归后，`<document.id>:document` 仅提供上下文，不能承载个人完成或正向支持资格；个人主张必须引用具体可用 item locator。全文 metadata 单独保留 `item_attribution`，不把全文标为个人所有。
- 模型配置指纹现按冻结环境解析实际 CLI 的绝对路径，并绑定文件 device/inode/size/mtime/ctime/mode 的元数据摘要；PATH 切换及同路径替换均改变版本，显式无效 CLI 不回退。指纹函数不执行 CLI。
- `analyze_job` 在调用前冻结环境，用同一环境计算配置并调用 `run_codex_exec(environment=...)`；报告的 `configuration_revision` 仅来自该次冻结请求，不从结束时可变环境重新推断。来源、JD 和任务 ABA 绑定由根执行者的 flow 适配统一核验。
- 最新引擎专项 **41 passed in 1.78s**。重新运行 `tests/test_application_match.py tests/test_codex_cli.py tests/test_jd_comparison.py`：**105 passed, 1 deselected in 17.31s**。Ruff check/format check 与 `git diff --check` 均通过。
- 独立审计在前一测试快照核验两项引擎修复：40 项专项与 2 项独立防护合计 **42 passed, 1 deselected in 1.99s**，未发现这两项的剩余阻断；其后新增显式缺失 CLI 不回退的合成回归。HTTP、flow 与完整离线最终状态仍由根执行者记录。
- 用户新增历史申请及进一步回复的校准要求后，本实现保留为未经真实历史结果校准的 `documentary-match/v1` 原始政策基线。未更改原公式，未据此声称经验校准完成；最终评分与本票关闭须等待根执行者的历史校准工作和所需复核。
- 引擎代码及两个合成资产已移交根执行者。此记录不含真实样本标签、计数、私有字段或派生指纹；未执行真实模型、浏览器、上传或最终 Submit。

### 根执行者最终整合与验收

- HTTP→flow→Codex boundary 的合成链已通过。分析不要求 URL、profile 或 worker；短请求在后台执行，结果和输入绑定到不可变任务产物。改变 JD、完整资料、实际 CLI/模型配置或历史基准会拒绝复用旧报告，原申请状态不变。
- 模型适配前后核对 company/role/location/完整 JD、来源快照、实际配置和 application revision；A→B→A 的输入竞态已用两个独立 RED→GREEN 场景修复。完成提交处再次在写锁中核验，过期结果只留历史，不被采纳。
- [历史参照票](13-historical-match-benchmark.md)已关闭并回读当前私有基准。报告新增 `historical_reference`，数值仍由用户公式确定；参照版本纳入任务输入。缺失、无效或过期基准明确不给相对位置，不伪造成功。
- 精确学历来源只允许 documentary/unknown，受对应文档可用性和版本核验；不能升级个人 mastery 或进入简历选材。模型 gap 提议未经个人事实确认时按 unknown，并保留原提议及解释；原始 known-gap 计算向量和硬条件语义不变。
- 引擎专项 **50 passed**；flow/HTTP/基准与分析联合 **203 passed** 的前次快照后，新增缺口及数学一致性专项亦通过。最新默认离线全量 **1745 passed, 140 deselected, 223.30s**；Ruff check、format check（197 files）及 `git diff --check` 通过。并行新增的邮件入口审计修复另由第 14 票记录当前专项证据。
- 独立审计对学历与未确认缺口路径复核 **12 passed, 38 deselected**，未发现该范围具体阻断。真实历史诊断有通过及来源拒绝，完整边界见第 13 票；这不是预测有效性或安装版验收。
- 本票完成软件分析接线与已审定历史区间参照。未执行 ATS、上传、自动最终 Submit，未写个人 Skill mastery 或已投递状态。界面、材料、worker、安装版及真实 Gmail App 业务验收仍由后继票完成。

