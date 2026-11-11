# 核对当前安装候选的完整材料准备链

Type: task
Label: wayfinder:task
Status: closed
Triage: done
Closure reason: completed
Completion: installed-synthetic-full-latex-journey-verified
Priority: P1
Interaction: AFK
Assignee: 01a150ef/root
Created: 2026-10-18
Updated: 2026-10-19
Parent: [交付 Gmail 岗位筛选与专用简历稳定版](../map.md)
Blocked by: [核验既有资料覆盖与单岗选择依据](17-source-coverage-and-job-selection.md)、[确定完整 LaTeX 简历的生成与事实审核契约](18-full-cv-review-contract.md)、[按实际原因显示资料准备状态](20-source-readiness-reasons.md)、[绑定完整源与新 PDF 并单独确认材料](23-confirm-reviewed-latex-pdf.md)、[补齐安装候选的完整 LaTeX 合成旅程入口](24-installed-full-latex-synthetic-entry.md)

## Question

原完整准备链与后续 Prism／已有 LaTeX／刷新优化的证据，是否覆盖同一当前安装候选和已选产品路径？若没有，只需补哪些组合、冷恢复或性能检查，才能交给真实人审？

## Existing evidence

- [在安装版运行完整合成准备流程](14-installed-preparation-acceptance.md)在其冻结候选下已通过，保持关闭；不追改其当时结论。
- [独立 Prism 回读](../../prism-readback-installed-2026-10-18/README.md)、[保存源变化提示](../../prism-autodetect-installed-2026-10-18/README.md)和[已有 LaTeX 岗位导出](../../existing-latex-installed-2026-10-18/README.md)已有各自安装证据。
- [刷新优化](../../preparation-refresh-installed-2026-10-18/verification.json)与[历史制品查询](../../artifact-query-installed-2026-10-18/verification.json)已有后继安装检查。加载后 HTTP 测量不能代表冷启动首屏，也不代表人审接受。

## Completion gate

- [x] 先按源码、包内资源、实际加载、配置与路径建立证据矩阵。可复用的证据说明其版本和范围；不默认重跑旧完整套件，不把最新报告名当作同一候选证明。
- [x] 对照已选完整 CV／事实审核契约，只补尚未覆盖的组合路径；若需要实现，先补明确前置票，不在验收票中默造新方案。
- [x] 覆盖来源与草稿／LaTeX／PDF绑定、改后失效、历史保留、明确读取／导出、未知结果回执核验，以及退出／冷重开不自动执行。已覆盖路径以相容性证据复用。
- [x] 区分冷启动首屏、加载后刷新和制品读取；首次读库是否达到本次可用要求须有实际测量，未测保留未知。只有具体瓶颈证据才能新增优化票。
- [x] 仅在获准且必要时使用隔离合成安装验证；具体真实材料、模型、编译或原生状态操作继续核对原授权。禁止消费旧 intent、恢复暂停申请或重传附件。
- [x] 写出可供真实人审的候选与剩余限制，公开报告遵循[数据边界](../../../docs/data-boundaries.md)：只保留允许的布尔结论，私人数据、测量和指纹留私有。

## Ownership and boundaries

先核对全部直接前置、唯一领取人及决策新增的实现票。本轮仅建票，未安装或运行验证。此票验证材料准备路径；真实字段／附件回读继续由[通过 App 用 Gmail 真实岗位验证至人工提交前](../../single-job-application-flow-2026-10-16/issues/11-gmail-real-job.md)持有。工程通过不关闭任何 HITL。

## Resolution comment

未解决。需要核对证据组合范围，不预设当前候选失败。

### 2026-10-18 — Source audit follow-up

[核验既有资料覆盖与单岗选择依据](17-source-coverage-and-job-selection.md)已产出来源范围、归属和选岗比较边界的私人核对结果；历史分析与当前整个来源版本不一致，技术导出不能代替新分析或事实接受。将已复现的[按实际原因显示资料准备状态](20-source-readiness-reasons.md)接为前置，只修原因显示并保留未读范围。当前整链票尚未执行。

### 2026-10-18 — Readiness reason fix completed in source

