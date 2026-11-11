# Architecture Research

**Domain:** Local-first career-evidence graph, human review, and real-JD hypothesis validation
**Milestone:** v1.1 Full Career Graph and Real JD Validation
**Researched:** 2026-08-28
**Confidence:** HIGH for current-code findings and the recommended integration shape; MEDIUM for implementation details that still require phase fixtures

## Executive Recommendation

Extend the existing packaged Python modular monolith. Keep one private filesystem workspace, one canonical graph projection, and the existing explicit state machines. Do not add a database, graph engine, agent framework, UI, or another career ledger.

Make the current STOA fixture path a legacy validation adapter and introduce a generic, reviewed career inventory as the production input. Audits and assessments continue to own their distinct review histories. A deterministic `CareerGraphSnapshot` becomes the only downstream read model: it joins one accepted inventory revision with completed audit hashes, current assessment-version hashes, active policy hashes, and explicit coverage states. It is a sealed projection, not a second editable fact store.

Apply the same rule to JDs. Raw bytes become one interpretation proposal, item-level reviews produce one effective proposal, and explicit acceptance seals that exact hash. Acceptance must not parse again. Exactly three accepted packet hashes are sealed into one immutable corpus manifest. Evaluation consumes the confirmed graph hash, three-JD corpus hash, frozen charter hash, and policy hashes; it never writes backward into inventory, assessments, or mastery.

## Standard Architecture

