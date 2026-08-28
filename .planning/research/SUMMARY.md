# Project Research Summary

**Project:** Career Evidence Graph — Core Hypothesis Validation
**Domain:** User-authoritative full-career evidence graph and real-JD hypothesis validation
**Researched:** 2026-08-28
**Confidence:** HIGH on scope, stack retention, authority boundaries, and build order; MEDIUM on real-corpus policy details and evaluation operations

## Executive Summary

Milestone v1.1 is a bounded empirical validation of a career-assessment system, not a résumé generator, graph explorer, or employment-effectiveness study. It must account for all career items known from a declared source universe as of a user-confirmed cutoff, retain reviewed and unresolved items in one status-aware `Experience → Contribution → Skill` graph, and determine whether that graph is useful across exactly three real JDs supplied and selected by the user. Completeness and capability authority are deliberately different: a complete inventory may contain pending, insufficient-evidence, or unresolved-responsibility items, while only admitted, human-reviewed Contribution–Skill assessments may establish or increase mastery.

The recommended implementation is the smallest extension of the existing Python modular monolith. Add no dependency by default. Keep Python 3.13.14, Pydantic 2.13.4, canonical JSON/JSONL, pytest 9.1.1, Ruff 0.16.0, uv, and the existing provider-neutral ports and storage primitives. Use one ignored private workspace with narrow semantic authorities for sources, inventory, audits, assessments, JDs, and evaluations, plus exactly one deterministic, rebuildable canonical graph projection for downstream reads. Every interpretation follows source custody → proposal → item review → immutable acceptance, and every derived artifact binds exact content and policy hashes.

The principal risks are evidential rather than infrastructural: false completeness, pending-to-mastery leakage, alias or responsibility inflation, source/JD tampering or privacy leakage, JD-to-graph backflow, stale experiment inputs, reviewer leakage, and claims beyond the frozen study. Mitigate them with explicit cutoff and user seals, stable identity and merge/split lineage, separate authority states, raw-byte/span custody, create-only accepted artifacts, before/after graph-hash checks, a sealed exactly-three-JD corpus, preregistered blind evaluation, and a read-only evaluator that ends in the frozen `supported` / `partially-supported` / `rejected` decision. The result may justify a later scoped product experiment; it cannot establish résumé, interview, offer, hiring, or employment effectiveness.

## Key Findings

### Recommended Stack

The current stack already supplies every required v1.1 primitive. The milestone should add project-owned contracts, adapters, and workflows rather than packages. A provider SDK or document parser is justified only after the user-confirmed source corpus proves a concrete capability gap; if needed, add one pinned adapter behind an existing-style Protocol, preserve raw and derived hashes, and keep its output non-authoritative until review.

**Core technologies:**

- **CPython 3.13.14 (`>=3.13,<3.14`)**: orchestration, hashing, private file custody, in-memory indexes, metrics, and CLI — the standard library covers the bounded, single-user workflow.
- **Pydantic 2.13.4**: strict frozen domain contracts, validation, serialization, and JSON Schema — retain one contract system and do not loosen sealed v1 schemas.
- **Canonical JSON + JSONL**: immutable bundles, current snapshots, append-only events, review lineage, and experiment records — inspectable, replayable, diffable, and already supported by the repository.
- **In-memory dictionaries and adjacency indexes**: graph traversal and coverage projection — persist canonical records, not a second graph engine.
- **Project-owned Protocol ports**: career-source and JD interpretation — recorded/offline implementations remain the default; model/provider output proposes but never confirms truth.
- **pytest 9.1.1, Ruff 0.16.0, and uv 0.12.0**: deterministic fixtures, adversarial and store-safety tests, lint/format, and locked execution — no new test or experiment framework is needed.

Critical version and dependency rules:

- Keep the current interpreter, package pins, `.python-version`, `pyproject.toml`, and `uv.lock`; no dependency update is part of v1.1 by default.
- Reuse existing canonical hashing, atomic replacement, create-only bundle, and provider-neutral decision seams.
- Add exactly one provider SDK or one format-specific parser only after a real accepted source requires it and fidelity/contract fixtures exist.
- Continue to defer databases, graph/vector stores, agent frameworks, web/UI stacks, telemetry, cloud storage, broad document conversion, and statistical platforms.

### Expected Features

**Must have (table stakes):**

- **Declared sources and cutoff** — bind “full career” to an inspectable source universe, unavailable-source declarations, capture metadata, and a recorded cutoff.
- **All-known-item reconciliation and user seal** — every candidate or user-added Experience, Contribution, Evidence item, and candidate Skill receives an explicit disposition; the user confirms the exact inventory hash without silent omissions.
- **One canonical status-aware graph** — retain confirmed, reviewed, pending, insufficient-evidence, and unresolved-responsibility content with stable IDs and merge/split/revision lineage.
- **Review-only mastery projection** — only current, admitted, substantively reviewed `reviewed-user-truth` Contribution–Skill assessments affect mastery.
- **Truthful uncertainty** — absent review is not a zero; relevant pending or unresolved content yields `uncertain` or `missing-evidence`, never positive support or an invented shortfall.
- **Resumable full-career audit queue** — reuse the existing one-question audit engine and prioritize JD-relevant unresolved Contributions without creating a second interview workflow.
- **Exactly three user-supplied real JDs** — retain exact private raw bytes, identity, acquisition metadata, and distinct source hashes; neither the system nor an evaluator substitutes the corpus.
- **Source-bound JD proposal and item review** — reconstruct every requirement from valid source spans, preserve absent fields, and support explicit edit/split/merge/add/reject lineage.
- **Immutable JD acceptance and corpus sealing** — acceptance binds the reviewed proposal and raw source hashes; exactly three distinct accepted packets are sealed before evaluation.
- **Frozen evaluation and decision ledger** — bind graph, corpus, charter, policies, baseline, blind assignment, repetitions, judgments, deviations, and the final reproducible decision.

**Should have (core differentiators):**

- **Completeness with truthful unknowns** — permit a user-confirmed coverage boundary without laundering unresolved content into capability.
- **Separate inventory, assessment, and admission authority** — prove `confirmed ≠ reviewed ≠ admitted` through contracts and negative tests.
- **Uncertainty-preserving JD matching** — explain whether a requirement lacks capability, evidence, review, or responsibility resolution.
- **Immutable, disputable JD interpretation** — preserve every correction from exact raw bytes through accepted requirements.
- **One truthful graph with three relevance views** — JDs may change selected Contributions and gaps, but never the graph or mastery hashes.
- **A hypothesis allowed to fail** — retain negative, unstable, or partial evidence and emit the frozen result rather than optimizing for roadmap momentum.

**Defer until a supported, scoped expansion decision:**

- Dynamic JD-tailored résumé selection and rewriting, followed by wording review, diff, layout, and export.
- Evidence-producing gap work, Gap Sprints, and post-work reassessment.
- Additional JDs or users except a preregistered replication for a named generalization gap.
- Continuous LinkedIn/GitHub/document synchronization, broad ontology ingestion, embeddings-first matching, graph visualization, and production UI.
- Multi-user SaaS, recruiter/employer workflows, applicant ranking, job application automation, and any claim about interviews, offers, hiring, employment, or long-term career outcomes.

### Architecture Approach

Extend the existing modular monolith with a functional core and imperative shell. One private `.career-evidence/` workspace contains several narrow repositories because sources, inventory, audits, assessments, JDs, and evaluations own different facts; this is still one persistence boundary, not multiple competing ledgers. A single projector joins exact accepted inventory, audit, resolution, assessment, and policy versions into an immutable `CareerGraphSnapshot`. No command edits that snapshot directly, and no JD or evaluation artifact becomes a second mastery authority.

**Major components:**