前置[按实际原因显示资料准备状态](20-source-readiness-reasons.md)已完成源码及合成验证，原状态及全部守卫保持，见[源码验证](../../source-readiness-reasons-2026-10-18/README.md)。安装版尚未更新；本票后续冻结候选时纳入该源码，复用既有HTTP和离线结果，按实际版本缺口补安装组合证据。该时点完整CV契约尚未解决；后续确认及实现前置见下，不自动领取或执行本票。

### 2026-10-18 — Full CV contract resolved; implementation chain pending

[确定完整 LaTeX 简历的生成与事实审核契约](18-full-cv-review-contract.md)已由用户五轮答复确认并结案。新增[完整岗位LaTeX生成](21-generate-full-latex-job-version.md)→[Prism分组事实审核](22-prism-grouped-factual-review.md)→[完整源与新PDF材料确认](23-confirm-reviewed-latex-pdf.md)依次实现，本票直接等待末票，前两票为传递前置。保留原资料核验、契约与原因提示依赖；本票仍未领取、未执行，安装、真实人审及真实申请门槛不变。

### 2026-10-18 — Complete LaTeX generation completed in source

[完整岗位LaTeX生成](21-generate-full-latex-job-version.md)已结案，源码及合成证据见[本次报告](../../full-latex-generation-2026-10-18/README.md)。安装版未更新；本票冻结后续候选时纳入该源码及既有原因提示修复，检查实际包内、加载与组合范围。Prism分组审核和新PDF确认仍未实现，本票继续等待既有实现链，不自动执行安装或真实人审。

### 2026-10-18 — Grouped Prism review completed in source

[Prism分组审核](22-prism-grouped-factual-review.md)已完成源码及合成验证，包含精确未变继承、未知回执和历史，见[交付证据](../../prism-group-review-2026-10-18/README.md)。后续候选需纳入此源码；原安装证据不自动覆盖新路径。当前仅[完整源与新PDF材料确认](23-confirm-reviewed-latex-pdf.md)仍为未完成的实现前置。本票保持未领取，不执行安装或真实材料接受。

### 2026-10-18 — Complete-source/PDF confirmation completed in source

前置[绑定完整源与新 PDF 并单独确认材料](23-confirm-reviewed-latex-pdf.md)已完成源码、实际store合成整合、HTTP、界面及完整默认离线验证，见[交付证据](../../full-latex-pdf-confirmation-2026-10-18/README.md)。生成→分组事实审核／精确未变继承→严格同源PDF绑定→具体材料独立确认的源码链已接通。封存`group_review`与任务`material_reviews`可作为候选组合核对的已有证据。

本票保持open／none，全部直接源码前置现已closed；下一步仍先比对源码、包内、实际加载及配置，只补当前候选缺口。不能把本轮合成user回执当作真实内容接受，也不能把源码通过当安装验收。本轮未领取或自动执行本票，真实申请继续暂停。

### 2026-10-18 — Claim and bounded evidence audit

用户授权开始本票，核对全部直接前置已closed且未领取后，由`01a14fd0/root`领取。先建立源码、包内、加载、配置及路径证据矩阵，复用已有确认和验证，只补具体缺口。仅使用隔离合成资料；不读真实邮箱／职业正文、不启用真实模型／Prism、不消费旧intent或修改既有真实运行。若发现必须实现的缺口，先建明确前置票；真实申请继续暂停。

### 2026-10-18 — Evidence matrix established; explicit implementation prerequisite

[本轮证据矩阵](../../current-candidate-journey-2026-10-18/README.md)已完成，当前公共源码基线已冻结并复核。最新PDF绑定候选相关文件、原因提示及生成核心仍匹配；保留既有源码／合成证据，不重复全套运行。只读检查现有安装包后，没有包包含当前完整链的全部所核对源码。实际加载、隔离运行配置和新链冷重开仍未验证；当前冷首读、加载后刷新和制品读取测量未知，未发现可据以建优化票的瓶颈证据。

新链的现有合成入口缺少完整底稿、完整生成schema和隔离Prism打开／编译替身；直接执行可能调用真实客户端。实际加载指纹也需直接覆盖两个新模块的函数，不能只凭导入时源码摘要确认。按本票“若需要实现，先补明确前置票”门槛，新增并连接[补齐安装候选的完整 LaTeX 合成旅程入口](24-installed-full-latex-synthetic-entry.md)，范围和验证责任均已写明。该前置仅提供安全入口及加载身份能力，实际安装组合验收仍由本票持有。

