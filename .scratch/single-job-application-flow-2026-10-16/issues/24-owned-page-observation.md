# 在 App 中可靠观察所属原申请页

Type: task
Label: wayfinder:task
Status: closed
Priority: P0
Interaction: AFK
Assignee: 01a150ef/root
Created: 2026-10-17
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [接通受版本约束的单岗位自动填写](06-single-worker.md)、[恢复打开超时后仍保留的原页复核入口](21-retained-page-recovery.md)

## 当前契约定位 — 2026-10-20

精确所属页、当前/历史值区分和只读观察能力继续复用；不把10秒新鲜证明或单独观察许可变成正常继续前置，28/37承接。

当前产品规范与执行顺序分别见[单岗位流程](../../../docs/single-job-flow.md)和[统一开发计划](../../../docs/development-plan.md)。本票既有Status、Assignee、完成记录和收据不变；关闭仅证明当时范围，不证明新规范已实现。下方与现行规范冲突的旧审批、白名单、总时间窗及运行门槛保留为历史，由现有后继承接，不重开、不追认，也不据此执行真实申请。

## Question

如何让 App 稳定定位并只读观察当前 worker 所属原页，避免读取另一 Chrome 实例、反复要求用户报告字段？

## Problem and priority

来源：[复盘 E02 与执行失误第 3 项](../test-findings-2026-10-17.md)。原页存在，但全局电脑控制可能选错实例或超时。P0：没有可靠原页观察，就不能验收填写或安全处理未知结果。

## Work and reuse

- 复用 worker 已持有的 Page、run/page 绑定、原 Cua client/socket 与原页恢复入口；先采用现有可用的 DOM/截图能力，不增加第二套浏览器执行器。
- 在 App 提供原页定位、当前 URL/标题、字段只读值与有效性、附件只读状态及截图；每份观察标明时刻、运行/页面和控制端/执行器版本。
- 区分当前观察、历史缓存、观察失败和原 owner/transport 已失效。named session 正常刷新不等于更换 owner。
- 观察不导航、不刷新、不聚焦后输入、不上传、不提交，不消费 intent 或清除停止原因。不能以另开页面、按 Chrome 名称选择或采用旧 profile 代替原页。

## Ownership

- `application_worker_browser.py`、`cua_driver.py` 的所属 Page 只读观察路径。
- `application_worker.py`、`application_flow.py`、`portal_static/application_flow.js` 的受绑定观察入口；复用对应现有测试。
- 多人共享文件先协调，不撤回其他修改。与 25 的网络诊断、29 的状态文案分别负责。

## Acceptance criteria

- [x] 两个 Chrome 实例和多个标签的合成用例中，App 始终观察精确所属 Page；无匹配页时明确失败，不自动选择其他实例。
- [x] paused、needs_recheck 和有未决 intent 时可以取得授权范围内的新鲜只读观察；旧缓存不能显示为当前值。
- [x] 原页 URL、标题、字段值/有效性、附件状态与截图按同一 run/page 绑定；字段观察不被解释为远端草稿已保存。
- [x] owner/transport 故障、关闭/替换页面或绑定漂移时停止，不创建新 client、不接管其他 profile。
- [x] 观察前后表单、附件、intent、核验结论和提交状态不变；网络写入、重传与 Submit 为零。
- [x] 受影响回归、当前包内以及安装版隔离原生观察分别通过；恢复真实页观察前另获用户恢复许可并记录实际结果。

## Verification and evidence

按 CONVENTIONS 先反例再修复。公开证据只用合成页面；真实截图/字段只进私有记录。不能只验定位成功或有 page_id 就关闭本票。

关闭范围为所属原页观察能力和安装版隔离验收，不要求先操作中止的真实申请。具体真实页观察由 30 后的 11/23 留证；当前执行器若不兼容新观察接口则明确停止，不借另一 transport 接管旧页。

## Authorization and stop boundary