1. **Workspace and source custody** — one path/permission policy; create-only raw source envelopes; regular-file, link, hash, fsync, and redaction checks.
2. **Career inventory workflow** — source candidates, item-level include/exclude/edit/split/merge review, coverage ledger, cutoff, and immutable accepted revision.
3. **Existing audit workflow, generalized** — consume accepted `ContributionContext` instead of STOA-specific paths while preserving one-question, attribution, assistance, pause/resume, and conclusion review behavior.
4. **Skill resolution and assessment authority** — reviewable aliases and immutable assessment versions; only admitted reviewed-user-truth reaches aggregation.
5. **Canonical graph projector** — the sole deterministic graph writer; retains all in-scope items and states, rejects dangling identities, and moves the current pointer only with expected-prior-hash checks.
6. **JD intake and corpus custody** — raw source → proposal → item review → exact-hash acceptance → ordered exactly-three-packet corpus.
7. **Read-only comparison** — compare accepted JD packets with one confirmed graph snapshot, keep match semantics separate from mastery, and assert graph hash stability.
8. **Evaluation and finalization** — create-only deterministic, adversarial, stability, human, blind-baseline, holdout, replication, and frozen-decision artifacts.

Key patterns are proposal → review → acceptance; stable source-local identity before cross-source deduplication; immutable inputs with versioned policies; one deterministic graph projector; source-bound interpretation ports; functional core/imperative shell; and exact hash ancestry across every transition.

### Critical Pitfalls

1. **False completeness and coverage-as-capability** — define completeness as all known items from declared sources as of a user-confirmed cutoff, retain unresolved states, and keep every non-admitted assessment out of mastery.
2. **Alias, duplicate, or responsibility inflation** — assign stable source-local IDs before reconciliation, preserve merge/split ancestry, rerun no-inflation invariants, and resolve user/team/other-person/coding-agent/third-party responsibility independently of artifact presence.
3. **Source tampering or privacy leakage** — hash raw bytes before interpretation, bind converter/version and derived-text hashes, use one hardened private store, reject unsafe links, and expose only safe identifiers/counts/hashes outside the ignored workspace.
4. **JD invention, substitution, or backflow** — require reconstructable spans and item-level completeness review, accept without reparsing, seal exactly three distinct packets, bind every run to immutable hashes, and prove comparisons leave the graph unchanged.
5. **Reviewer leakage and effectiveness overclaim** — freeze opaque assignments, baseline, criteria, graph, corpus, and reviewer roles before results; retain disagreement and variance; apply only the preregistered decision meanings and state generalization limits.

## Implications for Roadmap

The following are dependency-aware **suggested phase topics**, not final roadmap phases or new requirements. Historical numbering ends at Phase 6, so the topics continue from 7 only to help the roadmapper preserve ancestry. The roadmapper must reconcile, merge, split, or renumber them against the authoritative v1.1 requirements; research recommendations do not override those requirements.

### Suggested Phase Topic 7: Generic Identity, Source Custody, and One Private Workspace

**Rationale:** Every later artifact depends on generic, privacy-safe identities and one storage boundary; widening STOA regexes or adding per-format stores would bake fixture assumptions into production.
**Delivers:** Tagged source locators, source envelopes, generic IDs, one `WorkspacePaths` policy, shared atomic/create-only primitives, permission and link verification, safe status output, and a frozen STOA legacy adapter.
**Addresses:** Heterogeneous source custody, privacy, stable identity, and no-new-dependency stack retention.
**Avoids:** Parallel stores/parsers, source substitution, private-data leakage, phase-number storage contracts, and speculative infrastructure.

### Suggested Phase Topic 8: Full-Career Inventory, Reconciliation, and Cutoff Seal

**Rationale:** The coverage denominator and user authority must exist before a “full-career” graph can be claimed or production assessments scheduled.
**Delivers:** Declared-source manifest, all-known-item proposal, explicit category coverage, item correction/add/split/merge/exclude lineage, unresolved dispositions, resumable review packets, and a user-confirmed immutable inventory revision.
**Addresses:** Full-career completeness, user control, explicit unknowns, and visible audit readiness.
**Avoids:** File-count completeness, silent drops, resume-as-career substitution, and bulk acceptance.

