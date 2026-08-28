# Roadmap: Career Evidence Graph — Core Hypothesis Validation

## Overview

This milestone delivers six vertical validation capabilities in dependency order: freeze a falsifiable validation contract and provenance boundary, establish Contribution-grounded domain truth, run an artifact-aware Grill-Me audit, calibrate traceable Skill assessment and aggregation, test JD usefulness against baselines and adversarial cases, and make an evidence-backed expansion decision. The graph is an internal representation serving career decisions, not the product goal. Dynamic JD-tailored résumé generation remains a core downstream product capability and is deliberately deferred until this validation establishes that its source assessments are truthful and useful.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions, marked as INSERTED

- [x] **Phase 1: Validation Charter, Provenance, and Technical Decision Gate** - Evaluators can begin a falsifiable, reproducible study with explicit upstream and implementation boundaries. (completed 2026-07-30)
- [x] **Phase 2: Domain Contracts, STOA Fixture, and Deterministic Invariants** - Users and evaluators can represent Contribution-grounded career evidence and reject invalid assessment states. (completed 2026-07-30)
- [x] **Phase 3: Artifact-Aware Grill-Me and Attribution Workflow** - A user can complete and resume a focused Contribution audit with inspectable ownership and conclusions. (verification gaps found 2026-08-26) (completed 2026-08-27)
- [ ] **Phase 4: Contribution–Skill Assessment and Aggregation Calibration** - Reviewers can calibrate traceable Skill judgments and replaceable aggregation policies without score inflation.
- [ ] **Phase 5: JD Usefulness and Adversarial Evaluation** - Users can compare a stable Skill graph with contrasting JDs, and evaluators can test whether the results are truthful and more useful than baselines.
- [ ] **Phase 6: Replication and Core-Hypothesis Decision** - Evaluators can test held-out behavior, state generalization limits, and decide whether downstream product expansion is justified.

## Phase Details

### Phase 1: Validation Charter, Provenance, and Technical Decision Gate

**Goal:** As a validation evaluator, I want to start a falsifiable and reproducible validation study with fixed success rules, trust boundaries, and upstream reuse decisions, so that future results can be evaluated without tuning those rules after seeing them.
**Mode:** mvp
**Depends on:** Nothing (first phase)
**Requirements:** VAL-01, VAL-02, OSS-01
**Success Criteria** (what must be TRUE):

  1. An evaluator can apply a versioned charter that identifies baselines, development and sealed-holdout cases, acceptance and failure rules, and the meanings of supported, partially supported, and rejected outcomes before final results exist.
  2. An evaluator can reproduce a recorded validation run from its versioned fixture, artifacts, prompt, model, configuration, policy, and reviewer inputs without altering the original run.
  3. A maintainer can trace every reused or adapted seam to its pinned repository revision, source path, license, classification, attribution, and local divergence, while confirming that the upstream repositories remain reference inputs rather than wholesale runtime dependencies.

**Plans:** 2/2 plans complete
**Wave 1**

- [x] 01-01-PLAN.md

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md

### Phase 2: Domain Contracts, STOA Fixture, and Deterministic Invariants

**Goal:** As a user or evaluator, I want to record representative career evidence in a strict Contribution-grounded model, so that invalid or unsupported assessment states are rejected.
**Mode:** mvp
**Depends on:** Phase 1
**Requirements:** MOD-01, MOD-02, MOD-03, MOD-04, MOD-05, MOD-06, MOD-07, FIX-01, FIX-02
**Success Criteria** (what must be TRUE):

  1. A user can represent each supported career-history type as an Experience containing distinguishable Contributions and can attach provenance-bearing Evidence to the Contribution it supports.
  2. Attempts to derive mastery directly from an Experience, credential, title, repository, résumé skill list, or ontology relationship are rejected, and responsibility remains distinguishable as user, team, other-person, non-responsibility, Codex-assisted, or third-party work.
  3. A reviewer can inspect a Contribution–Skill assessment with independently valid 0–100 mastery, centrality, and confidence values plus context, duration, and an explicit assessment basis; incomplete or out-of-range records are rejected.
  4. A user can inspect one stable mastery value for a specific Skill while confidence, verified duration, recency, context, and JD match remain separate, and changing aliases or ontology adjacency does not create or increase mastery.
  5. An evaluator can exercise a human-reviewed STOA fixture and known-good and known-bad variants that span the required score, attribution, assistance, context, duration, and evidence-quality cases, with every assessment tracing to a Contribution.

