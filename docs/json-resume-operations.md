# JSON 简历与经历库操作入口

J01/J02 提供 JSON → subsection → 完整 TeX 的合成验证入口。J03 已重构现有经历
存储、同步和默认事实读取入口；J04 已接入现有读取、匹配及阶段恢复。
J05 已将内容 JSON 写作、单一终审和版本采用接入同一材料 CLI，操作见下文。
J06 已接回 Prism 人工修改、已有构建及中断恢复；J07 已重构申请 JSON 主存储；
J08 已连通现有主流程与 Worker 材料接续，见[J08 验证](../.scratch/json-resume-delivery-2026-10-24/j08-verification.md)。
所有简历输出为**英语**。合成模板使用 LaTeX 默认字体；实际接受模板保留原有样式，
不增加字体依赖。原始职业资料仍可保留其原语言。J01–J08 源码与合成验证、
[选中真实输入验证](../.scratch/json-resume-delivery-2026-10-24/real-input-verification.md)均保留原范围。
后继完整转换和材料验证见[完整真实输入记录](../.scratch/json-resume-delivery-2026-10-24/full-real-input-verification.md)。
原 P04 失败恢复与同 ID 源码快照主流程的当前状态，见
[P04 与主流程记录](../.scratch/json-resume-delivery-2026-10-24/p04-mainflow-verification.md)。
本阶段未更新安装版、连接用户 Prism 服务或启动真实 ATS；临时合成 Prism 验证单独记录。

## 现有经历库入口

现有 `scripts/run_career_experiences.py` 已支持 `content` 语义 JSON 保存，以及
`preview-import`、`import` 两个显式导入动作。它们复用现有 `CareerLibrary` 和
不可变版本存储，不使用另一套演示库。完整操作见
[经历 JSON 与来源导入](career-experiences.md)。

新结构化记录使用 `experience-record/v2`，其中 `content` 使用
`experience-facts/v1`。旧 `body` 及历史保持可读；已有旧记录转为 `content` 必须
逐段映射原文。预览不写库；发布要求覆盖完成，并校验当前 `expected_revision`。
结构、范围或引用不完整时拒绝发布。覆盖检查不代替语义审核。
同一入口也支持已有结构化记录的新增资料导入：只映射未覆盖或上下文变化的材料，
程序保留原事实和来源引用，新增引用必须有映射。已有事实更正继续使用 `save`。
普通保存不能自行提交覆盖记录；空导入或同内容重放不能清除真实读取失败。

默认分析读取逐条 JSON 事实及责任、状态、范围和来源上下文。来源同步保留已更正
事实，只补充关联资料；新增或变化资料保持待导入。历史 TeX 保存在材料档案，
不进入默认事实输入；教育提供已记录及已更正的 `profile_record` JSON。

初始全部当前申请经历现已通过原条件保存接口完成转换。原 ID、原始文件、材料与
不可变历史保留。额外保留的研究身份另存为仅供申请的记录，不修改研究身份或审核。
人工接受措辞已有来源引用和编辑保护；原 TeX 继续保留。

显式用户保存的申请记录可独立于研究 `record_class` 进入现有读取和交付。程序读取
不可变保存记录并核验 `origin`，不单凭目录元数据授权；目录读取失败仍通过原错误
状态报告，不把故障当作空库。当前源码的完整默认回归和 Ruff 已通过，覆盖与源码
稳定性已核验。完整真实输入结论单列，不替代安装版或真实 ATS 接受。

## 现有读取与匹配入口（J04）

继续使用 checkout 的现有 Portal 和 Flow 操作。没有新增匹配 CLI 或独立运行模式。
`analyze_job()` 仍负责普通两库分析；已有 Flow 的显式失败重试将原分析目录通过
`resume_from` 接回现有入口。

- 结构化经历按事实对应的来源 ID 选择，程序提供完整 JSON 事实与引用。旧长原文
  通过详情 Adapter 分段，模型只选择段落 ID，程序取得文字及原始范围。
- `unknown`/`partial` 先检查剩余未读候选，包含关联资料的实际读取集合。
  没有未读候选时直接结束查找；有候选时才补查。读取故障不记为能力不足。
