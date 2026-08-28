# Phase 2: Domain Contracts, STOA Fixture, and Deterministic Invariants - Research

**Researched:** 2026-07-30  
**Domain:** Contribution-grounded career-evidence contracts and deterministic offline fixtures  
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### STOA material sources

- **D-01:** Build candidate STOA facts only from Git-tracked development plans, handoffs, acceptance records, audit reports, and related project documentation in `stoa-backend`, `stoa-frontend`, `stoa-infra`, and `stoa-docs`. Do not inspect implementation code to extract the fixture.
- **D-02:** Pin the source snapshot to the current recorded HEAD of all four repositories:
  - `stoa-backend` — `84e93dae35dfde2c2e07fac6faf714b2d61c8377`
  - `stoa-frontend` — `42955a9ed38cfca868febffa752459ec27a88a30`
  - `stoa-infra` — `6d545ad8cae8d2fe67087f298d9d5fc7cc29b3f6`
  - `stoa-docs` — `53c91971572a52bf4bfdc68aebd8393f3080a76d`
- **D-03:** Exclude secrets, production or user data, caches, untracked files, and any other private operational material from fixture extraction.
- **D-04:** Repository documents may propose candidate project facts, but they cannot by themselves establish the user's personal responsibility, independent capability, or mastery. Those remain unconfirmed until human review.

### Contribution boundaries

- **D-05:** Represent STOA as one `Experience` containing all major documented outcomes, rather than selecting a small showcase subset.
- **D-06:** Define each `Contribution` as one independently explainable and auditable work outcome. A Contribution may span repositories when several components jointly deliver the same durable outcome.
- **D-07:** Consolidate development phases by durable product or system outcome. Do not create one Contribution per repository, commit, ticket, or development phase.
- **D-08:** Delivered and partially delivered outcomes may become Contributions, but every limitation must be preserved. Planned-only work remains background context and cannot generate a Skill or mastery assessment.

### Evidence and responsibility attribution

- **D-09:** Attribute each concrete work claim within a Contribution independently. A single Contribution may therefore contain user, team, other-person, non-responsibility, Codex-assisted, and third-party claims.
- **D-10:** Give each Evidence type an explicit proof limit:
  - plans establish intent or assignment, not completion;
  - handoffs and acceptance records establish recorded delivery;
  - audits establish observed state, defects, and limitations;
  - user confirmation establishes personal responsibility and claimed capability for fixture purposes.
- **D-11:** Store an Evidence item once and link it to one or more specific claims using section-level locators. Repeated links to the same source never count as independent Evidence.
- **D-12:** Preserve conflicting sources instead of silently choosing a winner. Mark the affected claim partial or unresolved, and prohibit a definite mastery conclusion until it is reviewed.

### Known-good and known-bad fixture generation

- **D-13:** The system drafts candidate facts from the selected documents; the user accepts, edits, or rejects each candidate. Only the resulting confirmed record may be labeled known-good.
- **D-14:** Confirm outcome facts, responsibility attribution, Evidence links, completion status, and limitations separately. Seal the known-good fixture only after every item is resolved or explicitly retained as unresolved.
- **D-15:** Derive each known-bad fixture from the confirmed known-good base and deliberately violate exactly one invariant. Record the base fixture and mutation so every expected rejection has one deterministic cause.
- **D-16:** Phase 2 fixture scores are human-confirmed test values or ranges used to exercise contracts and invariants. They are not calibrated real-world capability scores and must not imply that Phase 4 aggregation policy has been selected.
- **D-17:** Known-bad coverage must include, at minimum, direct mastery from an Experience/title/repository/résumé/ontology, wrong or obscured responsibility, duplicate Evidence inflation, missing lineage or assessment basis, dimension confusion, out-of-range values, and ontology-driven mastery changes.

### the agent's Discretion

- Exact class and field names beyond the locked semantic entities.
- Exact file layout for fixture source manifests, candidate-review records, sealed known-good data, and single-fault mutations.
- Exact deterministic IDs and locator syntax, provided they are stable, inspectable, and validated.
- Which additional negative cases are useful beyond the minimum classes, provided each case still violates only one rule.

### Deferred Ideas (OUT OF SCOPE)

