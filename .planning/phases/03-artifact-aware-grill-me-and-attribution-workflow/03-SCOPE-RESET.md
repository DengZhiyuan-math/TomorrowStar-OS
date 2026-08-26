# Phase 3 Scope Reset Ledger

This is the sole active scope authority for the Phase 3 repair round. It applies
the user-approved subtraction decisions in `03-CONTEXT.md` D-17 through D-21.
Git history remains evidence, but historic concurrency, installation, and exact
test-count claims cannot define current completion.

## Active contract

One trusted local operator audits one selected Contribution, one action at a
time. The retained persistence boundary is one strict, schema-versioned atomic
snapshot. It retains inspected facts, answers, coverage, contradictions,
attribution, the immutable original proposal, and ordered user reviews. Basic
safe-ID, corrupt-record, and direct-path controls remain. Multi-process writers,
event-head CAS, replay/deduplication, cross-file transactions, event logs,
journals, recovery/WAL, locks, active same-UID namespace defense,
installed-package authority, and fixed probe totals are outside this phase.

## Requirement and decision disposition

| ID | Disposition | Owner | Evidence |
| --- | --- | --- | --- |
| AUD-01 | retain | 03-15, 03-18 | Inspect journey in `03-VALIDATION.md`; inspectable snapshot facts and reasoned questions. |
| AUD-02 | simplify | 03-15, 03-17, 03-18 | Question, Resume, and Skip journeys; checkout-source CLI proof. |
| AUD-03 | retain | 03-17, 03-18 | Relevant hard-to-simple capability-boundary journey. |
| AUD-04 | retain | 03-17, 03-18 | Attribute journey requires ownership before assistance or unresolved attribution. |
| AUD-05 | retain | 03-15, 03-17, 03-18 | Review journey preserves original proposal and ordered user decisions. |
| D-01 | retain | 03-17 | A question names the inspected fact and the remaining uncertainty. |
| D-02 | retain | 03-17 | Fact-specific reason prefix regression and Question journey. |
| D-03 | retain | 03-17 | Relevant-area selection; no fixed five-area checklist. |
| D-04 | retain | 03-17 | Hard-to-simple ladder with one same-level follow-up. |
| D-05 | retain | 03-17 | Area and whole-Contribution self-assessed/unverified skip paths. |
| D-06 | retain | 03-17 | One focused same-level follow-up then descent. |
| D-07 | simplify | 03-15, 03-18 | Atomic snapshot restores next unanswered question without repeat. |
| D-08 | retain | 03-17 | `不知道` descends; non-ownership branches to attribution. |
| D-09 | retain | 03-17 | Boundary known or explicit skip/unresolved closes each relevant area. |
| D-10 | retain | 03-17 | Separate ownership turn followed by assistance turn on every terminal path. |
| D-11 | retain | 03-17, 03-18 | Concrete documentary/user conflict remains visible and unresolved when needed. |
| D-12 | retain | 03-17 | `coding-agent-assisted` is canonical; tool/model are provenance only. |
| D-13 | retain | 03-17 | Design, generation, modification, debugging, testing, and acceptance are separately clarified. |
| D-14 | retain | 03-18 | Per-capability conclusion entries carry boundary, basis, attribution, and unresolved points. |
| D-15 | simplify | 03-15, 03-18 | Snapshot preserves immutable proposal and ordered user corrections/rejections. |
| D-16 | retain | 03-17, 03-18 | No verified numeric score; optional skip rating remains self-assessed/unverified. |
| D-17 | retain | 03-14, 03-15 | Trusted-local, single-action contract stated above and tested through checkout source. |
| D-18 | remove | 03-16 | Remove expanded concurrency, installation, count, and adversarial-filesystem authority without a replacement store. |
| D-19 | simplify | 03-15 | One strict atomic `AuditSnapshot`; ordinary direct-path and corrupt-record controls only. |
| D-20 | superseded | 03-14, 03-18 | User journeys, not fixed node totals or installed CLI, are Phase 3 acceptance authority. |
| D-21 | retain | 03-17, 03-18 | Business-semantic gaps close before independent verification on one unchanged revision. |

## Execution and cleanup ownership

The serial repair order is `03-14 → 03-15 → 03-16 → 03-17 → 03-18`.

| Item | Disposition | Owner | Evidence |
| --- | --- | --- | --- |
| 03-01 through 03-04 business semantics | retain | 03-17, 03-18 | Repaired user journeys replace earlier incomplete coverage claims. |
| 03-05 through 03-13 Git commits and summaries | superseded | 03-14 | Git history remains recoverable; expanded-scope acceptance claims are inactive. |
| `src/career_evidence_graph/audit/models.py` | simplify | 03-15 | Minimal snapshot contract only. |
| `src/career_evidence_graph/audit/store.py` | simplify | 03-15, 03-16 | Atomic snapshot then removal of event/race/lock/recovery machinery. |
| `src/career_evidence_graph/audit/workflow.py` | simplify | 03-15, 03-17 | One-action orchestration and real capability/attribution decisions. |
| `src/career_evidence_graph/cli.py` | simplify | 03-15, 03-16 | Checkout-source local CLI; no installation authority. |
| `tests/test_audit_store.py` | simplify | 03-15 | Atomic snapshot behavior. |
| `tests/test_audit_cli.py` | simplify | 03-15 | Minimal checkout-source CLI behavior. |
| `tests/test_audit_storage_regressions.py` | remove | 03-16 | Descriptor, lock, race, and adversarial-filesystem scope. |
| `tests/test_assistance_migration.py` | remove | 03-16 | Migration machinery outside the single local audit boundary. |
| `tests/test_audit_inspection.py` | remove | 03-16 | Expanded inspection custody/count machinery; retained behavior moves to journey tests. |
| `tests/test_cli_tracer.py` | remove | 03-16 | Editable/install source-authority scope. |
| `_career_evidence_build.py` | remove | 03-16 | Custom editable-package proxy authority. |
| `pyproject.toml` | simplify | 03-16 | Restore ordinary packaging without proxy/install acceptance machinery. |
| `tests/test_audit_policy.py` | simplify | 03-17 | Focused relevant-area question and boundary decisions. |
| `tests/test_audit_attribution.py` | simplify | 03-17 | Ownership then assistance, conflict, and coding-agent provenance. |
| `tests/test_audit_workflow_regressions.py` | simplify | 03-18 | User-journey regressions only. |
| `tests/test_audit_conclusion.py` | simplify | 03-18 | Immutable proposal and ordered review evidence. |
| `tests/test_audit_event_models.py` | remove | 03-16 | Event authority removed. |
| `tests/test_audit_gap_e2e.py` | simplify | 03-18 | Replace event/custody acceptance with named user journeys. |
| `tests/test_audit_installation_regressions.py` | remove | 03-16 | Fresh-install containment is not Phase 3 authority. |
| `tests/test_validation_probe_matrix.py` | remove | 03-16 | Exact probe-count authority removed. |

## Historical byte-custody ledger

Rows are populated only after every listed proof succeeds: required blob,
reachable object, SHA-256, byte equality with the current file, and a proving
commit. Git blobs are the recovery authority; no archive copy is created.

| Path | Git blob | SHA-256 | Proving commit(s) | Disposition |
| --- | --- | --- | --- | --- |
| pending Task 2 | pending | pending | pending | pending |
| pending Task 3 | pending | pending | pending | pending |

## Acceptance authority

`03-VALIDATION.md` is the active acceptance matrix. Completion is permitted only
after deep code review, D-17-bounded security review, Nyquist validation, and
goal verification all pass on one unchanged revision. This ledger does not mark
Phase 3 or any AUD requirement complete.
