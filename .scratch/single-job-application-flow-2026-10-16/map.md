# 接通单岗位 JD 分析、专用简历与自动填写主流程

Label: wayfinder:map
Status: open
Assignee: 01a146b9/root
Created: 2026-10-16
Tracker: local-markdown

## Destination

把默认申请路径精简为一个岗位主控、共享材料能力和按职责保存的状态，在保留两库、人工编辑、断点及旧活动记录的前提下，完成推荐收录归档到逐岗投递的持续线性闭环。
最终Submit由用户操作，系统观察明确结果后继续下一岗；目标符合[APP-01–18](../../docs/single-job-flow.md)，源码、合成、安装和真实闭环证据各自明确。

## Notes

- 2026-10-22用户指定后继：[交付分经历简历生成并接续实际使用](../resume-agent-delivery-2026-10-22/map.md)持有新生成实现、其后唯一主App同步及旧任务占用核对；本图既有票状态、负责人和历史不变。当前允许Codex配合工具实际使用，其他高度自动化问题按反馈调整；下方暂停记录保留其时点含义。最终Submit人工，未知操作不重放。

- 2026-10-22：36第9项[材料/PDF独立核对](../ticket36-material-pdf-inputs-2026-10-22/README.md)3项通过。完整材料明确消费该location且两边均超128KB硬停；未证明无关重生成，不改生产。缩小对照旧PDF保持，未打印地点归档相同的实际Flow重复导出仍未覆盖；旧接受不重问，36保持claimed/第9部分，unknown/fill intent及真实申请暂停保持。

- 2026-10-22：36第9项[被分析省略来源更正的切片](../ticket36-omitted-source-2026-10-22/README.md)已完成RED/GREEN及一次默认离线回归（4672通过/2 skip），通过确切输入等价复用原分析结果，不调用模型。旧报告/attempt及有效事实确认保留；材料/PDF影响另判，36继续claimed且第9部分。新源码未安装，不跑旧安装矩阵，未知结果/fill intent及真实申请暂停保持。

- 2026-10-22：36号票已[核对当前11项](../ticket36-evidence-reconciliation-2026-10-22/README.md)，1—8/10/11满足、9部分，继续claimed及原负责人。仅剩更广职业资料/JD变化按实际消费判定影响和无关结果复用的边界；当前不是已复现bug，不重做已有两库更正/语言例外/同JD合并。不重问事实、不跑旧矩阵，unknown/fill intent及材料保持，真实申请继续暂停。

- 2026-10-21：37号票[按当前8项工程/合成要求结案](../ticket37-evidence-reconciliation-2026-10-21/README.md)，复用30/34/27、同一主App G1/G3及旧Submit接收端证据，无新实验/旧矩阵。34真实自然Submit闭环仍未验且暂停；未知结果、fill intent、旧owner、材料和接受记录保持。

- 2026-10-21：27号票[按票首当前5项恢复范围结案](../ticket27-installed-reconciliation-2026-10-21/README.md)，复用30映射、既有存储/进程竞争与同一主App G1/G3安装事实，不重跑旧矩阵。真实编译器原生在途中断、非空未知intent安装恢复及历史根因的限度保持，不新增旧实验门槛；未知结果和fill intent不变，真实申请继续暂停。

