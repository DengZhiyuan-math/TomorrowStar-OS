# 独立限制最终Submit并退役请求批准

Type: task
Label: wayfinder:task
Status: closed
Triage: done
Priority: P1
Interaction: AFK
Assignee: 01a15ab3/root
Created: 2026-10-20
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: none

## Question

如何在现有浏览器动作出口独立禁止自动最终投递，同时取消正常导航、草稿和上传对逐平台、URL及请求hash批准的依赖？

## Scope

依据[产品规范](../../../docs/single-job-flow.md)、[精简方案](../../../docs/development-plan.md)和[本轮审计](../../../docs/system-audit-2026-10-20.md)。本地图Notes沿用实施任务扩展；本次只发布票据，不领取、实施或关闭。已确认设计不再另设HITL批准。 本票拥有最终动作判定与请求批准退役；通用浏览器能力由[支持已观察到的通用ATS自定义必填控件](18-generic-ats-controls.md)负责，交接和提交结果由[一次继续人工交接并观察Submit结果和可恢复跳过](37-manual-submit-observation-continuation.md)消费本票限制。不能另建通用审批服务或第二个浏览器执行器。

## Acceptance criteria

- [x] 先在既有authorize/派发与网络路径建立独立最终Submit限制并通过回归，再撤除public/Lever/Ashby等逐URL、query和请求体hash批准。不能将_live_guard整体改为放行后再补限制。
- [x] 自动层不触发最终按钮、Enter、requestSubmit/form.submit、最终HTTP或混合GraphQL中的提交动作。普通Next、草稿保存、解析和上传可自动完成；不能仅凭按钮文字或POST方法判断最终投递。
- [x] 已确定的最终业务请求不会由自动执行者发送；确实无法判断某动作是否最终投递时停当前岗提示，不把所有未登记POST/query都当最终提交。
- [x] 人工接管后原页允许用户实际Submit；系统观察结果，不以新的网络限制挡住人工提交。
- [x] 保留当前owner、岗位/文件核对、先落intent、attempt归属、动作已发出及未知结果不重发记录。不能随authorize或grant函数整删。正常已确认失败与健康自动保存按实际结果处理。
- [x] 复用现有合成接收端验证普通Next/草稿/上传通过，自动最终动作计数为零、人工提交可成功；未知响应、网站重发及迟到结果不导致重复最终动作。测试不修改真实申请。
- [x] 列出退役的grant配置、批准参数和旧断言，保留适配器解析与结果识别；不承诺一次证明所有任意网站。

## Ownership and handoff

拥有application_worker_browser中的authorize/_live_guard/track_request相关职责和既有hosted_ats/ashby_drafts批准消费点及对应测试。运行检查票只移除包/lease证明，不能重复实现本票的最终动作判定。实际进入实现时与相关模块负责人协调函数范围；不是独自工作，不撤销他人修改。

## Out of scope

自动最终Submit、真实申请操作、全平台适配承诺、业务队列与主控重写、旧私人记录清理。

## Implementation started — 2026-10-20

用户已授权按当前spec开始系统精简。仅使用合成工作区实施与验证；保留既有材料、进度、人工修改和历史证据。最终Submit由用户操作。源码与测试恢复副本：`/private/tmp/tomorrowstar-simplification-20261020/before-source-tests-tickets.tgz`。

## Bounded implementation — 2026-10-20

已先加入独立限制，再退役请求批准消费点：

- `authorize`只接受既有`open/fill/upload`；没有自动最终点击、Enter、任意脚本或Submit派发动作。
- `_live_guard`与`track_request`独立拒绝已知Lever/Greenhouse最终业务路径，以及单个、混合和批量GraphQL中的已知最终操作。拦截先于普通传输规则，旧批准文件不能覆盖该限制。评论和字符串值不作为最终动作依据。
- 既有人工交接原页在网络限制之前放行。离线协议回归覆盖同一原页由自动执行禁止转为人工允许；不据此宣称已完成真实用户Submit或结果观察。
- Ashby按岗位身份选用既有适配器；理解单个已知根字段、表单/字段身份和当前答案/附件的语义后允许读取、草稿保存、定位和上传。查询格式、回读字段或普通变量声明变化不再要求哈希批准。上传地址来自已核对服务端handle，文件仍核对名称、类型和字节。
- Lever解析仍核对当前岗位来源、既有upload intent和所选PDF；公开account标识只需满足解析协议，不再查逐岗位批准文件。
- 保留`require_execution`、岗位/文件核对、先落intent、attempt/page/run归属、派发前消耗和持久历史防重复逻辑。保留未知保存/上传结果及原页，不自动重发。

