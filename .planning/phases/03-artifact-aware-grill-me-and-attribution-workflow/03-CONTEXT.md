# Phase 3: Artifact-Aware Grill-Me and Attribution Workflow - Context

**Gathered:** 2026-08-26
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers a resumable audit of one selected Contribution. The system
first inspects the supplied project artifacts in the background, then asks one
focused question per turn to establish the user's capability boundary and to
separate personal responsibility from team, other-person, coding-agent, and
third-party work. The user can pause, resume, skip verification, and review,
edit, confirm, or reject the resulting Contribution conclusion.

The artifact inspection record remains inspectable, but it is not shown as a
mandatory opening screen. This phase records capability boundaries and optional
unverified self-ratings; it does not calibrate mastery scores, aggregate Skills,
compare JDs, or evaluate application, interview, or hiring outcomes.

</domain>

<decisions>
## Implementation Decisions

### Artifact-aware audit entry and question coverage

- **D-01:** Inspect the selected Contribution's project documents before asking questions, but do not automatically show an opening summary or evidence table. Begin the audit directly with the first question. The inspection record required by `AUD-01` must remain available for inspection and later conclusion traceability.
- **D-02:** Prefix every question with one short, concrete reason that states what the project record established and what remains unverified. Example: "项目记录表明你参与了 Stripe 订阅流程，但无法确认你是否掌握异常恢复。因此：如果 webhook 重复或乱序，你会怎样保证状态正确？"
- **D-03:** Generate questions only for dimensions genuinely relevant to the selected Contribution. Technical design, implementation, research and development process, debugging, operation, organization, and collaboration are all eligible, but the workflow must not force irrelevant categories merely to fill a checklist.
- **D-04:** Start at a demanding capability level and move toward simpler questions to locate the user's actual boundary. Do not begin with simple questions and mechanically climb upward.

### Verification skip, questioning, and resumability

- **D-05:** The user may skip either the current capability/Skill area or the entire Contribution audit. A skip may include a user-supplied self-rating, which must be preserved verbatim as `self-assessed` and `unverified`; it must not be presented as an audit-confirmed or calibrated mastery score.
- **D-06:** If an answer at the current difficulty is incomplete, allow exactly one focused follow-up at that same level. If the missing capability is still not established, lower the difficulty rather than repeatedly interrogating at the same level.
- **D-07:** On pause and resume, restore answers, artifact-established facts, coverage, contradictions, attribution state, and unresolved questions, then ask the next unanswered question directly. Do not repeat the opening material or already answered questions unless the user explicitly requests a progress view.
- **D-08:** Treat "不知道" as failure to establish the current capability level and move downward. Treat "这部分不是我做的" as an attribution signal and branch to responsibility clarification; it is not evidence of low capability.
- **D-09:** Stop questioning a capability area once the strongest level the user can establish and the immediately higher level not established are both known. Move to the next relevant area. The Contribution audit completes when every relevant area is verified, explicitly skipped, or explicitly unresolved.

### Responsibility and assistance attribution

- **D-10:** Confirm responsibility and assistance in separate turns. First establish whether the work was user-owned, team-owned, or other-person-owned; then establish whether and how a coding agent or third party assisted. Never infer personal ownership solely from project documents or repository history.
- **D-11:** When the user's statement conflicts with project material, show the concrete conflict and ask for the user's actual responsibility boundary. Preserve both claims and mark responsibility unresolved if the boundary cannot be clarified; do not silently prefer either source.
- **D-12:** Use the provider-neutral primary assistance category `coding-agent-assisted`, not a Codex-specific domain category. When known, retain the concrete tool and model as provenance metadata, for example Codex CLI and GPT-5.6 Luna. Different vendors do not become different capability categories. — **Reversibility:** costly — changing the canonical assistance value after persisted audits exist requires a schema/data migration and compatibility handling.
- **D-13:** Coding-agent use does not automatically remove user responsibility or establish user capability. When relevant, clarify who made design decisions, generated code, modified outputs, debugged failures, tested behavior, and accepted the final result. Capability still depends on what the user can explain, modify, reproduce, debug, defend, or operate.