### Suggested Phase Topic 9: Generic Contribution Audit and Attribution

**Rationale:** Real Contribution evidence and responsibility boundaries must be established before Skill resolution or score-bearing assessment.
**Delivers:** Existing one-question audit over accepted inventory IDs and source hashes, contribution scheduling, neutral capability probes, separate responsibility and assistance review, immutable conclusions, and stale-lineage invalidation.
**Addresses:** Full-career audit queue, attribution, evidence sufficiency, pause/resume, and Contribution-level grounding.
**Avoids:** A second interview engine, team or coding-agent transfer, artifact-presence mastery, and unresolved responsibility entering assessment.

### Suggested Phase Topic 10: Skill Resolution and Reviewed-User-Truth Mastery

**Rationale:** Candidate labels and confirmed career facts remain non-scoring until reviewable Skill identity and the existing assessment/admission path are applied.
**Delivers:** Reviewable alias/equivalence decisions, immutable Contribution–Skill versions, real-user policy calibration, review-only aggregation, uncertainty semantics, and duplicate/no-inflation regression evidence.
**Addresses:** Specific Skill identity, separate mastery/centrality/confidence/context/duration, anchor integrity, and admission authority.
**Avoids:** Alias inflation, ontology propagation, default-zero scoring, arithmetic promotion, and candidate claims becoming discounted mastery.

### Suggested Phase Topic 11: Canonical Graph Projection and User Confirmation

**Rationale:** Downstream comparison needs one complete, immutable read model after inventory, audit, resolution, and assessment authorities are stable.
**Delivers:** A deterministic `CareerGraphSnapshot`, explicit coverage records for every accepted item, exact upstream/policy hashes, graph confirmation lineage, rebuild tests, and an expected-prior-hash current pointer.
**Addresses:** One canonical graph, completeness distinct from mastery, stable identity, and inspectable readiness.
**Avoids:** Mutable universal graphs, copied fact ledgers, unassessed-node loss, stale sidecars, and multiple graph authorities.

### Suggested Phase Topic 12: Three Real JDs, Item Review, and Immutable Corpus

**Rationale:** The empirical corpus must be supplied and accepted by the user before any target outcomes can influence extraction, selection, or policy.
**Delivers:** One JD interpretation port, recorded/offline proposals, span-bound requirements, item-level edit/split/merge/add/reject review, exact-hash acceptance, and one ordered corpus manifest containing exactly three distinct user-supplied real JDs.
**Addresses:** Raw-JD authority, correction, whole-packet acceptance, corpus custody, and prompt-like content as inert data.
**Avoids:** Synthetic substitution, omission/invention, re-parsing during acceptance, live-URL drift, bulk acceptance, and post-result corpus replacement.

### Suggested Phase Topic 13: Workspace-Bound Comparison and Frozen Evaluation Execution

**Rationale:** Automated structural and stability evidence should be generated from sealed inputs before human comparative judgments, without writing backward into career truth.
**Delivers:** Requirement-level comparisons bound to graph/corpus/packet/policy hashes; before/after graph-isolation assertions; deterministic, adversarial, three-attempt stability, holdout/leave-one-out, and feasible replication run bundles; retained deviations and failures.
**Addresses:** Truthful relevance views, uncertainty-aware comparison, experiment reproducibility, and no-backflow guarantees.
**Avoids:** JD-conditioned mastery, moving current pointers, stale/substituted manifests, hidden exclusions, averaged-away critical failures, and evaluation mutation.

### Suggested Phase Topic 14: Blind Human Review and Frozen Core-Hypothesis Decision

