# 持续顺序主线的源码集成 — 2026-10-21

这是现有开放票的工程后继。三项 P2 的独立冻结结果见[原修复记录](../p2-regression-fixes-2026-10-21/README.md)：12 个新增回归节点、557 项受影响测试通过，完整默认离线 4204 通过、2 跳过。该历史结果不覆盖这里的后续改动。

本后继只使用合成数据和离线测试。不更新或启动 App，不恢复真实邮件、模型、材料服务或申请，不替用户执行 Submit。票据状态、负责人、依赖和历史证据保留；不新增票。

## 已实现的工程切片

| 原票 | 本后继实现 | 证据及边界 |
| --- | --- | --- |
| 34 / 35 / 39 | 使用既有 RecommendationStore 的持久顺序队列，分页收录；只为当前岗取得完整 JD、分析并制作材料。空队列等待新邮件，等待用户时继续收录和去重，保留当前页与任务。取消旧总运行窗；明确暂停、未决动作和未知来源结果仍等待 | [队列记录](pipeline-assets/queue-implementation.md)。旧 source-chain 保留兼容；不声称已经实现完整 skip、返回或提交结果到下一岗 |
| 40 | 默认申请复用完整 LaTeX 生成、导出、PDF 检查及不可变材料保存。无完整源时等待补齐；不退回摘要模板。系统材料绑定明确 `human_reviewed=False` | [材料记录](material-assets/README.md)。必要额外附件、事实影响合并和完整人工编辑更新仍未完成 |
| 28 | 移除包、native 诊断、epoch、UI 短租约作为逐请求审批；保留实际目标、材料、语言、资格、owner、锁、intent、未知结果和手动 Submit 保护。测量日志失败只诊断；业务检查点保存失败保留 STOP，resume 不能清除它 | [运行支持记录](runtime-assets/README.md)。实际 OS 能力仍由需要该能力的操作检查，未做 App 或真实 ATS 验收 |
| 41 | 界面主线状态与持续收录说明跟随现有 API | 不构造尚无后端的 skip/返回按钮；完整入口收敛未因此完成 |

## 集成中补齐的实际缺口

- 准备前保留完整材料验证回调；不能因缓存目标检查而跳过它。
- 准备前验证采用的分析和材料 lineage，阻止先保存为 queued 再被子 Worker 拒绝。
- 完整导出使用 draft / export 两个原始标识；真实 Worker 必须识别导出记录，不能去错误的旧目录寻找 `sources.json`。
- 重复目标扫描在锁外执行，锁内复核投递文件集合及 stat；扫描后新增同 URL 记录时停止，不保存发送绑定或 Worker 批次。

这些缺口的 RED、后继 GREEN、初始夹具/断言错误和旧诊断矩阵失败分别保留，不将后者冒称产品 RED。源码恢复副本保存在本目标已有的 `/private/tmp/tomorrowstar-automatic-mainline-20261021` 及各支持记录所列目录。

## 当前验证

- Pipeline、capture、共享材料及准备入口组合：145 项通过。
- 单岗绑定、恢复、完整材料、PDF / Prism 导出组合：228 项通过、14 项默认排除。
- 运行与准备入口组合：212 项通过、18 项默认排除。

上述组合有覆盖重叠，不能相加为独立用例数量。最终主线组合 [292 项通过](affected-final.log)；遗漏旧测试预期迁移后的组合 [246 项通过](runtime-assets/final-test-migration-affected.log)。后者仅改两份测试，生产源码没有变化，见[两轮输入差异](v1-to-v2-input-delta.json)。独立复核原四失败节点 4 项通过，测试数量未减少，未新增 skip / xfail，见[独立复核](independent-review.json)。

### 首轮完整默认离线

[首轮运行](full-offline-run.json)为 **4259 passed、2 skipped、4 failed、428 deselected，654.48 秒**，不是全套通过。[原日志](full-offline.log)、[JUnit](full-offline.xml)及[753 份输入的无漂移核对](suite-inputs-after.json)保留。

四项失败是后续主线尚未迁移的旧测试预期：`test_synthetic_native_proof_faults` 三项仍要求普通 prepare 触发 native 诊断回调并返回旧审批拒绝；`test_career_portal_http` 一项要求调用旧准备内部校验钩子。当前准备已直接执行采用材料的 canonical lineage 检查。后继将诊断注入与其锁内日志断言保留为显式诊断行为，并验证普通准备的岗位 / 文件 / 暂停 / 零启动行为；不移除实际业务保护，不用 skip / xfail 隐藏失败。

### 第二轮完整默认离线与回读

**4263 passed、2 skipped、428 deselected，661.45 秒，exit0**。见[完整日志](full-offline-v2.log)、[运行收据](full-offline-v2-run.json)、[JUnit](full-offline-v2.xml)、[受测输入](suite-inputs-before-v2.json)及[运行前后输入核对](suite-inputs-after-v2.json)。753 份登记输入在本轮期间全部相同。原生 Web 桥的 21 项全部运行通过，没有修改原生夹具、60 秒时限或缓存策略。

两项跳过分别是需要明确 opt-in 的完整 HTTP / 模型性能基准及实际本地 Chrome 渲染性能基准；未开启它们。默认排除 live、live_model、worker_browser；另行运行的合成浏览器证据见各支持记录，不与本完整套件相加。

[全仓 Ruff](ruff-check-v2.log)、[格式](ruff-format-v2.log)及 JS 语法检查通过。首轮完整失败日志、JUnit、收据及输入文件原样保留；旧三项 P2 与更早 Swift 超时记录也保留原运行含义。

最终原票 / 地图 Notes、历史字节、原安装文件及链接的回读见[回读收据](final-readback.json)。这次源码通过不关闭任何票，不证明完整 skip / 返回、事实更正合并、安装、真实申请或用户接受已经完成。

## 未完成与接受边界

持续主线仍不是全部 24 张开放票完成。完整 skip / 返回、用户实际 Submit 的明确结果消费、细粒度事实更正与人工材料合并、必要额外附件、安装组合与实际 worker 加载、真实字段/附件及材料/体验接受分别保留在原票。历史 Chrome/TCC 调查保持其因果证据要求，不推断其已解决或重新设为日常前置。

完整默认离线运行保留默认 live / live_model / worker_browser 排除；另行明确选择的合成浏览器用例只证明其夹具场景。通过源码测试不代表已安装、真实运行或用户接受。
