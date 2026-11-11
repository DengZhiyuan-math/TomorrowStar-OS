# MC-02：修复映射导入材料的 Prism 人工后继

Type: bug
Label: wayfinder:task
Status: closed
Priority: P1
Interaction: AFK
Assignee: 01a17906-845c-7d91-8bde-c11810886142/root
Created: 2026-10-26
Parent: [Module 剩余开发地图](../map.md)
Blocked by: [MC-00](00-r6-source-baseline.md)
Triage: source-and-synthetic-verified
Closure reason: verified

## 问题与范围

合法 existing_latex/not_used 的 mapped-import 经 begin/finish Prism edit 后，消费者误读生成归档的 request/base_checkpoint，导致 KeyError。模板、manifest、后继回读和保留模板再消费须一并收敛。

## 文件所有权与并行边界

application_resume_versions.py，必要时 application_resume.py 的可信映射读取；测试复用 test_imported_content_mapping.py 及既有 reconciliation fixture。独占这两文件的模板/人工后继区域，与 MC-03 串行；不改 Flow/Portal 或纯 reconcile 规则来迎合错误契约。

共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [x] 先用公开 import → begin → 人工文字编辑 → finish → draft 回读得到失败回归，再按已保存的真实 mapping/template 形成合法后继。
- [x] 无改动、两代后继、无法唯一映射的 unmerged、人工顺序/省略/保护、plain 导入及后继 retained-generation 均保持正确；原导入字节与 origin 不变。
- [x] 损坏 mapping/template/range/parent/hash 和实时源竞争均拒绝错误采用；不能补造模型 request、终审或不存在的 base archive。
- [x] finish 响应丢失重试不新增作者/编译；写入与回读使用一致模板依据，相关导入/版本/保留写作回归及独立审查通过。

## 既有证据与限制

[已确认缺口](../mapped-import-prism-gap.md)与[最小修复方案](../mapped-import-prism-plan.md)仍为未修复证据；本票未执行真实 Prism。

需求以[正式设计](../../../docs/module-interfaces-and-migration-design.md)为准。R6 只证明原冻结源码与合成测试范围；本票如有新实现，
须记录实际改动、对应回归和审查，不能复用 R6 关闭新行为。未知结果、人工内容、原页、
原 journal 和历史记录保留，最终 Submit 手动。

## Comments

### 2026-10-26 接续认领与上下文核对（Europe/Zurich）

用户通过 wayfinder 要求“对接最前沿的 tickets”。本会话核对当前地图、开发计划、
交接和实时 tracker 后认领本票：已关闭的基线登记满足硬前置；本票为未认领前沿中
唯一 P1，先于另外两张 P2。原页直接接管保持原负责人，本次不接管其他票。
负责人为 `01a17906-845c-7d91-8bde-c11810886142/root`。

本次完成认领和实施上下文接续，没有开始修复或重新运行历史失败用例。只读源码
核对确认[最小修复方案](../mapped-import-prism-plan.md)的关键 producer/consumer
差异仍存在，没有发现需要改写方案的结构漂移：

- `application_resume_versions.py::_content_template` 仍读取原生生成的
  `base_checkpoint/request.latex_base` 与 `base-sources.json`；`_save_draft`
  仍直接复制这套依据。`_proofread_scope` 与 `validate` 的回读必须一并处理。
- `application_resume.py` 的导入入口仍保存并重新核验真实
  `content-mapping.json`、模板和 `ranges` manifest；不能补造生成 request 或终审。
- 首条正式回归复用 `tests/test_imported_content_mapping.py` 的 `mapped_import`
  和 `import_mapped`：公开 import → begin → 修改一个可变文本 → finish → draft
  回读，并核对重复 finish 不新增调用。现有 later-edit 用例使用 generated 父版本，
  不覆盖本缺口。

接续实施顺序：先完成上述失败回归，再最小修复真实模板依据与 manifest 适配；
同时处理后继的写入、回读和 retained-generation 消费；按原验收覆盖两代后继、
unmerged、人工保护、损坏与竞争、plain 导入和响应丢失，最后独立审查。
文件所有权保持本票原边界，不进入 Flow/Portal 或纯 reconcile 规则。

