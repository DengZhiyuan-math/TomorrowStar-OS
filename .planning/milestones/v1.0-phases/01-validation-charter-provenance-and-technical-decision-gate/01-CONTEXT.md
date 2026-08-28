# Phase 1: Validation Charter, Provenance, and Technical Decision Gate - Context

**Gathered:** 2026-07-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 defines the versioned functional-validation contract, reproducible
formal-run record, open-source provenance gate, and live-model technical gate
needed before implementing or tuning the core workflow.

The milestone validates whether the intended chain can operate correctly:

```text
Grill-Me
  → Contribution–Skill assessment
  → user Skill graph
  → JD comparison
```

It does not claim that the product improves application, interview, or hiring
outcomes. It does not create the STOA fixtures (Phase 2), implement the audit
workflow (Phase 3), freeze aggregation formulas (Phase 4), or conduct real
résumé submissions.

</domain>

<decisions>
## Implementation Decisions

### Functional Validation Contract

- **D-01:** The validation target is whether the designed end-to-end
  functionality runs correctly, not whether it improves real-world job-search
  outcomes.
- **D-02:** Acceptance requires all three of the following: one user-completed
  STOA flow, an automated end-to-end replay/regression case, and negative cases
  covering critical invalid behavior.
- **D-03:** A critical capability fabrication, incorrect responsibility
  attribution, broken assessment lineage, material instability for equivalent
  inputs, or inability to reproduce a formal run blocks functional acceptance.
  These failures cannot be offset by strengths elsewhere.
- **D-04:** Existing `supported` / `partially supported` / `rejected` language
  in `.planning/REQUIREMENTS.md` and `.planning/ROADMAP.md` must not be used to
  imply product effectiveness. Planning must explicitly reconcile that wording
  with the locked functional-validation target rather than silently mixing the
  two meanings.

### Cases and Expected Results

- **D-05:** Human-confirmed expected results are the correctness baseline.
  Expected results cover responsibility attribution, acceptable Skill
  identities, allowed capability ranges, required evidence relationships, and
  conclusions that must be rejected.
- **D-06:** Phase 1 defines the case protocol but does not pretend that cases
  already exist. Phase 2 creates the first cases from STOA.
- **D-07:** Do not create a sealed holdout while the project lacks enough
  independent cases. Reconsider hidden cases only after a sufficiently diverse
  case set exists.
- **D-08:** Case sufficiency is coverage-based, not quota-based. The minimum is
  one complete normal STOA path plus at least one targeted negative variant for
  every critical failure class, including fabrication, attribution error,
  duplicate evidence, broken lineage, and material instability.
- **D-09:** Comparison is structurally strict but semantically tolerant.
  Contribution identity, attribution, evidence lineage, and prohibited states
  must match exactly. Skill identity, mastery, and generated prose may use
  human-approved sets or ranges; prose is not compared character-for-character.

### Formal Runs and Review History

- **D-10:** Every run declared as formal validation or used to make an
  acceptance judgment is immutable and retained. Disposable exploratory
  debugging runs need not be retained.
- **D-11:** A rerun after changing code, prompts, models, configuration, or
  policy creates a new run linked to the prior run. It records what changed and
  the resulting differences; it never overwrites the prior run.
- **D-12:** Preserve the system's original proposal, the user's or reviewer's
  correction, and the correction reason. A corrected canonical result must not
  disguise an incorrect original proposal.
- **D-13:** Exact replay and live re-execution are separate. Exact replay uses
  the recorded raw model response. Live re-execution uses the recorded inputs
  and configuration to measure variability and reports differences rather than
  requiring word-for-word identity.

### Open-Source Provenance

- **D-14:** Copied code and copied upstream data require exact provenance:
  repository, pinned commit, source path, license, reuse classification, and
  documented local divergence.
- **D-15:** Recognizable architectural or workflow inspiration is recorded
  once per local subsystem in the central reuse matrix as `adapt` or
  `inspired-by`. It does not require line-level or file-level annotations.
- **D-16:** Provenance is completed where the reuse occurs. The same
  implementation change must add the applicable provenance record, license
  information, and local test; provenance is not deferred to a phase-end audit.

### Live-Model Technical Gate

- **D-17:** The selected live runtime is Codex CLI with model
  `gpt-5.6-luna` and reasoning effort `medium`.
