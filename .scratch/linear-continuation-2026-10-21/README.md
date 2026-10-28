# 当前岗继续、返回与事实材料后继 — 2026-10-21

三项 P2 的独立修复已经完成：[原修复记录](../p2-regression-fixes-2026-10-21/README.md)保留 12 个新增回归节点、557 项受影响测试和完整默认离线 4204 通过、2 跳过的冻结证据。其后的[持续主线切片](../automatic-mainline-2026-10-21/README.md)为 4263 通过、2 跳过。这里记录再后继的工作，不能用旧绿色结果证明当前源码。

只使用合成数据和离线测试。不更新或启动 App，不恢复真实邮件、模型、材料服务或申请；最终 Submit 始终由用户操作。原票只追加 Notes，不新增票，不改负责人、状态、依赖或历史勾选。

## 本切片行为

| 原票 | 已实现的工程行为 | 范围和证据 |
| --- | --- | --- |
| 34 / 37 / 39 | 同一 Worker 批次保存明确的当前岗指针；跳过保留任务、页面、PDF、claim 和未知 intent，返回直接恢复原岗。一次 Continue 读取原页后续行，保留人工字段与附件。 | [接口、测试及边界](pipeline-assets/HANDOFF.md)。未决动作不清除、不自动重放；非当前岗不能自动填写。 |
| 34 / 37 | 到最终确认页后自动停止机器写入，用户直接在原页 Submit；只读观察绑定的人工请求、响应和明确成功确认页，保存成功后才推进下一岗。 | 真实 Chromium **全离线**合成链 1 项通过，不替代真实网站验收。HTTP 200、页面文字或表单消失单独均不构成成功。 |
| 36 | 职业事实更正原位保存当前文档，同时保留原字节及请求/完成历史；信息库更正、撤回应答也保存历史。 | [事实与历史记录](fact-assets/README.md)。HTTP 补充 6 项通过；schema/sealed/research 文档拒绝修改，旧版本或保存失败保留原文。界面事实编辑器尚未实现。 |
| 36 / 40 | 默认完整材料读取实际 Worker 答案库；材料 revision 只绑定适用联系方式，资格 revision 分开。已确认联系方式可替换历史底稿页首旧值，底稿和职业资料保持原物。 | [材料记录](material-assets/README.md)。无关表单答案不使 PDF 失效；联系方式变化阻止发送旧材料。工作与教育不能借页首例外更改。 |
| 40 | 默认申请使用既有 PDF 复用；系统技术复用独立标记 `checked_pdf_reuse`，`human_reviewed=False`。完整人工源可经公开请求保存为独立版本，后续生成使用该源。 | 不跨 mode 读取准备库；已经绑定 Worker 的材料仍拒绝编辑。必要额外附件及完整上传后更新仍未实现。 |
| 41 | 开启、一次继续、暂停、跳过和返回接通既有后端；可明确恢复跟随当前岗。局部邮件读取失败不隐藏当前岗，启动响应未知时仍能暂停。 | [控件回归](ui-assets/pipeline-current-controls-green.log)3 项通过。[HTTP 及 Pipeline 组合](affected-root.log)131 项通过。 |

## 验证记录

- Pipeline / Worker 最终受影响组合：328 通过、19 默认排除，见 [HANDOFF](pipeline-assets/HANDOFF.md)。
- 信息库及完整源生成最终组合：146 通过；此前事实组合 412 通过、13 默认排除，二者覆盖重叠且源码版本不同，不能相加。
- 材料新增纵切片 7 通过；旧复用 53 通过；最终 seam 64 通过、1 默认排除，见[材料证据](material-assets/README.md)。
- [全仓 Ruff](ruff-check.log)和[格式](ruff-format.log)通过。JS 语法检查通过。
- [浏览器组合](ui-assets/browser-affected.log)首轮 16 通过、1 失败；[独立复现](ui-assets/preparation-retry-isolated.log)保留。失败断言用全局卡片选择器，将邮件卡和已有 JD 卡一起计数。后继仅收窄该选择器，不更改业务或删除用例。
- 初轮完整默认离线见[原日志](full-offline.log)、[收据](full-offline-run.json)、[冻结输入](suite-inputs-before.json)。独立复核发现后继 Submit 边界缺陷，主代理在改源码前主动中止本轮，exit 130；[回读](suite-inputs-after.json)确认 761 份原输入在中止时未变。这次中止不计为全套通过；修复后另跑最终候选。

