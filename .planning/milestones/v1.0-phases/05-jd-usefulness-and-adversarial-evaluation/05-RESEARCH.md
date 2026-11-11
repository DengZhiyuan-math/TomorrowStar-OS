# Phase 5: JD Usefulness and Adversarial Evaluation - Research

**Researched:** 2026-08-28
**Domain:** Private local JD comparison, truth-preserving routing, adversarial evaluation, and one-time human acceptance
**Confidence:** HIGH for repository reuse and custody architecture; MEDIUM for external security guidance; LOW for numeric routing thresholds until the user-provided fixtures exist

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

## Implementation Decisions

### Single-JD scoring and application routing

- **D-01:** Normal personal use processes one JD at a time, supplied as pasted text or a local
  file, against the user's complete Skill graph. Batch JD comparison is not a Phase 5 user flow.
- **D-02:** Every accepted analysis produces one JD-specific 0-100 match score and one explicit
  route: `customized-resume`, `standard-resume`, or `abandon`. JD match remains separate from
  Skill mastery and cannot mutate any underlying assessment or user-Skill value.
- **D-03:** A missing core hard requirement caps the highest attainable match tier. Numerous
  preferred, incidental, or unrelated strengths cannot fully compensate for that missing core
  requirement.
- **D-04:** The three routing bands use a transparent, configurable, versioned policy. Initial
  thresholds are calibrated against the fixed Phase 5 JD fixtures; every result retains the
  exact policy version, and later threshold changes apply only through a new analysis.
- **D-05:** An evidence-based customization exception requires a rare or distinctive core JD
  requirement to map directly to high-confidence Contribution evidence for the corresponding
  Skill combination. The result must expose that evidence and label the trigger
  `evidence-strong-match`.

### Priority-company routing

- **D-06:** Maintain one private local list of priority companies. Do not add a separate
  persistent role-level priority list.
- **D-07:** Every JD from a priority company enters the customized-resume route regardless of
  its ordinary match tier. The system must still show the honest score, core requirement gaps,
  limitations, and risks; preference changes routing, not capability truth.
- **D-08:** Reports distinguish `evidence-strong-match` from `user-priority-company`. A personal
  preference must never be presented as proof of a strong capability match.
- **D-09:** Priority-company lists are versioned forward-only inputs. Editing the list affects
  future analyses only. Historical reports retain their original score, route, company-list
  version, and reason; explicitly rerunning an old JD creates a new result rather than
  overwriting the old one.

### Match report and Contribution selection

- **D-10:** The report opens with the match score, application route, and concise key reasons,
  followed by the strongest match, the most important core gap, and the reason customization
  was or was not selected.
- **D-11:** Show decision-critical JD requirements by default and allow the full structured
  requirement list to be expanded. Every requirement still retains one of `supported`,
  `partially-supported`, `unsupported`, or `uncertain` in the complete result.
- **D-12:** Positive and partial judgments show a human-readable evidence summary naming the
  relevant Experience, Contribution, established capability, and material limitation. Internal
  identifiers, anchor details, confidence, policy versions, and full lineage remain available
  in expanded technical details rather than dominating the default view.
- **D-13:** The report recommends the Contributions most relevant to a customized resume and
  explains why each was selected. Phase 5 selects truthful source material only; it does not
  draft, rewrite, format, or export resume wording.
- **D-14:** Missing capability, missing evidence, context mismatch, and uncertainty remain
  separate explanations. They must not be collapsed into one generic gap label or treated as
  interchangeable reasons for the same score.

### Minimal development-only evaluation

- **D-15:** The fixed evaluation corpus contains three contrasting JDs that exercise
  evidence-strong customization, ordinary standard-resume routing, and low-match abandonment.
  An unchanged-JD priority-company counterfactual proves that preference can change only the
  route and reason, not the score, requirements, evidence, or user Skill graph.
- **D-16:** Independent human comparison is a one-time development acceptance checkpoint. The
  system produces a fixed review packet for an independent reviewer and records disagreement
  and adjudication as evaluation evidence; this is not a recurring multi-reviewer product
  workflow.
- **D-17:** Stale Skill-graph state, missing lineage, hidden text, prompt injection, or another
  trust-boundary failure blocks both scoring and routing. The system reports the concrete
  problem and requires repair or explicit confirmation followed by a new run; it must not emit
  a best-effort score that appears authoritative.
- **D-18:** Deterministic offline fixture runs must be exactly identical. Optional live-model
  evaluation may show small numeric variation, but the application route, core-requirement
  judgments, and cited evidence must remain stable across at least three runs. Material
  variance is retained and blocks acceptance rather than being averaged away.
- **D-19:** Phase completion establishes that the planned personal workflow and its truth
  guards run as designed and that the fixed evaluation can compare decision usefulness against
  the preregistered baseline. It does not establish real-world application, interview, offer,
  or hiring effectiveness; those require later multi-round job-search evidence.
- **D-20:** Research and planning must not search for, select, copy, or synthesize the three
  real test JDs. The user supplies those JDs only when execution reaches an explicit fixture
  checkpoint. Earlier tasks may define strict input contracts, validation commands, empty
  directories, and test harnesses, but the checkpoint blocks real-fixture execution and any
  completion claim until the user-provided JD files are present and accepted.

### the agent's Discretion

- Exact transparent weighting and initial numeric thresholds, provided required versus
  preferred status is preserved, D-03 cannot be bypassed, all inputs are inspectable, and the
  policy is versioned and fixture-calibrated.
- Exact strict model, file, CLI command, report-envelope, and local workspace names, provided
  the existing Pydantic, immutable-history, source-lineage, and offline-first patterns are
  reused rather than duplicated.
- Exact priority-company name normalization and alias handling, provided ambiguous company
  identity fails closed or requires confirmation and historical input versions remain stable.
- Exact preregistered flat-resume or keyword-baseline packet format, anonymization mechanics,
  and independent-review record layout, provided `EVAL-04` and `EVAL-05` remain development
  acceptance evidence rather than personal product workflow.
- Exact selection count and ordering of recommended Contributions, provided every selection is
  evidence-bearing and the complete structured comparison remains inspectable.

### Deferred Ideas (OUT OF SCOPE)

- Actual customized-resume drafting, claim rewriting, review, formatting, and export remain a
  downstream product phase. Phase 5 supplies the route and selected truthful Contributions.
- Measuring whether standard or customized resumes improve applications, interviews, offers,
  or hiring outcomes requires later multi-round real usage; it is not a Phase 5 claim.
- Multi-user accounts, recurring reviewer assignment, reviewer dashboards, and a complex web
  interface are outside this private personal system.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| JD-01 | Represent at least three contrasting JDs as structured requirements with source span, Skill, required/preferred status, and stated context fields where present. | Strict accepted-intake contract, source-span reconstruction, and user-fixture checkpoint. [VERIFIED: .planning/REQUIREMENTS.md:47-52] |
