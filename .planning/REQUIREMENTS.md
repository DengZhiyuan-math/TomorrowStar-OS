# Requirements: Career Evidence Graph — Full Career Graph and Real JD Validation

**Defined:** 2026-08-28
**Milestone:** v1.1 — Full Career Graph and Real JD Validation
**Core Value:** Accurately determine what the user can genuinely do within specific contributions and convert that understanding into skill scores and graph relationships that are useful for JD-relevant career decisions.

## v1.1 Requirements

Requirements for this milestone. Each requirement must map to exactly one roadmap phase.

### Full-Career Inventory and Source Custody

- [ ] **INV-01**: The user can declare the career-source universe, unavailable sources, and a cutoff that define what “all known career history” means for one inventory revision.
- [ ] **INV-02**: The user can record every known employment, project, research, publication, education, teaching, open-source, internship, and related Experience in one inventory without a résumé or repository list being treated as complete by itself.
- [ ] **INV-03**: The user can review every discovered or user-added inventory item and explicitly confirm, edit, add, split, merge, exclude with reason, or retain it as unresolved without silent omission.
- [ ] **INV-04**: The user can inspect a coverage report for every supported Experience category, declared source, candidate item, unresolved item, and unavailable source before the inventory is called complete.
- [ ] **INV-05**: The user can seal one exact inventory revision and cutoff only after every candidate has a recorded disposition; any later correction creates a new immutable revision instead of rewriting the accepted inventory.
- [ ] **INV-06**: An evaluator can trace every accepted inventory fact and Evidence item to a retained source identity, content hash, capture metadata, and any versioned transformation that produced derived text.
- [ ] **INV-07**: The operator can process raw career sources in the ignored private workspace while committed artifacts, routine status output, logs, and errors expose only safe identifiers, counts, hashes, and redacted diagnostics.

### Canonical Skill Graph and Assessment Authority

- [ ] **GRF-01**: The user can run the existing artifact-aware, one-question-at-a-time audit for any accepted Contribution ID without production schemas, workflows, or CLI commands requiring a STOA-specific identifier or path.
- [ ] **GRF-02**: Each real Contribution audit preserves capability coverage, user/team/other-person/coding-agent/third-party attribution, evidence sufficiency, assistance, skips, contradictions, and unresolved responsibility as distinct reviewable facts.
- [ ] **GRF-03**: The user can review candidate Skill identities and explicitly accept, correct, merge, split, or leave ambiguous aliases while source-local identity and decision lineage remain inspectable.
- [ ] **GRF-04**: The user can inspect one canonical graph snapshot containing every item in the accepted inventory, including reviewed, pending, insufficient-evidence, unresolved-responsibility, confirmed, and excluded-with-reason states where applicable.
- [ ] **GRF-05**: Only current admitted `reviewed-user-truth` Contribution–Skill assessments can establish or increase mastery; inventory presence, pending review, insufficient evidence, unresolved responsibility, résumé/JD wording, ontology relations, titles, credentials, and repository presence have no mastery effect.
- [ ] **GRF-06**: The user can inspect mastery, skill centrality, evidence confidence, context, duration, recency, responsibility, assistance, assessment basis, and admission status as separate meanings for every score-bearing Contribution–Skill relationship.
- [ ] **GRF-07**: Duplicate sources, Evidence, Contributions, aliases, and incidental uses cannot mechanically increase mastery, confidence, duration, or cross-context promotion; a higher band still requires observable evidence for that anchor.
- [ ] **GRF-08**: The user can inspect and confirm a deterministic graph snapshot bound to the accepted inventory, current audit and assessment versions, Skill-resolution decisions, policy versions, exclusions, coverage states, and one canonical graph hash.
- [ ] **GRF-09**: A correction, reassessment, attribution change, or policy change creates a linked new version, invalidates stale graph snapshots and dependent results, and preserves the prior accepted lineage.
- [ ] **GRF-10**: The user can pause and resume a full-career audit queue that shows why each Contribution is pending and may prioritize unresolved items relevant to the fixed JD corpus without hiding or deleting non-prioritized inventory items.

### Real JD Intake and Comparison

