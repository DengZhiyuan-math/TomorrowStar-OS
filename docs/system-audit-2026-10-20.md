# 系统流程与冗余审计 — 2026-10-20

## 结论与依据

现有系统具备推荐读取、来源保存、匹配分析、材料生成、部分 ATS 填写上传及断点记录。它尚未实现用户确认的持续线性投递闭环。主要问题是：旧研究评审、受限试验授权、安装诊断与日常业务混合；功能由多条备用流程承接；主编排没有正确执行所有匹配路由、连续下一岗及手动 Submit 后的自动结果观察。

整改依据是本次逐项确认的[APP-01–18](single-job-flow.md)，以最新版本为准。重要缺事实、冲突或未知结果停当前岗；不继续其他岗位，也不集中到最后问。只有推荐邮件收录可在等待时继续。最终 Submit 由用户操作。

本次已经完成文档修订与[开发重规划](development-plan.md)，**尚未修复运行代码**。目标规范、现有代码事实、历史试验和真实申请结果分别标明。

## 审计范围与证据强度

基线 HEAD：`e4a26d0c24311d014d478f7f92e58a88e6709b4b`。审计包括当前 staged、unstaged 和 untracked 实现，不能只用 Git diff 表示范围。

| 层面 | 实际检查 |
| --- | --- |
| 产品与研究范围 | AGENTS、README、PROJECT、REQUIREMENTS、ROADMAP、STATE、CONTEXT及Phase 7/8当前导航 |
| 邮件与来源 | Gmail connector设置、查询、分页、原邮件/推荐/JD持久顺序、去重与归档能力 |
| 分析与材料 | 匹配公式和路由、引用降级、学历/资格、完整LaTeX与主流程、PDF复用及附加材料 |
| 两库和更正 | CareerCatalog、信息库、worker答案匹配、入库位置和资料变化传播 |
| 浏览器与人工交接 | 原页、适配器、通用控件、网络grants、上传、人工编辑、Submit边界和结果记录 |
| 持续与恢复 | pipeline/flow/worker状态、总时限、单岗追加、显式等待、重开、未知动作和skip |
| 原生App与配置 | 实际权限、签名维护、readiness/lease/epoch、无关配置故障范围、UI交互和轮询 |
| 计划与验收 | 本地全量tracker查询、18张原开放票及其依赖、已关闭旧契约与重复验收链 |
| 已安装资源 | 13个关键Python模块及server/background_check与checkout逐字节相同；不据此宣称当前运行进程加载版本已验证 |

文档修订开始前记录工作树哈希；完成时复核运行源码、脚本、测试未改变。已安装资源比对为文件证据，不是完整真实浏览器验收。没有为本次审计读取真实邮件、改邮箱、调用生成模型、填写上传或提交申请。

## 实现发现与处置

下表的行号指本次未改的源码基线。票据承接与实际先后关系以开发计划为准。

