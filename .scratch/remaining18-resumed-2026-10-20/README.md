# 剩余18票：主安装版原生验收继续 — 2026-10-20

本轮优先复验此前被权限阻塞的原生子项，只使用现有唯一主 App
`~/Applications/TomorrowStar.app`、`dev.tomorrowstar.desktop` 与固定签名。
没有构建、安装或注册另一个 App，没有修改业务源码。真实申请继续暂停。
当前固定安装包与清单绑定；不把它称为整个最新工作树。工作树原有大量未提交内容保持。

## 已完成的实际原生子项

| 范围 | 实际证据与结论 |
| --- | --- |
| 主宿主权限 | fresh 无提示检查两权限均有效；native/Python/权限 daemon/proxy 责任链核对通过，登记进程退出，主包签名/字节/模式保持。 |
| 后台生产附着 | 固定 `--background-check` 实际经过主 App，保留同 CDP target 和同一 File 对象，原 transport 上即时更新 scope，profile/socket/进程清理通过。Chrome 由 LaunchServices 启动而自身负责；浏览器 daemon 由主 App 负责。 |
| 普通窗口准入 | 实际原生菜单产生 current-instance/nonce 桥证明；controller source/UI、disk package loaded mapping 和实际 managed worker 分别可见，current-package 命令兼容有测量依据。 |
| 实际 POST 正反例 | 已确认合成材料的 prepare 在 native proof 过期时 409，业务字节不变；fresh check 后 200 且保持 paused。实际 bootstrap 和 retained resume 均通过。 |
| 原页新鲜度 | 只更新 native 但沿用约28.75秒原页 capture 的继续命令被拒绝；同一次窗口内重新 observe 后，native verified / page current / owner accepted、reasons为空，原 worker/Page 合法继续。未放宽原30秒/10秒期限。 |
| 暂停与未决动作 | fixed unknown 国家控件实际产生 needs_recheck/readback_failed。暂停后通过 API 和主 App 的“只读观察所属原页”取得字段、有效性、附件可见状态及同页PNG；未决 intent、答案引用、动作历史与PDF保持。没有代填人工旧动作结论。 |
| 双 Chrome | 从同一主 App 固定诊断入口建立第二个隔离 Chrome，同时观察第一个暂停 worker；两 PID/profile 独立且采集完成时均存活，仍只观察原 worker/Page。仅短暂 SIGSTOP/CONT 本次新建第二诊断 Python 子进程以固定重叠窗口，原 worker未中断，第二诊断随后通过。 |
| 长暂停 | 实际暂停310秒后，同worker PID/run/Page及未决intent、答案引用、动作历史和PDF保持；新只读capture成功。仅证明owner保活，不证明named scope续期或未知路径非空File保持。 |
| 正常重开 | 已完成真实系统Chrome PDF后，用户重启。原native日志为正常Quit批准及父管道关闭；相同合成根重开后原task/resume/PDF及未确认状态保留，没有重复分析、生成或导出。此非在途/异常中断验收。 |

原生界面已实际显示 Synthetic Person、synthetic@example.invalid、保留的 Untouched note、
空国家与空文件字段，以及结果待核验、暂停和禁用继续按钮。空附件观察不能证明已上传，
也不能据此断言未上传；后台独立诊断中的同一 File 正例与未知控件路线分别记录。

## 票据回写与未完成边界

独立 critical 复核后，只勾选有完整证据的三个原条件：

- [24](../single-job-application-flow-2026-10-16/issues/24-owned-page-observation.md)：第2项暂停/needs_recheck/未决 intent 的新鲜观察，第3项同 run/page 绑定。
- [28](../single-job-application-flow-2026-10-16/issues/28-installed-readiness-version-handover.md)：第1项当前双权限与责任链，并引用保留的实际双缺权安全拒绝。

24的双实例、故障漂移、完整前后状态和整组安装验收仍分别需要完整证明。
28的三身份取得实际子范围证据，但配置不等价安装拒绝、逐权限/nonce/TOCTOU矩阵、
实际精确旧worker兼容交接仍未齐；生产历史兼容白名单保持为空。
没有把当前包兼容当成旧版本交接，也没有用“全拒绝”替代合法正例。

