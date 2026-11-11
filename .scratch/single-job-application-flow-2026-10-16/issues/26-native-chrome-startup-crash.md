# 复现并修复 Chrome 原生启动崩溃

Type: task
Label: wayfinder:task
Status: open
Priority: P3
Interaction: AFK
Assignee: 01a155fd/root
Created: 2026-10-17
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [将单岗位流程设为原生 App 默认运行方式](08-native-runtime.md)、[构建并在安装版 App 验证单岗位合成流程](10-installed-app.md)
Triage: deferred-diagnostic

## 当前替代范围 — 2026-10-20

取消产品运行依赖，保留历史Chrome启动因果诊断。已验证主App正常启动/PDF的证据复用；原工具完整受限沙箱GREEN、历史argv缺口及Dock来源不能再阻止正常获权主App进行当前产品验收。

规范：[单岗位流程](../../../docs/single-job-flow.md)；执行顺序：[统一开发计划](../../../docs/development-plan.md)。本节替代下方与之冲突的旧范围、验收、时间窗和运行门槛。Status、Assignee、历史勾选和原始收据不变；新验收尚未实施。

当前验收：

- [ ] 历史报告仍按已绑定/未绑定及实际环境记录；不能借新规范把未知根因写成已修复。
- [ ] 若继续研究只对准确实验条件下结论，明确与正常App路径差异；不重新跑真实申请来证明历史原因。
- [ ] 实际启动失败准确显示、保存断点及后继恢复纳入27/34；本票不再是30/11的直接或传递前置。

以下保留原范围与历史证据，不将新期望追写为旧票未完成原因。

## Current scope and remaining acceptance — 2026-10-20

- 已完成：历史报告逐项绑定或明确未绑定；独立安装候选整包与三次冷启动／PDF；最终主界面固定注册拒绝注入、停止提示及刷新不重试。
- 未完成：已绑定原失败条件的完整因果要求、原完整受限沙箱同条件修复成功；两份历史报告的直接argv缺口保持未知。
- 功能基线完整默认离线与最终文案后继的受影响回归分别引用，不把前者称作后继全套重跑。正常原生宿主导出成功不替代原完整沙箱GREEN，安全启动前阻断也不等同成功导出。
- 本票保持开放和原领取；本次修订不改既有验收勾选，不通过拆票解除安装组合验收的原前置。

## Question

本轮 Chrome 原生启动 SIGABRT 由什么条件触发，如何在相同环境中证明修复有效？

## Problem and priority

来源：[复盘 E03](../test-findings-2026-10-17.md)。已有三份启动崩溃报告，含 HIServices 应用注册及 TransformProcessType；唯一根因未定。P0：新的真实运行必须先有可信的原生启动证据。

## Work and reuse

- 先将每份报告与确切浏览器二进制、启动 argv、父进程/责任链、包签名、沙箱和显示会话条件关联；无法关联的标为未绑定，不补造归属。
- 复用原生诊断、已有冷启动调查和构建器；用一次性合成工作区建立原条件与单变量控制组。Chrome 与 Chrome for Testing 分开记录。
- 有复现证据后才做最小修复。不能把换一次启动路径、沙箱外成功或延长等待当作原故障修复。
- 故障发生时在 App 明确给出阶段及停止原因，保留诊断和可恢复原件。

## Ownership

- 按归因结果限定 `cua_driver.py`、`macos/App.swift`、`macos/server.py` 或现有启动调用点，不预先全部改写。
- 复用既有原生启动、Cua 生命周期与 macOS 测试；不修改真实浏览器 profile 或其他任务进程。
- 与 27 的原生会话中断、28 的安装预检协调共享文件；不将两种故障预设同因。

## Acceptance criteria

- [x] 三份历史报告逐一有已绑定/未绑定及依据；不能将 SIGABRT 栈顶本身写为唯一根因。
- [ ] 至少一个已绑定的原失败条件可受控复现，并有单变量对照支持因果判断。
- [ ] 最小修复在同一条件下由 RED 转 GREEN；原失败与后继结果均保留。
- [x] 冻结包在原时限内连续三次隔离原生冷启动通过，正常退出后只回收本次自建资源，不碰在途原页。
- [x] 注入同类启动失败时，App 有准确错误和停止状态；不会反复拉起、自动重建 profile 或开始填写。
- [x] 原生/包内与完整默认离线分别通过。若无法复现或因果未定，仅记录诊断进度，本修复票不关闭。

## Verification and evidence

原始系统报告与精确启动记录仅存私有位置，公开用脱敏条件矩阵和合成反例。保留原编译/启动超时，不放宽验收时限掩盖故障。

## Authorization and stop boundary

