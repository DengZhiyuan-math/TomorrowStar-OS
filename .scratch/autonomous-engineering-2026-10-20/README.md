# 夜间推进与集中待处理 — 2026-10-20

用户授权持续推进剩余票，人工审核/权限请求集中保留，真实申请暂停。本表由本轮全 tracker 实时读取生成，保留全部未关闭票，不把没有机械 frontier 当作所有工作已经完成。已有领取不因聊天 idle/notLoaded 自动失效，未转派其他会话。

本轮完成：[Chrome 原生启动崩溃的主窗口失败验收](../chrome-remaining-acceptance-2026-10-19/native-window-followup/result.json)。固定合成 CLI 的旧版本查询超时被定位到30秒阶段；单次明确重试后实际 WKWebView 显示准确停止提示，刷新无新调用、无PDF/worker，正常退出清理。原完整沙箱同条件 GREEN 仍阻塞；历史失败不覆盖。

## 集中人工事项

- 真实准备/完整简历与体验验收：相关票所绑定的具体来源、摘要、资格、完整源和 PDF 由用户逐项审核；不把工程通过当作用户已接受。
- 当前原生宿主权限：保留各票已有非提示检查与责任链。没有为了本轮验收改系统权限，当前不能替用户批准新访问。
- 真实申请恢复及发送范围：继续暂停，不代填、不上传、不提交。
- 未记录/旧会话归属：保留原领取；人工移交只在需改变责任边界时处理。

## 全部未关闭票

| 票据 | 当前领取 | 待处理类别 | 直接依赖编号（只作索引） |
|---|---|---|---|
| [调查 Cua 冷启动前置窗口阻断](../application-worker-stability/issues/07-cold-start-prewindow-investigation.md) | root | 保留现有领取；先核对证据与下一可解锁子项 | 无直接依赖 |
| [调查 CuaDriver 0.35 后台浏览器附着拒绝](../application-worker-stability/issues/10-cua-035-background-attach.md) | root | 保留现有领取；先核对证据与下一可解锁子项 | 无直接依赖 |
| [确认浏览器速度与人工接管体验](../browser-efficiency-2026-10-17/issues/09-browser-efficiency-acceptance.md) | none | 人工审核，保留待办，不代答 | 08, 11 |
| [接受准备版并记录剩余边界](../gmail-resume-preparation-2026-10-17/issues/16-release-closeout.md) | none | 人工审核，保留待办，不代答 | 15, 25 |
| [在安装版验收真实新岗位完整简历生成](../gmail-resume-preparation-2026-10-17/issues/25-installed-real-job-full-cv.md) | 01a15491/root | 人工审核，保留待办，不代答 | 07, 15, 19 |
| [Reconcile Ambiguous, Excluded, and Unresolved Career Items](../phase-08-career-experience-inventory/issues/07-reconcile-ambiguous-excluded-and-unresolved-items.md) | 归属未记录 | 人工审核，保留待办，不代答 | 06 |
| [Seal the User-Accepted Inventory Revision](../phase-08-career-experience-inventory/issues/09-seal-the-user-accepted-inventory-revision.md) | 归属未记录 | 人工审核，保留待办，不代答 | 07, 08 |
| [通过 App 用 Gmail 真实岗位验证至人工提交前](../single-job-application-flow-2026-10-16/issues/11-gmail-real-job.md) | 01a146b9/root | 人工审核，保留待办，不代答 | 15, 10, 14, 15, 18, 19, 20, 21, 22, 23 |
| [核对交付范围并关闭单岗位主流程地图](../single-job-application-flow-2026-10-16/issues/12-delivery-closeout.md) | 01a146b9/root | 真实路径暂停；保留现有领取及未完成验收 | 11 |
| [支持已观察到的通用 ATS 自定义必填控件](../single-job-application-flow-2026-10-16/issues/18-generic-ats-controls.md) | 01a146b9/ats_controls | 真实路径暂停；保留现有领取及未完成验收 | 10, 30 |
| [支持 Workable 普通简历字段的受控上传与回读](../single-job-application-flow-2026-10-16/issues/20-workable-resume-upload.md) | 01a146b9/workable_upload | 真实路径暂停；保留现有领取及未完成验收 | 06, 18, 30 |
| [支持当前岗位已确认邮箱的更正](../single-job-application-flow-2026-10-16/issues/23-current-job-email-correction.md) | 01a146b9/root | 真实路径暂停；保留现有领取及未完成验收 | 06, 07, 30 |
| [在 App 中可靠观察所属原申请页](../single-job-application-flow-2026-10-16/issues/24-owned-page-observation.md) | 01a150ef/root | 真实路径暂停；保留现有领取及未完成验收 | 06, 21 |
| [定位未批准请求并恢复受控字段核验](../single-job-application-flow-2026-10-16/issues/25-request-diagnostics-readback.md) | none | 真实路径暂停；保留现有领取及未完成验收 | 24 |
| [复现并修复 Chrome 原生启动崩溃](../single-job-application-flow-2026-10-16/issues/26-native-chrome-startup-crash.md) | 01a155fd/root | 真实路径暂停；保留现有领取及未完成验收 | 08, 10 |
| [诊断原生会话中断并验证阶段恢复](../single-job-application-flow-2026-10-16/issues/27-native-interruption-recovery.md) | 01a150ef/bounded_protocol | 真实路径暂停；保留现有领取及未完成验收 | 08, 09 |
| [核验当前安装身份与在途版本交接](../single-job-application-flow-2026-10-16/issues/28-installed-readiness-version-handover.md) | 01a150ef/bounded_protocol | 真实路径暂停；保留现有领取及未完成验收 | 08, 10 |
| [扩充安装版最小合成验收覆盖本轮故障](../single-job-application-flow-2026-10-16/issues/30-installed-minimal-regression.md) | none | 真实路径暂停；保留现有领取及未完成验收 | 24, 25, 26, 27, 28, 29, 31 |

