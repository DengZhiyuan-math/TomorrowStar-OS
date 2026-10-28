# 代码库职责审计与整理

本轮按 codebase-design 的 Module、Interface、Implementation、
Seam、Adapter 术语审计当前代码。原则是：每个流程消费明确的上游交付，只完成自己的
工作，再交付结果。调度流程可以组合多个步骤；它不重新实现这些步骤的判断和存储。

审计覆盖生产 Python 的 Interface 和依赖清点、主流程与材料链、执行和原生入口、
前端读投影、研究与存储职责。历史验证、第三方源码和私人记录保持原状。

## 流程的唯一职责

| 流程 | Module 所有权 | 消费及交付 | 不在此处执行 |
| --- | --- | --- | --- |
| 邮件与岗位来源 | `application_gmail`、`application_intake`、`application_recommendations` | 原始邮件/链接 → 已保存岗位交付 | 匹配、写作、浏览器填写 |
| 单岗推进 | `application_pipeline`、`application_flow` | 当前岗位、步骤状态与交付引用 → 下一必要步骤或等待原因；确定性计分委托纯评分 Module | 重写 JD、复制来源存储格式、重做模型匹配或改评分框架 |
| JD 解释 | `application_job_brief` | JD → 固定业务目标、要求和评分框架 | 根据申请人事实评分或决定执行动作 |
| 事实读取 | `application_career_library`、`application_retrieval`、`application_material_packet` | 固定目录/读取范围 → JSON 事实、引用和读取回执 | 推定不存在能力、写简历、判断申请资格 |
| 匹配与评分 | `application_match`、`application_inference`、`application_match_scoring` | 固定要求和已交付事实 → 判断、分数及资格结果 | 改写事实、写作、发送申请 |
| 资料投影与输入限额 | `application_material_sources`、`application_input_limits` | 已交付来源和显式环境配置 → 模型资料、原文定位及 byte budget | 调用 reader/matcher、读取申请状态或运行模型 |
| 分经历写作 | `application_writing`、`application_experience_content` | 已交付事实和写作要求 → scoped JSON | 重读资料库、重解 JD、修改固定个人信息和教育 |
| 渲染 | `application_resume_render` | 内容 JSON 和固定模板 → TeX、范围与版本 | 修改语义、运行模型或编译器 |
| 内容终审与采用 | `application_experience_content`、`application_resume_versions` | 组装内容和定位补丁 → 审查/采用记录 | 第二次匹配、改写人工保护项 |
| 构建与读取 PDF | `application_prism`、`application_resume_versions` | 已采用源和构建回执 → 对应 PDF | 再评估资格、重新内容终审 |
| 附加材料 | `application_materials.SupplementalMaterials` | 固定资料、JD 和已观察字段要求 → 保留的材料版本 | 观察网页、填写字段、重读现有职业资料库 |
| 网页执行 | `application_worker_browser`、ATS Adapter | 已绑定岗位、材料、答案及当前页面 → 动作与 readback | 重复 JD/语言筛选、最终 Submit |
| 状态展示 | Flow/Worker snapshot、`application_explanations`、前端 | 后端读投影 → 界面 | 创建业务事件、另算材料状态、重审已完成 P04 |
| 测量 | `worker_measurement` | 已提交状态转换 → 保留的测量事件 | 用 GET 轮询创造干预记录或改变业务状态 |

技术核验仍属于各 Interface：字段、身份、引用、版本、源/PDF 对应及未知结果必须
核验。它们不构成第二次事实判断或语义终审。最终 Submit 继续由用户操作。

## 2026-10-25：新页面识别与资料复用

同日新增的 [Codex 接管 T01/T02](../.scratch/codex-assist-t01-t02-2026-10-25/implementation.md)
仅落地元数据：Worker 拥有接管引用、条件采用与写者占用，browser 的脚本准入和排队
命令遵守该占用。`application_codex_assist` 只拥有专用进程与元数据协议，不提供模型
turn、原页工具或业务完成判断；页面权限始终为 false。后端仅传窄配置，Worker 内
构造休眠 Adapter，既有材料 `codex_cli` 的职责不变。原页操作、活动停写和可靠恢复仍
属于后续任务，源码验收不代表安装 App 已具备这些能力。

后续 [T03 原页只读工具](../.scratch/codex-assist-t03-2026-10-25/implementation.md)
由 `application_worker_browser` 负责固定原页、文档及接管引用核验，返回限量 DOM 和 PNG；
由 `application_codex_assist` 负责协议排队和图像内容编码。`progress` 不执行页面观察，
`service_readonly` 显式在 Worker 原线程调用只读工具。控制专用 tick 不执行排队页面命令
或后续业务派发。该工具不填写、不上传、不提交，也不生成“填写完成”业务结论。

[T04/T05](../.scratch/codex-assist-t04-t05-2026-10-26/implementation.md) 将撤权及停止事实
归 Worker，将原生中断和专用进程排空归 Adapter。后端关闭先撤权，原页核对在 Worker
原线程、业务锁外执行；核对完成仍暂停，不自动释放写者。后端进程身份不等同 UI
心跳，实际 kernel 代次失效不能继续授权工具。更广的 Module 迁移和最终回归仍在进行。

同日的 [Cover Letter 接入实施](../.scratch/cover-letter-integration-2026-10-25/implementation.md)
增加申请级正文及独立尝试。`application_resume_author` 通过既有分经历交接执行作者，
`application_cover_letter` 消费同一固定资料写完整正文并派生文本或按需 LaTeX，
`application_material_consistency` 精确复用已有版本对终审或补一次事实矛盾检查。
Flow 保存两路结果和恢复，Pipeline 继续只持有一个岗位；Worker 只消费本页交付。
人工正文与可唯一映射的 TeX 修改通过原条件保存流程形成受保护后继版本，
无法映射的修改保留源与差异。源码验证不代表安装版或真实 ATS 验收。

浏览器关闭后，以岗位记录和已保存资料重新开始填写，不要求恢复旧会话。
`application_recommendations` 在一次读取中建立岗位、记录 ID 和无链接候选索引，
保持原去重顺序，不增加持久缓存。`application_existing_handoff` 绑定同一 Flow、
岗位、终稿及当前信息库；`application_handoff` 保存新的填写尝试与旧填写提示。
前端只展示本次尝试的状态。材料准备不重新运行分析、生成或编译。

