# Prism-local 编辑与最终 PDF 接续

**P06 原交付与 J06 JSON 内容接回。** 当前顺序见[开发计划](development-plan.md#stage-plan-2026-10-23)及[实施地图 P06](../.scratch/resume-agent-delivery-2026-10-22/map.md#p06-prism)，证据见[P06 记录](../.scratch/resume-agent-delivery-2026-10-22/p06-source-verification.md)。源码、隔离合成编排、缓存原生编译器、真实服务、私人材料与安装版分别接受。本轮不修改私人 TeX/PDF，不安装或重启主 App。

## J06 当前行为

固定姓名、联系方式、教育和样式仍是 LaTeX 模板原文。人工返回沿用现有
`begin-prism-edit`、`finish-prism-edit` 和 `capture-prism-result`，不新增编辑平台。
可变条目的字面文字、链接、删项和顺序修改，只有精确重新渲染一致时才采用为
人工 JSON 子版本；人工新增不伪造库引用。人工改变列表的完整结构随采用版本保留，
后续作者和终审不能恢复删项或重排它。固定模板、任意宏和跨块修改保存为
`unmerged`，保留完整源、diff 与父内容引用，停止会覆盖它的自动重建。
手工构建仍可采用；不将旧 JSON 声称为该人工稿的完整来源。

快速文字校对仅允许当前可变条目范围内的局部补丁，固定资料、经历标题和排版
均不由校对改写。捕获原文、校对响应、条件写入及最终采用分别持久保存；重开
先采用可核验结果。请求已发出但结果未知时保持 `prism_edit_needs_recheck`，
不盲重发。迟到人工修改与上一终稿均保留。

生成项目和原生依赖绑定支持已有根 Git 目录及既有同步状态，不启动或修改同步。
符号链接、Git 重定向、嵌套仓库和不支持的配置仍拒绝。`.git` 不进入源归档或
编译依赖。只读提交 blob 与当前源由程序比较，记录确切 HEAD 和 diff 来源；
不执行 worktree `git diff` 的 clean filter，也不将已自动提交后的“上一提交 diff”
冒充本次修改。人工编辑的归档基线仍是内容接回依据。

当前实际 Prism 工作树与临时合成 Git 工程已验证连接、条件保存、真实 Tectonic
编译和原生回执读取。该外部工作树有既存修改；此结论不等于纯基线提交、用户
服务、私人文稿或安装版接受。详见[J06 验证](../.scratch/json-resume-delivery-2026-10-24/j06-verification.md)。

## 当前源码接口

P08 将实际 subagent 采用稿送入临时真实 Prism 服务，验证原生自动编译及只读
接回；它与用户服务更新、私人文稿质量及安装接受分开，见[组合交付](combined-delivery.md)。

普通自动材料沿用 `ApplicationFlowService` 和现有认证/写入保护。以下 POST
动作均传 `task_id`、`task_revision`：

| 路由 | 作用 |
| --- | --- |
| `/api/flow/begin-prism-edit` | 保留当前终稿，持久化人工编辑写锁，连接同一源项目 |
| `/api/flow/finish-prism-edit` | 明确读取人工主文档，一次快速校对，保存局部补丁与独立版本 |
| `/api/flow/capture-prism-result` | 只读已有成功结果，核验当前源/实际依赖/PDF 后采用新终稿 |

`local-material/v1` 将人工主文档版本与最终 PDF 分开保存。主文档捕获不是完整
可编译工程证明；PDF 采用另归档原生记录器给出的完整实际本地依赖。校对当前
限定独立主文档，多文件正文明确保留并提示不支持，不能声称已完成全稿校对。
原 AI 内容终审保留为来源历史，不要求人工表达再次通过它。

旧 Prism 的时间戳接口不能证明对应关系。新连接器使用 `GET /api/build/result`
的 `prism-build-result/v1` 回执及 `POST /api/file/conditional` 源哈希条件保存，
来源与许可见[引用记录](../references/README.md)。服务缺少这些能力时保留原文
和上一终稿，不回落重复 build 或无条件写入。Tectonic 多文件记录歧义、无法追溯
工具输入、缺记录器或外部依赖均明确停止对应采用；不宣称任意布局支持。

## 日常入口与职责

最终简历 PDF 区并列“打开最终 PDF”“在 Prism 中编辑”。后者进入当前岗位已有 TeX，不另开一份无关底稿。人工编辑期间系统暂停写入，Prism-local 使用自身已有自动编译和预览；App 不另建编译器、不添加保存后编译开关、不在每次预览/下载/返回时强制 build。

用户明确点击“完成编辑，返回校对”后，系统读取本次人工版本；关闭窗口不是完成信号。人工稿只进入快速文字校对，**不接回 AI 内容终审**：

- 可以修正明确拼写、语法、大小写、标点、重复词小错，输出局部文字补丁并记录。
- 不质疑事实或能力，不增删/润色内容，不改顺序、排版、字体间距或 TeX 命令。
- 歧义、专有名词和可能改变含义的修改保留原文，仅提示；人工意图优先，不把变化回写两库。

AI 新生成稿仍按[生成契约](resume-agent-generation.md)进入单一内容终审；它检查新表达忠实性，信任上游事实/推断，不重判匹配。两条路径不能混用。

## 源、PDF 与历史

App 复用 Prism 已有成功编译结果，记录它对应的 TeX 与实际本地编译依赖；文件对应关系不含无关目录、源库/JD、App/模型/提示词、登录元数据等全局版本。生产环境和编译器信息可保留为历史，不据未来变化判旧 PDF 失效。

- 当前源对应成功 PDF：显示已同步的最终 PDF。
- 人工改源、尚无对应成功结果：显示有未导出修改，上一版终稿仍可读。
- 编译失败/结果不明：保留源、产物和旧终稿，展示诊断/待核对；不重写 TeX，不盲目触发第二次编译。
- 已有新成功结果：采用对应源/PDF 后保留旧版本；迟到旧结果不能覆盖较新的源或终稿。
- 预览、下载和历史读取只读已保存产物，检查文件完整性，不重复审核内容或重扫两库。
- 网站附件继续指向实际上传的 PDF；新 PDF 的采用不代表远端已替换。

当前连接器对项目布局/依赖的支持范围须据真实接口验证，不能凭此目标宣称已支持任意多文件 TeX。采用结果时核对源/PDF 对应，正是本步骤的职责，不再扩展为全库“新鲜度”检查。实际缺少服务能力时明确报告，不通过新增例行授权或第二编译平台绕过。

## 旧接口说明的地位

以下原文保留旧可选准备模式、严格 build、逐组审阅、技术导出授权和安装证据。它们是历史/兼容记录，**不得作为默认应用的人工后内容重审、重复编译或全局材料失效要求**。新目标的实施/真实接受以开发计划和地图为准。

<details>
<summary>旧 Prism 连接器、准备模式与历史安装说明</summary>

## Default applications and optional material tools

The [single-job flow](single-job-flow.md) defines product behavior; the
[development plan](development-plan.md) orders the changes. This page retains
the existing optional Prism/preparation interfaces and their versioned evidence.
Their group reviews, imported-source technical-export authorization and
preparation-only restrictions belong to those explicit modes, not daily product gates.
This update changes documentation only, not the connector, installed App or receipts.

Normal jobs automatically receive a complete tailored résumé, necessary materials,
source/content and PDF technical checks, compilation and upload up to manual Submit.
Technical checks do not establish real content quality or visual layout acceptance. High-value,
high-match jobs receive complete analysis and material drafts before precise user
adjustment. Editing pauses page automation; one Continue action preserves the
user's changes and resumes the remaining steps. There is no separate acceptance
of each experience group, full source or PDF. An independent editor remains useful
for optional inspection; viewing it is not required for a normal application.

Reuse applicable career facts and information-library answers. Explicit career
additions/corrections go directly into the career library with source and history.
Source or citation problems mark the affected item; an important unresolved conflict
pauses the current job. Only affected content is updated, using the user's edited
material as its base. Model configuration changes leave usable results valid.
Routine compilation and technical validation remain system work, not user approvals.

Normal interrupted work resumes after reopening; deliberate pauses and waits remain.
An operation with an unclear result is reconciled first and prompts the user only
if still unclear. The system never clicks final Submit. After the user submits,
it recognizes clear success and records the outcome automatically.

The source implementation shares `ApplicationResumeStore.generate_for_task`,
`application_full_latex.generate_full_latex`, `export_for_draft` and `PrismClient.compile`
between complete automatic materials and optional preparation. Default automatic
materials bypass the group-review panel and expose saved PDF preview and complete
source editing directly. A missing full base waits for that base instead of using
the old short résumé. The former HTML résumé path is retired in all modes.
The [call and retention map](../.scratch/ticket39-41-source-2026-10-21/materials-entrypoints.md)
records the earlier branches and supporting regressions; the LaTeX-only policy above supersedes its HTML branch. This page does not
authorize App updates, compilation of personal material or real applications.

## Existing connector implementation

The remainder documents the existing preparation mode, its UI controls and old
restrictions. Instructions to approve, review or authorize describe that retained
interface only; they must not be copied into new product requirements.

Material preparation can bind an existing, dedicated LaTeX project to a saved
job draft. The review panel connects to an already running prism-local editor
and opens it in a separate tab. Edit the source and inspect its PDF there; return
to TomorrowStar to capture the saved source/PDF version. Explicit preparation
group reviews remain available where the task has a group session.

The LaTeX source is the document used for export. This path does not regenerate
HTML from the initial JSON draft. Prism performs a strict build of the reviewed
source; TomorrowStar retains that source, its source archive and the resulting
PDF as a separate export attempt. The current material panel saves and previews
that PDF without another per-PDF confirmation. Existing imported-source acceptance
receipts remain readable; they are not a routine application prerequisite.

In the original whole-draft path, reading an edited source clears the current
review and PDF selection while retaining history. The grouped generated-source
path below can inherit explicitly verified unchanged group reviews. Historical
deliveries recorded separate PDF approvals; the current panel does not request them.
An uncertain build requires receipt reconciliation
before another attempt; refreshing does not repeat compilation.

The current connector supports a standalone main document in an independent
local project without a Git ancestor, the standard `build/` output folder, and
the normal Prism builder without custom build commands or shell escape. It
does not start editors, Git synchronization, an agent or a model provider.
Unavailable services and unsupported project layouts leave the draft unchanged.

The backend discovers an existing editor through the loopback Prism Home
service at port 8790. `TOMORROWSTAR_PRISM_URL` can select another loopback HTTP
service. The connector verifies project identity before returning its editor
link or requesting a build. Source changes during a build stop adoption.

<a id="generate-a-complete-job-specific-latex-version"></a>

## Existing preparation interface: generate a complete LaTeX version

The checkout uses `resume-presentation/v1`. Education reuses documented fixed
facts and source wording; JD relevance cannot remove or rewrite it. Unchanged
supported education does not need another per-group factual confirmation.
Conflicting or unsupported education stays outside the adopted body until resolved.
Skills and work experience can be selected, ordered and rewritten for the actual
JD while retaining factual, team, collaboration and planned/completed boundaries.

AI assistance, coding-agent and editor/tool-use provenance stay in the internal
source and review records. They are not disclosures in the employer-facing CV.
This does not prohibit supported technical skills or project technologies.
Generation and edited-source admission check this policy. Historical drafts keep
their original policy and evidence; they are not retroactively accepted or rewritten.
The explicit preparation path retains group-review and imported-source controls.
Default automatic materials use technical checks and save the PDF directly.

In the current checkout's preparation workspace, complete the normal job analysis,
then use **完整 LaTeX 简历底稿** on that task. Explicitly select the existing
independent project directory and main file. Binding reads and fingerprints the
saved source without launching Prism, compiling, or invoking a model. A changed
base clears downstream materials while retaining analysis and historical artifacts;
active stages, unknown exports, cancelled tasks and worker bindings block replacement.

Select **生成完整 LaTeX 岗位版本** to generate a separate private source project.
The imported base still requires a standalone main file without Git ancestors.
The independent generated project carries an explicit `generated-latex-project/v1`
source policy, bound into its source revision. This policy permits a Git ancestor
so the private preparation workspace can remain versioned. Git metadata anywhere
inside the project, symlinks, external includes and unsupported layouts remain
blocked. The file, count and total-byte limits remain unchanged. Direct imports
and old four-field source bindings retain the original strict policy; historical
drafts are not migrated. Archive, review, editor and export checks retain the
saved policy and reject an unknown or changed policy.

Before calling the generation model, the generator creates the independent
destination from the bound base, verifies its source and archive, and saves a
`project-preflight.json` receipt. An invalid or unwritable destination saves a
not-started receipt and stops before the model runs. After the model returns,
the base and destination are checked again before the generated main source is
adopted. This does not compile or accept any material. The original project stays intact.
A4 is applied on the independent copy; unusual direct paper-dimension overrides
stop for source/layout reconciliation. Actual PDF layout remains unverified.

The generator uses the complete saved JD, available career sources, attributed
Contributions and applicable confirmed identity records. It preserves documentary
education and career dates as context, separately from personal contribution or
capability. Conflicting identity records require verification. Application-only
answers do not become résumé disclosure permission; missing answer records do not
erase documented facts. All generated content remains subject to semantic review.

Every original body line belongs to a displayed group: proposed text, reversible
relevance omission, or verification queue. The panel shows original and rewritten
LaTeX, source locators/revisions, responsibility attribution and reasons. Unsupported
source/ownership and unsupported new literal numbers/dates stay outside the body.
Omitted original fragments remain available for restoration in the subsequent
Prism editing workflow. The model must preserve source boundaries and use the
base's existing presentation commands; new external reads, executable constructs
and unsupported environments are rejected. These checks do not prove semantic
fidelity or successful compilation.

Each `origin=generated_latex` version retains complete base/output archives and
main-file bindings, JD/source/analysis/configuration and information-library versions.
Reads verify immutable archives and body coverage; editing the live generated
project does not rewrite a historical checkpoint. Inputs or base changes during
model work prevent adoption. Failed/interrupted attempts remain available and
require explicit retry; refresh/restart does not resume generation.

The existing generated-source path saves `factual_review=pending`. Its historical
2026-10-18 delivery reports recorded no App replacement in those runs and kept
real applications paused. Those are dated observations, not today's installation
status or a product-wide approval rule.

<a id="review-experience-groups-in-the-generated-version"></a>

## Existing group-review differences

| Existing implementation | Product change |
| --- | --- |
| Each group requires a fingerprint/source/preview-bound user receipt; unchanged receipts can be inherited. | Keep sources and editable groups; ordinary jobs use automatic checks, while high-value jobs receive one focused handoff. |
| Unresolved education, group mapping, preamble or ancillary-file changes can block the entire export. | Isolate affected claims; ask only about an important unresolved fact or conflict. |
| JD/source/base/configuration freshness is checked for the whole draft. | Update only affected content, preserve manual edits and reuse valid results after model configuration changes. |

Technical records remain useful: original/generated source archives, reversible
omissions, group IDs, source locators, responsibility and strict preview identity.
The model-generated checkpoint itself is not evidence of reviewed capability.
The [2026-10-18 group-review delivery](../.scratch/prism-group-review-2026-10-18/README.md)
retains the old controls, tests, failures and limited verification scope.

<a id="bind-the-reviewed-full-source-and-confirm-its-pdf"></a>

## Existing PDF-binding differences

The explicit grouped preparation implementation retains reviewed groups and a
formal export. The current PDF panel has no further user PDF-confirmation button;
default automatic materials also bypass group review. Existing exports retain `group_review`, draft/input/
source/preview identities, strict build records and PDF hashes; existing material
receipts remain historical records rather than prerequisites for the next job.

Source/PDF consistency and a readable, correctly laid out PDF remain automatic
checks. A complete existing build can be reused without generating or compiling
again. An unclear operation result is reconciled before any repeat. This technical
binding does not prove that the user clicked Submit or that an employer received
an application. The
[2026-10-18 PDF-binding delivery](../.scratch/full-latex-pdf-confirmation-2026-10-18/README.md)
retains the original implementation, acceptance receipts and synthetic tests.

<a id="use-an-existing-latex-résumé-for-a-saved-job"></a>

## Existing preparation interface: use an existing LaTeX résumé

If a job export has an unknown outcome, a separately completed standalone review
snapshot of the exact same project and source can be adopted with **采用已核验审阅快照**.
The App validates the archived source, strict build and expected PDF hash before
saving a separate `reuse_completed_review` export. This operation does not compile
or generate content. It preserves the original unknown attempt and continues to
block this task's execution and source changes, as well as importing a new LaTeX
job task. It grants no factual approval, material
confirmation or application permission. The snapshot directory is configured by
the server; the request cannot choose an arbitrary receipt path.

In **材料准备 → 已有 JD**, expand **使用已有 LaTeX 简历**, enter the
dedicated project directory and main file, then save the material version. This
creates a separate job task and immutable source archive without running an
analysis or generating résumé content. It records `origin=existing_latex` and
keeps factual review pending. It does not claim source selection, qualification,
language acceptance or model generation.

An operator can reuse a prior explicit human decision for the exact imported
source and PDF through `record-retained-material-acceptance`. The request binds
the current task, source and PDF hashes, plus `approval_record` containing the
original receipt hash, UTC acceptance time and statement. Verify the retained
receipt bytes before recording it: the hash is a reference supplied by the
operator, not evidence that the server read that external file. The separate
sealed material decision preserves the original user decision and the operator's
recording time. It does not create grouped generation review, qualification or
application permission.

The App then offers **将此已接受材料纳入暂停批次**. This records one existing
task, PDF and material decision directly in a paused batch, without creating a
task, queueing analysis, generating or compiling. Repeating the same request or
adopting the same material again reuses the batch. Reopening does not resume it.
Unknown export ancestry remains unknown and continues to block execution.

Select **仅授权此版本的技术导出**, then **导出 PDF**. This authorization binds
the exact job inputs, imported draft and saved LaTeX revision. It permits a local
strict Prism build only. The same export, receipt and native PDFKit checks used
by generated job materials validate the resulting source/PDF pair. **读取导出回执**
checks the adopted immutable receipt without compiling again; open the PDF to
inspect the exported document. Factual approval and material confirmation remain
unavailable on this technical path. It cannot start application work.

After source edits, import the saved project again to create a new task and
version; earlier tasks, sources, authorizations and PDFs remain inspectable.
An unknown or running attempt blocks replacement until its existing receipt is
resolved. Refresh, receipt reads and history selection never rerun compilation.

<a id="preparation-refresh-and-source-changes"></a>

## Existing preparation refresh and source changes

A preparation status request shares one career-source observation across its
qualification, freshness and material checks. Later requests still enumerate the
selected documents and check file identity and availability. Unchanged document
content is reused in memory; changed, added or renamed documents pass through the
bounded reader again. The first read after startup remains a cold read. Failed
reads are not cached, so a downloaded or repaired file can recover on the next
refresh. Changes to a saved file are detected even when its size and modification
time are restored. Opened-file identity is checked before and after subprocess
reading; redirected or concurrently changed input cannot populate the cache.

This observation cache applies only to a read-only status projection. New export
and model stages retain their independent freshness checks. Source changes can
make current materials stale without rewriting their draft, review or PDF
history. Historical artifact reads verify the saved adopted record and bytes
without recomputing job explanations or rescanning career content. The flow
service owns the locked adopted-artifact query; HTTP readers retain draft,
receipt and PDF verification. No refresh,
cache hit or source change grants approval or restarts work.

<a id="installed-app-entry"></a>

## Existing independent App entry

The local installation uses **显示 → 简历审阅（Prism）** (**⌘8**) to open
an independent review page inside the App. The same page is available in the
sidebar. No job draft or application task is required.

Use **在 Prism 编辑** to open the existing editor. Save there, return to the App,
and select **读取最新 LaTeX 并核验 PDF**. This explicit action uses a local strict
Prism build to establish the source/PDF pairing; an old PDF or its modification
time alone cannot establish that relationship. Merely opening or refreshing the
review page does not compile.

Each immutable snapshot retains its UTC capture time, version ID, full project
source revision, main-file SHA-256, PDF SHA-256 and page count. The displayed
source and embedded PDF always use the same snapshot ID. Select a prior version
to inspect its original source and PDF. While this page is visible, the App
checks saved sources every three seconds and checks immediately on window focus
or visibility return. Saved changes produce a prompt to read a new version.
**检查源文件变化** remains an optional immediate check. Detection only sends read
requests; it does not compile or capture. It updates the source status without
reloading the displayed PDF or changing the selected historical version.
Temporary connection failures preserve the current snapshot and retry on the next
check. Hidden or inactive review pages do not poll. Unsaved editor buffers are
not read. Clicking capture first reads the latest saved source identity, then
retains the existing source-version guard for the strict build.

All captures remain **待人工审阅**. Reading, compiling and viewing do not confirm
material or authorize applications. An uncertain or interrupted build retains
its attempt and blocks another capture; **核验上次读取结果** checks the existing
receipt without repeating compilation. A complete valid receipt can be adopted;
an incomplete result remains pending. A definite local PDF validation failure
retains its returned output and failed attempt; another read requires an explicit
capture. The installed path uses macOS PDFKit for complete PDFs, including
Tectonic compressed-object files, without a new Python dependency.
The installed macOS App also shares this inspector with job-bound Prism materials,
both when adopting an export and when reading its saved receipt. Inspection
unavailability preserves the attempt for reconciliation without another compile.

The private configuration is
`~/Library/Application Support/TomorrowStar/resume-review.json`, with exactly
`project_root` and `main` string fields. Snapshots are separate under
`~/Library/Application Support/TomorrowStar/resume-review-snapshots/`.
Do not put personal paths, source bodies or document fingerprints in the bundle
or public repository. Synthetic App modes do not load the host configuration.
The editor must already be running; this entry never starts Prism, Git sync,
an agent, a provider, or an application worker.

The previous [editor-opening installation record](../.scratch/native-prism-installed-2026-10-18/README.md)
remains historical evidence. The later
[readback installation record](../.scratch/prism-readback-installed-2026-10-18/README.md)
tracks the independent App review page. The
[automatic-detection update](../.scratch/prism-autodetect-installed-2026-10-18/README.md)
records its later read-only change prompts. Those reports retain their original
material-review and application-pause status; they do not define the current
product workflow or prove that its new behavior is implemented.

## Protocol provenance

The project identity and instance discovery protocol follows prism-local,
revision `e33657e0abd1073ed7f933a371c42c656e59dd7e`, specifically its
`registry.py`, `instances.py` and `server.py`. The source is MIT-licensed,
Copyright (c) 2026 Zhiyuan Deng. The local connector reads existing instances;
it does not expose Prism's registration, ensure/start, agent or Git operations.
No Prism package or new dependency is imported into TomorrowStar.


</details>
