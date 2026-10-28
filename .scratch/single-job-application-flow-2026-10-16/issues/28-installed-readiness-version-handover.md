# 核验当前安装身份与在途版本交接

Type: task
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: 01a150ef/bounded_protocol
Created: 2026-10-17
Updated: 2026-10-21
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [将单岗位流程设为原生 App 默认运行方式](08-native-runtime.md)、[构建并在安装版 App 验证单岗位合成流程](10-installed-app.md)
Triage: done
Closure reason: completed

## 当前结论 — 2026-10-21

按用户明确要求，已将保全核对结论同步唯一维护操作者，并在同一主App更新和隔离验收完成后复用现成安装证据。下列2026-10-20当前精简范围7项均已有源码行为回归及安装支持，按该范围结案；不重跑已被替代的旧证明矩阵。详见[逐项映射与最终读回](../../ticket28-installed-evidence-2026-10-21/README.md)。原负责人、依赖和下方历史验收勾选保留。

安装完整inventory及固定签名匹配v3候选，controller/UI实际加载匹配；worker完整加载映射仍unknown。G3只证明空intent的原页/字段/附件/PDF重开保留；未新测活旧worker跨版本执行、真实人工值修改或非空未知intent恢复。四正式运行根完整inventory保持，正式配置最终恢复原字节；误开普通窗口与配置JSON重排事故原样保留。旧owner、未知结果和fill intent不清除、不重放。30/34及其他真实验收不因此关闭，真实申请继续暂停。

## 当前精简范围 — 2026-10-20

## Question

如何移除逐操作安装/版本/epoch/短租约证明，并使诊断或无关配置失败只影响相关能力？

规范：[产品规范](../../../docs/single-job-flow.md)；安排：[开发计划](../../../docs/development-plan.md)。本节是本次精简任务化后的当前范围，替代下方冲突的旧范围和验收。Status、Assignee和历史收据不变；本次不领取、实施或关闭。

本票拥有运行能力与维护诊断的收敛；独立最终动作限制归[独立限制最终Submit并退役请求批准](38-independent-submit-boundary.md)，岗位状态归属归[统一岗位主控并派生浏览器执行状态](39-single-orchestrator-derived-state.md)。

当前验收：

- [x] 包清单、controller/UI/磁盘身份、nonce、epoch、固定几秒lease与原页proof不再是每次prepare/answer/resume/heartbeat的前提。构建签名与稳定单App维护保留，成功权限检查不使健康会话失效。
- [x] 只核对当前操作实际所需权限与相关事实；具体文件采用/上传时核对当前岗位及文件。普通字段操作不反复扫描全库、研究benchmark或无关模型配置。
- [x] 取消write_proof后仍直接复用prepare_application_task核对目标；保留真实owner/锁、显式暂停、先落intent/attempt、已发出动作及未知结果不重放。不能整删authorize/write_preflight带走必要职责；不新增公共权限服务。
- [x] 业务原子检查点保存失败停止并保留旧记录；measurements.track失败仅诊断，不再触发block_storage或新审批/恢复状态。
- [x] 缺模型或失效Codex路径只影响模型步骤，仍可浏览与修正资料；无关preparation_root不挡默认App启动。实际缺OS能力报告准确原因，不误报目录故障。
- [x] 旧runtime/PID/目录单纯存在不作为活性或全队列阻塞证明；实际同岗占用/未决操作仍保护，已存在原页和人工修改不被重启覆盖。
- [x] 将旧包/epoch/lease矩阵断言改为健康会话持续、局部故障隔离和必要业务保护的行为回归；真实当前能力失败仍可验证。历史Chrome/TCC根因未闭合不成为整票新总门槛。

以下保留原范围与历史证据，不将新期望追写为旧票未完成原因。

## Current acceptance boundary — 2026-10-20

