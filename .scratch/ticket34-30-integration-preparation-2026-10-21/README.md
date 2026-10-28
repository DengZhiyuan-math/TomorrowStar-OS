# 34/30集成与最小安装验收准备

2026-10-21，Europe/Zurich。用户授权继续集成与准备、协调原负责人；App更新和真实申请仍暂停。本轮不构建、安装或启动App，不读取真实配置/邮箱，不进行真实表单或Submit操作；没有commit/push。

## 已推进

1. 保留34/30的`claimed / 01a15926/root`。已在“审计当前工作进展”聊天与原负责人协调：原负责人负责[30验收矩阵/命令清单](owner30/README.md)；当前聊天补34的实际服务组合与必要fixture兼容修正。没有抢占原owner或关闭票。
2. 复用42的标签/局部错误/邮件收据与33的公开Ashby Query边界；新增`test_pipeline_mail_bootstrap_integration.py`的7项组合，实际执行既有Pipeline、Flow、WorkerService和Runner，模拟邮箱/页面/传输。覆盖缺事实、未知动作、显式暂停的收录、archive未知结果、重开幂等、先inspect不重归档、后台poll不越岗；坏标签/未配置仍收录；Ashby只读不结算未知动作，真实Flow skip/return保留原页，最终Submit被拒绝。
3. 为原两个测试fixture增加默认不变的job_url/server_options，不复制主流程。[调用清单](call-inventory.md)明确34仅持有编排/路由，继续消费主控、材料、UI和专业适配器。
4. 实际复测30既有合成场景时发现兼容缺陷：当前Runner使用有界fetch读取响应，旧固定HTML fixture只有旧continue路径，fetch仅支持Workable上传接收端。通用场景停在`public_read_result_unknown`，零字段填入。只修改`application_worker_fixtures.py`，为来源固定的GET和既有严格fetch参数提供内存200响应；无外部传输回退、未改生产Runner/请求保护/业务主流程。原上传接收端保持。

## 失败、回归与审查

- [组合首轮](composition-first.log)：5通过/1失败；失败是新夹具错误地把paused作为Worker岗位status。修正为worker filling+control paused，未放宽产品校验。
- [最初受影响集合](affected-v1.log)：145通过、2 deselected，11.61s。
- [浏览器首轮](browser-v1.log)：5失败/13通过；[单节点最小复现](generic-read-red.log)：1失败/3.61s；[四模式有界fetch RED](bounded-document-red.log)：4失败，具体错误`synthetic-browser-upload-target`。确认是固定HTML适配缺口，排除生产GET用途拒绝与时序假设；未增加超时。
- [最小GREEN](bounded-document-green.log)：4通过；加上真实后台poll和skip中间状态断言后的[离线组合/fixture](composition-fixture-green.log)：18通过、2 deselected。
- [完整所选浏览器复测](browser-v2-run.json)：18通过、75 deselected，原5失败全部通过，812项输入前后相同。包含实际隔离Chromium控件/普通resume签名上传、本地接收端字节回读、Ashby初始化、邮件UI和当前岗控制。上传接收端不是雇主网络。
- [最终受影响集合](affected-v2-run.json)：197通过、8 deselected，812项输入前后相同。与浏览器/全库有重叠，不相加。
- [独立增量审查](review.md)：无未解决发现；记录真实本地服务与页面/调度模拟的边界，skip中间状态断言已补。Ruff check/format通过。
- 共享fixture模块发生变化，最终完整默认[full-v1](full-v1-run.json)已通过：4608 passed、2 skipped、561 deselected，878.11s；812项输入前后相同。[原日志](full-v1.log)、[JUnit](full-v1.xml)和[跳过原因](skipped-tests.json)保留。以前的4597/2及43浏览器是42/33基线收据，不与本轮结果相加。

## 源码候选与后续安装

当前后继为[source-candidate-v1/manifest.json](source-candidate-v1/manifest.json)，423项，candidate `preparation-candidate-27258192ee8c1c69680f47daef98839117651bcbe4a04abe9b27df7c9b5a9ffe`；已与checkout核对。它不是安装包，也不是独立完整测试checkout；不重写42/33旧候选。

[原负责人准备](owner30/README.md)、[明确命令清单](owner30/commands.md)将独立可执行路线和原生未接入项拆开：

- 现有`integration-upload`可用于后续单岗原生字段/上传旅程；本轮隔离浏览器已测，实际安装仍未执行。
- G1：现有合成Native入口禁用设置/后台邮件队列；尚无一个入口可跑完“菜单设置→邮件处理→完整队列”七步。只应在现有入口补固定来源的合成场景桥，保留隔离目录和真实邮箱禁用；本轮没有开放所有合成模式或用普通真实配置凑场景。
- G2：33的离线Ashby Runner有正例，但生成器没有对应App枚举。首个有限安装组可先覆盖Workable并明确Ashby原生未验；若纳入则复用33接收器补固定场景，不造通用GraphQL框架。
- 28/30继续承接唯一主App更新、实际加载worker与适用旧版本交接、恢复回滚；不增加日常版本/权限审批。

30准备产物不代表上述G1/G2已实施，不代表APP-01–18、材料质量、真实邮箱/ATS或自然人工Submit闭环已通过。34/30的原验收勾选、Status、Assignee、依赖与历史均保留，最终Submit始终人工。

## 冻结交接

原负责人已在既有聊天提出：本轮完整回归及最终读回完成后，串行接手G1/G2最小合成入口。当前聊天不再并行修改generator、App.swift、server.py或fixture。最终读回先核对423项候选、812项输入、票头/历史及主App登记文件，再发送交接；后继G1/G2必须另存其输入和验证结果，不能追写为本轮已覆盖。

[最终读回](final-readback.json)：候选423项、812项输入无漂移；34/30票头和原字节前缀保持，tracker无错误、原20警告保持；173个本地链接通过，主App1465登记普通文件无变化。[冻结交接](handoff-released.json)已向原负责人发出，后继G1/G2不属于本轮已测输入。
