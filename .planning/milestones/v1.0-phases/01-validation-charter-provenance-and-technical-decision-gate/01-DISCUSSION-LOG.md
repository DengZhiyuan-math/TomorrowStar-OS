# Phase 1: Validation Charter, Provenance, and Technical Decision Gate - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-30
**Phase:** 1-Validation Charter, Provenance, and Technical Decision Gate
**Areas discussed:** 判定门槛与失败规则, 基线与封存样本协议, 可复现运行与评审记录, 上游 provenance 与技术决策门

---

## 判定门槛与失败规则

### Critical failures

| Option | Description | Selected |
|--------|-------------|----------|
| Hard gate | Fabrication, broken lineage, material instability, or unreproducible formal runs cannot be offset by other strengths | ✓ |
| Overall trade-off | Allow strong aggregate performance to offset a serious local failure | |
| Mixed | Fabrication is a hard failure; handle other failures by severity | |

**User's choice:** Hard gate.
**Notes:** Critical truthfulness and reproducibility failures cannot pass
functional acceptance.

### What the project evaluates

| Option | Description | Selected |
|--------|-------------|----------|
| Field-pilot readiness | Decide only whether to proceed to a real submission pilot | |
| Restricted hypothesis verdict | Keep supported/partial/rejected but limit it to the technical hypothesis | |
| No product-effectiveness verdict | Validate that the designed functionality works; real usefulness requires later résumé submissions | ✓ |

**User's choice:** The final target is whether the designed functionality can
run as expected, not a usefulness conclusion.
**Notes:** The user explicitly stated that product usefulness cannot be judged
internally and should later be observed through multiple real résumé
submissions.

### Strength of functional validation

| Option | Description | Selected |
|--------|-------------|----------|
| Full flow + repeatability + negative cases | Run the real STOA path, replay it, and reject critical invalid variants | ✓ |
| Full happy path only | Consider the workflow complete once one STOA-to-JD path finishes | |
| Automated tests only | Do not require a real user-completed flow | |

**User's choice:** Full flow, repeatability, and negative cases.
**Notes:** "Runs" means more than returning an output.

### Real use and fixed replay

| Option | Description | Selected |
|--------|-------------|----------|
| Both | The user completes one real STOA audit and the project keeps one automated end-to-end regression replay | ✓ |
| Real use only | Require user completion but no automated replay | |
| Replay only | Use scripted inputs without user completion | |

**User's choice:** Both.
**Notes:** The term "fixed replay" required clarification. It means saving a
human-confirmed interaction as a regression case so later code or prompt
changes can be checked automatically.

---

## 基线与封存样本协议

### Correctness baseline

| Option | Description | Selected |
|--------|-------------|----------|
| Human-confirmed expected results | Compare responsibility, Skill, capability range, lineage, and rejected conclusions with reviewed expectations | ✓ |
| Current manual workflow | Compare the system with how the user currently organizes the same information without it | |
| Flat résumé keywords | Compare JD results with a keyword matcher | |
| Agent discretion | Let the planner choose | |

**User's choice:** Human-confirmed expected results.
**Notes:** This is a functional-correctness baseline, not an employment-outcome
baseline.

### Sealed cases

| Option | Description | Selected |
|--------|-------------|----------|
| No sealed set yet | Phase 1 defines the protocol; Phase 2 creates the first STOA cases; hidden cases wait for a sufficiently diverse set | ✓ |
| Reserve hidden cases in Phase 2 | Create and immediately hide part of the first case set | |

**User's choice:** No sealed set yet.
**Notes:** The user pointed out that the project currently has no cases. The
workflow was corrected to avoid pretending a holdout already exists.

### Case sufficiency

| Option | Description | Selected |
|--------|-------------|----------|
| Coverage-based | One full normal path plus targeted variants for each critical failure type; no arbitrary quota | ✓ |
| Fixed count | Require preset numbers of normal and invalid cases | |
| One STOA path only | Do not add targeted invalid cases | |

**User's choice:** Coverage-based.
**Notes:** Failure coverage includes fabrication, attribution, duplication,
lineage, and instability.

### Comparison precision

| Option | Description | Selected |
|--------|-------------|----------|
| Structurally strict, semantically tolerant | Exact structure, attribution, lineage, and prohibited-state checks; approved sets/ranges for semantic output | ✓ |
| Exact equality | Require exact Skill, score, conclusion, and generated text | |
| Completion only | Check only that the workflow returns a result | |

**User's choice:** Structurally strict, semantically tolerant.
**Notes:** Generated prose does not need character-for-character equality.

---

