# 从 Gmail 推荐邮件自动取得岗位与原 JD

Type: task
Label: wayfinder:task
Status: closed
Interaction: AFK
Assignee: 01a146b9/root
Created: 2026-10-17
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [建立单岗位任务契约与持久恢复](01-task-contract.md), [修复原生父进程下 Codex CLI 的标准输入等待](17-native-cli-stdin.md)

## Question

如何让安装版 App 调用 Codex 读取 Gmail 中 LinkedIn、Indeed 等岗位推荐，自动取得原 JD，免去手动复制？

## Work and reuse

- 用户新增明确要求：自动化复制 JD 这一步，让 Codex 通过 Gmail 读取岗位推荐内容。主入口据此扩为推荐邮件取得岗位与原 JD，原 JD 输入保留为备用。
- 复用已连接 Gmail、现有 Codex CLI、ApplicationStore 的保存幂等和重复核验、当前 flow；不复制凭据、不新建邮箱账号或第二套岗位库。
- 邮件读取与 JD 匹配分阶段；推荐摘要不得伪称完整 JD。保留 message/thread ID、接收时间、原岗位 URL、正文完整性及取得来源；无法取得全文时显示待补齐/登录/失效状态。
- 对多岗位邮件逐条提取并按稳定岗位标识去重，已投递/已有任务保持可见，不能默认重新申请或覆盖原笔记。
- App 后台读取与提取使用短请求和状态观察；未连接/失效可恢复。邮件和页面内容为不可信资料，不得改写执行授权或触发投递。
- 新私有捕获及来源记录仅在外部私有运行目录。只读邮箱，不发信、不改标签、不归档或删除邮件。最终 Submit 仍由用户处理。

## Ownership

- `src/career_evidence_graph/application_recommendations.py` 与合成专项：`01a146b9/source_bundle`。
- Codex/Gmail 实际读取适配、HTTP、原生装配及 App 入口由根执行者协调；现有来源和简历模块不得被本票回退。

## Acceptance criteria

- [x] 安装版 App 可以从已连接 Gmail 取得当前推荐岗位，不要求用户复制邮件或 JD。
- [x] 邮件摘要与原 JD 全文区分明确；进入匹配的文本有可核验来源及完整性。
- [x] 多岗位、重复推荐、既有申请、未连接、失效页面和不确定保存结果有测试及恢复边界。
- [x] 真实 Gmail 读取和 App 内业务操作分别验证；邮箱写入、自动投递为零。

## Verification and evidence

纯解析、来源绑定与幂等使用合成邮件；真实 Gmail 与页面只在私有目录保留。当前聊天能读取邮箱，不等于安装版子进程已接通；关闭必须有实际装配与读取证据。

## Resolution comment

2026-10-17：按用户新增要求建立，来源/纯数据模块先行领取。当前尚未验证安装版 Gmail 通路，未声称实现完成。

2026-10-17 纯数据与私有持久化移交，票据保持 open：

