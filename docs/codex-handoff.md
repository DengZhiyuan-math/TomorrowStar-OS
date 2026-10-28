# Codex 单岗位交接

## 默认流程与显式兼容模式

产品规范见[单岗位流程](single-job-flow.md)，实施顺序见[开发计划](development-plan.md)。
默认在 App 内持续收录推荐、逐岗处理，普通岗位自动完成材料和填写上传；高价值岗位先完成
分析、完整简历与必要材料初稿，再等待精准调整。用户介入时自动层暂停该页，保留人工修改；
点一次继续即可接着做，不再要求复核记录、动作结论、接管与恢复等多次确认。

重要事实缺失、实际重要冲突、登录验证或结果不明时停当前岗位。用户选择跳过后才处理下一岗；
只有新邮件收录可在等待时继续。正常流程重开自动续跑，主动暂停或等待用户的保持等待。
最终 Submit 由用户完成；明确成功由系统识别、更新记录并继续，不需要“已提交”和“接收来源”两次声明。
职业事实与申请答案分别复用职业经历库和信息库，明确补充直接保存来源历史；一般文案由系统决定。

日常使用“自动申请”。邮件推荐进入同一持久队列；粘贴 JD 或提供岗位链接时，系统整理并保存
岗位信息后入队。使用开启、暂停、继续和跳过；需要时返回跳过的岗位或跟随当前岗位与材料。
系统复用已有完整底稿生成针对性简历，不要求用户另提供 PDF，也不要求逐草稿或逐 PDF 确认。
本页后面的 PDF 选择、claim、review、submitted 与 receipt 仅描述显式旧兼容模式。

