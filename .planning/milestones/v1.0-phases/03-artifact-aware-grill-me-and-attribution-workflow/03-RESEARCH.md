# Phase 3: Artifact-Aware Grill-Me and Attribution Workflow - Research

**Researched:** 2026-08-26  
**Domain:** contribution-scoped resumable CLI audit, evidence attribution, and immutable review lineage  
**Confidence:** HIGH for repository integration; MEDIUM for library and security guidance

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Artifact-aware audit entry and question coverage

- **D-01:** Inspect the selected Contribution's project documents before asking questions, but do not automatically show an opening summary or evidence table. Begin the audit directly with the first question. The inspection record required by `AUD-01` must remain available for inspection and later conclusion traceability.
- **D-02:** Prefix every question with one short, concrete reason that states what the project record established and what remains unverified. Example: "项目记录表明你参与了 Stripe 订阅流程，但无法确认你是否掌握异常恢复。因此：如果 webhook 重复或乱序，你会怎样保证状态正确？"
- **D-03:** Generate questions only for dimensions genuinely relevant to the selected Contribution. Technical design, implementation, research and development process, debugging, operation, organization, and collaboration are all eligible, but the workflow must not force irrelevant categories merely to fill a checklist.
- **D-04:** Start at a demanding capability level and move toward simpler questions to locate the user's actual boundary. Do not begin with simple questions and mechanically climb upward.

#### Verification skip, questioning, and resumability

- **D-05:** The user may skip either the current capability/Skill area or the entire Contribution audit. A skip may include a user-supplied self-rating, which must be preserved verbatim as `self-assessed` and `unverified`; it must not be presented as an audit-confirmed or calibrated mastery score.
- **D-06:** If an answer at the current difficulty is incomplete, allow exactly one focused follow-up at that same level. If the missing capability is still not established, lower the difficulty rather than repeatedly interrogating at the same level.
- **D-07:** On pause and resume, restore answers, artifact-established facts, coverage, contradictions, attribution state, and unresolved questions, then ask the next unanswered question directly. Do not repeat the opening material or already answered questions unless the user explicitly requests a progress view.
- **D-08:** Treat "不知道" as failure to establish the current capability level and move downward. Treat "这部分不是我做的" as an attribution signal and branch to responsibility clarification; it is not evidence of low capability.
- **D-09:** Stop questioning a capability area once the strongest level the user can establish and the immediately higher level not established are both known. Move to the next relevant area. The Contribution audit completes when every relevant area is verified, explicitly skipped, or explicitly unresolved.

#### Responsibility and assistance attribution

- **D-10:** Confirm responsibility and assistance in separate turns. First establish whether the work was user-owned, team-owned, or other-person-owned; then establish whether and how a coding agent or third party assisted. Never infer personal ownership solely from project documents or repository history.
- **D-11:** When the user's statement conflicts with project material, show the concrete conflict and ask for the user's actual responsibility boundary. Preserve both claims and mark responsibility unresolved if the boundary cannot be clarified; do not silently prefer either source.
- **D-12:** Use the provider-neutral primary assistance category `coding-agent-assisted`, not a Codex-specific domain category. When known, retain the concrete tool and model as provenance metadata, for example Codex CLI and GPT-5.6 Luna. Different vendors do not become different capability categories. — **Reversibility:** costly — changing the canonical assistance value after persisted audits exist requires a schema/data migration and compatibility handling.
- **D-13:** Coding-agent use does not automatically remove user responsibility or establish user capability. When relevant, clarify who made design decisions, generated code, modified outputs, debugged failures, tested behavior, and accepted the final result. Capability still depends on what the user can explain, modify, reproduce, debug, defend, or operate.

#### Conclusion review and scoring boundary