- **D-18:** Development may use the `gpt-5.6-luna` alias. A formal run should
  use an immutable model snapshot when available and must record the Codex CLI
  version plus complete model configuration.
- **D-19:** If an immutable snapshot is unavailable, formal runs may proceed
  only with the raw model response retained and the model-drift limitation
  explicitly recorded.

### the agent's Discretion

- Exact file names and JSON/JSONL envelope shapes for the charter, case
  expectations, formal runs, diffs, and provenance registry.
- The number of additional normal and negative cases beyond the required
  coverage.
- The exact comparison algorithm for approved Skill sets, mastery ranges, and
  semantically variable prose.
- How disposable exploratory runs are marked and cleaned up, provided no formal
  run can be deleted or overwritten through that mechanism.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope and Requirements

- `.planning/PROJECT.md` — Core hypothesis, domain invariants, mastery anchors,
  scope exclusions, and open-source constraints.
- `.planning/REQUIREMENTS.md` — Phase 1 requirements `VAL-01`, `VAL-02`, and
  `OSS-01`; also contains terminology that must be reconciled with D-01/D-04.
- `.planning/ROADMAP.md` — Phase boundary, goal, success criteria, and
  dependencies for Phase 1.
- `.planning/STATE.md` — Current project position and known Phase 1 concerns.

### Architecture and Validation Risks

- `.planning/research/ARCHITECTURE.md` — Local-first modular architecture,
  versioned JSON artifacts, immutable proposal/canonical separation, and
  reproducible run lineage.
- `.planning/research/PITFALLS.md` — Circular evaluation, leakage, score
  inflation, attribution collapse, duplicate evidence, and stale-cache risks.
- `.planning/research/STACK.md` — Pinned runtime/tooling choices, provider
  isolation, JSON/JSONL workspace, and upstream reuse decisions.

### Open-Source Baseline

- `references/README.md` — Pinned upstream revisions, licenses, reuse matrix,
  and integration rule.
- `.gitmodules` — Authoritative local paths and repository URLs for the six
  pinned upstream submodules.

### Model Configuration

- `https://developers.openai.com/api/docs/models/gpt-5.6-luna` — Official model
  ID, reasoning support, tool support, and snapshot guidance for GPT-5.6 Luna.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `references/README.md`: already provides the central upstream reuse matrix
  and can be extended rather than replaced.
- `references/upstream/cv-market-learning-planner/`: contains current/history
  snapshot patterns and deterministic JSON helpers suitable for narrow,
  attributed adaptation.
- `references/upstream/hiring-agent/`: contains provider isolation and
  validated stage-cache patterns; cache identity must be strengthened with
  complete input and configuration hashes.
- Six pinned submodules under `references/upstream/`: provide exact source and
  license baselines without becoming runtime dependencies.

### Established Patterns

- Local-first, schema-versioned JSON snapshots plus append-only JSONL audit
  events.
- Model output remains an immutable proposal; human correction creates a
  separate confirmed revision.
- Derived artifacts identify their inputs, policies, prompts, models, settings,
  and reviewer versions.
- Upstream patterns are classified as `reuse`, `adapt`, `inspired-by`, or
  `reject`, with project-specific tests protecting local semantics.

### Integration Points

- Phase 1 outputs become the gate consumed by Phase 2 fixtures and every later
  formal evaluation run.
- The formal-run record must support both recorded-response replay and live
  Codex CLI re-execution.
- The provenance registry extends the existing `references/README.md` baseline
  and must remain synchronized with local adaptations as they are introduced.
- No application source tree exists yet, so planning may establish the minimal
  packaged Python project shape without preserving a pre-existing local API.

</code_context>

<specifics>
## Specific Ideas

- A "fixed replay" is an end-to-end regression case built from a
  human-confirmed interaction. It verifies that later code or prompt changes
  do not silently break a previously working path.
- Product usefulness must eventually be evaluated through repeated real résumé
  submissions and observed outcomes; internal functional tests are not a proxy
  for that claim.

</specifics>

<deferred>
## Deferred Ideas

- Repeated real résumé-submission experiments measuring response, interview,
  and hiring outcomes — future product-validation milestone after résumé
  generation exists.
- Sealed holdouts — reconsider only after the project has enough independent
  cases to reserve a meaningful hidden set.

</deferred>

---

*Phase: 1-Validation Charter, Provenance, and Technical Decision Gate*
*Context gathered: 2026-07-30*
