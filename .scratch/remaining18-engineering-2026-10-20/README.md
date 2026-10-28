# 剩余18票：并发工程与集中人工事项 — 2026-10-20

> 后继状态：本报告中的签名／权限失败是固定签名迁移前的历史快照。
> [稳定签名与最终两次权限通过记录](../stable-main-signing-2026-10-20/README.md)已完成；当前无需再为签名或主App权限操作。真实申请仍暂停。


用户授权继续并发无需人工确认的工程，真实申请继续暂停。本轮保留所有原Status、Assignee、Claim state、依赖和验收勾选；只追加支持进度，不因源码通过关闭原生／HITL票。

## 本轮工程

| 分支 | 已完成源码／合成工作 | 记录 |
| --- | --- | --- |
| 原页观察 | 复现截图期间owner失效却发布观察；截图后在同一client／PID／window再次只读核对，失效则丢弃 | [工程记录](../remaining18-observation-2026-10-20/README.md) |
| 在途PDF恢复 | 真实后端被终止且旧合成PDF子进程仍活着时，缺回执不再被当作已结束并允许重试；迟到裸PDF不自动采用 | [工程记录](../remaining18-recovery-2026-10-20/README.md) |
| HTTP门禁 | 实际POST精确兼容恢复正例与配置／策略／命令／来源五种拒绝，保留同worker／Page／File | [工程记录](../remaining18-post-matrix-2026-10-20/README.md) |
| 主安装版只读权限 | 固定permission-only入口新实例：辅助功能false、屏幕录制false；原生及嵌入证明一致，责任链／退出／签名／App字节／配置均核对，未创建浏览器或提示权限 | [Boolean结果](native-permission-result.json) |
| 主安装版更新 | 已完成完整源码冻结、包内验证和主安装版更新；测试契约后继与候选运行时代码完全一致，私有回退副本已核验；不把仅两处补丁描述成全部与旧安装版差异 | [打包记录](../remaining18-package-2026-10-20/README.md) |

## 唯一安装版与旧权限记录

系统设置的App Management及Device Control and Data Access旧测试条目均已定点移除；fresh界面只保留TomorrowStar.app且开关开启，其他App记录保留。Screen & System Audio Recording列表也只有主App且开关开启。安装目录也只有主App。随后repo-wide补查发现build及.scratch仍有旧.app，已在无运行进程时全部以同文件系统rename原样保全至私有.noindex目录下的.bundle-backup，原目录inode、Info及可执行文件哈希一致，逐项恢复映射保留；此前只清理安装目录的范围不完整。部分精确旧路径启动注销返回-10814，保留真实失败；不把移走文件等同于LS／Spotlight缓存已全部清除，不执行全库重置。该页开关不证明辅助功能或屏幕录制有效，实际权限另行核验。[清理回读](legacy-permission-cleanup.json)。后续只覆盖固定主安装版，备份留在私有非.app目录。

签名审计另确认：本次候选与旧安装版的bundle identifier相同，但ad-hoc designated requirement不同；候选不能通过旧requirement核验。原生代码页相同也不能避免资源封印变化引起身份变化。本机无有效codesigning identity；固定名称／路径不保证授权延续。长期消除重建后的重复授权需配置稳定签名身份，不放宽验证或复用其他App授权。[签名连续性核验](signature-continuity-result.json)。

## 需要用户处理：集中清单