上述受影响组合有覆盖重叠，不相加为独立用例总数。默认离线保留 live、live_model、worker_browser 排除；明确另跑的浏览器测试仅访问本地合成夹具。

## 历史与尚未完成范围

[起点与恢复归档](baseline.json)保留本轮前 753 份输入；[保全清单](preservation-before.json)登记 321 份旧证据、128 份 tracker/map 文档和 93 份现有安装输入。旧失败、Swift 超时和后续通过分别保留，不改写旧结果。

材料集成中两项旧预期失败及一次跨 mode 历史试验失败保留在材料记录。跨 mode 的试验超出本切片现有可读来源，没有放宽模式保护，也不把该功能计为通过。后继测试迁移只采用实际材料投影 revision，并为手工 Worker 夹具初始化真实契约的空答案库；不忽略不可读答案库。

全部开放票仍未完成。细粒度职业事实影响重算、已上传材料的人工修改合并、必要附稿/附件、独立准备库历史复用、完整界面收敛、安装组合及实际 Worker 加载、真实字段/附件、用户人工 Submit 后的真实结果、材料质量与体验接受仍由原票承接。没有凭离线测试关闭任何票或地图。

## 独立复核补充

只读合成复核发现两个本切片新增问题：同一 ATS 原页切到另一岗位后的 GraphQL Submit 可能被误归属原岗；人工 Submit 已观察为 unknown 后，普通 Continue 可能重新允许填写。两项交原 Worker 负责人补回归并最小修复。缺少岗位归属或结果未知时，必须保留原页和材料，不能推进或重填。独立复核与修复后的结果分别追加，不把中止前运行计为最终证明。

后续复核又复现普通 DOM fill 在授权后的切岗窗口仍写旧页，以及三张保留页阻挡第四岗却保持 queued/running；分别补[公开回归 RED](pipeline-assets/dispatch-capacity-red.log)。材料复核另复现已确认联系方式替换后的完整源不能打开人工编辑。修复使用可验证的原底稿页首范围及原组事实，不放宽职业和教育来源。修后复核还要求旧岗未持久人工请求不能误锁新岗；当前岗结果未知的保护必须按岗位隔离。

当前岗修复最终[受影响 419 项通过](pipeline-assets/review-p2-affected-frozen.log)，[独立复跑 26 项通过](pipeline-assets/independent-current-frozen-recheck.log)，[修复交接](pipeline-assets/review-p2-handoff.md)保留逐项原因、旧失败和浏览器证据。联系人人工编辑修复[受影响 262 项通过](material-assets/header-edit-affected-262.log)，[独立复跑](material-assets/independent-retained-header-recheck.log)另存；其中原执行日志从持久化执行记录原样恢复，来源及 SHA 见[命令收据](material-assets/header-edit-command-receipts.json)，不冒称本次重跑。

第二轮完整运行也在独审发现缺陷后主动中止：[收据](full-offline-v2-run.json)、[原日志](full-offline-v2.log)及[762 份输入无漂移证明](suite-inputs-after-v2.json)保留。新复现为同时输出旧邮箱与当前邮箱仍通过 token 检查；后继对完整联系方式和实际链接目标收紧字面约束。第二轮不计为完整通过，也不修改已通过的历史运行。

联系人字面及链接目标后继已冻结：[受影响 272 项通过](material-assets/contact-literals-affected-final.log)，[独立复跑 23 项通过](material-assets/independent-contact-literals-final-recheck.log)。未知或额外旧联系人明确以 `resume_latex_invalid` 停止生成，不能靠将其移入 verification queue 后导出缺失页首的 PDF。合法多联系方式、同号码格式变化、命名链接、百分号 URL 及人工编辑另存均保留。初始双邮箱 RED、矩阵中合法电话误挡、旧负例失败及后继 GREEN 全部保留，见[精确命令、源码与日志哈希](material-assets/contact-literals-final-receipt.json)。

[独立复核收据](independent-review.json)声明其窄范围及测试作者关系，不冒称完整产品审计。当前岗的两项发送/容量回归由复核者编写，生产补丁由另一代理实现。

第三轮候选见[762 份冻结输入](suite-inputs-before-v3.json)、[起点至候选的 20 项修改 / 9 项新增](source-delta-v3.json)及[源码和测试差异](change-v3.diff)。这是本轮恢复归档作基线，不把既有脏工作计为新增，也没有删除登记输入。

