# 调查 Cua 冷启动前置窗口阻断

Type: task
Label: wayfinder:task
Execution: investigation
Interaction: AFK
Status: open
Assignee: root
Parent: [申请 worker 稳定性开发票](../README.md)
Blocked by: none
Created: 2026-10-13
Priority: P3
Triage: deferred-diagnostic

## 当前产品计划定位 — 2026-10-20

取消产品运行依赖，保留历史诊断。无窗口前置拒绝、Dock来源和历史argv缺口是本票研究；不能因为未自然复现或未证明唯一根因而禁止正常主App的当前产品验收。只对实际无法启动/无进展的操作暂停并说明原因，恢复功能由27/34承担。

以[当前产品规范](../../../docs/single-job-flow.md)和[唯一开发计划](../../../docs/development-plan.md)为当前执行依据；本节替代下方与之冲突的旧产品门槛，研究自身接受标准除外。Status、Assignee/未知owner、原依赖、历史勾选与收据均保留；本次只规划，没有执行或结案。

## What to execute

在新建、隔离的 Chrome/Cua 合成环境调查首个工作窗口创建前的
`cua_visibility_unknown / 无窗口启动出现了意外窗口`。
固定当前源码、驱动、启动参数和输入；建立可重复执行的前置守卫复现命令。
捕获首次拒绝的原始窗口条目、PID/启动代次、AppKit 和 WindowServer 时间边界，
判断拒绝是实际屏幕窗口、时序差异、内部弹窗还是身份/owner 不一致。

## Current evidence

- [历史失败](../../cua-locator-timeout-diagnosis-2026-10-13/replay-before-v2.log)
  发生在 `windowless_before`，早于 CDP、context 和工作页创建。
- [启动闪现修复](../../cua-startup-flash-diagnosis-2026-10-13/README.md)
  解决后续窗口创建动画，不能直接解释这个前置失败。
- [已有失败采集与 30 次对照](../../cua-prewindow-capture-2026-10-13/README.md)
  已补齐 production trace，但没有自然复现同类拒绝。
  历史窗口条目缺失；采样器依赖 AppKit 注册，存在注册前窗口和采样间隙边界。

## Execution limits

- 用户授权先推进本票。领取人为当前 chat “整理开放 tickets”的 root。
- 保留现有 worker、浏览器、页面、附件、私人状态和历史封存包。
- 只操作本次自有 profile、PID、启动代次、私有 Cua socket 和子进程组。
- 每次只启动一个自有 Chrome；新增负载最多两个离线进程组，并设总时限。
- 真实 ATS、模型调用、最终 Submit 和现有浏览器操作均为零。
- 首轮在 CDP 连接前结束。失败不自动重试，不延迟放行，不再次 hide 来掩盖拒绝。
- 没有自然复现前不声称根因，也不实施猜测修补。注入样例与自然故障分开记录。

## Acceptance

- [x] 已运行明确的复现命令；原始异常、阶段和输出可回读。
- [ ] 复现若成功，最小场景仍触发同一前置守卫；给出可证伪原因及独立对照。
- [x] 若未复现，报告全部采样分母、失败/中止、采样盲区和下一次失败所需证据；本票保持 open。
- [ ] 若有运行实现修补，保留 red/green 回归及原场景复验；守卫和发送限制不放宽。
- [x] 自有资源清理、现有资源保护、历史包及源码绑定完成回读。

## Progress

2026-10-13：用户明确要求建票并先推进冷启动调查。Root 已领取；先复用已有
前置命令和失败采集，再补足仅观察本次自有 PID 的注册前窗口采样。
执行证据将写入独立后继目录，不向旧封存目录重跑。

2026-10-13 首轮执行：[调查结果](../../cold-start-prewindow-investigation-2026-10-13/README.md)。
复用既有前置循环，增加仅记录自有 profile PID、覆盖 AppKit 登记前阶段的诊断采样器。
12 次原生合成采样全部通过，目标前置拒绝 0 次；4 项注入失败采集回归通过。
一项采样器未就绪的准备失败独立保留，未计为目标故障。
现有资源与私人文件回读保持，自有资源退出，生产启动和守卫未变。
历史根因仍未确认，最大采样间隙约 878 ms；不关闭本票，也不以这些通过推导绝对稳定性。

### 继续执行记录：隔离冷启动根因调查

用户要求继续定位，领取人 root 不变。新的证据目录为 [冷启动根因后继调查](../../cua-cold-start-rootcause-2026-10-13/README.md)。先执行当前守卫的无额外负载 / 双离线负载对照。首次 cohort 停止在 CDP 连接前。旧包与私人状态先建立只读保全基线。