- **D-14:** Produce one Contribution conclusion containing reviewable entries for each audited capability/Skill area. Each entry states the strongest capability established, the next-higher capability not established, the supporting basis, responsibility and assistance boundaries, whether it came from audit verification or unverified self-assessment, and every unresolved conflict or gap.
- **D-15:** Let the user edit, confirm, or reject each conclusion entry, and also confirm or reject the entire Contribution conclusion. Preserve the system's original proposal, the user's correction or rejection, and the reason rather than overwriting audit history.
- **D-16:** Do not generate a numeric score from the Phase 3 interview. Verified results are concrete capability-boundary statements. A numeric value appears only when the user elects to skip and supplies a self-rating; that value remains explicitly unverified and is not admitted into Phase 4 mastery or aggregation without later policy.

### the agent's Discretion

- Exact command names, JSON/JSONL envelope shapes, stable identifiers, and internal state-transition representation.
- Exact wording of neutral questions and capability ladders, provided the locked hard-to-simple, one-question, one-same-level-follow-up, reason-preface, and anti-leading constraints are enforced.
- Whether the inspectable artifact record is exposed by an explicit CLI command, included in the conclusion packet, or both, provided it is not forced as an opening display.

### Deferred Ideas (OUT OF SCOPE)

- Converting capability boundaries or self-ratings into calibrated 0–100 mastery, confidence admission, Contribution–Skill assessments, or user-level aggregation belongs to Phase 4.
- JD comparison and questions selected from target-job requirements belong to Phase 5.
- Real résumé-submission effectiveness remains a later empirical product-validation concern, not a Phase 3 conclusion.
</user_constraints>

## Project Constraints (from AGENTS.md)

- Follow the ordered preference: YAGNI, existing reusable implementation, standard library, framework-native capability, installed dependency, a clear one-line implementation, then the smallest custom implementation. [VERIFIED: AGENTS.md]
- Do not add a dependency speculatively; this phase should use the already installed Python, Pydantic, pytest, and standard-library JSON/filesystem facilities. [VERIFIED: AGENTS.md; pyproject.toml:10-22]
- Repository modifications must occur through a GSD workflow; this research artifact is produced by the active phase-planning workflow. [VERIFIED: AGENTS.md]

## Summary

Phase 3 is a deterministic, local workflow core, not a conversational product or a scoring engine. It should load the already sealed contribution graph, materialize an inspectable artifact record bounded by the fixture's pinned documents and proof limits, then use a pure transition function to accept one user action and emit at most one next question or a reviewable conclusion. This preserves the Phase 2 rule that documents establish bounded project facts but cannot establish personal responsibility or capability. [VERIFIED: src/career_evidence_graph/domain/fixtures.py:1-6; .planning/REQUIREMENTS.md:30-34]

Use new frozen Pydantic audit contracts plus a small workspace store, reusing `StrictModel` and the atomic, verify-before-read techniques in `FormalRunStore`; do not introduce an agent framework, database, UI, or provider call. Existing `StrictModel` is exactly `ConfigDict(extra="forbid", frozen=True)`, and `FormalRunStore` already writes canonical JSON through a temporary file, `fsync`, and `os.replace`. [VERIFIED: src/career_evidence_graph/validation/models.py:12-16; src/career_evidence_graph/validation/store.py:77-90] Pydantic supports typed models, strict extra-field handling, and JSON validation, but validation proves structure rather than the truth of a user's answer. [CITED: https://pydantic.dev/docs/validation/latest/concepts/models/]