本次只建票。原申请保持中止；执行开发、启动 App/浏览器及观察真实原页均不由本票创建自动授权。真实后继沿用第 31 票的限时与停止规则。

## Resolution comment

2026-10-17：由复盘新建，尚未领取、实现或验收；不改写已关闭第 21 票的原范围。

### 2026-10-19 — Authorized isolated engineering follow-up

用户明确要求继续剩余工程、跳过需其审批的内容并集中记录问题；真实申请继续暂停。本票前置已closed且原票无人领取，由`01a150ef/root`领取。只开发及验证所属原页观察能力，使用独立合成页面和隔离包；不观察或恢复旧真实页面、不采用旧profile、不消费旧intent、不触发真实写入。若原执行器不兼容新接口，保留明确停止与后续人审事项，不伪装接管。

### 2026-10-19 — Source and packaged synthetic progress; installed acceptance pending

已实现受capability与batch/run/page约束的暂停态观察请求，复用原worker持有的Page；旧执行器明确拒绝。原页隔离world读取字段，截图前后核对字段、frame/loader与URL，避免调用网页自定义getter。密码值隐藏，附件只读凭据不作为远端保存回执。原Cua client只作新鲜owner读取，不按URL重新选页、不建立另一浏览器。观察不结算intent，不生成用户结论；控制租约丢失但原worker仍有效时可只读回读。缓存过期或绑定改变明确降级。

源码与真实合成浏览器反例已覆盖多浏览器/多页、getter副作用、未知intent保持、旧接口拒绝、文档/字段/连接变化及owner过期；独立复核已修正主world getter风险。独立冻结包的实际模块与界面回归通过，导入来源核对为包内。当前源码另因退出诊断的保全测试修正而需要后继候选和完整回归，不将首轮全套失败改写为通过。

独立原生候选用包内解释器夹具后可启动并呈现；岗位详情入口经两次原生控制未发生预期变化，已停止该路径并保存问题，尚未到达本票观察入口的安装验收。HTTP就绪、源码或包内通过均不替代该门槛。本轮正常退出已回读原生请求、父EOF与后端关闭记录；原生与后端均已退出。票保持claimed，验收项暂不勾选，真实原页和真实申请未操作。

### 2026-10-19 — Installed successor reaches permission stop before any page

后继隔离包实际显示已准备的合成岗位，并通过原生界面单独启动包内填写器。执行器在 Cua 非提示权限核验处停止，日志明确为辅助功能或录屏权限不足；现有日志不能区分具体缺少哪一项。回读确认 worker 已退出、control 仍 paused、命令队列为空、未创建申请页、无 intent 或提交记录。没有修改权限、重试、另选浏览器或采用旧 profile。所属原页观察按钮保持不可用，因此本次是安装版停止反例，不能作为原页观察正例。停止和正常退出因果日志、界面、冻结包身份及原状态已私下保全。

安装正例仍需当前候选获得合规宿主权限后验证；这项需用户处理，暂列集中待办。继续推进无需授权变更的 28 号诊断与身份展示。票保持 claimed、整票验收框未勾，真实原页及真实申请未操作。

## Parallel execution group — 2026-10-20

