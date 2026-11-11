# Phase 8: Full-Career Inventory Review and Seal - Context

**Gathered:** 2026-09-01
**Status:** Ready for planning

## Current navigation clarification — 2026-10-20

This phase governs reviewable research inventory snapshots. Current application
behavior follows [single-job flow](../../../docs/single-job-flow.md), and remaining
implementation work follows [development plan](../../../docs/development-plan.md).
The decisions and historical verification records below do not require a user to
reseal a complete inventory before correcting or reusing an ordinary career fact.
Save a direct correction with its source and previous value; update only affected
derived results. Research seal acceptance and numeric capability assessment keep
their separate evidence requirements. No ordinary fact correction implies an
accepted Skill score or silently rewrites an earlier accepted research snapshot.

The application workflow is strictly sequential. Important missing facts, actual
conflicts and unknown results wait on the current job; only a user skip moves past
it. New mail may be collected while waiting. These product rules do not claim
that this historical phase plan or the installed App already implements them.

<domain>
## Phase Boundary

Phase 8 converts one Phase 7 source-universe revision into a complete, human-reviewable
Experience inventory. Every declared source and every known career item must receive an explicit
disposition. The user may confirm, edit, add, split, merge, exclude with a reason, or retain an
item as unresolved. The phase produces a coverage report and, only after all dispositions and the
blocking user checkpoint are complete, seals the exact accepted inventory revision.

The inventory covers employment, projects, research, publications, education, teaching, open
source, internships, and related career activity. It identifies real-world Experiences; it does
not yet decompose them into Contributions, audit responsibility or assistance, infer Skills,
admit mastery, compare JDs, or generate resume claims. Repository presence, resume wording,
credentials, and repeated descriptions remain discovery clues rather than capability evidence.

Phase 8 planning may begin from the accepted decisions below. Execution may prepare an unsealed
candidate inventory, but formal sealing remains blocked until the current Phase 7 implementation
has an independent verification result and every Phase 8 candidate has a recorded disposition.

</domain>

<decisions>
## Implementation Decisions

### Experience identity and grouping

- **D-01:** One Experience represents one real-world undertaking, engagement, period of work, or
  educational/research activity. A repository, document, resume entry, or website card is a
  source about an Experience, not automatically an Experience itself.
- **D-02:** Remote and local copies, renamed repositories, related frontend/backend/infra
  repositories, and repeated resume/portfolio descriptions may link to one Experience when the
  sources clearly describe the same undertaking. Preserve every source link and its distinct
  provenance after merging.
- **D-03:** Never auto-merge an ambiguous pair. Present it for user review as separate candidates
  or as an explicit merge proposal. Deduplication cannot erase source identity, conflicting
  descriptions, unavailable-source records, or independent corroboration.

### Inventory granularity and authority

- **D-04:** Phase 8 records Experience candidates without placeholder Contributions. The existing
  final `Experience` contract requires Contribution lineage, so planning must introduce or reuse
  a separate candidate/review contract and materialize contribution-linked Experiences only in
  the downstream audit phase.
- **D-05:** Inventory categories are `employment`, `project`, `research`, `publication`,
  `education`, `teaching`, `open_source`, `internship`, and `related`. Category assignment is for
  coverage and navigation only and has no mastery effect.
- **D-06:** Phase 8 may retain factual fields needed to identify and review an Experience, such as
  title, organization or context, date range, short description, source links, and uncertainty.
  It must not create responsibility, assistance, Contribution, Skill, mastery, confidence, JD
  match, or resume-quality conclusions.

### Candidate discovery and complete reconciliation

- **D-07:** Use resume and personal-website material as high-signal seeds for the initial career
  backbone, then reconcile every row in the Phase 7 source registry. Neither seed source is
  treated as complete or authoritative by itself.
- **D-08:** Every registry source and every discovered career item receives a reviewable
  disposition. Supported outcomes include use in one or more Experience candidates,
  background-only, conflict, exclusion with a reason, unavailable, and explicitly unresolved.
- **D-09:** Coverage reporting must show category coverage, source coverage, candidate coverage,
  unresolved items, conflicts, exclusions, and unavailable sources. Readable personal details
  belong only in the explicitly selected private workspace; public-repository checks and logs
  remain content-free.

### Review, unresolved items, and sealing

- **D-10:** The user may confirm, edit, add, split, merge, exclude with a reason, or retain each
  candidate as explicitly unresolved. Review operations must preserve the candidate revision and
  the source lineage that motivated the decision.
- **D-11:** An explicitly unresolved Experience is a valid inventory-level disposition and may
  remain in an accepted inventory revision. It is visibly unresolved and cannot supply accepted
  research Contribution, Skill, assessment or JD-evaluation conclusions until a later linked
  revision resolves it. Ordinary application material may reuse independently documented facts
  or a direct user correction without inventory acceptance. The unresolved claim itself cannot
  silently become a confirmed résumé claim or an assessed capability.
- **D-12:** Seal only an exact immutable inventory revision after every source and candidate has a
  recorded disposition, the coverage report has no silent omissions, the Phase 7 independent
  verification prerequisite passes, and the user explicitly accepts the blocking checkpoint.
