# MC-03：收拢 Resume 准备、版本和 PDF 生命周期

Type: task
Label: wayfinder:task
Status: closed
Priority: P2
Interaction: AFK
Assignee: 01a179dd-5d36-7390-b987-ffc07cb4d702/root
Created: 2026-10-26
Parent: [Module 剩余开发地图](../map.md)
Blocked by: [MC-02](02-mapped-import-prism-successor.md)
Triage: source-and-synthetic-verified
Closure reason: verified

## 问题与范围

保留现有生成/编辑/导出能力，将准备、复用、版本采用、模板和构建结果解释收回 Resume。已完成的作者切片不重做；覆盖其尚未明确的固定引用契约。

## 文件所有权与并行边界

application_resume.py、application_resume_versions.py，必要联动 application_experience_latex.py、application_resume_author.py；Flow/Portal 只改相应消费者。依赖 MC-02 的真实模板/后继契约；与 MC-04 可分文件推进，共享 Flow/Portal 消费者集成串行。

共享文件按地图的冲突规则协调；领取后才能写入。不得覆盖其他工作的修改。
依赖边表示必要交付，不表示外部运行授权；测试记录中的 deselected 不抵充覆盖。

## 验收条件

- [x] execute_generation 与 reconcile_generation 已归 Resume，Flow 持有逐调用准入。
- [x] 默认 prepare/reuse、终审版本采用与 read 走所属 Interface；调用者不解释版本目录/checkpoint 或自行发布完整版本。
- [x] 明确作者 handoff 为 ID-selector 或验证适用固定字段；错申请/任务/输入/版本、人工保护及旧任务恢复保持，不增加第二套作者状态。
- [x] build_pdf、capture_compiled_pdf、read_pdf、reconcile_build 保持不同副作用；可捕获 Prism 自动生成的原 PDF，原完成结果读取不编译、不重放未知。
- [x] 响应丢失复用原完整版本/PDF；源漂移、损坏、未映射人工 TeX 及 mapped-import 多代后继均按真实契约回读。
- [x] 默认 Flow/Portal 消费者和独立材料入口均覆盖；必要回归及审查通过，不新增例行材料接受关卡。

## 既有证据与限制

[作者切片](../../m3-resume-author-2026-10-26/implementation.md)和[保留限制](../../m3-resume-author-2026-10-26/review-closed.md)。既有生成票仅作上游历史，不能当本票新迁移已完成。

需求以[正式设计](../../../docs/module-interfaces-and-migration-design.md)为准。R6 只证明原冻结源码与合成测试范围；本票如有新实现，
须记录实际改动、对应回归和审查，不能复用 R6 关闭新行为。未知结果、人工内容、原页、
原 journal 和历史记录保留，最终 Submit 手动。

关联历史范围：[原资料影响更新票](../../single-job-application-flow-2026-10-16/issues/36-information-reuse-impact-updates.md)；其原状态、负责人和接受结论保留。

## Comments

### 2026-10-26 接续认领与源码边界核对（Europe/Zurich）

用户通过 wayfinder 要求“对接最前沿的 tickets”。实时 tracker 查询零错误，
本票是唯一 open、未认领且硬前置已关闭的前沿。已先保存认领：
`01a179dd-5d36-7390-b987-ffc07cb4d702/root`。前置
「修复映射导入材料的 Prism 人工后继」已按其源码/合成范围结案；
「JSON 交接与 Codex 原页直接接管」保持原负责人。