稳定性10还缺GUI宿主上的故意丢失Cua回执/不重发及完整后继scope场景；本轮的
readback_failed不是回执丢失。26原完整沙箱同条件因果GREEN、27真实在途子进程屏障
和25被拒请求/intent/字段/Page持久关联仍未齐。30与真实18/20/23/11的原前置保留。
所有18票状态、原领取及依赖保持；没有因部分原生成功关闭整票。

## 集中需要用户处理

| 时机 | 所需人审或领取决定 |
| --- | --- |
| 当前：材料25 | 在现有已生成准确版本上逐组审核完整源；随后按适用范围真实编译，并接受具体新PDF的内容、版式和源一致性。不重新生成或重复确认不变事实。 |
| 当前：职业07 | 确认 historical-owner-unverified 的领取/转交，并语义审核现成 pending successor 的准确版本与覆盖。技术绑定已核对，不重造清单。 |
| 前置完成后：职业09 | 领取尚未记录；07准确接受且Phase7前置有效后，才可按原封存器发布后继。 |
| 后续：材料16、效率09 | 分别等待材料25完成、未来获准的真实单岗11证据后再做人审；当前不要求解除真实申请暂停。 |

稳定性07/10的历史root已实时定位为聊天“整理开放 tickets”，无需用户辨认。
其他具名执行者保留；本轮支持验收不替换其领取。

## 失败与证据保全

- 首次后台外层harness误要求LaunchServices Chrome也由native负责；真实诊断已通过，独立终态核对修正了该断言。原脚本/失败保留，不计产品RED。
- 首个ordinary fixture的合成CLI来自较新工作树，被包内严格契约拒绝；marker/目录/权限均正确。新fixture采用安装包要求的精确CLI后通过，不改App或守卫。原失败输入保留。
- 本地helper曾发生Python参数重名（POST前失败），另一次observe使用错误payload结构而安全409；修正为文档规定的嵌套binding后通过。均不计产品缺陷。
- 双Chrome首轮第二诊断在原页截图完成前已退出，不能证明完整重叠。后继只冻结本次新诊断子进程固定重叠，不改原worker；保留早退出样本，不把它计为产品失败。
- 早期 `getApp` 隐式打开普通主窗口，正常启动保存配置时重序列化JSON。独立复核通过当前值、字段排列与Swift斜杠编码精确重建旧SHA，确认仅字段顺序变化、语义保持；不宣称整轮配置字节不变，也未覆盖回写全局配置。

原生原始日志、nonce/PID/路径、完整包清单、合成根和API回执只保存到私人持久证据目录；
公开[总结果](verification.json)使用Boolean字段。独立sampler只连续观察主native窗口/激活，
不扩称Chrome/Space全程采样；Cua版本提示也不能被解释成所有网络调用为零。
明确保持真实模型、Gmail、ATS、上传和Submit为零。

## 并发验证与导航

本轮默认离线聚焦回归三组分别为 **186 passed / 15 deselected**、**175 passed**、
**9 passed**；存在模块重叠，不将370次通过表述为370个唯一测试或完整离线套件。
脚本语法和diff检查另行记录；没有为文档回写重复运行整个产品测试集。

- [18票初审与集中清单](ticket-review/README.md)
- [恢复/原页/请求诊断回归](recovery-review/README.md)
- [身份审查及原生独立复核](identity-review/README.md)
- [后台原生Boolean结果](background-result.json)

本目录是此次后继支持记录。历史失败、原领取和旧回执不改写。

## 最终保全与停止

主App正常Quit关闭native/backend，按原设计保留独立paused worker及原页。随后用同一主App新控制端重开，相同worker PID/run/Page及未知intent仍在，只读observe成功；新控制端对该在途worker的填写兼容显示unknown，未尝试恢复，不把只读恢复写成填写交接通过。最后仅对命令行精确绑定本轮合成根的登记worker发送SIGTERM，正常清理完成；没有信号发送给既有用户worker。

独立最终回读确认本轮native/backend/worker/Chrome/daemon登记PID退出，三个历史loopback端口关闭，原profile/socket消失；主App全树字节、模式、签名与固定基线一致。配置语义仍保持，私有原始证据已持久归档。最终状态保留needs_recheck、原intent及本轮明确停止记录。最初终态harness误以为native Quit应销毁独立worker，失败已保留；现以原恢复契约和单独明确的合成清理分别留证。

[最终原生Boolean回读](final-native-result.json)。310秒、双浏览器和重开只读恢复均为本次真实主宿主合成实验，不是个人材料或真实申请验收。