## 可复现运行与评审记录

### Which runs are retained

| Option | Description | Selected |
|--------|-------------|----------|
| Formal runs | Retain every run declared as formal validation or used for acceptance; exploratory runs may be discarded | ✓ |
| All runs | Retain every temporary development and debugging run | |
| Passing run only | Discard failures and keep only the final accepted run | |

**User's choice:** Formal runs.
**Notes:** The user asked whether this concerned development or end-user use.
It was clarified that this decision covers development/formal validation
records; user audit pause/resume belongs to Phase 3.

### Rerun history

| Option | Description | Selected |
|--------|-------------|----------|
| New linked run | Keep the old run immutable and create a linked rerun with changes and diffs | ✓ |
| Revise original | Update the original record while keeping an internal revision history | |
| Unlinked run | Create a new record without documenting its relationship to the earlier run | |

**User's choice:** New linked run.
**Notes:** Prompt, code, model, configuration, and policy changes all trigger
the same rule.

### Human corrections

| Option | Description | Selected |
|--------|-------------|----------|
| Preserve proposal and correction | Keep the system output, human correction, and correction reason | ✓ |
| Final version only | Replace the proposal with the corrected result | |
| Pass/fail only | Record no detailed difference | |

**User's choice:** Preserve proposal and correction.
**Notes:** A correction must not make an initially incorrect proposal appear
correct in retrospect.

### Model reproducibility

| Option | Description | Selected |
|--------|-------------|----------|
| Separate replay and re-execution | Replay the stored raw response exactly; use a fresh call only to measure variability | ✓ |
| Require exact live identity | Treat any wording difference on a fresh call as unreproducible | |
| Final output only | Do not retain raw responses or compare fresh calls | |

**User's choice:** Separate replay and re-execution.
**Notes:** Live model variation is reported, not hidden or averaged away.

---

## 上游 provenance 与技术决策门

### Provenance granularity

| Option | Description | Selected |
|--------|-------------|----------|
| Exact copied-content records + subsystem-level inspiration matrix | Record copied code/data exactly; record architecture/workflow inspiration once per subsystem | ✓ |
| Copied code only | Remove adapted-seam traceability from OSS-01 | |
| Exact records for all adaptation | Trace every adaptation to specific upstream files | |

**User's choice:** Exact copied-content records with a lightweight central
matrix for architectural and workflow inspiration.
**Notes:** This was selected as the compromise between the user's initial
preference to record only copied code and the existing `OSS-01` requirement.

### When provenance is completed

| Option | Description | Selected |
|--------|-------------|----------|
| Where it is used | Complete provenance, license notes, and tests in the same implementation change | ✓ |
| Phase-end audit | Add all records at the end of the phase | |
| Release-time audit | Defer provenance until public release | |

**User's choice:** "用那里补齐那里" — complete it where it is used.
**Notes:** Provenance is part of implementation completion, not later
bookkeeping.

### Live runtime

| Option | Description | Selected |
|--------|-------------|----------|
| Codex CLI + GPT-5.6 Luna + medium | Use model ID `gpt-5.6-luna` with reasoning effort `medium` | ✓ |
| Recorded responses first, select later | Keep the live model unfrozen | |
| Multi-provider from the start | Build provider switching as initial functionality | |

**User's choice:** Codex CLI, GPT-5.6 Luna, medium reasoning.
**Notes:** Local configuration did not list Luna, so the exact model ID and
reasoning support were verified against OpenAI's official model documentation.

### Formal model pin

| Option | Description | Selected |
|--------|-------------|----------|
| Alias in development, snapshot when possible for formal runs | Record CLI/config; retain raw responses and disclose drift if no snapshot exists | ✓ |
| Alias only | Use `gpt-5.6-luna` for every run without snapshot pinning | |
| Block without snapshot | Do not permit formal validation until an immutable snapshot is available | |

**User's choice:** Alias in development, snapshot when possible for formal
runs.
**Notes:** Absence of a snapshot does not block the project if raw responses
and the drift limitation are preserved.

---

## the agent's Discretion

- Exact schemas, file names, and directory structure for charter, run, diff,
  expectation, and provenance artifacts.
- Additional case count beyond the coverage minimum.
- The semantic comparison mechanism for approved Skill sets, mastery ranges,
  and variable prose.
- Exploratory-run cleanup mechanics that cannot affect formal runs.

## Deferred Ideas

- Validate product usefulness through repeated real résumé submissions and
  observed response/interview/hiring outcomes after résumé generation exists.
- Introduce sealed holdouts only after enough independent cases exist to form a
  meaningful hidden set.
