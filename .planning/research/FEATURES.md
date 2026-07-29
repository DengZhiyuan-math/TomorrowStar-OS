# Feature Research

**Domain:** Contribution-grounded career capability assessment and JD comparison  
**Project:** Career Evidence Graph — Core Hypothesis Validation  
**Researched:** 2026-07-30  
**Confidence:** HIGH for project scope and pinned-upstream precedents; MEDIUM for proposed validation thresholds until calibrated on STOA

## Scope Boundary

This milestone must validate one loop:

```text
STOA Experience
  → distinguishable Contributions
  → artifact-aware, one-question-at-a-time Grill-Me audits
  → Contribution–Skill assessments
  → stable user Skill assessments
  → structured comparison with a small JD set
  → human-reviewed usefulness and calibration findings
```

The final product still has two core downstream outputs:

1. dynamically select and rewrite relevant Experiences and Contributions into a truthful, JD-tailored résumé; and
2. propose evidence-producing gap-closing work, then reassess the completed work.

Those outputs remain visible in the roadmap, but neither belongs in the current implementation. This validation should produce only the minimum interfaces and fixtures needed to show that the assessed graph could support them later.

## Feature Landscape

### Table Stakes for Core Validation

Missing any item below prevents a meaningful test of the stated hypothesis.

| Observable behavior | Why required now | Complexity | Acceptance signal |
|---|---|---:|---|
| Represent STOA as one `Experience` containing multiple distinguishable `Contribution` records, with `Evidence` supporting Contributions | Whole-experience scoring is explicitly invalid; Contribution is the smallest auditable fact unit | MEDIUM | Every assessed Skill relationship resolves to exactly one Contribution; no test fixture can create a Skill assessment directly from an Experience |
| Inspect supplied artifacts before questioning | Questions should test what cannot be established from code, commits, documents, deployments, or other evidence instead of asking the user to restate inspectable facts | MEDIUM | Audit trace records which artifacts were inspected and why each remaining question was necessary; an artifact-answerable golden question is rejected |
| Ask one focused question per turn and preserve resumable Q/A state | A deep audit needs usable pacing, non-repetition, and an inspectable reasoning trail | MEDIUM | Every audit turn contains at most one decision-bearing question; interrupted STOA audits resume without losing prior questions, answers, or extracted facts; repeated-question fixture fails |
| Challenge vague claims with concrete implementation, explanation, reproduction, defense, debugging, or operating probes | “Worked on X” is not evidence of capability | HIGH | Each audited Contribution reaches an explicit supported capability boundary or is marked unresolved/provisional; vague language alone never creates a mastery claim |
| Separate the user’s work, team/other-person work, non-responsibilities, Codex-assisted work, and third-party work | Responsibility attribution is necessary for truthful assessment | HIGH | Attribution fixtures classify mixed-person statements correctly; changing a Contribution from user-owned to assisted/other-owned changes its admissible assessment; no borrowed responsibility supports user mastery |
| Extract specific Skills only after grounding them in an audited Contribution | Credentials, titles, repositories, and ontology edges do not establish mastery | MEDIUM | Every extracted Skill has a Contribution link and an assessment basis; a skill mentioned only in an Experience title, résumé list, or repository dependency remains unassessed |
| Preserve the three separate Contribution–Skill signals | `demonstrated_mastery`, `skill_centrality`, and `evidence_confidence` answer different questions | MEDIUM | Schema requires all three 0–100 values plus context, duration, and assessment basis; fixtures prove that high confidence or high centrality can coexist with low mastery |
| Use the agreed observable mastery anchors | A 0–100 number without capability semantics cannot be calibrated | HIGH | Human reviewers can point to the observable anchor condition supporting the assigned band; no assessment enters a higher band without evidence for that band’s behavior |
| Aggregate Contribution evidence into one relatively stable user score per specific Skill without quantity inflation | The project needs a reusable Skill graph, not a pile of relationship scores | HIGH | Duplicating or adding incidental low-level Contributions does not move a Skill into a higher anchor band; a multi-context increase is allowed only when the combined evidence visibly satisfies the higher anchor |
| Keep mastery separate from confidence, duration, recency, context, and JD match | The same user capability must not change meaning with documentation volume or target role | HIGH | Re-running the same graph against different JDs leaves mastery unchanged while match, relevance, and selected evidence can change |
| Parse a small representative JD set into structured Skill expectations | Usefulness cannot be tested against unstructured keyword counts alone | MEDIUM | Each JD fixture records required/preferred status, expected capability or responsibility where stated, context, and source text span; reviewers can trace every expectation to the JD |
| Produce evidence-bearing JD comparisons | The graph must explain supported, partial, unsupported, and uncertain matches | MEDIUM | Every comparison result cites relevant Contribution–Skill assessments and keeps confidence visible; unsupported keywords cannot become positive matches |
| Preserve a versioned audit and calibration record | Non-deterministic assessments need reproducible inputs, outputs, and review history | MEDIUM | Each run records fixture version, prompt/model/config version, upstream baseline, structured output, reviewer decision, disagreement, and adjudication without overwriting prior runs |
| Run deterministic, golden-case, adversarial, repeated-run, and human-review evaluation | A passing happy path does not establish reliability | HIGH | Known-good and known-bad fixtures both behave as designed; all structural invariants pass; repeated runs remain within the accepted stability envelope; human adjudication is complete before the hypothesis is accepted |

