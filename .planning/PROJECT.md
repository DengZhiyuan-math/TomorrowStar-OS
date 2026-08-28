# Career Evidence Graph — Core Hypothesis Validation

## What This Is

This project is the local, evidence-grounded foundation for an agentic, skill-graph-based résumé and career-gap system. Its v1.0 closeout established Contribution-based records, auditable Grill-Me conclusions, attribution, Skill assessment and no-inflation aggregation, plus content-free JD-comparison and private-intake boundaries.

v1.0 is a user-approved partial closeout, not a successful empirical validation of the full hypothesis: no reviewed personal Skill graph was built and no real JD evaluation was run. Those two activities begin the next milestone. The broader product will use a reusable Skill graph to select and rewrite relevant experiences for tailored résumés and propose evidence-producing gap-closing work, but those downstream loops remain outside this foundation.

## Core Value

Accurately determine what the user can genuinely do within specific contributions and convert that understanding into skill scores and graph relationships that are useful for JD-relevant career decisions.

## Requirements

### Validated

- [x] **Validated in Phase 2:** Supported career-history types can be represented as strict `Experience → Contribution` records with provenance-bearing Evidence linked to concrete Contribution claims.
- [x] **Validated in Phase 2:** Contribution is the minimum auditable assessment unit; direct mastery paths from Experience, credential, title, repository, résumé skill list, or ontology relationships fail closed.
- [x] **Validated in Phase 2:** Contribution–Skill records keep mastery, centrality, confidence, context, duration, basis, responsibility, and assistance as distinct validated fields without selecting a calibration or aggregation policy.
- [x] **Validated in Phase 2:** A document-bounded, item-by-item human-reviewed STOA fixture can be sealed with immutable provenance and exercised against deterministic known-good and single-fault known-bad cases.
- [x] **Implemented in Phase 3:** A selected Contribution can be inspected, questioned one decision at a time, attributed across user/team/coding-agent/third-party work, resumed, and concluded through a reviewable local audit.
- [x] **Implemented in Phase 4:** Reviewed Contribution–Skill assessments can be admitted and aggregated with explicit anchors, confidence gates, immutable reassessment history, and no mechanical score inflation.
- [x] **Implemented in Phase 5 foundation:** Content-free JD packets, deterministic pure graph projections, private JD intake, and a preregistered evaluation charter enforce truthful source and graph-isolation boundaries.

### Active

- [ ] Build a reviewed, user-truth personal Skill graph from real Contributions, Evidence, attribution, and confirmed assessments.
- [ ] Accept user-supplied real JDs and evaluate them against that reviewed graph without allowing JD wording to create mastery claims.
- [ ] Run the preregistered deterministic, adversarial, stability, human-review, and blind-baseline evaluation with the real graph and JD inputs.
- [ ] Resolve or explicitly re-baseline the acknowledged Phase 2 full-suite regression before claiming the repository-wide suite is green.
- [ ] Run a held-out and minimal non-STOA replication, then make the evidence-backed core-hypothesis decision.

### Out of Scope

- Full production résumé compiler — tailored résumé generation is a core product output, but implementation is deferred until the skill graph proves useful for JD-relevant selection.
- One-week Gap Sprint generation and post-project reassessment — part of the broader product loop, deferred until the assessment model is validated.
- Modeling the user’s entire career history — the first validation uses STOA and only the minimum additional material required for meaningful tests.
- Finalizing every scoring dimension, weighting, aggregation formula, threshold, or calibration rule during project initialization — these must be developed and tested against concrete cases.
- Automated job application, recruitment-site automation, recruiter tooling, or job-search automation — unrelated to the first hypothesis.
- Multi-user SaaS or a complex web interface — unnecessary for validating the audit and scoring model.
- Large-scale external skill-ontology ingestion or a graph database — premature before the internal model and validation cases are stable.

## Context

