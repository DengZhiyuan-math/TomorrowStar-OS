# TomorrowStar OS 项目状态与完善清单

本页保留首次审查时的快照。用户随后要求完成的状态同步、通用适配、后继封存及质量验证，见 [后续交付记录](interview-delivery-2026-10-08.md)。下文“待完成”不覆盖后续交付结果。

截至 2026 年 10 月 8 日，项目已有可运行的本地工具、严格的数据契约和离线验证基础。
来源保管的独立 MVP 验证及首版经历清单接受、封存已完成。
当前主要缺口是从已接受清单进入真实 Contribution 审查的通用适配，以及提问和评分的语义校准。
完整个人 Skill 图、三个真实 JD 的封存与比较、核心假设决策仍未完成。

本次结论适用于本地 checkout，包括既有未提交修改和未跟踪文件。
Git 基线为 `e4a26d0c24311d014d478f7f92e58a88e6709b4b`；该提交本身不包含全部已验证功能。
个人来源、回答、记录标识、数量、路径和封存指纹保留在私人工作区。

## 当前完成边界

| 部分 | 当前状态 | 仍需完成 |
| --- | --- | --- |
| 领域模型与 STOA 基础 fixture | 已实现严格记录、归属、证据链和评分分离约束 | 在完整真实输入链路中验证泛化 |
| 来源保管 | 当前单用户 MVP 已有独立通过记录；旧版复杂保管方案已被替代 | 下次封存前刷新变化输入的验证绑定 |
| 经历清单 | 首版已接受并不可变封存；本次只读复验通过 | 已封存清单的关联后继发布能力，以及后续补充的精确验收 |
| Contribution 审查 | 单项问答、上下文请求、归属、暂停续接和结论复核已有实现 | 清单到 Contribution 的通用适配、全职业队列和完整三层访谈执行 |
| 三层访谈准备 | 模型、协议、CLI 和 Web 检查入口已实现 | 问题质量试运行、回答评估校准和锚点校准 |
| Skill 评估与聚合 | 提案、复核、准入、重评链和无膨胀规则已有实现 | 真实 Skill 身份复核、经校准的个人评估与准入 |
| Web 职业工作区 | 投递记录、材料检索、资料关系图和访谈准备已有实现 | 正式审查录入如有需要，须接入同一适配；准备入口目前不执行正式问答 |
| 个人 canonical graph | 聚合基础与资料关系展示已有实现 | 完整状态图、版本绑定、用户确认和依赖失效处理 |
| JD 与最终验证 | 私人 JD intake、接受 packet、纯比较和评价 charter 有基础实现 | 三个真实 JD 的完整复核与 corpus 封存，以及真实评价和最终决策 |

资料关系图是文档投影。它不能替代经复核的 `Experience → Contribution → Skill` 图。
`inspect-plan` 的成功状态只表示准备结构和调用者提供的上下文绑定有效。
它不核验来源保管、清单接受或问题的语义质量，也不形成个人分数。

依据：[当前 handoff](../.planning/STATE.md)、[系统工作流](workflows.md)、
[架构](../ARCHITECTURE.md)、[访谈 pipeline](question-scoring-pipeline.md)、
[来源保管独立验证](../.planning/phases/07-career-source-custody-and-private-workspace/07-VERIFICATION-2026-10-07.md)。

## 优先完成的工作

| 顺序 | 工作 | 完成条件 | 对应范围 |
| --- | --- | --- | --- |
| 1 | 对齐项目状态与验收索引 | ROADMAP、REQUIREMENTS、STATE 和机器状态使用一致的当前结果；历史失败、旧计划与正式完成分别保留 | 项目维护 |
| 2 | 支持已接受清单的关联后继 | 新版本绑定先前 seal，保留旧字节；只接受精确用户批准的修订；下游不会静默改绑 | Phase 8，INV-05 |
| 3 | 实现通用私人 audit adapter | 从明确选择的私人工作区验证 accepted seal，绑定 Contribution、来源和既有回答；拒绝未接受、未决或过期绑定 | Phase 9，GRF-01、GRF-02 |
| 4 | 完成项目访谈执行与队列 | 按介绍、深挖、迁移顺序执行；各层结论独立；暂停续接保留判据、回答、上下文请求和待审原因 | Phase 9，GRF-10 |
| 5 | 验证问题质量与评估可靠性 | 冻结样本与配置，检查合理替代解释、部分回答、回忆请求、工具协助和错误归属；复核锚点、档内依据及 confidence | Phase 9–10 |
| 6 | 形成真实 reviewed Skill 评估 | Skill 身份有接受或纠正记录；每项评分绑定一个 Contribution 和具体 Skill；未准入项保持可见且不增加 mastery | Phase 10 |
| 7 | 封存并确认完整 canonical graph | 所有接受清单项都有状态；快照绑定清单、审查、评估、Skill 决策、policy 和覆盖版本；修改使依赖结果失效 | Phase 11 |
| 8 | 接受三个真实 JD 并完成评价 | 三个不同来源逐项复核并封存；比较不修改 mastery；完成自动评价、稳定性、holdout、复制、独立盲审和单一最终决策 | Phase 12–14 |

顺序 2 和 3 可以分别推进。尚未接受的新增身份继续保留在后继审阅中，
不能进入正式 Contribution 准入。已有接受身份可用于适配验证。
正式个人能力问答仍按现有协议暂停，直至通用适配、问题质量和校准验收通过。