本票未解决，保持open并释放领取，明确等待新前置，不将建票当作实现或验收完成。原关闭票不重开，原三项HITL与旧申请owner不变。公开报告仅保留允许的布尔结论；详细指纹、配置定位和核对记录已保存在私有证据区。没有启动安装运行或真实资料／模型／Prism，真实申请继续暂停。

### 2026-10-18 — Safe full-LaTeX synthetic prerequisite completed

[补齐安装候选的完整 LaTeX 合成旅程入口](24-installed-full-latex-synthetic-entry.md)已完成源码、实际CLI／原生合成后端／HTTP及完整默认离线验证，见[当前冻结候选证据](../../installed-full-latex-synthetic-entry-2026-10-18/README.md)。完整底稿、确认资料、schema替身、隔离Prism打开／编译及加载身份覆盖已具备；改组继承、新PDF独立确认、未知结果停止和EOF／SIGTERM恢复已有源码组合证据，可据实际相容性复用。

本次共享Portal与store源码有最小接线修改，当前字节以该新冻结候选为准，不能再把旧PDF绑定报告的共享文件声明直接当作当前候选。早期RED的旧回调本机只读连接尝试已留档，未进入编译，不作为安全通过。

全部直接前置现已closed；本票保持open／none，可领取，不自动执行安装。下一步仅补独立包内／实际加载／隔离配置及原生窗口整链、冷启动首读和必要分阶段测量；固定PDF不替代真实编译或版式接受。原三项HITL和真实申请暂停保持。

### 2026-10-18 — Installed full-chain execution claim

用户明确授权执行本票，完成当前候选安装整链验证。五个直接前置已closed且原票未领取；由`01a150ef/root`领取。使用独立安装身份、全新合成目录及明确`--synthetic-preparation`参数，复核包内／实际加载、完整源与分组审核／具体PDF、改后失效／历史保留、未知回执及退出／冷重开，分别测量冷首读、加载后刷新和制品读取。复用相容源码证据；真实申请、真实邮箱／模型／Prism／ATS及原暂停任务继续保持原边界。工程结论不代替任何HITL。

### 2026-10-19 — Independent installed full-chain acceptance completed

用户授权范围内的当前候选合成安装整链已完成，见[独立安装验收](../../material19-installed-journey-2026-10-19/README.md)及[固定布尔结果](../../material19-installed-journey-2026-10-19/verification.json)。冻结源码、包内引擎／原生辅助入口、实际加载函数及服务资源已对应；原生窗口完成完整LaTeX生成、同源预览、逐组确认、正式源／PDF绑定及具体材料逐版独立确认。改单组后旧材料确认失效、未变组精确继承、历史源与PDF保留；新PDF即使固定字节相同也未继承旧批准。

正常退出及同目录原生冷重开后，会话改变而任务、历史和保存文件字节／修改时间保持一致，没有自动执行阶段或启动worker。未知回执另以同包实际store及固定客户端验证跨重建保留、捕获／核验拒绝重放；不将该项写成原生UI未知恢复。冷后端首次合成资料读取、加载后刷新和历史制品读取分别实测；原生窗口已呈现，精确首屏绘制与真实资料规模未测。当前小型合成读取可用，不据此接受真实使用体验或新增无证据优化。

产品源码未修改，严格候选一致性支持复用本线程完整默认离线及相容的既有机制证据。最终严格签名、候选退出／端口关闭、原App指纹及原真实运行目录元数据保全通过；元数据核对不冒充全量正文／字节验证。独立审查已通过，公开报告仅含其批准的固定Boolean字段，详细指纹、测量、截图、回执、脚本与失败记录保持私有。

首次LaunchServices因日志目标失败、环境探针换行解析及派生测量字段修正均保留原记录和后继验证；没有产品代码修复或隐藏首次失败。合成材料确认由代理执行，只是工程测试状态，`actor=user`不代表用户已接受真实材料。固定PDF不证明真实LaTeX编译或版式质量。

本票仅技术结案；[真实推荐与材料复核](15-real-preparation-pilot.md)、[准备版接受](16-release-closeout.md)及浏览器体验HITL保持open／needs-info／none。旧真实单岗票及其owner保持，未启动后继、未读取真实邮箱／职业正文、未调用真实模型／Prism／ATS、未恢复申请或上传附件，最终Submit仍由用户操作。