**Plans:** 6/6 plans complete

**Wave 1**

- [x] 02-01-PLAN.md — Prove the Contribution-grounded JSON-to-domain-to-CLI tracer and strict record contracts.

**Wave 2** *(after Wave 1; plans run in parallel)*

- [x] 02-02-PLAN.md — Enforce direct-source, user-Skill separation, and ontology non-propagation invariants.
- [x] 02-03-PLAN.md — Verify the pinned document-only STOA source boundary and produce the unsealed candidate packet.

**Wave 3** *(after 02-03)*

- [x] 02-04-PLAN.md — Conduct the blocking item-by-item human STOA review.

**Wave 4** *(after 02-02 and 02-04)*

- [x] 02-05-PLAN.md — Record corrections and seal the immutable known-good STOA fixture.

**Wave 5** *(after 02-05)*

- [x] 02-06-PLAN.md — Validate single-fault known-bad variants and close the offline phase gate.

### Phase 3: Artifact-Aware Grill-Me and Attribution Workflow

**Goal:** As a career-evidence user, I want to complete and resume an artifact-aware audit of a selected Contribution and review its capability and responsibility conclusion, so that I retain a truthful, inspectable record of what the evidence establishes.
**Mode:** mvp
**Depends on:** Phase 2
**Requirements:** AUD-01, AUD-02, AUD-03, AUD-04, AUD-05
**Success Criteria** (what must be TRUE):

  1. Before questioning begins, the user can inspect a record of the supplied artifacts, what each established, and why every remaining question is necessary.
  2. The user receives no more than one focused, decision-bearing question per turn; pausing and resuming preserves answers, extracted facts, coverage, contradictions, and unresolved questions without introducing repeated, multi-part, leading, or artifact-answerable prompts.
  3. Ambiguous responsibility or assistance is challenged until user-owned, team-owned, other-owned, Codex-assisted, and third-party work is separated or explicitly left unresolved.
  4. For each audited Contribution, the user can edit, confirm, or reject a conclusion that identifies the strongest established capability, the next-higher capability not established, its supporting basis, and every provisional or unresolved point.

**Plans:** 18/18 plans complete

**Wave 0**

- [x] 03-01-PLAN.md — Restore the locked runtime gate and prove the sealed-Contribution audit tracer with bounded artifact inspection.

**Wave 1** *(after 03-01)*

- [x] 03-02-PLAN.md — Enforce focused hard-to-simple questioning, resumable coverage, and separate provider-neutral attribution.

**Wave 2** *(after 03-02)*

- [x] 03-03-PLAN.md — Produce immutable, user-reviewable capability-boundary conclusions and close the offline phase gate.

**Wave 3** *(after 03-03)*

- [x] 03-04-PLAN.md — Repair lifecycle, attribution, reference, basis, and canonical conclusion-review semantics.

**Wave 4** *(after 03-04)*

- [x] 03-05-PLAN.md — Enforce hash-linked custody, one-lock transactions, identity-first replay, CAS, and durable recovery.

**Wave 5** *(after 03-04 and 03-05)*

- [x] 03-06-PLAN.md — Materialize and mark the original 28 plus nine gap behavioral pytest probes.

**Wave 6** *(after 03-06)*

- [x] 03-07-PLAN.md — Prove the offline end-to-end journey and exact pytest collection/full quality gate.

**Wave 7** *(after 03-07)*

- [x] 03-08-PLAN.md — Enforce public storage CAS and migrate existing direct test callers to caller-held transactions.

**Wave 8** *(after 03-08)*

- [x] 03-09-PLAN.md — Enforce review projection CAS, truthful unresolved attribution, scoped warning fixes, and final offline quality evidence.

**Wave 9** *(after 03-09)*

- [x] 03-10-PLAN.md — Close audit-root symbolic-link containment and restore canonical MVP goal metadata.

**Wave 10** *(after 03-10)*

