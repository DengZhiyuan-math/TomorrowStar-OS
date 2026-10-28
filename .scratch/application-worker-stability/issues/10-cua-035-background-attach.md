# 调查 CuaDriver 0.35 后台浏览器附着拒绝

Type: task
Label: wayfinder:task
Execution: investigation
Interaction: AFK
Status: open
Assignee: root
Parent: [申请 worker 稳定性开发票](../README.md)
Blocked by: none
Created: 2026-10-15

Claimed: 2026-10-15 by root; isolated synthetic investigation, background only.
Priority: P2
Triage: awaiting-app-update

## 当前产品计划定位 — 2026-10-20

后台附着/长暂停scope保留为适用Cua生命周期诊断与改进。复用已完成主App获权、同Page/File即时刷新证据；通用浏览器能实际运行时，不要求先证明完全无前台/窗口副作用才允许正常申请。登录态复用、本人验证和一次继续按当前规范；真实能力失败才停止相关操作。历史版本、权限及未验范围不追认完成。

以[当前产品规范](../../../docs/single-job-flow.md)和[唯一开发计划](../../../docs/development-plan.md)为当前执行依据；本节替代下方与之冲突的旧产品门槛，研究自身接受标准除外。Status、Assignee/未知owner、原依赖、历史勾选与收据均保留；本次只规划，没有执行或结案。

## What to execute

核对 CuaDriver 0.35.2 的 `browser_prepare(existing_profile)` 后台准入条件。
在自有空 profile、已确认 loopback CDP、PID/window/launch generation 的合成环境
复现前台风险拒绝，区分已有 CDP 复用、Chrome 提示判断与实际附着副作用。
先读真实工具 schema 与固定版本源码，给出可证伪对照，不猜测参数或弱化守卫。

## Current evidence

[升级后的实际预检](../../cua-mcp-native-verification-2026-10-15/native-run.log)
在附着前返回 `cua_refused`，提示可能把 Chrome 带到前台。本轮没有点击或自动重试。
MCP关闭和只读回执丢失的4项[原生传输检查](../../cua-mcp-native-verification-2026-10-15/transport-only/verification.json)通过，不算完整浏览器集成验收。

## Execution limits

- 不更新 TomorrowStar，不重启或操作原有 worker、Cua、浏览器、页面与附件。
- 只允许精确绑定本次自有 profile、PID、启动代次、私有 socket 和合成来源。
- 不自动切换 `foreground` delivery，不改变用户 Space 或激活窗口以绕过拒绝。
- 真实 ATS、模型、上传及最终 Submit 为0。未知结果不重试。
- 固定源码/驱动版本，保留拒绝与准备失败；新证据写入独立后继。

## Acceptance

- [x] 已绑定实际拒绝与输入，形成可运行的隔离对照。
- [x] 明确后台允许条件及副作用证据；不足时报告未验证，不猜测修补。
- [x] 准入修复保留 red/green，权限、前台和发送守卫保持。
- [x] 自有资源退出，原有资源和历史证据回读保持。
- [ ] 完整后台附着恢复：当前0.35.2不满足无前台副作用的受支持生命周期条件。

## 2026-10-15 执行结果

[隔离调查与后继证据](../../cua-035-background-attach-2026-10-15/README.md)。
根因：前台风险检查先于端点发现；worker 自建空 profile 不属于 driver-owned
生命周期。被动端点检测成功并不取得 profile 授权；省略策略后仍不能绑定。
原生拒绝和同进程对照均保存，未请求 foreground，未改变 Space 或守卫。

checkout 对已确认不兼容的0.35.2在浏览器创建前阻断，保存明确私有诊断。
真实驱动预检0.125227秒、资源创建0；相关23项与完整离线940项通过。
这只修复无效启动，不代表附着恢复。Status 保持 open，原始诊断持久私有保存。

## 2026-10-15 后继：driver-owned 生命周期准入