- **D-13:** Later corrections create a linked immutable inventory revision; they never rewrite an
  earlier accepted revision or silently retarget downstream lineage.

### the agent's Discretion

- Exact Pydantic class, field, file, and CLI names for candidate inventory, review decisions,
  coverage, and sealing, provided there is one inventory authority and no placeholder
  Contribution is created.
- Exact deterministic seed-extraction and candidate-proposal heuristics, provided proposals are
  reviewable, preserve source lineage, do not infer mastery, and ambiguous merges remain pending.
- Exact review batching and display order after the resume/personal-site backbone is proposed,
  provided every source and candidate remains reachable and the final checkpoint is complete.
- Exact safe identifier and private report layout, provided public logs and committed public
  artifacts expose no private labels, paths, counts, hashes, or source-derived fingerprints.

</decisions>

<specifics>
## Specific Ideas

- The first review pass should feel like reconciling a complete career ledger, not reviewing a
  list of repositories.
- A multi-repository product or research effort should normally appear once in the inventory,
  with all supporting repositories and documents attached as sources.
- Tutorial, course, fork, experiment, and abandoned-project repositories should not be silently
  promoted into career Experiences; they must still receive a visible source disposition.
- An unresolved item is retained to prevent omission, not treated as a weakly confirmed fact.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and private-source boundary

- `.planning/ROADMAP.md` — Defines Phase 8 goal, dependency, success criteria, blocking user
  checkpoint, and immutable revision behavior.
- `.planning/REQUIREMENTS.md` — Defines INV-02 through INV-05 and the downstream audit,
  assessment, JD, and resume boundaries.
- `.planning/STATE.md` — Records the live Phase 7 verification state and current execution gate.
- `.planning/phases/07-career-source-custody-and-private-workspace/07-CONTEXT.md` — Locks the
  public/private authority boundary, source-universe semantics, immutable captures, and the rule
  that source presence cannot establish mastery.
- `.planning/phases/07-career-source-custody-and-private-workspace/07-12-SUMMARY.md` — Records the
  current private-workspace bootstrap and source-registry handoff that Phase 8 consumes.
- `.planning/phases/07-career-source-custody-and-private-workspace/07-VERIFICATION.md` — Must be
  refreshed against the current Phase 7 implementation before Phase 8 sealing; its current
  historical result is not sufficient for the revised implementation.

### Existing reusable implementation

- `src/career_evidence_graph/domain/models.py` — Defines the final contribution-linked
  `Experience` model and the assessment boundaries Phase 8 must not bypass.
- `src/career_evidence_graph/domain/fixtures.py` — Provides reusable candidate/review,
  source-disposition, correction, exact-hash, and immutable-seal patterns. Its STOA-specific
  schema and claim-level unresolved rule must not be copied as inventory semantics wholesale.
- `src/career_evidence_graph/workspace.py` — Provides the Phase 7 private-workspace and source
  registry boundary that Phase 8 must consume rather than replace.
- `src/career_evidence_graph/validation/hashing.py` — Provides the canonical JSON/hash authority
  for exact candidate, review, coverage, and sealed-revision identities.
- `src/career_evidence_graph/validation/store.py` — Provides create-only, atomic, immutable
  publication and verification patterns.
- `tests/test_stoa_fixture.py` — Demonstrates deterministic review completeness, correction
  preservation, rejection omission, exact sealing, and tamper detection.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- The Phase 7 workspace registry already defines the complete source-universe revision and
  availability records; Phase 8 should consume it without adding another registry.
- `CandidateLedger`, review records, source-section dispositions, canonical hashes, and sealed
  envelopes demonstrate the review-before-materialization pattern needed here.
- Canonical JSON, SHA-256 identity, atomic writes, and create-only bundles already exist and must
  remain the single storage and hashing authority.

### Established Patterns

- Candidate artifacts are untrusted proposals until the user reviews them.
- Every decision retains exact input and review lineage; later corrections produce new immutable
  outputs instead of overwriting prior accepted state.
- Source, title, credential, repository, resume-skill list, and ontology relation cannot directly
  produce mastery.
- Public operations remain content-free; readable career material stays in the explicitly
  selected private workspace.

### Integration Points

- Add a generic full-career candidate inventory seam that consumes the Phase 7 registry and
  capture metadata from the explicit private workspace.
- Reuse the existing candidate/review/seal architecture at the pattern level while keeping the
  STOA fixture authority and the full-career inventory authority separate.
- Phase 9 consumes only accepted, non-excluded Experience entries and must continue to block
  unresolved items from Contribution materialization.

</code_context>

<deferred>
## Deferred Ideas

- Contribution decomposition, personal responsibility and assistance audit, and evidence-claim
  admission — Phase 9.
- Skill normalization, capability examination, mastery/confidence admission, and graph scoring —
  Phase 10 and later assessment work.
- JD comparison, targeted resume generation, interview preparation, and evidence-producing gap
  closure — downstream phases.

</deferred>

---

*Phase: 08-full-career-inventory-review-and-seal*
*Context gathered: 2026-09-01*