当前原第1项“主宿主权限及责任链”和第5项“预检对暂停任务无业务写入副作用、停止决定保持”已完成。后继主安装版获权正例与历史普通窗口双缺权拒绝分别保留；两权限同时缺失的负例不是分别缺权或完整身份／时序矩阵。实际三身份及当前包合法继续的子范围见本票末尾2026-10-20原生验收支持。

剩余范围继续由本票持有：运行worker、控制端、磁盘包三身份；配置不等价；当前获权正例与完整拒绝矩阵；旧worker／Page／附件保留及精确版本组合的兼容交接。未知兼容性不准入，也不能用“全部拒绝”替代合法正例。

下一次验收先声明固定候选及实际加载版本，并说明与当前源码的差异；不能把已验证的独立候选称作全部最新源码。证据持久保全的公共产物可复用，但不替代本票的实际身份、权限及交接证明。

## Question

如何在写入真实资料之前核对当前安装身份、权限和实际执行版本，并清楚呈现新控制端配合旧 worker 的合法过渡状态？

## Problem and priority

来源：[复盘 E01、E04 及执行失误](../test-findings-2026-10-17.md)。权限开关曾与实际宿主检查不一致，安装包与在途执行器版本也不能混为一谈。已恢复的历史权限不再另造一张 TCC 根因票；本票补就绪预检与交接契约。

## Work and reuse

- 复用当前 GUI-host 诊断、build manifest、worker loaded-source、流程/worker 锁与配置 revision，不增加第二份运行状态库。
- 在同一预检结果中分别呈现控制端版本、实际 worker 版本、当前宿主权限、原页归属、owner/transport 证据及分析/材料配置绑定。
- active=false 只表示 Chrome 未前台；owner_idle_seconds 是配置参数。owner 健康依据近期已确认保活或明确故障，不能由 App 开关、worker 心跳或 named session 字符串单独推断。
- 新控制端与旧 worker 可在已验证命令兼容、原包保留、锁交接及原 run/page 不变时配合；不得伪装热加载或强制同版本而重启在途任务。
- 使用系统合法授权流程，由用户处理 Touch ID；不自动重置 TCC。预检本身不导航、重启、采用旧 profile 或消费 intent。

## Ownership

- `macos/background_check.py`、`macos/App.swift`、`macos/server.py` 的现有身份/配置诊断。
- `application_worker.py`、`application_flow.py`、工作台版本/就绪展示与现有测试。与 24 的页面观察、29 的动作阶段文案分别负责。

## Acceptance criteria

- [x] 当前宿主两项权限与子进程责任链实际核验；系统开关开但宿主未获权的反例能准确停止，提示确切 App 和所缺能力。
- [ ] 控制端、运行 worker 和磁盘包的版本分别可见，未验证状态不会显示为可填写；配置不等价时拒绝，不重绑旧分析/材料绕过。
- [ ] 新控制端沿旧兼容命令控制时保留原 bundle、worker、Page 和一次性答案边界；不启动第二 worker，不假报加载新源码。
- [ ] 旧 worker 退出、owner/transport 故障、页面变化及锁转移失败有明确停止状态；不静默采用 profile、清空 intent 或恢复旧命令。
- [x] 预检对已暂停任务没有业务写入副作用；用户原停止决定一直有效。
- [ ] 当前安装版隔离预检及交接正反例通过，所验来源/版本/配置明确绑定，旧权限/包快照保留。

- [ ] 在本票固定安装候选的隔离合成工作区，通过真实POST／命令调用入口而非仅GET诊断，分别验证缺任一必要权限、宿主／责任链或nonce错配、过期／未知证明、配置不等价或跨版本命令兼容性未经证明会在副作用前拒绝。
- [ ] 上述拒绝后独立回读：没有创建或恢复worker／页面，没有字段写入、上传、消耗intent或改绑旧材料；检查与执行间证明变化也须在持锁复验处停止。记录有效证明允许既有批准合成命令的正例，包含原契约允许且已验证兼容的跨版本组合；不因版本号不同直接拒绝，也不以相同版本号自证兼容，不能靠全拒绝通过。最终Submit始终阻断。