**Primary recommendation:** Implement a contribution-scoped, persisted state machine with explicit immutable event/history records, deterministic question-policy guards, and a separate compatibility migration from `codex_assisted` to `coding-agent-assisted`; keep every assessment or numeric policy out of this phase.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| Fixture-bounded artifact inspection | API / Backend | Database / Storage | Pure Python loads the sealed fixture and manifest; persisted record makes the material inspectable. |
| Question selection and transition guards | API / Backend | — | Policy must enforce one question, relevance, follow-up limit, and difficulty movement before any CLI rendering. |
| Pause/resume and append-only history | Database / Storage | API / Backend | Workspace files retain state/events; application code validates and atomically publishes them. |
| Attribution and conflict clarification | API / Backend | — | It is domain logic, not a documentary inference or presentation concern. |
| CLI interaction/review commands | Browser / Client (CLI) | API / Backend | `argparse` only serializes actions/results; it does not own audit truth. |

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|---|---|---|
| AUD-01 | Inspect artifacts first; retain what was inspected, established, and why questions remain. | Bounded artifact-record contract from sealed fixture + source-manifest; reason-preface generated only from that record. |
| AUD-02 | One decision-bearing question per turn; resumable without state loss. | Pure transition guard, immutable events, validated snapshot, and atomic workspace store. |
| AUD-03 | Reject repeated, multi-part, leading, artifact-answerable questions; probe capability. | Deterministic question validator/policy tests; artifacts only populate known facts, never answer a capability probe. |
| AUD-04 | Separate ownership and assistance or mark unresolved. | Two explicit attribution rounds plus conflict record; assistance migration with provenance metadata. |
| AUD-05 | Review/edit/confirm/reject a complete capability-boundary conclusion. | Immutable proposal/correction/rejection lineage modeled after existing correction records and formal-run storage. |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---|---:|---|---|
| Python standard library (`argparse`, `json`, `pathlib`, `tempfile`, `os`) | Python `>=3.13,<3.14` | CLI, canonical file workspace, atomic replacement | Already the project baseline; existing store demonstrates the needed atomic JSON write. [VERIFIED: pyproject.toml:10-13; src/career_evidence_graph/validation/store.py:5-10,77-90] |
| Pydantic | `2.13.4` | Frozen, extra-forbidding audit/state/event/conclusion contracts | Already installed and used by `StrictModel`; Pydantic documents `model_validate_json` and `extra='forbid'`. [VERIFIED: pyproject.toml:10-13; src/career_evidence_graph/validation/models.py:12-16] [CITED: https://pydantic.dev/docs/validation/latest/concepts/models/] |
| pytest | `9.1.1` | Offline transition, persistence, migration, and CLI regression tests | Already installed and configured to exclude live-model tests by default. [VERIFIED: pyproject.toml:18-30] |

### Supporting

| Library | Version | Purpose | When to Use |
|---|---:|---|---|
| Ruff | `0.16.0` | Lint/format | Run against Phase 3 Python code using the existing `py313` target. [VERIFIED: pyproject.toml:18-22,32-38] |
| Existing `FormalRunStore` patterns | local | Atomic canonical JSON and immutable correction lineage | Reuse the pattern, not necessarily the formal-run schema, for audit workspace persistence. [VERIFIED: src/career_evidence_graph/validation/store.py:62-90,92-125; src/career_evidence_graph/validation/models.py:259-267] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|---|---|---|
| Small JSON/JSONL audit workspace | SQLite or workflow/agent framework | Out of scope: no concurrent users/query requirement, and opaque state machines conflict with deterministic audit guards. [VERIFIED: AGENTS.md; .planning/PROJECT.md] |
| Existing Pydantic contracts | Hand-written `dict` validation | Would duplicate already adopted strict-schema behavior and weaken fail-closed parsing. [VERIFIED: src/career_evidence_graph/validation/models.py:12-16] |

**Installation:** None. No dependency or lockfile change is justified. [VERIFIED: pyproject.toml:10-22]

## Package Legitimacy Audit

No external package installation is recommended for this phase; the package-legitimacy gate is therefore not applicable. [VERIFIED: pyproject.toml:10-22]

## Architecture Patterns

### System Architecture Diagram

```text
selected Contribution id + sealed STOA fixture
                    |
                    v
         bounded artifact inspector
   (pins, documents, proof limits, conflicts)
                    |
                    v
  validated audit snapshot <---- atomic audit store ---- append-only events
                    |
                    v
 deterministic transition / question-policy guards
     |                  |                    |
     | answer           | skip/pause          | attribution conflict
     v                  v                    v
 coverage update    resume snapshot    separate clarification turn
     |                  |                    |
     +------------------+--------------------+
                    |
                    v
 proposal conclusion -> entry review/correction/rejection -> confirmed conclusion
                    |
                    v
                 CLI JSON output
```

### Recommended Project Structure

```text
src/career_evidence_graph/
├── audit/
│   ├── models.py          # frozen Phase 3 audit records
│   ├── policy.py          # pure question/transition/conclusion rules
│   ├── store.py           # bounded atomic audit workspace
│   └── service.py         # fixture inspection plus command orchestration
├── domain/models.py       # evolved shared assistance compatibility contract
└── cli.py                 # minimal audit subcommands
tests/
├── test_audit_models.py
├── test_audit_policy.py
├── test_audit_store.py
├── test_audit_cli.py
└── test_assistance_migration.py
```

### Pattern 1: Pure state transition, then persistence

**What:** Parse a user action into a strict input model; apply a side-effect-free transition function to the current snapshot; validate invariants; atomically write the new snapshot and append a hash-linked event only after the transition succeeds.

**When to use:** Every start, answer, skip, pause/resume, attribution clarification, and review action.

**Why:** It makes one-question enforcement and replayable/resumable behavior testable without a live model. Existing storage already rejects unsafe IDs and destinations outside its workspace root before writes. [VERIFIED: src/career_evidence_graph/validation/store.py:62-75; tests/test_run_store.py:90-97]

### Pattern 2: Artifact facts are a read-only input layer

**What:** Derive a record containing source IDs, pinned commits, paths, hashes, proof limits, linked claims, and conflict/limitation references from the sealed fixture; let this record justify a question, never answer one.

**When to use:** Audit creation and `inspect` output; retain its hash/reference in every question and conclusion basis.

**Why:** The source manifest's documents have `personal_claim_proof: "none"`, and the Phase 2 fixture module explicitly says repository documents cannot establish responsibility or capability. [VERIFIED: validation/fixtures/stoa/v1/source-manifest.json:10-19; src/career_evidence_graph/domain/fixtures.py:1-6]

### Pattern 3: Two-round attribution and explicit conflict preservation

**What:** For a claim/capability area, first ask ownership (user/team/other/unresolved); only then ask assistance (none/coding agent/third party/unresolved), with tool/model details as metadata. If artifact and user assertions differ, record both plus the clarification result.

**When to use:** On initial attribution coverage and whenever an answer says the work was not personal.

**Why:** This implements D-10--D-13 and prevents treating a document, Git history, or coding-agent use as a shortcut to either ownership or mastery.

### Pattern 4: Proposal/correction lineage, not in-place conclusion edits

**What:** Generate an original conclusion proposal; an entry/whole-conclusion review emits a correction, confirmation, or rejection record carrying reviewer identity and reason. The original proposal remains immutable.

**When to use:** All AUD-05 review actions.

**Why:** `CorrectionRecord` already preserves `original_proposal`, `original_proposal_hash`, `correction`, `reviewer_id`, and `reason` verbatim. [VERIFIED: src/career_evidence_graph/validation/models.py:259-267]

### Assistance compatibility migration

The current source-of-truth union is exactly `AssistanceKind = Literal["none", "codex_assisted", "third_party"]`. [VERIFIED: src/career_evidence_graph/domain/models.py:32-35] The sealed STOA fixture contains exact persisted values `"assistance":"codex_assisted"`. [VERIFIED: validation/fixtures/stoa/v1/known-good.json:1] Implement a one-time, tested read-compatible migration (accept legacy persisted `codex_assisted`, write the new provider-neutral canonical value) before Phase 3 emits audit records. Do not silently rewrite sealed fixture bytes; preserve legacy provenance and make any reissue explicit. This last migration shape is an implementation recommendation, not a locked serialized format. [ASSUMED]

### Anti-Patterns to Avoid

- **Direct document-to-mastery/ownership inference:** Documents are bounded evidence, never a personal capability result. [VERIFIED: src/career_evidence_graph/domain/fixtures.py:1-6]
- **One LLM-generated checklist or multi-question turn:** Violates the locked focused-question and relevance constraints; implement policy guards first. [VERIFIED: .planning/phases/03-artifact-aware-grill-me-and-attribution-workflow/03-CONTEXT.md]
- **Mutating a conclusion after user feedback:** Loses audit custody; emit an immutable correction/rejection record. [VERIFIED: src/career_evidence_graph/validation/models.py:259-267]
- **Storing a Phase 3 numeric mastery score:** D-16 reserves calibrated score policy for Phase 4. [VERIFIED: .planning/phases/03-artifact-aware-grill-me-and-attribution-workflow/03-CONTEXT.md]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| JSON schema parsing | Loose dictionaries and ad-hoc checks | Existing `StrictModel` / Pydantic model validation | Existing project-wide fail-closed contract pattern. [VERIFIED: src/career_evidence_graph/validation/models.py:12-16] |
| Atomic snapshot publication | Direct `Path.write_text()` replacement | Existing tempfile + `fsync` + `os.replace` pattern | Avoids torn audit snapshots. [VERIFIED: src/career_evidence_graph/validation/store.py:77-90] |
| CLI framework | New interactive framework | `argparse` integration in `cli.py` | Existing project entrypoint is argparse; no UI requirement. [VERIFIED: src/career_evidence_graph/cli.py:48-120] |
| General workflow engine | Agent graph/checkpoint infrastructure | Pure transition function and local workspace | This MVP needs auditable deterministic transitions, not orchestration scale. [VERIFIED: AGENTS.md; .planning/PROJECT.md] |

**Key insight:** The difficult engineering is truth-preserving state and attribution custody, not chat UX. The project already supplies the correct primitive patterns; Phase 3 should compose them narrowly.

## Common Pitfalls

### Pitfall 1: Confusing structural validation with factual verification

**What goes wrong:** A well-formed answer/event becomes treated as proof of mastery or ownership.  
**Why it happens:** Schema validation confirms type/shape, not factual accuracy. [CITED: https://pydantic.dev/docs/validation/latest/concepts/models/]  
**How to avoid:** Separate artifact-established facts, user claims, capability-boundary results, self-assessment, and unresolved conflict in contracts and conclusion output.  
**Warning signs:** A conclusion states a numeric score, uses a document as personal proof, or has no unresolved/provisional field.

### Pitfall 2: Repeating questions after resume or incomplete answers

**What goes wrong:** The flow asks an already answered question, or asks several follow-ups at the same level.  
**Why it happens:** Coverage/follow-up count are implicit in prompt text rather than persisted state.  
**How to avoid:** Persist question identity, answer status, difficulty, one-follow-up allowance, and area coverage; make resumption call the same pure selector.  
**Warning signs:** A deterministic resume fixture produces a different next question or a second same-level follow-up.

### Pitfall 3: Attribution laundering through legacy terminology

**What goes wrong:** `codex_assisted` is erased, inferred to be ownership, or mapped to a numeric ability result.  
**Why it happens:** Updating a union without a read-compatibility plan breaks persisted evidence or loses provenance.  
**How to avoid:** Test legacy reading, new canonical writing, record tool/model only as optional provenance, and enforce distinct ownership/assistance rounds.  
**Warning signs:** A fixture migration changes unrelated hashes, or an assistance answer completes an ownership field.

### Pitfall 4: Workspace path escape or raw sensitive-data logging

**What goes wrong:** User-controlled IDs/paths escape the audit root, or raw model/answer data are over-logged.  
**Why it happens:** Persisted CLI workflows accept untrusted input and can expose private career data.  
**How to avoid:** Validate IDs, resolve and containment-check paths, use internally derived filenames, and define a redacted audit-event projection. Existing formal storage demonstrates destination containment checks. [VERIFIED: src/career_evidence_graph/validation/store.py:62-75] OWASP guidance requires trusted/generated paths or strict validation and calls for useful, sensitivity-aware logging. [CITED: https://cornucopia.owasp.org/taxonomy/asvs-5.0/05-file-handling/03-file-storage] [CITED: https://cornucopia.owasp.org/taxonomy/asvs-5.0/16-security-logging-and-error-handling/02-general-logging]

## Code Examples

Verified pattern adapted from existing source (not a new wire format):

```python
# Source: src/career_evidence_graph/validation/store.py:77-90
data = canonical_json_bytes(value) + b"\n"
descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
try:
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary_name, path)
except BaseException:
    Path(temporary_name).unlink(missing_ok=True)
    raise
```

Use this unchanged atomic-publication shape in the audit store after Pydantic validates a proposed new snapshot. The following existing strict base is the required contract parent:

```python
# Source: src/career_evidence_graph/validation/models.py:12-16
class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---|---|---|---|
| Current Phase 2 assistance literal `codex_assisted` | Locked Phase 3 provider-neutral `coding-agent-assisted` plus optional tool/model provenance | Phase 3 decision D-12 | Requires explicit compatibility/migration planning before persisted audit records are written. [VERIFIED: src/career_evidence_graph/domain/models.py:32-35; .planning/phases/03-artifact-aware-grill-me-and-attribution-workflow/03-CONTEXT.md] |
| Fixture document review | Contribution-level user capability/attribution audit | Phase 3 | Documents remain inspection inputs; they do not answer interview questions. [VERIFIED: src/career_evidence_graph/domain/fixtures.py:1-6] |

**Deprecated/outdated:** Treating a vendor name as the canonical assistance category is superseded by D-12; retain the legacy value only for compatibility/provenance. [VERIFIED: .planning/phases/03-artifact-aware-grill-me-and-attribution-workflow/03-CONTEXT.md]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | Read-compatible / write-canonical migration is the best exact serialization strategy for `codex_assisted` → `coding-agent-assisted`. | Assistance compatibility migration | Planner may need a different explicit version/reissue design. |
| A2 | A compact `audit/` package is the best exact module boundary. | Recommended Project Structure | Existing project conventions may favor another local organization. |
| A3 | Hash-linked append-only audit events should accompany a current snapshot. | Pattern 1 | Could be more than MVP needs; planner must keep it minimal while preserving required history. |

## Open Questions (RESOLVED)

1. **Schema and workspace:** Use frozen versioned JSON records (`audit-snapshot/v1`, `audit-conclusion/v1`) under one resolved `audits/<audit_id>/current.json` snapshot and append-only, hash-linked `events.jsonl`. IDs are allowlisted, snapshot replacement is atomic, and no database or second formal-run store is introduced. This is the minimum versioned JSON snapshot+event workspace consistent with D-07, D-15, AGENTS.md YAGNI, and the established `validation/store.py` pattern.
2. **Capability ladders:** Define deterministic ladders only for relevant areas present in the sealed STOA fixture. Store stable level IDs and neutral hard-to-simple question text in fixture-backed test data; `tests/test_audit_policy.py` proves demanding-first descent, the single same-level follow-up, and the D-09 stop boundary. Generalized model-generated ladders and every scoring rule remain outside Phase 3.
3. **Inspection exposure:** Provide a read-only `audit inspect` command and retain the inspection-record hash/reference in each question basis and conclusion entry. The command is optional and the audit still opens directly with the first reason-prefaced question, satisfying D-01 with the smallest independently inspectable exposure.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|---|---|---|---|---|
| `uv` | Locked test/lint commands | ✓ | `0.11.16` | Set `UV_CACHE_DIR` to a writable temporary location when needed. |
| Python 3.13.14 | Project `uv run --locked` | ✗ | — | Blocking: installed `uv` could not locate the required interpreter. |
| Codex CLI | Optional existing live-model technical seam only | ✓ | `0.146.0` | Default Phase 3 verification remains offline; no live model required. |

**Missing dependencies with no fallback:** Python 3.13.14 must be made available before the planner's normal `uv run --locked` validation commands can execute. The failed probe used a writable temporary uv cache and reported no managed/search-path Python 3.13.14.  
**Missing dependencies with fallback:** None for the default offline test design.

## Validation Architecture

### Test Framework

| Property | Value |
|---|---|
| Framework | pytest `9.1.1` [VERIFIED: pyproject.toml:18-22] |
| Config file | `pyproject.toml` [VERIFIED: pyproject.toml:24-30] |
| Quick run command | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q tests/test_audit_policy.py tests/test_audit_store.py` |
| Full suite command | `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked python scripts/run_pytest.py -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|---|---|---|---|---|
| AUD-01 | Artifact record is fixture/manifest bounded; reasons cite established vs unknown facts. | unit + integration | `... pytest -q tests/test_audit_inspection.py` | ❌ Wave 0 |
| AUD-02 | One output question, deterministic pause/resume, answers/coverage/conflicts retained. | unit + persistence | `... pytest -q tests/test_audit_policy.py tests/test_audit_store.py` | ❌ Wave 0 |
| AUD-03 | Reject multi-part/repeated/leading/artifact-answerable questions; accept a neutral capability probe. | unit parameter matrix | `... pytest -q tests/test_audit_policy.py -k question` | ❌ Wave 0 |
| AUD-04 | Ownership and assistance remain separate; conflict/unresolved/legacy migration cases are preserved. | unit + migration | `... pytest -q tests/test_audit_attribution.py tests/test_assistance_migration.py` | ❌ Wave 0 |
| AUD-05 | Entry and overall review yields immutable proposal/correction/confirmation/rejection lineage. | integration + CLI | `... pytest -q tests/test_audit_conclusion.py tests/test_audit_cli.py` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** targeted audit test file(s) plus `UV_CACHE_DIR=/tmp/career-evidence-uv-cache uv run --locked ruff check src tests`.
- **Per wave merge:** full offline pytest suite and `ruff format --check src tests`.
- **Phase gate:** Full suite green after Python 3.13.14 availability is restored; live-model execution remains excluded by the existing pytest configuration. [VERIFIED: pyproject.toml:24-30]

### Wave 0 Gaps

- [ ] `tests/test_audit_models.py` — strict audit contract rejection matrix.
- [ ] `tests/test_audit_inspection.py` — sealed source-manifest/fixture boundary and reason traceability.
- [ ] `tests/test_audit_policy.py` — one-question/relevance/anti-leading/difficulty/resume transition matrix.
- [ ] `tests/test_audit_store.py` — atomic snapshots, invalid IDs, corruption, and history immutability.
- [ ] `tests/test_audit_attribution.py` — separate ownership/assistance and conflict/unresolved flows.
- [ ] `tests/test_assistance_migration.py` — legacy `codex_assisted` compatibility with no sealed-fixture rewrite.
- [ ] `tests/test_audit_conclusion.py` and `tests/test_audit_cli.py` — review lineage and CLI end-to-end offline flow.
- [ ] Restore/install the locked Python 3.13.14 interpreter; do not change project Python range merely to use the host runtime. [VERIFIED: pyproject.toml:10]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---|---|---|
| V2 Authentication | no | Single-user local CLI; no authentication surface is planned. |
| V3 Session Management | no | Pause/resume is an audit-state record, not an authenticated web session. |
| V4 Access Control | limited | Restrict all workspace file reads/writes to the explicit local audit root. |
| V5 Input Validation / File Handling | yes | Strict Pydantic parsing, ID allowlists, `Path.resolve()` containment, and no user-controlled filenames. [VERIFIED: src/career_evidence_graph/validation/store.py:62-75] [CITED: https://cornucopia.owasp.org/taxonomy/asvs-5.0/05-file-handling/03-file-storage] |
| V6 Cryptography | limited | Reuse existing SHA-256 content hashes for tamper detection; do not invent encryption/cryptographic primitives. [VERIFIED: src/career_evidence_graph/domain/models.py:15-19; src/career_evidence_graph/validation/store.py:15-23] |
| V16 Security Logging | yes | Append-only, timestamped/redacted audit event projection; retain action/reviewer/cause but avoid credentials or unneeded raw prompt/model data. [CITED: https://cornucopia.owasp.org/taxonomy/asvs-5.0/16-security-logging-and-error-handling/02-general-logging] |

### Known Threat Patterns for local CLI audit state

| Pattern | STRIDE | Standard Mitigation |
|---|---|---|
| `run_id`/path traversal | Tampering / Information disclosure | Reject unsafe IDs and require resolved destination beneath audit root. [VERIFIED: src/career_evidence_graph/validation/store.py:69-75] |
| Snapshot or event tampering | Tampering / Repudiation | Canonical JSON hashes, immutable event/proposal/correction history, and verify-before-read. [VERIFIED: src/career_evidence_graph/validation/store.py:77-90,111-125] |
| Artifact text prompt injection | Tampering | Treat artifacts as untrusted data; extract bounded facts only, never execute artifact instructions or permit them to decide responsibility/capability. [VERIFIED: src/career_evidence_graph/domain/fixtures.py:1-6] |
| Attribution laundering | Spoofing / Repudiation | Separate ownership and assistance rounds; preserve contradictions and unresolved status. [VERIFIED: .planning/phases/03-artifact-aware-grill-me-and-attribution-workflow/03-CONTEXT.md] |

## Sources

### Primary (repository-verified)

- `src/career_evidence_graph/domain/models.py` — Phase 2 contracts and current assistance union.
- `src/career_evidence_graph/domain/fixtures.py` and `validation/fixtures/stoa/v1/source-manifest.json` — documentary proof boundary and sealed source scope.
- `src/career_evidence_graph/validation/models.py` and `store.py` — strict models, correction lineage, atomic storage, and path containment.
- `src/career_evidence_graph/cli.py`, `pyproject.toml`, existing tests — CLI and offline verification baseline.
- Phase 3 `CONTEXT.md`, `REQUIREMENTS.md`, and `STATE.md` — locked behavior and requirement scope.

### Secondary (official documentation)

- [Pydantic Models](https://pydantic.dev/docs/validation/latest/concepts/models/) — validation, model JSON parsing, and extra-field configuration.
- [pytest parametrization](https://docs.pytest.org/en/stable/how-to/parametrize.html) and [temporary paths](https://docs.pytest.org/en/stable/how-to/tmp_path.html) — isolated test-workspace patterns.
- [OWASP ASVS project](https://owasp.org/www-project-application-security-verification-standard/), [File Storage](https://cornucopia.owasp.org/taxonomy/asvs-5.0/05-file-handling/03-file-storage), and [General Logging](https://cornucopia.owasp.org/taxonomy/asvs-5.0/16-security-logging-and-error-handling/02-general-logging) — path and logging controls.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — entirely existing, pinned project dependencies and source patterns.
- Architecture: HIGH — directly derived from Phase 3 locked decisions and Phase 2 integration seams.
- Pitfalls: MEDIUM — repository evidence plus cited Pydantic/OWASP guidance.

**Research date:** 2026-08-26  
**Valid until:** 2026-09-25 for repository integration; recheck official library/security docs if implementation is delayed.
