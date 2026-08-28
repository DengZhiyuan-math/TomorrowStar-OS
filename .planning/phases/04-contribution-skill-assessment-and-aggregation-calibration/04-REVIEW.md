---
phase: 04-contribution-skill-assessment-and-aggregation-calibration
reviewed: 2026-08-28T11:07:35Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - src/career_evidence_graph/assessment.py
  - src/career_evidence_graph/cli.py
  - tests/test_assessment_admission.py
  - tests/test_assessment_cli.py
findings:
  critical: 1
  warning: 0
  info: 0
  total: 1
status: issues_found
---

# Phase 04: 代码审查报告

**审查时间：** 2026-08-28T11:07:35Z
**深度：** standard
**审查文件：** 4
**状态：** issues_found

## Summary

已逐文件审查重评审计保管、CLI 入口与两组回归。调用方提交的评估内容不会直接进入新版本，过期版本哈希也会在读取后续 corpus 前拒绝；但“拒绝必须零副作用”的核心契约未成立：一个最终会被拒绝的调用方伪造请求仍可物化并落盘新的审计快照。

验证结果：以 `PYTHONPATH=src uv run pytest -q tests/test_assessment_admission.py tests/test_assessment_cli.py` 运行，40 项通过；Ruff 检查与格式检查均通过。这些结果未覆盖下述审计目录写入副作用。

## Critical Issues

### CR-01: 被拒绝的重评仍会写入审计快照，违反零副作用保管边界

**分类：** BLOCKER

**文件：** `src/career_evidence_graph/assessment.py:1120`

**问题：** `reassess_from_new_evidence` 在比对调用方 `proposal` 与 canonical proposal 之前，先以真实 workspace 调用 `_materialize_audit`。当该 audit 尚不存在时，`_materialize_audit` 会在其审计旅程中调用 `AuditStore.replace`（`assessment.py:503-514`）创建 `workspace/audits/<audit-id>.json`；随后才在 `assessment.py:1140-1152` 因调用方篡改而抛错。故请求虽以 exit 2 拒绝，仍改变了审计历史，违背计划中“每个被拒绝的 reassessment 都零副作用”的要求，也允许攻击者用无效请求在受信工作区制造持久审计记录。

已独立复现：先在独立 staging workspace 构造有效 later corpus，再对 victim workspace 发起仅篡改 `skill_id` 的重评。调用前 `victim/audits/audit-later-evidence.json` 不存在；抛出 `reassessment proposal does not match canonical audit custody` 后该文件存在。现有 CLI 回归仅在 `tests/test_assessment_cli.py:369-391` 比较 assessment sidecar，而其辅助函数在请求前已经创建 later audit（第 356-360 行），因此无法发现此写入。

**修复：** 将后续审计的重放/校验与持久化拆开：先在内存或隔离 staging 目录中得到 canonical snapshot 与 proposal，完成所有调用方身份、保管、权限分区和 lineage 校验；仅当这些校验全部成功时，再把审计快照与新的 assessment version 一并提交到真实 workspace。若不能实现跨两类 sidecar 的事务，至少在失败路径恢复 audit 目录到调用前字节状态，并将恢复失败视为存储错误。补充黑盒回归：让 later corpus 有效但目标 workspace 中该 audit 尚不存在，篡改每个被比较字段后断言 assessment sidecar 和 `audits/` 目录（包括文件不存在性/字节内容）均完全不变。

---

_审查时间：2026-08-28T11:07:35Z_
_审查者：the agent (gsd-code-reviewer)_
_深度：standard_