- [RecommendationStore](../../../src/career_evidence_graph/application_recommendations.py) 提供 `import_messages(messages, jobs, *, page_captures=[])`、`snapshot()` 与 `select(id, revision)`。根执行者负责实际 Gmail/Codex/JD 页面读取和 App 装配。本模块不执行网络、模型、浏览器或邮箱操作。
- `normalize_message` 保留 message/thread ID、接收时间、发件人、主题、正文完整性和链接；使用标准库 HTMLParser 转成惰性文本、跳过 script/style、去零宽追踪字符，不加载图片或资源。snippet 始终是 excerpt；邮件文字不能触发申请或扩大授权。
- LinkedIn `/jobs/view/<id>`、`/comm/jobs/view/<id>`、`/email/jobs/view/<id>` 复用确切数字 ID；Indeed 只接受明确且不冲突的 16 位 `jk`/`vjk` 标识。其他 URL 复用现有 `application_key`。跨邮件重复推荐合并但追加每封原始来源；跟踪 token 不作为岗位 ID。
- 邮件与页面原捕获按内容 hash 追加到外部 `private_root`，文件为 0600；不覆盖旧捕获。`full` 必须绑定实际完整邮件正文或 `page_capture` 的 URL、正文、available 状态及显式完整性；正文空白规范化后必须包含所用 JD。不能核验则降为 excerpt/unknown。选中前再次回读实际捕获并检查 hash；原件漂移、不可读或摘要均停止选岗进入匹配。
- `select` 仅在明确选择 full JD、来源和 CAS 一致后调用 `ApplicationStore.create_application`，使用岗位身份派生的稳定 32 位 request_id。既有确切岗位申请直接返回且不改写；相同公司岗位但缺链接的历史记录显示为 possible_applications 并要求重复核验。推荐本身不创建申请。
- 保存前写私有 pending 日志。保存失败先查已有申请：已找到则复用并报告 reconciled；仍不明确则保存 needs_recheck，重启后也不自动重放创建。`snapshot` 显示 saved/unselected/needs_recheck。导入及选择复用 ApplicationStore 可重入写锁；并发导入保留全部邮件来源。后来的摘要不覆盖已捕获的完整 JD。
- [合成专项](../../../tests/test_application_recommendations.py) 共 **41 项通过**。与 `test_career_portal_data.py`、`test_application_automation.py` 联合运行共 **177 passed**。验证命令：`UV_CACHE_DIR=/private/tmp/tomorrowstar-single-job-uv-cache uv run --locked python scripts/run_pytest.py tests/test_application_recommendations.py tests/test_career_portal_data.py tests/test_application_automation.py -q`。覆盖多岗位、重复推荐、多邮件、既有已投递与缺链接记录、失效/登录页面、完整来源绑定、恶意邮件文字、未知保存、跨实例并发、状态损坏、符号链接和原捕获漂移。两文件 Ruff check/format 与 `git diff --check` 通过。
- 本次移交代码基线为 HEAD `e4a26d0c24311d014d478f7f92e58a88e6709b4b` 加保留的 dirty 工作区。`application_recommendations.py` SHA256 `6198194ddf525e45c075e258abde72758cfa6fe6b2668f5e525fafbf54408440`；专项 SHA256 `b2816de84064ff52e44daf55d2ea7044b1d8e3e9a50376ac3daf055a17cb6335`。
- 尚未验证安装版 Gmail 通路、真实邮件读取、真实页面或 App 内业务操作；本次没有读取真实邮箱、写邮箱、启动浏览器、执行投递或 Submit。后续装配与真实验收不得用本次合成通过代替。

2026-10-17 独立审计后的来源完整性与岗位身份修正：

- 审计复现了两处未被此前 177 项覆盖的缺陷：捕获全文的任意前缀可能被标为 full，漏掉资格尾部；岗位 A 的捕获可能绑定到目标岗位 B。上述历史通过记录不代表本次修复验收，保留为前一输入版本的证据。
- 新增反例先 RED，再将 page/mail 的 full 规则改为规范化空白后的**全文相等**。`jd_scope=captured_body` 明确所用范围；不能截取前段而忽略 German C1、工作许可或其他尾部条件。选岗时回读捕获并重验，因此旧持久 full 记录也不能绕过新规则。
- `body_completeness=full` 只表示邮件读取完整。普通推荐默认 `body_scope=message`，即使模型把整封短摘要原样声明 full，仍降为 excerpt。只有可信来源已明确 `body_scope=job_description`、正文全文等值、岗位身份一致时，才允许 mail full；模型选材不能升级邮件 scope。
- 页面绑定核验原邮件岗位 → capture.url → 连续有效 3xx redirects → final_url。目标 `job.url` 的 canonical 身份必须等于 final_url；取得来源可以是捕获 origin/final。缺跳链、断链、错源和把最终岗位正文写回旧 origin 身份均保持 excerpt，不能选择。原 mail_url 单独保留；没有取得链证据的外部 apply_url 不充当 JD 身份。
- 新增 13 项回归（裁尾、错目标、跳链、旧 full 记录、整封短摘要 scope）。当前推荐专项 **54 passed**；与 `tests/test_application_job_source.py`、`tests/test_career_portal_data.py`、`tests/test_application_automation.py` 联合验证 **244 passed**。两文件 Ruff check/format 与 `git diff --check` 通过。所有检查仍为离线合成；未执行真实 Gmail/App/浏览器或提交。
- 本次修复移交 `application_recommendations.py` SHA256 `9da8b95349e130d4b6dc98317b47390d98c2901bec14e45c3ef4419284e2a532`；专项 SHA256 `9f9b0c366e76a16d051e7bd32cc9fe2b14bbeb7a84c1837e265af78184bbcd4a`。票据仍 open，实际安装版与 Gmail 读取验收由根执行者继续。