- [x] 03-11-PLAN.md — Make the installed editable CLI resolve the current checkout without embedding a stale package copy.

**Wave 11** *(after 03-11)*

- [x] 03-12-PLAN.md — Anchor every audit lock, read, recovery, transaction, and publication to verified directory descriptors.

**Wave 12** *(after 03-12)*

- [x] 03-13-PLAN.md — Prove fresh installed-CLI containment and close the exact executable Phase 3 quality gate.

> Historical scope note: Plans 03-05 through 03-13 remain checked as executed Git history, but their concurrency, installed-package-authority, exact-test-count, and same-UID adversarial-filesystem claims are superseded for active Phase 3 acceptance by D-17 through D-20. Plans 03-14 through 03-18 are one frozen serial repair round.

**Wave 13** *(after 03-13)*

- [x] 03-14-PLAN.md — Freeze every requirement/decision disposition, Git-custody and retire expanded-scope reports, and remove only byte-proven stale copies.

**Wave 14** *(after 03-14)*

- [x] 03-15-PLAN.md — Restore one strict atomic AuditSnapshot and the minimal one-action source-checkout CLI contract.

**Wave 15** *(after 03-15)*

- [x] 03-16-PLAN.md — Remove event/race/install/count authority and restore ordinary packaging while retaining user-behavior tests.

**Wave 16** *(after 03-16)*

- [x] 03-17-PLAN.md — Repair relevant hard-to-simple questions, real boundary decisions, both skip paths, and mandatory ownership-then-assistance turns.

**Wave 17** *(after 03-17)*

- [x] 03-18-PLAN.md — Complete immutable conclusions, prove all offline user journeys, and hand one unchanged revision to independent gates.

### Phase 4: Contribution–Skill Assessment and Aggregation Calibration

**Goal:** Reviewers can turn confirmed Contribution audits into traceable Skill assessments and calibrate stable user-level mastery without collapsing distinct signals or rewarding evidence volume.
**Mode:** mvp
**Depends on:** Phase 3
**Requirements:** ASS-01, ASS-02, ASS-03, ASS-04, AGG-01, AGG-02, AGG-03, AGG-04
**Success Criteria** (what must be TRUE):

  1. A reviewer receives specific Skill proposals only from audited Contributions and can trace each proposal through its Evidence, answers, attribution, and assessment basis.
  2. Reviewers can independently assign and inspect mastery, centrality, and confidence, including high-centrality/low-mastery, low-centrality/high-mastery, and high-mastery/low-confidence cases.
  3. Every mastery judgment identifies the observable capability anchor it satisfies; unsupported higher-band claims are rejected, while high-mastery/low-confidence claims remain provisional until human confirmation.
  4. A user can inspect one aggregated mastery score per specific Skill, its admitted Contribution assessments, and its policy version; duplicate Evidence, duplicate Contributions, and numerous incidental uses do not mechanically promote the Skill.
  5. Evaluators can compare replaceable aggregation and confidence-admission policies on the fixtures, allowing cross-Contribution promotion only when the combined credible behavior satisfies the higher anchor and preserving variance, reviewer disagreement, calibration decisions, and regressions.

**Plans:** 8/11 plans executed

**Wave 1**

- [x] 04-01-PLAN.md — Prove the confirmed-audit to admitted specific-Skill aggregate tracer and strict local persistence.

**Wave 2** *(after 04-01)*

- [x] 04-02-PLAN.md — Expand specific-Skill proposals, independent judgments, and anchor-first mastery.

**Wave 3** *(after 04-02)*

- [x] 04-03-PLAN.md — Preserve substantive review, confidence admission, immutable corrections, and reassessment history.

**Wave 4** *(after 04-03)*

- [x] 04-04-PLAN.md — Aggregate one no-inflation result per Skill and gate cross-Contribution promotion on the next anchor.

**Wave 5** *(after 04-04)*

- [x] 04-05-PLAN.md — Calibrate same-input policies, retain disagreements/regressions, and activate explicitly.

**Wave 6** *(after 04-05)*

- [x] 04-06-PLAN.md — Close the AGG-04 calibration-custody blockers without changing the active calibration choice.

