# 分经历写作 CLI 与固定交付

J05 直接重构现有写作与终审入口。结构化事实交付采用
`generation_contract="content-writing/v1"`；已保存的 `fixed-writing/v1` 和 raw
任务继续原契约，不自动转换。[J05 验证](../.scratch/json-resume-delivery-2026-10-24/j05-verification.md)
分别记录源码、实际 subagents 合成验证与未执行项。没有迁移私人数据或更新安装版。

## 内容 JSON 默认入口（J05）

使用同一 `scripts/run_experience_generation.py`，沿用 `--applications`、
`--career-workspace`、`--resume-root` 和 UTF-8 JSON `--request`。
当前 Codex 会话按经历分派真实 subagents；Python 保存固定输入、检验结果和进度，
不启动另一套 agent 平台。写作者和终审都消费 JSON，不写 TeX 字符串。

```text
uv run --locked --offline --no-sync python -B scripts/run_experience_generation.py \
  --applications /absolute/applications \
  --career-workspace /absolute/career \
  --resume-root /absolute/flow/resumes \
  ACTION --generation-id ID --request /absolute/request.json
```

`prepare` 不传 generation ID。若当前任务配置职业库 manifest，所有动作继续传
相同 `--career-library-manifest`。参数文件、完整响应与模型原始证据留在选定私有
任务目录，不复制到公开文档。

| 动作 | 内容契约参数与结果 |
| --- | --- |
| `prepare` | `identifier`, `revision`, `source_snapshot`, `analysis`, `task_inputs`, `latex_base`；可带 `information_library`、`retained_draft`。必须显式绑定固定 LaTeX 模板；模板选择复用 `bind_latex_base` |
| `context` | 返回固定 `job_brief`、要求、`content_plan`、已有内容及省略记录；主 agent 据此选材、排序和编写全局 JSON |
| `configure` | 可传 `writing_plan`（`resume-template-plan/v1`）及 `main_writer_id`；省略计划则采用交付计划。主 agent 编写 AI 摘要/技能时必须记录真实 `main_writer_id` |
| `writer` | 传 `experience_id`；返回该经历的 `assignment`、`input_revision`、`output_schema`、保留条目和局部返工反馈 |
| `fragment` | `experience_id`, `input_revision`, `writer_id`, `content_fragment`；内容使用 `experience-writing/v1`，逐条 `fact_refs`/`inference_refs`，不能混入旧 TeX 参数 |
| `assemble` | 检查齐备、ID、分配版本、引用作用域及人工保护；组装完整内容 JSON，固定模板生成每经历一个 subsection 和完整 TeX |
| `review-context` | 完整 `resume_content`、写作计划、固定岗位说明及推断；仅审 AI 新表达 |
| `review` | `candidate_sha256`, `reviewer_id`, `passed`, `issues`；可带 `content_patch` 或 `rewrite_experience_ids`。不用旧 `patches[].latex` |
| `adopt` | 将补丁后终审绑定的内容版本采用到现有草稿存储；重复采用核验并返回同一版本 |

当前计划为 `resume-template-plan/v1`，组装后内容为 `resume-template-content/v1`。
它们保存 `application_id`、`template_revision` 及可变摘要、技能和经历；没有
`profile`/`education` 字段。主 agent 可选择和排序已交付经历、设置各经历
`writing_requirements`，编写 `summary`/`skills`；不能改变模板版本、候选 ID、事实
或已交付推断。程序重算分配版本。不同经历使用不同实际写作者；全局作者与经历作者分离。

固定样式、姓名、LinkedIn、网站、邮箱和教育直接写在模板中，章节标题也由模板
决定。每轮生成不从信息库覆盖这些内容；更正固定内容时单独更新模板。
冻结 `.tex` 归档中必须各有一次以下标记，renderer 只替换标记对应的槽位正文，
其余原文精确保留：