| JD-02 | Judge every requirement as `supported`, `partially-supported`, `unsupported`, or `uncertain`, with positive/partial claims citing Contribution-Skill assessments and limitations. | Evidence-bearing judgment records consume existing assessment lineage read-only. The four values are quoted verbatim. [VERIFIED: .planning/REQUIREMENTS.md:49-50] |
| JD-03 | Different JDs may change relevance, selected Contributions, gaps, and match judgments but not underlying mastery. | Canonical pre/post graph hashing and metamorphic JD-isolation tests. [VERIFIED: .planning/REQUIREMENTS.md:51-51] |
| JD-04 | Separate missing capability, missing evidence, context mismatch, and uncertainty; never create capability from JD or résumé wording. | Typed gap reasons plus exact-Skill, ontology-non-propagation, and no-keyword-authority tests. [VERIFIED: .planning/REQUIREMENTS.md:52-52] |
| EVAL-01 | Run the deterministic schema, lineage, interval, duplication, split/merge, ontology, isolation, and golden matrix. | One parameterized offline matrix over the complete intake-to-report loop. [VERIFIED: .planning/REQUIREMENTS.md:54-56] |
| EVAL-02 | Run the enumerated adversarial and counterfactual cases. | Single-fault mutations, security preflight, and fail-closed scoring/routing. [VERIFIED: .planning/REQUIREMENTS.md:57-57] |
| EVAL-03 | Run each critical case at least three times under identical versioned configuration and retain material variance. | Canonical result comparison with an ordered run vector; no averaging. [VERIFIED: .planning/REQUIREMENTS.md:58-58] |
| EVAL-04 | Preserve independent human judgments, disagreement, and adjudication. | One-time, immutable development review packet and separate reviewer records. [VERIFIED: .planning/REQUIREMENTS.md:59-59] |
| EVAL-05 | Blindly compare graph results with a preregistered flat-résumé or keyword baseline under fixed criteria; allow zero critical fabricated capability claims. | Preregistered two-arm packet, concealed arm mapping, fixed rubric, and hard acceptance gate. [VERIFIED: .planning/REQUIREMENTS.md:60-60] |
</phase_requirements>

## Summary

Phase 5 should be a narrow, local comparison layer over existing assessment truth, not a new mastery engine. `CalibratedUserSkillResult` already carries exact-Skill mastery, policy, authority, admitted source, contexts, and duplicate lineage; the aggregation path partitions results by Skill and authority. The JD layer should consume an immutable snapshot of those results, emit requirement judgments and a match/routing result, and prove byte-for-byte that the input graph did not change. [VERIFIED: src/career_evidence_graph/domain/models.py:666-701; src/career_evidence_graph/assessment.py:939-1027]

Raw JD text is untrusted input. Extraction must produce a proposal whose spans reconstruct against the exact source bytes; scoring begins only after strict validation and explicit acceptance. A detected trust failure blocks both score and route. The three actual JDs are deliberately absent from research: implementation may create contracts, empty fixture locations, and harnesses, but policy activation, real-fixture evaluation, and Phase 5 completion remain blocked until the user supplies and accepts all three. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:79-103]

Use two ordered decision stages: first derive evidence-bearing requirement judgments and a transparent score under a candidate versioned policy; then derive the route, allowing only the two explicit customization reasons. Priority-company routing may change route and reason but must leave score, requirements, evidence, and graph identical. Initial numeric weights and thresholds must remain candidate configuration until calibrated against the accepted real fixtures. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:28-56,79-94]

**Primary recommendation:** Build a pure, read-only JD comparison core with a strict accepted-intake boundary, immutable analysis bundles, versioned candidate policy, explicit user-fixture checkpoint, and one parameterized adversarial/acceptance harness; activate nothing and claim no phase completion before the three real JDs and graph snapshot are accepted.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| Pasted/local-file intake and report display | Browser / Client equivalent: local CLI | API / Backend equivalent: domain core | The existing stdlib CLI is the established local entry point; Phase 5 does not add an API or web UI. [VERIFIED: src/career_evidence_graph/cli.py:103-287; .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:9-19] |
| JD source validation and accepted requirement packet | API / Backend equivalent: domain core | Database / Storage equivalent: immutable JSON | Structure, span integrity, and acceptance are domain invariants; storage retains the exact source and hashes. [VERIFIED: src/career_evidence_graph/validation/models.py:12-15; src/career_evidence_graph/validation/store.py:62-115] |
| Requirement-to-Skill comparison and score | API / Backend equivalent: pure comparison service | Database / Storage equivalent: read-only assessment snapshot | Target relevance is derived from existing exact-Skill truth and cannot write to assessment storage. [VERIFIED: src/career_evidence_graph/domain/invariants.py:221-263,359-384; .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:28-42] |
| Route selection and priority override | API / Backend equivalent: policy function | Database / Storage equivalent: forward-only policy inputs | Route is a second-stage decision; priority changes route, not score or evidence. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:44-56,79-82] |
| Historical analyses and reruns | Database / Storage equivalent: local immutable workspace | API / Backend equivalent: verification service | Existing formal-run storage publishes immutable, hash-complete bundles and linked reruns. [VERIFIED: src/career_evidence_graph/validation/models.py:208-256; src/career_evidence_graph/validation/store.py:92-115] |
| Development evaluation and human acceptance | API / Backend equivalent: offline evaluator | Database / Storage equivalent: sealed review packet | Review is a one-time development gate, not a recurring product workflow. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:77-103] |

## Project Constraints (from AGENTS.md)

- Apply the priority order exactly: YAGNI; repository reuse; standard library; platform/framework native capability; installed dependencies; a clear one-liner; only then the smallest custom implementation. Avoid over-design, duplication, unnecessary abstraction, and dependency growth. [VERIFIED: user-provided AGENTS.md instructions]
- Preserve exact-Skill semantics, Contribution-level audit granularity, separate mastery/confidence/duration/context/JD-match meanings, anchor integrity, and responsibility attribution. [VERIFIED: AGENTS.md:13-22]
- Use the packaged Python 3.13 CLI/library, Pydantic, JSON/JSONL, pytest, Ruff, and stdlib before adding anything. Provider SDK selection remains unfrozen. [VERIFIED: AGENTS.md:34-57]
- Do not add a web/API stack, database, graph/vector database, agent framework, generic LLM score authority, ontology-to-mastery propagation, keyword-derived mastery, résumé generator, or gap-planning workflow. [VERIFIED: AGENTS.md:160-173]
- Work remains inside the GSD workflow; this research task was spawned by the Phase 5 planning workflow. [VERIFIED: AGENTS.md:240-252]
- No project-local skill was discovered. [VERIFIED: AGENTS.md:233-238]

## Standard Stack

### Core

| Library / capability | Version | Purpose | Why Standard |
|----------------------|---------|---------|--------------|
| CPython | `3.13.14` | Domain models, pure comparison, CLI, and evaluation harness | Matches the locked project runtime. [VERIFIED: pyproject.toml:6-13; environment probe 2026-08-28] |
| Pydantic | `2.13.4` | Frozen strict JD, policy, result, review, and manifest contracts | The repository's `StrictModel` is `ConfigDict(extra="forbid", frozen=True)`; official docs confirm these settings reject extra fields and prevent instance mutation. [VERIFIED: pyproject.toml:6-13; src/career_evidence_graph/validation/models.py:12-15] [CITED: https://docs.pydantic.dev/latest/api/config/] |
| Python standard library | Python 3.13 | `argparse`, `json`, `pathlib`, `hashlib`, `tempfile`, `unicodedata`, and deterministic comparison | These cover the local single-user workflow without a new dependency; existing storage already uses atomic temporary-file replacement. [VERIFIED: src/career_evidence_graph/validation/store.py:62-90; src/career_evidence_graph/validation/hashing.py:12-27] |
| Existing assessment and invariant modules | Repository source | Read-only user-Skill snapshot, evidence lineage, exact-Skill isolation, and no-inflation behavior | Reuse avoids creating a second mastery or normalization authority. [VERIFIED: src/career_evidence_graph/assessment.py:696-762,939-1027; src/career_evidence_graph/domain/invariants.py:221-384] |