| 发现 | 当前证据和影响 | 目标处置 / 承接 |
| --- | --- | --- |
| A01 有界单轮代替持续队列 | [pipeline](../src/career_evidence_graph/application_pipeline.py) L490固定1200秒；L703读3封/10候选；L763只取最高分一个；L995在ready_for_review停止。没有手动提交结果到下一岗闭环。 | APP-02/03/12/16；34、35、37。API分页可有页大小，不能成为总限额。 |
| A02 邮件收录和JD获取耦合 | [intake](../src/career_evidence_graph/application_intake.py) L947–980在本次候选获取完整JD后形成链；[gmail](../src/career_evidence_graph/application_gmail.py) L22–39限定7日LinkedIn/Indeed只读工具，没有label/archive。 | APP-01；35。先保存原邮件、条目、链接再标记归档，完整JD逐岗处理。处理账与已读状态分离。 |
| A03 已有路由未被主编排完整采用 | [screening](../src/career_evidence_graph/job_screening.py) L69–107有manual/hold等语义；pipeline选择分数最高条目后没有完整分派。隔离探针中manual高分及0分样本均进入filling。 | APP-06；34。普通自动、高价值初稿后精准人工、过低跳过；复用分数含义，不虚构已有数值阈值。 |
| A04 两库未形成统一事实复用 | [worker](../src/career_evidence_graph/application_worker.py) L591–624只匹配confirmed答案与固定fact/options；CareerCatalog只读。补充内容没有按职业事实/申请答案路由写回。 | APP-04/05；36、23。职业事实以职业库为准，明确更正直接保存来源和历史；答案信息库复用。 |
| A05 未知问题一律待答 | worker固定别名与browser必填字段规则将无适配答案视为缺失，包括低影响叙述。语义适用与重要性判断不足。 | APP-05；36、34。先查两库，自主处理动机和普通叙述；重要未知事实才停。 |
| A06 主材料路径能力较窄 | [resume](../src/career_evidence_graph/application_resume.py)保留4项摘要路径，完整LaTeX能力在备用preparation；[browser](../src/career_evidence_graph/application_worker_browser.py) L1631–1636拒额外必填附件。 | APP-07；34、20及材料25。复用成熟完整材料能力，不另造生成器；普通稿自动检查。 |
| A07 全局变化使有效结果失效 | [portal](../src/career_evidence_graph/career_portal.py) L254–278使用全局源/config身份；[flow](../src/career_evidence_graph/application_flow.py)的_fresh/update_inputs以整体输入比较清除材料。 | APP-15；36、34。实际影响依赖，保留用户版本及无关结果，模型设置变动不自动废弃成品。 |
| A08 人工交接需重复确认 | worker L1545–1600有review、reclaim、handoff_source、acknowledge；之后仍需resume。 | APP-10；37。人工修改保留，一次继续读取现状后完成剩余操作。 |
| A09 提交记录依赖人工二次声明 | worker L1514–1542要求submitted acknowledge，再提供receipt locator；pipeline没有成功观察后续队列推进。 | APP-11/12；37、34。用户仅操作最终Submit，系统观察明确结果；不明才问。 |
| A10 通用浏览器仍是受限执行器 | 固定字段/控件与部分Cua combobox支持存在，但缺通用导航、动态问题和多步规划。平台、上传和网络初始化限制会停止。 | APP-08/09；18、20、33。有适配复用，无适配自主浏览器处理，不以平台名单判定可否继续。 |
| A11 请求白名单成为业务审批 | browser L825–835未知写请求会标记unverified_send_path，阻后续读取；[hosted_ats](../src/career_evidence_graph/hosted_ats.py)/[ashby_drafts](../src/career_evidence_graph/ashby_drafts.py)使用精确grants。 | APP-08/11/17；18、20、33。正常读取、草稿保存和上传不逐请求批准；最终Submit单独禁止自动执行。 |
| A12 正常重开也全部变暂停 | pipeline L351–353及L1018–1027将运行流程变interrupted；旧材料批次也规定重开不自动续。 | APP-13；27、34。依据断点及当前结果恢复，显式暂停/等待保持等待，不能把进程中断一律当未知写入。 |
| A13 单一worker绑定挡住下一岗 | pipeline _materials拒已有活动任务/原页/intent；worker _prepare排斥原批次。单岗追加回归实际报batch_exists。 | APP-03/14；34、37。区分等待中当前岗、保留历史岗和可新建下一岗；skip不需清空原记录。 |
| A14 安装证明覆盖每次业务写 | [readiness](../src/career_evidence_graph/application_readiness.py) L59–110把包、UI、host、输入、材料、commands等证明套在prepare/resume/recheck/answer/library/heartbeat；portal还影子推演实际mutation。 | APP-17；28。保留实际能力、互斥和原子性；安装完整性为维护诊断，不作每步入库或继续的审批。 |
| A15 成功权限检查使租约失效 | server每次检查递增native epoch；portal L1340要求旧lease epoch一致。隔离探针两次均verified/权限true但epoch1→2，旧lease失配。 | APP-17；28。成功检查不能停止健康执行；只在实际能力变化影响当前操作时处理。 |
| A16 每动作反复扫描全部输入 | browser check_inputs与授权路径经single_binding重新读库、分析、PDF和配置；本地几秒租约再叠加页面时效。 | APP-15/17；28、36。缓存已验证未变依赖，检查与动作相关事实，移除无关全库门。 |
| A17 单条来源错误扩大到全库 | resume/source_reuse仍有retained_material_sources及resume_reuse_invalid整体失败路径；协作归属过滤可能排除整个贡献。 | APP-18；36、34。错误局部标记；按可证明的责任范围改写，不能用“不是全由用户完成”一概丢弃。 |
| A18 局部网络错误锁住整个控制台 | [application_flow.js](../src/career_evidence_graph/portal_static/application_flow.js) L60以uncertain禁用全部写操作；L1425任何无status/5xx均置uncertain，后台读取成功也不清除，需手动refresh(true)。暂停与收录入口被同锁覆盖。 | APP-03/13/16/17；34。结果核对限定实际动作；暂停始终可操作，不把无关动作或邮箱能力一并锁死。 |
| A19 轮询重建使键盘焦点丢失 | application_flow.js L262 replaceChildren；L1375–1383只恢复answerKey输入；L1418每1.2秒刷新。普通控制按钮的焦点未保留。 | APP-10；34、浏览器09。原位更新或恢复稳定焦点，不以轮询打断人工操作。 |
| A20 无关备用配置阻启动 | [App.swift](../macos/App.swift) L418–429默认申请模式仍验证preparation_root；[server](../macos/server.py) L420–423及806–808中显式Codex路径失效使整个服务退出，连已存材料浏览受阻。 | APP-17；28。只让实际依赖该能力的操作报错，保留查看和修正配置入口。 |
| A21 UI请求无超时 | [app.js](../src/career_evidence_graph/portal_static/app.js) L121–126没有fetch/JSON超时；flow.js L1422–1427保持busy，控制按钮均禁用。 | APP-16；34。为具体操作超时与提示保留控制入口，不能无限等待并禁止暂停。 |
| A22 查看当前岗后失去进度跟随 | flow.js L288调用openTask；L1442总设followingPipeline=false且无恢复入口；L1395自动下一岗选择依赖它。 | APP-03/12；34。区分查看历史与跟随当前岗位，真实进度持续可见。 |
| A23 收录与操作入口未分离 | flow.js L264、327–330混合邮件与完整JD进度；L366/369在intake.running时阻打开已有任务；没有真正的skip/return控件及分开的保存/标签/归档结果。 | APP-01/03/14；35、34、37。持续收录不能挡查看当前岗；提供可恢复跳过与分步补做状态。 |