## Verification and evidence

优先复用只读诊断；实际 OS 权限变化仅在另获授权时执行。共享契约变更跑完整默认离线；公开证据只存脱敏能力状态与代码/包版本。

## Authorization and stop boundary

仅建票，不打开系统设置、改权限、安装包或操作原运行。后续真实预检遵循第 31 票及用户恢复许可。

## Resolution comment

2026-10-17：新建未领取；历史权限重绑通过继续保留，不宣称已证明 TCC 数据库根因。

2026-10-19：核对 open/none 且 08/10 已关闭后领取。当前只实施 background_check.py 的显式 permission-only 边界与纯合成测试；控制端/磁盘包/worker 统一身份及安装验收仍未完成。本票保持 open，真实申请继续暂停。


2026-10-19 第一条源码边界：`macos/background_check.py` 新增显式
`run(root, permission_only=True)` 与 `--permission-only <private-directory>`。
复用原 native/Python/daemon/proxy 责任链和 `check_permissions(prompt=False)`；
完成权限检查与原有 daemon 清理后即返回，不进入 Playwright、浏览器管理器、profile、页面或附件。
`mode=permission-only` 将 `passed` 与 `permissions_required` 限定为权限检查结果；
进程退出码沿用原诊断约定，不能只凭退出码 0 宣称可填写或 owner 健康。
默认无参数的完整诊断仍进入原合成浏览器腿。输出目录继续要求独立、非链接且 0700。

纯合成 TDD 已先复现缺少新模式的 RED，再通过新模式 GREEN。
[权限只读回归](../../../tests/test_macos_permission_readiness.py)与既有输出目录守卫通过；
覆盖已获权、分别缺两权限、宿主链不匹配、native/嵌入权限不一致、完整诊断原入口及 CLI 目录限制。
测试用合成 subprocess/权限回执，不执行 OS 权限 API、不启动真实 daemon/App/Chrome。
所拥有源码的 Ruff、format、whitespace 检查通过；未改共享域契约，未增加无关全套回归。
原字节、RED、GREEN 与命令墙钟保留在执行者的任务独立临时证据目录。

限制：本边界沿用既有后台 native 快照（无窗口、非前台）约束；生产执行仍会启动仅含
`check_permissions/end_session` 能力的短命权限 daemon/proxy，随后清理，不接管在途 owner。
Swift 的现有 `--background-check` 尚未转发新 Python flag；未新增原生入口，未改 App.swift/server.py。
当前安装版宿主验收、统一三身份/配置/兼容投影与在途交接正反例仍未完成，六项整票验收均保持待核验。
本票仍 open，真实申请继续暂停。

2026-10-19 当前普通窗口宿主边界（源码与合成核验，整票未验收）：

- 显式原生 `--permission-check` 已接固定 Python `--permission-only`；原完整
  `--background-check` 与其零窗口限制保留。实际 bundle/executable 从 OS 的 native
  responsible PID、`proc_pidpath` 和 Info.plist 回查，不再以固定 bundle ID 或传入路径自证。
- 普通窗口每次 backend 启动生成新 nonce，并在既有父控制管道发送有界、白名单 JSONL。
  启动采样只核验当前 native/Python 链，保持 unknown。固定原生菜单“检查当前宿主权限”
  才运行独立、限时、nonprompt 的两权限 daemon/proxy 检查；不使用网页数据产生 native 回执。
- 共享既有权限探针，仅允许 `check_permissions/end_session`，有单次工作截止和有界清理。
  不借用在途 worker/client，不创建浏览器、profile、页面或附件；退出仅清理本探针注册的进程。
  纯 GET 读取深拷贝的内存 snapshot；无 RPC、OS 权限采样或业务写入。过期/未知不显示已验证。
- 错 nonce/PID/bundle/executable、责任链错配、缺权、超长/坏帧、重放及 backend 关闭均有停止边界。
  无效回执或检查中出现缺权后，晚到 probe 不能重新置绿；相同在途检查不会排队。