[C — 原页观察与请求诊断](../../open-ticket-parallel-plan-2026-10-20/README.md#c-observation)。跨票顺序、共享文件及原生实验串行约束见统一分组导航；本票状态、原领取、依赖与验收仍按上文执行。本次仅重组导航，不领取或扩大执行许可。

### 2026-10-20 — 原页观察支持修复

截图后在原Cua client再次读取owner并核对原PID／window，owner失效时丢弃观察，不发布截图或字段。真实合成浏览器反例及修复回归通过；安装原生正例仍受主宿主权限阻塞。 本次仅由01a1586d/root提供工程支持，不接管原领取，不更改Status、依赖或验收勾选。真实申请继续暂停。完整最终验证与集中待办见[本轮工程记录](../../remaining18-engineering-2026-10-20/README.md)。

### 2026-10-20 — 固定主签名及实际权限解除

用户授权修复后，现有唯一主App已迁移到固定本地CodeSigning证书；未构建或注册新App。用户完成钥匙串认证，并明确确认重建同一主App两项系统授权。两次独立非提示主宿主检查均为辅助功能true、录屏true，原生／嵌入一致，责任链及进程退出通过。构建和维护已加入证书／指定要求连续性检查，不回退临时签名，构建／验证不再产生.app副本。详见[稳定签名记录](../../stable-main-signing-2026-10-20/README.md)。

本次只解除签名／权限阻塞，不代替本票安装原生观察、旧worker交接或其他验收；原状态／领取／依赖保持，真实申请未恢复。


## 主安装版实际原页观察 — 2026-10-20

用户授权继续并发工程，本轮保留原领取，使用唯一固定签名主App的--synthetic-browser及包内精确合成CLI。真实POST创建/分析/实际Chrome PDF导出并准备worker；实际managed worker、current_package兼容和同一原Page均有加载证明。先在paused queued状态capture，再由固定未知国家控件触发needs_recheck/readback_failed，保留未决fill intent；暂停后API和原生界面「只读观察所属原页」都取得新capture。字段值/valid、URL/title、空附件状态和PNG绑定同batch/run/page及实际worker source；观察没有被写成远端保存成功。

按独立critical复核勾第2/3项。第1/4/5/6项仍保持未完成；本轮空附件观察不证明未知路径上传或非空File保持，两实例/故障漂移/完整组合验收仍待。观察后intent、answers引用、动作历史和PDF摘要保持，未记录人工旧动作结论或重试未知写。原领取、状态、依赖保持，真实申请暂停。[本轮证据与集中人审](../../remaining18-resumed-2026-10-20/README.md)。

### 2026-10-20 — 同一主安装版剩余原生验收已补齐

在用户继续工程授权下，仍只用固定签名主 App。新候选的实际 Cua 原页取得同 run/page 字段、有效性、非空同一 JS File 与 PNG；受控 owner 绑定、真实 proxy 退出、页关闭/替换、字段/document 漂移均按具体 reason 停止且无替代 client。正例观察无事件/DOM 变化、网络写入、重传或 Submit，原 intent 与业务 job 保持。

同一候选另证两个真实 Chrome 同时存活，第二诊断保持两个标签的已声明阶段，普通主窗口仍读取原 worker PID/Page；恢复自有诊断后正常结束。正常 Quit/重开保留原 worker 启动代次、Page、六项合成字段；重开只读入口可用，执行身份未知仍拒绝恢复。

最终默认离线3744 passed，包内适用回归129 passed；当前包验签/合成导出及实际安装原生分别留证，独立critical复核支持六项工程验收。四个源码专用case不适用于强制strict的安装布局；最初原工具沙箱浏览器启动失败及各harness失败均原样保留，未伪装成功。

验收勾选补齐，原 Status/Assignee/依赖保持，供原领取统一结案；没有恢复真实页或申请。详见[本轮记录](../../native-acceptance-next-2026-10-20/README.md)与[独立审查](../../native-acceptance-next-2026-10-20/identity/native-evidence-review.md)。

### 2026-10-20 — 按用户授权与六项证据结案

用户明确要求“24既然六项验收已齐就按证据结案”。本轮重新核对前轮私人持久归档与原件的完整字节、模式和链接清单；当前唯一主 App 与被验收候选完全一致，固定签名验证通过。重新读取最终默认离线3744 passed、包内适用129 passed原始日志及独立审查，六项工程验收证据齐备，Status改为closed，保留原Assignee与依赖。详见[本轮只读复验](../../review-and-completion-2026-10-20/prior-evidence-readback.json)。

关闭范围为固定候选的所属原页观察能力及隔离安装验收；本轮没有重跑历史测试、启动App或恢复真实页。真实申请保持暂停，真实后继仍由30之后11/23按另行许可执行。此结案不代替25的intent核验、28的版本交接或30的组合验收。