- 成功 P02 岗位说明、P03 目录计划和读取资料包在绑定一致时复用。P04 失败只续
  评估，不重解 JD 或重读成功资料。旧失败及新尝试 lineage 均保留。
- 没有现代检查点的历史失败，先按精确岗位绑定核验已有 JD 说明，再恢复当前读取
  计划。结构化事实通过 ID 交付，程序附上原始字段；旧原文仍校验精确引用。
  已保存原生响应须通过原输入、schema、范围和结果核验，才能在本地采用。
- 后续补查失败只恢复失败页及未完成步骤，保留已成功页面、评估和读取回执。
  修复实现后仍须核验输入绑定；不能把未知调用当成明确失败后重发。
- 固定岗位要求下，没有可选新候选的页面由程序记录并跳过模型，页覆盖仍完整。
  旧原生响应优先核验和复用；本地采用时检查原始 JSONL 与解析 JSON 一致。
- 已采用固定写作交付的导出继续使用该 P04 资格与固定输入，不重新解释实时资料。
  未知或不满足的资格、未采用交付、未知导出及源/PDF 不一致仍停止。
- JD、检索及 P04 的已保存响应优先在本地核验和采用；明确失败才重试对应阶段。
  资料读取保留成功回执；调用结果未知时返回
  `match_result_needs_recheck`，先核对原调用，不盲目重发。
- 已完成分析按已消费事实及语义配置核验。未选来源或纯诊断元数据变化可复用；
  实际事实、责任、引用、教育、适用信息或 JD 变化不能误用旧判断。

这些行为直接作用于现有生产源码。源码验收状态见
[JSON 实施地图](../.scratch/json-resume-delivery-2026-10-24/map.md)，
接口及状态细节见[两库读取与恢复](career-library-retrieval.md)和
[一次岗位解读](job-brief.md)。J04 的读取/匹配验证不调用真实模型或 ATS。J05 的实际作者合成运行单独举证；
J04 历史验证未迁移私库；后继转换范围见完整真实输入记录。用户 Prism 服务和安装版
未在本阶段操作。现有数据、人工更正和材料历史保留。

## 现有分经历写作与终审入口（J05）

继续使用 `scripts/run_experience_generation.py` 和现有持久任务。结构化事实交付
现在采用 `content-writing/v1`，不新增平行运行模式。

1. `prepare` 固定已交付事实、推断和显式 `.tex` 模板，生成
   `content_plan`（`resume-template-plan/v1`）。模板选择沿用 `bind_latex_base`。
   固定样式、姓名、LinkedIn、网站、邮箱及教育是模板原文，不按岗位注入 JSON。
   原人工保留稿仍须显式绑定。
2. 主 agent 在 `configure` 提交可选 `writing_plan`，选择与排序已交付经历、设置
   写作要求，编写全局 JSON 并记录 `main_writer_id`。
3. 每经历一个真实 subagent 消费 `writer` 的 scoped `assignment`、版本和 schema；
   `fragment` 只交 `content_fragment`，不交 TeX。程序检查 ID、版本和逐条引用。
4. `assemble` 形成 `resume-template-content/v1` 可变内容 JSON 并固定渲染；
   其中只有申请/模板绑定及摘要、技能、经历，没有 `profile`/`education`。
   一个独立终审通过 `content_patch`
   修订允许字段，或只退回 `rewrite_experience_ids`。成功作者不重跑。
5. `adopt` 将补丁后终审绑定的内容、render manifest 和 TeX 存到原草稿版本。
   读取时核验归档内容，不重新读取实时库。采用本身不证明 PDF 已编译。

模板须各含一次 `%% TOMORROWSTAR_SUMMARY %%`、`%% TOMORROWSTAR_SKILLS %%`、
`%% TOMORROWSTAR_EXPERIENCES %%`。章节标题与样式留在模板，程序只填槽位正文，
其余原文精确保留。缺模板或标记不合法时停止，不自动造模板或补写固定个人资料。
固定资料的更正单独更新模板。混合交付中未结构化的经历资料返回
`resume_content_material_required`，原资料保留，不静默省略。

