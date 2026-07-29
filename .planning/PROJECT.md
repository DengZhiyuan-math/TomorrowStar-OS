# Career Evidence Graph — Core Hypothesis Validation

## What This Is

This is the first validation project for an agentic, skill-graph-based résumé generation and career-gap system. It tests whether a Grill-Me workflow can accurately audit what a user understands and can independently explain, implement, reproduce, defend, or operate within their real experiences, then turn those findings into stable skill assessments that are useful when comparing the user with a small set of job descriptions.

The broader product will use this reusable skill-oriented career graph to dynamically select and rewrite relevant experiences for tailored résumés and to propose evidence-producing gap-closing work. Those downstream product loops remain central to the product vision, but this project deliberately stops at validating the Grill-Me → skill graph → JD usefulness hypothesis before building the complete pipeline.

## Core Value

Accurately determine what the user can genuinely do within specific contributions and convert that understanding into skill scores and graph relationships that are useful for JD-relevant career decisions.

## Requirements

### Validated

(None yet — this project exists to validate the core hypothesis)

### Active

- [ ] Represent résumé-relevant history through the hierarchy `Experience → Contribution → Skill`, with Evidence supporting each Contribution.
- [ ] Treat Contribution as the smallest Grill-Me audit unit while retaining Experience as a unified container for employment, projects, research, publications, education, teaching, open-source work, internships, and related experience types.
- [ ] Audit a Contribution deeply enough to determine what the user personally understands and can explain, implement, reproduce, defend, debug, or operate.
- [ ] Extract specific Skills from audited Contributions without inferring mastery directly from an Experience, education credential, repository, or ontology relationship.
- [ ] Assess each Contribution–Skill relationship with separate `demonstrated_mastery`, `skill_centrality`, and `evidence_confidence` values, plus context, duration, and an explicit assessment basis.
- [ ] Aggregate credible Contribution–Skill assessments into one relatively stable 0–100 mastery score for each specific user Skill while keeping evidence confidence, verified duration, context, and JD match separate.
- [ ] Use observable capability anchors for the 0–100 mastery scale and prevent numerous low-level Contributions from mechanically accumulating into advanced mastery.
- [ ] Build and audit a representative STOA Experience with distinguishable Contributions, Evidence, Skills, responsibility attribution, and Contribution–Skill assessments.
- [ ] Parse a small number of representative JDs into structured skill expectations and test whether the resulting user skill graph supports meaningful comparison and relevant experience selection.
- [ ] Evaluate the hypothesis with reproducible fixtures, golden cases, human review, and documented calibration findings before expanding into the complete résumé and gap-planning pipeline.
- [ ] Establish a version-pinned open-source reference baseline before original implementation, with explicit reuse, adaptation, rejection, attribution, and license boundaries for each upstream project.

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
| Scope this project to the first core hypothesis rather than the complete final pipeline | Validate assessment usefulness before investing in résumé compilation and gap-planning implementation | — Pending |
| Keep dynamic JD-tailored résumé generation as a core product output | The product must generate role-specific résumés from the skill graph, not merely present an evidence graph | — Pending |
| Use `Experience → Contribution → Skill`, with Evidence supporting Contribution | Supports heterogeneous career history while grounding every Skill judgment in distinguishable work | — Pending |
| Make Contribution the smallest Grill-Me audit unit | Whole experiences are too coarse, while Skill-first interviews lose the concrete work context | — Pending |
| Give every specific user Skill one stable 0–100 mastery score | Keeps capability distinct from evidence volume, duration, and target-JD fit | — Pending |
| Use the agreed observable capability anchors | Makes score ranges interpretable in terms of what the user can actually do | — Pending |
| Separate demonstrated mastery, skill centrality, and evidence confidence on Contribution–Skill assessments | Prevents capability, relevance, and credibility from collapsing into one ambiguous relationship score | — Pending |
| Allow combined Contributions to justify a higher mastery band only when they satisfy that band’s observable conditions | Supports repeated cross-context evidence without permitting mathematical score inflation | — Pending |
| Defer the exact aggregation formula and calibration rules | Concrete fixtures and human-reviewed cases are required before those details can be trusted | — Pending |
| Treat local-first, deterministic scoring, and provenance mechanisms as implementation choices or constraints to validate—not as the product definition | The product is defined by its agentic assessment, skill model, JD adaptation, résumé generation, and gap-closing loop | — Pending |
| Integrate pinned upstream references before implementation | Existing open-source projects contain relevant interview, ontology, workspace, parsing, and résumé-output patterns that should be evaluated before building substitutes | — Pending |
| Keep upstreams as licensed submodules with a local reuse matrix | Preserves exact source and attribution while preventing wholesale architecture copying | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `$gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `$gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-30 after open-source reference integration*