### Supporting

| Library / capability | Version | Purpose | When to Use |
|----------------------|---------|---------|-------------|
| pytest | `9.1.1` | Deterministic matrix, metamorphic, golden, security, and repeatability tests | Use explicit semantic parameter IDs so each adversarial case is separately attributable. pytest provides native parametrization and explicit IDs. [VERIFIED: pyproject.toml:15-28] [CITED: https://docs.pytest.org/en/stable/how-to/parametrize.html] |
| Ruff | `0.16.0` | Existing lint and format gate | Run through the locked environment; do not add a second linter. [VERIFIED: pyproject.toml:15-38; environment probe 2026-08-28] |
| Existing CLI launcher | Repository source | Ensure tests and commands import this checkout's `src` package | `scripts/run_career_evidence.py` inserts the checkout source before invoking the CLI. [VERIFIED: scripts/run_career_evidence.py:1-21] |
| Existing canonical hashing and formal-run custody | Repository source | Content identity, immutable history, corrections, and rerun lineage | Reuse helpers and manifest semantics; do not invent another hash format. [VERIFIED: src/career_evidence_graph/validation/hashing.py:12-27; src/career_evidence_graph/validation/store.py:25-115] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Strict accepted plain-text/local-file intake | PDF/DOCX parser | Deferred; document parsing adds hidden-text and format ambiguity without helping the Phase 5 hypothesis. [VERIFIED: AGENTS.md:46-51; .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:28-29] |
| Pure deterministic score/routing policy | LLM-generated final score | Rejected because it obscures fixture calibration and can convert prompt text into unsupported authority. [VERIFIED: AGENTS.md:168-171; .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:87-94] |
| Local JSON history | SQLite or web service | No concurrency or multi-user requirement exists in this phase. [VERIFIED: AGENTS.md:153-167; .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:9-19] |
| Existing exact-Skill normalizer | Embeddings/vector matching | Embeddings make ambiguous mappings less inspectable and still cannot establish mastery. [VERIFIED: AGENTS.md:164-171; src/career_evidence_graph/domain/invariants.py:266-356] |

**Installation:** None. Phase 5 needs no new external package. [VERIFIED: pyproject.toml:6-18; AGENTS.md:34-57]

## Package Legitimacy Audit

Not applicable: the recommended implementation installs no external package, so the package-legitimacy gate is not triggered. [VERIFIED: Standard Stack recommendation above]

## Architecture Patterns

### System Architecture Diagram

```text
Pasted text / local UTF-8 file
             |
             v
  [Security + source preflight] ---- failure ----> [BLOCK: no score, no route]
             |
             v
  [Raw bytes + canonical source hash]
             |
             v
  [Requirement extraction PROPOSAL]  <---- optional recorded/live proposer boundary
             |
             v
  [Strict schema + span reconstruction + human acceptance]
             |
             +---- not accepted / ambiguous ----> [BLOCK]
             |
             v
     Accepted JD requirement packet
             |
             |                         Assessment / audit / sealed-fixture stores
             |                                      |
             |                                      v
             |                         [Read-only graph + lineage verifier]
             |                                      |
             +----------------------+---------------+
                                    v
                         [Canonical graph-input hash]
                                    |
                                    v
                         [Per-requirement comparison]
                                    |
                                    v
                         [Versioned score policy]
                                    |
                          +---------+----------+
                          | active?            | no
                          v                    v
                    [core cap]              [BLOCK]
                          |
                          v
                    [ordinary route]
                          |
                          v
          [evidence exception / priority-company overlay]
                          |
                          v
                  Immutable analysis bundle
                          |
              +-----------+------------+
              v                        v
       Local readable report     Development evaluator
                                      |
                         repeats / counterfactual / A-B packet
                                      |
                                      v
                          one-time human acceptance gate
```

The diagram separates source proposal, accepted semantic input, existing graph truth, deterministic scoring, and routing. The optional proposer is outside the authority path: its result cannot score until spans and structure are accepted. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:28-42,77-103; src/career_evidence_graph/validation/models.py:12-15]

### Recommended Project Structure

The smallest proposed mapping is below. The exact new names are implementation recommendations, not existing paths. [ASSUMED]

```text
src/career_evidence_graph/
├── domain/models.py       # Extend only with strict JD/policy/result/review records
├── domain/invariants.py   # Add span, graph-isolation, and comparison invariants
├── jd.py                  # One narrow intake/comparison/routing/history module
├── validation/store.py    # Reuse/refactor canonical immutable-bundle primitives
└── cli.py                 # Add one-JD prepare/analyze/inspect and dev-eval commands

tests/
├── test_jd_models.py
├── test_jd_comparison.py
├── test_jd_evaluation.py
└── test_jd_security.py

validation/
└── jd/                    # Policies, empty fixture intake, manifests, and review packets
```

This mapping follows the locked integration points: one narrow module beside `assessment.py`, minimal extensions to models and CLI, and reuse of the validation workspace. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:209-218]

### Component Responsibilities

| Component | Owns | Must Not Own |
|-----------|------|--------------|
| JD source/intake record | Exact source bytes/hash, origin, size/encoding checks, extracted spans, acceptance receipt | Skill mastery, score, route, or silent text normalization. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:28-42,87-103] |
| Requirement proposal boundary | A replaceable proposal of structured requirements from inert JD text | Any authority to accept requirements or score capability. [VERIFIED: src/career_evidence_graph/audit/decision.py:25-53,132-166; .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:87-90] |
| Graph-input verifier | Current assessment versions, admitted IDs, authority, complete source lineage, canonical graph hash | Replay, repair, reassessment, or mutation. [VERIFIED: src/career_evidence_graph/domain/models.py:328-350,620-701; src/career_evidence_graph/assessment.py:480-549] |
| Requirement comparator | Exact-Skill mapping, evidence citations, limitations, status, separate gap explanation | Aggregating a new mastery score or inferring capability from ontology/JD text. [VERIFIED: src/career_evidence_graph/domain/invariants.py:49-133,221-356] |
| Match policy | Required/preferred weights, status values, core cap, score bounds, ordinary route thresholds, version | Company preference, graph writes, or LLM-generated opaque scores. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:28-42,107-109] |
| Route overlay | Evidence-based exception, priority-company version/identity, final route and distinct reason | Recomputing score, requirements, evidence, or mastery. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:39-56,79-82] |
| Analysis store | Create-only result, all input hashes/versions, parent rerun, report, pre/post graph hashes | Overwriting history or reusing formal-evaluation semantics as personal-analysis truth. [VERIFIED: src/career_evidence_graph/validation/store.py:62-125; .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:53-56] |
| Development evaluator | Three attempts, adversarial mutations, counterfactual, baseline preregistration, blinded packet, review/adjudication | Recurring reviewer product or real-world hiring-effect claims. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:77-103,238-246] |