### 后继调查结果：原生拒绝采集与 Space 对照

领取人 root；Status 保持 open。详见 [Cua 冷启动前置阻断：后继根因调查](../../cua-cold-start-rootcause-2026-10-13/README.md)。

- 当前代码 12 次、历史启动副本 6 次自然启动均通过，原自然阻断 0 次。历史单次根因仍未确认，未提交猜测性运行时修复。
- 10 次真实原生窗口对照中，4 次准确触发原守卫拒绝，Cua/window ID 与独立 WindowServer 轨迹一致，诊断先于清理；不算历史自然复现。
- 另 2 次对照断言失败保留：取消隐藏的窗口位于其他 Space，AppKit hidden=false 不能推出屏幕窗口。后继诊断已记录完整 Cua 响应和顶层 Space 信息。
- 4 项既有边界采集回归通过。初始 marker 排除和诊断导入 lint 记录保留；未来入口整理先保存执行版输入。
- 28 个自有 Chrome、28 个采样器和 18 个负载进程组退出。原进程、私人状态及 2,410 个历史文件保持；真实 ATS / 模型 / 自动最终 Submit 为 0。

### 固定 Space 后继执行

用户要求固定 Space 条件，root 继续领取；Status 保持 open。新目录 [固定 Space 冷启动对照](../../cua-fixed-space-investigation-2026-10-13/README.md)。采用本轮新建的空白 AppKit 窗口保持普通 / 自有全屏 Space，并连续核验 Space。自然阶段只启动独立无窗口 Chrome/Cua，仍在 CDP 前结束。Space 漂移单列中止，不在试验期间重新激活。历史包与私人状态另建保护基线。

### 固定 Space 后继结果：自然重开事件与最小机制

领取人 root；Status 保持 open。详见上面的后继报告与完整试验索引。

- 50 次实际试验中，38 次是有效无注入启动：37 次通过，1 次自然复现原拒绝。另有 2 次原生重开注入与 10 次准备/身份无效样本；30 次计划因首错停止而未执行，全部如实保留。
- 自然失败的 Space 1 全程不变。Chrome 隐藏确认后收到真实 `aevt/rapp` 原生重开事件，随后生成 New Tab。首次 Cua 与独立 WindowServer 的 PID、window ID、读取时间区间一致。
- 零负载、空 profile 的两次精确 PID 原生重开对照均触发同一守卫；相邻两次无注入对照通过。已定位本次自然故障机制，未把注入算作自然稳定性通过。
- 日志涉及 Dock。用户不确定是否当时操作过 Chrome，记录为未知；自然触发来源与历史失败同因尚未证明，保持 open。不据此放宽守卫或提交猜测修补。
- 固定普通/自有全屏 Space 的 LaunchServices / NSWorkspace 共 16 次有效对照通过，不能认定换启动 API 修复故障。原生版本与所有执行/归档输入绑定完成。
- 4 项边界回归通过。43 个新 Chrome、41 个私有发现服务、50 个采样器、16 个离线负载组清理；原进程、私人记录/PDF/设置及 2,742 个历史文件保持。118 个源码/测试/launcher 与锁文件未变，真实 ATS/模型/自动最终 Submit 为 0。

### 原生重开事件来源后继执行

用户要求追查 `aevt/rapp` 的触发来源。Root 继续领取，Status 保持 open。
新证据写入 [原生重开来源调查](../../cua-reopen-source-investigation-2026-10-13/README.md)。
先核对既有原始事件与发送/接收链，再用固定普通 Space、精确 PID 的激活与重开对照解释日志地址字段。
既有封存目录只读；不向真实 ATS 或现有浏览器发送事件，不把用户“不确定”改写为操作事实。

### 原生重开来源调查结果

2026-10-14：root 已完成本轮后继调查，Status 保持 open。详见 [来源证据与对照](../../cua-reopen-source-investigation-2026-10-13/README.md)。

- 已确认自然事件的直接发送者：Dock PID 717 的发送记录与自有 Chrome PID 81129 的接收记录匹配 `aevt/rapp`、returnID 20001，间隔约 55.273 ms。进程映像来自事件本身，超出先前仅有当前客户端映射的证明范围。
- 固定普通 Space 1 的 6 次隔离对照全部完成。2 次无注入通过；2 次精确 PID 重开均触发原拒绝并匹配已知发送者/接收者/returnID；1 次实际激活没有窗口并通过；另 1 次激活请求被系统拒绝，原断言失败保留。pytest 为 5 passed、1 failed。
- 接收日志中的地址描述与已知发送者一致。Dock 上游队列内容为 `<private>`，且所见队列消息晚于发送；没有明确点击、菜单动作或上游请求证据。用户回答仍为未知，不作人类操作归因。
- 用户补充的 Python 3.14.5 退出崩溃已保留私有原件并单列分析；具体脚本来源未确认，不计为冷启动目标拒绝。当前主试验使用锁定 Python 3.13.14。
- 6 个新 Chrome/私有服务/采样器和1 个控制器退出；原进程及私人记录/附件保持。3,412 个历史文件与 118 个执行源码/测试/launcher/锁文件无变，真实 ATS/模型/自动最终 Submit 为 0。