当前只建票；不启动 Chrome 或重启现有 worker。后续故障实验只用另获执行授权的隔离工作区，不在真实申请上注入故障。

## Resolution comment

2026-10-17：新建未领取；历史包验证成功未被当作本票根因或修复结论。

2026-10-19 只读归属审计：三份历史附件中，两份已归到其他会话或合成 harness；
第三份仍缺少进程身份与启动参数的直接关联证据，继续标为未绑定。不能仅凭
原生崩溃栈判断它属于当前申请链，也不能将合成 harness 的启动失败等同于历史
原生故障。当前没有已绑定原失败条件的受控复现、单变量因果对照及同条件修复
证据；历史原生根因仍未知，本票不能关闭。未启动真实浏览器、重启 worker 或
改变原页；真实申请继续暂停。

## Scope reconciliation — 2026-10-19

本票持有三份历史SIGABRT的进程／启动条件绑定、同条件受控复现及修复因果证据。[稳定性07](../../application-worker-stability/issues/07-cold-start-prewindow-investigation.md)持有无窗口启动前置拒绝、aevt/rapp及Dock直接发送的来源调查；Dock上游触发及历史同因仍未知。守卫拒绝与原生崩溃不预设同因。优先复用已绑定的原始证据，未绑定仍标未知；一票的局部成功不能关闭另一票。

两票仅互链范围，不新增彼此Blocked by、不复制同一轮根因实验或改写历史。原优先级、领取及验收条件保持；材料路径通过不证明本票修复，真实申请继续暂停。

## Execution claim — 2026-10-19

用户在当前会话要求使用implement开始执行下一张。本会话领取本票，限历史证据核对及一次性合成环境的原生启动归因／最小修复；不恢复真实申请、不重启现有worker、不使用真实profile。先建立可识别原SIGABRT的反馈环；未绑定历史条件或无法复现时记录限制、不关闭本票。旧证据与其他会话工作保留。

## Execution progress — 2026-10-19

本会话已读取现存系统报告及窄时间窗会话日志，并独立勘查现有冷启动／lookup／退出探针。现有公开三附件摘要缺少逐项身份，报告与启动条件尚未完整绑定；既有探针不覆盖HIServices SIGABRT，未建立原故障的red-capable反馈环。没有启动新浏览器或修改生产代码，不以其他环境成功冒称修复。下一步需要原三份报告／会话附件定位和对应实际启动记录。保留open、本执行者及全部未完成验收，详见[领取与诊断记录](../../chrome-startup-execution-2026-10-19/README.md)。

## Historical attachments recovered; diagnostic blind spot fixed — 2026-10-19

按用户要求继续自行检索，在原用户会话的粘贴文件引用中找齐三份报告：PID90954、95864及74201。90954与另项目直接Chrome启动有跨源强绑定；95864由合成Playwright测试的精确PID／SIGABRT直接绑定；74201与包内合成PDF导出强关联，PID／argv直接桥接仍缺。逐份原会话行号、调用ID及不确定性已保存，不再请用户重复提供报告。前述“需用户提供报告”已被本轮定位结果替代，旧进度记录保留。

工程上独立修复macos/verify.py捕获子进程输出但失败时未展示的问题：失败及超时通过原异常notes保留stdout/stderr，保持非零退出且不重试、不生成成功报告。原行为回归3失败／2通过，修复后相关7项通过；Ruff／格式／diff检查通过，独立复核无阻断。没有启动浏览器或恢复真实申请。

三报告逐一身份及绑定依据已完成第一项验收；同条件因果复现、实际崩溃修复与冻结包三次冷启动仍缺，票保持open及原执行者，不将诊断修复等同原生根因修复。详见[报告定位及独立修复](../../chrome-startup-execution-2026-10-19/followup.md)。

## Historical argv search exhausted; exact current reproduction and control — 2026-10-19

已继续自行补查PID90954与74201：原附件、原会话工具输出、系统统一日志、桌面日志、临时验证日志及Crashpad转储均未恢复PID到完整argv的缺失桥接。两份历史强关联维持，不用相邻PID或新实验冒充原事实，不再要求用户重复提供。缺失字段及搜索边界已记录。

在用户授权的隔离合成环境执行一次生产export_pdf：默认执行沙箱中的Chrome PID45535启动即SIGABRT；用户新贴系统报告精确匹配该PID及HIServices／RegisterApplication／TransformProcessType栈。同一当前二进制、源码、HTML和除临时profile外相同argv，在沙箱外单变量对照PID45901成功生成0600 PDF。当前证据支持执行沙箱因素，不证明具体OS拒绝规则或旧两PID的argv；各条件仅一次，不记为三次冻结包验收。

