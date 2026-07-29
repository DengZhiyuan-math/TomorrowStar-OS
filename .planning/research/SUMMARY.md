# Project Research Summary

**Project:** Career Evidence Graph — Core Hypothesis Validation  
**Domain:** Contribution-grounded conversational capability assessment and JD usefulness validation  
**Researched:** 2026-07-30  
**Confidence:** HIGH on scope, domain invariants, upstream boundaries, and major risks; MEDIUM on implementation pins, calibration policy, and generalizability

## Executive Summary

This project is a validation study for the core of an agentic career system, not a résumé builder and not a graph product for its own sake. It must determine whether an artifact-aware, one-question-at-a-time Grill-Me workflow can audit specific work at the `Contribution` level, produce truthful and separable Contribution–Skill assessments, aggregate those into relatively stable user Skill judgments, and make better decisions against STOA and a small, contrasting JD set than simpler baselines. Experts build this kind of assessment system around explicit constructs, standardized but non-leading probes, immutable evidence and attribution trails, human-confirmed claims, independently reviewable evaluation, and falsifiable gates—not around a single model-generated score.

The recommended implementation shape is a small modular monolith with strict domain contracts, an explicit audit state machine, model-output-as-proposal boundaries, and replaceable policies for normalization, assessment, aggregation, and JD comparison. A packaged Python 3.13/Pydantic/pytest/JSON-JSONL stack is the best researched starting candidate, but it is not yet a project-level commitment: `PROJECT.md` deliberately leaves implementation boundaries and phase-level choices open. Phase 1 should confirm the runtime and package pins against the actual fixture, provider, and test needs. Likewise, local-first storage, deterministic helpers, and complete provenance are valuable validation mechanisms; they support reproducibility but do not define the final product.

The central risk is a persuasive but invalid result: a coherent graph can still reward fluent self-report, team or Codex work, evidence volume, ontology proximity, or JD wording instead of demonstrated capability. Mitigate this by preregistering endpoints, baselines, holdouts, and failure rules; separating mastery, centrality, confidence, duration, context, and JD fit; keeping ontology relations non-evidentiary; testing split/merge, duplication, leakage, attribution, and prompt-injection counterfactuals; and requiring independent human review. Dynamic JD-tailored résumé generation remains a core final-product output, but implementation begins only after this validation supports the graph’s reliability and JD usefulness.

## Key Findings

### Recommended Stack

The research favors the smallest inspectable stack that can run the complete validation loop and replay it offline. The exact versions below are recommendations to confirm during the contracts/fixtures phase, not decisions that override `PROJECT.md`.

**Core technologies:**

- **CPython 3.13 (candidate pin `3.13.14`)**: packaged CLI/importable core — mature common baseline across relevant upstreams, with less compatibility risk than prematurely moving to 3.14.
- **Pydantic v2 (candidate pin `2.13.4`)**: strict, versioned domain and model-boundary contracts — makes invalid state and schema drift observable.
- **Python standard library**: paths, JSON, time, IDs, hashing, CLI, and provider protocols — enough for the validation scale without framework overhead.
- **Schema-versioned JSON/JSONL workspace**: canonical snapshots, append-only turns/events, proposals, fixtures, reviews, and run metadata — inspectable and reproducible for one-user calibration.
- **Project-owned `LLMClient` protocol**: narrow structured-output boundary — provider, model, SDK, and settings remain phase-level choices and cannot leak into the domain model.
- **pytest, Ruff, and uv (candidate current pins)**: offline invariant/golden/replay tests, lint/format checks, and a locked toolchain.

Defer FastAPI, React/Next.js, databases, graph/vector stores, workflow frameworks, authentication, document export, and multi-provider abstractions until concrete requirements justify them. Add a PDF/DOCX parser only if the selected STOA/JD evidence cannot be represented faithfully as text, Markdown, or JSON.

The six pinned upstream repositories are references, not runtime dependencies. Every borrowed seam must be classified as `reuse`, `adapt`, `inspired-by`, or `reject`, tied to an exact source path/commit/license, and protected by a local test expressing this project’s distinct semantics.

### Expected Features

**Must have (validation table stakes):**

