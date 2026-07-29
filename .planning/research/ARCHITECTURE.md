# Architecture Research

**Domain:** Career Evidence Graph core-hypothesis validation
**Researched:** 2026-07-30
**Confidence:** HIGH for project/upstream mapping; MEDIUM for the still-unvalidated assessment and aggregation policies

## Recommended Architecture

### Decision

Build a **local-first modular monolith with versioned JSON artifacts, strict domain contracts, and an append-only audit trail**. The smallest useful system is a CLI or thin local application, not a multi-user service. It should exercise one complete path:

```text
STOA source material
  → confirmed Contributions and responsibility attribution
  → resumable one-question-at-a-time Grill-Me audit
  → confirmed Contribution–Skill assessments
  → provisional user Skill aggregation
  → structured JD expectations
  → usefulness report showing relevant Contributions and gaps
```

Do not build the full résumé compiler, a graph database, a generalized agent platform, or a production web application. The validation target is whether Contribution-grounded audits produce stable skill judgments that help explain fit for a few JDs.

### System Overview

```text
┌──────────────────────────── Human Review Surface ────────────────────────────┐
│ seed/inspect → confirm contribution → answer one question → confirm claims │
│                                  → review assessment → review JD comparison │
└──────────────┬──────────────────────────────┬────────────────────────────────┘
               │ typed commands               │ typed proposals/reports
┌──────────────▼──────────────────────────────▼────────────────────────────────┐
│                           Application Orchestrator                          │
│  use cases only: seed, audit-next, confirm, assess, aggregate, compare-jd  │
└──────┬──────────────┬────────────────┬──────────────────┬───────────────────┘
       │              │                │                  │
┌──────▼──────┐ ┌─────▼────────┐ ┌─────▼──────────┐ ┌────▼─────────────────┐
│ Grill-Me    │ │ Skill        │ │ Assessment &   │ │ JD Usefulness Slice │
│ Audit       │ │ Normalizer   │ │ Aggregation    │ │ parse → normalize → │
│ State       │ │ Adapter      │ │ Policies       │ │ compare → explain   │
└──────┬──────┘ └─────┬────────┘ └─────┬──────────┘ └────┬─────────────────┘
       │              │                │                  │
┌──────▼──────────────▼────────────────▼──────────────────▼───────────────────┐
│                          Strict Domain Model                               │
│ Experience ─CONTAINS→ Contribution ─DEMONSTRATES→ Skill                   │
│ Evidence ─SUPPORTS→ Contribution; ContributionSkillAssessment is audited  │
└───────────────────────────────────┬────────────────────────────────────────┘
                                    │ repository ports
┌───────────────────────────────────▼────────────────────────────────────────┐
│ Versioned Workspace: canonical/*.json + sessions/*.json + events/*.jsonl │
│ proposals/*.json + snapshots/* + fixtures/* + reports/* + provenance/*   │
└────────────────────────────────────────────────────────────────────────────┘
```

### Architectural Invariants

These are domain rules, not prompt suggestions:

1. `Contribution` is the only Grill-Me audit target. An `Experience` can organize Contributions but cannot directly establish mastery.
2. `Evidence` supports a Contribution. It does not itself demonstrate a Skill and is not a second interview hierarchy.
3. Every `ContributionSkillAssessment` keeps `demonstrated_mastery`, `skill_centrality`, `evidence_confidence`, `context`, `duration`, and `assessment_basis` separate.
4. Responsibility attribution distinguishes at least `user`, `team/shared`, `other_person`, `codex_assisted`, `third_party`, and `unknown`.
5. Ontology aliases and relations may normalize or suggest Skills; they cannot create a user mastery assertion.
6. JD fit is computed per target JD and never mutates the stable user mastery assessment.
7. Only confirmed claims can feed a canonical assessment. LLM output is always a proposal.
8. User-level aggregation is a versioned policy over confirmed Contribution–Skill assessments. It may remain provisional until golden cases support it.
9. A higher user mastery band requires evidence satisfying that band's observable anchor; repeated weaker Contributions cannot numerically accumulate into expertise.
10. Every derived result records input IDs/revisions, policy version, model/prompt version when applicable, timestamp, and confirmation status.