### Hypothesis-Testing Differentiators

These are not general polish. They are the behaviors that make this system different from a résumé parser, self-rating tool, ontology browser, or keyword matcher.

| Differentiator | Value proposition | Complexity | Observable proof |
|---|---|---:|---|
| Contribution-first grilling that finds the user’s capability boundary | Converts a career claim into a defensible statement of what the user can independently explain, implement, reproduce, defend, debug, or operate | HIGH | For each selected STOA Contribution, the audit produces both a strongest-supported capability statement and a next-higher capability claim that was not established |
| Evidence sensitivity rather than evidence theater | Artifact quantity should not masquerade as capability; evidence changes credibility only where it supports responsibility and performance | HIGH | Removing decisive evidence lowers confidence or makes the assessment provisional; adding irrelevant files or duplicate evidence does not raise mastery |
| Explicit separation of mastery, centrality, and confidence | Prevents “important to the project,” “well documented,” and “high skill” from collapsing into one opaque score | MEDIUM | Counterexample fixtures cover high-centrality/low-mastery, low-centrality/high-mastery, and high-mastery/low-confidence cases and retain the distinctions end-to-end |
| Anchor-aware cross-Contribution aggregation | Repeated advanced responsibility can establish a higher band, while many weak uses cannot | HIGH | A multi-context golden case advances only when the collection demonstrates the higher anchor; a numerical pile-up case remains at the lower band |
| Stable capability with JD-specific relevance | Makes one reusable graph useful for multiple target roles | MEDIUM | Across at least three meaningfully different JD fixtures, mastery stays fixed while the comparison selects different Contributions, explains different gaps, and changes match judgments |
| Capability-based comparison that beats a flat keyword baseline | Demonstrates actual career usefulness, not merely graph correctness | HIGH | In blinded human review, graph-based comparison is preferred to or materially corrects the flat keyword baseline on a pre-registered majority of JD cases, with zero critical fabricated capability claims |
| Calibratable explanations and explicit disagreement | Turns human review into model improvement evidence rather than an informal thumbs-up | MEDIUM | Reviewers independently label assessment basis, anchor fit, confidence, and JD usefulness; disagreements are categorized and adjudicated; calibration changes are versioned and re-run against all golden cases |

## Observable Core-Hypothesis Acceptance Gates

The milestone should be accepted only if all gates pass. Numeric tolerances for agreement and score variance should be pre-registered after a small pilot, not chosen after viewing final results.

### Gate 1 — Structural integrity

- 100% of Contribution–Skill assessments contain a valid `contribution_id`, `skill_id`, the three separate scores, context, duration, and explicit assessment basis.
- 0 Skill assessments originate solely from Experience metadata, credentials, repository presence, ontology implication, or JD keywords.
- 0 user-mastery claims rely on work attributed to another person or an unqualified automation/tool contribution.
- All values validate against the agreed schema and all source links resolve within the fixture.

### Gate 2 — Audit quality on STOA

- Every selected STOA Contribution has a reviewed responsibility boundary and at least one inspected or user-supplied evidence item, or is explicitly marked as lacking evidence.
- Every Grill-Me conclusion states what capability was established, what was not established, and why.
- No audit asks multiple decision-bearing questions in one turn, repeats an already answered question, or asks for a fact already available in inspected artifacts.
- A human reviewer can reconstruct each assessment from the preserved Q/A and evidence without relying on hidden chain-of-thought.