退役的活动配置与参数：

| 旧项 | 本次处理 |
| --- | --- |
| `public-read-grants.json`及完整请求体hash | 不再读取；任意opaque POST不会因旧文件而获准。 |
| `lever-upload-grants.json`及逐job account批准 | 不再读取；`is_resume_parse`移除批准account参数。 |
| `ashby-draft-grants.json`、逐URL upload批准及`query_sha256` | 不再读取；`DraftSession`移除grant参数。 |
| `public_read_grants`、`lever_account_grants`、`load_grants`及runner批准缓存 | 删除活动加载与消费点；不删除或重写既有私人配置文件。 |
| 旧测试中的“批准缺失/错误即停止”断言 | 改为无需批准的已知读取/草稿/解析，以及旧文件不能放行最终或未知请求的行为断言。 |
| Workable诊断测试的`runner.public_post_reads.add(...)`及“无适配器时旧批准可放行”断言 | 移除已退役内部属性注入；用无效的旧配置文件验证有无Workable会话时未知请求都拒绝，保留`purpose=unknown`、`dispatch=not_sent`诊断。 |

验证：URL操作微调后的4个相关文件默认离线测试`181 passed, 56 deselected`；6个修改的源码/测试文件Ruff检查及格式通过。日志：`/private/tmp/tomorrowstar-simplification-20261020/submit-boundary-offline-final.log`。先前沙箱内Chromium启动以`SIGABRT / TargetClosedError`失败，未进入应用代码；记录在同目录`submit-boundary-browser-first-failure.log`。随后经自动审批允许的隔离、离线合成Chromium接收端回归及两个具体失败的诊断结果见下文，未操作真实ATS或已有浏览器。

最后的出口审计还复现并修复了URL参数中的已知最终操作：通用页面打开时，`GET ?op=ApiSubmitSingleApplicationFormAction`现在独立拦截；同名参数重复、顺序改变也不能隐藏该操作。该微调后的源码单独通过上述181项回归；并行全库和接收端运行若已导入微调前版本，不能冒称其验证了最终字节。微调前`hosted_ats.py`的hash保存在同目录`hosted-ats-before-op.sha256`。

本票仍未完成：通用Next/Continue执行和任意网站业务语义仍需#18及集成工作；不理解的opaque POST、persisted GraphQL、片段/多根操作保持当前岗位等待，理由为路径/语义未确认，不冒称最终Submit，也不新增批准步骤。真实人工Submit及自动结果观察属于#37及真实闭环验收。当前测试不证明所有任意网站。本票保持claimed，不关闭。

### Existing receiver assertion diagnosis and continuation

首轮隔离接收端结果为`22 passed, 1 failed`，在`test_generic_labeled_radio_group_uses_hidden_native_inputs[True]`停止；原日志`submit-boundary-browser-escalated.log`保留不改。单独运行当前用例再次复现同一失败，记录为`submit-radio-current.log`。从恢复tar提取完整旧`src/`及`tests/`到临时目录，运行同一旧用例亦出现完全相同的断言失败，记录为`submit-radio-before.log`。相关readonly DOM路由函数、用例和CUA测试替身在恢复副本与本次提交边界改动前后均相同。

失败是原有测试要求具体调用CUA，而既有DOM路由已成功填写关联listbox；表单`ready_for_review`及radio的必填、有效性和答案断言已通过。仅将这条过时执行器断言改为Education实际值`Master`且有效，保留radio、完成状态及零POST检查，没有改生产执行器。该参数组两项均通过：`2 passed in 12.80s`，日志`submit-radio-fixed.log`；修改测试的Ruff检查及格式通过。

按原收集顺序列出56个接收端nodeID，排除首轮已通过22项及上述2项，仅继续剩余32项；ID清单为`submit-browser-remaining-nodeids.txt`，运行日志`submit-browser-remaining.log`。不重跑首轮通过项目；此轮及后续分段结果见下文。所有上述文件均在`/private/tmp/tomorrowstar-simplification-20261020/`，均为合成证据。

### Preserve the actual blocked request cause