[完整机器快照](ticket-snapshot.json)保留每票依赖、门槛与状态。当前错误0、警告20、机械frontier为空。上述事项尚未完成，不标目标完成；后继继续从可独立验证的子范围推进。

## 后继：实际 HTTP POST 写前门禁回归

新增 `tests/test_installed_write_admission_http.py`，通过真实 loopback HTTP、Origin/CSRF 和路由进入写入入口。十项测试覆盖缺任一权限、nonce/责任链错配、过期/未知，以及检查后权限/nonce/配置变化；明确返回 `installed_write_preflight_required`，独立回读 flow/worker/applications 字节不变。有效证明可准备任务并接受明确 resume（spawn替身只记录一次，不创建进程）；Submit拒绝，状态保持。

新增10项通过；连同既有写前门禁和就绪检查共75项通过。Ruff/格式/diff通过。无生产代码改动，无真实模型/浏览器/ATS。[摘要及范围](admission-http/summary.json)和日志留存；日志明确是工具输出转录，不冒充原始逐字节进程日志。

此切片支持“核验当前安装身份与在途版本交接”和“扩充安装版最小合成验收覆盖本轮故障”。未改原领取和依赖，不关闭票：当前安装版实际三身份/交接及组合场景仍需独立证据，跨版本兼容正例未在本新增矩阵验完。

## 后继：当前独立候选的实际非提示权限核验

运行已安装 `TomorrowStar Chrome PDF Verified.app` 的固定 `--permission-check` 路由，2.201秒退出；该入口零窗口、不激活、不读取真实连接配置。实际原生与嵌入检查一致：辅助功能=false、录屏=false；Python/daemon/proxy 的OS responsible PID均为Native17564。权限提示、browser_prepare、真实ATS、上传和Submit均为零。四个登记进程退出，manifest保持、strict/deep签名有效。

[实际回执与身份](installed-permission/result.json)是本次独立候选无窗口权限诊断证据；不替代普通窗口nonce/命令证明、不证明用户系统设置开关状态，也不代表旧主App或其他签名已获权。当前需要用户集中处理的权限对象精确为此独立候选，后续获权须对实际最终候选重新核验；本轮不打开设置、不请求或变更授权。

## 后继：PDF保存与关闭竞争

[两种关闭时序及71项回归](pdf-shutdown-race/summary.json)通过。新增测试使用真实流程/简历store及有界子进程复制固定PDF；晚到输出保留未采用，重开保持版本/attempt/history，不重跑；明确核验后采用同一保存结果。没有生产代码变更。

这推进“诊断原生会话中断并验证阶段恢复”的独立源码证据；历史退出层、原生安装窗口/EOF、真实编译器子进程仍未证明，不提前关闭。测试子进程已正常退出，最后清理为有界兜底。前两次fixture错误保留，不宣称产品RED。

## 后继：状态文案票关闭

[统一旧动作核验与重新接管状态文案](../single-job-application-flow-2026-10-16/issues/29-action-resolution-status-copy.md)经独立六项审查关闭，限工程显示。未修改安装版11个原生场景、最新20项浏览器测试通过；暂停、intent与业务字节保持，1463包清单/签名/原主App配置保持。[最终证据](native-status-display/README.md)。本汇总前文“原生矩阵待验”已被本节替代；其他票和真实申请门槛不变。

## 后继：职业清单待审核包已定位并完成技术绑定

[Boolean核对](inventory-successor-binding.json)确认主私人资料库现有最新待接受包、proposal/review/manifest、准确Source universe及引用capture字节、cutoff与父链均匹配；首版接受来源仍在祖先链内。不要依据旧描述重复生成proposal。准确审核入口保留在主私人README的“最新完整待接受后继”，未把私人内容、路径、哈希或计数复制到本公开安全记录。

当前技术审核包已就绪；原领取人未核实，用户语义接受、accepted checkpoint与新封存仍缺。职业清单07保持claimed/historical-owner-unverified，09继续等待，不改变首版封存或任何私人记录。

## 后继：普通安装窗口实际POST缺权拒绝

[当前普通窗口证据](native-write-denial/README.md)完成nonce/身份责任链、非提示双缺权检查、实际prepare POST拒绝及业务字节不变。无worker/profile/批准/命令，正常退出后1463包清单、签名及原主App配置保持。独立复核后，仅勾28原第5项，无越权关闭。跨版本、running-worker和完整安装组合仍待。