**Rationale:** Automated checks cannot establish decision usefulness, and a polished result must not bypass the preregistered blind baseline, disagreement, replication, or decision rules.
**Delivers:** Opaque A/B assignment, frozen baseline and reviewer roles, human usefulness judgments, disagreement/adjudication records, criterion-by-criterion finalization, blockers and limitations, and the immutable `supported` / `partially-supported` / `rejected` decision.
**Addresses:** Blind baseline comparison, human authority, honest failure, and bounded generalization.
**Avoids:** Reviewer leakage, baseline tuning after results, roadmap-momentum bias, and résumé/interview/offer/hiring/employment-effectiveness claims.

### Phase Ordering Rationale

- Build generic identity and one private custody boundary before real source ingestion so adapters cannot create competing stores or authorities.
- Seal the inventory before claiming full-career coverage, but do not require every item to become assessed; explicit unknowns keep the experiment bounded and truthful.
- Audit Contributions before resolving score-bearing Skills; review/admit assessments before projecting mastery; project and confirm one graph before admitting target JDs into comparison.
- Accept all three JDs before evaluating any final result so corpus, extraction, and policy cannot be tuned to observed outcomes.
- Run comparison and evaluation as read-only consumers; corrections create new upstream versions and a separately declared rerun, never an in-place “improvement.”
- End at the frozen core-hypothesis decision. Any résumé or gap-work phase belongs to a later requirements process only if the decision authorizes a scoped follow-on.

### Research Flags

Suggested topics likely needing deeper phase research or real-fixture discovery during planning:

- **Suggested Topic 8:** Inventory reconciliation, merge/split lineage, source-category coverage, and manageable user review packets depend on the actual career corpus.
- **Suggested Topic 9:** Neutral capability probes and evidence/responsibility stopping rules vary by Skill family and should be validated without leading the user.
- **Suggested Topic 10:** Real-user aggregation policy, confidence admission, anchor promotion, alias resolution, and uncertainty categories require calibrated fixtures.
- **Suggested Topic 12:** The actual JD/source formats determine whether a provider or parser is needed; extraction completeness and span semantics need corpus-specific tests.
- **Suggested Topics 13–14:** Blind reviewer operations, replication feasibility, disagreement handling, and the mapping from retained evidence to the already frozen decision need preregistered operational detail.

Suggested topics with established implementation patterns where a separate research pass can usually be skipped:

- **Suggested Topic 7 storage mechanics:** Pydantic contracts, canonical hashing, atomic/create-only writes, local permissions, Protocol ports, and pytest safety fixtures already exist; research is needed only if encryption, binary parsing, or external transfer becomes an explicit requirement.
- **Suggested Topic 11 graph mechanics:** Deterministic projection, immutable snapshots, in-memory indexes, exact hash ancestry, and compare-and-swap pointer movement are well-defined in the current code and research.
- **Suggested Topic 13 structural comparison mechanics:** Pure read-only comparison and canonical evaluation bundles follow established repository patterns; deeper research should focus on evaluation design, not infrastructure.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Direct code and lockfile inspection show the current Python/Pydantic/stdlib/pytest stack covers v1.1. Provider and parser choices remain intentionally deferred until a real corpus proves need. |
| Features | HIGH | Table stakes, anti-features, authority semantics, and exactly-three-JD behavior derive directly from `PROJECT.md`, the frozen v1.0 foundation, and the current evaluation charter. External product analogues are corroborative only. |
| Architecture | HIGH for boundaries; MEDIUM for policy details | One workspace, narrow authorities, one projector, immutable inputs, and read-only evaluation map cleanly to verified code seams. Merge/split, coverage gates, and final policy versions need real fixtures. |
| Pitfalls | HIGH for authority, custody, and isolation risks; MEDIUM for operational evaluation details | The critical failures are visible in the current contracts and milestone constraints. Reviewer logistics, real-source heterogeneity, and replication feasibility remain empirical. |

**Overall confidence:** HIGH in the recommended scope, architecture boundaries, and dependency order; MEDIUM in the phase-level policies that must be decided with the user's real career corpus and three real JDs.

### Gaps to Address

