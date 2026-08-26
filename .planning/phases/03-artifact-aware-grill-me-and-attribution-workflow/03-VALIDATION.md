---
phase: 3
slug: artifact-aware-grill-me-and-attribution-workflow
status: draft
nyquist_compliant: false
created: 2026-08-26
---

# Phase 3 — User-Journey Validation Contract

The authoritative Phase 3 acceptance unit is a deterministic offline user
journey against the checkout-source CLI. Test-node totals, editable wheels, and
fresh-install paths are not completion authority.

| Journey | Requirement / decisions | Offline checkout-source command | Expected evidence |
| --- | --- | --- | --- |
| Inspect | AUD-01, D-01, D-17, D-19 | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_inspection.py` | Selected Contribution artifacts, established facts, and unresolved reason are inspectable. |
| Question | AUD-02, AUD-03, D-02, D-03, D-04, D-06, D-08, D-09 | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_policy.py` | One fact-specific, relevant, non-leading question; hard-to-simple boundary behavior. |
| Resume | AUD-02, D-07, D-19 | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_store.py tests/test_audit_cli.py` | Atomic snapshot restores answers, facts, coverage, conflicts, attribution, and the next unanswered question. |
| Skip | AUD-02, AUD-03, D-05, D-16 | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_policy.py tests/test_audit_workflow_regressions.py` | Area or whole Contribution skip preserves an optional self-rating as self-assessed and unverified. |
| Attribute | AUD-04, D-08, D-10, D-11, D-12, D-13 | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_attribution.py` | Responsibility precedes assistance; conflict and uncertainty remain visible; coding-agent detail is provenance, not capability. |
| Boundary | AUD-03, AUD-05, D-04, D-06, D-09, D-14, D-16, D-21 | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_policy.py tests/test_audit_conclusion.py` | Strongest established and next-higher unestablished capability are concrete prose, never a verified numeric score. |
| Review | AUD-05, D-14, D-15, D-21 | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_conclusion.py tests/test_audit_workflow_regressions.py` | Immutable original proposal plus ordered edit/confirm/reject decisions are reviewable. |

## Deterministic phase gate

After the named journeys are implemented, run:

```text
UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q
UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked ruff check src tests
UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked ruff format --check src tests
```

Those commands establish deterministic structural evidence only. The only
completion order is: (1) deep code review; (2) D-17-bounded security review;
(3) Nyquist validation; (4) goal verification; then (5) phase completion, all
on one unchanged revision. Until then the status remains requirements-addressed
only and independent completion is pending.