- A representative STOA `Experience` decomposed into distinguishable, human-reviewed `Contribution` records, with `Evidence` supporting Contributions.
- Artifact inspection before questioning, followed by one focused question per turn, resumable state, non-repetition, and explicit coverage/stop decisions.
- Neutral probes that establish the strongest supported capability boundary and what remains unestablished; no JD-conditioned or answer-leading grilling.
- Explicit user/team/other-person/Codex-assisted/third-party/unknown attribution, with unresolved ownership unable to support definitive mastery.
- Specific Skills extracted only from audited Contributions; credentials, repositories, keywords, and ontology relations never establish mastery.
- Separate `demonstrated_mastery`, `skill_centrality`, and `evidence_confidence`, plus context, verified duration, and assessment basis on every Contribution–Skill assessment.
- Anchor-aware, replaceable user Skill aggregation that resists duplicate evidence and numerous weak Contributions.
- A small structured JD set—recommended minimum three contrasting roles—and evidence-bearing supported/partial/unsupported/uncertain comparisons that cannot mutate mastery.
- Versioned fixtures, prompts/models/policies, proposals, human corrections, golden/adversarial cases, repeated-run results, and calibration history.
- A blinded comparison against at least a flat résumé/JD keyword baseline, with truthfulness, relevance, traceability, and decision usefulness judged separately.

**Should have (hypothesis differentiators):**

- A strongest-supported-versus-next-unestablished capability result for each audited Contribution.
- Evidence sensitivity tests showing decisive evidence affects confidence/status while irrelevant or duplicate material does not raise mastery.
- Counterexample fixtures for high-centrality/low-mastery, low-centrality/high-mastery, and high-mastery/low-confidence cases.
- Explicit reviewer disagreement and adjudication data rather than a hidden “ground truth” generated by the same model.
- Stable user capability across JDs with target-specific Contribution selection and gap explanations.

**Defer until the validation gate passes:**

- **Dynamic JD-tailored résumé generation** — the first major downstream product phase and a core final-product output, but not an implementation deliverable of this validation project.
- Résumé review/diff, layouts, PDF/DOCX export, cover letters, and interview-preparation presentation.
- Gap Sprints, post-sprint Grill-Me, and longitudinal reassessment.
- Broader career ingestion, large ontology coverage, persistent multi-cycle product workspaces, multi-user SaaS, and complex UI.

### Architecture Approach

Use a local modular monolith with a functional core and an imperative shell. Typed commands coordinate explicit stages; model-assisted stages emit immutable proposals; human confirmation creates canonical revisions and append-only events. Persist enough lineage to replay every result from exact Contribution, Evidence, Q&A, ontology, prompt/model, policy, and reviewer versions. Keep aggregation behind a replaceable policy and keep JD comparison as a read-only projection over stable user Skills.

**Major components:**

1. **Strict domain model** — identities, relationships, score semantics, attribution, duration, versioned envelopes, and invalid-state prevention.
2. **Evidence and Contribution workspace** — artifact hashes/locations, STOA decomposition, Contribution identity, shared-evidence tracking, and ownership confirmation.
3. **Grill-Me audit engine** — explicit resumable state, one-question policy, bounded context, claim extraction, coverage, and confirmation.
4. **Skill normalization adapter** — reviewable aliases from a pinned MIND slice; related/implied skills are question hints only.
5. **Assessment and aggregation policies** — Contribution-level proposals, anchor gates, human review, replaceable user-level aggregation, and calibration traces.
6. **JD usefulness slice** — structured expectations with source spans, stable-skill comparison, relevant Contribution selection, limitations, and gaps.
7. **Evaluation and provenance harness** — deterministic invariants, golden/adversarial/replay cases, baselines, blinded review, drift reports, and upstream adaptation ledger.
8. **Versioned workspace repository** — atomic canonical writes, immutable proposals, append-only events, snapshots, migrations, and content-addressed caches.

**Patterns to enforce:**

- Proposal → confirmation → canonical revision.
- Contribution-bounded context packets for assessment.
- Evidence-bearing derivations with source IDs/spans and limitations.
- Stable capability with target-specific JD projection.
- Deterministic workflow guards around nondeterministic model calls.
- Pinned upstream references with explicit reuse/adapt/inspired-by/reject decisions.

### Critical Pitfalls