旧填写与人工文案保留来源；旧页面和附件回执不作为新页面成功证明。
相同请求、响应丢失和中途保存失败复用已保存的本地准备结果。
未知提交、执行占用、资料冲突和材料变化仍停止当前岗位。

本轮完整默认回归、隔离浏览器回归、静态检查及执行清单一致性检查通过。
运行前后源码与测试保持一致。合成回归不代表真实网站填写、上传或最终提交验收。

## 已落地的整理

| 原问题 | 现在的 Interface 与 Implementation |
| --- | --- |
| 纯内容和记录流程反向加载 Worker，只为获得 hash/目录函数 | `validation.hashing.record_digest` 和 `application_storage.private_root` 拥有唯一 Implementation；Worker 只保留直接兼容导出。历史 JSON 字节和身份算法不变。 |
| 信息语义由 Worker 定义，Information 又反向依赖 Worker | `application_information` 拥有事实别名、作用域匹配及国家集合；生产调用者直接消费信息 Module。 |
| JD、检索、读取和匹配分别核验原生回执，检查不一致 | `codex_cli.validate_recorded_result` 与 `output_validation_marker` 拥有原生绑定、日志一致性及严格 JSON 类型核验；各流程只核验自己的业务 schema。 |
| JD Module 同时计算申请人分数、资格和路由 | 纯 `application_match_scoring` 拥有评分与匹配分类；JD 只构造/验证固定框架。旧导入路径是直接 alias。 |
| 展示已完成 P04 时再次查询事实并降级原判断 | `job_explanation(..., fixed_delivery=True)` 消费 Flow 已核验交付；旧实时刷新 Adapter 保留原行为。 |
| 用户明确否认资格仍被模型的 supported 覆盖 | Flow 的有效资格判断采用当前有效用户说明；原分析、评分及历史记录不被改写。已有 gap 冲突保护保留。 |
| Pipeline 读取 Intake 私有 `source-chain.json` | `Intake.source_delivery(run_id)` 拥有路径、读取、校验和稳定去重，Pipeline 只消费岗位 ID 交付。 |
| 浏览器执行前重复运行语言/JD 筛选 | 已验证 single 交付继续消费原资格；旧任务的筛选 Adapter 保留，原 binding validator 仍先执行。 |
| Worker snapshot 写入干预日志 | 问题分组为内部纯计算；已提交的 `WorkerStore.save` 观察步骤记录事件。snapshot 不写持久化记录，进程身份内存缓存保持原实现。 |
| 重开后同一请求组重复记录 | 测量 Module 从保留事件恢复请求组；不改组 ID，不宣称跨进程 exactly-once。 |
| JS 复制后端材料状态算法并遗漏 JSON 交付 | Flow snapshot 交付 `local_materials`；前端直接展示该值，不持有第二份判断。该字段不写入任务或改变 revision。 |
| 诊断 Module 保留未被当前生产路径使用的旧执行准入 Implementation | 原函数迁到既有 `application_execution`，诊断 Module 保留直接 alias；所有旧保护表达式不变，不改变运行权限。 |

这些 Seam 来自真实调用者和已有 Adapter，没有新增工作流框架、数据库或统一事件系统。
兼容导出指向同一函数对象，没有增加转发层。Depth 来自调用者可直接消费完整交付；
共享 Implementation 为多个调用者提供 Leverage，并让修复集中在职责所有者，提高 Locality。

## 保留的合理 Module

- `application_flow` 拥有单岗生命周期；`application_pipeline` 拥有跨步骤推进。这是
  调度职责，不因组合步骤就拆成多个调度器。
- ATS Adapter 拥有站点差异，Browser Module 拥有 intent、页面身份、执行及 readback。
  这些动作共同完成一次受约束执行，不按文件长度拆开。
- 原生 host 的 snapshot、receive、check 分别承担内存投影和实际探测。
- `domain`、`audit`、`assessment`、`interview`、研究 `jd` 保留其贡献证据、审查、
  评分及研究验证语义；它们不成为普通申请的新审批步骤。
- `workspace`、`career_experiences`、`career_portal_data` 和版本存储分别拥有对应记录
  的格式、原子写入与历史。研究 Git workspace 与申请运行目录的约束不能混用。
- 当前 JSON 路径与已保存旧 TeX 任务使用不同 Adapter。旧格式只负责恢复原任务，
  不借整理删除原始资料、人工编辑或历史证据。

## 第二轮已完成的职责迁移

| 原问题 | 现在的 Interface 与 Implementation |
| --- | --- |
| reader/matcher/writer 共享 matcher 私有来源投影，限额反向引用 reader | `application_material_sources` 拥有资料投影、结构化事实、原文引用及定位；`application_input_limits.context_limits(environment)` 拥有限额。所有调用者已迁移，reader/matcher 不再互相依赖。合成资料的 prompt/replay 字节、来源 ID 和 UTF-8 边界保持一致。 |
| Browser 附稿路径同时观察字段、准备材料、读取目录、生成和保存 | `SupplementalMaterials.prepare` 消费固定资料和观测要求，拥有生成、版本保存与采用；Browser 只 observe → consume → fill。持久化 callback 保留原事件合并，迟到结果和人工非空值保留。 |
| 附稿入口可重新取现有目录，重复资格筛查 | `read_delivered_material_inputs` 校验 single binding、P04、材料包和来源版本，交付固定资料。缺失或损坏时停止。Worker/Portal 先验证 binding 或材料 lineage，再消费唯一的 `check_single_qualification` 策略；固定交付能力来自校验结果，不能从 workflow 字符串推定。未具备固定交付的历史任务继续使用原 Adapter。 |
| Pipeline 自己解释 Flow 内部 stage 失败字段 | Flow 的只读 `analysis_outcome(task_id)` 交付尝试状态、错误和恢复类别；Pipeline 只决定等待或推进。旧分类保留直接 alias，旧失败规则不放宽。 |
| 纯目标核验同时构建旧 handoff prompt | `validate_application_target` 拥有目标、日期、重复记录和规范化 URL 核验；`prepare_application_task` 仅在实际 handoff 时组合 prompt。Browser、Worker 和 Portal 的纯核验调用者均已迁移。 |

