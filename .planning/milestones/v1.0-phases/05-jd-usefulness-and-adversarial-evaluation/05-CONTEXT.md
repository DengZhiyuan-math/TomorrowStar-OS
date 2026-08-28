# Phase 5: JD Usefulness and Adversarial Evaluation - Context

**Gathered:** 2026-08-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 5 delivers a private, local, single-user JD comparison workflow. The user supplies one
JD at a time; the system compares it with the complete, already-assessed Skill graph, produces
an honest JD-specific 0-100 match score, explains the evidence and gaps behind that score, and
routes the opportunity to one of three downstream application actions: customized resume,
standard resume, or abandon.

The phase also supplies the smallest development-only evaluation needed to prove that this
workflow runs end to end, preserves the Phase 2-4 truth and custody boundaries, resists the
enumerated adversarial cases, and is more decision-useful than the preregistered baseline. It
does not build a multi-user review product, generate or rewrite resume text, automate job
applications, or claim that the workflow improves interview, offer, or hiring outcomes.

</domain>

<decisions>
## Implementation Decisions

### Single-JD scoring and application routing

- **D-01:** Normal personal use processes one JD at a time, supplied as pasted text or a local
  file, against the user's complete Skill graph. Batch JD comparison is not a Phase 5 user flow.
- **D-02:** Every accepted analysis produces one JD-specific 0-100 match score and one explicit
  route: `customized-resume`, `standard-resume`, or `abandon`. JD match remains separate from
  Skill mastery and cannot mutate any underlying assessment or user-Skill value.
- **D-03:** A missing core hard requirement caps the highest attainable match tier. Numerous
  preferred, incidental, or unrelated strengths cannot fully compensate for that missing core
  requirement.
- **D-04:** The three routing bands use a transparent, configurable, versioned policy. Initial
  thresholds are calibrated against the fixed Phase 5 JD fixtures; every result retains the
  exact policy version, and later threshold changes apply only through a new analysis.
- **D-05:** An evidence-based customization exception requires a rare or distinctive core JD
  requirement to map directly to high-confidence Contribution evidence for the corresponding
  Skill combination. The result must expose that evidence and label the trigger
  `evidence-strong-match`.

### Priority-company routing

- **D-06:** Maintain one private local list of priority companies. Do not add a separate
  persistent role-level priority list.
- **D-07:** Every JD from a priority company enters the customized-resume route regardless of
  its ordinary match tier. The system must still show the honest score, core requirement gaps,
  limitations, and risks; preference changes routing, not capability truth.
- **D-08:** Reports distinguish `evidence-strong-match` from `user-priority-company`. A personal
  preference must never be presented as proof of a strong capability match.
- **D-09:** Priority-company lists are versioned forward-only inputs. Editing the list affects
  future analyses only. Historical reports retain their original score, route, company-list
  version, and reason; explicitly rerunning an old JD creates a new result rather than
  overwriting the old one.

### Match report and Contribution selection

- **D-10:** The report opens with the match score, application route, and concise key reasons,
  followed by the strongest match, the most important core gap, and the reason customization
  was or was not selected.
- **D-11:** Show decision-critical JD requirements by default and allow the full structured
  requirement list to be expanded. Every requirement still retains one of `supported`,
  `partially-supported`, `unsupported`, or `uncertain` in the complete result.
- **D-12:** Positive and partial judgments show a human-readable evidence summary naming the
  relevant Experience, Contribution, established capability, and material limitation. Internal
  identifiers, anchor details, confidence, policy versions, and full lineage remain available
  in expanded technical details rather than dominating the default view.
- **D-13:** The report recommends the Contributions most relevant to a customized resume and
  explains why each was selected. Phase 5 selects truthful source material only; it does not
  draft, rewrite, format, or export resume wording.
- **D-14:** Missing capability, missing evidence, context mismatch, and uncertainty remain
  separate explanations. They must not be collapsed into one generic gap label or treated as
  interchangeable reasons for the same score.

### Minimal development-only evaluation

- **D-15:** The fixed evaluation corpus contains three contrasting JDs that exercise
  evidence-strong customization, ordinary standard-resume routing, and low-match abandonment.
  An unchanged-JD priority-company counterfactual proves that preference can change only the
  route and reason, not the score, requirements, evidence, or user Skill graph.
- **D-16:** Independent human comparison is a one-time development acceptance checkpoint. The
  system produces a fixed review packet for an independent reviewer and records disagreement
  and adjudication as evaluation evidence; this is not a recurring multi-reviewer product
  workflow.