上述剩余运行结果为`19 passed, 1 failed`，在opaque请求用例停止。已保存合成checkpoint明确记录`unverified_send_path / dispatch=not_sent`、零派发及保留的`open` intent，但页面等待表单超时后，既有通用异常处理将岗位原因覆盖为`browser_result_unknown`。只修改异常原因fallback：优先保留显式错误code，其次使用当前原页已记录的阻止原因，最后才用通用结果未知。请求仍拒绝，intent、原页和历史均保留，不放行或重发操作。

该opaque回归增加了保留`open` intent及持久`not_sent`原因的核对，单独复验`1 passed in 13.57s`，日志`submit-opaque-fixed.log`。只执行此前尚未运行的最后12个nodeID，`12 passed in 18.28s`，日志`submit-browser-final12.log`；此前19项不重复执行。原定56个不同接收端用例的分段通过数为`22 + 2 + 19 + 1 + 12 = 56`，原有失败日志仍保留。

最终异常原因微调后，对请求诊断、worker恢复、attempt完成和稳定性运行默认离线检查，`125 passed, 40 deselected`，日志`submit-stop-reason-offline.log`。这是分层验证：首轮22项和181项离线记录各验证其当时源码；不冒称所有56项和完整离线库均针对最终字节重跑。最终修改文件Ruff与格式检查通过；没有真实申请、已有浏览器或安装App验收。

全库检查随后定位到另一个旧测试仍引用已删除的`public_post_reads`内部属性。只对齐`tests/test_workable_bootstrap_diagnostic.py`的上述过时批准断言，不恢复运行时缓存，不修改生产代码。整个诊断文件`32 passed in 0.88s`，日志`submit-workable-retired-grant.log`；该文件Ruff、格式及diff检查通过。保留其他Workable读取、未知路径和恢复诊断断言。

### Focused receiver closeout — continued implementation

本次仅新增`tests/test_submit_boundary_browser.py`的聚焦接收端证据，不重跑上述56项。复用`create_fixture_server`、既有WorkerService/runner、ATS字段及Ashby查询fixture；浏览器和API请求只到隔离的loopback接收端。现有自动执行器驱动真实填写与上传，原页人工交接使用既有`review`命令。测试侧主动调用页面脚本属于绕过尝试，和生产执行器的自动动作计数分开解释。

| 证据范围 | 接收端/状态核对 |
| --- | --- |
| 正常执行器及禁止的动作intent | 最终按钮、Enter、requestSubmit、form.submit计数为零；HTTP/GraphQL动作intent拒绝；已选PDF字节接收一次。 |
| 普通Next | 只证明同一岗位非最终GET能通过出口；不冒充尚未实现的#18 Next生产接口。 |
| 原页人工交接 | 同一page和form保留人工字段修改及附件；交接后手动按钮使真实合成提交接收计数由0变为1。 |
| 页面脚本的最终动作及混合GraphQL | 独立网络限制使接收端最终计数为零；这类脚本不算生产执行器的动作接口。 |
| 草稿语义 | 接收端独立求值直接变量引用和字面量；有效草稿实际保存，偷换字面量、混合最终操作及转义block string混合操作不发送。 |
| 307/308重定向 | 分别核对读取、fixture上传、Lever解析和Ashby草稿不会由浏览器第二跳进入最终接收端。 |
| 未知/迟到结果与站点重发 | 首次实际上传一次；响应丢失或原响应迟于recheck时保留原attempt与历史，站点重发及后续tick不增加上传/最终提交。 |

实际接收端已复现上传307绕过：初始允许上传后，浏览器在没有人工交接时跟随重定向，最终接收计数为1。RED证据为`/private/tmp/tomorrowstar-submit-closeout-20261020/receiver-redirect-red.log`。该测试发现真实出口缺口，不把拦截器调用计数当作接收结果。主代理随后在活动出口加入单次有界fetch、禁止跳转并拒绝3xx；又处理较晚失败不能沿用本地“已选择文件”验证或丢失原intent的竞态。生产修改由主代理负责，本接收端子任务不改生产源码。

生产冻结后只运行本次新增文件：

```sh
UV_CACHE_DIR=/private/tmp/tomorrowstar-uv-cache uv run --locked --offline --no-sync python -B scripts/run_pytest.py -q tests/test_submit_boundary_browser.py -m worker_browser
```