| 时机 | 用户事项 | 准确边界 |
| --- | --- | --- |
| 已解决：主App权限 | 当前无需用户处理；固定签名后的两项授权已重建 | 两次独立实际主宿主检查均true，责任链及退出核对通过。旧false结果作为迁移前历史保留。 |
| 已解决：固定签名 | 当前无需用户处理；单一长期证书及私人配置已固定 | 构建／更新拒绝身份变化和临时签名回退，不再为日常开发创建新App。此前无有效身份属于迁移前快照。 |
| 当前领取待核实 | 职业清单核对票的historical-owner-unverified需确认原领取人或明确转交；两张旧稳定性票只有root和历史聊天名，正式接管前需定位 | 其他具名01a…执行者全部保留，本会话只加支持记录，不要求逐张重分配。职业封存票是unrecorded，不伪装成已知冲突。 |
| 当前材料人审 | 在现有安装界面逐组审核已经生成的准确草稿；随后按适用范围处理真实编译及新PDF的内容／排版／源一致性接受 | 不重问未变事实、不重选已确认样本、不重生成，也不代替用户接受。 |
| 领取明确后 | 审阅并接受已有完整职业清单后继的准确版本和覆盖 | 现成proposal／review／cutoff／父链技术核对已完成，技术绑定不等于语义接受，不重造清单。 |
| 对应前置完成后，当前不催办 | 准备版整体接受，以及浏览器速度／人工接管体验接受 | 前者等待新岗材料完成，后者等待唯一真实链证据；当前真实路线暂停，不为获取体验证据自动恢复。 |

本轮不要求解除真实申请暂停。已有事实、材料和隐私确认不推定任何恢复、上传或Submit许可。

## 全部18张票的当前边界

| 规范票据 | 状态／原领取 | 剩余类别 | 下一步或阻塞 |
| --- | --- | --- | --- |
| [调查 Cua 冷启动前置窗口阻断](../application-worker-stability/issues/07-cold-start-prewindow-investigation.md) | open / root | 历史证据／领取 | Dock直接发送已确认；上游触发和历史同因仍未知。先定位历史root，未获新证据不猜修补。 |
| [调查 CuaDriver 0.35 后台浏览器附着拒绝](../application-worker-stability/issues/10-cua-035-background-attach.md) | open / root | 权限／领取 | 主安装版固定入口新实例两项权限均false；完整后台附着正例待实际获权。历史root仅在接管时需定位。 |
| [确认浏览器速度与人工接管体验](../browser-efficiency-2026-10-17/issues/09-browser-efficiency-acceptance.md) | open / none | 后续人审 | 等待唯一真实单岗证据及用户速度／接管体验；当前不启动真实链。 |
| [接受准备版并记录剩余边界](../gmail-resume-preparation-2026-10-17/issues/16-release-closeout.md) | open / none | 后续人审 | 等待新岗完整材料票，再对准确版本、日常生成范围与限制整体接受。 |
| [在安装版验收真实新岗位完整简历生成](../gmail-resume-preparation-2026-10-17/issues/25-installed-real-job-full-cv.md) | open / 01a15491/root | 当前人审 | 已有草稿待逐组审核；复用确认事实，不重新分析／生成。随后单独处理适用编译许可和新PDF接受。 |
| [Reconcile Ambiguous, Excluded, and Unresolved Career Items](../phase-08-career-experience-inventory/issues/07-reconcile-ambiguous-excluded-and-unresolved-items.md) | claimed / 未记录／历史领取待核实 | 当前领取／人审 | 现成后继技术绑定已完成；先确认历史领取，再接受准确后继及覆盖，不重建proposal。 |
| [Seal the User-Accepted Inventory Revision](../phase-08-career-experience-inventory/issues/09-seal-the-user-accepted-inventory-revision.md) | open / 未记录／历史领取待核实 | 前置／领取 | 等准确后继接受及当前独立验证，再按既有封存流程执行；Claim state unrecorded保持。 |
| [通过 App 用 Gmail 真实岗位验证至人工提交前](../single-job-application-flow-2026-10-16/issues/11-gmail-real-job.md) | open / 01a146b9/root | 真实路线暂停 | 保持原暂停；本轮不启动、恢复、填写、上传或Submit。 |
| [核对交付范围并关闭单岗位主流程地图](../single-job-application-flow-2026-10-16/issues/12-delivery-closeout.md) | open / 01a146b9/root | 前置 | 交付核对可复用现有索引；等待真实单岗及全部子票证据，不能仅据文档关闭。 |
| [支持已观察到的通用 ATS 自定义必填控件](../single-job-application-flow-2026-10-16/issues/18-generic-ats-controls.md) | open / 01a146b9/ats_controls | 前置／真实路线暂停 | 现有实现不重复开发；等待安装组合及未来获准的真实控件回读。 |
| [支持 Workable 普通简历字段的受控上传与回读](../single-job-application-flow-2026-10-16/issues/20-workable-resume-upload.md) | open / 01a146b9/workable_upload | 前置／真实路线暂停 | 保留原上传实现与owner；等待安装组合、控件验收及真实恢复许可，不尝试真实上传。 |
| [支持当前岗位已确认邮箱的更正](../single-job-application-flow-2026-10-16/issues/23-current-job-email-correction.md) | open / 01a146b9/root | 前置／真实路线暂停 | 已确认邮箱不重问；真实更正与字段回读仍暂停。 |
| [在 App 中可靠观察所属原申请页](../single-job-application-flow-2026-10-16/issues/24-owned-page-observation.md) | claimed / 01a150ef/root | 本轮修复／权限 | 截图后owner失效的真实合成RED已修复；仍需当前候选安装原页观察正例，不借另一client接管。 |
| [定位未批准请求并恢复受控字段核验](../single-job-application-flow-2026-10-16/issues/25-request-diagnostics-readback.md) | open / none | 前置 | 正式等待原页观察结案；不移除依赖或领取。后续补请求序列、intent／字段／page及拒绝理由绑定。 |
| [复现并修复 Chrome 原生启动崩溃](../single-job-application-flow-2026-10-16/issues/26-native-chrome-startup-crash.md) | open / 01a155fd/root | 原环境／历史证据 | 原完整沙箱同条件GREEN和历史直接argv缺口仍未齐；主App正常导出不替代该证明，也不是再开TCC即可关闭。 |
| [诊断原生会话中断并验证阶段恢复](../single-job-application-flow-2026-10-16/issues/27-native-interruption-recovery.md) | open / 01a150ef/bounded_protocol | 本轮修复／原生工程 | 在途子进程且无完成回执时过早允许重试的RED已修复；安装原生屏障／进程代次／attempt关联及历史因果仍待原owner，不靠猜测时点。 |
| [核验当前安装身份与在途版本交接](../single-job-application-flow-2026-10-16/issues/28-installed-readiness-version-handover.md) | open / 01a150ef/bounded_protocol | 本轮矩阵／权限 | 新增真实loopback POST精确兼容正例与五种策略拒绝；实际主App获权、三身份、旧worker交接仍待；生产白名单为空。 |
| [扩充安装版最小合成验收覆盖本轮故障](../single-job-application-flow-2026-10-16/issues/30-installed-minimal-regression.md) | open / none | 前置 | 等待观察、诊断、崩溃、恢复及身份等前置；不以源码／包内部分验证代替安装组合验收。 |