```tex
%% TOMORROWSTAR_SUMMARY %%
%% TOMORROWSTAR_SKILLS %%
%% TOMORROWSTAR_EXPERIENCES %%
```

缺少模板返回 `resume_template_required`，标记或模板绑定无效返回
`resume_template_invalid`；不自动生成替代模板。

`content_fragment.status` 为 `complete` 或 `needs_material`。缺少必要资料时用
`requests` 定位缺项，交回检索；不能生成空成功片段。程序拒绝错经历、旧分配版本、
跨经历引用和非法字段。重新配置只作废输入变化的作者结果；成功结果继续保留。
不重读整库、不重新解读 JD、不重算匹配或推断，不增加可信度批准。
混合交付中尚未结构化的经历原文不能静默省略；返回
`resume_content_material_required` 并保留原资料，等待补充语义事实。

终审必须独立于全局作者及所有经历作者，并由同一终审角色接续。
`content_patch` 使用 `resume-content-patch/v1`，给出基线内容版本、目标条目、
字段与预期旧值；程序独立授权 AI 条目的 `text`/`links`。补丁不能改变身份、
教育、引用或受保护人工内容。通过结论绑定补丁后的 `content_revision` 和 TeX。
实质重写只列对应 `rewrite_experience_ids`，其他作者结果保留；不能同时宣告通过。

采用在原版本目录保存 `content.json`、`render-manifest.json`、`draft.json` 和
TeX/source archives。读取时重新核验内容、固定渲染和终审绑定，不访问实时库。
所有简历为英语，固定模板使用 LaTeX 默认字体。该采用不代表已编译 PDF。
Flow 继续沿用既有 `resume-experience-generation` 接回入口。J06 已接回人工编辑、
已有构建和 finishing 恢复；完整主流程组合与私人材料接受继续归 J08。