```mermaid
flowchart LR
    A[首版清单已接受并封存] --> B[通用 Contribution 适配]
    B --> C[三层访谈执行与队列]
    C --> D[问题与评估校准]
    D --> E[真实问答及 reviewed Skill 评估]
    E --> F[完整图与用户确认]
    F --> G[三个真实 JD 与 corpus]
    G --> H[评价 盲审与核心假设决策]
    A --> S[关联后继与精确验收]
    S --> B
```

优先复用 `audit/`、`assessment.py`、`workspace.py`、现有 hashing 和 create-only store。
通用适配应隔离私人 seed 和来源特定提取逻辑，不能直接复制私人脚本到系统仓库。
不需要新增数据库、第二套评分器、解析框架或工作流引擎。

完整验收条件见 [ROADMAP](../.planning/ROADMAP.md) 和
[32 项需求及 phase 映射](../.planning/REQUIREMENTS.md)。

## 状态记录需要完善的地方

| 位置 | 当前差异 | 修订要求 |
| --- | --- | --- |
| ROADMAP Phase 7 和进度表 | 仍写独立验证待完成；Phase 8、9 仍显示未开始 | 引用已通过的 MVP 验证、首版接受封存和当前准备工作；不要把准备工作标为 Phase 9 完成 |
| REQUIREMENTS traceability | 来源保管仍为 `Gaps Found`，全部需求仍未勾选 | 逐项绑定当前验收证据；区分首版记录完成与通用修订能力未完成 |
| `.planning/state.json` | 仍停在旧 Phase 7 和 0% | 与当前 STATE handoff 同步；不要从测试数量推算产品完成率 |
| STATE front matter | 当前 Phase 9 与 `completed_phases: 0`、旧计划总数并存 | 明确执行进度与正式阶段验收的统计口径 |
| ARCHITECTURE persistence 段 | 仍把 full-career inventory seal 列为 pending | 区分首版已封存与关联后继能力待完成 |
| Phase 8 context 与旧审查文档 | 含有早期“验证未通过”“未接受”的历史状态 | 保留原证据，在当前入口链接后来的验证和 handoff；不追改历史结论 |
| 旧 milestone lock 与 review-fix 标记 | 保留较早执行记录，当前所有权未确认 | 先检查运行进程、worktree 和独有文件，再决定清理；本次未删除 |
| Git 工作区 | 多项核心文档、Web 代码和测试尚未跟踪，其他实现也有未提交修改 | 按功能审查并保留精确版本；提交时只选择确认过的路径，保留并发工作 |

这些差异使“已有能力”“实际验收”和“下一步”难以从一个入口判断。
状态同步应以现有证据为准，不能用本报告替代用户验收或独立审查。

当前运行边界仍是 checkout。构建后端只打包 Python 模块，完整操作流程依赖 checkout 输入；
Web 静态资源也不在 wheel 内。如果未来需要分发安装版，再单独验证和补齐打包。
当前本地运行无需先增加安装版支持。

## 本次验证

| 检查 | 结果 | 能支持的结论 |
| --- | --- | --- |
| 完整 checkout 离线测试 | **616 passed，1 deselected，159.13 秒** | 当前代码及合成拒绝路径通过；live-model 项未执行 |
| Ruff | **通过** | 当前 Python 静态规则通过 |
| Ruff format | **105 files already formatted** | 当前 Python 格式通过 |
| `git diff --check` | **通过** | 已有 diff 没有空白错误 |
| 私人 seal 操作的合成测试 | **7 tests，OK** | 首次封存、篡改拒绝与原记录保留的覆盖通过 |
| 已接受清单的只读完整链路复验 | **通过** | 原接受、来源、覆盖、审阅和封存绑定仍有效 |
| 旧独立验证输入与当前 checkout 比较 | **两项输入已变化** | `cli.py` 和 `ARCHITECTURE.md` 已不同；下次新封存前需要刷新验证绑定 |
| 主要导航文档的本地文件链接 | **未发现失效目标** | README、架构、规范、工作流、数据边界、pipeline 和 Web 指南的目标存在 |

旧独立验证绑定的变化不使原封存失效。现有 verifier 按保留的历史证据重验原封存，
新发布操作则要求当前验证输入一致。这两个检查本次分别执行。
来源保管的核心 `workspace.py` 不在本次发现的变化输入中。

验证命令：

```bash
uv run --locked python scripts/run_pytest.py -q -p no:cacheprovider
uv run --locked ruff check .
uv run --locked ruff format --check .
git diff --check
```

本次没有执行真实模型问答、个人评分、真实 JD 评价或浏览器交互验收。
较早的 Web 浏览器结果保留在 [validation-runs](validation-runs.md)，不作为本次新验收。
私人记录只读检查；本次没有接受新版本、写入个人记录、提交、推送或部署。

## 当前应继续延后的功能

动态 JD 定制简历和证据产出的补缺工作仍是产品目标。
它们应在当前核心假设得到支持后实施。
多用户 SaaS、复杂 Web 流程、图数据库、向量库和大规模 ontology 导入没有当前验收必要性。
继续完善资料图外观不会关闭真实能力评估、JD usefulness 或最终决策的缺口。
