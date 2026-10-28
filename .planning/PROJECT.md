# TomorrowStar OS — Product and Research Scope

## Current product: local automatic applications — 2026-10-20

The user has aligned the [application specification](../docs/single-job-flow.md),
requirements APP-01–18. This is the current operational design. The system
ingests email recommendations, reuses career facts and application information,
and handles jobs sequentially through manual final Submit. Important missing
facts, conflicts and unknown results stop the current job; manual edits need one
Continue. Explicit user career corrections are saved with source and history.

The [system audit](../docs/system-audit-2026-10-20.md) records current gaps. The
[development plan](../docs/development-plan.md) defines the current work order.
Fixed batch limits, whole-run deadlines, repeated material acceptance and routine
write/transport approvals are superseded for this product. This revision changes
documents and planning; it does not implement or start real applications.

The research scope below remains independent. Its exact inventory, mastery and
three-JD acceptance rules govern research conclusions, not routine application
progress or direct fact updates. Product work does not close research gates.

## Research: Career Evidence Graph — Core Hypothesis Validation

## What This Is

This project is the local, evidence-grounded foundation for an agentic, skill-graph-based résumé and career-gap system. Its v1.0 closeout established Contribution-based records, auditable Grill-Me conclusions, attribution, Skill assessment and no-inflation aggregation, plus content-free JD-comparison and private-intake boundaries.

v1.0 is a user-approved partial closeout, not a successful empirical validation of the full hypothesis: no reviewed personal Skill graph was built and no real JD evaluation was run. Milestone v1.1 now builds a user-confirmed full-career graph, tests it against exactly three user-supplied real JDs, and makes the frozen core-hypothesis decision. The broader product will use the reusable Skill graph to select and rewrite relevant experiences for tailored résumés and propose evidence-producing gap-closing work, but those downstream loops remain outside this milestone.

## Core Value

Accurately determine what the user can genuinely do within specific contributions and convert that understanding into skill scores and graph relationships that are useful for JD-relevant career decisions.

## Research Milestone: v1.1 Full Career Graph and Real JD Validation

**Goal:** Build a user-confirmed full-career Skill graph, evaluate it against exactly three real JDs, and make an evidence-backed core-hypothesis decision.

**Target features:**
- A user-confirmed authoritative inventory of the user's full career history as of a recorded cutoff, with explicit coverage status for every known item.
- One canonical status-aware `Experience → Contribution → Skill` graph in which only reviewed assessments can establish or increase mastery.
- User-supplied raw-JD intake, item-level requirement review, immutable acceptance, graph comparison, and the frozen real-input evaluation and decision protocol.

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

- [ ] Build and receive user confirmation of an authoritative inventory covering all known career Experiences, Contributions, Evidence, and candidate Skills as of a recorded cutoff.
- [ ] Generalize the STOA-bounded ingestion and audit path into one canonical full-career graph with explicit reviewed, pending, insufficient-evidence, unresolved-responsibility, and confirmed states.
- [ ] Admit mastery only from real, attribution-preserving, human-reviewed Contribution–Skill assessments and preserve all unreviewed or unresolved content as non-authoritative for scoring.
- [ ] Accept exactly three user-supplied real JDs through source-bound extraction, item-level correction, and immutable review, then compare them without mutating the user graph.
- [ ] Run the frozen deterministic, adversarial, stability, human-review, blind-baseline, holdout, and replication evaluation and make the evidence-backed core-hypothesis decision.

### Out of Scope for the research experiment

- Dynamic résumé compilation as an experimental graph-effectiveness claim — outside the research evaluation; operational tailored materials proceed under APP-07.
- One-week Gap Sprint generation and post-project reassessment — part of the broader product loop, deferred until the assessment model is validated.
- Finalizing every scoring dimension, weighting, aggregation formula, threshold, or calibration rule during project initialization — these must be developed and tested against concrete cases.
- Automated job application, recruitment-site automation, recruiter tooling, or job-search automation — unrelated to the first hypothesis.
- Multi-user SaaS or a complex web interface — unnecessary for validating the audit and scoring model.
- Large-scale external skill-ontology ingestion or a graph database — premature before the internal model and validation cases are stable.

**Operational scope updated 2026-10-20:** The separately authorized application
product now follows [APP-01–18](../docs/single-job-flow.md). Recommendation mail
is labelled and archived after durable ingestion; ordinary materials, filling
and upload proceed autonomously under the enabled flow. Final Submit remains
manual. Research exclusions above do not postpone this operational work until
completion of the three-JD experiment.

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

## Research Constraints