[后继调查与证据](../../cua-driver-owned-lifecycle-2026-10-15/README.md)。
核对官方稳定0.35.4的已签名候选包、真实 CLI schema，以及固定主分支
`dd6e146792951ba41ac7169d5531860595d06742`：仍没有受支持的无窗口后台
driver-owned 启动入口。连接池复用已批准的连接，不解决首次冷启动。
此外源码显示 `end_session` 清理会终止 driver-owned 浏览器，不能直接替换
当前刷新 Cua scope 时保留同一 Page/附件的模式；该行为没有做原生破坏性实验。

准入阻断补充0.35.4，保留新增 red；真实已安装0.35.2和私有0.35.4候选均在
资源创建前停止。没有安装升级、启动候选 daemon/Chrome 或操作真实 ATS。
相关24项、完整离线941项通过；119项未选入，不算完整浏览器接入验收。
完整后台附着仍未恢复，Status 保持 open。

继续准入需要同时满足：受支持的后台无窗口启动，以及 scope/会话更新时不结束
worker 所有的浏览器、Page 和附件。不能用前台启动后再隐藏、外部 profile 冒充
driver-owned、弱化授权或放宽发送守卫替代这些条件。

## 2026-10-15 后继：实现上游最小修复

用户明确授权实现上游修复并先在隔离合成环境复验。Assignee 仍为 root，Status 保持 open。
[本地补丁及复验报告](../../cua-upstream-owned-fix-2026-10-15/README.md)
固定上游 `c6cb386cf371fed3580ea1c5a238940ce4911641`，新增可选
`profile.windowless=true` 的 macOS 隐藏 driver-owned 启动。
使用原有隐式 transport owner 持有浏览器，named scope 重建只失效句柄。
可信所有权、进程 fingerprint、原生窗口与来源上限同时核验，没有增加全桌面或全 Chrome 授权。

复验又捕获 AppKit 过期状态读取：独立采样已隐藏，启动线程仍读到未隐藏。
改为主队列新鲜快照，保持原 3 秒期限。全部失败保留，未增加前台或隐藏 fallback。
冻结候选连续三轮真实 CuaDriver 合成复验通过：零启动页面，原 CDP target 和同一附件
`File` 对象保持；旧句柄、另一 transport、越界来源均拒绝；断开后自有资源清理完成。

core 983、macOS 库 568、Python MCP 10 项通过。状态读取修正前 CLI/MCP 全集
419 项通过，修正后补跑协议 schema 及真实代理恢复 4 项通过。跳过及未观察项见报告。
四个上游协议测试残留 daemon 经精确身份核对后清理；原有运行、封存证据、安装应用均保持。

- [x] 本地上游候选支持无窗口后台 driver-owned 启动。
- [x] 未过期 owner 内 named scope 更新保留原浏览器、页面和附件。
- [x] 拒绝、退出和保全证据通过；原始诊断持久私有保存。
- [x] 将候选接入 checkout worker 的实际生命周期与 scope 更新流程（2026-10-16，显式固定候选）。

本轮没有安装、推送、切前台或操作真实 ATS，也没有放行原版 0.35.2/0.35.4。
owner/manifest 到期续权和跨 daemon 保留未验证，原 TTL 保持。
本地候选通过不等于已安装 worker 的完整后台附着已恢复，因此原 Acceptance 的最后一项仍开放。

## 2026-10-16 后继：checkout 生命周期与 scope 接入

继续由 root 执行。[本轮变更、原生复验与保全](../../cua-worker-owned-integration-2026-10-16/README.md)。
`TS_CUA_DRIVER_BINARY` 只接受已复验候选的固定 SHA，未改变安装版准入。
私有 bounded daemon 与隐式 owner 常驻，named scope 更新复用同一 transport，必须重新绑定。
原 worker tick 只读保活，不增加线程或延长 TTL；新增来源拒绝，未知结果拒绝刷新且不重发。