- [ ] **JD-01**: The user can supply exactly three distinct real JD raw sources selected by the user, with exact private bytes, source identity, acquisition metadata, and three distinct raw-source hashes retained, and represent each as structured requirements containing reconstructable source spans, Skill or linked Skill constituents, required/preferred and core status, stated strength or responsibility, context, seniority, duration, and experience expectations where present.
- [ ] **JD-05**: The system can produce a source-bound interpretation proposal from each retained raw JD while prompt-like text remains inert, absent fields remain absent, and proposed content has no acceptance or mastery authority.
- [ ] **JD-06**: The user can review every proposed JD requirement and explicitly add an omitted requirement, edit fields, split, merge, accept, or reject an item while the original proposal and ordered correction lineage remain inspectable.
- [ ] **JD-07**: The user can immutably accept one reviewed packet for each of the three distinct raw-source hashes and seal those one-to-one source/packet identities into one corpus; any correction creates a new packet and invalidates dependent runs instead of modifying accepted bytes.
- [ ] **JD-08**: The user can inspect `supported`, `partially supported`, `unsupported`, and `uncertain` judgments for every accepted JD requirement, with cited Contribution–Skill lineage and missing capability, missing evidence, context mismatch, pending review, unresolved responsibility, and other uncertainty reported separately.
- [ ] **JD-09**: Comparing the same confirmed graph with any of the three accepted JDs can change only relevance, selected Contributions, gaps, route, and match judgments; the underlying graph and mastery hashes remain unchanged before and after every comparison.
- [ ] **JD-10**: An evaluator can reproduce each comparison from the exact accepted graph, JD corpus, packet, interpretation, comparison-policy, and configuration hashes without loading an arbitrary substitute or moving current pointer.

### Evaluation and Core-Hypothesis Decision

- [ ] **EVAL-01**: An evaluator can run deterministic schema, lineage, interval, duplication, alias, split/merge, ontology-non-propagation, JD-isolation, graph-rebuild, known-good, and known-bad tests against the complete real-input loop.
- [ ] **EVAL-02**: An evaluator can run adversarial and counterfactual cases covering borrowed responsibility, coding-agent or team attribution, evidence-volume inflation, centrality/confidence confusion, ontology inference, stale or substituted manifests, hidden text, unsafe source content, JD omission or invention, and prompt injection.
- [ ] **EVAL-03**: Each critical golden and adversarial case can run at least three times under one frozen versioned configuration, with supported mastery bands and JD judgments remaining stable and material variance reported rather than averaged away.
- [ ] **EVAL-04**: Independent human reviewers can judge inventory completeness, attribution, Skill specificity, mastery-anchor fit, centrality, evidence confidence, aggregation validity, JD interpretation, and JD usefulness while disagreement and adjudication remain retained.
- [ ] **EVAL-05**: A blinded reviewer can compare graph-based JD results with the preregistered flat-résumé or exact-keyword baseline using frozen relevance, truthfulness, decision-usefulness, and traceability criteria, with zero critical fabricated capability claims required for acceptance.
- [ ] **EVAL-06**: An evaluator can run sealed holdout, leave-one-Contribution-out, leave-one-JD-out, and feasible non-STOA or cross-Experience replication checks and can state the exact limits of any generalization claim from one user and three JDs.
- [ ] **DEC-01**: The milestone produces exactly one reproducible `supported`, `partially supported`, or `rejected for expansion` decision by applying the frozen validation rules and identifying every blocking failure, deviation, unstable result, and unresolved limitation.
- [ ] **DEC-02**: If and only if expansion is justified, the milestone produces a scoped next-milestone recommendation and provenance contract for dynamic JD-tailored résumé selection and rewriting without treating graph visualization, polished output, or the development evaluation as employment-effectiveness evidence.

## Future Requirements

Tracked product capabilities that remain central but are not part of the v1.1 roadmap.

### Dynamic JD-Tailored Résumé

- **RES-01**: The user can turn an accepted JD packet into a reusable requirement graph and inspect or correct its role-specific interpretation.
- **RES-02**: The user can dynamically select the most relevant Experiences and Contributions and generate a truthful role-specific résumé rather than keyword-editing a fixed résumé.
- **RES-03**: The user can trace every generated résumé claim to confirmed Contributions and Evidence and review, edit, accept, or reject proposed wording.
- **RES-04**: The user can compare revisions and export an approved tailored résumé in practical document formats.

