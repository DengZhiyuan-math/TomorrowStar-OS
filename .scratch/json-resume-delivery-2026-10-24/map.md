# JSON 简历内容实施地图

Label: wayfinder:map
Status: open
Assignee: root
Created: 2026-10-24
Updated: 2026-10-25
Tracker: local-markdown

## 范围与状态

设计依据：[JSON 内容与固定渲染](../../docs/json-resume-design.md)。
优先顺序由[统一开发计划](../../docs/development-plan.md#json-plan-2026-10-24)持有；
本图持有 J01–J08 的实施分解。**J01/J02 英文合成切片、J03 经历库、J04
读取/匹配、J05 内容写作/终审/采用、J06 人工接回及 J07 申请 JSON 主存储已接入源码。J08 已接通默认主流程，并完成分层合成验证。** 见[J01/J02 验证](j01-j02-verification.md)、
[J03 验证](j03-verification.md)、[J04 验证](j04-verification.md)、
[J05 验证](j05-verification.md)、[J06 验证](j06-verification.md)、
[J07 验证](j07-verification.md)、[J08 验证](j08-verification.md)与
[操作入口](../../docs/json-resume-operations.md)。
不重开 P01–P08 原票，不改写其负责人、交付或接受记录。

本轮目标覆盖经历事实、写作内容和申请记录的内部 JSON 流动。保留原始资料与
历史编辑格式。先完成单经历最小纵向切片，再迁移和接入，不以批量转库开场。
J01/J02 最小切片使用固定合成作者响应；J05 的实际 subagents 合成接受与源码回归
分别记录在本包验证中，不以开发协作 agents 冒充简历作者。J01–J08 验证轮不迁移
私库；后继[选中真实输入阶段](real-input-verification.md)保留原范围。
[完整真实输入阶段](full-real-input-verification.md)现已转换初始全部当前申请经历，
并保留原 ID、原始文件、材料与历史。未安装主 App 或启动真实 ATS。所有简历为英语；
新合成模板使用 LaTeX 默认字体，真实模板保留原有人工样式，不新增字体依赖。
后续[P04 与主流程验证](p04-mainflow-verification.md)已在同 ID 源码任务快照中完成
P04、实际作者 JSON、终审及原生 PDF 导出；原安装版失败和历史保留。
实现恢复、最终冻结回归与真实材料接受分别记录，不相互替代。

## 顺序、依赖与文件所有权

| 包 | 工作 / 对应原阶段 | 依赖 | 主要拥有文件（实施时确认） |
| --- | --- | --- | --- |
| J01 | 内容契约与合成样例 / P01、P05 | 无 | 新 `application_resume_content.py`；经历 schema 及合成 fixtures |
| J02 | 一经历 JSON→subsection→完整 TeX 纵向切片 / P05 | J01 | 新 `application_resume_render.py`；合成模板与 renderer 测试 |
| J03 | 经历事实结构化与纯输入、旧数据导入 / P01 | J02 | `career_experiences.py`、`application_career_library.py`、`application_source_reuse.py`、信息库映射 |
| J04 | JSON 检索/匹配交付与成功步骤恢复 / P02–P04 | J03 | `application_job_brief.py`、`application_retrieval.py`、`application_material_packet.py`、`application_matching_pipeline.py`、`application_match.py`、`application_flow.py`、`career_portal.py` |
| J05 | 真实分经历写作、JSON 终审、内容版本采用 / P05 | J04 | `application_experience_latex.py`、`application_experience_content.py`、`application_writing.py`、`application_resume_versions.py`、材料 CLI；复用 J01/J02 |
| J06 | 内容版本→构建、Prism/Git diff、人工接续 / P06 | J05；Git 入口只读调查可在 J02 后进行 | `application_resume_versions.py`、`application_prism.py`、`application_proofread.py`、`application_pdf_reuse.py` |
| J07 | 申请记录 JSON 主存储与历史 Markdown Adapter | J01；组合前完成 | `career_portal_data.py` 及其直接调用者；独立迁移入口 |
| J08 | 主流程组合、分层验证及交付准备 / P07–P08 | J05、J06、J07 | Flow/Pipeline/材料绑定的必要改动、组合 tests、验证报告 |

关键链为 **J01 → J02 → J03 → J04 → J05 → J06 → J08**。
J07 可与 J03–J06 并行，但 `career_portal_data.py` 与各调用者的共享改动须由同一
负责人协调。不开跨岗位并发；单岗写作继续一经历一实际 subagent。
先复用既有 Interface；不把这些工作包直接变成新平台或一批重复包装 Module。

## J01：契约与样例

交付：经历事实、分配输入、单经历输出、完整简历内容及字段补丁的最小 v1 契约。
复用 Pydantic 严格字段和现有 ID/版本/引用；不新增依赖。先定义
`validate_fragment`、`assemble_content`、`apply_content_patch` 的纯数据 Interface。

- [x] 明确 `experience_id`→canonical `candidate_id` 映射，逐条事实 ID、来源/推断
  引用、责任、状态与作用域；可选事实缺失不自动阻止整段经历使用。
- [x] `complete` 和 `needs_material` 互斥，缺项可定位；字段不允许携带 `latex`、
  `latex_fragment`、`raw_tex` 或用 Markdown/HTML 表示结构。
- [x] 模型拥有正文，程序拥有固定身份/教育、经历元数据、模板及排序落实；人工
  新增内容按申请作用域保存，不要求补造事实引用。
- [x] 合成正反例覆盖错经历、越权引用、多余字段、旧分配版本、重复 ID、空结果、
  planned→completed/参与→领导等单一终审语义例。

完成标准：一份明确契约及可验证合成样例。此处不修改私人数据，不声称真实作者已运行。
源码及合成验证已完成；可信人工保留当前只支持显式传入的经历条目，不代表既有
人工稿、删项或顺序已经迁移。补丁授权为独立程序参数 `allowed_targets`。

## J02：最小纵向切片

交付：一个合成经历，经合法作者 JSON→程序校验→固定 subsection→现有风格完整
TeX→隔离编译/PDF 检查。作者响应可先固定为合成数据；真实 subagent 另在 J05 验证。

- [x] 历史 J01/J02 完整 JSON 合成切片的 `render_resume` 隐藏固定信息和列表规则，
  内部每经历恰好一个 subsection。该旧切片保留兼容；当前 J05 要求显式 TeX 模板，
  不采用切片中把固定资料放入 JSON 的设计。
- [x] 英文特殊字符、链接、换行、空可选字段、长条目均有行为验证；命令输入
  只能输出为字面内容。公开合成模板保留固定身份/教育，不另造通用排版系统；
  实际私人模板接入尚未验证，不引入中文简历排版目标。
- [x] 输出稳定内容 ID→渲染范围映射，便于人工 diff 接回；不以行号保存事实身份。
- [x] 同内容/模板/renderer 生成相同 TeX；渲染失败保留诊断。编译及 PDF QA
  只证明此合成切片，不等于用户 Prism 服务或真实材料接受。

完成标准：先证明这条最短链可工作，再进入 J03。固定模板无法满足的实际内容在
此记录，优先收窄 v1，而非开放任意 raw TeX。

## J03：经历事实与导入

交付：扩展既有 `ExperienceStore`，新当前版本为语义 JSON；旧原文与版本保留。
`CareerLibrary` 返回可直接消费的字段，目录由完整事实及补充材料派生。

- [x] 导入先生成旧新映射与未表达项清单，再发布新版本；固定 ID、来源、独有
  事实、否定、责任、状态、更正和历史不丢失。不可简单 strip 或整段原文包装。
- [x] 复用信息库 JSON；固定教育不因 JD 选择而改写/遗漏，不把在读推成已授予。
- [x] 旧 retained TeX/`accepted_latex` 留作历史措辞与 provenance，不再进入新事实集；
  `snapshot_for_analysis` 不继承污染项，原生成产物也不能循环入库。
- [x] 修复“只有身份元数据就当作完整发现信息”的 P2；索引不足回退正文，失败
  明确显示，保存与索引失败不能隐藏经历。
- [x] 同一存储/API/CLI 的合成迁移验证覆盖预览不写库、条件发布、失败不改库及
  历史保全。来源同步保留结构化更正；新资料或上下文变化保持待导入。
  同一导入入口也可纳入结构化记录的新资料，保留原事实与引用；映射完成不抹掉
  未读来源，同内容重放不能冒充事实更正，普通保存不能提交自造覆盖记录。
- [x] 初始全部当前申请经历已按[完整真实输入验证](full-real-input-verification.md)条件发布；
  原 ID、原始文件、材料及历史保留，人工接受措辞已有引用与保护。额外保留研究
  身份另存为仅供申请的记录，不重开研究审核。显式用户保存记录独立于研究分类
  进入现有读取与交付，核验不可变来源；目录读取故障仍明确报告。
  不重新采访已保存事实，不将原合成验证改称私人迁移接受。

复用回归：`test_career_experiences.py`、`test_application_career_library.py`、
`test_application_source_reuse.py`、`test_retained_education_boundaries.py`。
完成标准：所有新事实输入都来自明确字段；原件保全与迁移覆盖可核查。

J03 修改的是现有保存、同步、默认事实投影和分析入口，不增加平行运行模式。
新增 `career_experience_import.py` 只负责纯覆盖校验；发布复用既有锁、原子写与历史。
逐原文范围与逐事实/来源映射检查不能证明语义等价，不自动提取或剥离排版来造事实。
旧 TeX 仍供兼容生成器在生成阶段读取。匹配输入保留原责任/状态限制，可信库策略不
允许模型将资料自动升级为个人已完成的责任声明；不增加研究能力审核关卡。

## J04：读取、匹配与恢复

交付：结构化经历/信息通过既有 P03/P04 输出固定 JSON 资料包及推断，P02 不重做。

- [x] 结构化事实按 ID 选择，程序取得完整内容、引用和责任；旧长原文保留按需分段
  Adapter。结构化事实不由模型复制全文或计算偏移，不把对象 `str()` 传下游。
- [x] 保留完整轻目录与按需正文策略，相关性/读取故障/无记录分开；无新增 top-K、
  向量库或第二匹配审核。
- [x] 修复“unknown/partial 但无未读候选仍空补查”的 P2；按成功读取而非仅选择判断
  耗尽，直接交付实际资料状态；仍有未读候选时继续真实补查。
- [x] 修复跨阶段恢复 P2：保留已成功 `job_brief`、读取回执、资料包，P04 失败只续 P04；
  同输入不重新解读 JD。保留每次失败；可核验结果本地采用，结果不明不盲重放。
- [x] 新内部交接保存契约/输入版本；完成分析核验已选事实、适用信息和语义配置后，
  可跨无关资料或 App 诊断元数据变化复用。原尝试、失败与人工材料保留。

复用回归：`test_job_brief_pipeline.py`、`test_p03_career_reads.py`、
`test_p03_retrieval_pipeline.py`、`test_p04_match_contract.py`、相关 continuation 测试。
完成标准：无排版原文混入新事实输入；局部重试调用计数与固定上游结果可验证。

J04 已直接修改现有默认流程。Flow 的新分析尝试关联前次阶段检查点，复用已完成
岗位解读、检索计划、读取回执与资料包；新尝试保存自己的结果，原失败目录不改写。
P04 多轮结果保留原出处。完整性或输入绑定不符不作为成功结果采用，未核验的
中断请求保持待核对。完成分析的语义复用继续保留旧来源 ID 和引用，不将无关
全库变化或诊断元数据变化变成新模型任务。针对性合成回归已验证这些分支，
冻结源码的完整默认离线回归、静态检查及前后指纹核验均通过，
见[J04 验证](j04-verification.md)；未验证安装版或私人材料。

## J05：作者、终审与采用

交付：直接重构既有任务编排为 `content-writing/v1`；一经历一真实 subagent，
主 agent 只写全局 JSON。源码、真实独立作者合成候选、独立终审、编译检查与
冻结源码的完整默认离线回归已通过，见[J05 验证](j05-verification.md)。
回归前后实现与测试指纹一致；私人材料及安装版不在本轮接受范围。

- [x] 复用同一 CLI 和 scoped `writer_context`；交付 `assignment`、`input_revision`
  与机器 schema，提交 `content_fragment` 接 J01；不扫描全库、不改 JD/分数、不写 TeX。
- [x] 缺项通过 `needs_material`/`requests` 定位；局部返工只退回对应作者，成功结果
  保留。程序核验逐项引用、候选经历身份、分配版本和写作者角色。
- [x] 独立单一终审只审 AI 新表达，使用 `content_patch` 字段补丁；结论绑定补丁后
  `content_revision` 和固定渲染结果。实质重写使用 `rewrite_experience_ids`，
  同一终审角色接续，不在编译/PDF 阶段再加语义审查。
- [x] 旧 TeX 契约继续可读、可续；新内容契约按已有交付中的结构化事实选择，
  旧片段不能命中新路径。当前 `resume-template-plan/v1` 与
  `resume-template-content/v1` 只有申请/模板绑定及可变正文，无 `profile`/`education`。
- [x] 显式绑定固定 TeX 模板及归档，模板选择复用 `bind_latex_base`。样式、章节标题、
  姓名、LinkedIn、网站、邮箱和教育均为模板字面内容，不逐岗从信息库注入；
  renderer 只填三个明确槽位的正文，其他原文精确保留。固定更正单独更新模板。
- [x] 混合旧来源缺语义事实时返回待资料结果，保留来源，不静默省略经历。
- [x] 在原草稿版本存储采用 `content.json`、`render-manifest.json`、TeX 和原归档；
  再次采用核验同一版本，不覆盖已采用内容。读取无需实时库。
- [x] 已映射人工条目的措辞、位置、经历顺序和记录省略作为保护基线；没有 JSON
  映射的显式人工 TeX 保留稿停止内容覆盖，不解析或迁移，交给 J06。

复用回归：`test_p05_generation.py`、`test_p05_writing_boundary.py`、
`test_p05_retained_writing.py`、J05 内容交接回归及同一
`scripts/run_experience_generation.py` 入口。
完成标准：真实 subagent 合成多经历证据与程序验证分开；不能用多次普通模型调用
冒称真实 subagents。本轮开发协作 subagents 也不是简历生成接受证据。
完整回归、独立审查和实际作者接受结论只由[J05 验证](j05-verification.md)持有；
未迁移私人数据或更新安装版。后继为 J06 的人工 diff 与构建接续。

## J06：版本、人工修改与 Prism

交付：内容 JSON 为主记录，TeX/PDF 为构建；直接 Prism 修改有可核查接回路径。
源码及当前实际 Prism 工作树的临时合成验证见[J06 验证](j06-verification.md)。

- [x] 先查实际入口、项目 Git 根与同步方式，确认当前 `sync=false`/Git 拒绝规则
  如何在具体 Adapter 中调整；不默认开启同步、不盲删检查、不自动提交/推送 Git。
- [x] 保存内容/模板/renderer/实际构建基线和 diff 来源；`.git` 不作编译依赖。
  映射明确的人工文字、删项、顺序变更回填 JSON，基线不符不能覆盖。
- [x] 无法表达的排版/跨块修改保留原源和 diff，标记待归并；人工稿仍可使用，
  暂缓会覆盖它的自动重建。以真实样例决定可接回范围，不做通用逆解析器。
- [x] 未归并状态归既有编辑会话/内容版本关联，构建绑定实际人工源与 diff；不得
  声称旧 JSON 可重建该稿。受影响内容不自动跨岗复用或按旧 JSON 重建，原任务
  手工构建及无关已归并片段仍可使用，不新建 PDF 业务接受状态。
- [x] 人工返回仅快速文字校对，补丁范围/条件写入/并发编辑保护保留；普通编辑
  不要求重复内容批准，不把人工新增事实静默写入两库。
- [x] 修复 finishing 中断 P2：同会话恢复捕获源、已有校对结果和条件保存回执；
  已知完成只采用，未知结果先核对，不重复模型或写入。
- [x] 内容复用与已完成构建捷径分开；取消新路径的独立 PDF 业务接受/版本判断。
  保留 PDF 完整性、实际输入对应、旧终稿、迟到结果隔离与真实上传文件身份。

复用回归：`test_p06_versions.py`、`test_p06_proofread.py`、`test_p06_prism_results.py`、
`test_application_prism.py`、`test_automatic_material_reuse_edit.py`、PDF 恢复测试。
完成标准：真实 Prism/Git 入口与支持/未支持编辑样例分别举证。无法接回的稿件不能
被标为“JSON 已完整同步”，也不能被新生成覆盖。

## J07：申请记录 JSON

交付：保留 `ApplicationStore` 调用 Interface，将当前申请记录的磁盘主记录迁入 JSON。
这是独立存储改造，不在 J05 中顺带重写 tracker。源码与合成记录见[J07 验证](j07-verification.md)。

- [x] 保存完整 JD 原文及既有必要查询字段，复用现有 JD 提取/解读；不重做已完成说明。
- [x] 保留已有申请 ID、外部链接、状态、输入版本、材料与动作记录。ID 若当前依赖
  文件路径，迁移显式映射，改名不得重复创建申请或破坏恢复引用。
- [x] Markdown 原件与 original-byte 备份保留；JSON 采用后 Markdown 仅作历史输入/
  可选导出。导出不能成为第二权威副本；外部旧笔记修改显式导入为修订，冲突保留。
- [x] 复用现有原子写与历史，迁移可重复执行；中断/重复导入/同源内容不会漏项、
  重复排队或覆盖新 JSON 修改。非法记录失败可定位，不能静默按空 JD 继续。

完成标准：两库与申请记录在内部都走 JSON；新日常调用不再从 Markdown 章节恢复字段。
旧任务继续可读与可恢复。用 ApplicationStore、intake、pipeline、worker 相关合成测试
验证；真实历史导入结果只留私库。

## J08：组合、QA 与交付准备

- [x] 接现有默认流程和材料准备入口；Worker 继续消费实际完成产物，不需要重写 ATS。
  岗位顺序、表单保护、未知结果核对和最终 Submit 手动保持原产品契约。
- [x] 覆盖多经历/固定身份教育/局部重写/人工删改/重复引用/编译失败/迟到结果/重开恢复；
  四个 P2 各有独立回归与原报告链接，不因 JSON 切换自动宣称已修复。
- [x] 先受影响测试；共享存储/流程修改后跑完整默认离线、Ruff 与必要浏览器合成验证。
  不混用早期测试计数，不把本轮文档检查当作新运行的源码绿灯。
- [x] 固定同一合成输入比较旧/新契约：事实保全、录制写作/修复、局部重试、人工修改
  和重开恢复；程序耗时仅作诊断，模型及完整端到端延迟尚未测量。原始日志留本机。
- [x] 已按后继明确范围，用真实资料生成完整内容、TeX 与 PDF，检查事实、教育/身份、
  截断、溢出、链接和版式，见[完整真实输入验证](full-real-input-verification.md)。
  本次真实申请原记录/旧稿/失败不覆盖；材料 QA 不等于 ATS 接受。
- [ ] 安装交付单列：冻结已验证候选后，用 `macos/main_app.py` 更新唯一主 App，复用
  固定签名并保留回滚；安装及真实运行遵循届时明确授权，本轮计划不触发它们。
- [x] 旧路径退出分步进行：新任务持有内容契约，不再进入旧 TeX 写作/事实接口；
  保留旧版本读取和失败诊断。不删除历史来制造“只剩一种格式”的表象。

完成标准分层记录：源码/离线、真实 subagents、Prism/Git、安装、私人材料/PDF、
网站行为各自有证据，未执行项留空。本轮目标不包含自动最终 Submit。

## 当前下一步

J01/J02 最小切片、J03 经历库、J04 读取/匹配、J05 内容写作/终审/采用、J06 人工
编辑与构建接续，以及 J07 申请记录 JSON 主存储已接入现有源码。固定姓名、
联系方式、教育和样式仍是 LaTeX 模板原文，不需要写作 JSON。

J06 按精确 renderer 范围接回可表达的人工文字、链接、删除与排序。身份歧义或
模板/宏变化保留完整 TeX、diff 和父内容引用，停止自动覆盖。finishing 恢复采用
已有校对和写入结果；未知结果先核对。列表保护和整段经历省略在每个版本保存，
连续人工接回或资料包变化不能清除。当前实际 Prism 工作树与临时 Git 工程完成
原生条件保存、真实编译及回执读取，用户服务和私人文稿仍未验收。

J07 保留原 ApplicationStore Interface，新记录走版本化 JSON。旧记录保留 ID、
Markdown 原字节及历史，显式预览导入不重做 JD 解读。JSON 与旧源双方有修改时
保留冲突；同一请求发布后中断能采用已有结果。

最终受影响组合、完整默认离线回归与静态检查已通过。默认节点分组逐项覆盖，
没有重复或漏项；回归前后实现与测试指纹一致。
各包结论由[J06](j06-verification.md)、[J07](j07-verification.md)和
[J08](j08-verification.md)验证记录分别持有。

J08 已在现有默认流程接通内容 JSON、固定模板、材料候选与原页面采用；
Worker 复用 Flow 声明信息库。实际作者、临时原生 Prism 和合成浏览器分别举证，
见[J08 验证](j08-verification.md)。当前申请经历完整转换与完整真实申请分经历作者
JSON 校验见[完整真实输入验证](full-real-input-verification.md)。单一独立内容终审、
固定渲染和逐页 PDF QA 均已通过；用户服务、安装及雇主网站接受仍单列待验。

本轮实现仍在工作区，尚未形成独立提交。原有未提交改动、私人资料、人工修改、
旧材料及失败记录保留。当前冻结源码完整默认回归覆盖无重复或漏项，前后源码
稳定，Ruff 通过。初始当前申请经历转换已完成；实际模板固定个人信息与教育，
保留原样式，不增加字体依赖。完整真实申请材料已通过内容终审、固定渲染与 PDF QA；
用户模板服务及安装更新未在本阶段执行。原真实申请 P04 分析失败及安装状态保持原证据，
完整材料验证不能替代原分析成功或 ATS 接受。