- 2026-10-21：34号票已[逐项复用30与同一主App证据](../ticket34-installed-reconciliation-2026-10-21/README.md)，当前1—7及9满足、第8部分；继续claimed，Triage为awaiting-real-acceptance。仅剩真实人工Submit→系统明确结果→下一岗实际接受，真实申请继续暂停。未知结果及fill intent保持，不重跑旧矩阵。
- 2026-10-21加载映射最终后继：[30实际安装worker映射及当前8项结案](../ticket30-worker-loaded-mapping-2026-10-21/README.md)已在用户明确授权后完成。首夹具失败和实际回滚保留；唯一实际worker映射匹配清单，正式四根/配置、旧unknown/fill intent及旧null回执保持，不重跑旧矩阵，真实申请继续暂停。下方较早6项满足/2项部分满足是此前核对时点。
- 2026-10-21：30号票已[复用安装证据逐项核对](../ticket30-installed-reconciliation-2026-10-21/README.md)，当前1—6项满足，7—8部分满足，仅待实际worker完整加载映射及覆盖范围；保持claimed及原负责人/依赖。不将真实Gmail或真实自然Submit列为本票合成缺口，未知结果和fill intent保留，真实申请继续暂停。
- 2026-10-21安装后继：同一主App已在明确维护授权下完成v3更新和隔离G0—G3，[维护记录](../main-app-maintenance-2026-10-21/README.md)保留失败、回滚及配置误开事故。下方“App暂不更新”是此前审计范围。真实申请继续暂停，未知结果和fill intent保持。
- 2026-10-21 可用优先重排：唯一当前顺序是[开发计划](../../docs/development-plan.md)；事实、逐票审计和旧依赖保存在[本轮审计](../usable-first-wayfinder-audit-2026-10-21/README.md)。详细实施/接受只放所属票，不复制开放票清单。
- 首个可用里程碑先复用已有顺序队列、完整材料、普通字段/上传、一次继续与人工 Submit 出口；优先补可确证的小功能，集中准备同一主 App 的有限支持旅程。完整目标及原验收不因此缩小，未支持的具体平台/导航明确保留。
- 本图继续执行扩展：已确认工程由 AFK 子票承接，源码依赖消费已具备公开接口，安装/真实后继由原票持有。按 Priority、再按文件顺序选择可领取源码票；只领未被占用的票。现有 Assignee 和未知 owner 不被清空或推断。
- 本轮只审计和重排，新增一个明确源码交接，不领取、实施、解决或关闭任何票；后续每会话按 Wayfinder 的单票规则推进。机械 frontier 不是 App 更新或真实申请授权，query 的 paused_route 表示本图真实路线仍暂停，不禁止既有授权下的合成源码建设。
- App 暂不更新、真实申请继续暂停。唯一已安装身份、原页、附件、用户编辑、未决 intent/attempt、真实 owner/锁与最终人工 Submit 保留。缺实际能力只影响相关操作，不复刻旧 nonce/epoch/短 lease 或全历史归因门槛。
- 复用[产品规范](../../docs/single-job-flow.md)与[CONVENTIONS](../../CONVENTIONS.md)。已确认目标不重复 grilling；真正出现未决人类选择才使用 grilling/domain-modeling，不能代答 HITL。
- 本轮前的地图全文移入现有[导航历史](README.md#可用优先重排前的完整地图)，原票正文、勾选与失败历史原样保留；当前票状态依实时查询，绿色源码、实际安装、真实体验和研究接受保持不同含义。

## Decisions so far

- [一次继续人工交接并观察Submit结果和可恢复跳过](issues/37-manual-submit-observation-continuation.md)已按当前8项结案：[逐项映射](../ticket37-evidence-reconciliation-2026-10-21/README.md)。一次Continue、原页人工合成提交、只读结果归属及skip/return已有适用证据；不改变34真实接受或恢复真实申请。

- [诊断原生会话中断并验证阶段恢复](issues/27-native-interruption-recovery.md)已按当前5项结案：[逐项证据及准确未验限度](../ticket27-installed-reconciliation-2026-10-21/README.md)。原负责人和旧正文/勾选保留；不同层次的恢复证据不改名为真实编译器故障注入，不代替34真实Submit闭环。

- [扩充安装版最小合成验收覆盖本轮故障](issues/30-installed-minimal-regression.md)已按当前8项合成验收结案：既有1—6分层证据复用，7—8由同一主App实际worker完整角色映射、PID/run及固定初始化/缺答案等待/暂停原页观察补齐。[实际结果与保全](../ticket30-worker-loaded-mapping-2026-10-21/README.md)保留readiness诊断unknown、历史null、失败及回滚；不代替34或真实材料/Submit闭环。
- [核验当前安装身份与在途版本交接](issues/28-installed-readiness-version-handover.md)已按票首当前7项精简范围关闭：[逐项证据映射](../ticket28-installed-evidence-2026-10-21/README.md)复用冻结源码和同一主App安装结果，不重跑旧证明矩阵。旧owner、未知结果及fill intent保全；worker完整加载映射unknown、活旧worker跨版本和非空未知intent恢复未新测的限度保留。30/34及真实接受不被覆盖。
- [独立限制最终Submit并退役请求批准](issues/38-independent-submit-boundary.md)已按独立出口职责关闭：冻结源码与合成接收端验证最终动作隔离、普通草稿/上传及原页人工交接；通用导航、结果消费和真实闭环仍由原专业票承接，既有队列追加失败单列。

- [定位未批准请求并恢复受控字段核验](issues/25-request-diagnostics-readback.md)已按限定工程范围关闭：
  最终冻结源码完整默认3896项通过，关键安装／实际worker字节对应。旧真实P08/P09原因未定，
  [核验当前安装身份与在途版本交接](issues/28-installed-readiness-version-handover.md)与[扩充安装版最小合成验收覆盖本轮故障](issues/30-installed-minimal-regression.md)及真实字段/附件验收不被覆盖；新初始化缺口见[核验 Ashby 公开初始化读取的精确请求边界](issues/33-ashby-public-bootstrap-review.md)。

- [持久化验收与回退证据](issues/32-durable-acceptance-and-rollback-evidence.md)：持久私人合成保全、失败拒绝、复制后字节／权限核验及清理后独立重开通过；真实安装与历史基线仍各守原门槛。

- [诊断并恢复 Workable 原页表单初始化失败](issues/22-workable-bootstrap-recovery.md)已关闭：当前安装版保留同页完成初始化，用户确认完整表单，App 扫描与两项字段回读通过；当时后续字段结果未知并停止；其后核验见 Notes，完整填写和上传另验。
- [恢复打开超时后仍保留的原页复核入口](issues/21-retained-page-recovery.md)已关闭：App 保存旧失败与恢复结论，并沿原 handle 完成明确重新核验；原运行后来终止的边界独立保留。

- [修正简历导出的内部审核文字](issues/19-resume-review-metadata.md)已关闭：当前安装版 PDF 已移除该内部状态行，来源/责任/边界保留；当时材料/发送范围由[通过 App 用 Gmail 真实岗位验证至人工提交前](issues/11-gmail-real-job.md)另验，当前自动材料规则以APP-07为准。

- [构建并在安装版 App 验证单岗位合成流程](issues/10-installed-app.md)已关闭：当前安装身份权限重新绑定后，通过原生窗口完成字段/PDF 上传与同页回读，最终 Submit 为零；真实岗位独立验收。

<!-- charting 不关闭票。已接受的范围写在 Notes；后续每行只链接已关闭票并概述，不复制其详细答案。 -->

- [修复原生父进程下 Codex CLI 的标准输入等待](issues/17-native-cli-stdin.md)已关闭：开放父管道的实际子进程 RED/GREEN 保留监控数据；安装版 Gmail 原超时已消失。
- [从 Gmail 推荐邮件自动取得岗位与原 JD](issues/14-gmail-recommendation-intake.md)已关闭：安装版窗口已实际读取推荐、取得原 JD 并区分完整/未知来源；未选岗或填写，真实链仍由[通过 App 用 Gmail 真实岗位验证至人工提交前](issues/11-gmail-real-job.md)核验。

- [修复单岗位 PDF 的同源内嵌预览](issues/16-pdf-preview-frame.md)已关闭：仅单岗位 PDF 成功响应允许同源嵌入，HTTP/完整离线通过；安装版同一 PDF 的原生文字与像素已可见。填写权限和真实岗位仍各自核验。

- [建立单岗位任务契约与持久恢复](issues/01-task-contract.md)：持久编排与严格 HTTP 接口已交付；重复启动、取消、输入漂移和进程中断已验证，独立审计的三个恢复缺陷已修复。

- [确定岗位匹配评分与未知证据规则](issues/02-match-policy.md)：用户确认 `documentary-match/v1`，采用下界/区间/覆盖、必需与加分 3∶1、部分支持 0.5，硬条件独立阻止冲突或未澄清的填写。
- [建立分析与简历共用的真实资料快照](issues/03-source-bundle.md)：全量来源、版本与责任边界已统一；个人资料可独立提供，分析不依赖 URL、worker 或公开网站，服务端验证资料变化。
- [以历史已投递与推进岗位审定匹配评分基准](issues/13-historical-match-benchmark.md)：用户确认保留公式，以当前资料重评原 JD 的历史区间作参照；来源与引擎版本绑定，失败对照和历史材料缺失均明确保留，不宣称预测验证通过。
- [接通 Codex 岗位分析与可解释匹配评分](issues/04-match-analysis.md)：后台分析、来源核验、输入漂移和历史参照已接通；离线全量通过，UI、材料与安装版业务验收继续由后继票负责。

- [复用岗位分析生成并确认专用简历](issues/05-tailored-resume.md)已关闭：当前分析选材、材料预览确认、显式重生成和 PDF 字节绑定已通过源码与合成整合验证。

- [接通受版本约束的单岗位自动填写](issues/06-single-worker.md)已关闭：批准材料与目标跨进程绑定，明确启动、旧占用和中断恢复通过源码与合成接口验收。

- [把单岗位五阶段流程接入 App 界面](issues/07-app-workspace.md)已关闭：推荐、匹配、材料、显式填写控制和复核入口通过当前合成 UI 回归，原生与真实发送另验。

- [将单岗位流程设为原生 App 默认运行方式](issues/08-native-runtime.md)已关闭：默认工作台、独立运行根、CLI/填写降级和退出恢复通过独立审计及冻结版本完整离线验证。
- [只读核验并保护旧版运行的岗位范围](issues/15-legacy-target-scope.md)已关闭：严格的全岗位字节与目标核验可建立只读占用范围，相同目标继续阻止；原件与未决动作不改写。
- [完成单岗位链路与故障恢复整体验证](issues/09-integration-verification.md)已关闭：新链实际单岗位子进程完成隔离上传、字段回读和同页恢复不重传；完整离线及复用浏览器故障回归通过，安装与真实业务另验。

- [统一旧动作核验与重新接管状态文案](issues/29-action-resolution-status-copy.md)：当前安装版11种合成原生显示、20项浏览器回归及只读副作用核验通过；工程展示范围关闭，真实申请暂停。

## Not yet specified

- 新平台的实际表单可能暴露目前无法具体命名的草稿、附件或最终动作差异；看到实例后再判断现有能力票是否足够，避免预建平台大全。
- 极少数旧活动记录可能出现当前样例未覆盖且确有重要歧义的组合；实例出现后最小处理对应岗位，不预建全历史迁移框架。
- 真实材料质量和用户体验可能暴露新的具体问题；既有验收已有承接，只有超出现有范围的新问题才产生后继。

## Out of scope

- 自动最终Submit、绕过MFA/CAPTCHA、编造个人事实、雇主联络或为测试强迫用户投递。
- 岗位并发、新数据库/框架/总调度器/权限服务/通用迁移平台、全平台普适性承诺。
- 自动找岗；只消费推荐邮件。邮件增量收录后的标签和归档在当前范围内，不再沿用旧“禁止收件箱修改”。
- 把研究Skill评审或历史Chrome/TCC完整根因作为日常投递前置；研究本身不因此完成。
- 结束其他聊天、抢占旧执行者、清理私人材料、篡改失败或已接受研究历史。
