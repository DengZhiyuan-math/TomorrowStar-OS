# Phase 2: Domain Contracts, STOA Fixture, and Deterministic Invariants - Context

**Gathered:** 2026-07-30
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers strict, schema-versioned domain contracts for `Experience`,
`Contribution`, `Evidence`, `Skill`, `ContributionSkillAssessment`, and the
separate user-Skill view; a human-reviewed STOA fixture covering all major
documented outcomes inside one Experience; and deterministic known-good and
single-fault known-bad cases that reject invalid or unsupported assessment
states.

The phase proves that the intended data and invariant chain can run correctly.
It does not perform the Phase 3 Grill-Me interview, calibrate the Phase 4
aggregation formula, compare JDs, generate résumés, or make claims about product,
application, interview, or hiring effectiveness.

</domain>

<decisions>
## Implementation Decisions

### STOA material sources

- **D-01:** Build candidate STOA facts only from Git-tracked development plans, handoffs, acceptance records, audit reports, and related project documentation in `stoa-backend`, `stoa-frontend`, `stoa-infra`, and `stoa-docs`. Do not inspect implementation code to extract the fixture.
- **D-02:** Pin the source snapshot to the current recorded HEAD of all four repositories:
  - `stoa-backend` — `84e93dae35dfde2c2e07fac6faf714b2d61c8377`
  - `stoa-frontend` — `42955a9ed38cfca868febffa752459ec27a88a30`
  - `stoa-infra` — `6d545ad8cae8d2fe67087f298d9d5fc7cc29b3f6`
  - `stoa-docs` — `53c91971572a52bf4bfdc68aebd8393f3080a76d`
- **D-03:** Exclude secrets, production or user data, caches, untracked files, and any other private operational material from fixture extraction.
- **D-04:** Repository documents may propose candidate project facts, but they cannot by themselves establish the user's personal responsibility, independent capability, or mastery. Those remain unconfirmed until human review.

### Contribution boundaries

- **D-05:** Represent STOA as one `Experience` containing all major documented outcomes, rather than selecting a small showcase subset.
- **D-06:** Define each `Contribution` as one independently explainable and auditable work outcome. A Contribution may span repositories when several components jointly deliver the same durable outcome.
- **D-07:** Consolidate development phases by durable product or system outcome. Do not create one Contribution per repository, commit, ticket, or development phase.
- **D-08:** Delivered and partially delivered outcomes may become Contributions, but every limitation must be preserved. Planned-only work remains background context and cannot generate a Skill or mastery assessment.

### Evidence and responsibility attribution

- **D-09:** Attribute each concrete work claim within a Contribution independently. A single Contribution may therefore contain user, team, other-person, non-responsibility, Codex-assisted, and third-party claims.
- **D-10:** Give each Evidence type an explicit proof limit:
  - plans establish intent or assignment, not completion;
  - handoffs and acceptance records establish recorded delivery;
  - audits establish observed state, defects, and limitations;
  - user confirmation establishes personal responsibility and claimed capability for fixture purposes.
- **D-11:** Store an Evidence item once and link it to one or more specific claims using section-level locators. Repeated links to the same source never count as independent Evidence.
- **D-12:** Preserve conflicting sources instead of silently choosing a winner. Mark the affected claim partial or unresolved, and prohibit a definite mastery conclusion until it is reviewed.

### Known-good and known-bad fixture generation

- **D-13:** The system drafts candidate facts from the selected documents; the user accepts, edits, or rejects each candidate. Only the resulting confirmed record may be labeled known-good.
- **D-14:** Confirm outcome facts, responsibility attribution, Evidence links, completion status, and limitations separately. Seal the known-good fixture only after every item is resolved or explicitly retained as unresolved.
- **D-15:** Derive each known-bad fixture from the confirmed known-good base and deliberately violate exactly one invariant. Record the base fixture and mutation so every expected rejection has one deterministic cause.
- **D-16:** Phase 2 fixture scores are human-confirmed test values or ranges used to exercise contracts and invariants. They are not calibrated real-world capability scores and must not imply that Phase 4 aggregation policy has been selected.
- **D-17:** Known-bad coverage must include, at minimum, direct mastery from an Experience/title/repository/résumé/ontology, wrong or obscured responsibility, duplicate Evidence inflation, missing lineage or assessment basis, dimension confusion, out-of-range values, and ontology-driven mastery changes.