## Component Boundaries and Contracts

| Component | Owns | Input Contract | Output Contract | Must Not Own |
|---|---|---|---|---|
| Domain model | Entity identities, relationships, enums, validation invariants | Typed construction commands | Strict, versioned entities | LLM calls, persistence layout, scoring formula |
| Evidence registry | Artifact metadata, immutable hashes, excerpts/locations, access status | Local artifact path or user explanation reference | `Evidence` plus provenance | Skill inference or mastery |
| Contribution workspace | STOA `Experience`, Contribution decomposition, responsibility attribution | Seed fixture and decomposition proposal | Confirmed/rejected Contributions | Questions or scores |
| Audit orchestrator | Current Contribution, coverage checklist, question history, pause/resume state | `StartAudit`, `AnswerQuestion`, `ConfirmClaims` | Next question, proposal, or terminal coverage result | Direct persistence and aggregation |
| Question policy | One best next question based on unresolved audit coverage | Confirmed Contribution, evidence inventory, prior turns | Exactly one `Question` with reason and target | Multiple-question batches or final scores |
| Claim extractor | Structured capability/responsibility claims from one answer and cited artifacts | Answer turn plus bounded context | `ClaimProposal[]` with source spans | Canonical mutations |
| Skill normalizer | Canonical name/alias lookup and ontology relation suggestions | Raw skill phrase, pinned ontology version | Candidate canonical Skills and match rationale | Mastery propagation through `impliesKnowingSkills` |
| Assessment policy | Contribution-specific capability judgment | Confirmed claims, Evidence links, mastery anchors | `ContributionSkillAssessmentProposal` | User-level aggregation or JD fit |
| Aggregation/calibration | Stable user-level mastery candidate and explanation | Confirmed assessments for one Skill, policy version | `UserSkillAssessmentCandidate` plus trace | Evidence ingestion or target-JD relevance |
| JD parser | Structured expectations from a small raw JD fixture | JD text and parser version | `JobDescription`, `JDSkillExpectation[]` | Résumé rewriting |
| JD comparator | Target-specific usefulness calculation | JD expectations, user Skills, Contributions and assessments | `JDUsefulnessReport` | Mutation of mastery/confidence/duration |
| Evaluation harness | Golden cases, invariant tests, replay, calibration comparison | Versioned fixtures and recorded runs | Reproducible pass/fail and disagreement reports | Production ranking or automatic acceptance |
| Workspace repository | Atomic load/save, snapshots, append-only events, migrations | Versioned domain envelopes | Current canonical state and historical revisions | Business decisions |

### Minimal Domain Contracts

Use strict Pydantic-style models (`extra="forbid"`) or equivalent. Persist every top-level file in a versioned envelope.

```python
class Envelope(BaseModel):
    schema_version: str
    artifact_type: str
    artifact_id: str
    revision: int
    created_at: datetime
    updated_at: datetime
    data: dict
    model_config = ConfigDict(extra="forbid")

class ContributionSkillAssessment(BaseModel):
    id: str
    contribution_id: str
    skill_id: str
    demonstrated_mastery: int       # capability anchor reached here
    skill_centrality: int           # importance to this Contribution
    evidence_confidence: int        # credibility/admissibility, not capability
    context: str
    duration: DurationEvidence
    assessment_basis: list[AssessmentBasisItem]
    responsibility_attribution: ResponsibilityAttribution
    status: Literal["proposed", "confirmed", "rejected", "superseded"]
    policy_version: str
    model_config = ConfigDict(extra="forbid")
```

Additional contracts:

- `AuditSession`: `session_id`, `contribution_id`, `status`, `coverage_items`, `turn_ids`, `pending_confirmation_id`, `started_at`, `resumed_at`, `completed_at`.
- `AuditTurn`: immutable question, answer, cited Evidence IDs, artifact observations, and source spans.
- `ClaimProposal`: claim text, claim type, responsibility attribution, source turn/span, related Contribution, candidate Skills, confidence, confirmation status.
- `AssessmentBasisItem`: claim/evidence IDs, capability anchor supported, counterevidence/limitations, reviewer decision.
- `UserSkillAssessmentCandidate`: skill ID, mastery, supporting assessment IDs, anchor rationale, confidence summary, verified duration summary, contexts, aggregation policy version. Confidence, duration, and contexts are outputs alongside mastery, never ingredients hidden inside its meaning.
- `JDSkillExpectation`: normalized skill ID or unresolved phrase, requirement level (`required`, `preferred`, `contextual`), expected capability text, importance, source span, parser confidence.
- `SkillJDComparison`: stable mastery, evidence confidence summary, verified duration, matching contexts, JD importance, fit judgment, supporting Contribution IDs, limitations. Each field remains visible and separately inspectable.