### Pattern 1: Accepted Input, Not Trusted Extraction

**What:** Keep three states conceptually separate: exact raw JD, extraction proposal, and accepted structured requirement packet. Validate every span by reconstructing it against the raw source and bind the accepted packet to the source hash. Pydantic whole-model validators are the standard place for cross-field/span consistency after individual field validation. [CITED: https://docs.pydantic.dev/latest/concepts/validators/]

**When to use:** Every pasted or local-file JD, including the three fixtures. No score or route is legal from an unaccepted proposal. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:28-29,87-103]

**Prescriptive contract:** A requirement carries one or more reconstructable source spans, exact Skill mapping or explicit unresolved mapping, required/preferred status, whether it is a core hard requirement, and optional stated responsibility/strength, context, seniority, duration, and experience expectations. Absence stays absence; the extractor must not fill unstated values. [VERIFIED: .planning/REQUIREMENTS.md:47-52; .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:33-35]

### Pattern 2: Read-Only, Authority-Filtered Graph Snapshot

**What:** Resolve current assessment versions, aggregate all admitted assessments, and admit only normal-use results whose source authority is the exact value `"reviewed-user-truth"`. The other existing value is `"derived-counterfactual"`; it remains calibration/evaluation data rather than personal capability truth. Both values are quoted verbatim from the source model. [VERIFIED: src/career_evidence_graph/domain/models.py:328-350,620-701]

Do not treat `CalibratedUserSkillResult` alone as a complete explanation. Resolve every admitted assessment ID back to `ContributionSkillAssessment` and its Experience/Contribution/Evidence lineage so positive and partial judgments can expose all relevant evidence, centrality, confidence, context, duration, and limitations. [VERIFIED: src/career_evidence_graph/domain/models.py:544-595,666-701]

Before and after comparison, hash both the mastery snapshot and a full graph-input envelope. `mastery_snapshot_bytes` proves mastery-bearing values are unchanged, while the full envelope additionally binds version/lineage custody. [VERIFIED: src/career_evidence_graph/domain/invariants.py:359-384; src/career_evidence_graph/assessment.py:751-762]

### Pattern 3: Judgment First, Score Second

**What:** Derive and retain a judgment for every accepted requirement before calculating any aggregate score. The exact judgment values are `"supported"`, `"partially-supported"`, `"unsupported"`, and `"uncertain"`. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:63-65]

Use these evidence rules:

| Judgment | Required basis |
|----------|----------------|
| `supported` | Exact-Skill admitted user-truth evidence satisfies the stated capability/responsibility in relevant context, with complete lineage and disclosed limitations. [VERIFIED: .planning/REQUIREMENTS.md:49-52; src/career_evidence_graph/domain/invariants.py:49-69] |
| `partially-supported` | Admitted evidence establishes a relevant part, but a material capability, responsibility, context, seniority, duration, or evidence limitation remains. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:66-75] |
| `unsupported` | The accepted mapping is clear but no admitted Contribution-grounded evidence establishes the required capability. [VERIFIED: .planning/REQUIREMENTS.md:50-52; src/career_evidence_graph/domain/invariants.py:72-133] |
| `uncertain` | Skill mapping, attribution, assistance, lineage, evidence confidence, duration, or source meaning is unresolved; uncertainty must not be converted to capability absence or support. [VERIFIED: src/career_evidence_graph/domain/models.py:544-595; .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:73-75] |

Each non-full judgment also retains one or more human-readable explanations corresponding to missing capability, missing evidence, context mismatch, or uncertainty. Keep those concepts separate in storage and report projection; exact internal field names are at the planner's discretion. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:73-75]

### Pattern 4: Transparent Candidate Policy and Non-Compensatory Core Cap

**What:** Store all requirement-status points, required/preferred weights, core-missing cap, score bounds, ordinary route thresholds, and policy version as inspectable data. Calculate the raw weighted score, then apply the core hard-requirement cap, then map to the ordinary route. A missing core requirement must never be offset by volume of preferred or unrelated support. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:30-42,107-109]

Do not choose initial numeric values in Wave 0. Implement policy validation and monotonicity tests with candidate values, then calibrate and activate one version only after the three user-supplied fixtures are accepted. Every stored result retains its exact version; a policy change requires a new run. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:36-38,99-103]

The existing aggregation-policy lifecycle has exact status values `"candidate"` and `"active"`, but JD routing policy must remain a separate authority because it cannot change mastery. Those values are quoted verbatim only as a reusable lifecycle pattern. [VERIFIED: src/career_evidence_graph/domain/models.py:405-413]

### Pattern 5: Route Overlay as a Pure Counterfactual

**What:** Compute the honest score and ordinary route first. Then apply exactly one of two disclosed customization causes where eligible: `"evidence-strong-match"` or `"user-priority-company"`. Both values are quoted verbatim. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:39-52]

The evidence exception requires an accepted rare/distinctive core requirement plus direct, high-confidence, admitted Contribution evidence for the corresponding exact-Skill combination. Reuse assessment admission, authority, attribution, and assistance gates rather than inventing a weaker JD-only confidence gate. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:39-42; src/career_evidence_graph/domain/models.py:544-595]

The priority-company counterfactual receives the same JD source, accepted requirements, graph snapshot, and score policy. Only final route and reason may differ. Ambiguous normalized company identity blocks or requires explicit confirmation; the company-list version is part of the result hash. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:46-56,79-82,113-114]

### Pattern 6: One Custody Primitive, Two Semantic Records

**What:** Keep a normal personal analysis record distinct from a formal evaluation run, but refactor/reuse the same canonical JSON, atomic-create, path-containment, symlink rejection, content manifest, and parent-rerun helpers. Do not duplicate hashing or silently reinterpret `FormalRunManifest`. Its exact semantics are `"formal-run/v1"`, run kind `"formal"`, execution modes `"recorded-response"`/`"live-reexecution"`, replay mode `"exact-recorded-response"`, and required hashes `"fixture"`, `"artifacts"`, `"prompt"`, `"model"`, `"configuration"`, `"policy"`, `"reviewer"`; all values are quoted verbatim. [VERIFIED: src/career_evidence_graph/validation/models.py:208-256; src/career_evidence_graph/validation/store.py:25-115]

Use the normal record for immutable local history and explicit reruns. Use `FormalRunStore` for the three-attempt adversarial/baseline/review evidence. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:53-56,83-94; src/career_evidence_graph/validation/store.py:62-338]

### Pattern 7: Attempt Retention, Not Result Deduplication

**What:** Persist three distinct attempt bundles per critical case even when their semantic result hashes are identical. Existing Phase 4 calibration intentionally deduplicates an identical result, so that exact history behavior must not be reused for EVAL-03 attempt counting. [VERIFIED: src/career_evidence_graph/assessment.py:1410-1467,1489-1507; tests/test_policy_calibration.py:121-137]

Offline acceptance requires identical canonical semantic-result hashes. Optional live acceptance retains all numeric values and requires identical route, core-requirement judgments, and cited evidence IDs; material variation is stored, mapped to the existing blocker `"material_instability"`, and never averaged. The blocker value is quoted verbatim. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:91-94; src/career_evidence_graph/validation/models.py:32-42]

### Pattern 8: Preregistered, Blinded One-Time Acceptance Packet