本轮未追加推测性生产补丁；已有异常notes修复保留。两自有进程和临时profile已退出／清理，没有真实申请、现有worker或原页操作。原验收状态及本执行者保持，整票不关闭。详见[补查边界、精确复现与对照](../../chrome-startup-execution-2026-10-19/rootcause-followup/README.md)。

## Service-denial cause narrowed; verifier preflight implemented — 2026-10-19

精确PID45535的系统日志显示launchd在崩溃前以Sandbox restriction拒绝LaunchServices、WindowServer等服务。公开bootstrap_look_up的无浏览器预检在默认执行沙箱返回1100，沙箱外相同服务返回0且端口释放成功；结合前轮同二进制对照，支持当前执行上下文阻止应用注册的机制。具体单条服务拒绝是否足以触发abort及历史两PID的直接argv仍未知。

最小修复落在macos/verify.py包验证入口：先检查应用注册服务，明确拒绝则在任何子进程前报macos_chrome_registration_denied；未知API／返回／端口状态明确为unknown，不自动切换宿主或放宽权限。既有子进程异常notes修复保留，核心导出及已安装App／worker不变。

17项相关回归、实际沙箱内CLI预启动阻断、沙箱外只读正例、独立高强度审查及全仓Ruff／格式／diff检查通过。没有新增Chrome崩溃、包安装或真实申请动作。本切片完成启动保护；原票的历史因果及冻结包完整验收仍未完成，保持open／本执行者。详见[原因、修复及验证](../../chrome-startup-execution-2026-10-19/service-preflight/README.md)。

## LaunchServices denial isolated; working PDF export verified — 2026-10-19

依用户要求推进单变量原生实验：allow-default基线成功；只拒绝LaunchServices导致PID52847同注册栈SIGABRT；只拒绝WindowServer仍导出成功；拒绝原六服务导致PID53081崩溃；只恢复LaunchServices并保留另五项拒绝后真实PDF成功。两份新系统报告精确匹配失败PID和栈。内核只读查询另证实五项拒绝实际生效，当前Chrome／宿主／合成导出中LS查询拒绝是可独立触发并可逆转的原因。

已纠正macos/verify.py过宽的WindowServer门槛，预检仅保留LaunchServices；红测2失败／8通过，收窄后相关17项通过。随后当前预检加生产export_pdf在恢复方案中连续三次独立profile成功，PDF均一页、正文匹配合成输入且权限0600。全仓lint／格式／diff及独立高强度复核通过，八轮自有进程／profile退出核对通过。

这是自建allow-default加服务deny的受控策略，不等于Codex原完整沙箱；没有修改系统／工具全局策略、安装App或恢复真实申请。三次源码组合成功不充当冻结安装包验收，旧两PID的argv缺失保留，原票保持open及本执行者。当前完整结果与可查看PDF见[LaunchServices因果与实际导出修复](../../chrome-startup-execution-2026-10-19/service-causality/README.md)。

## Installed native PDF acceptance — 2026-10-19

按用户要求将 LaunchServices 预检与固定合成 PDF 诊断入口接入独立签名安装版 `TomorrowStar Chrome PDF Verified.app`，保留原主 App 与连接配置。冻结基线 87 个核心 engine 文件不变；整包签名、重定位、包内运行时及实际系统 Chrome PDF 验证通过。已安装 App 经 LaunchServices 连续三次实际原生无窗口冷启动，耗时 6.449/7.677/3.757 秒，均在单次 40 秒观察上限内，包内 Python 和 Chrome 的 OS 责任链逐次绑定原生 PID。每次真实 PDF 一页、正文核验、0600，自有进程退出及临时 profile 清理通过。

完整默认离线套件 3505 通过、305 按默认标记排除；48 项相关回归通过，后续仅 AST 等价测试格式修正并重跑 2 项通过。源文件运行期间冻结；安装后包字节及签名保持。勾选本票安装包三次冷启动与原生/包内加完整默认离线两项，仅覆盖此独立包的固定合成诊断入口。

独立临时故障副本通过固定注册拒绝注入，准确记录 registration_preflight 和 macos_chrome_registration_denied，零浏览器/导出/重试；不冒称真实 OS 拒绝或主界面提示验收。历史 argv 缺口、原完整受限沙箱同条件修复及原界面失败停止验收保留未勾选。票保持 open / 01a155fd/root，不解除下游门槛。真实申请持续暂停，无模型/ATS/上传/提交。详见[安装版整包与三次冷启动报告](../../chrome-installed-validation-2026-10-19/README.md)。

## Remaining acceptance and main UI repair — 2026-10-20