1. **Non-falsifiable validation and weak baselines** — preregister constructs, endpoints, holdouts, baselines, thresholds, and stop/revise rules before tuning.
2. **Leading, fluent, or circular assessment** — hide JD rewards during elicitation, use neutral probes and work samples, freeze human-authored gold cases, and blind independent reviewers to system outputs.
3. **Attribution and evidence inflation** — confirm actor/subtask boundaries, track shared evidence, require split/merge and duplicate-evidence invariance, and never equate repository presence with capability.
4. **Semantic collapse and score inflation** — keep mastery, centrality, confidence, duration, context, and JD match separate; require observable higher-anchor evidence; do not freeze the exact formula before calibration.
5. **Ontology propagation and context leakage** — aliases may normalize or retrieve, but only direct Contribution assessments create user mastery; JD swaps, neighboring evidence, and stale caches must not change stable capability.
6. **STOA/JD overfit** — seal development/holdout Contributions and JDs before tuning, include negative controls, and replicate on at least one small non-STOA case or explicitly limit the claim to STOA.
7. **Prompt injection and poisoned lineage** — treat artifacts/JDs as untrusted data, use typed allowlisted extraction, read-only inspection, human-visible sources, cache invalidation, and adversarial fixtures.
8. **Upstream/license drift** — verify gitlinks and licenses, record exact source paths and divergence, retain MIT/Apache notices where required, and copy seams rather than architectures.

## Implications for Roadmap

The roadmap should use six validation phases. These phases deliberately end at the core-hypothesis decision; dynamic résumé generation belongs in the next milestone if that decision is positive.

### Phase 1: Validation Charter, Provenance, and Technical Decision Gate

**Rationale:** Evaluation rules, trust boundaries, sampling, and upstream reuse boundaries must be fixed before prompts, formulas, or cases are tuned. This phase also resolves the stack paper’s recommendation without pretending it is already settled.  
**Delivers:** Preregistered hypothesis/endpoints; development and sealed holdout sets; baselines; success/partial/reject rules; privacy/trust policy; upstream adaptation ledger; verified submodule pins/licenses; chosen minimal runtime/toolchain and provider experiment boundary.  
**Addresses:** Versioned audit/calibration record, reproducible fixtures, explicit upstream classification.  
**Avoids:** Non-falsifiable success, circular evaluation ownership, STOA/JD overfit, prompt-injection ambiguity, and license drift.  
**Validation gate:** A negative outcome is possible under frozen rules; holdouts and baselines are identified; exact stack/provider choices are recorded as implementation decisions rather than product definition.

### Phase 2: Domain Contracts, STOA Fixture, and Deterministic Invariants

**Rationale:** Every later model-assisted stage must adapt to the project’s semantics instead of importing an upstream data model or scoring theory.  
**Delivers:** Strict versioned entities; mastery anchors; attribution and temporal models; file repository; hand-authored STOA Experience/Contribution/Evidence fixture; minimal MIND adapter; golden good/bad cases; split/merge, duplicate, interval-union, no-propagation, and JD-isolation tests.  
**Addresses:** Contribution grounding, separate assessment dimensions, specific Skill identity, provenance, and fixture integrity.  
**Avoids:** Experience-to-Skill shortcuts, wrong granularity, dimension collapse, ontology-derived mastery, duration inflation, and stale lineage.  
**Validation gate:** Invalid states are rejected; every assessment-shaped fixture traces to one Contribution; direct evidence removal eliminates mastery even when ontology relations remain; two humans can apply the draft rubric.

### Phase 3: Artifact-Aware Grill-Me and Attribution Workflow

**Rationale:** The project’s core evidence must be produced before aggregation or JD optimization can influence the interview.  
**Delivers:** Read-only artifact registry; confirmed STOA decomposition; resumable single-question audit state machine; neutral question policy; claim proposals; user edits/rejections; coverage and stopping policy; attribution challenge fixtures; replayable transcripts for contrasting Contributions.  
**Addresses:** Inspect-before-ask, one-question flow, concrete capability probes, responsibility separation, and explicit unresolved/provisional states.  
**Avoids:** Leading questions, self-report fluency bias, interview fatigue, contradiction erasure, borrowed team/Codex work, and artifact injection.  
**Validation gate:** Every selected Contribution has reviewed ownership/evidence; each conclusion states what was and was not established; no scored question is leading, repeated, multi-part, or artifact-answerable.

### Phase 4: Contribution–Skill Assessment and Aggregation Calibration

**Rationale:** Relationship-level semantics must be trustworthy before a user-level number can summarize them. Formula choice is an empirical output of this phase, not an input from project initialization.  
**Delivers:** Confirmed Skill normalization; Contribution–Skill proposals and basis traces; independent human review; at least one replaceable aggregation candidate; anchor gates; confidence/provisional rules; repeated-run and drift reports; calibration decisions and regressions.  
**Addresses:** Separate mastery/centrality/confidence/context/duration; stable user Skill assessments; counterexamples and human calibration.  
**Avoids:** Opaque LLM final scores, arithmetic promotion, centrality/evidence-volume bias, false precision, circular judging, and cache/context leakage.  
**Validation gate:** Perturbation, split/merge, duplicate, overlap, propagation, attribution, and JD-swap tests pass; higher bands require observable anchor satisfaction; reviewer/model disagreement is reported rather than averaged away.