### Gate 3 — Score semantics

- High evidence confidence never automatically produces high mastery.
- High Skill centrality never automatically produces high mastery.
- Weak confidence keeps a high-mastery judgment provisional rather than silently lowering or legitimizing it.
- Duplicate and incidental-Contribution counterfactuals never cross a higher mastery anchor.
- A combined-Contribution case crosses a band only when reviewers agree the combined observable behavior satisfies that higher anchor.

### Gate 4 — Reliability and calibration

- Run each critical golden and adversarial case at least three times under the same versioned configuration.
- The supported mastery band remains stable across repeated runs; any material variance is surfaced rather than averaged away.
- Known-bad cases are rejected, including borrowed responsibility, unsupported skill inference, duplicate-evidence inflation, high-confidence/low-mastery confusion, and prompt-injected evidence.
- At least two human review passes are completed for ambiguous or high-impact assessments. Reviewer disagreement is preserved, categorized, and adjudicated; the LLM is not the final arbiter.
- Calibration changes improve or preserve all previously passing golden cases; regressions block acceptance.

### Gate 5 — JD usefulness

- Use a small but contrasting JD set, recommended minimum three: one closely aligned with STOA, one adjacent role, and one role containing attractive but unsupported requirements.
- Changing only the JD changes relevance, evidence selection, and gap explanation, but never the underlying user mastery score.
- Every positive match identifies the concrete Contributions and assessment basis that support it; every partial/unsupported match explains the missing capability or evidence.
- A blinded reviewer compares the graph-based output with a simple flat résumé/keyword baseline using a fixed rubric: relevance, truthfulness, decision usefulness, and traceability.
- The graph-based result must win or materially correct the baseline on a pre-registered majority of cases and must produce zero critical fabrications. A tie on relevance is acceptable only if traceability or gap accuracy is materially better.

### Gate 6 — Decision outcome

The hypothesis is **supported** only if the graph is both reliable enough to calibrate and useful for JD decisions. It is:

- **supported** when all structural, truthfulness, counterfactual, calibration, and usefulness gates pass;
- **partially supported** when Contribution auditing is reliable but JD usefulness is not yet better than the baseline, or vice versa; and
- **rejected for expansion** when assessments cannot be traced, repeated, responsibility-separated, or kept semantically stable.

No résumé-generation or Gap Sprint phase should begin merely because the data model or demo UI works.

## Later Product Milestones — Visible but Deferred

| Later feature | Product role | Dependency on this validation | Why deferred |
|---|---|---|---|
| Dynamic JD-tailored résumé generation | **Core final-product output:** select the most relevant Experiences/Contributions and truthfully rewrite them for each JD | Stable Skill graph, evidence-backed JD comparison, provenance-preserving selection | Building narrative generation before validating assessment usefulness risks optimizing polished output over truth |
| Tailored résumé human review, diff, layouts, and PDF/DOCX export | Lets the user inspect changes and produce an application artifact | Truthful dynamic résumé generation | Presentation and export do not test the current hypothesis |
| Evidence-producing Gap Sprints | Converts reachable gaps into bounded work that can create new evidence | Reliable gap identification and anchor semantics | A gap plan is unsafe if the baseline assessment is not calibrated |
| Post-sprint Grill-Me and graph reassessment | Closes the learn/build/evidence loop | Gap Sprint artifacts plus stable versioned reassessment | Requires longitudinal comparison beyond the initial STOA validation |
| Broader career ingestion | Adds employment, projects, research, publications, education, teaching, open source, internships, and other Experiences | Proven model and scalable ingestion contracts | Entire-career modeling inflates fixture and review scope |
| Large ontology adapter and normalization coverage | Improves aliases, concepts, domains, tasks, and cross-source interoperability | Stable internal Skill semantics | Ontology coverage must not define or propagate user mastery |
| Persistent multi-cycle career workspace | Stores current state, historical snapshots, reviews, gaps, work artifacts, and progress | Proven artifacts and versioning rules | Current milestone needs only a minimal reproducible validation record |
| Multi-user product UI and accounts | Makes the workflow usable as a service | Stable workflow and privacy/security design | A complex frontend does not validate the assessment hypothesis |

## Anti-Features and Explicit Exclusions