注册预检已接入真实 PDF 导出及共享主界面；已知拒绝/未知明确停止，不启动 Chrome、不自动重试。实际原生旧合并流程发现“草稿/审阅已保存、仅重试 PDF”的通用提示不实，已改为中性停止原因并补回归。最终相关 155 项、浏览器 7 项通过；功能基线完整默认离线 3512 通过、307 排除。最终 successor 仅变更生产错误文本及回归，未声称其重跑完整默认套件。

独立安装候选再次完成整包验收和三次实际原生冷启动/PDF：7.634/4.111/2.729 秒，PDF 一页/正文/0600、自有责任链和清理通过。原主 App 与连接配置保持。原完整受限沙箱实际查询仍被拒绝，无同条件 PDF GREEN，第2/3项仍不勾选。

原完整沙箱实际拒绝已在功能基线共享 UI 验证；最终文本通过七项浏览器回归。临时故障副本成功启动后发现并修复旧文案，但最后有效目标合成根目录的分析以 match_model_timeout 停止，未到导出；最终 WKWebView 失败路径仍未完整验完，第5项保留未勾选。首轮副本 spawn EPERM 为已保留历史尝试，不再视为当前唯一阻塞。自建原生/后端正常退出，观察页关闭；真实申请继续暂停。

历史 argv 缺口、同条件修复及原生最终失败路径逐项记录；tracker 无可独立领取 frontier，不越过他人依赖或改领其他票。票保持 open / 01a155fd/root，详见[本轮验收及阻塞](../../chrome-remaining-acceptance-2026-10-19/README.md)。

## Native window failure gate completed — 2026-10-20

继续处理原生验收阻塞：失败输入/结果间隔30秒，定位到版本查询限时，并非180秒分析响应。仅在临时固定合成 CLI 加入口记录、更新合成 marker；原实现、错误和超时不变。通过原生 UI 明确同步新合成配置后重试一次，版本和固定分析 exec 均完成；原30秒失败根因仍未知，未由成功覆盖。

在实际 WKWebView 点击生成后，最终 production exporter/UI 与独立安装候选逐字节相同，固定 guard 拒绝准确显示“PDF 导出已停止…不会自动重试；请先核对执行环境”。刷新后 flow 字节和 CLI 四条进入记录保持，无 PDF、无 worker；只读进程树只有 Native13534和backend13537，无Chrome子进程。正常Quit后两PID消失、后端EOF及关闭完成有据。fixture 的固定根目录Swift和拒绝guard为明确测试覆盖，不冒称OS实际拒绝或完整包字节无覆盖。

据此完成第5项注入失败主界面验收。原完整受限沙箱同条件GREEN和历史直接argv仍阻塞，票不关闭、不解除真实运行门槛。详见[原生失败回执](../../chrome-remaining-acceptance-2026-10-19/native-window-followup/result.json)及[截图](../../chrome-remaining-acceptance-2026-10-19/native-window-followup/failure.png)。

## Approved ticket revision — 2026-10-20

按用户同意的审计修订发布：更新当前停点及剩余验收，不改原领取、历史回执或既有依赖；不追加真实运行授权。新增证据保全工作可独立推进，其产物供本票适用范围引用，不代替本票原验收。

## Main installation consolidation — 2026-10-20

用户明确要求后，已验证 PDF 修复及失败提示已接入主安装版 TomorrowStar.app / dev.tomorrowstar.desktop。功能资源保持已验候选原字节，恢复主 Info.plist 并重签。整包隔离验收、安装后连续三次实际原生冷启动及合成 PDF 导出通过；普通合成材料窗口 source/UI、实际主身份及 loaded_mapping 通过，无 worker，正常 Quit。27 个旧测试／备份 App 已可恢复归档，Applications 仅留主 App；真实配置保持。

原完整受限沙箱同条件成功导出及两份历史 argv 缺口仍未补齐，不新增勾选或关闭；获权重验由 28 持有。真实申请保持暂停。见[主安装整合与回退](../../main-app-consolidation-2026-10-20/README.md)。

## Parallel execution group — 2026-10-20

[B — 启动与历史故障归因](../../open-ticket-parallel-plan-2026-10-20/README.md#b-startup)。跨票顺序、共享文件及原生实验串行约束见统一分组导航；本票状态、原领取、依赖与验收仍按上文执行。本次仅重组导航，不领取或扩大执行许可。


## Notes — 可用优先重排 2026-10-21

历史崩溃因果独立保留，不阻功能候选。

Priority/Triage/票头依赖按本次重排更新；旧边与原字节见[审计及变更账本](../../usable-first-wayfinder-audit-2026-10-21/README.md)。原 Status、Assignee、Interaction、既有验收勾选及全部旧正文保持，不领取、不关闭、不替用户接受。源码接口依赖不等于安装或真实操作许可；App 未更新，真实申请继续暂停。
