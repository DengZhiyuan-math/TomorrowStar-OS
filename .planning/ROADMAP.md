# Roadmap: Career Evidence Graph

## Milestones

- ⚪ **v1.0 Core Foundation and Deferred Validation** — user-approved partial closeout on 2026-08-28. The implementation foundation is archived; empirical validation was not run.
- 🚧 **v1.1 Full Career Graph and Real JD Validation** — Phases 7–14 build a user-confirmed full-career graph, test it against exactly three real JDs, and make the frozen core-hypothesis decision.

## Archived Milestone

<details>
<summary>v1.0 — Core Foundation and Deferred Validation</summary>

- [x] Phase 1: Validation Charter, Provenance, and Technical Decision Gate — 2/2 plans executed
- [x] Phase 2: Domain Contracts, STOA Fixture, and Deterministic Invariants — 6/6 plans executed; verification is stale and its full-suite regression is acknowledged, not fixed
- [x] Phase 3: Artifact-Aware Grill-Me and Attribution Workflow — 18/18 plans executed
- [x] Phase 4: Contribution–Skill Assessment and Aggregation Calibration — 11/11 plans executed
- [ ] Phase 5: JD Usefulness and Adversarial Evaluation — 2/6 foundation plans executed; no real graph or JD evaluation
- [ ] Phase 6: Replication and Core-Hypothesis Decision — not started

Full original roadmap, requirements, plans, summaries, and review artifacts: `.planning/milestones/v1.0-ROADMAP.md`, `.planning/milestones/v1.0-REQUIREMENTS.md`, and `.planning/milestones/v1.0-phases/`.

</details>

## v1.1 Overview

Milestone v1.1 proceeds through eight requirement-driven delivery boundaries. It establishes private source custody before the blocking inventory review, generalizes Contribution audits before reviewed mastery admission, projects and confirms one canonical graph, accepts exactly three user-supplied real JDs, runs reproducible comparison and automated evaluation, and ends with independent human review and the frozen core-hypothesis decision. Inventory acceptance, graph confirmation, and JD corpus acceptance are explicit user-blocking checkpoints; later evaluation consumes those sealed inputs without mutating career truth.

## Phases

**Phase Numbering:**

- Integer phases (7, 8, 9): Planned milestone work continuing from v1.0
- Decimal phases (7.1, 7.2): Urgent insertions, marked as INSERTED

- [ ] **Phase 7: Career Source Custody and Private Workspace** - The user can declare the career-source boundary while evaluators can trace accepted facts without private-data leakage.
- [ ] **Phase 8: Full-Career Inventory Review and Seal** - The user can reconcile every known career item and seal one complete inventory revision.
- [ ] **Phase 9: Generic Contribution Audit and Attribution** - The user can audit any accepted Contribution through the existing one-question workflow and retain truthful attribution.
- [ ] **Phase 10: Skill Resolution and Reviewed Mastery** - The user can resolve candidate Skills and admit only reviewed user truth into no-inflation mastery.
- [ ] **Phase 11: Canonical Career Graph and User Confirmation** - The user can inspect and confirm one complete, deterministic, status-aware career graph.
- [ ] **Phase 12: Three Real JDs and Immutable Corpus** - The user can review and seal exactly three source-bound real JD packets as the evaluation corpus.
- [ ] **Phase 13: Reproducible Comparison and Automated Evaluation** - Evaluators can compare the confirmed graph with all three JDs and run the frozen automated, stability, holdout, and replication checks.
- [ ] **Phase 14: Independent Review and Core-Hypothesis Decision** - Independent reviewers can judge usefulness against the baseline and produce the single frozen expansion decision.

## Phase Details

### Phase 7: Career Source Custody and Private Workspace

**Goal**: The user can declare the career-source boundary while accepted facts remain traceable and raw career material remains contained in one private workspace.
**Depends on**: Archived v1.0 partial-closeout foundation
**Requirements**: INV-01, INV-06, INV-07
**Success Criteria** (what must be TRUE):

  1. The user can declare the source universe, unavailable sources, and cutoff that define one full-career inventory revision.
  2. An evaluator can trace every accepted inventory fact and Evidence item to its source identity, content hash, capture metadata, and versioned transformations.
  3. The operator can process raw career sources in the ignored private workspace while routine output, logs, errors, and committed artifacts expose only safe identifiers, counts, hashes, and redacted diagnostics.

**Plans:** Historical execution is preserved: 07-00 through 07-08 and 07-10 have Summaries; 07-09 is superseded after its committed Task 1; 07-11 is superseded before execution; 07-12 executes the MVP simplification. Phase 7, its requirements, and the milestone remain incomplete pending independent verification.

Plans:
**Wave 0**

- [x] 07-00-PLAN.md — Create the synthetic Nyquist Wave 0 test and fixture surface.

**Wave 1** *(blocked on Wave 0 completion)*

- [x] 07-01-PLAN.md — Prove the end-to-end private-workspace custody tracer and security boundary.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 07-02-PLAN.md — Complete declaration, recapture, transformation-lineage, and deduplication contracts.

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 07-03-PLAN.md — Finish the safe operator surface, adversarial leak boundary, and private-workspace handoff.

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 07-04-PLAN.md — Make one explicit full Git commit OID authenticate the complete custody snapshot.

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 07-05-PLAN.md — Bind exact-source transformations and retained outputs to immutable declaration revisions.