### System Overview

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Thin CLI / operator workflow                                                │
│ inventory · audit · assessment · graph · jd · evaluation                    │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │ typed commands / explicit hashes
┌──────────────────────────────────▼───────────────────────────────────────────┐
│ Application workflows                                                       │
│                                                                              │
│ Career intake ─► inventory review ─► contribution audit ─► assessment       │
│                                             │                    │           │
│                                             └─────────┬──────────┘           │
│                                                       ▼                      │
│                                             canonical graph projector         │
│                                                                              │
│ JD intake ─► interpretation ─► item review ─► acceptance ─► 3-JD corpus     │
│                                                                              │
│ confirmed graph + sealed corpus + frozen charter ─► evaluation ─► decision  │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │ pure functions over strict models
┌──────────────────────────────────▼───────────────────────────────────────────┐
│ Domain and policy                                                           │
│ Experience · Contribution · Evidence · Skill · Audit · Assessment · JD      │
│ coverage state · mastery anchors · admission · matching · decision criteria │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │ shared canonical serialization primitives
┌──────────────────────────────────▼───────────────────────────────────────────┐
│ One private filesystem workspace: .career-evidence/                         │
│ sources/ · inventories/ · audits/ · assessments/ · graph/ · jds/ · evals/  │
│ create-only bundles + atomic current snapshots/pointers + explicit hashes   │
└──────────────────────────────────────────────────────────────────────────────┘
```

### One Workspace, Multiple Semantic Authorities

“One store” should mean one persistence boundary and one set of write primitives, not one untyped JSON document. `AuditStore`, `AssessmentStore`, and `JDIntakeStore` may remain narrow aggregate repositories under `.career-evidence/`; they are not competing graph stores because they own different facts. All should share one `WorkspacePaths` policy and the existing `atomic_write_canonical_json` / `create_only_canonical_bundle` primitives.

| Authority | Owns | Must not own | Canonical artifact |
|---|---|---|---|
| Source custody | Exact private bytes, content hash, locator, acquisition metadata | Personal responsibility, capability, mastery | Create-only source bundle |
| Inventory | Known Experience, Contribution, Evidence, candidate Skill identities and coverage as of a cutoff | Audit conclusions, mastery, JD relevance | Accepted inventory revision |
| Audit | Capability boundary, ownership, assistance, contradictions, conclusion review | Skill normalization decision, score, user-level mastery | Completed `AuditSnapshot` plus conclusion-lineage hash |
| Skill resolution | Whether wording maps to one existing Skill or creates one specific Skill | Evidence sufficiency or mastery | Hash-bound `SkillResolutionDecision` |
| Assessment | Contribution–Skill judgments, bases, substantive review, admission, immutable versions | Inventory completeness or JD fit | Current `AssessmentVersion` lineage |
| Graph projection | Status-aware join of accepted inventory, reviewed lineages, and user-Skill results | New source facts, free-form edits, JD-specific scores | Immutable `CareerGraphSnapshot`; one current pointer |
| JD | Exact source, span-bound interpretation, item reviews, accepted packet | User mastery or graph mutation | Accepted packet and three-packet corpus manifest |
| Evaluation | Runs, baselines, adversarial/stability results, blind review, final decision | Changes to graph, assessment, or JD truth | Create-only evaluation and decision bundles |

The graph is canonical because every downstream comparison reads one confirmed snapshot hash. It is not a second source of facts: every node, edge, score, and status carries revision hashes from the authority that owns it, and the projector is the only graph writer.

## Component Responsibilities

| Component | Change | Responsibility | Integration rule |
|---|---|---|---|
| `domain/models.py` | Modify | Add generic source, inventory, coverage, graph, JD review/corpus, and evaluation contracts | Add schema versions; do not loosen v1 contracts or rewrite sealed v1 data |
| `domain/fixtures.py` | Narrow to legacy | Preserve sealed STOA verification and mutation suite | Fixture-test authority only; never the production career loader |
| `inventory.py` | New | Source bundle → inventory proposal → item review → accepted inventory | One interpreter proposes; only review/acceptance creates truth |
| `workspace.py` | New, minimal | Resolve the sole private root and namespaces; reuse existing write helpers | No new persistence engine or generic repository framework |
| `audit/models.py` | Modify | Use the shared identifier and bind audits to inventory/graph/source hashes | Preserve one-question, coverage, attribution, and conclusion review |
| `audit/workflow.py` | Modify | Read `ContributionContext` instead of sealed STOA fixture paths | Keep one state machine and one decision port; no full-career fork |
| `audit/store.py` | Paths only | Continue one atomic resumable snapshot per audit ID | Incomplete snapshots never establish mastery |
| `assessment.py` | Modify | Generalize existing proposal/review/admission/aggregation for real user truth | Synthetic and real inputs use the same builder, partitioned by authority |
| `AssessmentStore` | Retain | Keep current sidecars with immutable embedded versions | Projector consumes only latest valid versions; no mastery cache |
| `graph.py` | New | Deterministically project and publish canonical snapshots/current pointer | Sole graph writer; expected-prior-hash check before pointer movement |
| `jd.py` | Modify | Add one interpretation port, item review, accepted loader, corpus seal | `analyze` uses a sealed corpus item, not an arbitrary packet path |
| `JDIntakeStore` | Modify | Keep source/proposal private; create-only accept/corpus operations | Preparing is not accepting; accepting never reparses |
| `evaluation.py` | New | Orchestrate frozen evaluation stages and final decision | Read-only over graph/JD; create-only outputs |
| `cli.py` | Modify | Thin commands and safe status views using IDs/expected hashes | No parser repair or canonical JSON mutation in CLI branches |

## Recommended Project Structure

Do not reorganize the whole package. Add only seams required by v1.1:

```text
src/career_evidence_graph/
├── domain/
│   ├── models.py              # existing contracts + new v1.1 schema versions
│   ├── invariants.py          # existing pure checks, extended
│   └── fixtures.py            # frozen STOA legacy path
├── audit/
│   ├── models.py              # generic IDs and input custody
│   ├── workflow.py            # same single-Contribution state machine
│   └── store.py               # same atomic snapshot repository
├── inventory.py               # source → proposal → review → inventory
├── assessment.py              # existing assessment authority, generalized
├── graph.py                   # sole canonical projector/publisher
├── jd.py                      # one interpret/review/accept/corpus/compare path
├── evaluation.py              # frozen evaluation orchestration and decision
├── workspace.py               # sole root/path policy
├── validation/
│   ├── hashing.py
│   └── store.py               # shared atomic/create-only primitives
└── cli.py