接入时又捕获新标签还原已最小化窗口的动画。最小对照确认触发链后，候选窗口保持
normal 且应用 hidden；创建前后继续核验隐藏、非激活、零上屏，没有前台或 hide fallback。
原版路径保持，红测和原失败全部保留。

完整离线945项、受影响28项、合成 browser 7项通过；跳过及全目录历史样式失败单独记录。
真实 CuaDriver 的最终短程、310秒真实暂停后自动更新 scope、已完成点击回执丢失三个场景通过。
原 CDP target 和同一附件对象保持；未知 intent 保留，后续 tick 和强制刷新没有发送新请求。
正常、未知结果及所有保留失败的自有资源清理和既有状态回读见本轮报告。

保留一轮上游启动身份拒绝及一轮完整快照超时，底层原因未确认；没有用重试或放宽期限获得通过。
未知 transport 停止保活，仍受原 owner 到期/断开清理约束；未验证未知后跨 idle 到期保页。
Status 仍为 open。已安装应用、现有运行及封存证据保持，真实 ATS/模型/网络上传/Submit 为零。

本轮全目录 Ruff 检查曾刷新历史缓存，首次保全检查失败。已保留事故字节，按原始
SHA-256 精确恢复 8 个缓存并移出 3 个新增缓存；3881 个历史文件路径与哈希复核一致。
验证命令已排除 `.scratch` 并禁用缓存，后继完整样式检查通过；细节见本轮事故记录。

## 2026-10-16 后继：启动注册与完整快照根因修复

仍由 root 执行，Status 保持 open。[后继证据及可复验补丁](../../cua-startup-snapshot-rootcause-2026-10-16/README.md)。
自然拒绝的新诊断记录：主队列没有原生应用身份时，拒绝清理前的 PID 和独立 profile 参数仍可读。
原防护立即退出并清理；同一 native lookup 的一次不可读故障已在 public MCP 入口复现 red/green。
修复只在原 3 秒 posture 窗口等待注册，仍需同一 PID、原启动代次、隐藏、非激活和完成启动。
持续不可读仍拒绝，prepare 只有一次；没有重启、重新 pin 身份或 foreground fallback。

完整快照有两条全应用扫描路径：授权元数据补全与浏览器分类。现在只读取目标 PID 的元数据，
原进程 fingerprint 与授权校验保持。无关 plist 的 16 秒延迟在原 15 秒期限复现失败；修复后同一
故障输入不再被访问，连续 12 次完整快照通过。原页及同一附件对象、未知结果不重发继续复验。

上游 core 985、最终 macOS 569、checkout 受影响 28 项通过；完整离线 945 项在本轮较早候选通过。
原自然失败、无效故障输入及一次 macOS 并发端口测试失败均保留。完整命令和版本绑定见报告。
本轮另有测试筛选错误：显式 `-m not browser` 覆盖默认排除，误在沙箱启动合成 Chromium。
已中止精确测试 PID，保留 18 个失败和匹配 crash 报告；它们不算验收通过。默认离线命令已澄清。

本地候选可复验不代表已安装应用恢复。[最终保全回读](../../cua-startup-snapshot-rootcause-2026-10-16/preservation.json)
已确认原有运行、页面、附件与配置保持，3957 个历史文件和此前 509 个私有原始文件哈希一致，
1419 个已安装 TomorrowStar 文件及 Cua/rollback 均保持。新自有进程、socket 和 profile 已清理。
早期失败留下的两层空 metrics 目录在保存路径后仅用 rmdir 移除，原失败文件未改。
原始诊断保存在本轮独立 0700 持久私有目录。没有更新安装应用或操作真实 ATS。

## 2026-10-16 后继：完成授权范围内的修复与隔离复验