本次完成上下文接续和只读调用点核对，没有开始本票实现。以下是后续实施入口，
不是新行为的验证结果，也不关闭任何验收项。合同沿用
[正式 Resume Interface](../../../docs/module-interfaces-and-migration-design.md#resume)，
不改变领域术语、原 ID 或保存契约。

**已经具备，直接复用：**

- `ApplicationResumeStore.execute_generation/reconcile_generation` 已拥有作者执行和
  无新模型调用的恢复；Flow 保留逐调用准入。原 intent/result、局部返工和未知结果
  仍由现有作者实现处理，不再建立作者状态机。
- `generate_for_task` 已有 content/fixed/legacy 准备分派；`draft` 与
  `_validated_draft_document` 已有完整版本、lineage 与历史契约回读。
  `persist_content_generation` 已核验终审、内容、renderer 和人工保护并复用原版本。
- 映射导入模板和多代人工后继已修复，复用
  [既有实现与回归](../../mc01-mc02-mc04-implementation-2026-10-26/mc02/implementation.md)。
  Prism 上游更新继续按用户决定搁置，不作为本票前置。

**待收拢的实际调用点：**

| 调用点 | 后续边界 |
| --- | --- |
| `career_portal.py::generate_flow_resume` | 目前选择 handoff 恢复、保留底稿/模板、直接调用 `adopt_generation`，并经私有 `_task_current` 与 `application_pdf_reuse.try_reuse` 决定复用。材料准备/复用及内部采用收回 Resume；Flow 保留任务准入和结果采用。 |
| `application_flow.py::start/_run_tasks` | 当前解释 retained `source_checkpoint`、`base_checkpoint`、origin 和 review 字段。材料结构解释收回 Resume；任务、attempt、输入与当前采用引用仍属 Flow。 |
| `application_experience_latex.py::adopt_generation` 与 Portal 的 `read_experience_generation` | 用 Resume 所属入口承接终审采用和 handoff 进度；继续复用历史分派与完整版本存储，不把 handoff 进度混成完整材料版本。 |
| `ApplicationResumeStore._run_generation` | 传入 handoff 仍仅以 `id` 选择已保存本体，未比较其余传入固定字段；[原审查限制](../../m3-resume-author-2026-10-26/review-closed.md#retained-interface-limitation)仍在。实施时须明确 ID-selector 或验证适用固定字段，不能把默认 Flow 的预检视为完整外部引用合同。 |
| `career_portal.py::export_flow_pdf` | 当前解释 local 契约、调用 Flow 的 `_prism_source`、拼构建参数并选择导出/核对。材料源/构建解释收回 Resume；本任务采用的引用由 Flow 核对。 |

**PDF 副作用必须分别验证：**

- `export_for_draft` 已有编译、意图和归档流程；自动 fixed/content/local 路径可转入
  既有捕获。`capture_compiled_pdf` 读取 Prism 已完成结果并写本地归档，不调用 compile。
- `read_export` 读取并校验原归档，不联系 Prism；`reconcile_export` 核对原 intent/回执，
  无法证明结果时保留 `needs_recheck`，不编译或重放。复用这些实现，不能仅加转发命名。
- Portal `export_flow_pdf` 当前先处理 local 捕获分支，再检查 `reconcile`；因此该
  callback 的 local reconciliation 可以读取 Prism，且无导出目录时可以创建归档。
  这是待核对的迁移边界，尚未运行反例，不能声称已经修复。目标
  `reconcile_build` 的原尝试语义须与显式捕获分开覆盖。
- 独立材料读取继续覆盖 `application_existing_materials`、`application_single_binding`
  和 `application_pdf_reuse`；未映射人工 TeX 仍保留原源与手动构建/导出能力。

**建议实施与验证顺序：**

1. 先固定 Resume 外部引用及 handoff selector 合同，在公开入口补错申请/任务/输入、
   版本冲突、未知动作与响应丢失的回归；保留现有固定输入与 Flow 准入。
2. 复用既有准备、版本和采用实现，迁移 Portal 的 prepare/reuse/采用/读取，随后移出
   Flow 的材料 checkpoint 解释；保留既有默认和独立材料入口的响应合同。
3. 分开迁移 build/capture/read/reconcile。验证无 App 构建也可捕获已有 Prism PDF，
   归档读取零外部调用，核对未知不重编译，丢响应复用原版本/PDF。
4. 覆盖源漂移/损坏、人工保护、unmapped 与 mapped-import 多代后继。先定向回归，
   再对同一冻结源码执行完整默认离线与必要隔离浏览器验收，最后独立审查。

现有回归入口：`test_resume_generation_interface.py`、
`test_resume_author_known_recovery.py`、`test_application_experience_latex.py`、
`test_resume_drafts.py`、`test_json_resume_content.py`、`test_pdf_reuse_portal.py`、
`test_pdf_reuse_flow.py`、`test_flow_retained_baseline.py`、`test_p05_retained_writing.py`、
`test_prism_resume_export.py`、`test_resume_export.py`、`test_p06_versions.py`、
`test_j06_content_reconcile.py` 和 `test_imported_content_mapping.py`。

文件所有权沿用本票；Flow/Portal 仅迁移上述材料消费者，同一方法串行集成。
岗位调度仍由「M4 收拢剩余准备与岗位调度职责」承接，新接管控制仍由
「T09 App 自动派发与统一控制」承接，不提前领取或关闭下游。

本轮仅更新本票与地图/交接/开发计划的认领导航。未改产品代码、测试或运行配置，
未执行行为测试、模型、Prism、安装 App 或真实 ATS。验收复选框保持原样。

### 2026-10-26 开始实施（Europe/Zurich）

用户调用 implement 并要求执行本票。当前会话继续持有认领；准备/版本与 PDF 方法分区实施，
Flow/Portal 消费者由父会话统一集成。先边界回归再最小迁移，保留已有方法兼容与历史。
本轮记录位于[实施目录](../../mc03-resume-lifecycle-2026-10-26/)。源码及隔离合成验证属于本轮；
不扩大到其他票、安装版或真实服务验收。


### 2026-10-26 Resolution：源码与相关合成验收完成（Europe/Zurich）

Resume 已收回默认准备/复用、保留模板选择、已保存 handoff 延续、终审版本采用和
完整材料回读；Portal 只组装输入并调用所属入口，Flow 保留任务准入、attempt、取消
和条件采用。继续复用原作者状态、完整版本与历史，未新增材料库或作者状态机。
handoff 支持 ID-selector；提供固定字段时逐项核验，任务输入冲突在作者调用前拒绝。
采用候选必须与核验后的归档完整内容相同，不能仅凭同 ID/hash 替换保存正文。

build/capture/read/reconcile 已分开：显式捕获可保存 Prism 已有原 PDF，不要求 App
发起构建；原完成结果从归档读取。核对未知只读取原登记尝试，不能重新捕获/编译，
也不能用新请求 ID 绕过原未知。丢响应恢复保留原版本/PDF ID 和字节；源漂移、损坏、
人工保护、未映射 TeX 与 mapped-import 多代后继沿用真实归档合同。

独立审查发现并修正新 Resume→Flow 依赖、未知构建请求 ID 绕过和 PDF 固定引用漏验。
全套回归另发现旧导出关键字调用兼容性及两个合成调度夹具问题，均已修复复核。
两个审查记录及初始反例、失败/中断批次均保留在
[实施报告](../../mc03-resume-lifecycle-2026-10-26/README.md)。

最终同一 668 文件快照：完整默认离线 **7,755 passed、2 skipped**，随后相关隔离合成浏览器
**102 passed**；零失败/错误。两个清单与 JUnit 精确对应且互不相交，运行前后源码
不变；Ruff、格式与 diff 检查通过。两项跳过仍为未启用的 PDF 性能基准。
详见[最终验证](../../mc03-resume-lifecycle-2026-10-26/final-verification.json)。

本票按源码/合成范围结案，不建立例行材料接受关卡；未提交、发布、更新安装 App、
更新 Prism 上游或运行真实模型/Prism/ATS。JSON 原页接管保持原负责人；
「M4 收拢剩余准备与岗位调度职责」解除硬阻塞，仍未认领。
最终 Submit 手动，全部 Module 与 AC 整体验收仍未完成。