### Phase 5: JD Usefulness and Adversarial Evaluation

**Rationale:** The hypothesis is useful only if the calibrated graph improves decisions for contrasting target roles without corrupting capability truth.  
**Delivers:** Structured small-JD fixtures with source spans; reviewed expectations; evidence-bearing comparison reports; JD-specific relevant Contribution selection; explicit limitations/gaps; blinded comparison against preregistered baselines; prompt-injection, hidden-text, alias, negative-control, and stale-cache suites.  
**Addresses:** Structured JD expectations, stable capability with JD-specific relevance, traceable supported/partial/unsupported decisions, and baseline comparison.  
**Avoids:** Keyword-match-as-success, JD-conditioned mastery, attractive unsupported claims, adversarial artifact manipulation, and evaluation on happy paths only.  
**Validation gate:** JD swaps leave the user graph unchanged; positive matches trace to confirmed assessments; there are zero critical fabricated capabilities; graph-based output wins or materially corrects the baseline under the frozen rubric.

### Phase 6: Replication and Core-Hypothesis Decision

**Rationale:** A polished STOA result is insufficient evidence for expansion. The project must test held-out behavior and state its limits before authorizing downstream product work.  
**Delivers:** Sealed-holdout results; leave-one-Contribution/JD-out analysis; one minimal non-STOA replication where feasible; consolidated human calibration findings; supported/partially-supported/rejected decision; scoped generalization statement; recommendation for the next milestone.  
**Addresses:** Reproducible evaluation, honest uncertainty, and readiness criteria for downstream résumé generation.  
**Avoids:** Single-case overclaiming and using résumé prose or UI polish as retrospective proof.  
**Validation gate:** All required structural, truthfulness, calibration, adversarial, and usefulness gates pass for “supported”; mixed results produce “partially supported”; failures of traceability, stability, attribution, or usefulness block expansion.

### Phase Ordering Rationale

- Freeze the validation contract and provenance before tuning; otherwise success, reuse, and security rules drift toward observed results.
- Encode domain invariants and representative fixtures before building model orchestration; every borrowed upstream pattern must prove it preserves Contribution-level semantics.
- Audit and confirm Contributions before assessment; assess Contribution–Skill relationships before aggregation; aggregate stable Skills before comparing JDs.
- Keep JD information out of the Grill-Me and stable-mastery path to prevent target leakage.
- Treat adversarial testing and human calibration as validation work, not post-launch hardening.
- Authorize dynamic JD-tailored résumé generation only after Phase 6 supports the hypothesis; then build it as a provenance-preserving consumer of the graph, not as a new source of capability truth.

### Research Flags

Phases likely needing deeper research during planning:

- **Phase 1:** Select defensible endpoints, baseline protocols, holdout sampling, privacy handling, reviewer independence, and the exact runtime/provider/tool pins.
- **Phase 3:** Design neutral, skill-family-appropriate probe/work-sample patterns and stopping rules without teaching the answer.
- **Phase 4:** Compare aggregation candidates, confidence admission rules, anchor interpretation, inter-rater statistics, and acceptable run-to-run variance.
- **Phase 5:** Define the small JD sample, flat and human baselines, blinded usefulness rubric, and adversarial corpus before outputs are seen.
- **Phase 6:** Decide the minimum non-STOA replication and the exact scope of any generalization claim.

Phases with established patterns where targeted implementation research can be skipped:

- **Phase 2 repository/contracts mechanics:** strict Pydantic models, atomic JSON/JSONL persistence, hashing, append-only events, fixtures, and offline pytest patterns are well documented. Research is still needed for domain semantics, not the mechanics.
- **Pinned-upstream provenance mechanics:** exact gitlink verification and license ledger practices are defined; execution needs diligence rather than architectural discovery.

## Open Questions and Validation Gates

These decisions must remain visible rather than being smuggled into a stack, schema, or prompt:

- Which exact STOA Contributions and Evidence artifacts span the necessary attribution, mastery, confidence, and centrality cases without becoming full-career modeling?
- What quantitative endpoints, failure thresholds, inter-rater statistic, and repeated-run stability envelope are appropriate for the final fixture count?
- Which baseline set is feasible and fair: keyword, artifacts-only, interview-only, and structured human review?
- Which skill families need different neutral probes or confirmatory work samples?
- What is the smallest useful MIND slice, and when should a normalization remain unresolved?
- Which aggregation candidates should be calibrated, and what evidence admits a high-mastery claim as confirmed rather than provisional?
- Which provider/model/SDK and structured-output transport best meet the chosen phase requirements? This choice is intentionally outside the domain model.
- Is text/Markdown/JSON sufficient for faithful evidence, or do selected fixtures justify adding PDF/DOCX parsing?
- Can one small non-STOA case be included without expanding the project beyond hypothesis validation?
- If the hypothesis is supported, what provenance contract must dynamic résumé selection and rewriting preserve in the next milestone?

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | The minimal architecture and “avoid premature infrastructure” conclusion are strong; exact Python/package versions are time-sensitive recommendations and `PROJECT.md` leaves implementation decisions open. |
| Features | HIGH | Table stakes, exclusions, and acceptance gates derive directly from the project hypothesis and agree across all four research files and pinned upstream analysis. Numeric thresholds remain intentionally uncalibrated. |
| Architecture | HIGH for boundaries; MEDIUM for policies | Component separation, proposal/confirmation flow, and lineage rules are well supported. Aggregation, confidence gates, stop criteria, and JD-fit policy remain empirical decisions. |
| Pitfalls | HIGH for project-specific validity/integrity risks; MEDIUM for external guidance | The major failure modes follow directly from invariants and pinned code. Population fairness, quantitative thresholds, and some security/interview guidance need validation beyond this single-user study. |

**Overall confidence:** HIGH on the recommended validation roadmap and scope boundaries; MEDIUM on the eventual implementation configuration and assessment calibration.

### Gaps to Address

- **Calibration evidence:** No validated scoring formula, confidence gate, threshold, or reviewer agreement target exists yet. Resolve in Phases 1 and 4 using frozen cases.
- **Generalizability:** STOA and one user cannot establish broad hiring validity or fairness. Use sealed holdouts, attempt minimal non-STOA replication, and state limits.
- **Ground truth:** Human review is necessary but not infallible. Pilot the rubric, preserve disagreement, blind reviewers where possible, and report uncertainty.
- **Skill-family work samples:** Appropriate demonstrations differ for product reasoning, software implementation, teaching, deployment, and research. Research these selectively in Phase 3.
- **Legal obligations:** Exact duties depend on what is copied and distributed. Maintain the ledger and obtain legal review if substantial adaptation makes obligations unclear.
- **Final-product bridge:** Résumé generation is intentionally absent from implementation, not from the product vision. Phase 6 must hand off stable evidence-selection and provenance contracts for the next milestone.

## Sources

### Primary (HIGH confidence)

- [PROJECT.md](../PROJECT.md) — product hypothesis, accepted domain relationships and anchors, scope, deferred decisions, and final-product boundary.
- [Open-source reference baseline](../../references/README.md) — pinned commits, licenses, reuse matrix, and integration rule.
- [STACK.md](./STACK.md) — minimal implementation candidate, current package research, upstream file-level reuse decisions, and deferred technology choices.
- [FEATURES.md](./FEATURES.md) — table stakes, differentiators, acceptance gates, anti-features, dependencies, and human-review contract.
- [ARCHITECTURE.md](./ARCHITECTURE.md) — modular-monolith boundaries, contracts, data flow, persistence, build order, and upstream integration map.
- [PITFALLS.md](./PITFALLS.md) — validity, integrity, security, provenance, overfit, and phase-gate risks.
- Pinned upstream snapshots: Tabiya Compass `8470bea7…`, Matt Pocock Skills `2ab95809…`, MIND Tech Ontology `2367527d…`, CV Market Learning Planner `ea507847…`, Hiring Agent `70fd3ea9…`, and Resume Matcher `ad7754c8…`.

### Secondary (MEDIUM confidence)

- Official Python, Pydantic, pytest, uv, Ruff, and Python Packaging documentation cited in [STACK.md](./STACK.md) — current compatibility and tooling guidance.
- NIST AI Risk Management Framework, U.S. OPM structured-interview/self-report guidance, and OWASP LLM Prompt Injection guidance cited in [PITFALLS.md](./PITFALLS.md) — evaluation independence, standardized probes, uncertainty, and adversarial controls.
- Human/LLM evaluation surveys and employment-validity documentation cited in [FEATURES.md](./FEATURES.md) — rubric, calibration, and work-related construct corroboration.
- Evidence & Conclusion Ontology, Microsoft human-in-the-loop guidance, and competence/JD-matching research cited in [ARCHITECTURE.md](./ARCHITECTURE.md) — evidence-bearing assertions, persisted confirmation, and separation of capability from suitability.

---
*Research completed: 2026-07-30*  
*Ready for roadmap: yes*