- 合成权限/责任链、真实 Foundation Swift 编码 harness、真实子进程父管道 EOF/超长帧恢复、
  原生退出与安装材料保全聚焦回归通过：true。Swift typecheck 通过：true。Ruff 通过：true。
  RED/GREEN、原字节与源 hash 保留在任务独立的私有临时证据目录。

当前安装普通窗口的实际 host/daemon 权限证据、统一交接正反例仍待安装候选验收。
本边界未启动 App、浏览器或真实权限 daemon，未请求 grant、改 TCC 或使用凭证。
原历史权限/包证据保留；六项整票验收仍不打勾，本票 open，真实申请继续暂停。

## Current wiring and write admission — 2026-10-19

静态核对已确认：原生server从自身定位Resources并传入包资源及当前原生身份绑定，Portal向flow／worker注入write_preflight，相关prepare／resume／recheck写路径已接持锁复验。这只是当前源码接线；下文较早“尚未接线”不再作为现存源码缺陷。当前候选普通窗口、包／加载／worker三身份和版本交接正反例仍需按本票验收，不以GET诊断或按钮状态代替实际命令门禁。

[稳定性10](../../application-worker-stability/issues/10-cua-035-background-attach.md)保留其已完成的包内隔离附着、GUI缺权拒绝证据及当前GUI获权后的完整后台链剩余门槛。它不代替本票统一身份／配置／版本交接，本票也不代替它的原页／附件／scope与未知结果验收；仅证据互链，不互相添加阻塞。

本票新增写前验收的安装组合演示由[30](30-installed-minimal-regression.md)汇总。28先完成自己的固定候选负例及交接证据再关闭，30复用同一候选，禁止28反向等待30而制造环。原领取与未完成状态保持，发布不执行原生权限检查、不请求grant或修改TCC。

## Supporting actual HTTP admission regression — 2026-10-20

总目标授权下，本会话补充独立源码验收支持；原Assignee及依赖保持。新 `tests/test_installed_write_admission_http.py` 通过真实HTTP POST（规范Host、Origin/CSRF），缺权/nonce/责任链/过期/未知和检查后权限/nonce/配置变化均在写前拒绝；独立回读flow/worker/applications字节不变。有效证明可准备任务和明确恢复（spawn仅替身记录），Submit拒绝。新增10项、相关合计75项通过，Ruff/格式/diff通过，无生产代码变更或真实申请。

此为合成权限/包证明的源码HTTP门禁证据，不冒称当前安装版三身份、实际TCC、跨版本兼容正例或完整组合验收。全部未完成门槛保留，详见[支持回归与限制](../../autonomous-engineering-2026-10-20/admission-http/summary.json)。

## Current independent candidate nonprompt permission receipt — 2026-10-20

本会话总目标下补实际证据，原Assignee保持。独立已安装 `TomorrowStar Chrome PDF Verified.app` 的固定permission-only入口完成：2.201秒，零窗口/非激活；原生及嵌入检查一致，两权限均false，Python/daemon/proxy责任链均绑定Native17564。未发browser_prepare，未弹提示；四登记PID退出，manifest及strict/deep签名保持。

此为当前独立候选无窗口实际宿主证明，不冒称普通窗口nonce/三身份交接、系统设置开关状态或已获权全链路。没有读取真实配置或改变TCC。权限事项集中保留；普通窗口与交接剩余验收不打勾。见[本次回执](../../autonomous-engineering-2026-10-20/installed-permission/result.json)。

## Actual ordinary-window POST denial — 2026-10-20

本会话在用户总目标授权下继续补验，原领取保持。未修改当前独立安装候选，以新合成资料打开普通窗口，从原生菜单取得实际非提示check/current_instance回执；nonce桥绑定、身份/责任链已核验，两权限均false。实际窗口后端prepare POST携带规范Origin/CSRF，在输入current时返回installed_write_preflight_required。业务文件前后不变，暂停/空队列/无worker、无发送批准或worker_ref保持。原生界面明确准确App与双缺权能力。