A18–23是本轮补充的UI和配置故障范围发现；其余结合前两轮源码与文档审计复核。没有把“存在历史安全测试”直接等同于运行门槛；每项运行问题都有实际调用路径或可复现证据。

## 已有修正与可复用能力

不能把旧问题一概记为仍未处理。当前源码已经有这些改进：

- 引用校验可按对应requirement降级为unknown并继续（[match](../src/career_evidence_graph/application_match.py) L670–705）；剩余全库来源失败路径仍见A17。
- 已取消学历关键词硬拦，资格unknown不必在分析/材料阶段一律等待；真正必要未知事实另处理。
- 主申请路径已有自动绑定当前生成PDF的分支（flow L2186–2214），不能声称所有普通岗位目前都必须人工接受PDF。逐组/PDF审核主要仍在备用流程和旧文档中。
- 匹配分数、来源归属、答案作用域、上传回读、原页观察及最终Submit限制都有现成代码。改造应复用这些能力，不重写整个系统。
- 职业能力研究的Grill-Me评审不应被取消，也不应作为日常投递的默认入场条件。

## 文档与计划发现

| 冲突 | 本次修订 |
| --- | --- |
| 顶层只宣布研究v1.1，产品被列为研究完成后的未来工作 | PROJECT、AGENTS、README、ROADMAP分开当前申请产品与研究范围。完整研究仍未被宣称完成。 |
| REQUIREMENTS禁止邮箱变更、每份材料及目的地另确认 | 引入APP-01–18，明确收录后label/archive和普通申请自主推进；最终Submit仍人工。 |
| CONTEXT要求缺信息继续别岗、人工声明submitted、每个未知问题待答 | 词典改为严格当前岗等待、可跳过、系统结果观察、重要性与语义判断。 |
| README同时称默认材料准备和默认自动投递 | 保留实际默认入口及其实现差距，备用材料准备独立说明。 |
| workflow/Prism把逐组、逐PDF、逐导出批准当主流程 | 主流程采用自动材料检查；高价值草稿后精准调整，研究及自选审阅独立。 |
| native/generic把包/请求/版本矩阵和固定时间窗写作长期产品契约 | 改为现存实现差距或历史诊断；当前产品以实际能力和操作结果决定等待。 |
| Phase8仍导航旧Phase7失败验证和已替代custody设计 | 当前导航改为MVP addendum和后续验证，保留旧报告历史。 |
| tracker以历史根因/完整证明链阻塞控件、上传和真实验收 | 复用旧票重写当前范围及依赖，历史诊断独立；只新增35–37三个缺口任务。 |
| 开发工作流配置被误当App业务规范 | `.planning/config.json`仍是开发工具配置。research/plan_check/UI/API/security/human_verify等开关不证明每项在App实际执行。本次未修改机器配置；按变更风险选择必要检查，不再列为逐岗用户审批。 |

