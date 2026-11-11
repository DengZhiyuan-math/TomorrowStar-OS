# Phase 4: Contribution–Skill Assessment and Aggregation Calibration - Context

**Gathered:** 2026-08-27
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase turns confirmed Phase 3 Contribution conclusions into traceable
assessments of specific Skills. The system assigns demonstrated mastery, Skill
centrality, and evidence confidence, admits or withholds those assessments under
a reviewable confidence policy, and produces one versioned user-level mastery
result per specific Skill without rewarding duplicated evidence or mere evidence
volume.

This phase calibrates assessment and aggregation behavior on the existing
validation inputs. It does not compare the user with JDs, generate resumes,
recommend gap-closing work, or claim that the resulting Skill graph improves
application, interview, or hiring outcomes.

</domain>

<decisions>
## Implementation Decisions

### Skill proposal and normalization

- **D-01:** Only a concrete, independently verifiable specific Skill receives an assessment or user-level mastery score. Broad areas such as “backend development” may classify Skills but never receive a mastery score.
- **D-02:** One Contribution may propose every specific Skill it directly supports. Each Contribution–Skill pair is assessed independently and retains its own traceability; the system must not force one primary Skill or create a combined multi-Skill label.
- **D-03:** Deterministic, unambiguous aliases and synonyms may normalize automatically. Ambiguous or unmatched candidates require explicit human confirmation of an existing Skill or creation of a new specific Skill.
- **D-04:** A Phase 3 skip or self-rating may become a formal Phase 4 assessment only after the substantive human confirmation defined in D-10. Its `self-assessed-unverified` origin remains visible permanently; Phase 4 admission must not rewrite history as though Phase 3 verified it.

### System assessment and human correction

- **D-05:** The system directly produces `demonstrated_mastery`, `skill_centrality`, and `evidence_confidence`. Human review is exception-based: a reviewer intervenes when a result is disputed, low-confidence, or otherwise flagged rather than confirming every routine result.
- **D-06:** For demonstrated mastery, the system first identifies the satisfied 0–100 capability anchor, then selects an exact score inside that band and stores the observable basis for both decisions. A bare number without anchor fit is invalid.
- **D-07:** Demonstrated mastery, Skill centrality, and evidence confidence remain independent stored judgments with separate bases. The system may additionally derive one convenience composite for display, but that composite is not mastery, cannot replace the three source dimensions, and cannot drive mastery-anchor promotion opaquely.
- **D-08:** A human correction preserves the original system proposal, the corrected values, the reviewer, and the reason. The corrected assessment becomes the current effective version without overwriting the original proposal.

### Low-confidence admission

- **D-09:** A high-mastery proposal with low evidence confidence is marked `pending-confirmation`, visibly prompts for human review, and remains outside the formal user-level Skill aggregate until confirmed.
- **D-10:** Human confirmation is substantive. The reviewer must inspect the assessment basis, verify responsibility attribution and capability-anchor fit, and explicitly accept or modify all three judgments. A confirmation click without that review is insufficient.
- **D-11:** If the reviewer still finds the basis insufficient, retain the record as an `unverified-candidate` outside the formal aggregate. Inability to verify is not a mastery score of zero, and the candidate is neither deleted nor silently admitted.
- **D-12:** New evidence or a later audit creates a new assessment version and triggers a new confidence/admission decision. Preserve the earlier candidate, its basis, and every prior human decision.

### Multi-Contribution aggregation

- **D-13:** The strongest admitted Contribution–Skill assessment is the baseline for user-level mastery. Other admitted Contributions establish stability and breadth; their scores are not averaged, summed, or converted into automatic volume bonuses.
- **D-14:** Several Contributions may raise user-level mastery above the strongest individual assessment only when their combined credible behavior observably satisfies the next higher mastery anchor. The aggregate must store an explicit cross-Contribution rationale naming the behaviors and admitted assessments that justify promotion.
- **D-15:** One evidence item may support multiple different Skills, with its relevance assessed independently for each Skill. Repeated references to the same evidence within one Skill do not multiply its weight. Relationships are preserved even when duplicate weighting is suppressed.
- **D-16:** Aggregation and confidence-admission policies are versioned. During calibration, the same inputs may be recalculated under a candidate policy and compared with the current policy; activation is explicit, and prior policy results, variance, reviewer decisions, and regressions remain inspectable.

### the agent's Discretion

- Exact replaceable thresholds for `pending-confirmation`, provided D-09 through D-12 hold and the threshold is recorded as policy data rather than hidden in code.
- Exact formulas for Skill centrality, evidence confidence, the convenience composite, and user-level aggregation within the locked separation, no-inflation, and anchor-promotion constraints.
- The internal policy/result envelope, stable identifiers, command names, and report layout, provided lineage, current-effective status, and history remain explicit.
- Whether the system proposal is produced by deterministic rules, a structured model call, or a narrow combination during calibration. Offline deterministic tests and provider isolation remain mandatory.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project scope and Phase 4 contract

- `.planning/PROJECT.md` — Defines the accepted mastery anchors, score separation, Contribution-level grounding, anchor integrity, and validation-only boundary.
- `.planning/REQUIREMENTS.md` — Defines Phase 4 requirements `ASS-01` through `ASS-04` and `AGG-01` through `AGG-04`.
- `.planning/ROADMAP.md` — Defines the Phase 4 goal, success criteria, dependency on Phase 3, and boundary from Phase 5.
- `.planning/STATE.md` — Records Phase 4 as the current planning focus and preserves the replaceable-policy calibration concern.

### Prior phase decisions and accepted inputs