### Command/Proposal Separation

Use a small application layer with typed commands:

```text
StartContributionAudit(contribution_id)
RecordAnswer(session_id, question_id, answer, evidence_ids)
ConfirmClaims(proposal_id, accepted_claim_ids, edits)
ProposeAssessment(contribution_id, skill_id)
ConfirmAssessment(proposal_id, edits)
AggregateSkill(skill_id, policy_version)
ParseJD(jd_id, parser_version)
CompareJD(jd_id, comparison_policy_version)
```

Each model-assisted operation produces a file under `proposals/`. A human confirmation command appends an event and writes a new canonical revision. Rejecting or editing a proposal never destroys the original proposal; this is essential for measuring model error.

## Explicit Data Flow and Confirmation Points

### Flow A: Seed and Confirm STOA

```text
source material/artifacts
  → Evidence registry hashes and indexes artifacts
  → decomposition proposes Experience + Contributions + attribution
  → [HUMAN CONFIRMATION 1] accept/edit/reject each Contribution and ownership
  → canonical STOA Experience and Contribution revisions
```

The system may inspect files before asking questions. It must not treat repository presence, authorship metadata, résumé prose, or an Experience title as mastery.

### Flow B: Grill-Me One Contribution

```text
confirmed Contribution + Evidence inventory + unresolved coverage
  → question policy chooses one question
  → user answers and may cite/add Evidence
  → claim extractor proposes concrete claims and responsibility classification
  → [HUMAN CONFIRMATION 2] accept/edit/reject extracted claims and attribution
  → coverage auditor identifies the next unresolved capability boundary
  → repeat until stop criteria are met
```

Coverage should test observable capability: explain, implement, reproduce, defend trade-offs, debug/failure handling, and operate/maintain where relevant. The policy chooses only applicable dimensions; it must not force every Contribution through an identical checklist.

Pause/resume occurs after every persisted turn. A pending confirmation is an explicit state, not a prompt convention. Resume loads the same session, pending proposal, and one next allowable action.

### Flow C: Contribution–Skill Assessment

```text
confirmed claims + linked Evidence + responsibility + mastery anchors
  → normalizer proposes canonical Skill identity
  → [HUMAN CONFIRMATION 3] confirm ambiguous normalization only
  → assessment policy proposes mastery, centrality, confidence, context, duration
  → invariant checks reject semantic collapse or unsupported anchor jumps
  → [HUMAN CONFIRMATION 4] review assessment and explicit basis
  → confirmed ContributionSkillAssessment revision
```

Normalization confirmation can be skipped for exact alias matches already covered by golden fixtures. Assessment confirmation cannot be skipped during validation because disagreement is a primary outcome.

### Flow D: User Skill Aggregation

```text
all confirmed assessments for one Skill
  → deterministic aggregation policy candidate
  → anchor gate checks observable requirements
  → report supporting and contradicting Contributions
  → [HUMAN CALIBRATION 5] record accept/adjust/reject and reason
  → provisional UserSkillAssessment revision
```

Keep the formula replaceable behind `AggregationPolicy`. During validation, store all candidate outputs and reviewer decisions. Do not make a database schema depend on one weighting formula.

### Flow E: Thin JD Usefulness Slice

```text
2–5 raw JD fixtures
  → parser proposes explicit required/preferred skill expectations and source spans
  → [HUMAN CONFIRMATION 6] correct normalization and importance in golden fixtures
  → comparator joins expectations to stable user Skills
  → relevance policy selects supporting Contributions
  → usefulness report:
       expectation | mastery | confidence | duration | context | JD fit
       supporting Contributions | limitations/gaps
```