| Anti-feature / exclusion | Why it is tempting | Why it is harmful now | Required alternative |
|---|---|---|---|
| Full résumé compiler in this milestone | Produces a visible, impressive demo | Expands scope and can hide weak assessment behind good prose | Emit structured JD comparison and selected evidence only; keep résumé generation as the next core product output |
| Experience-, credential-, title-, or repository-level mastery inference | Fast and easy to automate | Confuses association with demonstrated capability | Require an audited Contribution and explicit assessment basis |
| Keyword match percentage as the success metric | Easy to compute and familiar from résumé tools | Measures textual overlap, not capability, truthfulness, centrality, or confidence | Compare structured JD expectations with assessed Skills and cite Contributions |
| Ontology `impliesKnowingSkills` propagation into user mastery | Rapidly fills the graph | Creates unsupported capability claims | Use ontology relations only for normalization/discovery; independently assess every user Skill |
| One composite “skill score” mixing mastery, evidence, duration, relevance, and recency | Produces a single sortable number | Makes the score target-dependent and uninterpretable | Keep user mastery stable and expose other signals separately |
| Arithmetic accumulation into expert bands | Makes aggregation straightforward | Many weak uses can manufacture expertise | Use anchor-aware aggregation with explicit higher-band evidence |
| Opaque LLM final scores | Reduces implementation effort | Cannot be calibrated, audited, or defended | Store structured assessment basis, evidence links, version, counterfactual tests, and human review |
| GitHub activity or artifact volume as privileged proof | Appears objective and plentiful | Activity may be team-owned, generated, irrelevant, or not representative of understanding | Inspect artifacts as supporting evidence and verify ownership/capability through Contribution grilling |
| Freezing the final formula before fixtures | Creates premature decisiveness | Encodes untested assumptions and encourages tuning to the first example | Validate candidate rules against golden and adversarial cases; version calibration decisions |
| Graph database, large-scale ontology ingestion, or event-driven infrastructure | Sounds architecturally aligned with a “graph product” | Adds operational complexity before the internal model is stable | Use the smallest inspectable local representation that supports tests |
| Automated applications, recruiter tooling, job-site automation, application tracker, cover letters, or generic interview prep | Adjacent to résumé products | Unrelated to the first hypothesis and distracts from assessment validity | Keep explicitly outside this project |

## Feature Dependencies

```text
[Pinned provenance baseline]
          │
          ├──> [STOA Experience/Contribution/Evidence fixture]
          │             │
          │             ├──> [artifact inspection]
          │             └──> [responsibility attribution]
          │                           │
          └───────────────────────────┴──> [one-question Contribution Grill-Me]
                                                   │
                                                   └──> [Contribution–Skill assessment]
                                                              │
                                  [mastery anchors] ───────────┤
                                                              └──> [stable user Skill aggregation]
                                                                          │
[small structured JD fixtures] ────────────────────────────────────────────┤
                                                                          └──> [evidence-bearing JD comparison]
                                                                                      │
[golden/adversarial fixtures + human calibration] ────────────────────────────────────┘
                                                                                      │
                                                                                      └──> [core-hypothesis decision]
                                                                                                │
                                                                                                ├──> [dynamic tailored résumé]
                                                                                                └──> [Gap Sprint loop]
```

### Dependency Notes

- **Artifact inspection and responsibility attribution precede mastery judgment:** otherwise the audit can reward facts already visible in files or work performed by others.
- **Contribution–Skill assessments precede user aggregation:** direct Experience-to-Skill aggregation violates the project model.
- **Mastery anchors precede aggregation:** the aggregation rule must implement capability semantics, not invent them.
- **Structured JDs and stable user Skills are independent inputs:** JD parsing must not mutate the capability record.
- **Human calibration is part of validation, not a post-launch enhancement:** the project cannot accept its own automated labels as ground truth.
- **Dynamic résumé generation and Gap Sprints depend on a supported hypothesis:** both are downstream consumers of the graph and should not be used to prove it retrospectively.

## Validation MVP Definition

### Launch With

- [ ] One representative STOA Experience decomposed into enough distinct Contributions to exercise different responsibility, mastery, centrality, and confidence cases.
- [ ] Artifact-aware, one-question-at-a-time Contribution Grill-Me with resumable Q/A history.
- [ ] Explicit attribution for user, team/other-person, assisted, and third-party work.
- [ ] Structured Contribution–Skill assessments with context, duration, and assessment basis.
- [ ] Anchor-aware user Skill aggregation with anti-inflation counterfactuals.
- [ ] A small, contrasting structured JD fixture set and evidence-bearing comparisons.
- [ ] Deterministic invariants, golden good/bad cases, adversarial cases, three-run stability checks, and documented human calibration.
- [ ] A baseline comparison showing whether the graph improves JD decisions over flat keyword matching.