2026-10-17 根执行者接手后台与 App 整合：

- 已接入异步 Gmail 读取、原岗位惰性抓取及 HTTP 刷新/选岗入口。真实只读 HTTP 预检已验证 Codex 子进程能调用连接器搜索和读取邮件；原申请记录未变化，未选岗或触发匹配/填写。私有证据仅保存在外部私有运行目录。
- 当前预检暴露 Indeed 地区推荐路径识别缺口，正在补合成反例及最小修复。邮件可读不等于取得全文；安装版入口、真实原 JD 和 App 内操作仍待验收。
- 独立审计发现关闭读取器后可能在队列边界启动新读取，正在修复。票据保持 open。

2026-10-17 来源解析与后台原 JD 预检增量：

- 修复 Indeed 精确 `/rc/clk/dl` 推荐路径，保留合法原地区域名；取消订阅、assessment 和未知跟踪路径继续跳过。关闭后 admission 拒绝新的 Gmail/页面 IO；已经开始的 IO 不阻塞退出，返回后不再抓取下一页或导入中断任务。独立恢复 guard 已复核。
- 对没有 JSON-LD 的 LinkedIn 公开岗位增加结构受限的 DOM 提取：最终岗位 ID、canonical 与 og:url 一致，唯一且闭合的岗位标题、公司及描述容器，保留完整描述、尾部硬条件、地点和岗位条件。JSON-LD 身份拒绝、缺结构、截断、登录或失效不能降级绕过。相关来源/推荐/读取专项 **177 passed**，Ruff 与 diff 检查通过。
- 后台已用真实连接器读取并保留的推荐邮件，结合新鲜公开页面取得完整原 JD；没有要求用户复制正文。需要登录的页面保持 unknown/login_required，不采用摘要评分。旧申请记录字节版本保持；未选岗、未启动匹配或填写，邮箱写入与 Submit 为零。私有原件、来源链与回读仅在外部私有目录，具体身份和派生统计不写入本票。
- App 工作台已进入合成浏览器验证；安装版读取与 App 业务验收尚未完成，本票仍 open。

2026-10-17 安装版首次实际读取：通过原生窗口触发推荐刷新，调用超时并显示邮件连接暂不可用。原诊断没有 Gmail 工具事件，CLI 等待读取附加标准输入；失败原件保留在私有位置。第 17 票已用开放父管道的实际离线子进程稳定复现并做最小隔离修复，仍需新安装版再次通过窗口读取。本轮失败没有导入/选岗、改邮箱或填写，不把此前聊天/后台预检替代为本票通过。

2026-10-17 关闭：第 17 票修复的新安装版由原生窗口再次触发 Gmail 刷新，界面显示推荐已载入；完整岗位可选择，无法获取或需登录者保持未知且不可选择。原生窗口展开核对了邮件来源、取得时间、原岗位链接与 JD 范围。实际子进程的完成事件只有 Gmail 搜索和读取，公开页捕获与完整性链已回读。没有要求用户复制邮件/JD。

[当前安装及源码绑定](../assets/native-cli-fix-source-binding.json)、[包内验收](../assets/native-cli-fix-package-acceptance.json)及[原生 Gmail 脱敏验收](../assets/native-gmail-intake-acceptance.json)。原始邮件、页面、工具事件、岗位身份/数量与具体运行指纹只保存在外部私有回执。原申请及旧运行逐文件字节/权限回读一致；App 正常启动重新序列化了等价配置，原始与当前字节均已私有保留，配置值相同。邮箱写入、选岗、真实填写及最终 Submit 均为零；本票通过不代表第 11 票真实岗位链已通过。最新完整离线 **1974 passed、151 deselected**，来源、未知状态、去重及恢复反例继续由专项与整体验证覆盖。