This slice proves usefulness without generating résumé prose. A successful output answers:

- Which confirmed Contributions are relevant to this JD requirement, and why?
- What capability has actually been demonstrated?
- How credible and broad is the evidence?
- What is missing or only weakly supported?
- Would a human choose similar Contributions for a future tailored résumé?

Do not add layouts, PDF export, bullet rewriting, cover letters, or a résumé editor in this project.

## Persistence: Required Now vs Provisional

### Persist Canonically Now

| Data | Why It Must Persist |
|---|---|
| Experience, Contribution, Evidence, Skill identities and relations | Core graph under test |
| Responsibility attribution and user corrections | Truthfulness and auditability |
| Full question/answer turns with artifact citations | Replay and assessment basis |
| Claim proposals and confirmation decisions | Measures extraction error; prevents silent model mutation |
| Confirmed Contribution–Skill assessments | Primary validation output |
| JD raw text, parsed expectations, source spans, and corrections | Reproducible usefulness comparison |
| Model/prompt/policy/schema/upstream versions | Reproducibility and regression diagnosis |
| Golden fixtures and human review outcomes | Calibration evidence |
| Append-only events and supersession links | Preserve history without event-sourcing the whole product |

### Keep Replaceable/Provisional

| Decision | Representation Now | Why Not Freeze |
|---|---|---|
| Aggregation formula and weights | `AggregationPolicy` function plus versioned configuration | Core hypothesis requires empirical calibration |
| Confidence admission threshold | Named policy with fixture results | False-positive/negative trade-off is unknown |
| Audit stop criteria | Coverage policy and human override | Different Contribution types need different depth |
| Question-selection prompt/model | Versioned adapter | Model behavior will change |
| JD importance/fit formula | Explainable comparison policy | Only a small usefulness test is in scope |
| Ontology subset | Read-only pinned adapter and local Skill IDs | Avoid coupling canonical data to the full upstream ontology |
| Storage engine | Repository interface backed by files | JSON is enough for one user and golden cases |

### Workspace Layout

```text
workspace/
├── canonical/
│   ├── experiences.json
│   ├── contributions.json
│   ├── evidence.json
│   ├── skills.json
│   ├── contribution_skill_assessments.json
│   └── user_skill_assessments.json
├── sessions/<session_id>/
│   ├── state.json
│   └── turns.jsonl
├── proposals/
│   ├── claims/
│   ├── assessments/
│   └── jd_parses/
├── jobs/<jd_id>/
│   ├── source.txt
│   ├── expectations.json
│   └── usefulness_report.json
├── events/audit_events.jsonl
├── snapshots/<timestamp>/
├── fixtures/
│   ├── stoa/
│   ├── audits/
│   ├── assessments/
│   └── jds/
├── reports/
└── provenance/
    ├── upstream_baseline.json
    └── model_policy_versions.json
```

Write canonical files atomically (temporary sibling then rename), validate before replacement, and snapshot before migrations or recalibration runs. JSONL is appropriate for turns, confirmations, and reviews; current entities remain ordinary versioned JSON for simple inspection and diffs.

## Recommended Source Structure

```text
src/
├── domain/
│   ├── entities.py
│   ├── value_objects.py
│   ├── commands.py
│   ├── proposals.py
│   └── invariants.py
├── application/
│   ├── seed_stoa.py
│   ├── audit_contribution.py
│   ├── assess_contribution_skill.py
│   ├── aggregate_skill.py
│   └── compare_job.py
├── audit/
│   ├── state_machine.py
│   ├── question_policy.py
│   ├── claim_extractor.py
│   └── coverage_policy.py
├── skills/
│   ├── ontology_port.py
│   └── mind_adapter.py
├── assessment/
│   ├── contribution_policy.py
│   ├── aggregation_port.py
│   └── anchor_gates.py
├── jobs/
│   ├── parser.py
│   ├── comparator.py
│   └── usefulness_report.py
├── infrastructure/
│   ├── workspace_repository.py
│   ├── model_gateway.py
│   ├── artifact_reader.py
│   └── provenance.py
└── cli.py
tests/
├── unit/
├── contract/
├── golden/
├── adversarial/
└── replay/
```