### Add After Validation

- [ ] Dynamic JD-tailored résumé generation — first downstream product phase after assessment usefulness is supported.
- [ ] Provenance-preserving résumé review/diff and export — add after truthful narrative selection and rewriting work.
- [ ] Gap Sprint generation and reassessment — add after gap judgments are calibrated.
- [ ] Additional Experience types and larger JD coverage — add when new cases expose a model limitation, not for completeness theater.

### Future Consideration

- [ ] Large ontology ingestion and richer graph relations.
- [ ] Multi-user SaaS, account system, and complex interactive UI.
- [ ] Full longitudinal career workspace and progress views.

## Prioritization Matrix

| Feature | Validation value | Implementation cost | Priority |
|---|---:|---:|---:|
| STOA Contribution/Evidence fixture | HIGH | MEDIUM | P1 |
| Artifact-aware Contribution Grill-Me | HIGH | HIGH | P1 |
| Responsibility attribution | HIGH | HIGH | P1 |
| Structured Contribution–Skill assessment | HIGH | MEDIUM | P1 |
| Anchor-aware aggregation and anti-inflation tests | HIGH | HIGH | P1 |
| Structured small-JD comparison | HIGH | MEDIUM | P1 |
| Golden/adversarial/repeated-run/human calibration harness | HIGH | HIGH | P1 |
| Blinded comparison against keyword baseline | HIGH | MEDIUM | P1 |
| Dynamic JD-tailored résumé generation | HIGH final-product value, LOW current validation value | HIGH | P2 |
| Gap Sprint and reassessment | HIGH final-product value, LOW current validation value | HIGH | P2 |
| Export/templates/UI polish | MEDIUM | HIGH | P3 |
| Large ontology or graph infrastructure | LOW now | HIGH | P3 |

## Exact Upstream Precedents

| Category | Upstream precedent | What to adapt | What not to inherit |
|---|---|---|---|
| One-question grilling | `references/upstream/mattpocock-skills/skills/productivity/grilling/SKILL.md` | One question at a time; inspect the environment for facts; let the human decide unresolved judgments | Generic planning-interview semantics or an unstructured transcript as the data model |
| Responsibility boundaries | `references/upstream/tabiya-compass/backend/app/agent/experience/experience_entity.py` and `.../skill_explorer_agent/_responsibilities_extraction_tool.py` | Separate responsibilities, non-responsibilities, and other people’s responsibilities | Treat responsibilities as equivalent to Skills or mastery |
| Attribution fixtures | `references/upstream/tabiya-compass/backend/evaluation_tests/skill_explorer_agent/_responsibilities_extraction_tool_test.py` | Known-answer cases for mixed pronouns, manager decisions, and other-person work; repeated LLM evaluation | The upstream’s broad experience-level granularity |
| Resumable interview state | `references/upstream/tabiya-compass/backend/app/agent/skill_explorer_agent/skill_explorer_agent.py` | Preserve questions, answers, explored units, and resumable state | Experience-level Q/A as a substitute for Contribution audit records |
| Coverage and stopping | `references/upstream/tabiya-compass/backend/app/agent/skill_explorer_agent/_conversation_llm.py` | Skip covered topics, avoid repeat questions, clarify contradictions, stop on disengagement | Its deliberate avoidance of deep specifics; this project must probe concrete Contribution capability |
| Structured extraction and role rubrics | `references/upstream/hiring-agent/models.py`, `roles.py`, and `evaluator.py` | Pydantic output contracts, role-specific categories, evidence required for each judgment | LLM-generated résumé scores as calibrated mastery |
| Versioned career workspace | `references/upstream/cv-market-learning-planner/scripts/run_cycle.py` and `scripts/update_progress.py` | Separate current state from history; append reviews; deterministic file preparation | Exercise generation, fixed learning levels, or free-form gap scoring in this milestone |
| JD keyword baseline | `references/upstream/resume-matcher/docs/agent/features/jd-match.md` | Use its keyword extraction/match concept only as a deliberately weak comparison baseline | Match percentage as capability or success |
| Golden and adversarial evaluation | `references/upstream/resume-matcher/apps/backend/tests/evals/golden/cases.py`, `scorers.py`, `test_scorers.py`, and `test_tailoring_eval.py` | Good/bad fixtures, deterministic truthfulness invariants, semantic rubric layer | Letting an LLM judge replace human calibration |
| Later résumé interaction and export | `references/upstream/resume-matcher/docs/agent/features/enrichment.md`, `resume-templates.md`, and builder components | Later: additive review, diff, layouts, export, JD-aware presentation | A flat master résumé or presentation model as the source of truth |

