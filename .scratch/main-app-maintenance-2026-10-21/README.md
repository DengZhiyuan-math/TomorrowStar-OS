# 同一主App维护窗口

2026-10-21。已从协调聊天读取用户原始授权：按既有方案构建、备份、更新、最小隔离安装验收，必要时回滚；活worker/未决页先保全交接，真实申请继续暂停。仅本聊天执行App维护，协调聊天只读。

源码保持39/40/41最终v2冻结，不重复默认完整回归。本记录待追加实际结果；未提前声称idle、更新或安装验收通过。


## 第一轮维护结果

原固定签名与证书、426文件来源/820输入核验、新私人包构建、95项engine/12项public输入比较、现有包验证、备份/同一路径替换及G0实际权限均通过。原包两个副本和失败新包保留在本次私人根。

G1标签原值保存和两页两封收录通过；第二封归档模拟成功但回包丢失。重开后inspect一次，已归档2/待核对0，label/archive操作次数始终各2，无重发。随后现有继续按钮实际返回pipeline_current_missing（当前没有选中的岗位），此时尚无active_task。已保存真实loopback状态和UI原始工具记录；本轮G1未通过，G2/G3未运行，按授权正常退出并回滚。修复现有邮件bootstrap继续路径后，另做源码冻结和回归，不沿用旧测试覆盖。

## 工具意外及纠正

G1第一次退出后，CUA对旧App绑定读取AX意外重新启动无参数普通窗口。立即正常Quit，未点击业务按钮。四正式运行根全inventory保持；原Pipeline为paused且无queue_mode，_tick不会进入邮件轮询或岗位推进。正式portal.json被原生启动重排JSON，语义完全相同；已在语义相等前置下恢复原字节，并保留变后副本、原生退出日志及事故记录。不能将本轮说成从未读取正式配置。没有把未知结果改成已完成；旧intent/附件/profile未变。后续退出只用ps/proc，不再读取已退出App句柄；每场显式synthetic启动并核对其进程参数后才绑定UI。

## 源码后继

最小修复由原实现worker负责；只改既有Pipeline继续路径及相应真实HTTP回归，不加审批或新主控。修复完成前不构建/安装下一候选。


## G1修复后继v3源码结果

仅Pipeline及test_synthetic_mail_mode两文件变化，见[source delta](source-delta-v3.diff)；两轮真实HTTP RED/GREEN与稳定13模块见source-fix/（修改中的affected-v1仅历史）。最终4661 passed, 2 skipped, 572 deselected in 1178.71s (0:19:38)；浏览器86 passed in 387.02s (0:06:27)；受影响221 passed, 2 deselected in 177.06s (0:02:57)。集合有重叠不累加，2项skip不是通过。820冻结输入前后/当前一致，[源码候选](source-candidate-v3/manifest.json)426文件，ID `preparation-candidate-18bae4ebc37098b5a36727d99fa5986b059cd1c9197fd7547e5be3b04b2c66b5`。静态检查通过。[统一读回](successor-source-readback.json)。该结果只证明源码；新包与安装场景待继续记录。

G2记录脚本首个resume调用因复用Driver.action的operation参数重名，在发送POST之前抛TypeError；原g2-resume.log保留。改为同一既有Driver.request的公开worker-action调用，未重放未知请求或修改生产源码。

## 最终维护与隔离安装结果

已按协调聊天中用户后续明确授权完成维护；早先39/40/41源码阶段的“App暂停”是当时范围，不覆盖这次已授权窗口。真实申请始终暂停。v3构建、包验证、唯一安装路径替换与固定签名通过；G1实际发现的继续故障已最小修复。首轮失败候选、实际回滚、两个G3根和全部失败日志保留。

| 场景 | 本次实际结果 | 限度 |
| --- | --- | --- |
| G0 | 包内Python/server/离线Chrome PDF验证通过；实际Accessibility、Screen Recording及责任链有效；controller/UI加载与manifest一致 | 不表示每种业务故障都已原生注入 |
| G1 | 原失败根一次Continue不再409；两页收录、标签保存、归档丢回包后inspect不重发；缺国家等待期间只收录，skip/return保留原task和PDF | 无真实Gmail；无国家未启动worker；三类路由仍为源码证据 |
| G2 | 固定Ashby posting/organization各1次；原guard允许公开初始化，表单出现并因缺答案等待；暂停后原页观察通过 | 未填、未上传；无真实Ashby兼容结论 |
| G3 | 7项必需字段verified；旧偏好和未动字段保留；上传1次、远端回读1次、72495字节SHA与PDF一致、Submit为0；同岗位邮箱更正后未重传；暂停/正常退出/同根重开保留runtime、原页、document、字段、附件、PDF和空intent | 未新测真实用户人工值修改或非空未知intent；不代表真实材料质量或自然人工Submit闭环 |

G3首根先生成PDF再补事实，resume被`flow_inputs_stale`拒绝：fill/upload/receiver均0；原根pause后正常退出，精确清理本次自有worker。后继根使用安装版既有`put_information_answer`公共Python API，在Flow/材料之前保存测试源码已有的7条固定事实；随后全部材料和Worker操作使用现有公开HTTP路由。没有直接改task、intent、snapshot或批准对象，没有新增材料刷新实现，没有放宽校验。邮箱更正复用`correct-email → recheck → resume`，仅本岗一次性命令，未改全局信息库或PDF。

Worker实际`loaded_engine_revision=null`，因此完整加载版本映射保持unknown。G2/G3的实际startup测量32文件与安装字节一致；这个事实不能替代完整callable加载身份。controller/UI有实际匹配证据。未修改生产代码补诊断，也不把此缺口变为日常业务审核。

最终[只读回执](final-readback.json)确认：820输入及完整/浏览器前后快照一致，源码候选426文件验证通过；安装完整inventory与签名v3候选相同；四个正式运行根全部inventory不变，正式配置最终等于原始字节；四份旧包备份与原inventory一致且签名有效；App/本次自有worker、浏览器和接收器均已退出。未重新打开普通真实模式。最早工具误开普通窗口及配置JSON重排已在上节明确披露，不能表述为“整个维护期间从未读取正式配置”。

私人原始包、备份、截图、状态与接收端日志位于本次私人维护根；公开交接只保留本页、[逐项范围](acceptance.md)、冻结/回归与摘要回执。协调方独立只读安装核对见[记录](../ticket30-34-install-coordination-2026-10-21/installed-v3-independent-readback.json)。

39/40/41保持源码closed；30/34保持claimed，原负责人、依赖、旧勾选与历史不改。本次没有新增需要用户立即确认的事项；何时恢复真实申请仍统一待用户决定，最终Submit人工。本窗口已结束，不继续App操作。