结果为 **22 passed in 52.42s**，完整stdout/stderr保存在`/private/tmp/tomorrowstar-submit-closeout-20261020/receiver-final-exact-byte.log`。通过的接收端断言包括：正常自动执行时最终接收0、选定PDF接收1；同岗位非最终GET接收1；原页人工交接后最终接收由0变1且上传仍1；所有脚本绕过、已知读取/上传/解析/草稿的307/308第二跳最终接收均0；有效草稿实际保存1，错误字面量/混合最终操作实际保存0；响应丢失、迟到及站点重复请求上传总数保持1。上述计数由测试当时读取真实loopback接收端事件文件核对；pytest临时目录后来被其他运行清理，未另存这些逐项原始事件文件，不把通过日志冒称原始事件快照。

运行前后核对全部产品Python源码及4个测试/fixture文件，共79个文件，SHA256均相同。清单和比较结果分别为同目录`receiver-exact-byte-before.json`、`receiver-exact-byte-after.json`及`receiver-exact-byte-comparison.json`；本次新增测试SHA256为`47bab58b7dc911388c34d8dc33178ab93d91bac8b711f5389b7cd35bc3bd5514`。对应冻结的`application_worker_browser.py`、`hosted_ats.py`、`ashby_drafts.py` SHA256依次为`1f0eb4afc76e25274968330ded56ed5dd8d7bb16d6cb3521ef5c79852012331f`、`45186b78a6c5c922531aa749fda8eb18e61a506646d136b4734d99579a0e5ab2`、`d3587134cece9f62058cb89204f5f92e7eef016cd5bc4420ce8d1bd2a2fcc628`。新增文件Ruff检查、格式检查和全仓diff空白检查通过。

这里暂不勾选验收项、不关闭票据、不声明#18导航驱动、#37提交结果观察、任意网站或真实申请验收完成。原有56项接收端测试没有重复运行；它们保持此前分层证据，不冒称验证了这次冻结后的全部字节。

## Independent boundary audit — 2026-10-20

本节记录独立合成审计发现，不改变票头、验收项或关闭状态；发现时版本与后续修复版本须分开。

- **非live guard缺口（已交主实现修复）**：`ApplicationRunner._guard` 的同源GET分支未调用独立最终动作判定。最小离线请求 `GET /graphql?op=ApiSubmitSingleApplicationFormAction` 在classifier结果为True时仍得到allowed。该路径只有非GET才进入track_request；不能以live路径已有检查代替本路径验证。
- **转义GraphQL block string造成已知最终动作漏判（收口所需修复）**：`hosted_ats.graphql_names` 与 `ashby_drafts.single_draft_operation` 使用的三引号正则把合法block string内的转义三引号当作结束。由此可把后续真实 `submitSingleApplicationFormAction` 根字段误当字符串删除。完整live guard离线复现已得到 `known_final_classified=false / route_outcome=allowed / dispatch_kinds=[save]`。仅在draft parser拒绝block string不能保护通用GET discovery中的同类query；独立分类与dispatch均须保持拒绝/等待。
- **实际query参数没有绑定已核验variables（收口所需修复）**：`single_draft_operation`只跳过根参数组；`DraftSession.allows`核对variables字典，但query可以完全不用这些variables，改用其他组织、form、字段和值的字面量。同一真实live guard离线复现得到allowed/save。退役query hash后仍须验证实际执行参数与当前岗位/表单/事实的关系；不支持的绑定表达式应等待，不能由一份正确但未使用的variables获得发送许可。

以上两个完整Ashby复现保存在 `/private/tmp/tomorrowstar-simplification-20261020/submit-graphql-review-repro.py`，发现时输出保存在同名 `.log`。它们只使用临时合成工作区、fake route和已存在测试helpers；没有浏览器、真实ATS、provider或私人数据操作。审计未修改生产代码。

另外已报告需接收端确认的redirect问题：普通Lever解析/Ashby草稿分支使用route.continue，而Workable分支已明确禁止重定向与重试。需证明获准请求的307/308不会在后续未重新分类的跳转中发送最终业务请求；在接收端证据前不把该疑点写成已确认漏洞。

还有一个保守误判：只读 `query ApiJobPosting { jobPosting { id submit: id applicationForm { id } } }` 中 `submit`只是id别名，当前token-name判定却称其为已知最终动作。它不会造成自动最终投递，但若不能证明业务意义，应使用语义未确认理由，不把别名当成实际Submit证据。