- **D-17:** Stale Skill-graph state, missing lineage, hidden text, prompt injection, or another
  trust-boundary failure blocks both scoring and routing. The system reports the concrete
  problem and requires repair or explicit confirmation followed by a new run; it must not emit
  a best-effort score that appears authoritative.
- **D-18:** Deterministic offline fixture runs must be exactly identical. Optional live-model
  evaluation may show small numeric variation, but the application route, core-requirement
  judgments, and cited evidence must remain stable across at least three runs. Material
  variance is retained and blocks acceptance rather than being averaged away.
- **D-19:** Phase completion establishes that the planned personal workflow and its truth
  guards run as designed and that the fixed evaluation can compare decision usefulness against
  the preregistered baseline. It does not establish real-world application, interview, offer,
  or hiring effectiveness; those require later multi-round job-search evidence.
- **D-20:** Research and planning must not search for, select, copy, or synthesize the three
  real test JDs. The user supplies those JDs only when execution reaches an explicit fixture
  checkpoint. Earlier tasks may define strict input contracts, validation commands, empty
  directories, and test harnesses, but the checkpoint blocks real-fixture execution and any
  completion claim until the user-provided JD files are present and accepted.

### the agent's Discretion

- Exact transparent weighting and initial numeric thresholds, provided required versus
  preferred status is preserved, D-03 cannot be bypassed, all inputs are inspectable, and the
  policy is versioned and fixture-calibrated.
- Exact strict model, file, CLI command, report-envelope, and local workspace names, provided
  the existing Pydantic, immutable-history, source-lineage, and offline-first patterns are
  reused rather than duplicated.
- Exact priority-company name normalization and alias handling, provided ambiguous company
  identity fails closed or requires confirmation and historical input versions remain stable.
- Exact preregistered flat-resume or keyword-baseline packet format, anonymization mechanics,
  and independent-review record layout, provided `EVAL-04` and `EVAL-05` remain development
  acceptance evidence rather than personal product workflow.
- Exact selection count and ordering of recommended Contributions, provided every selection is
  evidence-bearing and the complete structured comparison remains inspectable.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project scope and Phase 5 requirements

- `.planning/PROJECT.md` — Defines the private validation milestone, stable Skill semantics,
  three-way product boundary, and the prohibition on claiming real job-search effectiveness.
- `.planning/REQUIREMENTS.md` — Defines Phase 5 requirements `JD-01` through `JD-04` and
  `EVAL-01` through `EVAL-05`, including structured JD spans, truth-preserving comparison,
  adversarial coverage, repeatability, human review, and baseline comparison.
- `.planning/ROADMAP.md` — Defines the Phase 5 goal, success criteria, dependency on Phase 4,
  and boundary from Phase 6 replication and expansion decisions.
- `.planning/STATE.md` — Records Phase 4 completion and Phase 5 as the current planning focus.

### Locked upstream phase decisions and verified authority

- `.planning/phases/04-contribution-skill-assessment-and-aggregation-calibration/04-CONTEXT.md`
  — Locks specific-Skill assessment, separate mastery/centrality/confidence, no-inflation
  aggregation, substantive review, and versioned policy semantics consumed by JD comparison.
- `.planning/phases/04-contribution-skill-assessment-and-aggregation-calibration/04-VERIFICATION.md`
  — Confirms the admitted assessment and calibrated user-Skill foundations available to this
  phase.
- `.planning/phases/03-artifact-aware-grill-me-and-attribution-workflow/03-CONTEXT.md` — Locks
  Contribution-level audit, ownership/assistance separation, unverified self-rating, and
  conclusion-review semantics that JD comparison must not reinterpret.
- `.planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants/02-CONTEXT.md`
  — Locks Contribution as the minimum auditable unit, documentary proof limits, conflict
  preservation, and single-fault fixture construction.

### Existing implementation and validation assets

- `src/career_evidence_graph/domain/models.py` — Provides strict Skill,
  `ContributionSkillAssessment`, assessment-version, promotion, and
  `CalibratedUserSkillResult` contracts to reference rather than duplicate.
- `src/career_evidence_graph/domain/invariants.py` — Provides exact-Skill, baseline-lineage,
  and mastery-isolation validation patterns that JD comparison must preserve.
- `src/career_evidence_graph/assessment.py` — Provides assessment loading, admission,
  no-inflation aggregation, versioned policy history, and immutable reassessment seams.