第三轮[完整原日志](full-offline-v3.log)、[运行收据](full-offline-v3-run.json)、[JUnit](full-offline-v3.xml)为 **4345 passed、2 skipped、4 failed、432 deselected，677.92 秒，exit1**，不是完整通过。[输入回读](suite-inputs-after-v3.json)确认 762 份输入全部不变。原生 Web 桥 21 项全部运行通过，未改其 60 秒时限或缓存策略。

四项完整运行失败分别定位如下，原断言或业务保护不以跳过/删除掩盖：

| 失败 | 实际原因 | 后继处理 |
| --- | --- | --- |
| current email / batch-workflow | 新增当前岗状态校验提前泄漏 `ValueError`，本应受控拒绝 | 使用既有 `PortalDataError` 返回 409，保持拒绝与原文件不变 |
| current email / 保留其它一次性答案 | 旧夹具把姓名写进共享库，但历史材料无当前联系绑定；材料门禁正确拒绝 | 前置准备改用真正 one-use 命令，保留后续一次性答案及字段断言 |
| snapshot adoption / information library | 旧兼容把导入草稿 resume stage complete 当成完整 PDF；未知导出也忽略新增信息输入 | 兼容仅限已有 PDF 身份/哈希且没有活动或未知尝试；原负例断言保持 |
| job explanations / 资格变化 | 语言资格已实时变 conflict 并拒绝生成，但旧测试要求无关材料输入全局失效 | 保留实时资格拦截、匹配/模型调用不变和零导出，迁移旧 freshness 预期 |

两个 email 问题的[独立诊断](pipeline-assets/full-v3-email-diagnosis.log)、[采用快照诊断](material-assets/full-v3-adoption-diagnosis.log)、[资格诊断](material-assets/full-v3-qualification-diagnosis.log)及[真实本地 HTTP 资格行为复现](material-assets/full-v3-qualification-behavior-probe.log)均保留。第四轮仅在上述修复/迁移、受影响回归及独立复核通过后启动。

### 第四轮候选

上述四节点已全部通过：[email 精确回归](pipeline-assets/full-v3-email-green.log)、[材料精确回归](material-assets/full-v3-repairs-green.log)。受影响组合分别为 [369 passed / 1 默认排除](pipeline-assets/full-v3-email-affected.log)和[251 passed](material-assets/full-v3-repairs-affected.log)，覆盖重叠，不能相加。原 snapshot adoption 负例不变；one-use 夹具增加共享库保持不变断言；资格测试保留评分、模型、导出及事实隐私检查。

[第四轮独立复核](independent-v4-review.json)确认仅四份预期文件相对第三轮变化，原四失败节点[独立 4 passed](independent-v3-four-repairs-recheck.log)。[全仓 Ruff](ruff-check-v4.log)、[格式](ruff-format-v4.log)和[差异检查](diff-check-v4.log)通过。

第四轮[冻结 762 份输入](suite-inputs-before-v4.json)，相对本轮恢复起点为[22 项修改、9 项新增、零登记输入删除](source-delta.json)，[差异](change.diff)保留。当前[完整日志](full-offline-v4.log)及[收据](full-offline-v4-run.json)记录完整运行；结束前不声称通过。

### 最终完整离线结果与同步回读

**4349 passed、2 skipped、432 deselected，676.79 秒，exit0**。见[完整日志](full-offline-v4.log)、[运行收据](full-offline-v4-run.json)、[JUnit 节点结果](full-offline-v4.xml)和[输入回读](suite-inputs-after-v4.json)。762 份登记输入全部相同，没有新增或移除登记范围的测试输入。4351 个默认选中节点中零失败、零错误；原生 Web 桥 21 项实际运行并通过，未改夹具、60 秒时限或缓存策略。

两项跳过仍是需要显式 opt-in 的模型/HTTP 及本地 Chrome PDF 复用性能基准；没有启用它们。默认 live、live_model、worker_browser 排除保持，单独合成浏览器结果不与完整套件相加，也不代替安装或真实业务接受。

原三项 P2、后继回归和完整第三轮四项失败分别保留原结果。第四轮成功不改写前两次主动中止或第三轮失败，不倒推旧 Swift 超时的唯一原因。源码通过不证明全部开放票、材料质量、安装组合或真实流程已完成。

原票和地图只追加本轮 Notes，字段、依赖、勾选及历史正文不变；最终[回读收据](final-readback.json)核对 tracker、历史支持记录、安装输入及文件链接。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。