领取人仍为 root。[最终修复报告](../../cua-final-repair-audit-2026-10-16/README.md)
和[逐项边界审计](../../cua-final-repair-audit-2026-10-16/completion-audit.md)记录六项新增 red/green：
启动就绪越过原 3 秒期限、AppKit 缺失误报退出、未确认退出即删除 profile、
checkout 窗口发现越过原 2 秒期限，以及两个上游测试夹具的 FD 继承和 daemon 遗留。
进程活性改为精确内核启动代次，AppKit 的启动身份及隐藏条件继续单独核验。
真实拒绝终止对照下，旧候选删除待处理合成文件；修复候选保留该文件和 193 个 profile 文件。
随后独立控制器按 PID/launchDate 终止本轮自有 Chrome，profile 作为私有失败证据保留。

最终固定候选通过真实后台附着及 scope 更新、12 次完整快照、已完成点击的回执丢失、
一次注册不可读恢复、持续不可读拒绝和真实 SIGTERM。所有场景保持原期限，prepare 不重发，
原 Page/同一 File、来源上限、未知 intent 和发送守卫保持。采样 Space 固定，未观察到激活或上屏。
core 986、macOS 570、CLI 单元 327、CLI 集成 83、testkit 112 项通过；CLI 的 helper 子进程
结果不重复计数。恢复测试夹具修复后两项精确复验通过且无遗留 daemon。Python 离线 947、
最终受影响 30 项通过。跳过项、构建绑定与所有失败见报告。

授权的本地软件修复和隔离复验已完成。Status 仍为 open：原 Acceptance 中的已安装版本
完整附着验收尚未执行，用户明确要求不更新已安装应用；不会把本地候选通过改写为安装验收。
原 native-06/native-10 的唯一历史归因、跨 daemon/owner 到期后的保页不新增保证。
现有运行、封存证据和安装字节的最终保全结果见报告；原始诊断保存在独立 0700 持久私有目录。

## 2026-10-16 后继：接入已安装应用

用户明确授权安装；root 继续领取。[接入、回退和隔离验收](../../cua-installed-integration-2026-10-16/README.md)
将固定修复版作为 TomorrowStar 的包内辅助程序，保留官方 CuaDriver.app 的厂商签名与原字节。
原应用完整备份，安装前后严格签名有效；只有两个引擎文件、辅助程序/许可证及三个签名/清单文件变化。
不通过重签官方应用来冒充厂商身份，不迁移或扩大 TCC 授权。

暂存验收又捕获 profile 部分删除后的清理拒绝。保留自然失败及原 runtime 后，在真实删除入口
注入一次 ENOTEMPTY 复现；最小后继只在确认退出后、每次所有权标记仍匹配时作有限本地删除重试。
持续错误和所有权变化仍拒绝；原 3 秒姿态、2 秒窗口发现、15 秒 MCP 期限及未知结果不重发保持。
原候选与所有新失败独立封存，没有改写为通过。

- [x] 修复版已接入实际安装包，包内默认路径与固定 SHA 已回读。
- [x] 实际安装包的隔离合成验收完成：310 秒暂停后刷新 scope、原 Page/同一 File、未知回执不重发和完整快照。
- [x] 原包回退、现有进程/私人状态、官方驱动及历史证据通过最终回读。
- [ ] TomorrowStar GUI 宿主自身的 TCC 身份独立验收。本轮未启动 GUI；只读权限结果明确属于测试调用宿主，不能替代该项。

Status 保持 open，仅将本轮安装和隔离合成交付记为完成，不把调用宿主权限当成 GUI 权限。
未切前台、未放宽守卫、未启用桌面代理，真实 ATS/模型/上传/最终 Submit 均为零。

## 2026-10-16 后继：GUI 宿主 TCC 独立验证

root 继续领取。[原生宿主权限及后台调用报告](../../cua-gui-host-tcc-2026-10-16/README.md)
记录实际安装包的无窗口诊断入口、签名、完整回退与独立系统责任链核验。
入口在创建窗口或读取私人配置前分流，仅运行随包固定脚本，不接受任意命令或脚本路径。
原生宿主、Python、MCP 代理和 daemon 的 OS responsible PID 均为原生 TomorrowStar PID。
没有通过 advisory host_bundle_id 声明、包路径或 Codex 调用权限来代替真实身份验证。