The intended final product is not a keyword rewriter for a fixed résumé. Its central loop begins with Grill-Me audits of existing projects, employment, research, publications, education, teaching, open-source contributions, and other résumé-relevant experiences. It then builds a reusable user skill graph, compares that graph with structured JD requirements, dynamically selects the most relevant experiences, produces tailored résumé narratives, identifies reachable gaps, proposes evidence-producing work, and feeds completed work back through Grill-Me.

For the current project, the graph is an internal representation supporting future résumé generation, matching, and skill development; it is not the product goal by itself. Résumé generation remains a core output of the broader system even though its full implementation is outside this validation scope.

The agreed domain relationships are:

```text
Experience
  CONTAINS → Contribution

Contribution
  DEMONSTRATES → Skill

Evidence
  SUPPORTS → Contribution
```

`Experience` is a unified upper-level container rather than a synonym for Project. A single Experience can contain many Contributions. A Contribution represents a distinguishable piece of work actually performed by the user, such as designing a module, completing a proof, implementing a data pipeline, operating a deployment, or leading a product decision. It is the smallest Grill-Me audit unit.

A Contribution may demonstrate multiple Skills, and the same Skill may be supported by Contributions from multiple Experiences. Skill-focused follow-up questions are allowed, but every assessment must return to concrete Contributions. Evidence such as source code, commits, papers, experiments, deployments, documentation, or user explanations supports a Contribution rather than forming another audit layer.

Each `ContributionSkillAssessment` should at least preserve:

```text
contribution_id
skill_id
demonstrated_mastery: 0–100
skill_centrality: 0–100
evidence_confidence: 0–100
context
duration
assessment_basis
```

`demonstrated_mastery` is the highest capability level that this Contribution can establish for the specific Skill. `skill_centrality` records how important that Skill was to completing the Contribution. `evidence_confidence` records how credibly the available information supports the Contribution, responsibility attribution, and mastery judgment. High confidence does not imply high mastery; high centrality does not imply high mastery; high mastery with weak confidence remains provisional.

At user level, each specific Skill receives one relatively stable mastery score. Supporting facts such as independence, complexity, implementation maturity, explanation quality, and operational responsibility inform that judgment but are not generic user-level sub-scores. Evidence confidence, verified duration, recency, context, and JD-specific match remain distinct so the meaning of the mastery score does not change with the target job or quantity of documentation.

The accepted mastery anchors are:

```text
0–19    Exposure only; cannot complete a practical task
20–39   Understands fundamentals; can complete simple tasks with explicit guidance
40–54   Can complete bounded practical tasks with documentation or guidance
55–69   Can independently complete common, well-bounded practical tasks
70–79   Can independently handle complex problems and explain and defend decisions
80–89   Can own a complete module or system, including failures, trade-offs, and maintenance
90–95   Has repeatedly carried advanced responsibility in multiple real contexts and can guide others
96–100  Rare; sustained, broad, and strongly verified expert capability
```

The eventual user-level aggregation should use demonstrated mastery as the capability signal, skill centrality as contribution importance, and evidence confidence as an admissibility/discount and confidence signal. A collection of Contributions may justify a user score above the highest single Contribution only when the collection observably satisfies the higher capability anchor—for example, repeated advanced responsibility across real contexts. A numerical pile-up of many mid-level or incidental uses must never create expert mastery. The exact aggregation formula is intentionally not frozen.

STOA is the initial validation Experience. It may contain Contributions such as teacher-handoff workflow design, structured AI output definition, product requirements and roadmap ownership, backend participation, and deployment configuration. These Contributions may demonstrate different Skills with different mastery, centrality, confidence, contexts, and responsibility attribution.

The project starts from a pinned open-source reference baseline rather than designing every subsystem from scratch:

- **Tabiya Compass** for experience exploration, responsibility separation, interview state, and conversation/extraction/transition boundaries.
- **Matt Pocock Skills** for one-question-at-a-time grilling, artifact inspection, and domain-language clarification.
- **MIND Tech Ontology** for skill normalization and ontology relations, without propagating implied knowledge into user mastery.
- **CV Market Learning Planner** for versioned career workspaces, analysis history, deterministic helpers, and gap/learning artifacts.
- **Hiring Agent** for structured résumé extraction, Pydantic contracts, staged caching, role-specific evaluation, and adversarial lessons.
- **Resume Matcher** for later résumé-tailoring interaction and export patterns, not as the source-of-truth model.