Organize by domain capability, not by generic `controllers/services/models`. The application layer coordinates components; domain and policy modules remain testable without an LLM or filesystem.

## Build Order Driven by Dependencies and Hypothesis Risk

Every stage must leave a testable artifact.

1. **Freeze contracts, invariants, and fixtures**
   - Implement strict domain models, versioned envelopes, canonical mastery anchors, responsibility enum, and file repository.
   - Seed a hand-authored STOA Experience with distinguishable Contributions and Evidence links.
   - Evidence produced: schema tests, invalid-state tests, round-trip fixtures, provenance baseline.
   - This comes first because every upstream pattern must adapt to this model rather than redefine it.

2. **Validate Contribution decomposition and responsibility attribution**
   - Build artifact indexing, decomposition proposals, and confirmation workflow.
   - Evidence produced: human-reviewed STOA Contributions, false-attribution cases, accepted/rejected proposal log.
   - This attacks the highest upstream-integration risk: whole-experience or team work being mistaken for personal capability.

3. **Build a resumable single-Contribution Grill-Me loop**
   - Implement audit state machine, one-question policy, persisted turns, claim proposals, and confirmation.
   - Start with one representative STOA Contribution, then one contrasting Contribution.
   - Evidence produced: replayable transcripts, question-quality review, responsibility corrections, coverage/stop decisions.

4. **Produce Contribution–Skill assessments without aggregation**
   - Add normalizer adapter, separate assessment dimensions, basis trace, and human review.
   - Evidence produced: golden assessment cases, semantic-separation tests, counterexamples where confidence and mastery diverge.
   - Do not hide weak evidence behind a user-level score before this relationship is trustworthy.

5. **Calibrate replaceable user-level aggregation**
   - Implement at least one simple policy plus anchor gates; compare policy outputs across fixtures and repeated runs.
   - Evidence produced: reviewer agreement/disagreement, no-score-inflation tests, cross-context higher-anchor cases.
   - Exact formula remains provisional until this evidence supports a choice.

6. **Add the thin JD usefulness slice**
   - Parse a few JDs, confirm expectations, compare separate dimensions, rank/explain relevant Contributions.
   - Evidence produced: golden JD parses, selected-Contribution agreement, usefulness review, explicit gaps.
   - This is the first end-to-end hypothesis result and the stopping point for the validation project.

7. **Harden replay and adversarial evaluation**
   - Add prompt-injection artifacts, hidden-text cases, contradictory answers, fabricated ownership, ambiguous aliases, and repeat-run variance checks.
   - Evidence produced: deterministic invariant results and documented model variability.
   - Only after this gate should a roadmap consider résumé compilation.

## Upstream Integration Map

All pinned upstreams are reference inputs, not runtime dependencies. Copying or adapting code requires provenance in `provenance/upstream_baseline.json`, the relevant license/notice, a local divergence note, and a test expressing this project's distinct semantics.