### Conclusion review and scoring boundary

- **D-14:** Produce one Contribution conclusion containing reviewable entries for each audited capability/Skill area. Each entry states the strongest capability established, the next-higher capability not established, the supporting basis, responsibility and assistance boundaries, whether it came from audit verification or unverified self-assessment, and every unresolved conflict or gap.
- **D-15:** Let the user edit, confirm, or reject each conclusion entry, and also confirm or reject the entire Contribution conclusion. Preserve the system's original proposal, the user's correction or rejection, and the reason rather than overwriting audit history.
- **D-16:** Do not generate a numeric score from the Phase 3 interview. Verified results are concrete capability-boundary statements. A numeric value appears only when the user elects to skip and supplies a self-rating; that value remains explicitly unverified and is not admitted into Phase 4 mastery or aggregation without later policy.

### the agent's Discretion

- Exact command names, JSON/JSONL envelope shapes, stable identifiers, and internal state-transition representation.
- Exact wording of neutral questions and capability ladders, provided the locked hard-to-simple, one-question, one-same-level-follow-up, reason-preface, and anti-leading constraints are enforced.
- Whether the inspectable artifact record is exposed by an explicit CLI command, included in the conclusion packet, or both, provided it is not forced as an opening display.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project scope and Phase 3 contract

- `.planning/PROJECT.md` — Defines Contribution-level audit granularity, score separation, anchor integrity, truthfulness, and the validation-only product boundary.
- `.planning/REQUIREMENTS.md` — Defines Phase 3 requirements `AUD-01` through `AUD-05`.
- `.planning/ROADMAP.md` — Defines the Phase 3 goal, success criteria, dependencies, and its boundary from Phase 4 calibration.
- `.planning/STATE.md` — Records Phase 2 completion and Phase 3 as the current focus.
- `.planning/phases/01-validation-charter-provenance-and-technical-decision-gate/01-CONTEXT.md` — Locks functional validation, immutable proposals/corrections, replay separation, and the Codex CLI technical gate.
- `.planning/phases/01-validation-charter-provenance-and-technical-decision-gate/01-VALIDATION.md` — Defines deterministic validation expectations inherited by this workflow.
- `.planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants/02-CONTEXT.md` — Locks Contribution boundaries, documentary proof limits, claim-level attribution, conflict preservation, and Phase 4 score deferral.
- `.planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants/02-VALIDATION.md` — Defines the completed Phase 2 validation baseline consumed by Phase 3.
- `.planning/phases/02-domain-contracts-stoa-fixture-and-deterministic-invariants/02-VERIFICATION.md` — Confirms the sealed STOA fixture and invariant foundations available to this phase.

### Sealed STOA audit input

- `validation/fixtures/stoa/v1/known-good.json` — Sealed known-good STOA fixture that supplies the selected Contributions, claims, evidence links, limitations, and current attribution state.
- `validation/fixtures/stoa/v1/source-manifest.json` — Pinned source-document scope and hashes for artifact inspection.
- `validation/fixtures/stoa/v1/candidates.json` — Original documentary proposals retained separately from human review.
- `validation/fixtures/stoa/v1/review.json` — Human decisions that establish the current canonical fixture without pretending to establish Phase 3 capability.

### Existing implementation contracts