读取超时可能被包装为 `retrieval_execution_incomplete`，该错误不能单独证明调用结果
已知。Flow 将此情况保留为 unknown/needs_recheck。默认队列的已知失败和未知结果均
停在同岗，Continue 不重读来源、不重解 JD、不盲重试或跳到下一岗位。

实际发送前仍重新核验当前页面、字段、附件和人工操作。材料生成成功不授权覆盖
迟到的人工输入。目标、资格、材料来源及页面身份核验分别保护其所属 Interface。
固定资格引用的适用信息后来发生实际冲突时，执行停在当前岗位；这项交付核验不
重解 JD、不另算匹配，也不把其他资料库或无关信息的冲突变成当前岗位的阻断条件。
已引用事实被更正或撤回同样停止。prepare、resume、review、recheck 都消费已验证的
固定交付标记；历史任务在这些入口执行原语言 Adapter。recheck 补齐了旧入口之间
的不一致，不能把这项收紧描述为仅搬移代码。

## 验证与交付范围

- 关键变更先留失败回归，再通过所属 Interface 验证。
- 纯 JSON 和纯信息读取可在执行 Module 不可用时工作。
- 用户说明、Boolean 分组、原评分字节、原生回执类型、未知结果、只读快照、重开、
  来源交付、旧导入、迟到材料和人工输入保护均有定向回归。
- 独立交叉审查已完成；完整默认回归、静态检查和格式检查按最终冻结源码单独记录。
- 本轮不读取私人经历库、不调用真实模型，不更新安装版或操作 ATS。历史安装与
  真实材料接受记录继续持有原范围，不能替代本轮源码检查。

| 本轮检查 | 最终结果 |
| --- | --- |
| 生产 Module Interface 与静态依赖清点 | 通过 |
| 关键公开 Interface、历史兼容和人工修改保护回归 | 通过 |
| 冻结源码完整默认离线回归 | 通过 |
| 默认选择完整覆盖、无重复、测试前后源码及测试文件稳定 | 通过 |
| Ruff、格式和 diff 检查 | 通过 |
| 最终冻结版本独立交叉审查 | 通过 |
| 安装版、真实模型、真实浏览器与 ATS 验收 | 本轮未执行 |

私人验证入口保存完整 Module Interface/依赖清单、变更前指纹、分工审计、红绿日志、
交叉审查与最终回归。初次失败和因后继源码修正失效的中间运行分别保留；只有最后
冻结版本持有本轮全套通过结论。公开文档不复制私人记录或运行定位。

## 2026-10-25：高频读取与调度复核

此次复核保留上述整理，清点生产 Python Module，并重点检查单岗调度、申请记录、
筛查和状态读取的实际调用。一个读取流程只交付调用者需要的结果；完整性核验仍由
原 Module 执行，不以缓存跳过。调度保持单岗顺序执行。

| 热点 | 整理后的职责与性能特征 |
| --- | --- |
| 单条申请读取反复验证同一批 JSON | `ApplicationStore` 的内部逐条交付在一次调用中复用已验证结果；查询仍遍历并核验全部 JSON，其他坏记录仍阻断。没有跨请求缓存，外部编辑和旧 Markdown 变更在下一次读取中可见，写入继续重读版本与备份后的原文。 |
| Pipeline 仅需当前任务却投影所有历史任务 | `Flow.task_snapshot(task_id)` 只投影选定任务，沿用 Worker 与既有 handoff 检查；返回值与完整 snapshot 的对应任务一致。恢复及重启仍使用完整历史。 |
| 队列过滤为每条推荐重建已处理 ID 集合 | Pipeline 每次快照只构建一次集合，保持来源顺序、重复项与旧记录行为。过滤成本从两组记录数的乘积降为两者之和。 |
| Pipeline 展示每个岗位名称都再次扫描全部记录 | 每次快照用一次列表交付建立本次调用的名称索引；缺失记录保留原字段。列表遇到旧资料错误时回退原逐项查询，不扩大读取失败的影响。 |
| 当前岗位筛查重复计算全部其他岗位 | `screen_applications(..., application_id=...)` 只计算当前岗位的筛查结果；重复申请和公司历史仍消费完整记录。默认批量 Interface 保持原结果。 |
| 准备模式 GET 重扫计量历史并写入事件 | PDF 或分组交付成功保存后，由观察回调记录请求；GET 保留材料完整性核验，只交付状态。保存失败不会创建请求事件，重开后的事件去重沿用原实现。计量异常标记记录不完整，不改变已保存的业务结果。 |
| 旧浏览器重新核验没有向表单采样交付已确认现场 | 浏览器核验成功后交付原页面观察，由表单 Module 确认当前采样。明确未应用的动作只有在运行、页面、文档、字段形状、答案版本和目标值均一致时才可重新计划；人工第三值、未知结果和后继结论不继承重试权限。 |
| 命令与采样各存一份状态，后一次保存覆盖刚记录的观察 | 原页 Continue、人工查看和旧重新核验向采样传入同一份已锁定状态。传输事件、迟到失败、未知动作和旧文档历史由同一所有者保存。默认独立采样仍使用原读取路径。 |
| 必填附稿尚未上传，就被最终就绪检查阻断 | 先执行受保护的附稿上传和读回，再返回下一轮采样与解析稳定检查。最终就绪条件不变；附件自身读回同时绑定类型、文件名、hash 和字段定位，持续保护同名异内容与迟到人工修改。 |
| 局部材料提交后，严格信息读取先于本地恢复 | 用户 Continue 先协调当前任务已有的精确恢复日志，再执行原绑定核验。暂停只消费已验证的控制投影；所有真实动作保留原身份、所有权、取消、材料及页面核验。 |
| 已完成人工源编辑仍被下一次 Continue 当作待办 | 已完成更新保留历史但不再次生成；新的明确编辑仍建立自己的更新版本。 |
| 人工定位原页与最终表单审阅混用就绪检查 | 仅明确请求且原页当前有效的人工查看可跳过最终表单就绪条件；岗位、材料、答案和单岗绑定检查仍执行。查看不标记完成、不清除未知动作、不启动自动执行。 |
| Ashby 为不同内容的材料返回同一附件 ID | 附件 Adapter 在采用链接回执和最终核验时，比对已知附件 ID、路径与内容 hash；不同内容不能共用同一已知远端附件。相同内容复用和原路径更新继续执行原核验。 |
| 暂停后的旧观察覆盖答案队列或邮箱纠正等待 | 缺答案结果在原写锁内核对最新答案，再发布问题和等待状态；拒绝发布会结束旧执行轮。纯就绪推导同样核对当前上下文，保留新的未知动作、邮箱纠正、人工接管和暂停；真实动作回执继续保留。 |

