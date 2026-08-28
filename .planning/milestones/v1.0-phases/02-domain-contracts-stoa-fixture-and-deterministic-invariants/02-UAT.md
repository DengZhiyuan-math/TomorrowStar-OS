---
status: complete
phase: 02-domain-contracts-stoa-fixture-and-deterministic-invariants
source:
  - 02-01-SUMMARY.md
  - 02-02-SUMMARY.md
  - 02-03-SUMMARY.md
  - 02-04-SUMMARY.md
  - 02-05-SUMMARY.md
  - 02-06-SUMMARY.md
started: 2026-07-30T18:29:43.735Z
updated: 2026-07-31T08:17:36.251Z
mode: mvp
---

## Current Test

[testing complete]

## Tests

### 1. 验证一份代表性职业证据记录
expected: 运行 known-good fixture validation CLI 后成功退出并报告有效，同时保留 Contribution 溯源、责任/协助、partial 状态、限制和未校准边界。
result: pass

### 2. 拒绝不受支持的 assessment 状态
expected: 运行 fixture validate-suite 后，16 个单故障案例全部无一被误判为有效；每个案例只返回其声明的唯一错误码。
result: pass

### 3. Experience 类型与 Contribution 子记录
expected: 支持的 Experience 类型保留可区分的 Contribution 子记录，错误类型和标识符被拒绝。
result: pass
source: automated
coverage_id: 02-01-D1

### 4. Evidence、归属、时长和评分边界
expected: Evidence proof limits、claim attribution、duration 和独立评分边界都 fail closed。
result: pass
source: automated
coverage_id: 02-01-D2

### 5. JSON 到离线 CLI 的完整 tracer
expected: 合法非校准 fixture 穿过 JSON、domain validation 和真实离线 CLI，错误 Contribution lineage 被拒绝。
result: pass
source: automated
coverage_id: 02-01-D3

### 6. 禁止直接从间接来源推导 mastery
expected: Experience、credential、title、repository、résumé skill list 和 ontology 不能直接建立 user-Skill assessment。
result: pass
source: automated
coverage_id: 02-02-D1

### 7. 每个 Skill 的独立 UserSkillView
expected: 每个被评估的准确 Skill 只有一个分离视图，并稳定报告 lineage、Evidence 和 attribution 错误。
result: pass
source: automated
coverage_id: 02-02-D2

### 8. 固定 STOA 文档源清单
expected: source manifest 只接受四个固定仓库、四个 pinned commits 和十个哈希文档。
result: pass
source: automated
coverage_id: 02-03-D1

### 9. 未封存 packet 的自动边界
expected: pin-verified candidate/review packet 在人工真值决定前保持不可封存，自动 source/review 检查通过。
result: pass
source: automated
coverage_id: 02-04-D1

### 10. 审核决定的精确保留
expected: 人工授权的 correction、reviewer identity 和 unresolved fixture-score expectations 被原样物化。
result: pass
source: automated
coverage_id: 02-05-D1

### 11. 不可变 known-good 与离线回放
expected: STOA known-good FormalRunStore bundle、canonical hash linkage 和 provider-free replay 全部有效。
result: pass
source: automated
coverage_id: 02-05-D2

### 12. 十六个单故障 known-bad fixtures
expected: 16 个 sealed-base 变体各自产生一个稳定的声明错误，known-good 和 FormalRunStore bytes 不变。
result: pass
source: automated
coverage_id: 02-06-D1

### 13. 离线批量 fixture gate
expected: validate-suite 验证 sealed base、精确 known-bad inventory、唯一错误和 fail-closed 输入。
result: pass
source: automated
coverage_id: 02-06-D2

### 14. Phase 2 验证矩阵同步
expected: 只有 focused checks、完整 pytest、lint 和 format 都通过后，Phase 2 validation 才标为 validated。
result: pass
source: automated
coverage_id: 02-06-D3

### 15. Alias 与 ontology 不改变 mastery
expected: Unicode aliases 和 ontology relations 只产生可审核元数据；运行指定 regression test 后 canonical mastery bytes 保持不变。
result: pass
coverage_id: 02-02-D3
reason: coverage classifier rejected verification kind `regression`; retained as a fail-safe human checkpoint

### 16. 文档候选在人工决定前不是个人事实
expected: candidate/review packet 在个人责任、能力、限制接受和 fixture test values 被明确决定前保持 unsealed、unconfirmed 和 non-personal。
result: pass
coverage_id: 02-03-D2
reason: human judgment required

### 17. 每个 STOA candidate 的六类真值决定
expected: reviewer `zhdeng` 对四个 candidate 分别记录六类决定，没有 blanket approval；责任为 user、协助为 Codex-assisted，partial、限制/冲突和 unresolved score/range 被保留。
result: pass
coverage_id: 02-04-D2
reason: human judgment required

### 18. MVP 结果确认
expected: 从用户角度，合法的代表性 Contribution-grounded 职业证据可以被记录和验证，而不受支持、越权或不完整的 assessment 状态会被明确拒绝。
result: pass

## Summary

total: 18
passed: 18
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
