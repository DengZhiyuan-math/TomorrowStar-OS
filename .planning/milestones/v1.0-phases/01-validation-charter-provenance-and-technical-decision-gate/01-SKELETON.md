# Walking Skeleton — Career Evidence Graph Validation Core

**Phase:** 1
**Generated:** 2026-07-30

## Capability Proven End-to-End

An evaluator can validate a versioned functional charter, create an immutable
synthetic formal-run bundle, replay its recorded model response exactly, and
verify the upstream provenance records through one local CLI path.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Application shape | Packaged Python 3.13 CLI/library | The milestone validates domain and evaluation mechanics, not a web product |
| Data layer | Schema-versioned JSON plus append-only JSONL in a local workspace | Human-inspectable, hashable, replayable, and sufficient at validation scale |
| Contracts | Strict Pydantic v2 models | Rejects unknown or incomplete formal-run and provenance records |
| Live model boundary | Codex CLI `codex exec`, GPT-5.6 Luna, medium reasoning | Locked by Phase 1 context while remaining outside the domain model |
| Test boundary | Offline pytest suite plus an opt-in live Codex smoke test | Deterministic default verification without hiding live-runtime drift |
| Directory layout | `src/career_evidence_graph/`, `validation/`, `tests/` | Standard packaged Python separation of code, versioned artifacts, and fixtures |
| Deployment target | Documented local `uv run` commands | Multi-user hosting and production deployment are explicitly out of scope |

## Stack Touched in Phase 1

- [ ] Project scaffold: Python 3.13, uv, Pydantic, pytest, Ruff.
- [ ] CLI route: charter validation and synthetic formal-run tracer.
- [ ] Data write/read: one immutable JSON/JSONL run bundle written and replayed
  from a temporary local workspace.
- [ ] Provenance validation: human reuse matrix plus machine-validated records.
- [ ] Live-runtime boundary: opt-in, read-only Codex CLI smoke test.
- [ ] Local execution: documented locked commands exercise the complete tracer.

## Generic Web-Skeleton Items Not Applicable

- Database: no concurrency, transaction, or query-scale requirement exists;
  JSON/JSONL is the approved persisted data layer.
- Browser UI: the project explicitly starts with a CLI and inspectable reports.
- Authentication: there is no multi-user service in this milestone.
- Dev deployment: local locked execution is the defined development target.

Adding placeholder UI, authentication, a database, or hosting only to satisfy a
generic skeleton template would violate the approved project scope.

## Out of Scope

- STOA career fixtures and domain contracts.
- Grill-Me questioning and audit-session resume behavior.
- Skill assessment and aggregation.
- Real JD parsing or comparison.
- Résumé generation, submission, and outcome measurement.
- Multi-user API, database, authentication, UI, and deployment.

## Subsequent Slice Plan

- Phase 2: add strict career-evidence domain contracts and the first
  human-reviewed STOA fixtures.
- Phase 3: add the resumable artifact-aware Grill-Me workflow.
- Phase 4: add Contribution–Skill assessment and aggregation calibration.
- Phase 5: add structured JD comparison and adversarial end-to-end evaluation.
- Phase 6: add replication checks and document the boundary for any downstream
  field pilot.
