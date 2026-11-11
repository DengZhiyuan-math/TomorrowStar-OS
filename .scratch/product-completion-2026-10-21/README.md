# 必要材料、匹配路由与恢复后继 — 2026-10-21

最终冻结 v4：**4440 passed, 2 skipped, 460 deselected in 718.67s (0:11:58)**。受影响离线 1097 项、本地浏览器 164 项通过；[最终保全回读](final-readback.json)。原票和地图仅追加 Notes；App 未更新，真实申请继续暂停。

本记录承接继续推进现有开放票的授权。只执行源码、合成输入和离线检查；不新增票，不改票头、负责人、状态、依赖或既有勾选。App 不更新或启动，真实申请继续暂停，最终 Submit 始终人工。

## 当前实现

| 范围 | 实现及证据 |
| --- | --- |
| APP-05/07 必要材料 | 在既有 Worker 中按岗位、字段、draft path、材料类型和 attempt 保存附稿。复用已有模型接口生成实际动机正文及 cover PDF，保存逐段来源与检查结果；系统草稿不写成用户 confirmed 答案。证书只接受实际提供的文件或原页已有附件。详见 [材料记录](material-assets/README.md)。 |
| APP-06 既有路由 | 普通岗自动推进；既有低路由记录原因并处理下一岗；精准路由完成完整简历后等待，一次 Continue 使用原稿或人工修改稿。未编造数值匹配阈值。详见 [路由记录](routing-assets/README.md)。 |
| APP-13 重开恢复 | 原 owner 持锁、原 run/Page、材料和当前值核验后恢复；主动暂停、等待和未知结果保持。未开页的单岗队列可在已核验边界启动新 owner。重复关闭和迟到命令不能恢复写权限，legacy 已接收请求也受关闭门保护。详见 [恢复记录](recovery-assets/handoff.md)。 |
| APP-15 联系资料与分析 | 联系信息变化保留未受影响的分析和完整人工 LaTeX 底稿，更新当前材料并保留旧 PDF。未知生成/导出不能被 update-inputs 清除。资格答案必须实时核验，不能使未消费该答案的分析/PDF 失效。详见 [输入影响记录](input-impact-assets/README.md)与 [独立复核](input-review-assets/audit-findings.md)。 |
| APP-41 默认控制与编辑 | 请求有 30 秒超时；未知结果按实际 Flow/Pipeline 操作目标限制，暂停仍可用。状态不可读时不按旧状态自动保存；恢复读取后保存原输入。轮询保留同任务编辑焦点和选区。文档更正直接保存历史，迟到保存回执不覆盖另一个文档。缺失必要附件可从当前任务保存真实 PDF，保持暂停。 |

只新增小型共享附稿生成模块，继续复用既有队列、信息库、职业库、模型执行、PDF 导出、原子保存和页面动作记录。没有新增依赖、第三套事实库或另一套岗位调度。

## 测试与审查

初始三项 P2 的 [4204 通过历史](../p2-regression-fixes-2026-10-21/README.md)、持续主线的 [4263 通过历史](../automatic-mainline-2026-10-21/README.md)，以及一次继续后继的 [4349 通过历史](../linear-continuation-2026-10-21/README.md)均保留原输入和时点，不由本轮追改。

- 本轮 [24 项 UI 浏览器回归](ui-assets/browser-affected-v4.log)通过，包括请求挂起、局部读取失败、旧岗未知结果、实际操作目标、自动保存、原页控制、真实附件、文档历史和编辑焦点。早期 UI 运行的失败和导航夹具问题完整保留，不能作为当前通过数相加。
- [恢复/UI/附稿独审](review-assets/independent-review.md)保留公开 RED、修复和独立回读：5 项离线与 3 项浏览器复核通过。独审发现的已关闭恢复命令、过期 owner、已接收 legacy 请求、跨文档回执、旧状态自动保存、Ashby 附件身份和动态必填缺陷均有原始证据。
- 原 owner 的分域受影响测试及模型预算、并发保存、同 SHA 不同附件等回归见各分域记录。它们有重叠，不能相加为独立覆盖数。
- 全仓 Ruff、格式、JavaScript 语法与 diff 检查通过；最终冻结和完整默认离线结果在本记录后继追加，当前不预写完整通过。

所有浏览器测试均使用隔离本地页面。模型、PDF 导出和编译服务响应按测试场景使用合成替身；实际 Intake/Flow/Worker、存储、页面和部分本地传输接口执行。这不证明真实模型文案质量、真实 LaTeX 环境、真实 ATS 或安装版行为。Swift 原生桥仍使用原夹具和原 60 秒编译时限。

## 明确保留的范围

- 已有 Worker 原页上的简历 PDF 安全置换尚未实现。实质联系资料变化继续严格停写，保留原 Worker/Page/PDF；不能清引用重新 prepare 或把旧上传当作新材料成功。
- Workable 附稿没有已核验的发送契约时保持 `unsupported_attachment_transport`，不借用简历端点。未知必要材料意义、多文件控件或实际来源冲突仍等待处理。
- 失去原 owner 的旧 cold Page 没有可核验归属证据时保持 `needs_recheck`；没有用 URL 重开假装恢复。
- 精准路由本轮先完成简历初稿；表单中新发现的其他必要附件由当前 Worker 后续生成。安装组合、实际运行代码、真实完整流程及用户体验接受仍分别未验。