- `src/career_evidence_graph/domain/models.py` — Existing strict Experience, Contribution, claim, Evidence, Skill, assessment, responsibility, assistance, and confirmation contracts; the Codex-specific assistance literal requires the Phase 3 provider-neutral evolution decided in D-12.
- `src/career_evidence_graph/domain/invariants.py` — Existing contribution-lineage, evidence-link, attribution, and mastery-isolation checks.
- `src/career_evidence_graph/domain/fixtures.py` — Existing source verification, candidate review, fixture sealing, and deterministic mutation patterns.
- `src/career_evidence_graph/validation/models.py` — Existing strict immutable schema patterns, formal-run contracts, and correction records.
- `src/career_evidence_graph/validation/store.py` — Existing atomic immutable storage, content hashing, and correction lineage.
- `src/career_evidence_graph/validation/replay.py` — Existing exact recorded-response replay boundary.
- `src/career_evidence_graph/codex_cli.py` — Existing read-only structured Codex CLI adapter using the selected live-model technical configuration.
- `src/career_evidence_graph/cli.py` — Existing argparse integration point for fixture, run, replay, provenance, and guarded live-execution commands.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `StrictModel` and the Phase 2 domain contracts provide frozen, extra-forbidding Pydantic patterns for audit state, questions, answers, attribution, coverage, and conclusions.
- `CareerEvidenceFixture`, `Contribution`, `ContributionClaim`, `Evidence`, and `ClaimEvidenceLink` provide the grounded input graph; Phase 3 should extend around these records rather than create a second parallel experience model.
- `FormalRunStore` and `CorrectionRecord` provide immutable original-proposal plus human-correction lineage suitable for confirmed or rejected conclusions.
- `replay_recorded_response` provides exact deterministic replay for recorded interview decisions without conflating replay with live model re-execution.
- `build_codex_exec_argv` and the existing Codex CLI result contracts provide the optional live structured-output seam; offline fake or recorded behavior remains the default test path.

### Established Patterns

- Contracts are schema-versioned, frozen, and fail closed on extra or invalid fields.
- Documents establish bounded project facts but never automatically establish personal responsibility or mastery.
- Proposal, human correction, confirmed result, and formal-run lineage remain distinct and immutable.
- JSON/JSONL workspaces and standard-library file operations are preferred over a database or workflow framework.
- Default verification is deterministic and offline; live-model execution is opt-in, read-only, and separately recorded.

### Integration Points

- Add the audit state machine and resumable store beside the existing domain and validation packages, reusing their strict contracts and immutable lineage.
- Consume the sealed STOA known-good fixture as the first Contribution audit input while retaining its unresolved score boundary.
- Extend the existing argparse CLI with the smallest commands needed to start, answer, skip, pause/resume, inspect, and review an audit.
- Evolve assistance attribution from the current `codex_assisted` literal to the provider-neutral `coding-agent-assisted` contract without weakening existing Phase 2 attribution evidence.
- Feed only confirmed capability-boundary conclusions and clearly labeled unverified self-ratings forward; Phase 4 decides whether and how either becomes an assessment.

</code_context>

<specifics>
## Specific Ideas

- The desired opening experience is immediate questioning, not a dashboard: project material is read in the background and the first user-visible content is a reason-prefaced, difficult question.
- A question should read like: "项目记录表明你参与了 Stripe 订阅流程，但无法确认你是否掌握异常恢复。因此：如果 webhook 重复或乱序，你会怎样保证状态正确？"
- The workflow is voluntary self-capability verification. A user who does not want the interview can bypass one area or the entire Contribution and enter a self-rating without the system mislabeling it as verified.
- "借助 coding agent 独立完成" can still be user-owned work, but the audit must establish the user's decisions and operational understanding rather than treating tool use as either automatic mastery or automatic disqualification.

</specifics>

<deferred>
## Deferred Ideas

- Converting capability boundaries or self-ratings into calibrated 0–100 mastery, confidence admission, Contribution–Skill assessments, or user-level aggregation belongs to Phase 4.
- JD comparison and questions selected from target-job requirements belong to Phase 5.
- Real résumé-submission effectiveness remains a later empirical product-validation concern, not a Phase 3 conclusion.

</deferred>

---

*Phase: 3-artifact-aware-grill-me-and-attribution-workflow*
*Context gathered: 2026-08-26*