| Local Component | Exact Upstream File/Pattern | Action | Adaptation / Rejection | License |
|---|---|---|---|---|
| Audit state and resumability | `tabiya-compass/backend/app/agent/skill_explorer_agent/skill_explorer_agent.py` (`SkillsExplorerAgentState` tracks questions/answers) | Adapt pattern | Key state by `contribution_id`, add pending confirmation, coverage, Evidence citations, revisions; do not audit whole Experience | MIT, pinned `8470bea…` |
| Conversation/extraction/transition separation | `tabiya-compass/backend/app/agent/collect_experiences_agent/collect_experiences_agent.py`, `_dataextraction_llm.py`, `_transition_decision_tool.py` | Adapt pattern | Separate next-question generation, claim extraction, and deterministic state transition; reject fixed work-type progression and automatic state mutation from extraction | MIT |
| Responsibility attribution | `tabiya-compass/backend/app/agent/skill_explorer_agent/_responsibilities_extraction_tool.py` and `_responsibilities_extraction_llm.py` | Adapt pattern | Preserve user/non-user/other-person separation; extend to team/shared, Codex-assisted, third-party, unknown; require confirmation before canonicalization | MIT |
| Application state repository | `tabiya-compass/backend/app/application_state.py`, `app/store/json_application_state_store.py` | Inspired-by | Keep repository port and file-backed state; add atomic writes, schema versions, migrations, proposal/history separation | MIT |
| One-question discipline | `mattpocock-skills/skills/productivity/grilling/SKILL.md` | Adapt behavioral pattern | Ask one question, inspect environment first, distinguish facts from user decisions; add Contribution target, coverage policy, and persisted outcome | MIT, pinned `2ab9580…` |
| Artifact-first grilling | `mattpocock-skills/skills/engineering/grill-with-docs/SKILL.md` | Adapt behavioral pattern | Read available Evidence before asking; reject documentation generation as the audit goal | MIT |
| Canonical vocabulary and boundary cases | `mattpocock-skills/skills/engineering/domain-modeling/SKILL.md` | Adapt pattern | Maintain domain glossary and challenge ambiguity; do not let glossary terms encode scoring policy | MIT |
| Skill normalization | `mind-tech-ontology/__aggregated_skills.json`, `skills/*.json`, `concepts/*.json` | Reuse data through adapter | Use canonical names, synonyms, misspellings, domains, concepts, and tasks from pinned read-only snapshot | MIT, pinned `2367527…` |
| Ontology loading | `mind-tech-ontology/skills.py` | Inspired-by, preferably reimplement small adapter | Implement only indexed lookup needed by fixtures; do not import the entire class hierarchy into the domain | MIT |
| Implied knowledge | `impliesKnowingSkills` / `impliesKnowingConcepts` fields in MIND data | Reject for mastery; allow suggestion only | May suggest a follow-up question or JD normalization candidate. Never create a user Skill or score from the edge | MIT |
| Versioned workspace | `cv-market-learning-planner/references/schemas.md`, `scripts/run_cycle.py` | Adapt pattern | Separate current canonical artifacts from history/snapshots; replace CV/gap/learning files with graph/audit/JD artifacts | MIT, pinned `ea50784…` |
| Append-only review history | `cv-market-learning-planner/scripts/update_progress.py` | Adapt code pattern | Use JSONL for audit turns, confirmations, calibration reviews; do not inherit exercise progress semantics | MIT |
| Strict structured boundaries | `hiring-agent/models.py` and `pdf.py` section-specific Pydantic/JSON Schema calls | Adapt pattern | Define project-specific strict models per extraction stage; validate proposals before display/persistence | MIT, pinned `70fd3ea…` |
| Staged extraction and caching | `hiring-agent/pdf.py`; cache orchestration in `hiring-agent/score.py` | Adapt pattern | Cache by content hash + model/prompt/schema version; never use stale outputs after policy changes | MIT |
| Role-specific configuration | `hiring-agent/roles.py`, `roles/<role>/role.json`, prompt templates | Inspired-by | Use versioned JD parsing/comparison policy configs; reject direct free-form résumé scoring and final LLM score | MIT |
| Adversarial lessons | `hiring-agent/README.md` coverage discussion | Reuse as fixture inspiration | Add variance, hidden-text, GitHub bias, and prompt-injection cases. GitHub signals cannot bypass Contribution audit | MIT |
| Raw JD ingestion | `resume-matcher/apps/backend/app/routers/jobs.py` | Adapt very thin pattern | Store raw JD and ID, then parse to versioned expectations; no database/service required | Apache-2.0, pinned `ad7754c…` |
| Golden JD fixtures and truthfulness checks | `resume-matcher/apps/backend/tests/evals/golden/cases.py`, `tests/evals/test_tailoring_eval.py`, `tests/unit/test_prompt_guardrails.py` | Adapt test pattern | Pair good/bad cases, use structural scorers first and optional LLM judge second; replace résumé-tailoring assertions with Contribution-selection and no-fabrication assertions | Apache-2.0 |
| Résumé schemas, editor, PDF/export | `resume-matcher/apps/backend/app/schemas/models.py`, frontend builder, PDF pipeline | Reject for this project | Useful only after graph usefulness is validated; flat résumé state must not become source of truth | Apache-2.0 |

### License-Aware Integration Rules