## Competitive/Precedent Comparison

| Capability | Pinned upstream pattern | Limitation for this project | Required project behavior |
|---|---|---|---|
| Experience exploration | Tabiya Compass extracts and classifies responsibilities from resumable conversation | Experience-level and occupation/skill linking do not establish mastery | Audit distinguishable Contributions and assess each Skill relationship |
| Relentless clarification | Matt Pocock Skills asks one question at a time and inspects artifacts first | Produces shared understanding, not a career evidence model | Persist structured assessment entities and observable capability boundaries |
| Career-gap planning | CV Market Learning Planner compares CV evidence with market demand and preserves history | CV-level evidence and planning artifacts are too coarse for current truth claims | Ground every gap in calibrated Skill evidence and Contribution assessments |
| Role scoring | Hiring Agent uses structured, evidence-bearing role rubrics | Final LLM scores are not a validated user mastery model | Keep stable mastery separate from role/JD match and require human calibration |
| JD matching/tailoring | Resume Matcher highlights keywords and tests truthful tailoring with golden cases | Keyword coverage is not capability; tailoring is downstream | Use keywords only as baseline; compare structured expectations with assessed capability |

## Human Review and Calibration Contract

- Human review is mandatory for ambiguous, high-band, low-confidence, responsibility-disputed, and hypothesis-decision cases.
- Reviewers see source Evidence, audit Q/A, structured assessments, and anchor definitions; they do not need hidden model reasoning.
- Review dimensions are separate: responsibility correctness, Skill specificity, mastery-anchor fit, centrality, evidence confidence, aggregation validity, and JD usefulness.
- Reviewers first judge independently. Disagreements are recorded before adjudication to expose ambiguous rubrics and unstable cases.
- Calibration changes are versioned and re-run against the full golden/adversarial set.
- An LLM judge may triage or apply a rubric, but it cannot be the sole reference label for the same system’s assessment quality.

## Research Gaps to Resolve During Planning

- Select the exact STOA Contributions and evidence artifacts that span enough assessment cases without expanding into full career modeling.
- Pilot the review rubric, then pre-register acceptable reviewer agreement and repeated-run variance thresholds.
- Decide the minimum internal Skill normalization needed for the JD set; defer broad ontology coverage.
- Define a simple flat keyword/résumé baseline and blinded comparison protocol before seeing final system outputs.
- Decide which aggregation candidates enter calibration; do not freeze the final formula in project initialization.

## Sources

### Pinned project sources — HIGH confidence

- `.planning/PROJECT.md`
- `references/README.md`
- Tabiya Compass at pinned commit `8470bea7f68d0990898f441a12bbb6a261a0ef34`
- Matt Pocock Skills at pinned commit `2ab958093e83e0ec752e6c1c5932da465bf23e0c`
- CV Market Learning Planner at pinned commit `ea507847c7a42a1a54becc853fadd15506479b38`
- Hiring Agent at pinned commit `70fd3ea9aa74d8f76519ec643a99f9871003e70d`
- Resume Matcher at pinned commit `ad7754c8b2c3ecee21314ee0b49b0e07d89e3e09`

### Cross-checks — MEDIUM confidence

- [Human Evaluation of Large Language Models: A Review and Protocol Selection Framework](https://www.mdpi.com/2673-2688/7/5/174) — supports explicit rubrics, calibration, uncertainty, and human adjudication for consequential evaluation.
- [A Survey on Evaluation of Large Language Models](https://doi.org/10.1145/3641289) — supports combining task-specific criteria, automatic checks, and human evaluation rather than relying on one metric.
- [41 CFR § 60-3.15 — Documentation of impact and validity evidence](https://www.law.cornell.edu/cfr/text/41/60-3.15) — cross-check for relating a measured construct to concrete work behavior and documenting validity evidence.

---
*Feature research for the Career Evidence Graph core-hypothesis validation project.*