These repositories are pinned under `references/upstream/`; `references/README.md` records the reuse matrix and license boundaries. They are reference inputs rather than runtime dependencies. Any copied or adapted code must retain required attribution and be justified against this project’s distinct Experience → Contribution → Skill assessment model.

## Constraints

- **Validation scope**: Prove the Grill-Me → Contribution–Skill assessment → user Skill graph → JD usefulness hypothesis with STOA and a small JD set before implementing the full product pipeline.
- **Assessment semantics**: Every user-level score evaluates one specific Skill; unrelated capabilities must not be hidden as generic subdimensions of that score.
- **Audit granularity**: Contribution is the minimum auditable fact unit; Experience alone cannot produce a Skill score.
- **Score separation**: Mastery, evidence confidence, verified duration, context, and JD match must retain different meanings.
- **Anchor integrity**: Higher mastery bands require observable higher-order capability; they cannot be reached through mechanical accumulation of weaker evidence.
- **Truthfulness**: User, team, other-person, Codex-assisted, and third-party work must remain distinguishable wherever responsibility affects assessment.
- **Decision timing**: Formula details, confidence gates, calibration rules, and implementation boundaries are phase-level decisions to validate with fixtures rather than assumptions to freeze during initialization.
- **Open-source provenance**: Reused or adapted code and patterns must identify their upstream repository, pinned revision, license, and local divergence.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Scope this project to the first core hypothesis rather than the complete final pipeline | Validate assessment usefulness before investing in résumé compilation and gap-planning implementation | ⚠ v1.0 established the foundation only; the empirical test moved to the next milestone |
| Keep dynamic JD-tailored résumé generation as a core product output | The product must generate role-specific résumés from the skill graph, not merely present an evidence graph | — Pending |
| Use `Experience → Contribution → Skill`, with Evidence supporting Contribution | Supports heterogeneous career history while grounding every Skill judgment in distinguishable work | — Pending |
| Make Contribution the smallest Grill-Me audit unit | Whole experiences are too coarse, while Skill-first interviews lose the concrete work context | — Pending |
| Give every specific user Skill one stable 0–100 mastery score | Keeps capability distinct from evidence volume, duration, and target-JD fit | — Pending |
| Use the agreed observable capability anchors | Makes score ranges interpretable in terms of what the user can actually do | — Pending |
| Separate demonstrated mastery, skill centrality, and evidence confidence on Contribution–Skill assessments | Prevents capability, relevance, and credibility from collapsing into one ambiguous relationship score | — Pending |
| Allow combined Contributions to justify a higher mastery band only when they satisfy that band’s observable conditions | Supports repeated cross-context evidence without permitting mathematical score inflation | — Pending |
| Defer the exact aggregation formula and calibration rules | Concrete fixtures and human-reviewed cases are required before those details can be trusted | ✓ Conservative policy and explicit anchors are implemented; real-user calibration remains pending |
| Treat local-first, deterministic scoring, and provenance mechanisms as implementation choices or constraints to validate—not as the product definition | The product is defined by its agentic assessment, skill model, JD adaptation, résumé generation, and gap-closing loop | — Pending |
| Integrate pinned upstream references before implementation | Existing open-source projects contain relevant interview, ontology, workspace, parsing, and résumé-output patterns that should be evaluated before building substitutes | — Pending |
| Keep upstreams as licensed submodules with a local reuse matrix | Preserves exact source and attribution while preventing wholesale architecture copying | ✓ Applied in v1.0 foundation |

## Evolution

v1.0 closed on 2026-08-28 by explicit user authorization as a partial closeout. The archived roadmap and requirements preserve all Phase 5/6 gaps. The next milestone starts with a real reviewed personal graph and user-supplied JD tests; it must not infer a positive product hypothesis from v1.0's content-free foundation.

---
*Last updated: 2026-08-28 after user-approved v1.0 partial closeout*