职责判断：本票可证明既有出口对普通非最终导航/草稿/上传的边界许可，再把Next动作producer实现明确交给#18，把实际用户Submit结果观察交给#37；不能因此声称完整产品主线、任意网站Next或真实Submit闭环已经验收。上述本票自身的独立出口、参数绑定与接收端证据缺口须先解决，不能用后继票代替。

### Bind executed draft arguments to verified variables — 2026-10-20

独立审计中的字面量覆盖首先通过真实live-guard接口合成回归复现为RED（原实现发送save），然后修复为GREEN。`ashby_drafts.single_draft_operation`现在复用共享`graphql_tokens`，只支持已理解的单一根字段；每个根参数必须为`同名参数: $同名变量`，声明集合、实际根参数集合和已核验JSON variables集合必须完全一致。拒绝默认值、未使用/未声明变量、重复参数、变量换绑、字面量覆盖、input object和缺失参数；不支持的形状等待，不恢复hash批准。现有岗位、form、字段、答案、handle和PDF值核验保持原职责。

五个既有Ashby fixture query已增强为显式变量声明及根参数引用，覆盖读取、字段保存、位置查询、handle和文件挂接。它们不再通过“query未使用variables但fixture仅检查variables”的弱证据获得通过。新增live-guard参数组保留原intent并确认零派发，覆盖10种不受支持/错误绑定形状；5种已支持payload另有正向协议覆盖。修改仅限`ashby_drafts.py`及`tests/test_ashby_drafts.py`，没有编辑其他执行器。

默认离线检查：`tests/test_ashby_drafts.py` **65 passed, 20 deselected in 1.45s**；两文件Ruff检查和格式检查通过。用发现时原样保存的完整两例脚本重新验证，输出另存`submit-graphql-review-repro-fixed.log`，原失败日志不改：escaped block string混合最终动作现在为classifier=True、blocked、零派发；字面量覆盖为classifier=False、blocked、零派发。以上日志及脚本均位于`/private/tmp/tomorrowstar-simplification-20261020/`。

边界仍需明确：该参数绑定只支持直接、同名、顶层参数；没有证明真实API的重命名变量、默认值或input-object映射可执行。此类形状保持等待。20个浏览器用例被默认marker排除，不能把本次65项离线检查写成对这些浏览器路径或真实Ashby的完整验收。新的接收端证据及本票最终验收由本轮主实现继续汇总，本节不关闭本票。

### Ashby forwarding protocol regressions — 2026-10-20

随主实现改为自动请求使用有界fetch/fulfill，现有Ashby单元和浏览器fixture已同步模拟该协议。所有获准的自动请求要求`max_redirects=0, max_retries=0, timeout=10000`；unit fake拒绝自动continue并确认只fulfill同一次fetch得到的响应。浏览器fixture保持offline，仅返回合成响应；结果丢失通过异常模拟，不提前fulfill或接触真实网络。拒绝请求另断言零fetch，原intent与状态断言保留。

本次65项默认离线用例通过（20个worker_browser排除）；随后20个被修改fixture直接影响的浏览器用例全部通过：`20 passed, 65 deselected in 38.53s`。沙箱内首次Chromium在应用代码前SIGABRT的日志保存在`ashby-bounded-fetch-browser.log`；经自动审批通过的隔离offline Chromium运行保存在`ashby-bounded-fetch-browser-escalated.log`。两日志均在上述临时证据目录，旧失败日志不改。两涉及文件Ruff检查与格式检查通过。这组浏览器用例验证当前Ashby绑定与转发协议，不冒称真实ATS或完整产品验收。

### Final Ashby forwarding/disposal and recovery verification — 2026-10-20

自动转发响应增加dispose后，Ashby fake response现断言每个响应只释放一次，且fulfill发生于释放之前；拒绝路径不产生fetch或释放。浏览器fixture亦保存全部合成响应并检查释放，不访问外部网络。

新的迟到失败保护在普通成功用例中暴露了一个独立Chromium行为：即使有合法CORS响应头，合成HTTP 204上传令页面fetch成功返回204，浏览器仍可能发出`requestfailed(net::ERR_ABORTED)`。用不加载产品代码的最小offline浏览器独立复现了这一点。正常用例的失败日志保存在`ashby-bounded-fetch-disposal-browser.log`及`ashby-bounded-fetch-disposal-normal-cors.log`、`ashby-bounded-fetch-disposal-normal-diagnostic.log`，未覆盖。