这次只更新本票认领和地图/交接/开发计划的状态导航。产品源码、测试及运行配置
未改，未执行模型、Prism、App 更新或真实 ATS。验收复选框不变；本票未解决，
「收拢 Resume 准备、版本和 PDF 生命周期」仍被本票阻塞。

### 2026-10-26 Prism 远端版本补核（Europe/Zurich）

用户追问远端更新后是否已对接最新版。结论：此前上下文接续只核对了当前本地
契约，未完成最新上游接入。当前只读核对如下：

- 远端仓库现名为 [Local-Ai-agent-for-latex](https://github.com/DengZhiyuan-math/Local-Ai-agent-for-latex)，
  原 prism-local URL 重定向到该仓库。`git ls-remote` 读取的 `main` 为
  [`e5392e0938b6970079916a96afc890fbc75cdbfa`](https://github.com/DengZhiyuan-math/Local-Ai-agent-for-latex/commit/e5392e0938b6970079916a96afc890fbc75cdbfa)，提交日期 2026-10-22。
- 本地 Prism checkout 的 HEAD 及本仓库 P06 provenance 仍是
  `e33657e0abd1073ed7f933a371c42c656e59dd7e`；提交图为本地独有 0、远端新增 162。
  远端引用已取回不等于工作树已合并。现有 P06 五个文件仍与记录的补丁哈希相同，
  checkout 另有未提交改动，本次没有覆盖或合并。
- 最新远端 `prism_local` 源码中未包含 `api/build/result`、
  `api/file/conditional` 或 `prism-build-result/v1`。TomorrowStar 仍消费这套
  本地适配接口；上游同期修改了 server、project、build 和 httpbase，不能直接
  拉取后假定这些补丁及连接器已经兼容。

后续最新版接入须在保留现有改动的基础上核对/迁移本地适配并验证连接器。本票
原有 mapped-import 模板/后继缺口仍属 Resume 内部；其回归不替代最新上游集成证据。
本次未更新 Prism 工作树、重启服务或修改已安装 App，未核验运行中服务的代码版本。

### 2026-10-26 开始并发实施（Europe/Zurich）

用户调用 implement，明确授权并发执行本票、「核对并补齐 M1/M2 剩余职责迁移」和
「收拢 CoverLetter 与材料一致性契约」。本票由本会话 Resume 子代理独占原定
模板/人工后继文件区域；共享消费者由父会话协调。Prism 远端更新按用户决定搁置，
仅在出现 Prism 特有缺陷且上游差异相关时重新评估，不作为本轮前置。
实施与验证记录位于[并发实施记录](../../mc01-mc02-mc04-implementation-2026-10-26/)。

### 2026-10-26 Resolution：源码与相关合成验收完成（Europe/Zurich）

合法 mapped-import 的人工后继现从重新核验的原 mapping 读取真实模板，在所属
版本操作发布真实槽位模板与归档；导入 manifest 仅在内部适配。两代、unmerged、
人工顺序/省略/保护、plain、retained-generation、损坏/竞争及响应丢失已覆盖，
原导入字节、真实 origin 和历史保持，不补造生成 request 或终审。

受影响 21 文件最终回归 320 项通过；独立专项 34 项通过，未发现需修复项。
逐项结果见[本票实施记录](../../mc01-mc02-mc04-implementation-2026-10-26/mc02/implementation.md)及
[独立审查](../../mc01-mc02-mc04-implementation-2026-10-26/reviews/mc02-review.md)。
旧缺口/计划保留为修复前证据。「收拢 Resume 准备、版本和 PDF 生命周期」
现解除本票硬阻塞，仍未认领或实施。Prism 上游按用户决定不更新。

同一 665 文件最终快照：完整默认离线 **7,722 passed、2 skipped**，随后相关隔离
合成浏览器 **89 passed**；零失败/错误。JUnit 精确覆盖两个不相交清单，运行前后
源码一致；Ruff、格式与差异空白检查通过。两项跳过为未启用的显式 PDF 性能基准。
最终结果见[统一验收](../../mc01-mc02-mc04-implementation-2026-10-26/final-verification.json)。
此前两个中断批次不作通过证明，原失败与修复记录保留。

本票按当前源码/合成范围结案；未执行真实模型、Prism 服务、安装 App 或 ATS
接受，不扩大为全部 Module 或最终 AC 验收。未提交、发布或更新安装版。