.career-evidence/              # ignored, private, single-user workspace
├── sources/<source_hash>/
├── inventories/<revision_hash>/
├── audits/<audit_id>.json
├── assessments/<assessment_id>.json
├── graph/{snapshots,current.json}
├── jds/{prepared,accepted,corpora}/
└── evaluations/<run_hash>/
```

Keep raw career material, raw JD text, user answers, personal graph snapshots, and evaluations under the ignored private root. Committed `validation/` contains only schemas, content-free fixtures, adversarial cases, redacted manifests, and hashes. Preserve the STOA fixture and exact hashes untouched; generic v1.1 data uses new schema versions.

## Canonical Domain Additions

### Generic source custody

The current `Evidence` contract requires a repository, pinned commit, and tracked path. Full-career material needs Git objects, private files/pastes, and reviewed user statements. Do not weaken provenance with nullable repository fields. Add a tagged `SourceLocator` union (`git-object`, `private-blob`, `user-statement`) in which every variant retains a stable source ID, content hash, and bounded locator. Acquisition adapters return bytes and metadata only; one career interpreter turns admitted source bundles into inventory proposals. No adapter may create canonical Contributions directly.

### Status-aware graph without status inflation

Add `GraphCoverageRecord(entity_kind, entity_id, state, basis_hashes, limitation)` rather than overloading audit or admission status.

| State | Meaning | Mastery effect |
|---|---|---|
| `pending` | Known item, required review incomplete | None |
| `insufficient-evidence` | Review/audit cannot establish the claim or capability | None |
| `unresolved-responsibility` | Ownership or assistance remains unresolved/disputed | None |
| `reviewed` | Relevant item review is complete, but graph-wide cutoff confirmation is not | Only a separately admitted reviewed assessment may contribute |
| `confirmed` | User confirmed inclusion/coverage in this exact snapshot as of its cutoff | Confirmation alone never creates mastery |

Mastery eligibility remains separate: the assessment must be current in its immutable version lineage, `reviewed`, substantively reviewed, `reviewed-user-truth`, and admitted by the active policy.

### Canonical graph snapshot

`CareerGraphSnapshot` should retain the cutoff, accepted inventory revision hash, prior graph hash, active policy hashes, stable entity/relation references, every coverage record, current assessment-version hashes, derived user-Skill results, graph hash, and separate confirmation lineage. It must not copy raw source bytes or full transcripts. Corrections happen in the owning inventory, audit, resolution, or assessment workflow; the projector then emits a new snapshot.

## Authoritative Data Flow

### Full-career inventory

```text
private bytes / pinned Git objects / reviewed statements
    ↓ validate encoding, locator, bounds, hash
create-only SourceBundle
    ↓ one CareerInterpreter or recorded proposal
InventoryProposal (non-authoritative)
    ↓ one decision per Experience / Contribution / Evidence / candidate Skill
ordered InventoryReview lineage
    ↓ all known items have a disposition + recorded cutoff
AcceptedInventoryRevision
```

Completeness is measured against the declared source bundle and cutoff, not an unknowable lifetime universe. Omitted, rejected, unavailable, and unresolved items remain explicit dispositions; deletion is not coverage.

### Audit, resolution, assessment, and graph

```text
AcceptedInventoryRevision
    ↓ project one ContributionContext with exact Evidence hashes
existing AuditWorkflow → completed, whole-confirmed AuditSnapshot
    ↓
single Skill resolver → explicit SkillResolutionDecision
    ↓
Assessment proposal → substantive review → admission → AssessmentVersion
    ↓
CareerGraphProjector ← accepted inventory + all current status/version hashes
    ↓
immutable CareerGraphSnapshot → user confirms exact graph hash/cutoff
    ↓
atomic current pointer movement with expected-prior-hash check
```

Modify `load_reviewed_user_graph` into a snapshot loader/projector. Its current assessment-only projection drops unassessed Contributions and coverage states; v1.1 must retain them while still allowing only admitted reviewed-user-truth assessments into mastery.

### Raw JD to immutable three-JD corpus

```text
raw UTF-8 JD bytes
    ↓ existing code-point, size, ID, and source-hash checks
JDRawSource + JDInterpretationProposal
    ↓ item-level confirm/edit/reject/split/merge decisions
effective proposal with ordered before/after hashes
    ↓ explicit exact-hash acceptance
AcceptedJDPacket
    ↓ select exactly three distinct accepted packet hashes