正常Quit及父EOF/后端关闭有据，两个登记PID退出；1463安装清单、严格签名、原主App/配置保持。自建fixture初始null批准字段引起的GET失败已单列保留并修正为规范字段缺省，未计产品RED，未改生产实现。

经独立critical复核，仅勾原第5项预检无业务副作用；其余整票项保留未勾。当前是双缺权实际安装负例，不宣称逐项权限因果、完整错配/过期/TOCTOU矩阵、有效及跨版本交接正例或实际running-worker三身份通过。票保持open，真实申请暂停。见[安装普通窗口验收](../../autonomous-engineering-2026-10-20/native-write-denial/README.md)。

## Approved ticket revision — 2026-10-20

按用户同意的审计修订发布：更新当前停点及剩余验收，不改原领取、历史回执或既有依赖；不追加真实运行授权。新增证据保全工作可独立推进，其产物供本票适用范围引用，不代替本票原验收。

## Permission-enabled notification recheck — 2026-10-20

用户报告相关权限已开启后，本会话对独立候选与主安装版分别执行固定无提示权限入口。两个新原生进程及各自嵌入探针均一致返回辅助功能 false、屏幕录制 false；责任链核验一致。未推断系统设置状态或根因。两次零窗口、零提示、无 browser_prepare，八个登记 PID 独立核验全部退出；manifest 保持、strict/deep 签名通过，候选 1463 项清单匹配。

当前获权正例仍被阻塞，不新增验收勾选，不改变领取与依赖。真实申请保持暂停；本次权限结果不证明 26 号票原受限沙箱修复。见[新核验记录](../../permission-recheck-2026-10-20/README.md)。

## Main installation consolidation — 2026-10-20

按用户明确要求，已验证 PDF 候选功能资源接入固定主安装版 TomorrowStar.app / dev.tomorrowstar.desktop，恢复原主 Info.plist 并完成签名后再打开权限设置。整包隔离验收、安装后连续三次原生冷启动及实际合成 PDF 导出通过；普通合成材料窗口主身份、nonce桥、source/UI 与 loaded_mapping 核验通过，无 worker，正常 Quit 清理。27 个旧测试／备份 App 已可恢复归档，Applications 仅留主 App；旧证据不改写，真实配置保持。

系统设置已定位主 App，由用户重授；目前不宣称新主宿主获权、完整受限沙箱修复或剩余交接矩阵通过。原 Assignee、状态、依赖、验收勾选保持，真实申请仍暂停。见[主安装整合与回退记录](../../main-app-consolidation-2026-10-20/README.md)。

## Parallel execution group — 2026-10-20

