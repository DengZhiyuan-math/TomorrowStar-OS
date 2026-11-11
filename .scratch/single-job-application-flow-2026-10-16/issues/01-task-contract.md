# 建立单岗位任务契约与持久恢复

Type: task
Label: wayfinder:task
Status: closed
Interaction: AFK
Assignee: 01a146b9/task_contract
Created: 2026-10-16
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: none

## Question

如何用一份持久单岗位任务串起 JD、分析、简历和现有 worker，并在重复点击、刷新与重启后保留正确进度？

## Work and reuse

- 新增最小 application_flow.py：只编排分析和材料阶段，填写阶段引用 worker 的 batch/job 身份与状态，不复制浏览器状态机。
- 定义短请求启动、任务快照查询、阶段重试和取消接口；模型调用在后台串行执行，不阻塞 App HTTP 请求。
- 冻结任务 ID、JD/资料版本、分析 ID、简历 ID/hash、材料确认和 worker 引用的契约。输入变化只使受影响下游产物失效，原产物保留。
- 原申请笔记继续由 ApplicationStore 管理；任务状态置于独立私有目录，原子写入，不添加数据库或事件框架。
- 将岗位匹配分析、匹配分、专用简历草稿、申请就绪、已提交、接收回执的术语按既有格式补入或校正 CONTEXT.md；保留 mastery 与 match 的区分。

## Ownership

- `src/career_evidence_graph/application_flow.py（新增）`
- `src/career_evidence_graph/career_portal.py（任务 API 接口）`
- `tests/test_application_flow.py（新增）`
- `CONTEXT.md`

以上为责任范围，不表示必须修改每个文件。多人同时工作时不得回退他人修改；共享接口按已完成依赖契约衔接，必要时先协调文件所有权。

## Acceptance criteria

- [x] 同一阶段重复启动只有一个有效任务/执行；刷新或重开 App 仅恢复观察，不重跑模型、填表或上传。
- [x] 失败、取消、资料过期和待核验可区分；进程中断后不把 analyzing/filling 误报成功，外部动作未知时沿用 needs_recheck。
- [x] 服务端验证任务/输入身份；过期 revision 请求不能覆盖新结果。模型失败重试限于该阶段。
- [x] 合成持久状态及 HTTP 行为测试通过；记录交给后续票的稳定接口。

## Verification and evidence

- tests/test_career_portal_http.py
- tests/test_application_execution.py
- 先执行受影响的有意义测试；涉及共享流程/存储时按 CONVENTIONS 完成完整离线验证。浏览器合成与真实 ATS 分开记录。
- 关闭前将实际修改、所用版本、检查结果与限制写入本票 Resolution comment，并链接资产；不能用通过数或历史报告代替本票当前输入验收。
- 真实资料与私有衍生信息只保存在私有位置。本地图中的报告仅使用合成/脱敏状态，不嵌入真实字段、附件、岗位 URL 或私有指纹。
- 自动最终 Submit 保持为零。未知外部动作不自动重试。源码通过、安装版通过、真实填写、人工提交和雇主接收分别报告。

## Resolution comment

2026-10-16：由 `01a146b9/task_contract` 领取，正在实现持久任务与后台阶段契约。
HTTP 接口由根执行者整合；此记录不表示验收完成。

2026-10-17 代码及合成验证记录（未关闭，等待独立审计和根执行者完整验收）：

- 新增 `application_flow.py` 与 `test_application_flow.py`；`CONTEXT.md` 补入单岗位任务、岗位匹配分析、匹配分、专用简历草稿、已提交及接收回执术语。
- `ApplicationFlowService(applications, explicit_private_root, callbacks=..., input_provider=...)` 使用原子 `flow.json` 和保留的 `snapshots/<task_id>/<revision>.json`；原笔记仍由 `ApplicationStore` 管理。
- 公开请求为 `request(create|start|cancel|update-inputs|confirm-materials, payload)`；`snapshot(task_id=None)` 只观察。`bind_worker` 和 `observe_worker` 仅供服务端适配，不接受浏览器请求。
- `analysis` 与 `resume` 阶段通过串行后台回调运行；结果要求 `id`，简历结果另要求 `pdf_sha256`。每次执行保留独立 attempt 和版本产物，失效或取消的晚结果不采纳。
- `input_provider(application_id)` 返回服务端的 `{application_revision, inputs}`；`inputs` 承载 JD/资料版本。无关备注变化只更新笔记 CAS，不使相同 JD/资料产物失效。
- 本执行者实际执行：`UV_CACHE_DIR=/private/tmp/tomorrowstar-single-job-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_application_flow.py tests/test_application_execution.py tests/test_career_portal_http.py`：**121 passed in 7.74s**。包含合成模型、真实子进程退出后的持久恢复、重复点击、取消晚结果、未知外部结果及只读重开。
- 两个新增 Python 文件 Ruff check/format check 及 `git diff --check` 通过。根执行者负责记录完整离线检查的最终状态及当前代码验收。
- 限制：尚未独立审计完成；未执行真实模型、安装版或真实 ATS；自动最终 Submit 为零。后台写入故障及结果采用时的输入变化窗口正在独立复现，未据此宣告票完成。

2026-10-17 独立审计修复与当前交接：

- `contract_audit` 复现并确认三个缺陷：最终输入核验与结果采用之间存在并发窗口；后台持久化异常可终止 runner 后仍接收任务；关闭后旧模型尚未退出即释放执行锁。
- 已修复：最终输入核验与结果采用在同一申请写锁内完成；后台故障设置 `flow_checkpoint_unavailable` 并拒绝后续写入/入队，`create`/`start` 在写锁内再次验证 runner；旧回调退出前保留唯一执行锁。
- 加入持久化故障及跨实例关闭/重试的回归保护。当前任务专项 **12 passed**；本执行者重新执行 `test_application_flow.py`、`test_application_execution.py` 和 `test_career_portal_http.py`，**123 passed in 7.65s**。新增 Python 文件 Ruff check/format check 与 `git diff --check` 再次通过。
- 独立复核报告：12 项专项、3 项独立防护测试及新 HTTP 测试合计 **16 passed in 1.36s**；核验独立 writer 被最终核验锁阻塞且无死锁，后台故障后拒绝请求并在重开后仅显式重试，旧回调退出前拒绝新实例执行。限定范围无剩余具体阻断项。
- 完整离线结果由根执行者记录于 [verification.md](../verification.md)。本执行者已移交稳定契约；HTTP、完整验收和关闭状态仍由根执行者统一记录。未执行真实模型、浏览器、上传或最终 Submit。


根代理最终整合复验：`tests/test_application_flow.py tests/test_career_portal_http.py tests/test_application_execution.py` **124 passed in 7.34s**（含新增 HTTP 后台短请求与重复点击测试）。既有完整离线回归 **1535 passed、141 deselected**；新增合同与 HTTP 用上述专项补齐，检查分次运行。三项独立审计复核通过，无剩余本票阻断。Python 3.13.14、Pydantic 2.13.4、pytest 9.1.1、Ruff 0.16.0 已实际核对。后续整链最终检查仍由第 09 票负责；本票不代表新模型、PDF、安装版或真实 ATS 通过。