### the agent's Discretion

- Exact class and field names beyond the locked semantic entities.
- Exact file layout for fixture source manifests, candidate-review records, sealed known-good data, and single-fault mutations.
- Exact deterministic IDs and locator syntax, provided they are stable, inspectable, and validated.
- Which additional negative cases are useful beyond the minimum classes, provided each case still violates only one rule.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project scope and Phase 2 requirements

- `.planning/PROJECT.md` — Defines the validation-only product boundary, accepted domain relationships, score separation, mastery anchors, and deferred aggregation policy.
- `.planning/REQUIREMENTS.md` — Defines the Phase 2 contracts and fixture requirements `MOD-01` through `MOD-07`, `FIX-01`, and `FIX-02`.
- `.planning/ROADMAP.md` — Defines the Phase 2 goal, success criteria, dependencies, and boundaries relative to Phases 3–6.
- `.planning/STATE.md` — Records Phase 1 completion and Phase 2 as the current planning focus.
- `.planning/phases/01-validation-charter-provenance-and-technical-decision-gate/01-CONTEXT.md` — Locks the functional-chain-only claim boundary and the future STOA review/replay requirement.
- `.planning/phases/01-validation-charter-provenance-and-technical-decision-gate/01-VALIDATION.md` — Defines validation strategy and deterministic evidence expectations inherited by this phase.
- `.planning/phases/01-validation-charter-provenance-and-technical-decision-gate/01-VERIFICATION.md` — Confirms the immutable run, exact replay, provenance, and fail-closed foundations available to Phase 2.

### Existing validation implementation

- `src/career_evidence_graph/validation/models.py` — Provides frozen, extra-forbidding Pydantic v2 contract patterns and the existing formal-run schemas.
- `src/career_evidence_graph/validation/store.py` — Provides atomic immutable bundle publication, complete input hashing, ancestry verification, and correction records.
- `src/career_evidence_graph/validation/replay.py` — Provides exact recorded-response replay against confirmed expectations.
- `src/career_evidence_graph/validation/provenance.py` — Provides fail-closed machine and human provenance validation.
- `tests/test_charter.py` — Demonstrates strict contract and prohibited-claim testing.
- `tests/test_run_store.py` — Demonstrates immutable run and lineage tests.
- `tests/test_replay.py` — Demonstrates deterministic replay tests.
- `tests/test_security_boundaries.py` — Demonstrates independent negative-case blockers and hostile-input boundaries.

### STOA backend documentation

- `/Users/zhdeng/stoa-backend@84e93dae35dfde2c2e07fac6faf714b2d61c8377` — Pinned backend repository snapshot; documentation is evidence input, not proof of personal ownership.
- `/Users/zhdeng/stoa-backend/docs/audit/full-project-audit.md` — Broad project audit; its internal-alpha and non-production-ready limitations must be retained.
- `/Users/zhdeng/stoa-backend/docs/build-week-2026/BUILD-WEEK-EVIDENCE.md` — Recorded Build Week delivery evidence and outcome candidates.
- `/Users/zhdeng/stoa-backend/docs/build-week-2026/OWNER-HANDOFF.zh-CN.md` — Owner handoff statements and responsibility candidates subject to user confirmation.

### STOA frontend documentation

