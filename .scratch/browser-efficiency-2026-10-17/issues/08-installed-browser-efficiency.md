# 在安装版复验已选浏览器快速路径

Type: task
Label: wayfinder:task
Status: closed
Triage: ready-for-agent
Completion: installed-synthetic-branches-verified
Priority: P1
Interaction: AFK
Assignee: 01a14a95/root
Created: 2026-10-17
Updated: 2026-10-18
Parent: [交付 DOM 优先的受控浏览器效率改进](../map.md)
Publication order: 21
Blocked by: 无；07及两份精确合成PDF测试授权门槛已满足。09实际用户体验接受单独保留。

**What to build:** 实际安装候选在隔离合成页使用已选快速路径，并提供准确版本、停止边界和回退办法。

## Acceptance criteria

- [x] 读回磁盘包、实际加载版本及配置；逐项演示候选已选范围。
- [x] 保留原页面、附件、profile、私人记录和暂停任务；unknown不重试、不切路线重做。
- [x] 可选只读JD来源不是安装验收的前置，原生未验证部分不能被宣传为通过。
- [x] 安装行为证据与源码/离线结果分别保存。

## Standing boundaries

复用已有能力和已完成研究；每票形成可独立演示或验证的用户行为。先做本票必要的最小整理，不引入推测性框架。个人材料留私有；保持真实申请暂停、未知动作停止及人工最终Submit。规划发布不授权真实邮箱／模型／ATS执行。任何代码变更均需本切片的有效验证。

## Ownership

沿用票头Status和Assignee；本次仅发布，未领取或执行。先核对frontier并写入唯一领取人，再做工作；多人共享模块时协调，不回退其他人的改动。HITL必须由用户实际参与，不能由代理代答。

## Comments

### 2026-10-18 — Installed synthetic engineering verification completed

用户已手动Cancel系统钥匙串提示；真实材料/申请仍暂停。两份精确新合成PDF的测试确认、manual派发前停止/原页交接、unknown单次动作保留及App冷重开无重放均实测完成。发现原生旧动作结论下拉框在每1.2s页面心跳重绘时失效，保留原失败后仅从渲染比较排除page_observation.at；其它页面/intent/错误/控制变化仍更新。真实行为先红后绿，11项受影响浏览器通过，完整默认离线2555 passed/270 deselected、exit0，静态及冻结245文件检查通过。

后继候选aea59ef4…6216的独立安装App已验证75引擎及deep/strict签名、实际UI加载；完整旧包可回退。全包仅UI/候选清单/对应签名四路径不同，全部Python/helper字节与前驱相同，原unknown worker/Chrome未停止或升级。原生UI保存一条manual_stop，来源明确代理合成测试；再次App冷重开后完整intent/结论/来源/附件保持、继续接管disabled。动作记录8→8→8、原页一致、files/Submit均0。原三个App及九项私人元数据保持。

[最终报告与范围](../../browser-efficiency-release-2026-10-18/branches-authorized/README.md)、[机器核验](../../browser-efficiency-release-2026-10-18/branches-authorized/verification-final.json)、[独立终审](../../browser-efficiency-release-2026-10-18/branches-authorized/independent-audit.md)已逐项回读。08按合成工程复验结案，正式进度20/23。DOM/manual采用字节相同的前驱执行证据，后继安装验证同一unknown现场的UI保存与冷重开；不重放旧unknown补演示。新后台processunknown，不能宣称worker重启、重新受管或恢复执行。原生trusted输入/真实ATS/安装新性能数字/09人工接受均未代答。钥匙串取消不等于系统问题修复；用户提供的Chrome for Testing启动崩溃单列为环境失败。以下未完成/拒绝记录为历史，均保留。

### 2026-10-18 — Two exact synthetic PDFs authorized; manual passed; unknown stopped

用户明确授权 manual / unknown 两份新合成PDF测试确认，已通过原生安装App执行。manual实测unsupported_control，国家route_decision=manual/not_sent，无国家intent；姓名/邮箱verified，原页国家未改、files/Submit均0；handoffcomplete后显式暂停，保存证据后释放该已知未发送测试页。unknown单次国家动作readback_failed，完整intent与attempt ce97935e…ef60保留、paused、重新接管disabled，未重试/切路线/重建批次，原页与附件/profile保留。

[本轮证据与当前限制](../../browser-efficiency-release-2026-10-18/branches-authorized/README.md)：未知结论尚未保存、同根App冷重开仍未完成，不能使用DOM冷重开代替。用户报告Chrome钥匙串提示；没有重置或改钥匙串，Cua明确禁止操作UserNotificationCenter，已请用户手动Cancel。安装包签名/75引擎字节前后通过，原三个App及九项私人元数据midpoint保持。08仍open；不再缺两份合成PDF测试授权，真实审核/申请仍暂停，HITL未接受。