完整离线回归首轮发现两项旧测试契约，已更新且扩展受影响52项通过；第二轮因启动器umask077使两个共享目录负例变成私有目录而失败，已保留并中止（非产品修复）。最终以正常umask022、单独0600日志完成完整后继回归，结果见下文。原始日志、实际包基线、配置摘要及进程定位只保存在明确的私人持久证据目录；公开结果使用Boolean字段。

## 最终核验与交付

正常umask022完整离线回归：**3626 passed、2 skipped、310 deselected**。Ruff、格式、diff检查通过；最终allowlist源码与测试后继完全一致，运行时代码及全部原生构建输入与已验证候选一致。

已直接更新唯一主安装路径，签名及全部候选文件字节／模式核对通过；旧安装版两份原样回退保全在私有非.app位置，配置未改变。[安装结果](installation-result.json)。最终主App非提示权限检查仍为辅助功能false、录屏false，原生与嵌入结果一致，责任链核对通过，所有本次诊断进程已退出。未创建浏览器、未提示授权、未打开常规任务界面。[权限结果](native-permission-result.json)。

归档后repo无旧TomorrowStar.app；LS与Spotlight已审计范围内仍存在的.app只有主安装版。旧Chrome测试身份不再出现在fresh LS转储，仍有一条已不存在路径的历史记录；不伪装全库已清空。[退役核验](retirement-result.json)。

剩余18票状态、原领取、依赖及验收勾选保持；本轮支持修复不替代原生验收或人审。真实申请继续暂停。[Boolean总结果](verification.json)。