### Evidence-Producing Gap Closure

- **GAP-01**: A user targeting a weakly matched but reachable role can receive a time-bounded project, open-source contribution, hackathon, or similar action plan tied to specific missing Skills and evidence goals; its exact duration must be confirmed before promotion.
- **GAP-02**: The user can feed completed gap-closing work back through Grill-Me and update Contributions, Evidence, assessments, and user Skill mastery without losing history.

### Broader Product Operation

- **OPS-01**: The user can maintain longitudinal career-graph changes across later JDs, generated résumés, gap work, and reassessments after the core hypothesis is supported.
- **OPS-02**: Additional users or JD corpora can be introduced only through a separately scoped replication or product-validation milestone with explicit privacy and authority boundaries.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Dynamic résumé selection, generation, wording review, layout, or export | Core downstream output, but implementing it before the v1.1 decision would contaminate the current hypothesis test. |
| Gap Sprint generation or post-gap reassessment | Deferred until graph usefulness and gap semantics are supported; plan duration is intentionally unfrozen here. |
| More or fewer than the exactly three user-selected real JDs | The frozen development evaluation requires a bounded three-JD corpus; a different corpus requires a new declared experiment. |
| Automated job applications, job-site automation, recruiter tooling, employer ranking, or applicant ranking | Unrelated to the user-authoritative assessment hypothesis and outside the product boundary. |
| Interview, offer, hiring, employment, or long-term career-effectiveness claims | One-user, three-JD development evidence cannot establish these outcomes. |
| Automatic acceptance of source, inventory, Skill, assessment, or JD interpretations | Structured output and parser confidence do not create user truth or mastery authority. |
| A second inventory, fact ledger, parser path, graph authority, validator, or scoring engine | Would create divergent truth and invalidate correction, custody, and evaluation semantics. |
| Graph database, vector database, embeddings-first mastery inference, generic agent framework, or speculative parser/provider dependency | No confirmed v1.1 requirement needs these; add only after a measured, corpus-specific gap. |
| Multi-user SaaS, authentication, billing, production web UI, or graph visualization | Delivery infrastructure and polish do not test the core hypothesis. |
| Upload, synchronization, telemetry, or cloud processing of private career/JD material | No external-transfer boundary is authorized for this local validation milestone. |

## Traceability

Roadmap phase mapping is populated after roadmap approval. Every v1.1 requirement must map to exactly one phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INV-01 | TBD | Pending |
| INV-02 | TBD | Pending |
| INV-03 | TBD | Pending |
| INV-04 | TBD | Pending |
| INV-05 | TBD | Pending |
| INV-06 | TBD | Pending |
| INV-07 | TBD | Pending |
| GRF-01 | TBD | Pending |
| GRF-02 | TBD | Pending |
| GRF-03 | TBD | Pending |
| GRF-04 | TBD | Pending |
| GRF-05 | TBD | Pending |
| GRF-06 | TBD | Pending |
| GRF-07 | TBD | Pending |
| GRF-08 | TBD | Pending |
| GRF-09 | TBD | Pending |
| GRF-10 | TBD | Pending |
| JD-01 | TBD | Pending |
| JD-05 | TBD | Pending |
| JD-06 | TBD | Pending |
| JD-07 | TBD | Pending |
| JD-08 | TBD | Pending |
| JD-09 | TBD | Pending |
| JD-10 | TBD | Pending |
| EVAL-01 | TBD | Pending |
| EVAL-02 | TBD | Pending |
| EVAL-03 | TBD | Pending |
| EVAL-04 | TBD | Pending |
| EVAL-05 | TBD | Pending |
| EVAL-06 | TBD | Pending |
| DEC-01 | TBD | Pending |
| DEC-02 | TBD | Pending |

**Coverage:**

- v1.1 requirements: 32 total
- Mapped to phases: 0
- Unmapped: 32 — roadmap pending

---
*Requirements defined: 2026-08-28*
*Last updated: 2026-08-28 after v1.1 research and scope confirmation*