已有 JSON 人工条目的措辞、位置及经历顺序受保护；已记录省略不能由新作者恢复。
显式保留稿如果只有人工 TeX、没有内容映射，返回
`resume_content_manual_merge_required`，原稿保留并停止内容覆盖。J05 不解析或迁移
这类任意 TeX。J06 在现有 Prism 返回入口按固定渲染范围接回可表达的人工文字、
链接、删除和排序。无法映射的稿件仍保留原文并停止覆盖。人工改动的列表结构通过
`retained_protected_scopes` 在每个采用版本保存并传入下一轮写作和终审，包含
已清空的摘要/技能列表。`retained_omitted_experience_ids` 保存整段经历省略，
资料包暂未包含该经历或连续人工返回也不能清除记录；不自动恢复删除项。详见[Prism 接续](prism-resume-review.md#j06-当前行为)。
本入口不启动 ATS、不上传附件、不执行最终 Submit。

<details>
<summary>已保存 fixed-writing/v1 任务的兼容接口</summary>

以下仅适用于原契约，不是新内容作者的输出格式。

## P05 固定交付接口

当前 Codex 会话编排实际写作者；程序不启动另一套 agent 平台。
正常分析同时交付 `job_brief`、`material_packet`、`inference_result` 时，建立
`generation_contract="fixed-writing/v1"`。主 agent 消费固定上游，形成计划；
每段经历一位写作者，主 agent 负责全局块。终审独立于这些作者。

从 checkout 使用 `scripts/run_experience_generation.py`，沿用 `--applications`、
`--career-workspace`、`--resume-root` 和 JSON `--request`。私有输入与完整结果留在
任务目录，不复制到公开文档。固定 `prepare` 必须传交付的 `source_snapshot`；
未传快照的旧 raw 入口仍沿用旧读取方式。

| 动作 | 新契约参数与结果 |
| --- | --- |
| `prepare` | `identifier`, `revision`, `source_snapshot`, `analysis`, `task_inputs`, `latex_base`；可带已保存 `retained_draft` 和本轮 `information_library`。下游不重读实时库或重判匹配 |
| `configure` | `groups`, `experiences`, `organization_plan`；可带 `writing_plan`、有限 `affected_group_indexes` 及原因。分组按底稿位置升序登记，顺序调整只用 `block_order` |
| `writer` | `experience_id`；得到本经历的固定事实/推断、块、重点、篇幅、版本及 `allowed_refs` |
| `fragment` | `experience_id`, `input_revision`, `writer_id`, `status`, `used_refs`, `issues`，及 `groups`；单块也可用 `block_id` + `latex_fragment` |
| `assemble` | 收齐成功片段，检查归属、位置、引用和 TeX 结构，生成单文件候选及块/片段版本映射 |
| `review-context` | 完整候选、固定上游、写作计划和人工保护；只检查本轮新表达 |
| `review` | `candidate_sha256`, `reviewer_id`, `passed`, `issues`；可给局部 `patches` 或 `rewrite_experience_ids` |
| `adopt` | 采用唯一终审绑定的候选。已采用任务不可再修改；重复采用只返回同一已核版本 |

`groups` 沿用 `title/start_line/end_line/source_ids/latex/disposition/reason`。
`experiences` 声明 `experience_id/source_ids/group_indexes/focus/business_relevance/evidence_role`，
可加 `length`。匹配预选只是建议，实际选材可以使用已交付资料包中的其他来源；
不能借此读取未交付资料或改变背景分。

`writing_plan` 使用稳定 `block_id`、唯一 `owner`、`group_index`、`order`、`focus`、
`length` 与允许引用。默认计划由现有分组与经历映射形成；显式 `block_order` 必须
恰好列出全部块。固定身份、学历及人工保留块不能移动或交给经历写作者改写。
保留人工底稿时，只有明确指定的受影响块可改；省略历史单独保留，不恢复旧文字。

片段状态为 `complete`、`missing_details` 或 `failed`。使用引用可指本经历来源、
事实 ID 或闭合的推断要求 ID；不要求 `source_notes`、实际读取凭据或可信度批准。
缺细节时明确报告，组装停止，其他成功片段继续保留。`read` 仍可读取所分配来源，
但不是片段接受门槛。

局部终审补丁为 `{block_id, expected_latex, latex}`：原块必须逐字对应当前候选；
只允许本轮可写块。程序应用补丁，再将同次终审绑定补丁后的候选。实质返工只退回
指定经历，成功片段保留，并由同一终审角色接续。不能同时要求返工又宣告通过。
终审不重解 JD、不重算分、不重做推断或自述审核；组装与采用不重复做数字/关键词
语义批准。TeX 外部读取、执行、宏和结构限制仍保留。

任务一旦交付，后续 JD、库、模型、登录配置或外部底稿变化不自动废弃该任务。
明确采用新输入时建立后继交付。组装保留模板前后缀，不暗改纸型或排版；采用直接
保存已审候选，不再次生成。普通 Flow 接续仍使用原任务和交接 ID。


</details>

<details>
<summary>历史 raw 分析兼容入口与原参数说明</summary>

本入口由当前 Codex 会话调用。Python 不启动模型或 subagents。App 的完整简历生成入口准备持久交接，显示经历写作、组装及终审进度；主 Codex 使用实际 subagent 工具分派写作者。

从 checkout 运行 `scripts/run_experience_generation.py`。所有命令使用相同的 `--applications`、`--career-workspace`、`--resume-root`，对应当前任务的投递目录、独立职业库和 Flow 下的 `resumes` 目录。用 `uv run --locked python -B` 启动；有沙箱缓存限制时设置可写的 `UV_CACHE_DIR`。

```text
python -B scripts/run_experience_generation.py \
  --applications /absolute/applications \
  --career-workspace /absolute/career \
  --resume-root /absolute/flow/resumes \
  ACTION --generation-id ID --request /absolute/request.json
```

`--request` 是程序参数的 UTF-8 JSON 对象。无需参数的动作可以省略它。stdout 输出 JSON；错误返回非零退出码。文件和输出含任务资料，只保存在明确的私有工作目录，不复制进公开文档。

若当前服务配置了显式职业库 manifest，所有动作同时传 `--career-library-manifest /absolute/manifest.json`。该参数与当前任务保持一致，使分析、生成和新鲜度校验读取同一来源集合；不能只在分析时加入库来源，再用裸工作区校验生成结果。未配置 manifest 的旧入口不变。

| 动作 | JSON 参数 | 作用 |
| --- | --- | --- |
| `prepare` | `identifier`, `revision`, `analysis`, `task_inputs`, `latex_base`，可选 `information_library`, `retained_draft` | 无 App 时准备交接；来源快照由程序本地读取。此动作不传 generation ID |
| `status` | 无 | 查看映射、完成的经历、候选及采用状态 |
| `context` | 无 | 主 Codex 读取 JD、实际底稿、来源定位和选中集合，不返回整库正文 |
| `configure` | `groups`, `experiences`, `organization_plan`；更新时可传 `affected_group_indexes`, `context_impact_reason` | 先说明业务目标对应的摘要重点和排序，再明确底稿位置和经历归属 |
| `writer` | `experience_id` | 只取该经历的 JD、片段位置、输入版本和写作要求 |
| `read` | `experience_id`, `source_id`，可选 `offset`, `limit`, `field` | 分次读取所属来源；记录实际读取范围，单次最多 32000 字符；`field="boundaries"` 读取独立责任/范围限制，默认 `field="text"` |
| `fragment` | `experience_id`, `input_revision`, `groups`, `source_notes`, `issues`, `writer_id` | 保存一位写作者的片段；未决问题会阻止组装 |
| `assemble` | 无 | 核验全部经历后由程序组装独立单文件候选 |
| `review-context` | 无 | 给一个终审 agent 实际候选、JD、来源说明和保留稿上下文 |
| `review` | `candidate_sha256`, `reviewer_id`, `passed`, `issues`, `business_alignment` | 保存独立终审及整体业务定位判断；修改后须重新组装和终审 |
| `adopt` | 无 | 通过当前终审后沿用现有版本存储采用草稿 |

`groups` 使用现有完整 LaTeX 分组结构：`title`, `start_line`, `end_line`, `source_ids`, `latex`, `disposition`, `reason`。行号指文档正文内部，必须完整覆盖实际底稿。未分派块原样保留。学历和联系方式沿用现有保护，不交给经历写作者重写。

`experiences` 的每项包含 `experience_id`, `source_ids`, `group_indexes`，可加 `focus`, `target`。一经历可以含多个来源、多个正文块。先沿用已有 ID 和来源关联；缺关联时，主 Codex 读取实际材料后提供明确映射。配置不能隐含加入未选来源。写作者拿到的 `input_revision` 必须随片段原样交回。

**历史 raw 接口限制：** 旧岗位分析包含 `role_understanding`（`business_objective`, `work_outputs`, `methods_role`）及按选材顺序排列的 `selection_rationale`（`source_id`, `business_relevance`, `evidence_role`）。`context` 返回这些内容及岗位要求，不能只按来源标题选材。旧接口遇到遗漏要求返回岗位分析并更新预选。新设计由检索补资料、写作计划选材，不以分析预选限制生成，也不因此重算完整背景匹配分。

对这些新分析，`configure` 的 `organization_plan` 须含非空 `summary_focus`、`ordering_rationale`，每项 `experiences` 须含非空 `focus`、`business_relevance`，以及 `evidence_role="direct_domain"` 或 `"transferable"`。`writer`、`review-context` 继续携带目标和计划；`review` 须以非空 `business_alignment` 说明整份简历的业务关联判断。旧交接仍可读取，原历史不补写这些判断。这是旧接口的业务/版本绑定，不能成为重复业务审核。新设计仅在明确采用新写作任务时更新相关片段；外部 JD、库或配置变化不自动废弃既有交付。

`organization_plan.positioning_group_indexes` 可列出主 agent 负责的可编辑全局定位块，索引对应 `groups`。主 agent 直接提供这些块的实际 LaTeX 和已选经历来源，程序统一组装；不要把摘要强行归入某一经历，也不要让它作为未分派块逐字继承旧定位。全局块不能同时分派给经历写作者。固定身份、学历、已接受页眉、只读来源及未受影响人工文字继续保留原保护。

每条 `source_notes` 包含 `source_id`, `reason`, `read`。`read` 原样引用一次 `read` 结果的 `source_id`, `offset`, `end`, `source_revision`（读取限制字段时还包含 `field`）。这属于旧接口的读取范围记录，不是事实可信度结论。新终审只对照已交付事实与推断检查新表达，不重新审核经历、自述或匹配，也不要求写作者提交新的可信度证明。大来源可以分次读，不得把读取范围宣称为全量覆盖。

主 Codex 一经历分派一写作者，写作者仅交回自己的 JSON/正文片段。程序是最终 `main.tex` 的唯一写入者。失败时保留其他已完成片段；重新配置只作废输入变化的片段。旧接口的输入变化重分析门槛在 P05 收窄；新设计明确重做哪个步骤才采用新输入，并复用其他已完成结果，不自动重解 JD 或重算匹配。

采用后，主 Codex 调用当前本地服务的 `POST /api/flow/resume-experience-generation`，传 `task_id`, `task_revision`, `generation_id`，沿用当前服务认证和写入保护。它接回原任务的生成阶段及自动编译导出，无需用户再批准普通材料。不能直接改 `flow.json` 或重建任务。服务只接受已采用且对应当前任务的生成结果；未知导出仍沿用现有核对机制，不盲重编译。

本入口不启动浏览器、不上传附件、不执行最终 Submit。真实个人简历质量和实际 ATS 使用由对应产品验收记录承接。

已在安装版材料 CLI 完成生成和导出、但原 Flow 尚未采用时，使用同一服务的
`POST /api/flow/attach-experience-materials`，传 `task_id`, `task_revision`,
`generation_id`, `export_id`。该入口只读取并核验已通过终审的采用稿和已完成 PDF，
检查当前岗位、分析、来源、原人工稿谱系、输入及导出绑定后接回原任务。
它不启动模型或编译，也不创建岗位任务。旧材料与接回前状态保留在历史中。
存在真实在途或未知操作、新人工修改或输入不匹配时停止；先核对，不能借此跳过。
已妥善取消的重复准备任务保留历史，但不再阻挡原任务或成为默认当前任务。

**旧接口的全局块约束：** 全局定位还须记录 `organization_plan.positioning_writer_id`，终审者须独立于此写作者及经历写作者。第一节之前的页眉整体保留，包含宏定义身份，不由全局定位改写。全局引用的每个来源必须具有经历写作者已提交的非空正文读取凭据及支持说明，单独读取边界或空范围不算正文依据；终审结合这些说明检查全局表述。这些读取凭据要求是保留的旧参数，不是新产品的逐片段内容批准；新设计仅保留引用关联、块归属与新生成表达的单一终审。

## HTML 简历退役

`POST /api/resumes/generate` 已移除。旧 HTML 简历生成接口和无 LaTeX 编译来源的导出请求返回 `resume_html_retired`；缺少底稿的生成请求返回 `resume_latex_required`。这些请求不调用模型、HTML 渲染器或旧导出器。旧文件留作历史，界面不再提供继续审阅、重新生成或导出 HTML 简历的按钮。新材料统一从完整 LaTeX 入口准备。

新任务的自动底稿选择在识别出可压缩教育块时创建任务独立副本；显式绑定、已有任务及人工接受源不改写。标准教育块保留全部事实并使用局部 10pt/12pt，不能识别的布局原样保留。真实生成质量、已安装 App 和实际申请仍分别核验。

</details>
