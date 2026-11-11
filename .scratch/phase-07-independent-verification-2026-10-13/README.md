# Phase 7 独立复验 — 2026-10-13

时区：Europe/Zurich。所属票为
[Refresh the Phase 7 Independent Verification Prerequisite](../phase-08-career-experience-inventory/issues/08-refresh-the-phase-7-independent-verification.md)。

## 当前结论

**公开 custody 合同：passed。完整后继发布前置：尚未确定。**

独立源码审查、56 项现有回归与 12 项独立合成探针，在当前单用户本地合同范围内
未发现已证实的阻断性 custody 或隐私缺口。私有 inventory publisher 和完整 seal
verifier 尚未取得显式工作区绑定。不能将公开模块通过扩大成完整后继发布前置通过。
票据保持 `open`，`Assignee: root`。本次不接受或封存私人 inventory。

## 领取核对

领取前，票据为 `open`，Assignee 缺失，`Blocked by: none`。
当前本会话有用户明确推进授权。相关 chat “整理开放的 Wayfinder tickets” 为 idle，
“审计工作并整理开放 tickets” 为 notLoaded；已读近期回合未建立本票的已有领取。
这是一项有界核对，不证明全部历史或归档会话没有其他活动。
领取记录见[ownership check](ownership-check.json)；原票和地图字节留在 `before/`。

## 固定输入与范围

审查采用当前源码字节，不以 Git HEAD 代替未提交实现。
[input manifest](input-manifest.json)记录 21 个直接复验输入、139 个保留文件、
当前 HEAD，以及旧报告逐项摘要比较。直接输入另存于 `inputs/`。

[2026-10-07 报告](../../.planning/phases/07-career-source-custody-and-private-workspace/07-VERIFICATION-2026-10-07.md)
的 11 项输入中，7 项匹配、4 项变化：`workspace.py`、`cli.py`、数据边界文档和架构文档。
变化不撤销首版历史接受。此次范围以
[MVP addendum](../../.planning/phases/07-career-source-custody-and-private-workspace/07-MVP-SIMPLIFICATION-ADDENDUM.md)
及当前数据边界为准。

本轮独立 reviewer 是本会话 root；本会话未修改被核验实现。
公开 Source-universe 发布路径绑定到 `record_captured_source_successor` 与
`load_source_universe_snapshot`。这些 API 创建 candidate provenance。
它们不替代私有 inventory publisher、精确 approval 或 accepted seal verifier。

## 源码与合同核验

| 合同 | 当前实现与观察 | 结果 |
| --- | --- | --- |
| 显式独立 Git workspace | `open_private_workspace` 核对根目录及 Git common directory，拒绝 public、ancestor、child 和共享 Git storage；无自动选择私有目录 | passed |
| 安装包边界变化 | `workspace.py` 对显式非 Git 安装目录提供 fallback，私人选择仍须是 Git workspace；无效或符号链接安装目录不能启用 fallback | passed；合成安装目录，未执行实际 App |
| Raw 保留与隔离 | effective ignore、raw Git index、普通路径及符号链接检查先于写入；create-only；失败可留 orphan，不自动清理 | passed |
| Registry 语义 | cutoff、Source type、availability、可选 unavailable reason、capture time 和 hash 经过验证；available Source 不接受 reason 字段 | passed |
| Source-universe 后继 | 保留 parent、cutoff 和 Source type；父 capture 损坏、缺失中间 parent 或重复 Source ID 均停止；发布后禁止 base capture/mapping 改写 | passed |
| 数据出口与权限 | routine status/error 保留 content-free 语义；detached snapshot 是数据出口，仅为内部私有 handoff；不生成接受、Contribution、Skill 或 mastery | passed，限已审查与测试边界 |
| 通用 inventory handoff | `ProjectInterviewAdapter.verify_binding` 要求精确接受版本、confirmed Experience 和 Source 成员；过期接受不能继续写入 | passed，inventory loader 使用合成替身 |
| 私有完整发布链 | 私有 publisher、完整 accepted seal verifier 和其当前输入尚未绑定 | unobserved；阻止本票完整通过与关闭 |

`cli.py` 的当前入口与 help 保持没有 Phase 7 `career-source` 命令。
audit、assessment 和 JD 的 workspace 参数是其他流程；它们不构成第二套 source registry。
相关代码定位可在输入副本中核对：`workspace.py` 的 workspace selection、raw vault、
registry loader 和 successor writer；`interview.py` 的 `verify_binding`。

## 新执行证据

| 核验 | 当前结果 | 证据 |
| --- | --- | --- |
| Checkout 回归 | 56 passed，4.43 秒 | [日志](checkout-regression.log)、[JUnit](checkout-regression.xml) |
| 独立合成探针 | 12 passed，1.84 秒 | [探针](independent_probes.py)、[日志](independent-probes.log)、[JUnit](independent-probes.xml) |
| 探针 Ruff | passed | [日志](probe-ruff.log) |
| CLI help 只读入口 | exit 0 | [输出](cli-help.log) |
| 实际加载源码与依赖 | 当前 checkout `workspace.py`；Python 3.13.14、pytest 9.1.1、Pydantic 2.13.4 | [runtime binding](runtime-binding.json) |

两组用例分别运行。独立探针没有合并为现有回归的新历史结果。
没有 skipped 用例；全部使用新建临时合成 workspaces。
被测试的缺失 parent、raw symlink 和坏 capture 仅作用于合成数据。
没有读取真实私人清单、答案、接受记录或个人 Source。

执行命令使用锁定 checkout launcher，并禁止 bytecode 和 pytest cache 写入：

```sh
PYTHONDONTWRITEBYTECODE=1 uv --cache-dir /private/tmp/ts-phase7-verification-uv run --locked --offline python scripts/run_pytest.py -q -p no:cacheprovider tests/test_career_source_custody.py tests/test_career_source_security.py tests/test_project_interview.py --junitxml=.scratch/phase-07-independent-verification-2026-10-13/checkout-regression.xml
PYTHONDONTWRITEBYTECODE=1 uv --cache-dir /private/tmp/ts-phase7-verification-uv run --locked --offline python scripts/run_pytest.py -q -p no:cacheprovider .scratch/phase-07-independent-verification-2026-10-13/independent_probes.py --junitxml=.scratch/phase-07-independent-verification-2026-10-13/independent-probes.xml
```

## 仍需绑定的输入

需要用户显式指定私有职业数据仓库。随后只读定位现有 successor publisher、完整
seal verifier、对应合同与合成测试，固定它们的当前字节和具体复验入口。
私人路径、Source 标签、计数、hash 和报告留在私有环境；公开记录只保留通用门槛。
当前问题不请求接受 successor，也不授权运行接受或发布命令。

私有绑定完成前，本次结果只能确认公开 Phase 7 模块边界。新 seal 仍被
[Reconcile Ambiguous, Excluded, and Unresolved Career Items](../phase-08-career-experience-inventory/issues/07-reconcile-ambiguous-excluded-and-unresolved-items.md)
及本票阻塞。

## 保留边界

本轮不证明 adversarial concurrency、TOCTOU、Git history/remote visibility、
备份或加密、实际安装包行为、真实私人资料完整性、inventory 接受或 Skill 能力。
没有实现修补、提交、推送、模型调用、浏览器操作或真实申请。
执行后输入保留、其他票据不变和文档检查见[postcheck](postcheck.json)。
后续私有复验另建后继证据；保留此次固定输入和结果。