JDCorpusManifest (create-only, ordered slots, corpus hash)
```

The current `PreparedJDIntake.packet` is already typed as `AcceptedJDPacket`, collapsing proposal and acceptance. Replace it with a strict proposal model; only complete review and explicit confirmation construct the accepted packet. Production `jd analyze` must load a packet from the sealed corpus through `JDIntakeStore`. Arbitrary `--packet` paths remain fixture-test helpers only.

### Evaluation and final decision

```text
confirmed graph hash + three-JD corpus hash + charter/policy/baseline hashes
    ↓
create-only EvaluationRun
    ├── deterministic comparisons
    ├── adversarial and no-backflow checks
    ├── repeated-run stability
    ├── human usefulness review
    ├── opaque blind baseline review
    └── holdout and replication evidence
    ↓
FinalDecisionRecord with criterion verdicts and limitations
```

An unfavorable result remains a valid retained result. A rerun after a correction creates a linked bundle with parent hash and change reason; it never overwrites the prior run or silently changes the charter.

## Review and Hash Transitions

Use one transition grammar across domains:

```text
original proposal hash
  → review[n] {before_hash, after_hash, reviewer, reason}
  → effective hash
  → acceptance/admission {effective_hash + policy/input hashes}
  → immutable output hash
```

Required ancestry:

1. `source_bundle_hash = H(manifest + declared source hashes)`
2. `inventory_revision_hash = H(proposal + review lineage + cutoff + source_bundle_hash)`
3. `audit_snapshot_hash = H(inventory_revision_hash + Contribution context + conclusion lineage)`
4. `assessment_version_hash = H(audit hash + Skill-resolution hash + effective assessment + review + admission policy)`
5. `graph_hash = H(inventory hash + current audit/assessment versions + policy hashes + coverage projection)`
6. `graph_confirmation_hash = H(graph hash + reviewer + cutoff acknowledgment + limitations)`
7. `accepted_jd_hash = H(raw source hash + proposal + item-review lineage)`
8. `jd_corpus_hash = H(three ordered distinct accepted_jd_hash values)`
9. `evaluation_hash = H(graph confirmation + corpus + charter/policy/baseline hashes + outputs)`
10. `decision_hash = H(evaluation hash + criterion verdicts + reviewer decision + limitations)`

Only resumable working snapshots and `current.json` use atomic replacement. Accepted inventories, assessment versions, graph snapshots, accepted JDs, corpora, evaluations, and decisions are append/create-only.

## Explicit STOA Hard-Coding Retirement

| Current coupling | v1.1 replacement | v1.0 treatment |
|---|---|---|
| Literal STOA repository IDs, `_REPOSITORIES`, `_DOCUMENT_PATHS`, exact 4/10 counts | Generic `SourceBundle` with tagged locators | Preserve inside legacy verifier |
| `src-stoa-*`, `exp-stoa`, `contrib-stoa-*`, `claim-stoa-*`, `evid-stoa-*` regexes | Shared `Identifier` contract | Old IDs remain valid; remove prefix requirements from generic schemas |
| STOA candidate/review/sealed schemas as runtime ingress | Generic inventory proposal/review/revision schemas | Never rewrite historical known-good |
| Phase 2 path resolution and checkpoint lookup | Workspace-relative bundle ancestry | Legacy verification only |
| `inspect_contribution(fixture_path, manifest_path, ...)` | `inspect_contribution(ContributionContext)` | Fixture helper may adapt STOA for tests |
| Audit models require `contrib-stoa-*` | Generic ID plus bound input revision hash | Legacy snapshots stay readable |
| Assessment `fixture_hash` / `source_manifest_hash` | v2 source-bundle, inventory, and graph-input hashes | v1 envelopes remain readable |
| Literal rejection of `skill-stoa-reviewed-fixture` | Semantic rejection of fixture markers/non-specific Skills | Preserve old negative case |
| Calibration corpus is the only assessment builder | One generic builder; calibration supplies derived authority | Synthetic data cannot enter user-truth partition |
| `.career-evidence/phase-05` | Stable domain namespaces under the same private root | Explicit migration only if real private v1 data exists |
| Arbitrary CLI fixture/JD packet paths | Workspace-bound production IDs plus explicit legacy test commands | Keep test compatibility separate |

Generalization is complete only when no production schema, workflow, or CLI command requires `stoa`; remaining occurrences are confined to legacy fixtures, validation data, tests, and explanatory names.

## Architectural Patterns to Follow

### 1. Functional Core, Imperative Shell

Keep parsing, normalization, aggregation, graph projection, coverage calculation, comparison, and evaluation as pure functions over validated Pydantic models. Keep filesystem reads, atomic writes, timestamps, and CLI argument handling at the edge. This extends the current workflow/store split and makes every policy replaceable without changing custody.

### 2. Proposal → Review → Acceptance

Every interpretation that can alter career truth must cross an explicit review boundary:

```text
source bytes + interpreter version
        ↓