- MIT upstreams: retain copyright and permission notice in substantial copied/adapted portions; record source file and pinned commit.
- Resume Matcher is Apache-2.0: preserve license and notices, mark modified files, and do not assume MIT treatment. Prefer pattern adaptation rather than copying large subsystems.
- Maintain a per-file classification: `reuse`, `adapt`, `inspired-by`, or `reject`.
- A local test must demonstrate the divergence that matters: Contribution granularity, confirmed responsibility, separate score dimensions, no implied mastery, or JD fit isolation.

## Patterns to Follow

### 1. Proposal → Confirmation → Canonical Revision

**What:** Model output lives as an immutable proposal. Human decisions create a new canonical revision and append an event.

**Why:** Corrections are validation data. Direct model writes would erase the error signal and make audits irreproducible.

### 2. Functional Core, Imperative Shell

**What:** Parsing gateways and repositories handle I/O; domain validation, anchor gates, aggregation, and comparison are pure functions over typed inputs.

**Why:** The hypotheses can be tested without model calls, and changing a formula does not require changing persistence.

### 3. Evidence-Bearing Derivations

**What:** Every claim and score cites source turns, artifact locations, and prior entity revisions.

**Why:** Evidence and assertion are distinct. External Evidence Ontology practice likewise records evidence so users can understand why an assertion was made and apply quality control.

### 4. Stable Capability, Target-Specific Projection

**What:** User Skill assessment is stable; a JD comparison is a separate projection joining capability with target requirements.

**Why:** Research on competence-level prediction and résumé–JD suitability treats them as distinct tasks, and adjacent competence levels remain difficult even for expert annotators. Combining them would make calibration opaque.

## Anti-Patterns to Reject

### Experience-to-Skill Shortcut

**Mistake:** Infer Skills or mastery from the existence/title of an Experience.

**Consequence:** Team work, credentials, and broad summaries become unearned capability.

**Instead:** Audit confirmed Contributions and create assessments only from confirmed claims.

### One Ambiguous Relationship Score

**Mistake:** Multiply mastery, centrality, confidence, duration, and JD relevance into a single stored edge weight.

**Consequence:** A score change cannot be interpreted or calibrated.

**Instead:** Persist semantically distinct values and combine them only in a named, versioned view/policy.

### Ontology Edge as Personal Evidence

**Mistake:** `Next.js → React` becomes "the user masters React."

**Consequence:** Taxonomic knowledge turns into fabricated personal knowledge.

**Instead:** Use the edge to normalize a JD or ask a follow-up question.

### Transcript as Source of Truth

**Mistake:** Recompute all facts from raw chat on every run.

**Consequence:** State drifts with model versions and corrections are lost.

**Instead:** Preserve transcript plus confirmed claims and canonical revisions.

### Model as Workflow Controller

**Mistake:** Let a prompt decide whether to mutate state, skip confirmation, or declare the audit complete.

**Consequence:** Non-determinism changes process guarantees.

**Instead:** Model proposes; typed state machine validates allowed transitions.

### Premature Final Pipeline

**Mistake:** Add a graph database, agents, web UI, résumé rewriting, export, and gap sprints.

**Consequence:** The project can ship impressive plumbing without learning whether assessment is valid.

**Instead:** Stop at the JD usefulness report.

## Scaling Considerations

| Scale | Architecture Adjustment |
|---|---|
| Current validation: one user, STOA, 2–5 JDs | File-backed modular monolith; synchronous or simple async model calls; manual confirmation; no service boundary |
| Dozens of users / repeated pilots | Swap repository implementation to SQLite/PostgreSQL, add per-user encryption/access control and job queue; keep domain/application interfaces |
| Production product | Consider durable workflow execution, object storage, search/vector indexing, and separate résumé compiler only after measurement shows distinct load or ownership needs |

The first bottleneck will be review throughput and calibration consistency, not database scale. The second will be repeated model calls; address it with content-addressed stage caching and replay before adding distributed infrastructure.

## Validation and Observability

Record enough metadata to answer:

- Which question/prompt/model produced this proposal?
- Which exact answer span and Evidence supported each claim?
- What did the human change, and why?
- Which policy version produced this score or JD comparison?
- Does replay with the same recorded model output produce the same canonical result?
- How often do repeated live model runs disagree?