- `src/career_evidence_graph/validation/models.py` — Provides frozen extra-forbidding models,
  model/config identity, acceptance state, and formal-run lineage patterns.
- `src/career_evidence_graph/validation/store.py` — Provides immutable formal-run publication,
  full input hashes, rerun lineage, and correction records for development evaluation.
- `src/career_evidence_graph/cli.py` — Provides the existing stdlib `argparse` integration point
  for the smallest local JD analysis and evaluation commands.
- `validation/fixtures/stoa/v1/known-good.json` — Supplies sealed Contribution, Evidence, Skill,
  and assessment fixture lineage; it cannot be reinterpreted from JD wording.
- `validation/calibration/phase-04/policies.json` — Supplies versioned aggregation/admission
  policies whose outputs feed JD comparison without target-dependent mastery mutation.
- `validation/calibration/phase-04/policy-calibration/history.json` — Supplies retained policy
  and result history needed to pin the user-Skill input used by each JD run.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `StrictModel` and the Phase 2-4 domain records provide frozen, extra-forbidding contracts for
  structured JD, comparison, routing-policy, and evaluation records.
- `CalibratedUserSkillResult` already exposes one exact-Skill mastery result with admitted
  assessment lineage, policy version, authority label, and supporting contexts; JD comparison
  should consume it read-only.
- `ContributionSkillAssessment`, `AssessmentVersion`, and `AssessmentSourceEnvelope` already
  retain the Contribution, audit, policy, responsibility, evidence, and effective-version
  custody needed for evidence-bearing positive judgments.
- `FormalRunStore`, `FormalRunManifest`, and `CorrectionRecord` provide immutable input hashes,
  recorded responses, corrections, and linked reruns suitable for the development evaluation
  packet.
- The existing `argparse` CLI and JSON emission/error boundary provide the minimal personal
  local interface without adding an API, database, or web application.

### Established Patterns

- Domain and validation contracts are schema-versioned, frozen, and fail closed on extra,
  stale, corrupt, or lineage-invalid state.
- Mastery is exact-Skill user truth; target-JD relevance is a derived, replaceable result and
  cannot write back into assessment or aggregation stores.
- Policy changes and reruns retain immutable history instead of overwriting old results.
- Default acceptance is deterministic and offline; optional live-model behavior is isolated,
  recorded, and never the sole source of truth.
- Golden and known-bad tests use explicit fixed fixtures and single/counterfactual mutations,
  which can be extended to the three JDs and priority-company route variant.

### Integration Points

- Add one narrow JD comparison module beside `assessment.py`; consume existing calibrated
  user-Skill results and assessment lineage without creating a second Skill or mastery engine.
- Extend `domain/models.py` only with the strict JD requirement, comparison, route, priority
  policy, and evaluation contracts actually required by this phase.
- Extend `cli.py` with the smallest one-JD analysis, inspect, and development-evaluation
  commands; no normal-use reviewer workflow is needed.
- Reuse the validation workspace for fixed JD inputs, versioned comparison policies, repeated
  results, the priority-company counterfactual, and the one-time independent review packet.

</code_context>

<specifics>
## Specific Ideas

- A report header should read like `78/100 · customized resume`, followed by the key reason,
  strongest evidence-backed match, and most important core gap.
- Apple and Google were the user's examples of priority companies whose JDs always receive
  customized-resume treatment, while retaining honest match scores and limitations.
- The three real test JDs are user-supplied evaluation inputs. Planning and research should
  prepare the intake contract and checkpoint, not source substitutes in advance.
- Default reports should be simple and readable; complete lineage and policy details remain
  available through expansion rather than being removed.
- “Worth customizing” is a routing decision for personal effort allocation. It is not a new
  mastery signal and is not evidence that the user is qualified for the role.

</specifics>

<deferred>
## Deferred Ideas

- Actual customized-resume drafting, claim rewriting, review, formatting, and export remain a
  downstream product phase. Phase 5 supplies the route and selected truthful Contributions.
- Measuring whether standard or customized resumes improve applications, interviews, offers,
  or hiring outcomes requires later multi-round real usage; it is not a Phase 5 claim.
- Multi-user accounts, recurring reviewer assignment, reviewer dashboards, and a complex web
  interface are outside this private personal system.

</deferred>

---

*Phase: 5-jd-usefulness-and-adversarial-evaluation*
*Context gathered: 2026-08-28*