**Wave 6** *(blocked on Wave 5 completion)*

- [x] 07-06-PLAN.md — Authenticate retained outputs and stage every legacy chain in one exhaustive workspace migration.

**Wave 7** *(blocked on Wave 6 completion)*

- [x] 07-07-PLAN.md — Finalize and retain the migration through dedicated-ref CAS while preserving later recapture verification.

**Wave 8** *(blocked on Wave 7 completion)*

- [x] 07-08-PLAN.md — Close symlink, bidi-control, and commit-aware raw-cleanup boundary failures.

**Wave 9** *(blocked on Wave 8 completion)*

- [~] 07-09-PLAN.md — Superseded after recording the committed Task 1 repair and validation audit; it never ran its security checkpoint or current-HEAD evidence task.

- [x] 07-10-PLAN.md — Record current-HEAD synthetic gate evidence without promoting Phase 7 or its requirements.

**Historical supersession**

- [~] 07-11-PLAN.md — Superseded before execution; its cleanup-race, commit-anchor, and temporal-custody direction is replaced by the single-user MVP addendum.

**Wave 10 — MVP simplification** *(blocked on the completed 07-10 history)*

- [x] 07-12-PLAN.md — Replace Phase 7 custody overbuild with an explicit-workspace, append-only raw vault and minimal source index; retain only local safety and synthetic boundary tests.

### Phase 8: Full-Career Inventory Review and Seal

**Goal**: The user can reconcile every known career item and immutably accept one complete inventory revision at the declared cutoff.
**Depends on**: Phase 7
**Requirements**: INV-02, INV-03, INV-04, INV-05
**Success Criteria** (what must be TRUE):

  1. The user can inspect every known employment, project, research, publication, education, teaching, open-source, internship, and related Experience in one inventory without any résumé or repository list being treated as complete by itself.
  2. The user can confirm, edit, add, split, merge, exclude with reason, or retain every discovered or user-added item as unresolved without silent omission.
  3. The user can inspect category, declared-source, candidate, unresolved-item, and unavailable-source coverage before the inventory is called complete.
  4. The user can seal an exact inventory revision only after every candidate has a recorded disposition; later corrections create linked immutable revisions rather than rewriting accepted history.

**Plans**: TBD
**Blocking checkpoint**: The user must accept the inventory revision before Phase 9 begins.

### Phase 9: Generic Contribution Audit and Attribution

**Goal**: The user can audit any accepted Contribution through the existing one-question workflow and retain a truthful, resumable record of capability and responsibility.
**Depends on**: Phase 8
**Requirements**: GRF-01, GRF-02, GRF-10
**Success Criteria** (what must be TRUE):

  1. The user can run the artifact-aware, one-question-at-a-time audit for any accepted Contribution ID without STOA-specific production identifiers or paths.
  2. Each audit keeps capability coverage, user/team/other-person/coding-agent/third-party attribution, evidence sufficiency, assistance, skips, contradictions, and unresolved responsibility as distinct reviewable facts.
  3. The user can pause and resume a full-career audit queue, see why every Contribution is pending, and prioritize JD-relevant unresolved items without hiding or deleting other inventory items.

**Plans**: TBD

### Phase 10: Skill Resolution and Reviewed Mastery

**Goal**: The user can resolve candidate Skills and admit only attribution-preserving, reviewed user truth into stable, no-inflation mastery.
**Depends on**: Phase 9
**Requirements**: GRF-03, GRF-05, GRF-06, GRF-07
**Success Criteria** (what must be TRUE):

  1. The user can accept, correct, merge, split, or leave ambiguous each candidate Skill identity while source-local identity and decision lineage remain inspectable.
  2. Only current admitted `reviewed-user-truth` Contribution–Skill assessments can establish or increase mastery; inventory presence, unresolved content, wording, ontology relations, titles, credentials, and repository presence have no mastery effect.
  3. The user can inspect mastery, centrality, confidence, context, duration, recency, responsibility, assistance, assessment basis, and admission status as separate meanings for every score-bearing relationship.
  4. Duplicate sources, Evidence, Contributions, aliases, and incidental uses cannot increase mastery, confidence, duration, or cross-context promotion without observable evidence satisfying the higher capability anchor.

**Plans**: TBD

### Phase 11: Canonical Career Graph and User Confirmation

**Goal**: The user can inspect and confirm one deterministic graph that represents the entire accepted inventory without confusing coverage with mastery authority.
**Depends on**: Phase 10
**Requirements**: GRF-04, GRF-08, GRF-09
**Success Criteria** (what must be TRUE):

  1. The user can inspect one graph snapshot containing every accepted inventory item with reviewed, pending, insufficient-evidence, unresolved-responsibility, confirmed, and excluded-with-reason states where applicable.
  2. The user can confirm a deterministic snapshot bound to exact inventory, audit, assessment, Skill-resolution, policy, exclusion, and coverage versions under one canonical graph hash.
  3. A correction, reassessment, attribution change, or policy change creates linked new lineage, invalidates stale graph snapshots and dependent results, and leaves the prior accepted graph inspectable.