- `/Users/zhdeng/stoa-frontend@42955a9ed38cfca868febffa752459ec27a88a30` — Pinned frontend repository snapshot; documentation is evidence input, not proof of personal ownership.
- `/Users/zhdeng/stoa-frontend/docs/qa/development-artifact-audit.md` — Frontend development artifact audit and observed limitations.
- `/Users/zhdeng/stoa-frontend/docs/production/production-readiness.md` — Production-readiness status; incomplete readiness must remain explicit.
- `/Users/zhdeng/stoa-frontend/docs/release/next-stage-backlog.md` — Planned-only and next-stage work that must not be converted into delivered Contributions.

### STOA architecture, deployment, and infrastructure documentation

- `/Users/zhdeng/stoa-docs@53c91971572a52bf4bfdc68aebd8393f3080a76d` — Pinned documentation repository snapshot.
- `/Users/zhdeng/stoa-docs/PLAN.md` — Product and system planning evidence with intent-only proof limits where delivery is not independently recorded.
- `/Users/zhdeng/stoa-docs/ADR.md` — Architecture decision evidence and candidate system outcomes.
- `/Users/zhdeng/stoa-docs/DEPLOYMENT.md` — Deployment design and operating-context evidence, not automatic proof of production operation.
- `/Users/zhdeng/stoa-infra@6d545ad8cae8d2fe67087f298d9d5fc7cc29b3f6` — Pinned infrastructure repository snapshot.
- `/Users/zhdeng/stoa-infra/README.md` — Infrastructure scope and documented operating/deployment context.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `StrictModel`: extend the existing frozen Pydantic v2 pattern so unknown fields and silent schema drift fail closed.
- `FormalRunStore`: reuse immutable, atomic publication and full input hashes for fixture-review runs and future replay bundles rather than introducing a second mutable persistence mechanism.
- `CorrectionRecord`: retain the original system proposal and human edits when turning candidates into confirmed fixture facts.
- `replay_recorded_response`: reuse exact comparison for structurally exact known-good results; declared sets or ranges should remain explicit policy rather than fuzzy equality.
- Provenance validation: extend current pinned-source discipline to the four STOA document snapshots and section locators.

### Established Patterns

- Contracts are schema-versioned, frozen, and reject extra fields.
- Invalid trust or lineage states fail closed rather than being repaired silently.
- Formal inputs and outputs are content-hashed, immutable, and linked through explicit reruns or corrections.
- Offline deterministic tests are the acceptance baseline; live Luna execution is optional and separately marked.
- The accepted runtime seam remains Codex CLI with `gpt-5.6-luna`, medium reasoning, structured output, and read-only source access when a live extraction smoke is later authorized.

### Integration Points

- Add Phase 2 domain contracts beside the Phase 1 validation contracts without weakening the existing charter models.
- Represent the human-reviewed STOA fixture as versioned input to the existing formal-run and replay boundary.
- Feed confirmed Contributions and Evidence into Phase 3 later; Phase 2 must not implement the conversational audit state machine.
- Expose deterministic validation through the existing package/CLI conventions and cover it with offline pytest cases.

</code_context>

<specifics>
## Specific Ideas

- The fixture should tell one coherent STOA story while retaining multiple durable outcomes, cross-repository relationships, partial delivery, and readiness limitations.
- A concrete known-bad case should be explainable as “the same confirmed STOA fixture, except this one rule was broken.”
- Fixture review is a development-time truth-sealing step, not an end-user replay feature and not an evaluation of whether STOA or the career product improves job-search outcomes.
- No repository authorship, project title, résumé wording, planning claim, or ontology relationship can substitute for the user's explicit confirmation of personal responsibility.

</specifics>

<deferred>
## Deferred Ideas

- Interactive artifact-aware Grill-Me questioning, pause/resume behavior, and conclusion review belong to Phase 3.
- Real mastery calibration, confidence-admission gates, and user-level aggregation formulas belong to Phase 4.
- JD comparison, adversarial full-loop evaluation, and usefulness judgments belong to Phase 5.
- Product, application, interview, and hiring effectiveness conclusions belong outside this phase and require later empirical evidence.

</deferred>

---

*Phase: 2-domain-contracts-stoa-fixture-and-deterministic-invariants*
*Context gathered: 2026-07-30*
