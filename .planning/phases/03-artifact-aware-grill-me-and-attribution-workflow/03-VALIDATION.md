---
phase: 3
slug: artifact-aware-grill-me-and-attribution-workflow
status: requirements-addressed
nyquist_compliant: false
created: 2026-08-26
---

# Phase 3 — Offline User-Journey Validation Contract

Phase 3 acceptance is a deterministic offline journey through the checkout-source
CLI. Test-node totals, installed-package behavior, and live model output are not
completion authority. Every action below uses the sealed STOA fixture, one strict
atomic snapshot, and recorded decisions only.

| ID | Journey | Offline checkout-source command | Expected observable result / evidence |
| --- | --- | --- | --- |
| AUD-01 | Inspect | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_gap_e2e.py` | Selected Contribution facts and limitations are inspectable before questioning. |
| AUD-02 | Question/resume/skip | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_gap_e2e.py tests/test_audit_cli.py` | One action updates one snapshot; pause/resume restores the active question; skip remains self-assessed. |
| AUD-03 | Relevant boundary | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_gap_e2e.py tests/test_audit_policy.py` | Recorded relevant area uses hard-to-simple boundaries rather than arbitrary answer inflation. |
| AUD-04 | Attribution | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_gap_e2e.py tests/test_audit_attribution.py` | Ownership precedes assistance, including signal paths, without becoming a capability. |
| AUD-05 | Review | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_conclusion.py tests/test_audit_gap_e2e.py` | Original proposal persists while ordered edits, confirms, and rejects append review history. |
| D-01 | Inspect | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_inspection.py` | Question context comes from the selected Contribution's inspected facts. |
| D-02 | Question | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_policy.py` | Each question names a concrete inspected fact and unresolved capability. |
| D-03 | Relevant boundary | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_policy.py` | Only recorded Contribution-relevant capability areas are selected. |
| D-04 | Relevant boundary | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_policy.py` | Every selected area has a distinct hard, intermediate, and simple ladder. |
| D-05 | Skip | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_conclusion.py tests/test_audit_gap_e2e.py` | Area and whole-Contribution skip retain optional rating verbatim as unverified. |
| D-06 | Question | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_policy.py` | One same-level follow-up precedes deterministic descent. |
| D-07 | Resume | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_cli.py` | Atomic snapshot restores exactly one active unanswered question. |
| D-08 | Attribution | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_workflow_regressions.py` | Uncertainty descends; non-ownership signal enters attribution before resume. |
| D-09 | Boundary | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_policy.py` | A selected area closes only through boundary, skip, or explicit unresolved outcome. |
| D-10 | Attribution | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_attribution.py tests/test_audit_conclusion.py` | Terminal verified entries require separate ownership then assistance turns. |
| D-11 | Attribution | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_attribution.py` | Documentary and user conflict remains visible as unresolved. |
| D-12 | Attribution | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_attribution.py` | Coding-agent assistance is provider-neutral; tool identity is provenance only. |
| D-13 | Attribution | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_attribution.py` | Design, generation, modification, debugging, testing, and acceptance remain separately inspectable. |
| D-14 | Review | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_conclusion.py` | Capability-only entries include boundary, basis, attribution, conflicts, and gaps. |
| D-15 | Review | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_conclusion.py` | Original proposal hash remains stable and reviews are ordered append-only records. |
| D-16 | Skip | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_conclusion.py` | No verified numeric score exists; self-rating is opaque unverified text. |
| D-17 | Resume | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_cli.py` | Trusted local operator performs one transition over one snapshot. |
| D-18 | Static cleanup | `! rg -n 'phase03_(original|gap)_probe' tests pyproject.toml` | No legacy marker registration or decorator remains in active tests/config. |
| D-19 | Resume | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_store.py tests/test_audit_cli.py` | Strict schema-versioned atomic snapshot rejects corrupt and unsafe records. |
| D-20 | Closure gate | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_gap_e2e.py` | Checkout-source user journey, not node totals or package installation, is acceptance evidence. |
| D-21 | Closure gate | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_audit_gap_e2e.py tests/test_audit_conclusion.py` | Reduced implementation closes question, attribution, skip, and review business gaps. |

## Same-revision independent closure order

Before Phase 3 can be completed, use one unchanged source revision for: (1) deep
code review; (2) D-17-bounded security review; (3) Nyquist validation; and (4)
goal verification. Any source or test change invalidates downstream reports. Until
all four independently pass, this phase remains `requirements-addressed`; no AUD
requirement is marked complete here.

## Final deterministic check

```text
uv run --offline --locked python scripts/run_pytest.py -q
uv run --offline --locked ruff check .
uv run --offline --locked ruff format --check .
if rg -n 'phase03_(original|gap)_probe' tests pyproject.toml; then exit 1; fi
```