职业定位使用独立可选槽位 `%% TOMORROWSTAR_HEADLINE %%`，须单独一行且位于文档正文。
使用该槽位的模板要求主作者在计划中填写 `headline`（一个 `ContentItem`，含逐项引用）。
职业定位按本次已交付岗位说明生成，参与终审、人工措辞回写及轻量校对，不属于固定个人信息。
人工删除继续受保护；旧模板和旧内容版本不新增空字段或改变哈希。无该槽位的模板不能接收
职业定位字段，避免静默丢失。字体、位置和间距仍由槽位周围的模板样式控制。
默认申请和材料准备均可复用现有 `resume-review.json` 的显式模板绑定；更新配置只影响
未来首次选择模板的任务，不替换已绑定任务、已接受正文或历史 PDF。

紧凑经历排版可复用[合成模板](../assets/templates/resume-compact.tex)。在固定模板的
导言区明确声明 `\newcommand{\TomorrowStarExperienceMeta}[4]` 后，程序仍为每段
经历生成一个 `\subsection`，并把机构、职位、地点、日期作为四个转义后的参数交给
该宏。模板把职位、机构、地点合并为一行，日期靠右；长字段可在左栏换行，空字段
不生成多余分隔符。姓名、联系方式、教育仍是模板中的固定原文。

该声明采用 `resume-template-renderer/v2`；未声明的历史模板保持 v1 原始输出和
编辑范围。更换版式须保存新模板并显式更新内容的模板绑定，保留旧模板、TeX、PDF
与人工版本。布局变更不重新读取经历库、解读 JD 或改写已接受正文。
源码回归、真实编译及视觉验证见[紧凑模板记录](../.scratch/json-resume-delivery-2026-10-24/compact-template-verification.md)。

人工 JSON 措辞、条目位置、经历顺序和记录省略受保护。只有人工 TeX 而无内容
映射的显式保留稿停止内容覆盖并返回 `resume_content_manual_merge_required`；
原稿保留；J06 仅按固定 renderer 接回能唯一定位的内容修改，其他修改仍停止覆盖。旧 `fixed-writing/v1` 与 raw 任务继续
原契约。参数、字段和人工保护边界见[材料 CLI](resume-agent-operations.md)，
接受范围见[J05 验证](../.scratch/json-resume-delivery-2026-10-24/j05-verification.md)。

新 Flow 任务保存程序指定的 `material_contract="content-writing/v1"`。缺少结构化
经历时停止并返回 `resume_content_material_required`，先完成显式内容导入；不新建
旧 TeX 写作交接。无标记的历史任务及已保存旧交接仍可按原契约恢复。

模板按原文字节归档并绑定版本。下一岗位默认选择原固定模板基线，跳过没有槽位的
较新历史成稿，并核验内容 lineage 的模板版本。固定个人资料、教育及排版保持原文。
新任务通过 `prepare_automatic_materials` 或 `bind_latex_base` 首次接入时，沿用
`generated-latex-project/v1`，允许已有根 Git，Git 元数据不进入源归档或构建依赖。

已有人工 TeX 若已保存精确内容映射，可通过
`ApplicationResumeStore.import_latex_for_task(content_mapping=...)` 接回。映射须同时
包含内容 JSON、固定模板、render manifest 和来源定位及哈希；程序核验完整 TeX
能精确重渲染后才保存。此操作保留导入来源，不补造模型生成或终审记录。
随后 `prepare_automatic_materials(..., retained_draft_id=..., retained_draft_sha256=...)`
显式绑定该稿。固定个人信息和教育继续留在模板，人工条目、顺序和来源随原稿保留。
已开始的自动材料任务不能静默替换底稿；后续已采用版本优先于最初导入底稿。

## 人工编辑与已有构建（J06）

继续沿用现有 Flow 的 `begin-prism-edit` → `finish-prism-edit` →
`capture-prism-result`。固定个人信息与教育仍为模板原文。程序按归档基线、内容
范围和精确重渲染接回可定位的文字、链接、删项及排序。人工列表的完整结构
在每次版本采用时保存，连续人工返回也不丢失。整段经历省略随版本保留，资料包
暂时缩窄再恢复时不能将它重新加入。多个改写无法唯一辨识条目时保留为未归并，
不猜 ID 和引用。