主实现将例外严格限定于已收到204的已知`upload`协议ack；不是所有2xx、resume_parse、无ack、重定向或文件挂接失败的放行。该修复后，普通成功用例先通过，随后仅运行剩余19项，合计20个不同用例全过：`1 passed in 2.91s`（`ashby-bounded-fetch-disposal-normal-fixed.log`）及`19 passed, 66 deselected in 43.26s`（`ashby-bounded-fetch-disposal-remaining19.log`）。65项默认离线再次通过，Ruff检查及格式检查通过。

最终独立只读复核核对了共享lexer、真实参数绑定、有界fetch/无重试/响应释放、人工handoff、迟到失败的精确batch/run/attempt及用户明确结论保护。pending失败会在新intent产生前停止，已结算旧事件只保留历史；未结算且后来变未知的旧写操作仍可停岗核验，其他已完成动作历史保留。未发现新增P1问题。

本组运行前后当前三个源码文件均与`/private/tmp/tomorrowstar-submit-closeout-20261020/source-freeze.sha256`相符，且三个源码修改时间早于成功普通用例日志创建时间。上述分段日志均在`/private/tmp/tomorrowstar-simplification-20261020/`。这里只确认该有界源码与合成协议结果；本节不决定整票关闭，不扩展到真实ATS、#18 Next producer或#37实际用户Submit观察的验收。


## Resolution comment — 2026-10-20

**按独立出口职责关闭。** 继续已有实现，修复 fixture 同源最终 GET、GraphQL 转义 block string、真实参数换绑、未经重新判定的重定向、响应体释放及迟到未知写恢复问题。保留 owner/目标/PDF/intent/attempt、显式人工结论、取消/人工接管和历史证据；退役清单沿用上文，不清理旧配置或私人记录。

当前验收对应关系：

| 验收项 | 本票证据与范围 |
| --- | --- |
| 独立限制先于批准退役 | authorize、两个 guard、track_request 均独立拦截；旧 grant 无法覆盖，历史 RED/GREEN 保留。 |
| 自动最终动作零执行，普通动作可通过 | 生产 dispatcher 无最终按钮/Enter/submit/evaluate 动作；实际合成接收端 Next 非最终 GET、草稿和上传通过，最终 HTTP/混合 GraphQL/页面脚本绕过为零。Next producer 仍由通用 ATS 票实现。 |
| 已知最终拒绝，未知停当前岗 | 已知字段/URL 操作先拦截；未知请求、绑定或结果保留等待，不把所有 POST 命名为最终动作，也不恢复逐请求批准。 |
| 原页人工 Submit | 同页、同表单、人工编辑和 PDF 保留；模拟人工点击后实际接收一次。业务结果观察及续岗由人工交接后继票消费，不冒称真实投递闭环。 |
| 保留安全与恢复职责 | 未知响应先保留原 attempt；派发前消耗、历史去重、pending 失败阻止新派发；显式核验、旧 batch/run、不同活动动作、取消及人工接管均保护。 |
| 合成接收端 | 新增 22、Ashby 20、其余既有 80、无界面计量 9 个不同用例均有最终通过记录；重定向第二跳、重复及迟到不造成最终动作重发。 |
| 退役清单与适配器保留 | 上文配置/参数/旧断言表完整；保留解析和响应识别，未支持网站/参数形状仍等待。 |

受影响默认离线 **390 passed**；完整默认 **4126 passed、1 failed、2 skipped、367 deselected**。唯一失败是既有主流程追加 `batch_exists`，原源码同例复现及函数相同证据保留；不影响本票独立出口结论，也不宣称完整套件或整条产品主线通过。Ruff、格式与 diff 检查通过。

[最终实施与验证记录](../submit-boundary-closeout-20261020.md)及[证据目录](../assets/submit-boundary-closeout-20261020)保存冻结源码、通过/失败日志、实际测试断言、恢复副本与哈希。上文 claimed/未完成及早期分段数字均为当时记录，本节是当前关闭结论。没有 commit/push、安装主 App、真实邮箱/申请/模型操作；最终 Submit 仍由用户操作。