**What:** Freeze the baseline method, reviewer rubric, arm assignment, input hashes, and acceptance rule before generating results. Produce two opaque arms per accepted JD, keep the A/B mapping outside the reviewer-visible packet, collect independent judgments without showing prior judgments, then retain disagreement and a separate adjudication record. [VERIFIED: .planning/REQUIREMENTS.md:59-60; .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:83-86,115-117]

The fixed rubric must cover relevance, truthfulness, decision usefulness, and traceability, plus attribution, Skill specificity, anchor fit, centrality, evidence confidence, and aggregation validity. Acceptance requires zero critical fabricated capability claims. [VERIFIED: .planning/REQUIREMENTS.md:59-60]

Reuse `CorrectionRecord`'s preservation of original proposal/hash, correction, reviewer, and reason, and adapt `AssessmentReview`'s explicit reviewer/outcome/reason/sequence/acknowledgment pattern. Do not reuse its Phase 4 activation's single-reviewer constraint for the independent reviewer. [VERIFIED: src/career_evidence_graph/validation/models.py:259-267; src/career_evidence_graph/domain/models.py:480-490,598-617]

### Anti-Patterns to Avoid

- **Direct score from raw JD or model prose:** bypasses accepted spans, exact-Skill mapping, evidence lineage, and injection controls. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:87-90]
- **Target-dependent mastery:** any JD field in assessment aggregation or any write to assessment/audit storage violates JD isolation. [VERIFIED: src/career_evidence_graph/domain/invariants.py:221-263,359-384]
- **Compensatory core scoring:** many preferred matches cannot erase a missing core hard requirement. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:33-35]
- **Priority-as-capability:** priority changes route only; it cannot change score, judgments, evidence, or graph. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:46-56,79-82]
- **Result dedup as repeat evidence:** three equal hashes still require three separately retained execution attempts. [VERIFIED: .planning/REQUIREMENTS.md:58-58; src/career_evidence_graph/assessment.py:1410-1467]
- **Adjudication overwrite:** preserve initial reviewer disagreement and write adjudication as a new record. [VERIFIED: .planning/REQUIREMENTS.md:59-59]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JD sourcing | Search, scraper, synthetic substitute, or agent-selected fixtures | Explicit user file checkpoint | Sourcing is forbidden and would invalidate the fixed real-fixture evaluation. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:99-103] |
| Strict schemas | Hand-written permissive dict validation | Existing `StrictModel` + Pydantic validators | Extra fields and mutation already fail closed. [VERIFIED: src/career_evidence_graph/validation/models.py:12-15] [CITED: https://docs.pydantic.dev/latest/api/config/] |
| Content identity | New serializer/hash convention | `canonical_json_bytes` and `sha256_digest` | Existing behavior fixes Unicode, NaN rejection, key ordering, separators, and `sha256:` identity. [VERIFIED: src/career_evidence_graph/validation/hashing.py:12-27] |
| Safe publication | Direct writes or overwrite-in-place | Existing atomic create/replace and immutable-bundle checks | Existing store handles partial writes, path escape, symlinks, manifests, and tamper verification. [VERIFIED: src/career_evidence_graph/validation/store.py:62-338] |
| Skill/mastery model | JD-local Skill entity or second aggregation engine | `ContributionSkillAssessment` + `CalibratedUserSkillResult` | Phase 5 compares existing truth read-only. [VERIFIED: src/career_evidence_graph/domain/models.py:544-701] |
| Skill inference | Keyword count, résumé list, ontology implication, or embedding score | Exact-Skill normalization plus reviewed Contribution evidence | Existing invariants explicitly forbid direct mastery from `"experience"`, `"credential"`, `"title"`, `"repository"`, `"resume-skill-list"`, and `"ontology-relation"`; all values are quoted verbatim. [VERIFIED: src/career_evidence_graph/domain/invariants.py:72-133] |
| Numeric scoring | Opaque model judge or hidden constants | Versioned inspectable policy calibrated on accepted fixtures | Score inputs and core cap must be reviewable and rerunnable. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:33-38,107-109] |
| Repeatability | Averaging three model outputs | Three retained attempts + invariant comparison | Material variance is evidence and blocks acceptance. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:91-94] |
| Review product | Reviewer dashboard/accounts/workflow engine | Fixed local A/B packet and immutable records | Independent review is a one-time development checkpoint. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:83-86,245-246] |

**Key insight:** The hard part is custody and semantic isolation, not formula complexity. The smallest trustworthy design makes every derived decision replayable while refusing to let JD text, preference, or evidence volume become capability truth. [VERIFIED: AGENTS.md:13-22; .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:28-103]

## Common Pitfalls

### Pitfall 1: Calibrating Before the Real Fixture Checkpoint
**What goes wrong:** Numeric thresholds become tuned to synthetic or agent-selected substitutes.  
**Why it happens:** The harness is ready before the user inputs exist.  
**How to avoid:** Keep policy status candidate and fixture directories empty; add a hard execution checkpoint for three user-supplied, accepted files and their source hashes.  
**Warning signs:** A committed JD body, a nonempty fixture corpus before the checkpoint, or an “active” policy with no accepted fixture manifest. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:79-103]

### Pitfall 2: Treating Extraction as Authority
**What goes wrong:** Hidden or injected JD text controls the interpretation and produces an authoritative-looking score.  
**Why it happens:** Proposal, validation, and acceptance are collapsed into one model call.  
**How to avoid:** Retain raw bytes, reconstruct every span, validate strict structure, and require acceptance before comparison.  
**Warning signs:** A score from a raw model response, cited text not found at declared offsets, or silent control-character stripping. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:87-90; src/career_evidence_graph/audit/decision.py:25-53,132-166]

### Pitfall 3: Reading the Wrong Graph Projection
**What goes wrong:** A fixture expectation or derived counterfactual is presented as personal user truth.  
**Why it happens:** CLI output is trusted without authority filtering, or `UserSkillView` is mistaken for the real graph.  
**How to avoid:** Rebuild from current assessment versions, require `"reviewed-user-truth"`, and resolve all admitted assessments. `UserSkillView` uses the exact markers `"fixture-test-expectation"` for source and authority, so it is not the normal-use graph. [VERIFIED: src/career_evidence_graph/domain/models.py:666-712; src/career_evidence_graph/assessment.py:939-1027]

### Pitfall 4: Baseline-Only Explanations
**What goes wrong:** The report names only the strongest assessment and omits material supporting limitations or contexts.  
**Why it happens:** `CalibratedUserSkillResult` retains the baseline source envelope but not full detail for every admitted assessment.  
**How to avoid:** Resolve each admitted assessment ID and render all decision-relevant lineage.  
**Warning signs:** A positive/partial judgment cannot identify the Experience, Contribution, capability, and limitation required by D-12. [VERIFIED: src/career_evidence_graph/domain/models.py:666-701; .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:66-69]

### Pitfall 5: One Hash Used as Full Custody
**What goes wrong:** Mastery bytes are stable while assessment versions or source lineage have gone stale.  
**Why it happens:** `aggregation_snapshot_bytes` covers only Skill ID, mastery, and anchor.  
**How to avoid:** Retain that isolation hash plus a full graph-input manifest of assessment version hashes and source envelopes.  
**Warning signs:** An analysis result has a mastery hash but no accepted graph-version/lineage hash. [VERIFIED: src/career_evidence_graph/assessment.py:751-762; src/career_evidence_graph/domain/models.py:620-701]

