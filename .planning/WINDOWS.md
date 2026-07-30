---
schema_version: 1
open_count: 1
waived_count: 0
fixed_count: 2
total_count: 3
last_updated: 2026-07-30T15:41:06.836Z
---

# Broken Windows Ledger

> Cross-phase defect register. `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 02 | deviation | tests/test_domain_models.py |  | Rebuilt stale local package before current-source domain test verification | fixed |  | 2026-07-30T14:27:28.112Z | 2026-07-30T14:28:23.044Z |
| 2 | 02 | deviation | .planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants/02-03-SUMMARY.md |  | Local locked package rebuild was required before Task 1 verification | fixed |  | 2026-07-30T14:58:00.022Z | 2026-07-30T14:58:42.984Z |
| 3 | 02 | deviation | src/career_evidence_graph/domain/fixtures.py |  | Offline package rebuild used source-path validation because uncached flit-core could not be downloaded. | open |  | 2026-07-30T15:41:06.836Z |  |

````json
[
  {
    "id": 1,
    "kind": "deviation",
    "phase": "02",
    "file": "tests/test_domain_models.py",
    "line": null,
    "description": "Rebuilt stale local package before current-source domain test verification",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-07-30T14:27:28.112Z",
    "resolved_at": "2026-07-30T14:28:23.044Z"
  },
  {
    "id": 2,
    "kind": "deviation",
    "phase": "02",
    "file": ".planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants/02-03-SUMMARY.md",
    "line": null,
    "description": "Local locked package rebuild was required before Task 1 verification",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-07-30T14:58:00.022Z",
    "resolved_at": "2026-07-30T14:58:42.984Z"
  },
  {
    "id": 3,
    "kind": "deviation",
    "phase": "02",
    "file": "src/career_evidence_graph/domain/fixtures.py",
    "line": null,
    "description": "Offline package rebuild used source-path validation because uncached flit-core could not be downloaded.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-07-30T15:41:06.836Z",
    "resolved_at": null
  }
]
````