- **Actual career-source inventory:** Source kinds, unavailable materials, duplicates, and conversion needs are unknown until the user declares the corpus. Start with raw custody and deterministic adapters; add no parser speculatively.
- **User-blocking authority checkpoints:** The inventory seal, unresolved-state review, graph confirmation, three-JD selection/acceptance, and human evaluation require explicit user participation and resumable readiness views.
- **Identity reconciliation:** One-to-many and many-to-one merge/split cases need fixtures that preserve source-local ancestry without creating duplicate mastery.
- **Coverage and uncertainty policy:** Planning must state which unresolved states block inventory or graph confirmation and how each state affects JD judgments without becoming zero mastery.
- **Real-user calibration:** Aggregation, confidence gates, comparison policy versions, and higher-anchor promotion must be frozen from reviewed fixtures before the final run.
- **Evaluation operations:** Reviewer independence, opaque assignment, baseline custody, disagreement/adjudication, holdout/replication feasibility, and rerun rules must be executable rather than prose-only.
- **Privacy escalation boundary:** Current local permissions are appropriate for v1.1. Encryption at rest, synchronization, upload, or telemetry would require a separate threat model and explicit authority.
- **Bounded claims:** Three JDs and one user can test the core hypothesis under declared conditions, not general hiring or employment outcomes. The final artifact must state that limitation even if the result is supported.

## Sources

### Primary (HIGH confidence)

- [PROJECT.md](../PROJECT.md) — v1.1 goal, active requirements, authority semantics, exactly-three-JD boundary, and out-of-scope claims.
- [Current roadmap](../ROADMAP.md) and archived v1.0 roadmap/requirements — historical Phase 1–6 ancestry and the incomplete empirical validation carried into v1.1.
- [STACK.md](./STACK.md) — current dependency surface, project-owned seams, exact versions, and no-new-dependency recommendation.
- [FEATURES.md](./FEATURES.md) — acceptance checkpoints, authority/status semantics, table stakes, anti-features, and feature dependencies.
- [ARCHITECTURE.md](./ARCHITECTURE.md) — one-workspace architecture, component boundaries, one canonical projector, data flows, and build order.
- [PITFALLS.md](./PITFALLS.md) — authority, identity, privacy, JD custody, evaluation isolation, and overclaim risks.
- `validation/jd/evaluation-charter.json` — frozen case inventory, repetition, baseline, blind-review, fabrication, and limitation rules.
- Existing `domain`, `audit`, `assessment`, `jd`, and `validation` modules — verified contracts, review/admission authority, private custody, graph isolation, hashing, and create-only storage seams.
- [Pydantic documentation](https://docs.pydantic.dev/latest/) — strict validated models and JSON Schema.
- [Python 3.13 library documentation](https://docs.python.org/3.13/library/) — hashing, file controls, atomic replacement, fsync, statistics, and optional SQLite boundary.
- [pytest documentation](https://docs.pytest.org/en/stable/) — parametrization, fixtures, markers, and temporary-directory support.
- [OWASP LLM Prompt Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html) and [File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) — untrusted-input separation, human review, allowlists, restricted storage, and file-processing controls.
- [NIST AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/) — provenance, privacy, human oversight, limitations, and repeatable evaluation.
- [W3C PROV](https://www.w3.org/TR/prov-overview/) and [Web Annotation](https://www.w3.org/TR/annotation-model/) — derivation, attribution, revision, and source-segment anchoring.

### Secondary (MEDIUM confidence)

- Europass and LinkedIn documentation cited in [FEATURES.md](./FEATURES.md) — broad editable career inventories and item-level user control as interface expectations.
- Teal, Huntr, and Jobscan product pages cited in [FEATURES.md](./FEATURES.md) — master-source, JD review, and text-baseline expectations; no vendor effectiveness claim was adopted.
- Microsoft human-AI interaction guidance, APA responsible assessment guidance, OSF preregistration guidance, and the human-baseline research cited in [FEATURES.md](./FEATURES.md) — correction, oversight, preregistration, and baseline rigor.

---
*Research completed: 2026-08-28*
*Ready for roadmap: yes — requirements remain authoritative; suggested topics are advisory*