### 2026-10-18 — Exact-material authority exercised; DOM passed; remaining scenarios retained

用户明确授权仅对原 `b002d206…b0570` 合成PDF执行测试确认，真实材料与申请仍暂停。原任务确认与准备后，首次启动在开页前被 `single_binding_invalid / inputs changed` 守卫拦截。失败记录保留；只读单变量对照确认子进程漏传专用CLI身份。修复仅给严格合成子进程补回由已验证根目录推导的CLI路径，未改守卫、原PDF或原任务。针对性先红后绿55通过，完整默认离线2555通过/269排除；后继冻结候选 `65f58a09…1711` 仅替换独立测试App并保留回退包，75引擎文件和deep/strict签名前后通过。

[本轮报告](../../browser-efficiency-release-2026-10-18/continuation-authorized/README.md)及[机器核验](../../browser-efficiency-release-2026-10-18/continuation-authorized/verification.json)：实际安装填写三个字段verified，姓名/邮箱DOM、国家只读下拉框窄DOM；原页回读值正确、备注未变，文件数及Submit计数均0。handoff=complete；App实际冷重开后原worker/browser仍存活，旧动作/原页/字段保留、无重放。新后台进程状态unknown且control_connection_lost，不能声明重新受管或可恢复执行，更不能替代unknown动作或worker重启验收。

manual及unknown分别通过安装App生成并预览新合成PDF；两份均保持materials_confirmed=false、worker_ref=null，无批次/任务派发。原授权限定同一PDF，因此新具体材料的测试确认集中留在待审核清单。08仍open/needs-info，正式进度仍19/23。原页取证后已通过App释放并停止本轮自有进程，六个端口关闭；原三个App及九项私人元数据保持。历史性能比较和人工体验接受状态不改写。

### 2026-10-18 — Installed partial evidence; review gate retained

[安装部分验证](../../browser-efficiency-release-2026-10-18/installed-partial-verification.json)已保存：独立新路径安装、75引擎文件及实际加载进程/4个UI资源、前后deep/strict签名通过；实际原生选岗→合成分析→具体PDF预览完成，实际持久字段materials_confirmed=false、worker_ref=null。退出与冷重开后整个待审任务及40个任务/fixture文件完全一致，4个独立启动stdout/stderr不计入保存内容。原3个App哈希、九项私人元数据未变，两次自有App/backend均退出且端口关闭。[实际守卫映射](../../browser-efficiency-release-2026-10-18/installed-dom/actual-review-guards.json)说明：旧application模式没有pdf_approval/worker_batch_id键，早期摘要.get()产生的null不是实际审批记录，原始快照保留。

在具体合成PDF确认处，自动审批明确拒绝代理代替用户延期的人工审核（即使合成材料）；未提交确认，撤销此前未提交勾选，没有通过API、底层方法或另一条执行链绕过。DOM/manual/unknown安装填写尚未执行，不能标安装快路径已通过。本票保持open/needs-info，由[统一待审核清单](../../tomorrowstar-delivery-2026-10-17/review-queue.md)集中保留这一具体确认。真实申请继续暂停。

首次Cua getApp调用跨约8.6小时、只返回窗口外壳，原因未指认；随后工具/后端/窗口正常响应，单独留作工具观察限制，不算App启动或性能样本。

### 2026-10-18 — Execution claim

07已按真实五对组合、六类诊断及独立逐臂复核结案，root领取08。候选4809f867…与完整2554离线/86浏览器源码门槛逐项相同，独立暂存包75引擎文件及deep/strict签名通过。将安装到新路径和独立bundle ID，用安装解释器生成全新dom/manual/unknown合成目录，实际原生App→backend→bundled worker验证；不替换原App、不接入真实账号或旧任务。原程序哈希及九项私人元数据已留本轮新基线；实际安装、加载、冷恢复与最终保全另证，不以源码测试冒充。真实申请继续暂停。

### 2026-10-17 — Approved ticket migration

用户已批准23张拆分及迁移。此票沿用原路径和身份，采用批准后的纵向交付契约；此前内容保存在不可覆盖的历史快照中，不丢失原问题、依赖、评论或验收记录。

- [批准的逐票草案](../../tomorrowstar-ticket-consolidation-2026-10-17/drafts/21-installed-browser-path.md)。
- [迁移前完整原文](../../tomorrowstar-ticket-consolidation-2026-10-17/history/pre-publication/.scratch/browser-efficiency-2026-10-17/issues/08-installed-browser-efficiency.md)。
- [当前正式导航与全部承接关系](../../tomorrowstar-ticket-consolidation-2026-10-17/README.md)。

本次迁移不是实现完成或用户产品接受；真实申请继续暂停。