[E — 宿主身份、权限与后台附着](../../open-ticket-parallel-plan-2026-10-20/README.md#e-identity)。跨票顺序、共享文件及原生实验串行约束见统一分组导航；本票状态、原领取、依赖与验收仍按上文执行。本次仅重组导航，不领取或扩大执行许可。

## Parallel implementation support — 2026-10-20

用户明确授权implement并发工程；本会话以01a1586d/root/identity_matrix补充源码门禁，不替换原领取。已复现并修复精确历史兼容组合在合法resume后被heartbeat租约无条件拒绝的问题。后续命令仍须同一managed进程／run／源码、原冻结配置和身份，以及未被撤销且明确支持该命令的精确兼容证据；生产历史白名单保持为空。新增真实loopback POST宿主／桥错配及持锁前过期拒绝反例。相关回归通过，详见[源码支持与限制](../../identity-matrix-support-2026-10-20/README.md)。

所有权限／包身份均为合成注入，未启动原生App或证明实际获权及旧worker交接。本票保持open、原领取及现有验收勾选；独立代码复核与整仓检查见[并发执行记录](../../parallel-implementation-2026-10-20/README.md)。

### 2026-10-20 — 实际HTTP策略矩阵支持验证

新增loopback实际POST的精确兼容恢复正例，以及配置、策略白名单、未声明恢复、缺少依据、相同版本标签但源码不同的五种拒绝。未启动替代worker，保留原Page／File；生产兼容白名单仍为空。 本次仅由01a1586d/root提供工程支持，不接管原领取，不更改Status、依赖或验收勾选。真实申请继续暂停。完整最终验证与集中待办见[本轮工程记录](../../remaining18-engineering-2026-10-20/README.md)。

### 2026-10-20 — 单一主安装版与签名连续性核对

已核对Applications中仅有TomorrowStar.app；系统App Management及Device Control and Data Access中旧测试App残留已定点移除，主App原开关保留，录屏列表也只有主App。签名审计确认相同bundle identifier不等于相同代码身份：此次资源变化使ad-hoc designated requirement改变，候选不能满足旧要求；本机无可用稳定签名身份。后续只更新主安装版，不再安装需要重复授权的测试身份。实际有效权限仍须最终安装后fresh核验，不能从开关外观推断。此项不代表原生观察或旧worker交接验收，也不恢复真实申请。详见[集中记录](../../remaining18-engineering-2026-10-20/README.md)。

### 2026-10-20 — 固定主签名及实际权限解除

用户授权修复后，现有唯一主App已迁移到固定本地CodeSigning证书；未构建或注册新App。用户完成钥匙串认证，并明确确认重建同一主App两项系统授权。两次独立非提示主宿主检查均为辅助功能true、录屏true，原生／嵌入一致，责任链及进程退出通过。构建和维护已加入证书／指定要求连续性检查，不回退临时签名，构建／验证不再产生.app副本。详见[稳定签名记录](../../stable-main-signing-2026-10-20/README.md)。

本次只解除签名／权限阻塞，不代替本票安装原生观察、旧worker交接或其他验收；原状态／领取／依赖保持，真实申请未恢复。


## 固定主安装版实际准入正反例 — 2026-10-20

本轮保留原领取及依赖，只用唯一主App。新无提示检查证明两权限有效与实际native/Python/daemon/proxy责任链，结合历史准确App双缺权拒绝，独立critical复核后勾原第1项；这不代替分别缺任一权限或完整nonce/TOCTOU矩阵。

普通主窗口实际check/current_instance/nonce桥绑定；actual prepare POST在native proof过期时409拒绝且业务字节不变，fresh check后200且保持paused。实际bootstrap worker和保留worker继续均200；后者须同窗口fresh native与10秒内fresh owned-page proof。一次仅刷新native却沿用28.75秒旧capture的resume被安全拒绝；补fresh原页后page/current、owner/accepted、reasons为空，沿原worker/Page合法继续。控制端source/UI、disk package loaded mapping及running managed worker/current_package兼容分别可见。

三身份子范围已取得实际证据，但第2项整体的安装配置不等价拒绝、第3项实际旧版本兼容和其余身份/逐权限/TOCTOU矩阵仍未齐，不勾整项。生产历史白名单仍为空，不写入未经验证组合。未决合成fill被保留，Submit/真实申请均未恢复。[完整支持证据、脚本失败及人审事项](../../remaining18-resumed-2026-10-20/README.md)。


### 本轮最终长暂停与重开边界

310秒实际paused后同worker/Page及未知intent保持，新的只读capture通过；不记作named scope续期。主App正常Quit后按设计保留独立worker，重开新控制端能只读观察同一原页且不重放intent，但填写兼容仍unknown；未尝试resume，更不是旧版本交接通过。最终只对本轮精确合成根登记worker执行明确SIGTERM清理，未知记录保留。[持久保全与最终回读](../../remaining18-resumed-2026-10-20/README.md#最终保全与停止)。

### 2026-10-20 — 本轮主安装版原生支持

同一固定签名主App新候选完成实际三身份子范围：controller/运行worker加载映射/磁盘包核对，compatibility=current_package verified；其独立readiness同时保留inputs state_changed及历史页限制，不能称整个readiness全绿。普通原生实际POST完成六种只会降级的proof fault×两种phase共12个拒绝，业务字节保持；移除fault后相同实际native check仍verified，prepare200且paused，随后原页新鲜观察+明确resume完成六项合成字段。fault为受控否定注入，不是实际分别撤销TCC；after-first-read未独立追踪锁阶段，不计完整TOCTOU。

重开同根保留原worker/Page；只读展示修复已由真实重开验证。process/compatibility仍unknown，fresh新宿主check存在时实际resume仍409且serial/run/page/job/受保护字节保持；该状态也有历史Page等复合拒绝原因，不冒充单一原因隔离。精确历史兼容交接、配置不等价与完整持锁TOCTOU仍欠缺，生产allowlist保持为空。原领取/状态/勾选不变。

详见[本轮统一记录](../../native-acceptance-next-2026-10-20/README.md)。


## Notes — 持续主线源码后继 2026-10-21

已退役逐请求包 / native 诊断 / epoch / UI 时效审批和 UI 自动宿主探针；实际目标、材料、语言、资格、owner / 锁、intent、未知结果、原页及 Submit 保护保留。真实保存失败 STOP 在 resume 前拒绝，测量日志失败只诊断；安装和实际能力验收未由源码结果替代。

完整默认离线：4263 passed, 2 skipped, 428 deselected in 661.45s (0:11:01)；[工程记录与原日志](../../automatic-mainline-2026-10-21/README.md)。旧三项 P2 的独立冻结记录及全部失败历史保留。Status、Assignee、依赖、既有勾选均不变，不新增票、不关闭本票；App 未更新，真实申请继续暂停，最终 Submit 始终人工。


## Notes — 28号票源码精简后继 2026-10-21

本次按票首2026-10-20当前精简范围继续源码工程。失效、过长或无法展开用户目录的显式Codex路径只降级模型步骤，资料读取、更正及流程状态保持可用，且不回退执行其他CLI。无关preparation_root不再阻止默认启动；选中的材料准备模式仍验证其目录。后台错误仅在实际工作区故障时要求修复目录。

单岗位普通动作及直接Worker恢复使用相关事实核对，不再枚举当前全职业库、研究benchmark或无关模型配置。材料采用/上传继续核对当前career/JD/contact、已采用lineage及精确PDF/附件；相关联系方式还包括当前career profile的固定事实。真实owner/锁、显式暂停、current选择、intent/attempt和未知结果不重放继续保留。完成分析保留原模型配置及研究benchmark修订；当前岗位或职业事实变化仍触发过期保护。Flow显式Continue/准备仍属于事实与材料采用边界，不声称所有路径零扫描。

既有逐操作包/epoch/短lease门禁退役及measurement故障隔离在本次基线已存在，本次回归复用，不冒称新增。原诊断、检查点失败停止及旧运行保护保留。以上仅为源码及隔离合成证据；安装App、实际权限、原页/附件及在途版本组合本次未运行，不用历史旧矩阵扩张票首当前范围。

最终统一完整默认离线：4552 passed、2 skipped；受影响集合：229 passed；本地合成浏览器：372 passed（两个不重叠分片）。集合重叠不累加。[本次源码、冻结清单、原日志及独立审计](../../ticket28-runtime-simplification-2026-10-21/README.md)。原Status、Assignee、依赖及既有验收勾选不变，不新建或关闭票。主App未更新或启动，真实申请继续暂停。


## Notes — 可用优先重排 2026-10-21

最新源码精简已验证；保留安装/适用在途交接，不复刻旧证明矩阵。

Priority/Triage/票头依赖按本次重排更新；旧边与原字节见[审计及变更账本](../../usable-first-wayfinder-audit-2026-10-21/README.md)。原 Status、Assignee、Interaction、既有验收勾选及全部旧正文保持，不领取、不关闭、不替用户接受。源码接口依赖不等于安装或真实操作许可；App 未更新，真实申请继续暂停。