- Interactive artifact-aware Grill-Me questioning, pause/resume behavior, and conclusion review belong to Phase 3.
- Real mastery calibration, confidence-admission gates, and user-level aggregation formulas belong to Phase 4.
- JD comparison, adversarial full-loop evaluation, and usefulness judgments belong to Phase 5.
- Product, application, interview, and hiring effectiveness conclusions belong outside this phase and require later empirical evidence.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|---|---|---|
| MOD-01 | Typed Experience records cover supported career-history types and contain distinguishable Contributions. | Use a closed `ExperienceType` literal plus nested `Contribution` records; require distinct stable IDs and one parent Experience. [VERIFIED: codebase grep + `.planning/REQUIREMENTS.md`] |
| MOD-02 | Contribution is the minimum auditable unit; direct Skill assessment from indirect sources is rejected. | Make every `ContributionSkillAssessment` and user-Skill record reference Contribution-based lineage only; add one negative fixture per prohibited direct source. [VERIFIED: codebase grep + `02-CONTEXT.md`] |
| MOD-03 | Typed provenance-bearing Evidence supports Contributions. | Model source kind, proof limit, pinned document locator, source hash, and claim links; never make Evidence a second audit hierarchy. [VERIFIED: codebase grep + `02-CONTEXT.md`] |
| MOD-04 | Contribution–Skill assessment has three independent bounded scores, context, duration, and basis. | Validate each 0–100 field independently and require non-empty context, duration state, and basis references. [VERIFIED: codebase grep + `.planning/PROJECT.md`] |
| MOD-05 | Attribution distinguishes own, team, other, non-responsibility, Codex-assisted, and third-party work. | Attribute each `ContributionClaim`, not the whole Experience; reject definite mastery without reviewed user-owned capability support. [VERIFIED: codebase grep + `02-CONTEXT.md`] |
| MOD-06 | One stable per-Skill mastery remains separate from confidence, duration, recency, context, and JD match. | Keep a narrowly scoped `UserSkillView` and separate evidence/context/JD view records; no Phase 2 aggregation formula. [VERIFIED: codebase grep + `.planning/PROJECT.md`] |
| MOD-07 | Normalization must not create or increase mastery. | Treat aliases and ontology adjacency as provenance-bearing canonicalization metadata only; regression-test non-propagation. [VERIFIED: codebase grep + `.planning/PROJECT.md`] |
| FIX-01 | Human-reviewed STOA fixture decomposes Contributions, Evidence, attribution, and assessments. | Use a pinned source manifest, candidate-review record, explicit human sealing checkpoint, then immutable known-good data. [VERIFIED: pinned STOA documents + `02-CONTEXT.md`] |
| FIX-02 | Good/bad fixtures cover score, context, duration, attribution, assistance, and evidence quality. | Generate each bad case through one declared mutation of the sealed good fixture and assert its sole invariant error. [VERIFIED: codebase grep + `02-CONTEXT.md`] |
</phase_requirements>

## Summary