### Pitfall 6: Route Override Leaks Back Into Score
**What goes wrong:** A priority company appears better matched or a customization reason is reported as capability evidence.  
**Why it happens:** Ordinary route and overlay are calculated together.  
**How to avoid:** Persist the ordinary result, then apply a pure overlay; assert identical score/requirements/evidence/graph in the unchanged-JD counterfactual.  
**Warning signs:** Any counterfactual diff outside final route and reason. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:46-56,79-82]

### Pitfall 7: Evidence-Volume or Ontology Inflation
**What goes wrong:** Repeated evidence, incidental uses, or related ontology nodes raise support or match.  
**Why it happens:** Counts/relations are used as capability proxies.  
**How to avoid:** Reuse exact-Skill and no-inflation invariants; evidence can trace or clarify but cannot mechanically increase mastery.  
**Warning signs:** Duplicating a Contribution changes the score, or an ontology relation changes a requirement judgment without new admitted assessment evidence. [VERIFIED: tests/test_skill_aggregation.py:118-184; tests/test_domain_invariants.py:271-332]

### Pitfall 8: Three Results Collapse Into One Attempt
**What goes wrong:** An idempotent history entry is claimed as three-run repeatability.  
**Why it happens:** Existing Phase 4 result deduplication is reused unchanged.  
**How to avoid:** Give every attempt a unique immutable run ID while requiring identical input hashes.  
**Warning signs:** `attempt_count` is three but only one manifest exists. [VERIFIED: src/career_evidence_graph/assessment.py:1410-1467; .planning/REQUIREMENTS.md:58-58]

### Pitfall 9: Blind Packet Is Not Actually Blind
**What goes wrong:** Labels, ordering, identifiers, explanation style, filenames, or metadata reveal which arm used the graph.  
**Why it happens:** Only visible headings are anonymized.  
**How to avoid:** Freeze opaque arm IDs and mapping before generation; normalize presentation; keep mapping out of reviewer-visible files; test the packet for method-identifying fields.  
**Warning signs:** Arm names contain “graph,” “resume,” “keyword,” policy IDs, or distinct filenames. [VERIFIED: .planning/REQUIREMENTS.md:60-60; .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:115-117]

### Pitfall 10: Structural Passing Becomes an Outcome Claim
**What goes wrong:** Passing fixtures is reported as proof of improved applications, interviews, offers, or hiring.  
**Why it happens:** Technical and product-effect evidence are conflated.  
**How to avoid:** Keep the conclusion limited to workflow, truth guards, adversarial resistance, and fixed baseline comparison.  
**Warning signs:** Any completion text asserting real-world employment effectiveness. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:95-103,241-244]

## Code Examples

Verified patterns from current repository and official documentation:

### Frozen, extra-forbidding contracts

```python
# Source: src/career_evidence_graph/validation/models.py:12-15
class StrictModel(BaseModel):
    """Base model that rejects silent schema drift."""

    model_config = ConfigDict(extra="forbid", frozen=True)
```

All Phase 5 domain records should inherit this existing base. Cross-field source-span reconstruction belongs in an after-model validator, which runs after the whole model is validated and returns the validated instance. [VERIFIED: src/career_evidence_graph/validation/models.py:12-15] [CITED: https://docs.pydantic.dev/latest/concepts/validators/]

### Canonical graph-isolation guard

```python
# Sources: src/career_evidence_graph/validation/hashing.py:12-27;
#          src/career_evidence_graph/domain/invariants.py:359-384
before_mastery = mastery_snapshot_bytes(assessments, user_skill_results)
before_graph = sha256_digest(canonical_json_bytes(graph_input_envelope))

result = compare_accepted_jd(accepted_jd, graph_input_envelope, active_policy)

after_mastery = mastery_snapshot_bytes(assessments, user_skill_results)
after_graph = sha256_digest(canonical_json_bytes(graph_input_envelope))
assert after_mastery == before_mastery
assert after_graph == before_graph
```

The example is a recommended use of existing canonical helpers; the comparison function and envelope names are prospective. [VERIFIED: src/career_evidence_graph/validation/hashing.py:12-27; src/career_evidence_graph/domain/invariants.py:359-384]

### Priority-company metamorphic test

```python
# Source values quoted from 05-CONTEXT.md:28-32, 46-56, 79-82
ordinary = analyze(accepted_jd, graph_snapshot, priority_company=False)
priority = analyze(accepted_jd, graph_snapshot, priority_company=True)

assert priority.score == ordinary.score
assert priority.requirements == ordinary.requirements
assert priority.evidence == ordinary.evidence
assert priority.graph_hash == ordinary.graph_hash
assert priority.route == "customized-resume"
assert priority.route_reason == "user-priority-company"
```

The exact route `"customized-resume"` and reason `"user-priority-company"` are quoted verbatim from locked context. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:28-32,46-56,79-82]

### Explicitly identified adversarial cases

```python
# Source: pytest native parametrization documentation
@pytest.mark.parametrize(
    "case",
    [
        pytest.param(borrowed_responsibility_case(), id="borrowed-responsibility"),
        pytest.param(codex_assistance_case(), id="codex-assistance"),
        pytest.param(prompt_injection_case(), id="prompt-injection"),
    ],
)
def test_adversarial_case_blocks_or_preserves_truth(case):
    assert_case_contract(case)
```

The case builders are proposed Wave 0 helpers; native `pytest.param(..., id=...)` is documented by pytest and avoids anonymous failure labels. [CITED: https://docs.pytest.org/en/stable/how-to/parametrize.html]

## State of the Art

| Old / unsafe approach | Current Phase 5 approach | When established | Impact |
|-----------------------|--------------------------|------------------|--------|
| JD keywords produce a match percentage | Accepted requirements map to exact Skills and admitted Contribution evidence | Locked by JD-01 through JD-04 | Wording cannot create capability. [VERIFIED: .planning/REQUIREMENTS.md:47-52] |
| One opaque composite score | Separate requirement judgments, match score, mastery, evidence confidence, duration, context, and route | Project and Phase 5 constraints | Each number/decision retains one meaning. [VERIFIED: AGENTS.md:13-21; .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:28-75] |
| Preference changes perceived fit | Priority is a route-only counterfactual | Phase 5 D-06 through D-09 | Personal preference remains visibly distinct from capability evidence. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:44-56] |
| Repeated outputs averaged or deduplicated | Three retained attempts with invariant comparison and blocking variance | Phase 5 D-18 / EVAL-03 | Instability remains visible evidence. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:91-94; .planning/REQUIREMENTS.md:58-58] |
| Reviewer consensus overwrites disagreement | Independent records plus separate adjudication | Phase 5 D-16 / EVAL-04 | Evaluation preserves the evidence needed to audit human judgment. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:83-86; .planning/REQUIREMENTS.md:59-59] |

**Deprecated/outdated for this phase:** `ProductEffectLabels` has exact values `"supported"`, `"partially-supported"`, and `"rejected"`; it is a charter-level product-effect contract and must not substitute for the four Phase 5 requirement judgments. All values are quoted verbatim. [VERIFIED: src/career_evidence_graph/validation/models.py:54-57; .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:63-65]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The proposed exact new filenames and `validation/jd/` layout are suitable; they do not exist yet and remain planner discretion. [ASSUMED] | Recommended Project Structure | Low: planner may choose equally narrow names while preserving responsibilities. |