Required test layers:

1. Domain invariant and schema round-trip tests.
2. Contract tests for each model-assisted stage using recorded outputs.
3. Golden audit/assessment/JD cases with expected ranges and rationale, not only exact opaque scores.
4. Metamorphic tests: adding irrelevant Evidence or duplicate low-level Contributions cannot increase mastery.
5. Adversarial tests: hidden text, instruction injection, conflicting ownership, alias collisions, fabricated metrics, and copied repository content.
6. Human agreement reports for Contribution boundaries, confirmed claims, mastery anchors, and selected JD-relevant Contributions.

## Sources

### Pinned primary upstreams

- [Open-source reference baseline](../../references/README.md) — pinned revisions, reuse matrix, and license boundary. **Confidence: HIGH**
- [Tabiya Compass collect-experiences orchestration](../../references/upstream/tabiya-compass/backend/app/agent/collect_experiences_agent/collect_experiences_agent.py), [transition decision](../../references/upstream/tabiya-compass/backend/app/agent/collect_experiences_agent/_transition_decision_tool.py), [responsibility extraction](../../references/upstream/tabiya-compass/backend/app/agent/skill_explorer_agent/_responsibilities_extraction_tool.py), and [application state](../../references/upstream/tabiya-compass/backend/app/application_state.py). **Confidence: HIGH**
- [Matt Pocock one-question grilling](../../references/upstream/mattpocock-skills/skills/productivity/grilling/SKILL.md) and [domain modeling](../../references/upstream/mattpocock-skills/skills/engineering/domain-modeling/SKILL.md). **Confidence: HIGH**
- [MIND Tech Ontology README](../../references/upstream/mind-tech-ontology/README.md), [aggregated skills](../../references/upstream/mind-tech-ontology/__aggregated_skills.json), and [loader/classes](../../references/upstream/mind-tech-ontology/skills.py). **Confidence: HIGH**
- [CV Market Learning Planner workspace schema](../../references/upstream/cv-market-learning-planner/references/schemas.md), [snapshot cycle](../../references/upstream/cv-market-learning-planner/scripts/run_cycle.py), and [append-only reviews](../../references/upstream/cv-market-learning-planner/scripts/update_progress.py). **Confidence: HIGH**
- [Hiring Agent structured models](../../references/upstream/hiring-agent/models.py), [section extraction](../../references/upstream/hiring-agent/pdf.py), [role configuration](../../references/upstream/hiring-agent/roles.py), and [documented architecture/adversarial lessons](../../references/upstream/hiring-agent/README.md). **Confidence: HIGH**
- [Resume Matcher JD ingestion](../../references/upstream/resume-matcher/apps/backend/app/routers/jobs.py), [golden cases](../../references/upstream/resume-matcher/apps/backend/tests/evals/golden/cases.py), [tailoring evaluation](../../references/upstream/resume-matcher/apps/backend/tests/evals/test_tailoring_eval.py), and [prompt guardrails](../../references/upstream/resume-matcher/apps/backend/tests/unit/test_prompt_guardrails.py). **Confidence: HIGH**

### External corroboration

- [Pydantic models documentation](https://docs.pydantic.dev/latest/concepts/models/) — typed nested models, explicit extra-field behavior, validation, serialization, and JSON Schema. **Confidence: HIGH**
- [Microsoft Agent Framework human-in-the-loop with AG-UI](https://learn.microsoft.com/en-us/agent-framework/integrations/ag-ui/human-in-the-loop) — typed interrupt and resume protocol as corroboration for explicit persisted confirmation states. **Confidence: MEDIUM**
- [Evidence & Conclusion Ontology](https://evidenceontology.org/about_eco/) — separation of evidence, assertions, and assertion methods; evidence-bearing quality control. **Confidence: MEDIUM**
- [Li et al., “Competence-Level Prediction and Resume & Job Description Matching Using Context-Aware Transformer Models”](https://aclanthology.org/2020.emnlp-main.679/) — separate competence and suitability tasks; expert annotation and adjacent-level ambiguity. **Confidence: MEDIUM**

---
*Architecture research for: Career Evidence Graph — Core Hypothesis Validation*
*Researched: 2026-07-30*