### Python 退出崩溃的独立来源与修复后继

2026-10-14：用户要求继续追查 PID 12530 并隔离复现/修复。见 [Python I/O 退出修复](../../python-io-exit-diagnosis-2026-10-14/README.md)。

- 高置信关联到 chat「解释当前问题」的隔离过滤代理；历史执行源码从四次变更重建并与原型摘要一致，探针时间覆盖原报告生命周期。历史 OS argv 未留存，保留该归因边界。
- 实际历史源码在假后端复现 SIGABRT；用户随后截图的 PID25292 对应本轮唯一故意崩溃红测。开放输入导致 `feed` 守护线程仍持 stdin 缓冲锁，提前输入 EOF 的对照通过。
- 修复后继用 selector/os.read 和退出前停止/join 解决；原开放输入复验通过，原21项与新增4项真实管道回归全部通过。原型与旧证据不覆盖，修复版另存相邻后继目录，未启用真实客户端代理。
- 原有资源、3,526 个历史文件及118个 TomorrowStar 源码/测试/launcher/锁文件保持，真实 ATS/模型为0。此独立 Python 故障不计入新的冷启动自然拒绝，冷启动票保持 open。

### 修复代理的真实 app-server 隔离复验

2026-10-14：用户授权真实 app-server 复验，领取人 root 不变。见 [真实 app-server 复验](../../real-appserver-io-fixed-verification-2026-10-14/README.md)。Status 保持 open。

- 固定原 CLI 摘要、Python 3.14.5 和已交付修复代理摘要，9 项真实后端检查通过。4 项后端先退出场景保持 stdin 开放，包含半帧；后端与代理独立退出记录均为0，代理退出0.053–0.113秒，无 I/O 锁 fatal。SIGTERM 转发与输入 EOF 场景也通过。
- 三组直接/代理配对核对协议大整数/中文 ID、错误响应、无关警告、审批与完整 sandbox 控制字段；Guardian enabled=true/false 配置保持。未执行真实 Guardian 决策或模型轮次。
- 1 次观察器准备失败及当时脚本保留，发生在真实 app-server 启动前。修正校准工具后复验，代理源码未变；原失败和旧代理不重跑、不覆盖。
- 9 个新后端和6个新代理均退出。现有进程、私人记录/附件和桌面配置保持，3,579 个旧封存文件与118个执行文件无变。桌面代理未启用，真实 ATS/模型为0。此独立复验不解释 Dock 上游触发来源，冷启动票保持 open。

## Scope reconciliation — 2026-10-19

本票继续持有无窗口启动前置拒绝与aevt/rapp来源调查。已证明Dock直接发送，不等于已证明Dock上游人类操作或全部历史失败同因。[旧单岗26](../../single-job-application-flow-2026-10-16/issues/26-native-chrome-startup-crash.md)另持有SIGABRT报告归属、同条件复现与修复。本票的守卫拒绝不可替代其崩溃因果证明，反之亦然；复用原始证据，不复制同一根因调查，不添加双向Blocked by。

Status=open、原Assignee=root和全部既有证据保留；本次只补责任边界，不重新启动Chrome／Cua或执行历史实验，真实申请继续暂停。

## Parallel execution group — 2026-10-20

[B — 启动与历史故障归因](../../open-ticket-parallel-plan-2026-10-20/README.md#b-startup)。跨票顺序、共享文件及原生实验串行约束见统一分组导航；本票状态、原领取、依赖与验收仍按上文执行。本次仅重组导航，不领取或扩大执行许可。


## Notes — 可用优先重排 2026-10-21

历史冷启动前窗口归因保留，不作为当前正常功能候选前置。

Priority/Triage/票头依赖按本次重排更新；旧边与原字节见[审计及变更账本](../../usable-first-wayfinder-audit-2026-10-21/README.md)。原 Status、Assignee、Interaction、既有验收勾选及全部旧正文保持，不领取、不关闭、不替用户接受。源码接口依赖不等于安装或真实操作许可；App 未更新，真实申请继续暂停。