Phase 2 should extend the existing strict Pydantic-v2 contract family, immutable formal-run store, canonical JSON hashing, and exact offline replay rather than introduce a database, generic graph engine, model call, or mutable fixture store. The implementation must represent the full STOA record as one Experience, but it must place every assessment lineage on a Contribution and then on independently attributed concrete claims. [VERIFIED: `src/career_evidence_graph/validation/models.py`, `store.py`, `replay.py`; CITED: https://pydantic.dev/docs/validation/latest/concepts/models/]

The pinned source review found a deliberately mixed documentary record: delivery/acceptance candidates, explicit internal-alpha and readiness limitations, and planned-only backlog items. The fixture therefore needs a source manifest that labels each document's proof limit and candidate status; documents can propose factual candidates but human confirmation is the only source that can establish the user's responsibility or capability. [VERIFIED: pinned `stoa-backend` Build Week Evidence and Full Project Audit; pinned `stoa-frontend` Production Readiness and Next-Stage Backlog; `02-CONTEXT.md`]

**Primary recommendation:** Add a small `domain` contract/invariant module and a versioned, document-only STOA fixture pipeline: `source manifest → candidate review → human-sealed known-good → declared one-fault known-bad`. [VERIFIED: existing Phase 1 contract/store patterns + `02-CONTEXT.md`]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| Strict Experience → Contribution → Claim/Evidence domain truth | API / Backend | Database / Storage | Validation lives in the importable Python domain core; JSON fixture files persist only already-validated records. [VERIFIED: existing `src/career_evidence_graph/validation/` package] |
| Evidence-source pinning, locators, and source-hash verification | Database / Storage | API / Backend | Source manifests and sealed fixtures need immutable, inspectable bytes; contract code validates their declared identity. [VERIFIED: existing `FormalRunStore` and hashing helpers] |
| Human acceptance, edit, or rejection of candidate facts | API / Backend | Database / Storage | Phase 2 stores review decisions and corrections, but does not build the Phase 3 conversational UI/state machine. [VERIFIED: `CorrectionRecord`; `02-CONTEXT.md`] |
| Deterministic known-good and one-fault known-bad validation | API / Backend | Database / Storage | Offline pytest invokes validators against sealed JSON and mutation metadata; it requires no browser, provider, or live service. [VERIFIED: `tests/test_security_boundaries.py`; `pyproject.toml`] |
| Alias/ontology normalization without mastery propagation | API / Backend | — | Canonicalization is metadata-only domain behavior; a normalizer cannot mutate an assessment or user-Skill value. [VERIFIED: `.planning/PROJECT.md`; `02-CONTEXT.md`] |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---|---|---|---|
| Python | `3.13.14` through `uv run --locked` | Domain models, deterministic fixture validation, JSON bytes, IDs, and CLI wiring. | The locked project environment resolves Python 3.13.14 and its default suite passes there. [VERIFIED: `uv run --locked python --version`; `pyproject.toml`] |
| Pydantic | `2.13.4` (already pinned) | Frozen, extra-forbidding nested contracts and cross-record validators. | The project already uses `StrictModel`; Pydantic documents `ConfigDict(extra='forbid')`, `model_validate*`, nested models, `model_dump`, and model validators for this kind of typed boundary. [VERIFIED: `pyproject.toml` and `src/career_evidence_graph/validation/models.py`; CITED: https://pydantic.dev/docs/validation/latest/concepts/models/] |
| Python standard library | Python 3.13 | Canonical JSON, SHA-256, `pathlib`, and declared JSON loading. | Existing Phase 1 canonical serialization and immutable-store code already use this boundary without a new runtime dependency. [VERIFIED: `hashing.py`, `store.py`] |

### Supporting

| Library | Version | Purpose | When to Use |
|---|---|---|---|
| pytest | `9.1.1` (already pinned) | Offline contract, fixture, single-fault, and non-propagation tests. | Use for every domain invariant and exact fixture regression; default configuration excludes live-model tests. [VERIFIED: `pyproject.toml`, Phase 1 validation report, and successful locked suite] |
| Ruff | `0.16.0` (already pinned) | Lint and formatting. | Run in the phase's full offline gate; it already excludes pinned upstreams and planning artifacts. [VERIFIED: `pyproject.toml` and successful locked Ruff checks] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|---|---|---|
| Pydantic strict models | Dataclasses with bespoke validation | Do not use: strict nested parsing, unknown-field rejection, JSON serialization, and structured errors are already established Pydantic patterns in this project. [VERIFIED: existing `StrictModel`; CITED: https://pydantic.dev/docs/validation/latest/concepts/models/] |
| Versioned JSON fixture workspace | SQLite or graph database | Do not use in Phase 2: the fixture is small, reviewable, immutable, and schema calibration is the goal; no concurrency/query-volume requirement exists. [VERIFIED: `AGENTS.md` stack constraints; `.planning/PROJECT.md`] |
| A declared, one-operation mutation record | Generic JSON Patch/diff subsystem | Do not use: each expected rejection must have one readable cause, so only the bounded mutation forms needed by fixture tests should exist. [VERIFIED: `02-CONTEXT.md` D-15] |

**Installation:** No package installation is authorized or required for Phase 2. [VERIFIED: `pyproject.toml`; `02-CONTEXT.md`]

## Package Legitimacy Audit

Not applicable — Phase 2 must use the already pinned Python, Pydantic, pytest, and Ruff environment and introduce no external package. [VERIFIED: `pyproject.toml`; `02-CONTEXT.md`]

## Architecture Patterns

### System Architecture Diagram

```text
Pinned, tracked STOA documents only
          │  (commit + path + section locator + source hash)
          ▼
SourceManifest ──validates scope/pins──► CandidateFact[]
                                             │
                                             │ user accepts / edits / rejects
                                             ▼
      CandidateReview + CorrectionRecord + explicit unresolved status
                                             │
                                             │ all items resolved or retained unresolved
                                             ▼
Experience ─contains─► Contribution ─contains─► ContributionClaim
                           │                         │
                           │                         └── attribution + confirmation state
                           ▼
               EvidenceDocument ─links once─► ClaimEvidenceLink[]
                           │
                           ▼
ContributionSkillAssessment ──► UserSkillView (fixture expectation only)
        │                              │
        │                              └── separate evidence/duration/context/JD view
        ▼
Sealed known-good fixture ──single declared mutation──► known-bad fixture → invariant error
```

The diagram follows the Phase 2 boundary: document extraction proposes facts, human review establishes personal claims, and only Contribution-based records can reach an assessment. [VERIFIED: `02-CONTEXT.md` D-04, D-09–D-16]

### Recommended Project Structure

```text
src/career_evidence_graph/
├── domain/
│   ├── models.py          # Strict Experience, Contribution, Claim, Evidence, Skill, assessment views
│   ├── invariants.py      # Cross-record lineage, attribution, duplicate, and non-propagation validators
│   └── fixtures.py        # Bounded known-good loading and single-fault mutation validation
├── validation/            # Preserve Phase 1 formal-run, replay, provenance, and acceptance boundaries
└── cli.py                 # Extend only with deterministic fixture validation commands if needed

validation/fixtures/stoa/v1/
├── source-manifest.json   # Four pinned repos, permitted document paths, proof limits, hashes
├── candidates.json        # Document-derived proposals; not personal facts or mastery
├── review.json            # Accept/edit/reject/unresolved record plus retained corrections
├── known-good.json        # Sealed human-reviewed contract fixture
└── known-bad/             # One declared mutation + expected invariant error per case

tests/
├── test_domain_models.py
├── test_domain_invariants.py
├── test_stoa_fixture.py
└── test_fixture_mutations.py
```

This separates reusable domain truth from Phase 1's validation infrastructure while using the established package, fixture, hashing, and offline-test conventions. [VERIFIED: existing source tree, `tests/conftest.py`, and `02-CONTEXT.md`]

### Pattern 1: Strict contract plus collection-level invariant gate

**What:** Keep individual records syntactically strict, then validate foreign keys, uniqueness, source proof limits, and prohibited paths at the aggregate fixture boundary. [CITED: https://pydantic.dev/docs/validation/latest/concepts/models/; VERIFIED: existing `ValidationCharter` model validator]

**When to use:** Use it whenever an invariant needs more than one record, such as “all assessment evidence links resolve to claims inside the referenced Contribution.” [VERIFIED: `02-CONTEXT.md` D-09–D-12]

**Example:**

```python
# Source: project StrictModel pattern and Pydantic v2 model validators
from typing import Literal

from pydantic import Field, model_validator

from career_evidence_graph.validation.models import StrictModel


class ContributionSkillAssessment(StrictModel):
    schema_version: Literal["contribution-skill-assessment/v1"]
    assessment_id: str
    contribution_id: str
    skill_id: str
    demonstrated_mastery: int = Field(ge=0, le=100)
    skill_centrality: int = Field(ge=0, le=100)
    evidence_confidence: int = Field(ge=0, le=100)
    context: str = Field(min_length=1)
    verified_duration_months: int | None = Field(default=None, ge=0)
    assessment_basis_claim_ids: tuple[str, ...]

    @model_validator(mode="after")
    def requires_basis(self):
        if not self.assessment_basis_claim_ids:
            raise ValueError("assessment requires an explicit claim-level basis")
        return self
```

The fixture-level gate, not this single model, must verify that IDs resolve and that an unresolved/conflicting or non-user claim cannot yield a definite mastery conclusion. [VERIFIED: `02-CONTEXT.md` D-09–D-12]

### Pattern 2: Evidence document once; evidence links are references, not votes

**What:** Assign one stable `evidence_id` to a document section and link it to concrete claim IDs with a uniqueness rule on `(evidence_id, claim_id)`. Count independent documents or confirmation events deliberately; never count repeated links as additional support. [VERIFIED: `02-CONTEXT.md` D-10–D-11]

**When to use:** Use this for one audit/acceptance/handoff section that supports more than one claim. [VERIFIED: pinned STOA documents and `02-CONTEXT.md`]

### Pattern 3: State preservation, not conflict repair

**What:** Model claim status as `confirmed`, `partial`, or `unresolved`, retain every conflicting locator, and disallow `definite` assessment conclusions when the basis is partial/unresolved. [VERIFIED: `02-CONTEXT.md` D-12]

**When to use:** Use whenever a plan claims an outcome while an audit says readiness, ownership, or completion is limited. [VERIFIED: pinned `stoa-docs/PLAN.md` and `stoa-backend/docs/audit/full-project-audit.md`]

### Pattern 4: Human-sealed golden fixture and single-fault mutations

**What:** Keep proposals and reviewer edits as review history, produce an immutable known-good payload only after the checkpoint, and make each negative case an explicit base-hash plus one typed mutation and one expected invariant code. [VERIFIED: existing `CorrectionRecord`/`FormalRunStore`; `02-CONTEXT.md` D-13–D-16]

**When to use:** Use for every Phase 2 known-bad case. The mutation engine must reject multi-operation cases and validation must assert that the named invariant is the only intentionally violated rule. [VERIFIED: `02-CONTEXT.md` D-15, D-17]

### Anti-Patterns to Avoid

- **Experience-level scoring:** Reject any constructor/API that can make an assessment from an Experience, title, credential, repository, résumé list, or ontology edge; it violates MOD-02. [VERIFIED: `.planning/REQUIREMENTS.md`; `02-CONTEXT.md` D-17]
- **One attribution label per Contribution:** Do not use it; concrete claims can have different owners/assistance within one durable outcome. [VERIFIED: `02-CONTEXT.md` D-09]
- **Evidence link counting:** Do not derive evidence confidence or mastery from link count; one source repeated many times remains one source. [VERIFIED: `02-CONTEXT.md` D-11]
- **Silent conflict resolution:** Do not choose the more favorable record; retain both locators and downgrade to partial/unresolved until review. [VERIFIED: `02-CONTEXT.md` D-12]
- **Automatic fixture sealing:** Do not label a document-only result known-good; execution needs a human checkpoint that confirms each required field. [VERIFIED: `02-CONTEXT.md` D-04, D-13–D-14]
- **Pydantic `model_construct()` for untrusted fixture JSON:** Do not use it; it bypasses validation. [CITED: https://pydantic.dev/docs/validation/latest/concepts/models/]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| Nested schema parsing and unknown-field handling | Ad hoc dictionaries with manual key checks | Existing `StrictModel` Pydantic-v2 base plus `model_validate` | It already rejects schema drift and provides structured nested validation. [VERIFIED: `models.py`; CITED: https://pydantic.dev/docs/validation/latest/concepts/models/] |
| Immutable fixture/run publication and ancestry | A second mutable fixture writer | `FormalRunStore`, canonical JSON bytes, SHA-256 hashes, and linked corrections | Phase 1 already tests atomic publication, tamper detection, and parent verification. [VERIFIED: `store.py`, `hashing.py`, `tests/test_run_store.py`] |
| Exact recorded replay | A new provider/model runner | `replay_recorded_response` | Existing replay reads retained bytes only and cannot invoke a live runner. [VERIFIED: `replay.py`, `tests/test_security_boundaries.py`] |
| General graph database / ontology inference engine | Neo4j/vector store or mastery propagation | Small explicit relationships and metadata-only normalization records | Graph/ontology adjacency cannot create mastery and infrastructure is out of scope. [VERIFIED: `.planning/PROJECT.md`; `02-CONTEXT.md`] |
| Generic patch framework | Recursive diff/patch engine | A closed, typed one-fault mutation record | D-15 requires readable, deterministic one-cause rejection, not broad patch semantics. [VERIFIED: `02-CONTEXT.md` D-15] |

**Key insight:** Phase 2's difficult work is semantic containment and reviewable lineage, not data-storage scale; reuse the already-tested strict/immutable primitives and keep the new code narrowly domain-specific. [VERIFIED: existing Phase 1 code/tests; `.planning/PROJECT.md`]

## Common Pitfalls

### Pitfall 1: Treating documented project work as personal proof

**What goes wrong:** A delivery record, project title, repository, or plan is turned directly into the user's responsibility or mastery. [VERIFIED: `02-CONTEXT.md` D-04, D-10]

**Why it happens:** Documentary sources can establish different things—intent, recorded delivery, observed limitation, or a candidate fact—but have different proof limits. [VERIFIED: `02-CONTEXT.md` D-10]

**How to avoid:** Require a per-claim attribution and review status; only user confirmation can establish personal responsibility/capability for this fixture, while other evidence remains provenance-bearing support. [VERIFIED: `02-CONTEXT.md` D-04, D-09–D-10]

**Warning signs:** A known-good payload has no reviewer decision, no claim-level attribution, or an assessment basis that names a repository rather than claim IDs. [VERIFIED: `02-CONTEXT.md` D-04, D-13–D-14]

### Pitfall 2: Losing limitations when consolidating a coherent STOA Experience

**What goes wrong:** “One Experience” becomes a showcase summary that converts partially delivered or planned outcomes into completed Contributions. [VERIFIED: `02-CONTEXT.md` D-05–D-08]

**Why it happens:** STOA documents include delivery candidates, an internal-alpha/readiness limitation, and a separately labelled next-stage backlog. [VERIFIED: pinned `stoa-backend/docs/audit/full-project-audit.md`; pinned `stoa-frontend/docs/release/next-stage-backlog.md`]

**How to avoid:** Keep a completion status and limitations on every candidate/Contribution; only `delivered` or `partially_delivered` outcomes are contribution-eligible, while planned work is explicit background context. [VERIFIED: `02-CONTEXT.md` D-08]

**Warning signs:** A backlog-only path is linked to an assessment, or an audit limitation disappears from the sealed record. [VERIFIED: `02-CONTEXT.md` D-08, D-12]

### Pitfall 3: Collapsing three assessment dimensions

**What goes wrong:** High centrality or high evidence confidence is presented as high mastery, or scores are constrained to agree. [VERIFIED: `.planning/PROJECT.md`; `.planning/REQUIREMENTS.md` MOD-04]

**Why it happens:** Each score shares the 0–100 range but measures different semantics. [VERIFIED: `.planning/PROJECT.md`]

**How to avoid:** Use three independently bounded fields, test deliberately contrasting cases, and require the assessment basis to name the capability evidence for mastery specifically. [VERIFIED: `.planning/PROJECT.md`; `02-CONTEXT.md` D-16–D-17]

**Warning signs:** A validator says scores must equal or ordered, or a user-level field silently mixes confidence/duration/JD match into mastery. [VERIFIED: `.planning/PROJECT.md`; `02-CONTEXT.md`]

### Pitfall 4: Duplicate evidence inflation through references

**What goes wrong:** Multiple links to the same document section are treated as independently corroborating Evidence. [VERIFIED: `02-CONTEXT.md` D-11]

**Why it happens:** An evidence list is stored per claim/assessment with no global evidence identity. [VERIFIED: `02-CONTEXT.md` D-11]

**How to avoid:** Store source evidence globally once, enforce link uniqueness, and make any confidence/admission calculation inspect unique evidence IDs rather than link rows. [VERIFIED: `02-CONTEXT.md` D-11]

**Warning signs:** A known-bad duplicate source changes only multiplicity and nonetheless increases a score or evidence count. [VERIFIED: `02-CONTEXT.md` D-17]

### Pitfall 5: Letting normalization mutate truth

**What goes wrong:** Adding an alias, ontology dependency, or `implies knowledge` edge creates a new user Skill or promotes mastery. [VERIFIED: `.planning/REQUIREMENTS.md` MOD-07; `02-CONTEXT.md` D-17]

**Why it happens:** Normalization and assessment fields share mutable records or normalization returns a scored result. [VERIFIED: `.planning/PROJECT.md`; `02-CONTEXT.md`]

**How to avoid:** Treat normalization as a separate mapping/provenance output; regression-test the byte-identical mastery portion of the fixture before and after alias/edge changes. [VERIFIED: `.planning/PROJECT.md`; existing canonical JSON helpers]

**Warning signs:** An ontology-only fixture validates a new `UserSkillView`, changes `demonstrated_mastery`, or adds an assessment without a Contribution ID. [VERIFIED: `.planning/REQUIREMENTS.md` MOD-02, MOD-07]

## Code Examples

Verified patterns from the current project and official Pydantic documentation:

### Load a sealed fixture through validation, then canonicalize for identity

```python
# Source: `StrictModel`, `canonical_json_bytes`, and Pydantic model_validate documentation
import json
from pathlib import Path

from career_evidence_graph.domain.models import CareerEvidenceFixture
from career_evidence_graph.validation.hashing import canonical_json_bytes, sha256_digest


def load_fixture(path: Path) -> CareerEvidenceFixture:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return CareerEvidenceFixture.model_validate(payload)


fixture = load_fixture(Path("validation/fixtures/stoa/v1/known-good.json"))
fixture_hash = sha256_digest(canonical_json_bytes(fixture))
```

This intentionally uses validation rather than `model_construct()`, which Pydantic documents as a no-validation path. [CITED: https://pydantic.dev/docs/validation/latest/concepts/models/]

### Assert alias normalization does not change mastery

```python
# Source: Phase 2 non-propagation decision and canonical JSON helper
before = fixture.user_skill_views
normalization = normalize_skill_aliases(fixture.skills, alias_index)
after = apply_normalization_metadata(fixture, normalization).user_skill_views

assert canonical_json_bytes(after) == canonical_json_bytes(before)
```

`apply_normalization_metadata` must not be able to create, remove, or modify an assessment/user-Skill record. [VERIFIED: `.planning/REQUIREMENTS.md` MOD-07; `02-CONTEXT.md` D-17]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---|---|---|---|
| Pydantic v1-style `class Config`, `parse_obj`, and ad hoc dictionaries | Pydantic-v2 `ConfigDict`, `model_validate*`, `model_dump`, and `@model_validator` | Current project uses v2 APIs from Phase 1. | Preserve the existing v2 strict contract pattern; do not introduce deprecated v1 style into Phase 2. [VERIFIED: `src/career_evidence_graph/validation/models.py`; CITED: https://pydantic.dev/docs/validation/latest/concepts/models/] |
| Mutable case files or generated test data | Immutable formal bundles, full input hashes, corrections retaining original proposals, and exact recorded replay | Established in Phase 1. | STOA sealing and revisions must preserve prior bytes/lineage rather than overwrite a “golden” record. [VERIFIED: `store.py`, `models.py`, `tests/test_run_store.py`] |

**Deprecated/outdated:** `model_construct()` for fixture ingress is unsuitable because it skips validation and can create invalid models. [CITED: https://pydantic.dev/docs/validation/latest/concepts/models/]

## Assumptions Log

All implementation recommendations are grounded in the locked context, current repository, pinned documents, or official Pydantic documentation; no `[ASSUMED]` claim is used. [VERIFIED: research sources listed below]

## Open Questions

1. **When will the user conduct the required STOA candidate review?**
   - What we know: A document-only candidate record cannot be known-good; D-13 and D-14 require acceptance/edit/rejection and separate confirmation of facts, attribution, Evidence, completion, and limitations. [VERIFIED: `02-CONTEXT.md` D-13–D-14]
   - What's unclear: The confirmed personal-responsibility and capability decisions are not available during research. [VERIFIED: `02-CONTEXT.md` D-04]
   - Recommendation: The plan must include a blocking `checkpoint:human-verify` after deterministic candidate extraction and before `known-good.json` is sealed; execution may still create/test contracts and unsealed candidates before that checkpoint. [VERIFIED: `02-CONTEXT.md` D-04, D-13–D-14]

2. **Which exact score values/ranges will the human confirm for fixture cases?**
   - What we know: Phase 2 values exercise contracts/invariants only and cannot claim real calibration or select a Phase 4 aggregation policy. [VERIFIED: `02-CONTEXT.md` D-16]
   - What's unclear: Specific test values must follow the actual review rather than be inferred from documents. [VERIFIED: `02-CONTEXT.md` D-04, D-16]
   - Recommendation: Define deterministic fixture slots and range/score validation now, then fill them only at the review checkpoint and preserve the reviewer correction history. [VERIFIED: existing `CorrectionRecord`; `02-CONTEXT.md` D-13–D-16]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|---|---|---|---|---|
| Project Python through uv | Contract/test execution | ✓ | Python `3.13.14` through `uv run --locked` | — [VERIFIED: environment probe] |
| uv | Locked environment and full validation gate | ✓ | `0.11.16`; locked commands pass | Do not modify the lockfile in this phase; any uv-version alignment is separate from domain work. [VERIFIED: environment probe and successful locked suite] |
| Git | Read pinned STOA documents only by commit/path | ✓ | `2.54.0` | — [VERIFIED: environment probe] |
| Four local STOA repositories | Source manifest/candidate extraction | ✓ | Context-pinned HEADs resolve; only untracked `.DS_Store` appears in `stoa-infra` and `stoa-docs` | Exclude all working-tree/untracked material and read only `git show <pin>:<document>`. [VERIFIED: git probes] |
| External model/provider | Phase 2 default validation | Not required | — | Default suite remains offline; live Codex remains an opt-in technical gate only. [VERIFIED: `pyproject.toml`, `tests/test_codex_cli.py`, `02-CONTEXT.md`] |

**Missing dependencies with no fallback:** None for deterministic Phase 2 implementation. [VERIFIED: environment probe]

**Missing dependencies with fallback:** None. [VERIFIED: environment probe]

## Validation Architecture

### Test Framework

| Property | Value |
|---|---|
| Framework | pytest `9.1.1` with Pydantic contracts. [VERIFIED: `pyproject.toml`] |
| Config file | `pyproject.toml`. [VERIFIED: `pyproject.toml`] |
| Quick run command | `uv run --locked pytest -q tests/test_domain_models.py tests/test_domain_invariants.py tests/test_stoa_fixture.py tests/test_fixture_mutations.py` (Wave 0 adds these files). [VERIFIED: existing pytest convention; planned Phase 2 coverage] |
| Full suite command | `uv run --locked pytest -q && uv run --locked ruff check . && uv run --locked ruff format --check .`. [VERIFIED: Phase 1 validation report; executed successfully during this research] |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|---|---|---|---|---|
| MOD-01 | All supported Experience types can contain distinct Contributions with valid parent/ID references. | unit | `uv run --locked pytest -q tests/test_domain_models.py -k experience` | ❌ Wave 0 |
| MOD-02 | Direct Experience/credential/title/repository/résumé/ontology → mastery paths reject. | unit + negative fixture | `uv run --locked pytest -q tests/test_domain_invariants.py -k direct_mastery` | ❌ Wave 0 |
| MOD-03 | Evidence has a pinned section locator and claim-level links without a second audit hierarchy. | unit | `uv run --locked pytest -q tests/test_domain_models.py -k evidence` | ❌ Wave 0 |
| MOD-04 | Three scores validate independently; required context/duration/basis and bad ranges reject. | unit | `uv run --locked pytest -q tests/test_domain_models.py -k assessment` | ❌ Wave 0 |
| MOD-05 | Per-claim attribution and assistance boundaries remain distinguishable; unsupported definite mastery rejects. | unit + fixture | `uv run --locked pytest -q tests/test_domain_invariants.py -k attribution` | ❌ Wave 0 |
| MOD-06 | One user-Skill mastery is unique/specific and separate evidence/duration/recency/context/JD data cannot overwrite it. | unit | `uv run --locked pytest -q tests/test_domain_invariants.py -k user_skill` | ❌ Wave 0 |
| MOD-07 | Alias/ontology metadata creates or changes no mastery record. | regression | `uv run --locked pytest -q tests/test_domain_invariants.py -k ontology` | ❌ Wave 0 |
| FIX-01 | Pin-only source manifest, candidate review, human-sealed known-good fixture, and lineage resolve. | integration + manual checkpoint | `uv run --locked pytest -q tests/test_stoa_fixture.py` | ❌ Wave 0 |
| FIX-02 | Every known-bad case has one base, one declared mutation, and one expected rejection class. | regression | `uv run --locked pytest -q tests/test_fixture_mutations.py` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** Run the smallest listed module for the changed contract/fixture plus Ruff on changed code. [VERIFIED: Phase 1 validation strategy]
- **Per wave merge:** Run the full offline suite and lint/format command. [VERIFIED: Phase 1 validation strategy]
- **Phase gate:** Full suite green, source-manifest pins verified, every known-bad fixture reports its declared sole failure, and the human review checkpoint has sealed the good fixture before asserting FIX-01/FIX-02 complete. [VERIFIED: `02-CONTEXT.md` D-13–D-17]

### Wave 0 Gaps

- [ ] `src/career_evidence_graph/domain/__init__.py` and domain modules — strict contracts/invariants/fixture helpers for MOD-01–MOD-07.
- [ ] `validation/fixtures/stoa/v1/source-manifest.json` — permitted document-only, pinned locator inventory.
- [ ] `validation/fixtures/stoa/v1/candidates.json` and `review.json` — auditable proposal/review separation.
- [ ] `validation/fixtures/stoa/v1/known-good.json` — created only after `checkpoint:human-verify`.
- [ ] `validation/fixtures/stoa/v1/known-bad/*.json` — one fault and expected error per case.
- [ ] `tests/test_domain_models.py`, `tests/test_domain_invariants.py`, `tests/test_stoa_fixture.py`, `tests/test_fixture_mutations.py` — requirement coverage above.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---|---|---|
| V2 Authentication | No | This is a local offline domain/fixture phase with no user authentication surface. [VERIFIED: Phase 2 scope and existing CLI] |
| V3 Session Management | No | No session state is added; Phase 3 owns resumable interview state. [VERIFIED: `02-CONTEXT.md` deferred ideas] |
| V4 Access Control | No | No multi-user/API authorization surface is introduced; claim attribution is evidence semantics, not an access-control mechanism. [VERIFIED: Phase 2 scope] |
| V5 Input Validation | Yes | Strict extra-forbidding Pydantic models, content-hash/source-pin checks, locator validation, explicit one-fault mutation schema, and fail-closed errors. [VERIFIED: existing `StrictModel`/`FormalRunStore`; CITED: https://pydantic.dev/docs/validation/latest/concepts/models/] |
| V6 Cryptography | Yes, integrity only | Reuse existing SHA-256 canonical-content identifiers; do not implement cryptography. [VERIFIED: `hashing.py`] |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---|---|---|
| Source/document scope escape via untracked file, implementation code, symlink, or mutable working tree | Tampering | Source manifest accepts only fixed commit/path documents; load with `git show <pin>:<path>` or verified stored bytes; reject outside paths. [VERIFIED: `02-CONTEXT.md` D-01–D-03; existing store path tests] |
| Document text prompts the system to treat an unverified personal claim as fact | Spoofing | Treat documents as untrusted candidate input; retain proof limit and require explicit human confirmation for responsibility/capability. [VERIFIED: `02-CONTEXT.md` D-04, D-10] |
| Duplicate evidence link inflates confidence/mastery | Tampering | Global evidence identity plus unique `(evidence_id, claim_id)` links; negative regression from the same sealed base. [VERIFIED: `02-CONTEXT.md` D-11, D-17] |
| Attribution laundering through Contribution-level label | Spoofing | Per-claim attribution enum and assessment gate requiring reviewed user-owned support. [VERIFIED: `02-CONTEXT.md` D-09, D-17] |
| Fixture overwrite or unexplained mutation | Repudiation | Reuse immutable formal-run/correction history and require base hash plus a single typed mutation. [VERIFIED: `FormalRunStore`, `CorrectionRecord`, `02-CONTEXT.md` D-15] |
| Operational/secret/user data included in the research fixture | Information Disclosure | Permit only named tracked documents and redact/exclude secrets, production/user data, caches, and untracked materials. [VERIFIED: `02-CONTEXT.md` D-01–D-03] |

## Sources

### Primary (HIGH confidence)

- `02-CONTEXT.md` — locked Phase 2 source scope, proof limits, review/sealing gate, and required negative classes. [VERIFIED: codebase grep]
- `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md` — domain semantics, requirements MOD-01–MOD-07/FIX-01/FIX-02, phase goal, and active planning state. [VERIFIED: codebase grep]
- `src/career_evidence_graph/validation/models.py`, `store.py`, `replay.py`, `hashing.py`, and Phase 1 tests — established strict, immutable, replay, and hashing patterns. [VERIFIED: codebase grep]
- Pinned STOA documentation at the four exact commits — candidate outcome facts and limitations only; no implementation code was used for extraction. [VERIFIED: `git rev-parse`, `git cat-file`, and `git show`]
- `uv run --locked pytest -q`, `ruff check`, and `ruff format --check` — baseline: 52 tests passed, one live test deselected, lint/format green. [VERIFIED: executed command]

### Secondary (MEDIUM confidence)

- [Pydantic Models documentation](https://pydantic.dev/docs/validation/latest/concepts/models/) — v2 model validation, `ConfigDict(extra='forbid')`, nested models, serialization, validators, and `model_construct()` caveat. [CITED: https://pydantic.dev/docs/validation/latest/concepts/models/]

### Tertiary (LOW confidence)

- None. [VERIFIED: research log]

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — existing locked dependencies and the actual Python 3.13.14 environment were verified; official Pydantic behavior was checked. [VERIFIED: `pyproject.toml`, environment probe; CITED: https://pydantic.dev/docs/validation/latest/concepts/models/]
- Architecture: HIGH — Phase 2 locks the semantic boundary and Phase 1 establishes the exact local patterns to extend. [VERIFIED: `02-CONTEXT.md`, existing code/tests]
- Pitfalls: HIGH — required failure classes are explicit in context and the pinned STOA document set demonstrates mixed delivery/limitation/planned status. [VERIFIED: `02-CONTEXT.md`; pinned STOA documents]

**Research date:** 2026-07-30  
**Valid until:** 2026-08-29 for the local/pinned findings; re-check Pydantic documentation before changing the pinned dependency. [VERIFIED: current research snapshot]