历史与 App 字节、票据元数据、Notes 前缀、最终链接及冻结源码的回读由本轮收尾记录另行绑定。当前不关闭任何票或地图。

## 冻结版本的受影响测试

最终受影响默认离线集合：[1063 passed, 110 deselected in 97.34s](affected-v3.log)；本地浏览器集合：[164 passed, 1063 deselected in 279.88s](affected-browser-v2.log)。两者分别受默认离线和本地浏览器标记约束，不代表全部测试。运行完成后 [770 项源码、正式测试与配置输入](affected-inputs-after-verification.json) 与冻结 v3 哈希全部相同。

早期目标集合的失败分别保留于 affected-final、affected-browser-final 和 UI 分域日志。只读兼容字段恢复和旧 UI 导航修正后的独立绿色回读也保留。没有删除失败节点、放宽 Swift 时限或将浏览器测试冒称真实 ATS 验收。

## 完整 v1 的失败与修正

第一轮完整默认离线结果：[4436 passed, 2 skipped, 3 failed, 460 deselected in 721.96s](full-offline-v1.log)。[运行前后 770 项输入不变](full-offline-v1-run.json)。三个失败节点与独立复现日志均保留，不覆盖或删除。

- 草稿及导出旧测试要求在 callback 仍运行时刷新输入并清空当前 stage。现有保护拒绝该操作，保留原 attempt。测试改为核验 409、持久字节不变、一次 callback、迟到旧结果未采用，以及终态后合法刷新；全部原迟到草稿/PDF安全断言保留。导出用同一 canonical input provider 记录真实来源变化，不能仅拒绝请求后采用旧 PDF。[独立裁决](input-review-assets/full-v1-draft-verdict.md)。
- `preparation_policy_revision` 未证明只影响材料，不能作为 material-only 输入排除。恢复它参与分析核验；保留原 HTTP 策略失效测试，并增加已完成分析保留历史后显式更新再分析的回归。[追加独审](input-review-assets/full-v1-additional-verdict.md)。
- [四文件 60 项检查通过](full-v1-corrections-green-v2.log)。新冻结 v4 相比 v3 仅更改上述一个源码文件和两个正式测试文件，仍为 770 项输入。后续扩大受影响集合及完整 v2 独立保留，以下不预写结果。

语法检查初次命令误用了不存在的 `src/career_evidence/` 路径，原错误保留于 js-*-final.log；改用实际 `src/career_evidence_graph/` 路径后两份 JavaScript 语法检查通过（[实际命令与退出码](js-check-results-v2.json)）。这不是应用代码错误。

## 修正后冻结 v4 的受影响集合

[1097 passed, 110 deselected in 100.67s](affected-v4.log)；[164 passed, 1097 deselected in 286.82s](affected-browser-v3.log)。测试结束后 [770 项输入与 v4 冻结值一致](affected-inputs-after-verification-v4.json)。完整默认 v2 使用同一冻结输入启动，不与目标集合相加计算覆盖数。

与本轮起点相比，最终候选 [21 个修改、8 个新增、0 个删除](source-delta-v4.json)；[可复核差异](change-v4.diff)直接从本轮恢复归档读取旧字节生成，未把仓库原有脏改动算成本轮工作。

## 最终完整离线与保全回读

[完整默认 v2 原始日志](full-offline-v2.log)：**4440 passed, 2 skipped, 460 deselected in 718.67s (0:11:58)**。包括原 60 秒编译时限下 21 项 native web-check bridge 通过。[实际 XML 摘要](full-v2-xml-summary.json)、[实际运行参数和退出码](full-offline-v2-run.json)、[运行前输入](suite-inputs-before-v2.json)及[运行后输入](suite-inputs-after-v2.json)分别保留。770 项输入与冻结 v4、受影响集合和完整运行前后完全一致；这不是独立干净 checkout，也不是所有间接历史输入的穷尽闭包。

两项跳过仍为既有显式 opt-in 性能用例：`test_full_http_entry_paired_preparation_to_viewable_pdf`（完整本地渲染/模型 benchmark）及 `test_offline_cold_warm_and_reuse_rendering_pairs`（实际 Chrome 冷/暖渲染配对）。没有把跳过、460 项默认排除或本地浏览器替身计为真实完整验收。

[最终回读](final-readback.json)核对：127 张票的完整解析记录与起点一致，24 张未关闭；13 张相关原票及地图共 14 份文档仅追加 Notes，128 份既有票/地图文档均保留原字节前缀。636 个历史证据文件与安装版 App 的 93 个记录文件哈希不变；HEAD 保持原值。未新增或关闭票，负责人、状态、依赖和既有勾选均不变。[新增 Notes 链接](notes-link-readback.json)已逐项核验。

[最终静态检查](static-check-results-v4.json)中 Ruff、格式、两份 JavaScript 语法和 diff 检查全部成功。此前完整 v1 三项失败、独立 RED、修复前字节及后续绿色结果均保留。App 未更新或启动，真实申请继续暂停，最终 Submit 始终人工。原页 PDF 置换、精准等待前全部必要附件、未核验 Workable 附稿与安装/真实体验等后继仍按上文边界保留；本轮不声称全部开放票已完成。
