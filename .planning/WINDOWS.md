---
schema_version: 1
open_count: 0
waived_count: 0
fixed_count: 1
total_count: 1
last_updated: 2026-07-30T14:28:23.044Z
---

# Broken Windows Ledger

> Cross-phase defect register. `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 02 | deviation | tests/test_domain_models.py |  | Rebuilt stale local package before current-source domain test verification | fixed |  | 2026-07-30T14:27:28.112Z | 2026-07-30T14:28:23.044Z |

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
  }
]
````