- **Validation scope**: Prove the Grill-Me → Contribution–Skill assessment → user Skill graph → JD usefulness hypothesis with a user-confirmed full-career inventory and exactly three user-supplied real JDs for the research hypothesis. The separately authorized application product proceeds under APP-01–18.
- **Assessment semantics**: Every user-level score evaluates one specific Skill; unrelated capabilities must not be hidden as generic subdimensions of that score.
- **Audit granularity**: Contribution is the minimum auditable fact unit; Experience alone cannot produce a Skill score.
- **Score separation**: Mastery, evidence confidence, verified duration, context, and JD match must retain different meanings.
- **Anchor integrity**: Higher mastery bands require observable higher-order capability; they cannot be reached through mechanical accumulation of weaker evidence.
- **Truthfulness**: User, team, other-person, coding-agent-assisted, and third-party work must remain distinguishable wherever responsibility affects assessment.
- **Decision timing**: Formula details, confidence gates, calibration rules, and implementation boundaries are phase-level decisions to validate with fixtures rather than assumptions to freeze during initialization.
- **Open-source provenance**: Reused or adapted code and patterns must identify their upstream repository, pinned revision, license, and local divergence.

## Interview and Assessment Protocol

Use the [question-generation and scoring pipeline](../docs/question-scoring-pipeline.md)
for project interviews. Retrieve source context and prior answers before generating
questions. Keep the accepted Experience, selected Contributions, inspected facts,
and responsibility boundaries explicit.

| Order | Question layer | Observable target |
| --- | --- | --- |
| 1 | Project overview | Concisely explain the goal, content, main technical approach, personal contribution, result and limits |
| 2 | Project depth | Explain and defend relevant mechanisms, decisions, implementation or research reasoning, and verification within bounded Contributions |
| 3 | Transfer | Adapt an inspected mechanism to a similar problem with one explicit changed condition; explain assumptions, limits and verification |

Question layer and difficulty are different concepts. Depth and transfer each
retain their own demanding-to-simple ladder. Ask one focused question at a time.
Declare observable evaluation criteria before receiving its answer. Accept sound
alternative explanations; do not require a preferred wording or a memorized answer.

Preserve the three layers' conclusions separately. Score only a reviewed
Contribution–Skill relationship against the existing capability anchors. Do not
average the layers into a project score. Overview fluency alone does not establish
technical mastery. Transfer reasoning does not establish a new completed
Contribution, deployment, or repeated responsibility across real contexts.

### Grill-Me Recall Policy

Grill-Me assesses the user's capability and reviews their real work; it is not a memory test.
Before asking, retrieve and preserve relevant document labels, source locators, prior answers, and
artifact context. Explain unfamiliar labels in the question and use them to ground a concrete,
one-at-a-time capability prompt. A user not recalling a label, exact wording, or a project detail
is not negative capability evidence and must not cause an otherwise relevant Contribution to be
excluded. Record the resulting uncertainty explicitly, then assess only what the user can
actually explain, implement, reproduce, defend, or operate.

Route requests for missing context separately from capability answers. Such a
request does not consume a question or lower difficulty. Supplied reminders are
context, not evidence of the user's independent explanation.

### Resume Content Policy

Education reuses fixed confirmed institutions, degrees, dates, status and details.
Do not rewrite or omit it for JD relevance or repeat confirmation of unchanged
recorded facts. Resolve actual source conflicts separately; an in-progress degree
is not an awarded credential.

Select and order evidenced skills and work experience for the current JD, and
adapt their wording without inventing skills, proficiency, results or responsibility.
Preserve real team/collaborator scope and planned versus completed work.

AI assistance, coding-agent attribution and editor/tool-use provenance remain in
internal evidence records, not in the employer-facing resume. Supported technical
skills and project technologies remain valid content. Only important unresolved source
conflicts or substantive choices require user judgment. Material acceptance
is required only where the research or optional review operation explicitly seeks an accepted artifact. Ordinary application materials are generated, checked and used under APP-07; no routine source/PDF acceptance is required. Final Submit remains manual.

### Research Acceptance Boundary

The typed plan and read-only inspection entrypoint establish structure and binding
to supplied context only. Full-career inventory admission and complete interview
sequencing require the generic private adapter in Phase 9. Question-quality trials
and reviewed answer/anchor calibration remain required before personal scoring.
Phase 9 and Phase 10 success criteria retain these gates. Synthetic tests do not
establish semantic grading accuracy or personal capability.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Scope the research experiment to the first core hypothesis | Test assessment usefulness without claiming the application product is validated by research | ⚠ v1.0 established the foundation only; the empirical test moved to the next milestone |
| Deliver the local automatic application product independently of research completion | User-aligned APP-01–18 govern the continuous sequential flow, direct fact reuse and manual final Submit | ✓ Design aligned 2026-10-20; implementation and real acceptance remain planned |
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
| Build one canonical full-career graph with explicit coverage states | Completeness requires every known item to remain visible while mastery authority remains limited to reviewed assessments | — Pending |
| Use exactly three user-supplied real JDs and finish with the frozen decision protocol | Preserves user source authority and closes the empirical research validation loop without gating the separately authorized application product | — Pending |

## Evolution

v1.0 closed on 2026-08-28 by explicit user authorization as a partial closeout. The archived roadmap and requirements preserve all Phase 5/6 gaps. Milestone v1.1 starts from that content-free foundation and must not infer a positive product hypothesis until the full-career graph, real-JD evaluation, and frozen decision protocol are complete.

---
*Last updated: 2026-10-07 after integrating the three-layer interview protocol; milestone acceptance remains pending*
