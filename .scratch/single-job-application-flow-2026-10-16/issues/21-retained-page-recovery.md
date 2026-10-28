# 恢复打开超时后仍保留的原页复核入口

Type: task
Label: wayfinder:task
Status: closed
Interaction: AFK
Assignee: 01a146b9/retained_page
Created: 2026-10-17
Parent: [接通单岗位 JD 分析、专用简历与自动填写主流程](../map.md)
Blocked by: [接通受版本约束的单岗位自动填写](06-single-worker.md)

## 当前契约定位 — 2026-10-20

复用原页保留与定位能力；恢复不再要求先填写核验来源再recheck/resume多次操作，37承接一次继续。

当前产品规范与执行顺序分别见[单岗位流程](../../../docs/single-job-flow.md)和[统一开发计划](../../../docs/development-plan.md)。本票既有Status、Assignee、完成记录和收据不变；关闭仅证明当时范围，不证明新规范已实现。下方与现行规范冲突的旧审批、白名单、总时间窗及运行门槛保留为历史，由现有后继承接，不重开、不追认，也不据此执行真实申请。

## Question

打开动作超时后，如何让 App 定位运行中仍持有的原页，保留未知动作并允许明确人工核验？

## Work and reuse

- 已确认缺陷：浏览器 Page 已注册且持续观察，但 `page_open` 只在导航和表单等待全部成功后设置；超时会使原页复核入口消失。
- 复用当前 runtime、page observation、人工交接和 recheck；区分原页仍被持有与页面准备成功。当前未保存精确超时消息，不能断言具体等待失败。
- 只有新鲜、同一运行和同一原页的观察可支持原页交接。未知 open intent 保留，不自动清除、重开或重传。
- 现有真实运行必须保留原 native、server、worker 与原 bundle；新服务不得把旧运行声称为新版本执行证据。并行 App 仅允许核验已有绑定后的原页 review，不取得 flow 写所有权，不写 flow 快照、不恢复执行或另起 worker；其余写操作继续拒绝。先验证兼容恢复与责任链，再选择安装方式。

## Ownership

- application_worker.py 的原页可用判断及 review 门禁；必要的 App 复核入口。
- 对应状态、接口和同页恢复测试。
- 不修改已批准材料、业务记录或未知动作，不绕过 App 直接发业务命令。

## Acceptance criteria

- [x] RED/GREEN 复现 `page_open=false` 且原页观察有效时的入口缺失；修复后可明确接管同页。
- [x] 过期、其他运行、关闭/崩溃、无 page id 的观察继续拒绝；未核验 intent 不因交接而清除。
- [x] 原页核验和明确 recheck 可沿用既有 handle；不自动重新打开或重传。
- [x] 后继安装版入口、实际加载身份和旧运行保留分别留证；完整离线检查通过。

## Verification and evidence

遵守 diagnosing-bugs、tdd、CONVENTIONS。公开证据只含合成状态及源/包版本；实际岗位、页面和进程身份保留在私有运行收据。真实业务只经 App。

## Resolution comment

2026-10-17：实际首次 open 超时进入 unknown；同一运行继续观察到原 Page，但 App 因 `page_open=false` 隐藏交接入口。已通过 App 暂停，原 worker 与浏览器均保留；未重开、填写、上传或提交。该具体恢复缺陷先修复，后续真实验收仍由第 11 票负责。

第一恢复包已通过隔离包验证并并行安装，原 native/server/bundle/worker 保持存活。原生 UI 的原页入口已出现，但实际 review 请求在重复扫描资料期间持有共享锁，使心跳暂时无法更新，随后被新鲜度门禁拒绝；未交接、未清除 intent、未重开。独立审核确认删除这次重复扫描后，既有 check_single 仍完整核验全部输入，且在同一锁内保留新鲜度前置检查；后继修复中。第一版完整离线为 2037 passed、1 failed、188 deselected；唯一失败为旧 partial-review 测试缺少运行观察 fixture，必须补真实合成运行而不降低生产门禁。原结果保留，不冒称通过。

修正版完整默认离线 **2043 passed、188 deselected，337.80s**，Ruff/format/diff 通过；隔离包验证、并行安装字节与签名、原生 UI 和原页交接均已通过，见[恢复验证证据](../assets/retained-page-recovery-verification-20261017.json)。原执行宿主、worker、浏览器及 bundle 保留，未知 open intent 未清除，批准 PDF 未变。新 UI 只发既有 review 命令，实际浏览器执行仍为上一已验证安装包。当前界面控制接口只能定位另一个浏览器实例，故原页内容与明确 recheck 仍待核验；保持 open，不以 handoff complete 冒充表单通过。

后续只读核查确认：既有 review 只取得窗口/目标绑定元数据，没有请求表单快照或截图；驱动的快照返回与引用缓存属于原传输的内存状态，没有现成落盘内容可核验。新连接不能凭公开会话名称或窗口身份继承原浏览器所有权；旧 worker 也没有预览命令。因此没有在保留旧运行条件下可安全补入的只读桥，未建立新会话、采用 profile 或改动 scope。当前原页内容核验需要用户实际观察；未知动作与暂停保留。

用户随后确认原页异常并提供截图；原生只读观察也短暂取得同一错误页：原地址可见，但站内显示网络错误，无申请表。后续电脑控制绑定切换到其他浏览器实例，条件检查已阻止重载；未刷新其他窗口、未填写或上传。初始化诊断由[第 22 票](22-workable-bootstrap-recovery.md)继续；本票的明确 recheck 仍未完成。

最终复核：原生窗口再次定位后，先由同一安装版 App 的工作台界面保存 `manual_stop` 及公开错误页依据，再在已交接的同一标签页执行明确刷新。原表单实际出现，用户也确认恢复。App 追加 `current_matches`，保留旧失败，执行明确 recheck 后清除旧 open intent；原 worker 在同一运行、同一 page handle 完成表单扫描，取得待补问题。未重新开页或上传。App 前端控制经内嵌浏览器访问同一安装版服务，执行仍由原 native/server/worker 负责；不把前端操作声称为新的原生包执行。见[最终复核边界](../assets/retained-page-final-recheck-20261017.json)。本票完成。

之后实际记录出现 `page_closed`、`context_closed`，原宿主及 worker/driver/browser 均已结束，无待核验 intent。该终止快照与原表单恢复证据已另存私有收据；不能声称旧 handle 现仍存活。后继运行、当前表单填写与受控附件上传仍由第 22/18/20/11 票验收。