这些变化使用已有存储、投影、筛查和观察回调，没有新增依赖或工作流框架。
合成测量验证本地记录读取和操作次数的改善；它不能建立模型、PDF 编译、已安装 App
或真实申请的端到端提速结论。

扩展浏览器回归同时修正了旧测试夹具：通过真实折叠导航进入保留的兼容编辑功能，
显式构造历史任务与材料归档，并按现行上传、解析稳定、差异合并顺序等待。
浏览器内置 PDF 查看资源属于本地资源；测试继续拒绝未声明的外部网络请求。
测试不恢复已退役的 HTML 路径，也不把合成 PDF 或准备状态当作用户验收。
共享等待工具观察指定岗位，并调用真实 Runner 推进；不直接改时钟、心跳、答案或
控制状态。Runner 仍负责岗位调度；未知结果、人工差异和暂停保留专门的停止回归。
当前 JSON 材料流程与历史 LaTeX 恢复分别使用
真实归档和各自的生产入口，不通过删除契约标记把新任务伪装成旧任务。

完整默认离线回归、隔离浏览器回归和静态检查已在最终冻结版本完成。两类回归均无
失败或错误；实际执行 ID 与完整采集清单逐项一致，没有遗漏或重复。运行前后源码、
测试及工具链文件保持一致。此前表格中的结论继续保留其原有验证范围。

| 本轮最终检查 | 结果 |
| --- | --- |
| 生产 Module、公开入口及静态依赖清点 | 通过 |
| 缺答案、纯就绪推导、实际动作回执及附件身份回归 | 通过 |
| 完整默认离线回归 | 通过 |
| 完整隔离浏览器回归 | 通过 |
| 实际执行 ID 完整一致、无重复 | 通过 |
| 运行前后源码、测试及工具链文件稳定 | 通过 |
| Ruff、格式与 diff 检查 | 通过 |
| 最终生产修复独立交叉审查 | 通过 |
| 显式启用的性能基线、实际编译基准与原生 Cua 项 | 本轮跳过，不计为通过 |
| 安装版更新、真实模型及真实 ATS 验收 | 本轮未执行 |

原始失败、夹具死锁导致的中断、修复前后的定向回归与最终全套结果分别保留。
本轮结果建立源码和隔离测试结论，不替代安装版、真人材料接受或真实申请验收。

<a id="public-entry-points"></a>
## 核心 Module 当前公开入口（2026-10-27，MC-17）