No numeric routing threshold, weight, company alias, baseline outcome, JD content, or real-fixture result was assumed during research. Planning later selected a configurable `max_raw_jd_bytes=262144` safety default with inclusive-boundary tests; that implementation decision does not supply or characterize any JD.

## Open Questions (RESOLVED)

1. **Where are the three accepted real JD files?**
   - What we know: They must be contrasting, user-supplied, unchanged after acceptance, and must exercise evidence-strong customization, ordinary standard routing, and abandonment. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:79-103]
   - Resolution: Plan 05-03 Task 1 is the blocking `checkpoint:user-action`. The user supplies exactly three local JD files and the assessment-workspace path; the executor may not browse for substitutes. Plan 05-03 Task 2 records explicit hash-bound acceptance, and Plans 05-04/05-05 depend on that checkpoint.

2. **Which current graph snapshot is authoritative for normal personal comparison?**
   - What we know: Normal comparison must consume admitted `"reviewed-user-truth"` results and resolve all current assessment versions/lineage; `"derived-counterfactual"` is a separate exact authority value. [VERIFIED: src/career_evidence_graph/domain/models.py:328-350,620-701]
   - Resolution: Plan 05-03 Tasks 1-2 obtain the runtime assessment workspace, reopen current versions and policy ancestry, filter normal authority to complete `reviewed-user-truth`, present the graph-manifest hash, and require user acceptance. `jd inspect --expect accepted-corpus-and-graph` exits 2 if the graph is absent, stale, mixed-authority, or incomplete.

3. **What numeric policy becomes active?**
   - What we know: Required/preferred distinctions, core cap, transparency, versioning, and fixture calibration are locked. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:33-38,107-109]
   - Resolution: Plans 05-01/05-02 implement only the transparent candidate-policy schema and invariant tests. Plan 05-04 Task 1 compares candidate configurations after the accepted fixtures exist, records the exact inputs and decision, and activates one forward-only version; no earlier task claims an active numeric policy.

4. **How is the raw-text extraction proposal produced in normal use?**
   - What we know: Provider choice remains unfrozen; the repository already has a narrow decision-port pattern that treats delimited JSON as data and validates cited IDs. [VERIFIED: AGENTS.md:42-50; src/career_evidence_graph/audit/decision.py:25-53,132-166]
   - Resolution: Plans 05-01/05-02 define one provider-independent seam: `jd prepare` requires exactly one raw source plus one content-bound recorded proposal JSON. Only after the user supplies a JD in Plan 05-03 may the current coding agent author that JSON from the checked-in schema. The CLI validates source hash and spans, calls no model, and cannot bypass the separate user acceptance step.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| CPython | All Phase 5 code | ✓ | `3.13.14` | — [VERIFIED: environment probe 2026-08-28; pyproject.toml:6-13] |
| Pydantic | Strict contracts | ✓ | `2.13.4` | — [VERIFIED: environment probe 2026-08-28; pyproject.toml:6-13] |
| pytest | Validation architecture | ✓ | `9.1.1` | — [VERIFIED: environment probe 2026-08-28; pyproject.toml:15-28] |
| Ruff | Static gates | ✓ | `0.16.0` | — [VERIFIED: environment probe 2026-08-28; pyproject.toml:15-38] |
| uv | Locked command runner | ✓ | installed `0.11.29`; project documentation names `0.12.0` | Existing installed version successfully ran locked offline tests; do not expand Phase 5 to a tool upgrade. [VERIFIED: environment probe 2026-08-28; AGENTS.md:53-57] |
| Current coding agent | Recorded proposal authoring after user source delivery only | ✓ | User-selected runtime/model | The authoritative core accepts content-bound recorded JSON and never calls a provider; proposal and source still require explicit review and acceptance. [VERIFIED: Phase 5 Plans 05-01 through 05-03] |
| Database or external service | None | not required | — | Local immutable JSON workspace. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:9-19] |

**Missing dependencies with no fallback:** None. The blocking inputs are user-provided evidence fixtures, not installable dependencies.

**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest `9.1.1` [VERIFIED: pyproject.toml:15-28] |
| Config file | `pyproject.toml`; default suite excludes the existing `live_model` marker. [VERIFIED: pyproject.toml:20-28] |
| Quick run command | `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_comparison.py -x` [ASSUMED: proposed Wave 0 test file] |
| Full suite command | `uv run --offline --locked python scripts/run_pytest.py -q` [VERIFIED: scripts/run_pytest.py:1-21] |
| Static commands | `uv run --offline --locked ruff check .` and `uv run --offline --locked ruff format --check .` [VERIFIED: pyproject.toml:15-38] |

The current reuse foundation was exercised with immutable-policy replay, no-inflation, and all existing critical-blocker cases: 8 tests passed in 0.73 seconds. [VERIFIED: local focused execution 2026-08-28]

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| JD-01 | Strict requirement schema, exact source-span reconstruction, optional stated fields, split/merge cases | unit + property-style matrix | `... tests/test_jd_models.py -x` | ❌ Wave 0 [ASSUMED] |
| JD-02 | Four judgments; positive/partial evidence and limitation lineage | unit + golden | `... tests/test_jd_comparison.py -x` | ❌ Wave 0 [ASSUMED] |
| JD-03 | Different JD changes derived result while pre/post mastery/full graph hashes remain identical | metamorphic | `... tests/test_jd_comparison.py -x` | ❌ Wave 0 [ASSUMED] |
| JD-04 | Four gap concepts remain separate; JD keywords and ontology relations cannot create support | adversarial + metamorphic | `... tests/test_jd_comparison.py -x` | ❌ Wave 0 [ASSUMED] |
| EVAL-01 | Complete deterministic schema/lineage/interval/duplication/split-merge/ontology/isolation/golden matrix | parameterized integration | `... tests/test_jd_evaluation.py -x` | ❌ Wave 0 [ASSUMED] |
| EVAL-02 | Borrowed work, Codex/team attribution, volume, centrality/confidence, stale state, hidden text, injection | parameterized security/integration | `... tests/test_jd_security.py -x` | ❌ Wave 0 [ASSUMED] |
| EVAL-03 | Three distinct attempts; offline hash equality; live invariant stability; retained variance | integration | `... tests/test_jd_evaluation.py -x` | ❌ Wave 0 [ASSUMED] |
| EVAL-04 | Independent packet, separate judgments, preserved disagreement, adjudication lineage | schema/integration + manual checkpoint | `... tests/test_jd_evaluation.py -x` | ❌ Wave 0 [ASSUMED] |
| EVAL-05 | Preregistered baseline, hidden A/B mapping, fixed rubric, zero fabricated claims | integration + manual blind review | `... tests/test_jd_evaluation.py -x` | ❌ Wave 0 [ASSUMED] |

The ellipsis in per-row commands abbreviates the verified prefix `uv run --offline --locked python scripts/run_pytest.py -q`; plans must write the full command. [VERIFIED: scripts/run_pytest.py:1-21]

### Sampling Rate