candidate items (replaceable proposal)
        ↓ item-level human decisions
accepted items (source-bound authority)
        ↓
derived assessments / graph / comparisons
```

Acceptance records must bind the exact proposal hash, source hashes, schema version, and reviewer decisions. Acceptance must validate an existing proposal; it must never invoke the interpreter again. Re-running interpretation creates a new proposal with a new hash and requires a new review.

Apply the pattern separately to inventory items, audit claims, skill resolutions, contribution-skill assessments, and JD requirements. Do not collapse their decisions into one generic approval object: they share custody mechanics but retain different semantics.

### 3. One Deterministic Graph Projector

Introduce one projector that consumes accepted inventory, accepted contribution records, reviewed assessments, and reviewed skill resolutions to create a `CareerGraphSnapshot`. This snapshot is the sole graph read model for inspection, JD comparison, and evaluation.

The projector must:

- retain every in-scope inventory item, including uncovered and unassessed items;
- expose explicit coverage and review states instead of treating absence as failure or capability;
- use accepted stable IDs and relationship records without copying mutable facts into graph-only fields;
- reject dangling or ambiguous identities;
- produce a deterministic content hash from canonical serialized inputs and projector version;
- remain rebuildable from upstream authorities.

No command may edit the graph snapshot directly. A correction is made at the owning upstream authority, then projected into a new immutable snapshot.

### 4. Source-Bound Interpretation Ports

Use one career-source interpretation port for heterogeneous career materials and one JD interpretation port for job descriptions. These are intentionally separate because their output contracts and review questions differ. Within either domain, all file formats and providers must route through the same port and proposal schema; do not create a second parser for “real” inputs beside the fixture path.

The raw source record remains authoritative for provenance. The interpreter produces candidates, not truth. Deterministic adapters for JSON, Markdown, or text should be preferred; a provider-backed implementation is added only where the real source set proves it necessary.

### 5. Immutable Inputs, Versioned Policies

Treat raw source captures, accepted review bundles, graph snapshots, the three-JD corpus, and evaluation runs as create-only artifacts. Treat normalization rules, aggregation formulas, question-selection logic, comparison policy, and evaluation rubrics as versioned replaceable policies. Every derived artifact records the policy version and hashes of authoritative inputs so a changed rule produces a new artifact rather than silently rewriting history.

### 6. Stable Identity Before Cross-Source Deduplication

Assign source-local immutable item IDs before resolving equivalence across sources. Preserve aliases and merge decisions as reviewed resolution records. Do not use display names, paths, or guessed semantic similarity as graph identity. This allows a resume line, repository contribution, interview statement, and audit item to converge on one accepted contribution without losing their individual provenance.

## Anti-Patterns to Avoid

### Parallel Fact Ledgers

**What:** Storing inventory claims, accepted evidence, or skill facts again inside an assessment, graph, JD analysis, or evaluation bundle.

**Why bad:** Corrections would have multiple owners, hashes could remain valid while facts diverge, and “latest file wins” would become accidental policy.

**Instead:** Store stable references plus the exact upstream artifact hashes. Denormalize only immutable display summaries and make them non-authoritative.

### Mutable Universal Graph

**What:** Treating one editable graph JSON object as source, workflow state, assessment store, and analysis result.

**Why bad:** Review state and evidence custody become indistinguishable from derived relationships, and partial updates cannot be independently audited.

**Instead:** Keep semantic authorities separate and project one immutable graph snapshot for reads.

### Re-parsing During Acceptance or Analysis

**What:** Accepting raw documents directly or letting JD analysis re-run extraction.

**Why bad:** The reviewed content is no longer necessarily the analyzed content; model or parser changes can alter results without a new review.

**Instead:** Analysis reads accepted, hash-bound packets only.

### Coverage-as-Capability

**What:** Converting inventory presence, repository activity, keywords, ontology implication, or a reviewed JD match into mastery.

**Why bad:** It violates Contribution-level grounding and lets unverified work inflate user truth.

**Instead:** Coverage indicates workflow completeness; only reviewed Contribution–Skill assessments can affect mastery.

### Evaluation Backflow

**What:** Letting an evaluation score mutate graph, JD, or assessment records, or selecting “passing” evidence after seeing the desired outcome.

**Why bad:** Evaluation stops being independent evidence and becomes another scoring authority.

**Instead:** Evaluation is a read-only consumer that emits a create-only run and final decision record.

### Phase-Number Storage Contracts

**What:** Encoding runtime paths such as `phase-05` as permanent domain locations.

**Why bad:** Milestone progression changes paths and encourages new stores for each phase.

**Instead:** Use stable semantic directories under one private workspace; planning phase numbers belong only in roadmap artifacts.

### Speculative Infrastructure

**What:** Adding a graph database, SQL database, workflow framework, vector store, web API, or UI before a concrete validated requirement.

**Why bad:** It introduces migrations and competing abstractions while the domain contracts are still being validated.

**Instead:** Continue with Pydantic, standard-library orchestration, atomic JSON/JSONL bundles, and explicit CLI commands.

## Dependency-Aware Build Order

1. **Generic identity, source, and workspace foundation**
   - Replace STOA-shaped identifiers and path assumptions with generic source and inventory models.
   - Consolidate atomic/create-only storage helpers behind one `.career-evidence/` workspace root.
   - Preserve the current STOA fixture as a frozen regression adapter.

2. **Full-career inventory and cutoff**
   - Ingest heterogeneous sources into one proposed inventory.
   - Add item-level include/exclude/merge/split review and an accepted coverage cutoff.
   - Do not begin production assessment until the in-scope inventory is sealed.

3. **Generic contribution audit**
   - Generalize audit models and workflow from `contrib-stoa-*` to accepted inventory item IDs.
   - Reuse proposal/review/admission and local snapshot mechanics.
   - Make unanswered, declined, unsupported, and covered states explicit.

4. **Skill resolution and reviewed-user-truth production**
   - Resolve candidate skill identities through a reviewable mapping layer.
   - Produce reviewed Contribution–Skill assessments and user-level aggregations from accepted audits only.
   - Preserve attribution, mastery, confidence, duration, and context as separate meanings.

5. **Canonical graph and user confirmation**
   - Implement the single deterministic graph projector.
   - Surface inventory coverage, audit coverage, assessment state, and unresolved references.
   - Seal a reviewed graph snapshot only after required user-truth checks pass.

6. **Raw-JD interpretation and immutable corpus**
   - Extend the existing JD prepare/accept seams to raw inputs and item-level requirement review.
   - Seal exactly three accepted, source-hashed JD packets into one immutable corpus manifest.
   - Prevent corpus replacement or hidden packet substitution during comparison.

7. **Workspace-bound JD comparisons**
   - Compare each accepted JD packet with one selected canonical graph snapshot.
   - Bind analysis outputs to graph, corpus, packet, and policy hashes.
   - Keep match results distinct from user mastery.

8. **Evaluation orchestration and final decision**
   - Run deterministic structural checks first, then any explicitly selected model-assisted rubric.
   - Emit immutable per-case results, aggregate evaluation, exceptions, and final go/hold decision.
   - Evaluation must not write upstream state.

This order prevents downstream work from stabilizing against STOA-only IDs, partial inventory, mutable review packets, or an unconfirmed graph authority.

## Privacy and Publication Boundary

All real resumes, raw career documents, audit transcripts, evidence files, raw JDs, review packets, graph snapshots, and evaluation runs remain beneath the ignored private workspace. Committed artifacts may contain only synthetic fixtures, schemas, policy versions, redacted examples, tests, and aggregate claims that cannot reconstruct private material.

Store source locators as workspace-relative opaque references rather than absolute user paths. Never copy raw text into logs or planning documents merely for convenience. A publish/export command is unnecessary for v1.1; if later required, it must be an explicit redaction boundary with its own tests.

## Scaling Considerations

| Concern | v1.1 approach | Trigger for reconsideration |
|---------|---------------|-----------------------------|
| Data volume | Load validated JSON artifacts and build in-memory indexes | Measured memory or query latency on a real corpus becomes material |
| Writes | Single-process atomic replacement and create-only bundles | Concurrent writers or transactional multi-record updates become required |
| Graph queries | Deterministic projection plus dictionaries/adjacency maps | Repeated real queries cannot be expressed or performed acceptably in memory |
| Interpretation | Sequential, resumable proposals with recorded provider calls | Throughput becomes a demonstrated bottleneck after correctness is stable |
| Evaluation | Local orchestrator over immutable fixtures/runs | A reproducible distributed evaluation need is demonstrated |

None of these triggers is present in the milestone scope; do not add infrastructure for hypothetical scale.

## Open Design Questions for Phase Fixtures

- Which heterogeneous source kinds are actually present, and which need deterministic adapters versus model-assisted interpretation?
- What item-level review vocabulary is sufficient across inventory, skill resolution, and JD requirements without erasing their semantic differences?
- Which coverage states block graph sealing, and which may remain explicitly unresolved at the evaluation cutoff?
- How should accepted merge/split decisions preserve stable identity when one source item maps to multiple contributions or vice versa?
- Which aggregation and comparison policy versions constitute the final experiment, and what fixture failures force recalibration?
- What exact decision rule turns three bound JD comparison results and evaluation evidence into the milestone go/hold conclusion?

These are phase-level policy questions. They should be decided with real reviewed fixtures, not embedded prematurely in infrastructure.

## Sources

### Verified Project Sources

- `.planning/PROJECT.md`, `.planning/ROADMAP.md`, and `AGENTS.md` — milestone constraints, authority semantics, and YAGNI/reuse requirements. **Confidence: HIGH**
- `src/career_evidence_graph/domain/models.py`, `domain/fixtures.py`, and `domain/invariants.py` — current canonical models, STOA-bound identities, and invariants. **Confidence: HIGH**
- `src/career_evidence_graph/audit/models.py`, `audit/workflow.py`, and `audit/store.py` — current audit proposal/review/admission workflow and local persistence. **Confidence: HIGH**
- `src/career_evidence_graph/assessment.py` — assessment sidecars, aggregation, and current reviewed-user-graph projection. **Confidence: HIGH**
- `src/career_evidence_graph/jd.py` — source-bound JD preparation, acceptance, inspection, and analysis seams. **Confidence: HIGH**
- `src/career_evidence_graph/validation/store.py` — existing atomic replacement and create-only bundle primitives. **Confidence: HIGH**
- `src/career_evidence_graph/cli.py` — current command boundaries and phase-number/private-path coupling. **Confidence: HIGH**

### Corroborating Standards and Documentation

- [Pydantic unions](https://docs.pydantic.dev/latest/concepts/unions/), [strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/), and [validators](https://docs.pydantic.dev/latest/concepts/validators/) — support explicit heterogeneous contracts and strict validation at authority boundaries. **Confidence: MEDIUM**
- [Python 3.13 `os.replace` and `fsync`](https://docs.python.org/3.13/library/os.html) — support the existing standard-library atomic file-store approach. **Confidence: MEDIUM**
- [W3C PROV Overview](https://www.w3.org/TR/prov-overview/) — corroborates representing entities, activities, agents, and derivations without making provenance itself the capability authority. **Confidence: MEDIUM**

*Architecture confidence: HIGH for integration and component boundaries because recommendations follow verified local seams; MEDIUM for policy details intentionally deferred to real-fixture phases.*

*Primary recommendation: evolve the existing validated-file architecture into one private workspace with several narrow semantic authorities and exactly one rebuildable graph projection. Do not introduce a second store, parser, graph authority, database, framework, or UI.*