**Plans**: TBD
**Blocking checkpoint**: The user must confirm the canonical graph snapshot before Phase 12 begins.

### Phase 12: Three Real JDs and Immutable Corpus

**Goal**: The user can supply, correct, and immutably accept exactly three real JDs as one source-bound evaluation corpus.
**Depends on**: Phase 11
**Requirements**: JD-01, JD-05, JD-06, JD-07
**Success Criteria** (what must be TRUE):

  1. The user can supply exactly three distinct real JD raw sources whose private bytes, identities, acquisition metadata, and distinct hashes are retained, with proposed requirements reconstructable from source spans and preserving every supplied expectation field.
  2. Prompt-like source text remains inert, absent fields remain absent, and source-bound interpretation proposals have neither acceptance nor mastery authority.
  3. The user can review every proposed requirement and add omissions, edit fields, split, merge, accept, or reject items while the original proposal and ordered correction lineage remain inspectable.
  4. The user can immutably accept one reviewed packet for each distinct raw-source hash and seal exactly those three packets into one corpus; later corrections create new packets and invalidate dependent runs.

**Plans**: TBD
**Blocking checkpoint**: The user must accept all three JD packets and seal the corpus before Phase 13 runs.

### Phase 13: Reproducible Comparison and Automated Evaluation

**Goal**: Evaluators can produce truthful, reproducible JD comparisons and automated validation evidence from the sealed graph and corpus without writing back into mastery.
**Depends on**: Phase 12
**Requirements**: JD-08, JD-09, JD-10, EVAL-01, EVAL-02, EVAL-03, EVAL-06
**Success Criteria** (what must be TRUE):

  1. The user can inspect `supported`, `partially supported`, `unsupported`, and `uncertain` judgments for every accepted JD requirement, with cited Contribution–Skill lineage and missing capability, missing evidence, context mismatch, pending review, unresolved responsibility, and other uncertainty reported separately.
  2. Comparing any accepted JD can change only relevance, selected Contributions, gaps, route, and match judgments; the confirmed graph and mastery hashes remain unchanged before and after comparison.
  3. An evaluator can reproduce each comparison from the exact accepted graph, corpus, packet, interpretation, comparison-policy, and configuration hashes without accepting a substitute or moved current pointer.
  4. An evaluator can run the frozen deterministic, known-good, known-bad, adversarial, counterfactual, and three-attempt stability cases; supported mastery bands and JD judgments remain stable, while material variance and failures remain visible.
  5. An evaluator can inspect sealed-holdout, leave-one-Contribution-out, leave-one-JD-out, and feasible non-STOA or cross-Experience replication results together with the exact limits of generalizing from one user and three JDs.

**Plans**: TBD

### Phase 14: Independent Review and Core-Hypothesis Decision

**Goal**: Independent reviewers can determine whether the graph is truthful and more decision-useful than the frozen baseline, then make the one permitted expansion decision with explicit limitations.
**Depends on**: Phase 13
**Requirements**: EVAL-04, EVAL-05, DEC-01, DEC-02
**Success Criteria** (what must be TRUE):

  1. Independent human reviewers can judge inventory completeness, attribution, Skill specificity, mastery-anchor fit, centrality, confidence, aggregation validity, JD interpretation, and usefulness while disagreement and adjudication remain retained.
  2. A blinded reviewer can compare graph-based results with the preregistered flat-résumé or exact-keyword baseline under frozen relevance, truthfulness, decision-usefulness, and traceability criteria, with zero critical fabricated capability claims required for acceptance.
  3. An evaluator can apply the frozen rules to produce exactly one reproducible `supported`, `partially supported`, or `rejected for expansion` decision that identifies every blocking failure, deviation, unstable result, and unresolved limitation.
  4. If and only if expansion is justified, the user receives a scoped next-milestone recommendation and provenance contract for dynamic JD-tailored résumé selection and rewriting; graph polish and development-evaluation results are not presented as employment-effectiveness evidence.

**Plans**: TBD
**Blocking checkpoint**: Independent human judgments and adjudication must be complete before the final decision is sealed.

## Progress

**Execution Order:**
Phases execute in numeric order: 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 7. Career Source Custody and Private Workspace | v1.1 | 11/11 | In Progress |  |
| 8. Full-Career Inventory Review and Seal | v1.1 | 0/TBD | Not started | - |
| 9. Generic Contribution Audit and Attribution | v1.1 | 0/TBD | Not started | - |
| 10. Skill Resolution and Reviewed Mastery | v1.1 | 0/TBD | Not started | - |
| 11. Canonical Career Graph and User Confirmation | v1.1 | 0/TBD | Not started | - |
| 12. Three Real JDs and Immutable Corpus | v1.1 | 0/TBD | Not started | - |
| 13. Reproducible Comparison and Automated Evaluation | v1.1 | 0/TBD | Not started | - |
| 14. Independent Review and Core-Hypothesis Decision | v1.1 | 0/TBD | Not started | - |