- **Per task commit:** Run the relevant proposed JD test file with `-x`, plus any touched existing assessment/store/security test file.
- **Per wave merge:** Run the full offline pytest suite and both Ruff gates.
- **Phase gate:** Full offline suite green; three accepted real JD inputs present; active policy pinned; all critical cases have three retained attempts; independent review/adjudication complete; zero fabricated capability claims; no blocking variance or trust failure.

### Wave 0 Gaps

- [ ] `tests/test_jd_models.py` — strict intake, spans, policy/result/review models. [ASSUMED]
- [ ] `tests/test_jd_comparison.py` — judgment, score, cap, route, evidence, and graph-isolation tests. [ASSUMED]
- [ ] `tests/test_jd_evaluation.py` — golden/adversarial repetitions, priority counterfactual, baseline, packet, and adjudication tests. [ASSUMED]
- [ ] `tests/test_jd_security.py` — hidden text, injection, stale lineage, path, symlink, and no-output-on-block tests. [ASSUMED]
- [ ] Empty user-fixture intake and manifest contract — must contain no sourced/synthetic JD body before the checkpoint.
- [ ] Explicit user-action checkpoint — obtains and accepts the three real JDs and authoritative graph snapshot.
- [ ] No framework install is needed. [VERIFIED: pyproject.toml:6-38]

## Security Domain

Security enforcement is enabled at ASVS Level 1, and Nyquist validation is enabled. [VERIFIED: .planning/config.json:20-50]

### Applicable ASVS Categories

| ASVS 5.0 Category | Applies | Standard Control |
|-------------------|---------|------------------|
| V1 Encoding and Sanitization | yes | Decode once as UTF-8, retain raw bytes/hash, never silently remove hidden controls, and escape report rendering. [CITED: https://github.com/OWASP/ASVS] |
| V2 Validation and Business Logic | yes | Positive expected-structure validation in a trusted domain layer; enforce the accepted-input → graph-verify → score → route sequence. ASVS 5.0 controls V2.2.1, V2.2.2, and V2.3.1 are directly relevant. [CITED: https://github.com/OWASP/ASVS/blob/master/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.flat.json] |
| V5 File Handling | yes | Configurable maximum size, regular local file only, strict resolved-path containment, no symlinks, and declared plain-text content. ASVS 5.0 V5.2/V5.3 controls cover these boundaries. [CITED: https://github.com/OWASP/ASVS/blob/master/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.flat.json] |
| Authentication / Session Management | no | Private local single-user CLI; no account/session feature is in scope. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:9-19] |
| Access Control | limited | No application authorization layer; filesystem containment, symlink rejection, and create-only history remain mandatory. [VERIFIED: src/career_evidence_graph/validation/store.py:62-115] |
| Cryptography | integrity only | Reuse stdlib SHA-256 for content identity; do not claim authentication, encryption, or secrecy. [VERIFIED: src/career_evidence_graph/validation/hashing.py:25-27] |

### Known Threat Patterns for the Local Python/LLM Boundary

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection embedded in JD | Tampering / Elevation of Privilege | Treat JD as inert data, no tools in proposer, strict structured output, span binding, explicit acceptance, and fail closed with no score/route. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:87-90] |
| Zero-width, bidi, NUL, or other hidden control content | Tampering | Retain raw bytes; detect and disclose code points; reject or require explicit confirmation followed by a new run; never normalize silently. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:87-90] |
| Path traversal, symlink, hardlink, or manifest escape | Tampering | Resolve under one workspace root; regular-file checks; reuse existing safe path and immutable publication logic. [VERIFIED: src/career_evidence_graph/validation/store.py:62-115,252-338] |
| Stale graph or detached lineage | Tampering | Reopen current versions/sources, verify complete hashes, require reviewed-user-truth authority, and bind full graph manifest before scoring. [VERIFIED: src/career_evidence_graph/domain/models.py:328-350,620-701] |
| Borrowed/team/Codex work converted into user capability | Spoofing | Preserve attribution/assistance values and require admitted Contribution-level evidence; adversarial single-fault tests. [VERIFIED: src/career_evidence_graph/domain/models.py:544-595; .planning/REQUIREMENTS.md:57-57] |
| Private JD/company data leaked through logs or packets | Information Disclosure | Keep local, store only necessary artifacts, exclude raw private content from routine console errors, and inspect the blinded packet for identifying metadata. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:9-19,46-47,83-86] |
| Trust failure emits partial authoritative output | Tampering | Transactional fail-closed pipeline: publish neither score nor route nor formal result on any blocker. [VERIFIED: .planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md:87-90] |

## Sources

### Primary (HIGH confidence)

- `.planning/phases/05-jd-usefulness-and-adversarial-evaluation/05-CONTEXT.md` — locked boundary, routing semantics, report, evaluation, fixture checkpoint, and deferred scope.
- `.planning/REQUIREMENTS.md` — JD-01 through JD-04 and EVAL-01 through EVAL-05.
- `src/career_evidence_graph/domain/models.py` and `domain/invariants.py` — exact-Skill assessment, authority, lineage, graph projection, and isolation contracts.
- `src/career_evidence_graph/assessment.py` — admitted aggregation, no-inflation, snapshots, policy history, and current-version seams.
- `src/career_evidence_graph/validation/models.py`, `validation/store.py`, and `validation/hashing.py` — strict models, canonical hashes, immutable formal runs, corrections, and reruns.
- `src/career_evidence_graph/cli.py`, `scripts/run_pytest.py`, and `scripts/run_career_evidence.py` — minimal local integration and checkout-safe execution.
- Existing tests in `tests/test_policy_calibration.py`, `tests/test_skill_aggregation.py`, `tests/test_domain_invariants.py`, and `tests/test_security_boundaries.py` — current deterministic, no-inflation, ontology, and blocker patterns.

### Secondary (MEDIUM confidence)

- [Pydantic configuration API](https://docs.pydantic.dev/latest/api/config/) — `extra="forbid"` and frozen model behavior.
- [Pydantic validators](https://docs.pydantic.dev/latest/concepts/validators/) — whole-model validation pattern.
- [pytest parametrization](https://docs.pytest.org/en/stable/how-to/parametrize.html) — explicit parameter IDs and built-in matrix support.
- [OWASP ASVS 5.0 repository](https://github.com/OWASP/ASVS) and [flat controls](https://github.com/OWASP/ASVS/blob/master/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.flat.json) — input, business-flow, file, and fail-secure controls.

### Tertiary (LOW confidence)

- None. Unknown fixture contents and numeric policy choices are left unresolved rather than inferred.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — existing pinned runtime and dependencies are sufficient; focused offline reuse tests passed.
- Architecture: HIGH — Phase 2-4 contracts expose the required read-only graph, lineage, hashing, and custody seams.
- Pitfalls: HIGH for repository-specific isolation/custody failures; MEDIUM for generalized input-security details, which are backed by official ASVS controls.
- Numeric weights and thresholds: LOW until the three user-provided fixtures are accepted and calibration is reviewed.

**Research date:** 2026-08-28  
**Valid until:** 2026-09-27 for external guidance; repository findings remain valid only until relevant source contracts change.  
**Fixture custody:** No JD was searched for, selected, copied, synthesized, or added during research.  
**Completion boundary:** This research is ready for planning, but real-fixture execution and Phase 5 completion remain blocked until the user supplies and accepts the three JD files and authoritative graph snapshot.

## RESEARCH COMPLETE