本节登记**当前代码**中七个核心 Module 被其他源码文件实际调用的入口，供改代码前判断能用什么、
审 diff 时识别越界。来源是对 `src/career_evidence_graph/` 的 AST 扫描（含函数内导入和
`obj.method` 调用，按接收者名过滤同名方法后人工剔除误报），不含 tests/。Module 文件归属沿用
[设计的职责表](module-interfaces-and-migration-design.md#职责与状态所有权)。设计各小节的签名是
目标表达；**问“现在能调用什么”以本节为准**，问“应该变成什么”以设计为准。行号属于 2026-10-27
快照（计划收回表的行号于 2026-10-28 MC-15/MC-19 后按当前代码重核），以文件和符号为准。当前有效段落的总导航见[当前有效索引](current-index.md)。

规则：新代码只调用本表入口；需要表外能力时，在所属 Module 增加公开入口并同改本表，不新增私有访问。
MC-18 棘轮拦截跨模块私有**导入**；MC-19 新增的 `private_attribute_uses` 计数（`tests/test_dependency_ratchet.py`）按文件统计 src 与 tests 中接收者表达式**恰为**
`flow`、`self.flow`、`pipeline`、`store`、`ApplicationFlowService`、`ApplicationResumeStore` 的 `obj._name` 访问，增加即失败、减少须记录。
它只覆盖这些接收者名：其他接收者（如 `service`、`case.flow`、`p.pipeline`、`*.application_flow_service`）及 `getattr(obj, "_name")` 字符串访问不计入，
仍须审查把关；`store` 也会计入 Resume 以外的 store（如 `assessment.py`、`application_information.py`）。
每张 MC 票结案时同步更新本节及下节。

MC-06 结案（2026-10-27）：未新增也未收回 Worker 外部入口。原生材料交付新增的 `_resolve_native_material_call`、
`_prepare_native_material_call`、`_reconcile_native_material`、`_native_material_network_permitted` 与 `WorkerStore` 的
`resolve_bound_material`、`native_material_intent`、`record_native_handoff` 只在 `application_worker*.py` 内部调用；
新原生工具 `browser_deliver_material` 属驱动协议（`fixed-material/v1`），不是 Python 入口。

MC-07 结案（2026-10-27）：未新增 Worker 外部入口。`adopt_assistance_report`、`adopt_assistance_outcome`、`assistance_completion`、
`assistance_binding_resumed_only` 与 `_service_assistance_return` 只在 `application_worker*.py` 内部调用；Pipeline 继续只消费既有 ready_for_review 投影。

MC-08 结案（2026-10-27）：Pipeline 新增命名控制 `pause`、`continue_current`、`skip_current`、`return_to`、`observe_result`、`start`、
`capture_mail`、`admit`、`begin_material_edit`（`cancel_current` 原有）；`request(action, payload)` 仅为薄映射，MC-14 移除。Portal 以路由表映射到
这些方法，`/api/flow/worker-action` 的 pause/skip/select/observe 与材料编辑路由经 Pipeline。Worker 新增公开入口 `takeover_candidate`、
`request_takeover`（Pipeline 调用）；`technical_blocker`、`record_takeover_failure`、`archive_stopped_assistance`、`takeover_pending_intent` 仅 Worker 内部使用。
`begin_material_edit` 经 Flow 已注册的 `bound_worker_state` 回调读取 Worker 停写状态（与 `_pause_owned_worker` 同一读取器，非新增穿透）。

MC-14 结案（2026-10-27，隔离副本实施）：新增 `application_runtime.py`（`open_runtime(...)` 与 `ApplicationRuntime.stop_writes/close`）负责组装、启动和关闭；
`career_portal.create_server` 签名不变，只做端口/准入策略、安装布局、静态文件、绑定与 HTTP 映射，页面投影已于 MC-15 移入 `application_flow_view.FlowView`。
Pipeline 移除 `request(action, payload)`，新增 `flow_control(action, payload)`（原 Portal `_pipeline_worker_control`），Portal 的 `pipeline_control` 只按路由表映射命名控制；
`__init__` 在线程启动前登记 `preparation_allowed`。Flow 新增材料装配 `configure_materials` 与读取/核验入口及 `witness`、`read_checked_task`、`writable_task` 等（见下表）；
写前检查移入 `application_single_binding.write_preflight`/`validate_write_preflight`/`preflight_target`（只调 Flow 公开入口，Runtime 登记为回调，不新增导入环）；`application_readiness.ReadinessProbe` 取代 Portal readiness 闭包；Worker 只新增 `readiness_facts`；
`application_material_batch` 新增 `batch_candidates`/`select_batch_item`。行为变化仅一处：畸形请求发到已关闭 Pipeline 时由 `pipeline_unavailable`（409）改为
`pipeline_request_invalid`（与开启时相同的 400/409 与文案），均无副作用。

MC-15 结案（2026-10-28）：页面状态投影由 Portal 移入 `application_flow_view.py`（`FlowView.state(task_id=None)`，Runtime 在 `_assemble` 装配为
`runtime.flow_view`；`/api/flow/state` 与 `/api/flow/<id>` 调用之）。旧键与顺序不变，新增 `progress`（与 snapshot 同一写锁下的 Flow `progress`，去掉
`task`）与 `preparation_activity`（`running`/`needs_recheck`/`idle`）。Pipeline `snapshot` 新增 `notice`（等待通知，或仅在接管进行中的接管标题/消息）；
`notification` 与 App 协议不变。`open_runtime`/`create_server` 新增仅合成用 `resume_model_mode`、`flow_automatic_latex_base`，`macos/server.py` 创建后不再修改服务；
删除 `career_portal._external_directory`。新增 FlowView 入口见下表。`loaded_code` 角色覆盖由 `tests/test_loaded_role_coverage.py` 强制：
实际加载的包模块（含应用写路径中延迟导入的模块）须在某个角色中，或列入带理由的豁免表；角色内容以 `loaded_code.py` 与该测试为准。
MC-20 起每个角色须包含其模块的全部静态包导入闭包（模块级与函数内惰性导入），不再只要求“在某个角色中”：
worker 角色因此也覆盖控制器侧准备路径（无论 worker 是否执行）；worker 在记录启动身份前调用 `loaded_code.load_worker_modules()`
预载整个角色（与 `load_controller_modules()` 对称），并由跨进程测试核对运行时记录的身份与源码上 `measure_packaged_roles`
（`macos/build.py` 使用的同一函数，不含打包 Python 与构建环境）两种加载顺序的结果一致。
默认页面已读取 `preparation_activity` 与 Pipeline `notice`，仍保留的本地阶段状态规则与未决事项见 [MC-15 结案记录](../.scratch/module-completion-2026-10-26/issues/15-m6-ui-compatibility-identity.md)。

MC-19 结案（2026-10-28）：Flow 新增/调整公开入口 `valid_material_acceptance`（`application_source_reuse`、`application_pdf_reuse` 调用）与
`writable_task(task_id, task_revision=None)`（无 revision 时只检查可写）；`verify_latex_base`、`verify_prism_source` 直接持有原私有方法的实现（私有方法已删除）。
Resume 新增模块函数 `application_experience_latex.read_completed` 与常量 `FEEDBACK_KEY`（由 Flow 的 existing-experience 回调与 `application_existing_materials` 使用）。
`application_bound_materials` 不再导入 Flow（消除一处导入环），`application_material_edit` 只用 Flow 公开入口。
MC-19 未删除无外部调用者的 Flow 公开方法（理由见下表 Flow 行末列）；测试侧暂留项见下节说明。

| Module | 文件 | 允许外部调用的入口 | 主要外部调用者 | 公开但无外部调用者 |
| --- | --- | --- | --- | --- |
| Pipeline | `application_pipeline.py` | `ApplicationPipeline`：`snapshot`；命名控制 `pause`、`start`、`continue_current`、`skip_current`、`return_to`、`observe_result`、`capture_mail`、`admit`、`cancel_current`、`begin_material_edit`（MC-08；`request` 已于 MC-14 删除）、`flow_control`（MC-14，Portal 的 Flow 当前岗控制与材料编辑停写）、`manual_entry`、`preparation_allowed`、`close`；材料更新 journal：`complete_material_update`、`resume_material_commit`、`validate_material_authorization`、`commit_material_authorization`（9） | Portal、`application_bound_materials` | `verify_authorization`；设计中的命名控制操作|
| Flow | `application_flow.py` | `ApplicationFlowService` 32 个（MC-14 另增 19 个，见本行末）。调度：`create`、`prepare`、`progress`、`update_inputs`、`continue_preparation`、`cancel_preparation`、`cancel_cover_letter`、`task_snapshot`、`snapshot`、`analysis_outcome`、`material_outcomes`、`cover_letter_outcome`、`material_consistency_outcome`、`material_update_progress`、`prepare_worker`、`worker_action`；装配与 Portal：`configure_analysis`、`configure_worker`、`fixed_writing_inputs`、`resume_call_allowed`、`adopted_artifact`、`prepare_bound_candidate`、`request`、`close`；材料更新：`begin_material_update`、`material_update_inputs`、`validate_material_candidate`、`commit_material_candidate`、`complete_material_update`、`adopt_cover_letter_successor`；批次：`start`、`cancel`。模块函数 10 个：`pipeline_http_entry`、`legacy_analysis_failure`、`job_input_revision`、`analysis_input_binding`、`retained_configuration_inputs`、`qualification_status`、`task_eligibility`、`local_materials`、`latest_preparation_task`、`material_task_view`。MC-14：装配 `configure_materials`；材料读取与核验 `read_draft`、`read_export`、`verify_draft`、`verify_materials`、`material_tasks`、`reuses_base_sources`、`ready_cover_letter_content`、`adopted_resume_content`、`cover_letter_call_allowed`；写前与读取 `witness`、`read_checked_task`、`writable_task(task_id, task_revision=None)`（MC-19 放宽：无 revision 时只检查可写）、`verify_latex_base`、`verify_prism_source`、`check_inputs_current`、`check_available`；模块函数 `stat_tokens`。MC-19：类方法 `valid_material_acceptance`（`application_source_reuse`、`application_pdf_reuse` 调用） | Pipeline、Portal、Runtime、`application_readiness`、`application_single_binding`、`application_bound_materials`、`application_material_edit`、`application_material_batch`、`application_explanations`、`application_single_binding` 等 | 2026-10-28 AST 计数：`ApplicationFlowService` 94 个公开方法中 40 个在包内其他源码文件无按名调用。其中 22 个是 HTTP 动作，经 `request(action, payload)`（`application_flow.py`:1690 起的动作表）按动作名 `getattr` 分派（:1825），按名扫描看不到调用者；其余作为回调或 Flow 内部使用，未逐个核实。MC-19 未删除任何此类方法：逐个收窄须先核对 HTTP 路由、页面、App 与测试的实际调用，超出本票“不改变行为”范围；暂留，未分配后续票（记录于 MC-19 结案） |
| Worker | `application_worker.py`、`application_worker_browser.py`（`application_form_runner`、ATS Adapter、`application_worker_fixtures` 视为内部） | `WorkerService` 22 个：`readiness_facts`（MC-14，ReadinessProbe 只读事实）、`snapshot`、`request`、`check_new_current_job`、`cancel_execution`、`cancellation_progress`、`request_backend_recovery`、`recover_backend`、`suspend_backend`、`begin_backend_close`、`close_backend`、`execution_reference`、`select_execution`、`prepare_execution`、`control_execution`、`check_material_preparation`、`validate_material_update`、`commit_material_update`、`verify_material_update`、`material_update_progress`、`validate_material_successor`、`commit_material_successor`。`WorkerStore`（经 `worker.store`/`runner.store`）16 个：`load`、`save`、`resolve`、`stop_reason`、`check_single`、`check_generic_enabled`、`check_language_requirement`、`language_levels`、`single_context`、`block_storage`、`verify_material`、`field_material`、`material_inputs`、`material_sources`、`library`、`answers_for`。`ApplicationRunner`（子进程内，交给 journal 协调）5 个：`observe`、`verified_intents`、`recovered_upload`、`effective_action_results`、`permitted`。模块级：`OWNED_PAGE_OBSERVATION`、`assistance_reference`、`assistance_stop_pending`、`checked_material_preparation_job`、`manual_submission_unresolved`、`material_edit_pending`、`precision_preparation_pending`、`unresolved_write_failure`、`worker_lock_is_held`；进程入口 `application_worker_browser.main` | Pipeline、Flow（执行引用与控制）、Portal、`application_bound_materials`、`application_material_edit`、`application_materials` | `WorkerService` 5 个、`WorkerStore` 9 个；收窄归 MC-06/07/08 |
| Resume | `application_resume.py`、`application_resume_versions.py` | `ApplicationResumeStore` 34 个。生成与准备：`prepare`、`execute_generation`、`progress_generation`、`reconcile_generation`、`validate_prepared`、`retained_career_draft`、`verify_for_task`、`verify_reuse`、`read_reuse`、`save_automatic_source`、`select_template`、`import_latex_for_task`、`prepare_bound_draft`、`prepare_bound_edit`、`verify_bound_candidate_source`；读取：`read`、`draft`、`read_export`、`configuration`、`export_configuration_revision`；Prism 与分组编辑：`begin_prism_edit`、`finish_prism_edit`、`prism_edit_state`、`capture_compiled_pdf`、`prepare_group_review`、`capture_group_review`、`edit_group_review`、`group_review_state`、`group_preview_pdf`、`adopt_review_snapshot`；PDF：`build_pdf`、`reconcile_build`、`read_pdf`、`pdf`。模块函数 13 个：`career_source_snapshot`、`export_pdf`、`local_materials`、`material_prism_binding`、`material_source_binding`、`prepared_material_state`、`resume_configuration_revision`、`retained_preparation_base`、`validate_prepared_result`、`validate_retained_template`、`verify_latex_base`、`verify_prism_source`、`application_resume_versions.persist_content_generation`；MC-19：`application_experience_latex.read_completed` 与常量 `application_experience_latex.FEEDBACK_KEY`（Flow 的 existing-experience 回调与 `application_existing_materials` 使用） | Portal（Store 方法主体）、Flow（模块函数）、`application_group_review`、`application_full_latex`、`application_experience_latex`、`application_writing`、`application_pdf_reuse` 等 | 39 个公开方法中 5 个 |
| CoverLetter | `application_cover_letter.py` | `CoverLetterModule.prepare`、`read`；模块函数 10 个：`edit_delivered_letter`、`export_cover_letter_pdf`、`reconcile_cover_letter_pdf`、`read_letter_material`、`render_cover_letter`、`reconcile_letter_tex`、`bind_letter_template`、`read_template`、`validate_letter`、`letter_inputs_revision` | Portal、`application_materials`、`application_material_edit`、Worker、Flow、`application_material_consistency` | 无 |
| Analysis | `application_match.py`、`application_matching_pipeline.py` | `Analysis`：`prepare`、`progress`、`read`、`reuse`、`prepare_refresh`、`configuration_revision`（Flow），`read_sources`（Portal）；模块级：`match_configuration`、`match_configuration_revision`、`POLICY_VERSION`。`application_matching_pipeline` 无外部调用者 | Flow、Portal、Resume、`application_match_refresh`、`application_explanations` | `reconcile`（仅类内使用） |
| Intake | `application_intake.py`、`application_recommendations.py`、`application_gmail.py` | `ApplicationIntakeService` 全部 10 个：`snapshot`、`refresh`、`acquire`、`select`、`source_delivery`（Pipeline），`ingest`、`reconcile_job`、`continue_read`、`reconcile_source`、`close`（Portal）。推荐与邮件文件只被 Intake 使用；`application_gmail.validate_recommendation_query` 仅供合成夹具 | Pipeline、Portal、`application_preparation` | 无 |
| FlowView（页面投影，MC-15） | `application_flow_view.py` | `FlowView.state(task_id=None)`（Runtime 在 `_assemble` 装配为 `runtime.flow_view`） | Portal 的 `/api/flow/state` 与 `/api/flow/<id>` 路由、Runtime（装配） | 模块函数 `preparation_activity(task)`（仅 `FlowView` 内部使用） |

<a id="planned-withdrawals"></a>
### 计划收回的内部入口

下列入口当前被所属 Module 之外的源码使用，但不属于允许外部调用的入口。收回时先由所属 Module
提供只表达调用者所需结果的正式入口，再迁移调用者和测试，删除旧用法（替换，不叠加）。
测试中的同类私有调用：MC-19 按用户决定只迁移读取内部状态的断言（计划中的 18 处 `flow._load()["tasks"]` 读取改用 `witness`、`snapshot`、`task_snapshot`；独立审查列出的其余同类断言读取的处理见 MC-19 结案），并把草稿/导出规则用例移入 `tests/test_flow_artifact_query.py`。暂留（用户决定）：约 67 处 `flow._save` 状态重放夹具（持久恢复契约，须从已保存状态重放）与 145 处 `pipeline._tick`（Pipeline 单步推进接缝）；完整 LaTeX、分组审阅、已审阅 LaTeX、渲染器与未知 manifest 的 HTTP 链作为跨多个 Module 的回归链保留。负责：未分配后续票（记录于 MC-19 结案）。

| 内部入口 | 当前外部调用位置 | 负责票 |
| --- | --- | --- |
| `pipeline.flow`/`pipeline.worker` 穿透；`pipeline._owner`、`pipeline._closed` | `application_bound_materials.py`:113、152、255、271、351；158 | MC-14 保留（理由）：材料 journal 是 Pipeline 内部辅助（只由 Pipeline 锁内调用），读取同一 Flow/Worker 与开闭状态，另设入口只会转发；`pipeline._task` 已改为 `flow.task_snapshot`（MC-14 收回） |
| `flow.worker_action`（Pipeline 借 Flow 控制 Worker） | `application_pipeline.py`:1273、1503、1509、1521、1591、1924、2611、2675、2793、2814（10 处，含 MC-09 丢失保存后 Continue 改走 Worker `resume` 的 1503） | MC-14 保留（理由）：公开 Flow 入口；只有 Flow 能按任务 id/revision → `worker_ref` 校验原 batch/run 并施加写前检查，Pipeline 无自有执行引用 |
| `flow.applications`（Pipeline 借 Flow 取共享存储，26 处） | `application_pipeline.py`:73、133、140、153、165、207、273、295、423、568、601、730、756、765、771、864、981、1027、1098、2224、2334、2339、2454、2489、2546、2564 | MC-14 保留（理由）：`write_lock()` 是 Flow 与 Worker 写入共享的唯一跨模块锁，另建锁会造成交错；读取尚无 Application Module 接口 |
| `evidence._paths()`、`evidence._KINDS`、`applications._paths()` | `application_readiness.py`:661、662、673（`ReadinessProbe`，原 Portal readiness）；`application_single_binding.py`:1150、1159（`write_preflight`，原 Portal check_preparation） | MC-14 保留（用户决定）：只读文件标记，CareerCatalog/ApplicationStore 尚无公开路径清单入口；收回时随两库读接口 |
| `review._binding`（`PrismReviewStore`） | `application_flow.py`:1374（`configure_materials`，原 Portal） | MC-14 迁移未改语义；收回需 PrismReviewStore 公开绑定读取 |
| `application_pdf_reuse._acceptance`（导入） | `application_runtime.py`:84（测量观察者，原 Portal） | MC-14 迁移；Flow 不导入 pdf_reuse 以免新增环（pdf_reuse 已导入 Flow） |
| `flow._load` | `application_existing_materials.py`:41；`application_existing_handoff.py`:155；`application_match_refresh.py`:281、799；`application_match_recheck.py`:35；`application_material_batch.py`:189、440、518、879、938、950、1016 | MC-19 保留（理由）：Flow 拆分出的内部文件，仅由 Flow 方法传入 `self` 调用，属 Flow Module 内部 |
| `flow._task` | `application_existing_materials.py`:42；`application_existing_handoff.py`:156；`application_match_refresh.py`:800；`application_match_recheck.py`:36 | MC-19 保留（理由）：Flow 拆分出的内部文件，仅由 Flow 方法传入 `self` 调用，属 Flow Module 内部 |
| `flow._fresh` | `application_existing_materials.py`:75、81；`application_existing_handoff.py`:51、113、359；`application_match_recheck.py`:55；`application_material_batch.py`:610、978 | MC-19 保留（理由）：Flow 拆分出的内部文件，仅由 Flow 方法传入 `self` 调用，属 Flow Module 内部 |
| `flow._save` | `application_existing_materials.py`:158；`application_existing_handoff.py`:74、225、274；`application_match_refresh.py`:959；`application_match_recheck.py`:169；`application_material_batch.py`:295、454 | MC-19 保留（理由）：Flow 拆分出的内部文件，仅由 Flow 方法传入 `self` 调用，属 Flow Module 内部 |
| `flow._writable` | `application_existing_materials.py`:40；`application_existing_handoff.py`:31、154；`application_match_refresh.py`:798；`application_match_recheck.py`:34；`application_material_batch.py`:188、439 | MC-19 保留（理由）：Flow 拆分出的内部文件，仅由 Flow 方法传入 `self` 调用，属 Flow Module 内部 |
| `flow._checked` | `application_match_refresh.py`:743、834、932；`application_match_recheck.py`:41；`application_material_batch.py`:313 | MC-19 保留（理由）：Flow 拆分出的内部文件，仅由 Flow 方法传入 `self` 调用，属 Flow Module 内部 |
| `flow._group_guard_change` | `application_existing_handoff.py`:42、106、355；`application_match_refresh.py`:294；`application_match_recheck.py`:54；`application_material_batch.py`:609 | MC-19 保留（理由）：Flow 拆分出的内部文件，仅由 Flow 方法传入 `self` 调用，属 Flow Module 内部 |
| `flow._read_checked`、`flow._identity`、`application_flow._material_pending`（导入） | `application_existing_handoff.py`:32；127；28、97、331 | MC-19 保留（理由）：Flow 拆分出的内部文件，仅由 Flow 方法传入 `self` 调用，属 Flow Module 内部 |
| `flow._adopt_export`、`flow._batch_after`、`flow._batch_guard_change` | `application_existing_materials.py`:126；157；55 | MC-19 保留（理由）：Flow 拆分出的内部文件，仅由 Flow 方法传入 `self` 调用，属 Flow Module 内部 |
| `flow._check_other_execution_pending` | `application_match_refresh.py`:870 | MC-19 保留（理由）：Flow 拆分出的内部文件，仅由 Flow 方法传入 `self` 调用，属 Flow Module 内部 |
| `self.flow._queue.put`（Flow 准备队列） | `application_material_batch.py`:450、537 | MC-19 保留（理由）：Flow 拆分出的内部文件，由 Flow 以 `self` 进入，属 Flow Module 内部 |
| `getattr(flow, "_owner", True)`（Flow 所有权标记） | `application_pipeline.py`:70 | MC-19 保留（理由）：Pipeline 跨模块读取 Flow 的所有权标记 `_owner`；缺省 `True` 供不带该标记的测试替身使用；改为公开属性只会转调同一值，故保留并记录 |
| `ApplicationFlowService._stage_material_update`、`flow._editable_material_update`、`flow._prepare_material_update` | `application_bound_materials.py`:87；112；120 | MC-19 已收回：未被源码调用的包装已删除，测试改用 Flow 公开入口 `begin_material_update`、`begin_automatic_edit`、`save_automatic_source` |
| `flow._explanations`、`flow._retained_material_current`、`flow._reviewed_groups` | `application_material_batch.py`:259；314；817 | MC-19 保留（理由）：Flow 拆分出的内部文件，仅由 Flow 方法传入 `self` 调用，属 Flow Module 内部 |
| `ApplicationFlowService._valid_material_acceptance` | `application_source_reuse.py`:341；`application_pdf_reuse.py`:81 | MC-19 已收回：公开为 `ApplicationFlowService.valid_material_acceptance` |
| `store._read_version_file`（Resume 外 18 处） | `application_group_review.py`:170、189、474、516、743、755、773；`application_experience_latex.py`:98、1498、1510；`application_writing.py`:703、771；`application_full_latex.py`:1611、1873、2199、2251、2254、2301 | MC-19 保留（理由）：Resume 拆分出的内部文件，由 `ApplicationResumeStore` 调用，属 Resume Module 内部 |
| `store._draft_document`（Resume 外 16 处） | `application_group_review.py`:158、538、648、777；`application_writing.py`:254、341；`application_full_latex.py`:1572、1597、1617、1661、1662、1665、1678、1908、2226、2267 | MC-19 保留（理由）：Resume 拆分出的内部文件，由 `ApplicationResumeStore` 调用，属 Resume Module 内部 |
| `store._task_current` | `application_group_review.py`:188；`application_experience_latex.py`:110、232；`application_full_latex.py`:1641、2136 | MC-19 保留（理由）：Resume 拆分出的内部文件，由 `ApplicationResumeStore` 调用，属 Resume Module 内部 |
| `store._current_export_draft` | `application_experience_latex.py`:1730（`read_completed` 已由 MC-19 移回 Resume） | MC-19 保留（理由）：Resume Module 内部 |
| `ApplicationResumeStore._validate_export_pdf`（类级调用） | `application_cover_letter.py`:954；`application_materials.py`:550；`application_worker.py`:7832；`application_prism_review.py`:103 | MC-19 保留（理由）：冻结的 v1 生产者副本 `tests/fixtures/cover-letter-v1-producer.py` 以此名调用；改名需改动封存副本或叠加两个名字 |
| `application_resume_versions._content_template`（导入） | `application_experience_content.py`:337 | MC-19 保留（理由）：Resume 拆分出的内部文件，由 `ApplicationResumeStore` 调用，属 Resume Module 内部 |

审计 D2 的 `_read_version_file` 45 次、`_draft_document` 24 次包含 `application_resume_versions.py`
内部调用；该文件属于 Resume Module，故本表只列 Resume 之外的 18、16 处。`flow._load` 源码外部 23 处
与审计一致（Portal 8 处、其他 15 处）；MC-14 后 Portal 0 处，余 15 处归 MC-19；MC-19 后非拆分源码文件中外部 `flow._load` 为 0 处，拆分文件内的使用按 Module 内部登记。MC-08 行中 `flow.worker_action`、`flow.applications`、
`pipeline.flow/worker` 是公开名的穿透，按 MC-08 补充只要求新增控制不再穿透，保留者逐项记理由。

不分配收回票的跨文件私有使用：`application_match` 的 `_ModelOutput`、`_known_failed_model_result`、
`_model_failure_code` 被 Analysis 周边的 `application_match_refresh`、`application_job_brief`、
`application_retrieval`、`application_material_packet` 导入；`ApplicationRunner._live_guard` 被 Worker
内部夹具使用。它们由 MC-18 基线防止增加，是否收回待 MC-14/19 后再定。