**Wave 7** *(after 04-06)*

- [x] 04-07-PLAN.md — Make normal assessment execution idempotent and human decisions append-only.

**Wave 8** *(after 04-07)*

- [x] 04-08-PLAN.md — Close the AGG-03 authority-transfer blocker and hand the remediations to fresh verification.

**Wave 9** *(after 04-08)*

- [ ] 04-09-PLAN.md — Bind reassessment to authoritative later-audit custody and reject caller-forged provenance or authority.

**Wave 10** *(after 04-09)*

- [ ] 04-10-PLAN.md — Make reassessment consume only a pre-existing confirmed audit and keep every rejected request zero-write across audit and assessment stores.

**Wave 11** *(after 04-10)*

- [ ] 04-11-PLAN.md — Persist exhaustive whole-proposal mutation coverage with zero-write dual-store assertions.

### Phase 5: JD Usefulness and Adversarial Evaluation

**Goal:** Users can obtain evidence-bearing comparisons against contrasting JDs while evaluators can determine whether the complete validation loop is stable, truthful, and more decision-useful than preregistered baselines.
**Mode:** mvp
**Depends on:** Phase 4
**Requirements:** JD-01, JD-02, JD-03, JD-04, EVAL-01, EVAL-02, EVAL-03, EVAL-04, EVAL-05
**Success Criteria** (what must be TRUE):

  1. An evaluator can represent at least three contrasting JDs as structured requirements with source spans, Skills, required/preferred status, strength or responsibility, context, seniority, duration, and experience expectations where supplied.
  2. A user can inspect supported, partially supported, unsupported, and uncertain judgments for each JD requirement, with positive or partial judgments tracing to Contribution–Skill assessments and missing capability, missing evidence, context mismatch, and uncertainty reported separately.
  3. Changing the target JD changes only relevance, selected Contributions, gaps, and match judgments—not the user's underlying mastery—and JD wording or résumé keywords never create an unsupported capability claim.
  4. An evaluator can run schema, lineage, interval, duplication, split/merge, ontology-non-propagation, JD-isolation, known-good/known-bad, responsibility, assistance, evidence-inflation, dimension-confusion, stale-state, hidden-text, and prompt-injection cases at least three times under one recorded configuration; supported mastery bands remain stable and material variance is reported rather than averaged away.
  5. Independent human reviewers can preserve and adjudicate disagreement across attribution, Skill specificity, anchor fit, centrality, confidence, aggregation, and JD usefulness, then blindly compare graph-based results with the preregistered baseline under fixed criteria with zero critical fabricated capability claims.

**Plans:** TBD

### Phase 6: Replication and Core-Hypothesis Decision

**Goal:** Evaluators can determine how far the validation result generalizes and make an evidence-backed decision about whether to build the downstream résumé product loop.
**Mode:** mvp
**Depends on:** Phase 5
**Requirements:** EVAL-06, DEC-01, DEC-02
**Success Criteria** (what must be TRUE):

  1. An evaluator can inspect sealed-holdout, leave-one-Contribution-out, leave-one-JD-out, and—where feasible—one minimal non-STOA replication result together with explicit limits on any generalization claim.
  2. An evaluator can apply the frozen validation rules to produce exactly one supported, partially supported, or rejected-for-expansion decision and identify every blocking failure behind it.
  3. If expansion is justified, the user receives a scoped next-milestone recommendation and a provenance contract for dynamic JD-tailored résumé selection and rewriting; no résumé implementation or polished demonstration is treated as evidence for this milestone's conclusion.

**Plans:** TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Validation Charter, Provenance, and Technical Decision Gate | 2/2 | Complete    | 2026-07-30 |
| 2. Domain Contracts, STOA Fixture, and Deterministic Invariants | 6/6 | Complete    | 2026-07-30 |
| 3. Artifact-Aware Grill-Me and Attribution Workflow | 18/18 | Complete    | 2026-08-27 |
| 4. Contribution–Skill Assessment and Aggregation Calibration | 5/5 | In Progress|  |
| 5. JD Usefulness and Adversarial Evaluation | 0/TBD | Not started | - |
| 6. Replication and Core-Hypothesis Decision | 0/TBD | Not started | - |