历史文档不整批重写：旧验收、旧截止窗口、旧失败和精确安装证据保留。活跃入口需指向本次规范，并明确旧机制的作用域。开发者可并行审计或实现不同模块，不代表产品已有岗位并发。

## 保留的最小可靠性边界

- 最终Submit由用户操作，自动执行者不能用点击、Enter、form.submit或最终网络请求绕过。
- 不编造个人事实；学历、实际团队责任和计划/完成状态正确保留。研究Skill分数仍需要其评审证据。
- 结果不明先核对，不盲重放可能已完成的外部动作；保留人工修改、来源、历史与断点。
- 本机实际OS权限、一个执行者互斥、原子保存、防重复和稳定单App维护继续保留。
- 个人记录与系统源码分开。公开发布仍有其单独边界；普通申请无需重复隐私审批。

没有要求取消事实核对、合并所有状态、把所有异常吞掉，或用“自动化”代替用户最终Submit。精确源码/PDF绑定可支持诊断和一致性核对，不能自动升级成每版本都要用户签字的流程。

## 验证记录与限制

以下运行验证来自本次目标前的连续审计阶段，保留其原始范围。文档修订阶段复核关键源码未改变，没有为纯文档再次运行整套业务测试。

| 验证 | 观察及边界 |
| --- | --- |
| Pipeline/intake/Gmail/screening默认离线选择集 | 250 passed。证明选中的现有契约，不证明新APP规范完成。 |
| hosted ATS/native/readiness/installed write admission选择集 | 11 passed，272 deselected。包含最终请求被阻止与旧epoch失配规则。绿测试中的旧限制也可能正是待改行为。 |
| 同邮件下一岗追加回归 | 1 failed，5 deselected；test_same_email_cycle_appends_next_job_and_preserves_waiting_page报batch_exists。此测试是前轮提前实现留下的未完成变更，本轮没有改它或修代码；34负责完成相应行为。 |
| 匹配与编排隔离探针 | manual/高分和0分样本仍filling；ready_for_review后tick不准备下一岗。不是现实申请。 |
| 权限epoch隔离探针 | 两次权限成功仍使旧epoch不匹配；使用测试host与临时目录，不操作真实App权限。 |
| 已安装资源比对 | 13模块加server/background_check全部相同。没有验证实时进程、实际页面或真实ATS提交成功。 |
| tracker重规划前刷新 | 120总票，18未关闭：15open、3claimed。33/34缺Blocked by，已有历史owner未知；本次补当前依赖而不虚构旧owner。新增35–37后数量以完成检查为准。 |

本次文档和票据检查结果见下方完成记录。它们只证明本次修订交付，不关闭开发、真实质量、用户体验或研究验收。

## 文档修订完成记录

- 已整理23项源码/流程发现与9类文档、规划冲突，全部对应当前规范及开发承接。
- 已统一APP-01–18，并同步顶层范围、词典、技术说明、工作流和相关历史导航。普通应用与研究评审的边界明确。
- 统一开发计划给出6步顺序、现有代码入口、证据缺口与验收条件；复用原票，仅新增35/36/37。
- 最终tracker查询：123总票、102 closed/resolved、21未关闭（18 open、3 claimed）；依赖错误0。原120票的Status和Assignee逐条比对未变，未虚构关闭或领取。
- 修改的94份Markdown已逐文件检查1540个本地链接、章节锚点、围栏、行尾空白；补齐原“限时执行”链接的兼容锚点，明确旧总时限已替代。Git diff whitespace检查通过。
- 332份运行源码、脚本和测试文件与本轮开始时的哈希完全一致，无新增或删除运行文件；既有未提交工作保留。
- 纯文档修订不重复业务测试，不触发模型、邮箱或真实申请操作。运行实现、真实闭环及用户体验按开发计划继续待实施/验证。