- `.planning/phases/01-validation-charter-provenance-and-technical-decision-gate/01-CONTEXT.md` — Locks the falsifiable validation boundary, immutable proposal/correction lineage, and deterministic/offline default.
- `.planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants/02-CONTEXT.md` — Locks specific-Skill semantics, Contribution grounding, documentary proof limits, and Phase 4 score deferral.
- `.planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants/02-VALIDATION.md` — Defines the deterministic fixture and invariant validation baseline inherited by this phase.
- `.planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants/02-VERIFICATION.md` — Confirms what the sealed STOA fixture and domain invariants establish and what they do not establish.
- `.planning/phases/03-artifact-aware-grill-me-and-attribution-workflow/03-CONTEXT.md` — Defines confirmed capability boundaries, skip/self-rating provenance, attribution, and the handoff into Phase 4.
- `.planning/phases/03-artifact-aware-grill-me-and-attribution-workflow/03-VALIDATION.md` — Defines accepted Phase 3 audit journeys and offline validation evidence.
- `.planning/phases/03-artifact-aware-grill-me-and-attribution-workflow/03-VERIFICATION.md` — Confirms the completed audit behavior and the unchanged revision available to Phase 4.

### STOA calibration input

- `validation/fixtures/stoa/v1/known-good.json` — Sealed STOA truth fixture; its assessment and user-Skill collections are intentionally empty and make no calibration claim.
- `validation/fixtures/stoa/v1/source-manifest.json` — Pinned source scope and hashes behind the STOA evidence graph.
- `validation/fixtures/stoa/v1/review.json` — Human fixture decisions that remain distinct from capability and mastery review.

### Existing implementation contracts

- `src/career_evidence_graph/domain/models.py` — Contains `SkillNormalizationRecord`, `ContributionSkillAssessment`, `AssessmentLineage`, and the Phase 2 fixture-only `UserSkillView` that Phase 4 must evolve rather than duplicate.
- `src/career_evidence_graph/domain/invariants.py` — Contains Contribution lineage, duplicate evidence-link, attribution, one-view-per-Skill, and mastery-isolation checks that must be retained or deliberately evolved.
- `src/career_evidence_graph/audit/models.py` — Contains Phase 3 `AuditConclusion`, verification provenance, immutable original proposals, ordered review lineage, responsibility, and assistance boundaries consumed by assessment.
- `src/career_evidence_graph/validation/models.py` — Provides strict schema-versioned proposal/correction and run-record patterns.
- `src/career_evidence_graph/validation/hashing.py` — Provides canonical content hashing used by existing immutable lineage.
- `src/career_evidence_graph/codex_cli.py` — Provides the optional structured coding-agent execution seam while leaving model/provider choice outside the domain.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `SkillNormalizationRecord` already distinguishes deterministic matches, review-required candidates, unmatched names, and descriptive-only ontology relations; extend this path instead of creating another normalizer.
- `ContributionSkillAssessment` already stores the three separate 0–100 judgments, Contribution lineage, context, duration, basis claims, and review status. Phase 4 should evolve its status, anchor basis, audit-conclusion lineage, and version history rather than introduce a parallel assessment model.
- `AuditConclusion`, `ConclusionEntry`, and `ConclusionReview` already preserve `audit-verified`, `self-assessed-unverified`, and unresolved provenance plus immutable proposal/review history. These are the assessment admission inputs.
- `UserSkillView` and `validate_user_skill_views` already establish one view per exact Skill and trace it to same-Skill assessment IDs. Its current `fixture-test-expectation` marker is explicitly non-calibrated and requires a Phase 4 policy-bearing evolution.

### Established Patterns

- Strict Pydantic contracts are frozen, schema-versioned, and fail closed on extra fields.
- Documents, credentials, repository presence, and ontology relations never establish mastery by themselves; Phase 3 audit conclusions and Phase 4 human admission retain authority.
- Original proposals, human corrections, current-effective results, and policy/run lineage remain distinct and inspectable.
- Duplicate links are rejected without discarding legitimate many-to-many Evidence relationships.
- Default validation remains deterministic and offline; any structured model call is opt-in, isolated behind the existing adapter, and recorded.

### Integration Points

- Consume only completed, reviewable Phase 3 audit snapshots and their conclusion lineage; do not infer a Skill score directly from the Experience, repository, title, credential, or ontology.
- Reconcile the Phase 2 invariant that currently rejects any assisted reviewed claim with Phase 3's provider-neutral rule that coding-agent assistance neither proves nor automatically disqualifies capability. Admission must depend on audited user understanding and responsibility boundaries.
- Preserve backward loading of the sealed Phase 2 STOA fixture while adding calibrated assessment, admission, policy, review, and aggregate result contracts.
- Add the smallest CLI/report surface needed to propose assessments, inspect pending candidates, record corrections or confirmations, compare policy versions, and inspect one traceable user-level result per Skill.

</code_context>

<specifics>
## Specific Ideas

- The convenience composite exists because the user prefers a simpler overview, but the three underlying judgments remain visible and authoritative.
- A high-level evidence item may legitimately support several Skills. The user's example was a mathematics PhD supporting probability, mathematics, numerical analysis, and statistics. The system should assess relevance independently per Skill, not restrict the evidence to one Skill.
- `pending-confirmation` must be an explicit user-visible state with a direct request for human confirmation, not merely a low confidence number hidden in a record.

</specifics>

<deferred>
## Deferred Ideas

- Structured JD requirements, JD relevance, gaps, and JD usefulness evaluation belong to Phase 5.
- Resume selection, rewriting, review, export, and evidence-producing gap work remain downstream product capabilities.
- Whether the system improves real application, interview, or hiring outcomes requires later multi-round empirical use and is not a Phase 4 completion claim.

</deferred>

---

*Phase: 4-contribution-skill-assessment-and-aggregation-calibration*
*Context gathered: 2026-08-27*