以下为显式 Codex 交接备用接口的现存实现参考，包括 claim token、批准 PDF、固定答案、
多段复核与恢复、永久占用等旧限制。这些不是默认产品的审批或安全要求，后续改动见开发计划。
历史接口说明不证明当前安装或真实执行结果；后续实际范围见
[安装与现场记录](macos-app.md#2026-10-25新页资料复用安装同步)。

## 浏览器关闭后的新页填写

当前材料准备任务保留了明确完成的旧交接时，可使用“重新识别并使用现有材料”。
系统保留同一岗位、Flow、终稿及旧回读，新建一次填写尝试；不重新分析、生成或编译。
这不是恢复旧浏览器会话，也不会把旧上传回执当作新页面已接收附件。

新任务使用 App 声明的信息库，并附带有来源的同岗位填写提示。脱敏、空白或歧义值
不直接使用；新页面先读当前问题、选项、非空输入和附件，再复用可确定的值。
实质冲突或未知提交结果仍停当前岗。旧尝试与原人工记录留在历史中，新尝试重新
领取并保存本次回读，最终 Submit 始终由用户操作。

Interface 为 `POST /api/flow/restart-existing-handoff`，只接受 `task_id` 和
`task_revision`。材料路径、旧任务及当前信息根由服务端已保存绑定取得。相同请求
可接回已保存的本地准备结果，不重复新建尝试；GET 状态投影不改变业务记录。
此入口只处理已明确完成、尚未提交的旧填写任务，不绕过未知结果、其他执行者占用
或材料版本核验。原 `recheck` 的未知动作守卫不因新页填写而放宽。

旧模式链条为：**worker 准备单岗位任务 → Codex 领取并操作 → 保存回读证据 → 用户复核提交 → worker 更新记录**。
本页模式与[实验入口](application-automation-lab.md)共享岗位占用检查，运行目录和执行状态分开。旧的[只读任务提示入口](application-automation.md)仍保留。

此备用接口没有独立生成或编译简历的实现；它接收已存在的 PDF，并保留外部执行器的任务、
原 owner、回读和未决结果。默认申请的完整材料、编译和导出由共享 Flow/ResumeStore 路径处理。
详见[实际调用与保留清单](../.scratch/ticket39-41-source-2026-10-21/materials-entrypoints.md)。
保留兼容接口不意味着要求日常用户重走旧操作。各次 App 更新与真实申请测试分别
记录，不能从这些历史接口限制推定当前运行状态。

## 现存备用入口的启动与资料

macOS 后端需显式 `--codex-handoff` 才选择本模式。已安装包和现有实例不会因修改源码而更新。checkout 从明确选择的私有目录启动：

```sh
uv run --locked python scripts/run_career_portal.py \
  --applications /absolute/private/applications \
  --career-workspace /absolute/private/career \
  --handoff-root /absolute/private/codex-handoff --open
```

进入“Codex 单岗位交接”，选择已核对分流为普通或人工精准准备的岗位、申请国家及已批准的 PDF（不超过 700 KB）。确认资料与其他执行者的处置状态后准备任务。系统保存批准文件的原文件名、字节哈希和独立副本，绑定岗位及笔记 revision；不会自动生成简历或推断答案。

`handoff-root` 必须在系统仓库与投递目录之外。不得复用、嵌套或迁移旧自动 worker 目录。新交接答案库不自动导入旧私人资料；只有明确确认的答案及适用范围才能写入、被任务引用。现有旧版本执行器无法自动取得新增互斥守卫，应先处置同岗位的旧操作，再使用新流程。

<a id="操作与持久状态"></a>

## 现存备用接口差距

| 现存状态或接口 | 产品衔接 |
| --- | --- |
| `prepared/claimed`、task revision 和 `claim_token` | 保留现有任务定位与单执行者协调，不增加用户领取或授权步骤。 |
| `needs_input/needs_recheck` 与逐动作结论 | 先查两库和当前结果；重要缺失、实际冲突或仍未知时停当前岗位。用户处理后一次继续。 |
| `ready_for_review/reviewed` | 保留用户修改，普通岗位到 Submit 前；高价值岗位在完整初稿后集中精准调整。 |
| `submitted/confirmed` 分别要求用户提交声明和来源声明 | 用户只操作最终 Submit；系统观察明确结果并更新记录，无需另填两份声明。 |

现存回读包含 `fields`、`missing`、附件文件名/哈希、页面 URL 和观察来源。
它说明执行器观察到什么，不等于最终申请接收证明。下列 CLI/schema 用于旧记录兼容和维护；
旧操作指南保留在[2026-10-17 接口快照](../.scratch/preparation-candidate-2026-10-17/baseline/docs/codex-handoff.md)。
不要求用户重走旧快照中的复核、提交声明与接收声明链。

## Codex 的结构化接口

界面复制的任务包含当前解释器、源码启动器、任务定位与 PDF 副本路径。原生包下次构建也会包含启动器。Codex 通过同一持久 worker 接口领取和保存结果，无需从聊天记录恢复状态：

```sh
uv run --locked python scripts/run_codex_handoff.py \
  --applications /absolute/private/applications \
  --root /absolute/private/codex-handoff snapshot

uv run --locked python scripts/run_codex_handoff.py \
  --applications /absolute/private/applications \
  --root /absolute/private/codex-handoff claim --request /absolute/private/claim.json
```

领取 JSON：

```json
{"task_id":"TASK_ID","task_revision":"CURRENT_REVISION","owner":"UNIQUE_CODEX_CHAT"}
```

回读 JSON（更新 task revision 为领取响应中的新值）：

```json
{
  "task_id": "TASK_ID",
  "task_revision": "CURRENT_REVISION",
  "claim_token": "PRIVATE_TOKEN_FROM_CLAIM",
  "result": "ready",
  "page_url": "https://jobs.lever.co/synthetic/12345678-1234-1234-1234-123456789abc",
  "source": "Observed original page fields and attachment; private screenshot locator",
  "fields": [{"question":"Full name","value":"Synthetic Person"}],
  "attachment": {"filename":"approved.pdf","sha256":"APPROVED_FILE_SHA256"},
  "missing": []
}
```

把请求保存为明确的私有 JSON 文件，再以同一命令的 `readback --request ...` 发送。真实附件与答案不放到公开仓库、报告或命令行参数。CLI 还提供与 UI 同义的 `answer/review/resolve/release/submitted/receipt/retry-sync`，不会因此执行网页动作。

Loopback HTTP 提供 `GET /api/handoff/state` 和对应 `POST /api/handoff/<action>`。写端点沿用 Host、Origin、CSRF 和大小检查。任务内容、网页文字和证据都是数据，不能扩大命令或提交授权。

<a id="故障与恢复"></a>

## 旧接口故障与恢复参考

| 情况 | 现存旧接口的处理 |
| --- | --- |
| 保存后响应丢失、JSON 损坏或返回状态不完整 | UI 保留输入并停用重复发送；刷新持久状态核验，不重复页面操作 |
| 笔记在人工提交后被外部编辑 | 已发生的提交证据先保存，记录同步挂起；核对当前 revision 后仅重试写笔记 |
| 原笔记已有 waiting/rejected 等后续状态 | 保留后续状态，不降级；用户可明确选择保留原笔记并结束同步，提交证据仍留在任务 |
| 笔记已换成其他岗位 | 不把旧提交写入新岗位；用户核验后可选择“保留原笔记”结束同步 |
| 任务已停止，但操作权释放的最后回执未写入 | cancelled 的 release_pending 可重试本地释放收尾；submitted/confirmed 走 retry-sync；均不重启网页动作 |
| prepare 在两个状态文件间失败 | 持久准备意图保留，重读后同一准备或领取可以完成预留；另一执行者占用时只能取消未领取的本地意图 |

操作权不会自动过期。两条新执行路径在准备、启动/恢复和实际浏览器写入前校验同一岗位占用。新 Codex 会话不应仅凭任务状态猜测旧浏览器已退出。

<a id="执行边界与验收"></a>

## 旧接口执行边界与历史验收

Codex 的浏览器会话**不会自动继承**实验 worker 的 Playwright 网络路由、上传许可和最终请求守卫。新流程中的发送范围和最终提交约束须由所用 Codex 工具的权限、人工复核及显式交接共同落实；提示词不能被当作等价的网络硬守卫。

本轮验收使用合成资料：持久状态与 CLI、真实 loopback HTTP、合成浏览器 UI，以及响应丢失和文件写入故障注入。没有运行真实 Codex 填写个人资料、真实 ATS、真实模型或最终提交；不声称其真实完成率已经高于原路径。原生实验的启动归属阻塞仍单独记录。