`content_reconciliation` 显示 `mapped`、`unchanged` 或 `unmerged`，
`parent_content_ref` 保留可重建的父内容。未归并稿仍可使用实际手工构建；重新
自动生成会停止，保护完整 TeX。文字校对只修改可变条目，已保存响应和条件写入
先核验采用，未知请求保持待核对，不自动重发。详见[Prism 操作](prism-resume-review.md#j06-当前行为)。

已绑定 Worker 原页时，Prism 返回先保存候选源、草稿和实际 PDF，保留旧材料绑定。
一次 Continue 核验原页及材料后采用候选；失败或无变化保留旧版本，未知结果停止。
发送前使用可信本地任务选定的信息库核对适用联系人与资格，不能用 Worker 默认库
替代该目录。固定模板资料仍只从模板读取。

J08 已分别验证源码组合、两位实际经历作者与独立终审，以及临时 Prism 当前工作树
上的原生编译和页面人工编辑。固定输入的录制比较不证明真实模型延迟或提速。
后继完整真实申请的实际分经历作者 JSON 已通过程序校验，固定个人信息及教育仍取自
实际接受模板。单一独立内容终审、固定渲染及逐页 PDF QA 均已通过，见
[完整真实输入记录](../.scratch/json-resume-delivery-2026-10-24/full-real-input-verification.md)。
原真实申请 P04 分析失败保持原记录；后续主流程状态由
[P04 与主流程记录](../.scratch/json-resume-delivery-2026-10-24/p04-mainflow-verification.md)
单独持有。用户服务、安装版和真实 ATS 未在本阶段接受。

## 申请记录 JSON 主存储（J07）

现有 Portal/Flow 的新建与修改直接使用同一 `ApplicationStore`。新记录为
`application-record/v1`，无需另开 tracker。历史 Markdown 可继续读取；首次普通
修改采用 JSON 并保留原件。显式迁移入口要求明确目录、ID 和当前 revision，
不自动扫描或批量转换私库：

```bash
uv run --locked --offline --no-sync python -B scripts/run_application_records.py --root /path/to/selected/applications list
uv run --locked --offline --no-sync python -B scripts/run_application_records.py --root /path/to/selected/applications read --id APPLICATION_ID
uv run --locked --offline --no-sync python -B scripts/run_application_records.py --root /path/to/selected/applications preview-import --id APPLICATION_ID --expected-revision CURRENT_REVISION
uv run --locked --offline --no-sync python -B scripts/run_application_records.py --root /path/to/selected/applications import --id APPLICATION_ID --expected-revision CURRENT_REVISION
```

`preview-import` 不写文件，显示字段、文件对应及未映射旧属性。导入保留原申请 ID、
完整 JD、原 Markdown 字节和历史；未映射属性留在原件，不伪称已结构化。
采用后的 `source_name` 指向 JSON，`legacy_source_name` 定位旧源，
`legacy_source_changed` 提示旧源变化。JSON 为当前权威记录，不生成 Markdown
镜像；双侧修改时返回 `source-import-conflict`，保留两边供实际合并。
发布后丢失响应可用同一原 revision 核对采用，后续人工变更仍返回冲突。
该 CLI 输出属于所选私人目录的数据，不应复制到公开验证报告。

## 运行 J01/J02 历史最小验证

此命令保留原 `resume-plan/v1` / `resume-content/v1` 完整 JSON 合成切片兼容，
包括当时的 `profile`/`education` 字段。它不定义当前 J05 模板绑定契约；当前正式
写作要求固定 TeX 模板，并将固定资料排除在可变内容 JSON 之外。

从 checkout 根目录运行，目标必须是尚不存在的新目录：

```bash
uv run --locked --offline --no-sync python -B scripts/create_json_resume_demo.py /private/tmp/json-resume-demo
```

命令使用公开合成样例，输出以下文件：

| 文件 | 含义 |
| --- | --- |
| `input.json` | 固定经历事实、程序分配计划及合成作者 JSON 响应 |
| `resume.json` | 已校验的完整简历内容及内容版本 |
| `main.tex` | 固定模板生成的完整英文 TeX |
| `render.json` | 内容/模板/renderer 版本、输入及 TeX 哈希、内容 ID→字符范围映射 |

`render.json` 是一次渲染记录，`operation=render_only` 不代表已经编译。
完整引用追溯须保留 `input.json` 和对应 manifest；不能只保留 `resume.json` 中的
引用 ID 就声称已有完整来源快照。内容范围使用 Python 字符位置，不是 UTF-8 字节位置。

编译使用已有 LaTeX 工具，例如现有 Tectonic；不新增 App 内编译器：

```bash
mkdir /private/tmp/json-resume-demo/build
tectonic -X compile --untrusted --keep-logs --outdir /private/tmp/json-resume-demo/build /private/tmp/json-resume-demo/main.tex
```

也可使用已有 LaTeX compile 技能。编译/PDF 检查是此合成切片的验证，不是用户
Prism 服务、真实材料、安装或 ATS 的接受。生成命令本身不编译、不导出 PDF。

## 稳定 Interface

| Interface | 作用 |
| --- | --- |
| `validate_fragment(payload, assignment)` | 核验身份、分配版本、逐条事实/推断引用及结果状态，返回 JSON 字典 |
| `assemble_content(plan, fragments, retained=None)` | 按程序计划排序并固定经历元数据，保留明确传入的受保护人工条目；历史完整契约兼容原身份/教育字段 |
| `validate_content(payload)` | 核验完整内容结构及规范化内容版本 |
| `apply_content_patch(base, patch, *, allowed_targets)` | 仅在指定基线、旧值和程序授权字段一致时应用局部补丁 |
| `render_resume(content, template_revision=..., *, template=...)` | 当前契约提供显式固定模板，纯函数填槽位并生成 TeX、版本及范围；历史完整契约兼容无模板调用 |

`allowed_targets` 由程序独立提供，不能取自模型自报的修改权限。补丁只改允许的
`text`/`links`，不改身份、教育、经历元数据、引用或人工保护内容。
当前 J05 姓名、联系方式及教育取自显式模板的字面内容，不进入可变 JSON；
经历标题/角色等由事实分配输入固定，不交给经历作者自由重写。
无机构、日期或角色的经历仍可使用，不补造缺失事实。

契约模型使用已安装的 Pydantic v2；`v1` 指 JSON 契约版本。
机器 Schema 从模型导出，命令与字段说明见
[合成契约样例](../tests/fixtures/json_resume/README.md)。Schema 约束结构；
引用归属和补丁权限还须调用拥有实际输入的验证函数。

## 保留与限制

生成命令对已有目录报错，不覆盖、清理或自动迁移任何文件。该验证入口的契约和渲染
函数是纯数据操作；此命令本身不驱动正式写作流程。正式流程已在上方 J05 入口
调用同一契约及 renderer。此最小切片的 `retained` 仅接受程序显式传入的本申请
受保护人工经历条目，保留文字和换行；不要求为人工新增内容伪造引用。

此验证命令不读取或转换现有人工 TeX。J05 的正式入口已保护映射后的人工条目、
全局内容、顺序和省略，并接入原版本存储；J06 已在上述入口接回可表达修改。
这些保护不等于旧人工稿已迁移或任意 TeX 已可逆。

`semantic-review-cases.json` 中的“计划→完成”“参与→领导”是结构合法但语义越界
的例子。它们需要单一内容终审判断，程序不冒充语义审核。此入口使用固定合成
响应，不声称运行过真实简历作者或终审模型。

文本特殊字符与命令作为字面内容转义；链接仅允许合适的 HTTP(S)/mailto 目标。
本轮不引入中文简历字体或多语言排版目标。任意字体字形、不可断长词及实际私人
模板兼容不由这次合成验证保证。

受影响验证通过 checkout launcher 运行：

```bash
uv run --locked --offline --no-sync python -B scripts/run_pytest.py tests/test_json_resume_content.py tests/test_json_resume_render.py tests/test_json_resume_demo.py -q
```