- [x] GUI 宿主自身 TCC 身份已独立核验。原生 AX/CG 只读 API 与嵌入 MCP 均返回辅助功能=false、录屏=false。
- [x] 生产后台调用在浏览器创建前返回 `cua_permissions_required`；没有 browser_prepare、profile 或新 Chrome。
- [x] 独立采样未观察到激活或上屏，原生窗口数为零，Space 保持 1；签名、回退、既有运行及封存证据完成回读。
- [ ] GUI 宿主具备必要 TCC 权限后的完整后台浏览器验收。本轮因两项权限均缺失，未执行原页/附件、scope 或未知结果故障场景。

Status 保持 open。核验的是本轮重新本地签名后的实际安装身份；不据此推断旧签名或旧授权。
没有请求授权、打开系统设置、修改 TCC 数据库、放宽守卫或切前台。原始诊断保存于新的持久私有目录。
生产运行记录的 `closed=false` 原样保留；独立终态核验确认本轮 daemon、代理、socket、profile 均无遗留，
不改写该保守字段为成功。旧包内路径的合成通过记录仍保留，不重复记为本轮 GUI 全链路通过。

## Scope reconciliation — 2026-10-19

本票已完成的隔离包内附着及当前GUI缺权安全拒绝保留；剩余仍是该GUI宿主实际获权后的完整后台浏览器／原页／附件／scope与未知结果链，不能据其他宿主授权、合成通过或新材料旅程关闭。

[旧单岗28](../../single-job-application-flow-2026-10-16/issues/28-installed-readiness-version-handover.md)负责统一权限／身份／配置／版本交接及实际写前门禁，[旧单岗30](../../single-job-application-flow-2026-10-16/issues/30-installed-minimal-regression.md)负责字段／附件／恢复的组合安装验收。互相引用相同候选的有效证据，不互相代替结案，不添加双向Blocked by，也不重复请求系统授权或复制同一安装实验。

Status=open、原Assignee=root保持。本次不检查或改变系统权限，不启动原生工具，不恢复任何真实申请。

## Parallel execution group — 2026-10-20

[E — 宿主身份、权限与后台附着](../../open-ticket-parallel-plan-2026-10-20/README.md#e-identity)。跨票顺序、共享文件及原生实验串行约束见统一分组导航；本票状态、原领取、依赖与验收仍按上文执行。本次仅重组导航，不领取或扩大执行许可。


## 主安装版获权后原生支持验收 — 2026-10-20

本轮仅使用固定主App及固定签名。新实例非提示双权限、责任链、后台生产附着、同一Page/同一File即时scope刷新及清理实际通过；另在普通主窗口通过真实POST运行隔离合成worker，暂停/未决fill intent下的原页观察实际通过。详细来源、限制和失败保全见[本轮原生验收](../../remaining18-resumed-2026-10-20/README.md)。

原root已定位到历史聊天「整理开放 tickets」，不要求用户辨认，也不改原领取。当前固定unknown控件是readback_failed，不是故意丢失Cua回执；即时scope刷新不能代替长暂停后的named scope更新。此为原生子范围进展，完整链其余门槛仍未验收，Status保持open，真实申请暂停。


## Notes — 可用优先重排 2026-10-21

当前GUI后台链长暂停/未知结果专门验收留原票；不成为全部功能建设总门槛。

Priority/Triage/票头依赖按本次重排更新；旧边与原字节见[审计及变更账本](../../usable-first-wayfinder-audit-2026-10-21/README.md)。原 Status、Assignee、Interaction、既有验收勾选及全部旧正文保持，不领取、不关闭、不替用户接受。源码接口依赖不等于安装或真实操作许可；App 未更新，真实申请继续暂停。
