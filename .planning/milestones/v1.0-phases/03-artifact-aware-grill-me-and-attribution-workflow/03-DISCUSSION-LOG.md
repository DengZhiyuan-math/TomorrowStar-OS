# Phase 3: Artifact-Aware Grill-Me and Attribution Workflow - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-26
**Phase:** 3-artifact-aware-grill-me-and-attribution-workflow
**Areas discussed:** Audit entry and artifact use, Question selection and resumability, Responsibility and assistance, Conclusion review

---

## Audit entry and artifact use

### Opening behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Opening audit summary | Show inspected materials, established facts, remaining gaps, and why the first question is needed | |
| Collapsed minimal summary | Show known facts and open points while hiding sources until expanded | |
| Full evidence table | Show every artifact, fact, conflict, and gap before questioning | |
| Direct questioning after background inspection | Read project documents in the background, then immediately ask relevant questions from difficult to simple | ✓ |

**User's choice:** No opening display; after reading project documents, begin asking technical, organizational, research-and-development, and other relevant questions from difficult to simple.
**Notes:** The artifact record remains available to satisfy traceability, but it must not block or delay the first question.

### Reason shown with each question

| Option | Description | Selected |
|--------|-------------|----------|
| Short reason plus question | State what the record establishes and the remaining gap, then ask | ✓ |
| Question only | Ask without showing why it is needed | |

**User's choice:** Short reason plus question.
**Notes:** The user explicitly approved the Stripe/webhook example preserved in `03-CONTEXT.md` D-02.

### Verification bypass scope

| Option | Description | Selected |
|--------|-------------|----------|
| Current area only | Skip one capability or Skill area and continue elsewhere | |
| Entire Contribution only | End all questioning for the selected Contribution | |
| Support both scopes | Let the user skip one area or the entire Contribution | ✓ |

**User's choice:** Support both scopes.
**Notes:** The user may provide a direct self-rating when skipping. It must be labeled self-assessed and unverified.

### Coverage selection

| Option | Description | Selected |
|--------|-------------|----------|
| Material-relevant dimensions | Ask technical, R&D, organization, collaboration, or operation questions only when relevant to the Contribution | ✓ |
| Fixed category checklist | Ask every category for every Contribution | |
| Mandatory technical and responsibility core | Always ask technical and ownership questions, with other categories conditional | |

**User's choice:** Material-relevant dimensions.
**Notes:** Do not create artificial questions merely to fill category quotas.

---

## Question selection and resumability

### Incomplete difficult answer

| Option | Description | Selected |
|--------|-------------|----------|
| One same-level follow-up, then lower difficulty | Give one targeted chance to complete the answer before moving down | ✓ |
| Lower difficulty immediately | Do not follow up at the same level | |
| Continue same-level probing | Remain at that level until the answer is considered sufficient | |

**User's choice:** One same-level follow-up, then lower difficulty.
**Notes:** This limits repetitive interrogation while allowing clarification.

### Resume behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Restore state and ask the next question | Resume directly without showing prior material again | ✓ |
| Show a progress summary first | Recap progress before continuing | |
| Ask the user where to resume | Require manual area selection after every pause | |

**User's choice:** Restore state and ask the next question.
**Notes:** A progress view may still be available when explicitly requested.

### "不知道" versus "不是我做的"

| Option | Description | Selected |
|--------|-------------|----------|
| Separate capability and attribution branches | Lower difficulty for unknown capability; clarify ownership for work not done by the user | ✓ |
| Lower difficulty for both | Treat both answers as capability evidence | |
| End the area for both | Stop without further clarification | |

**User's choice:** Separate capability and attribution branches.
**Notes:** Lack of ownership is not a low-capability score.

### Stopping rule

| Option | Description | Selected |
|--------|-------------|----------|
| Stop at the established boundary | Stop after identifying the strongest established and immediately higher unestablished capability | ✓ |
| Ask all prepared questions | Complete the full question inventory regardless of established boundary | |
| Offer optional extra questions | Ask whether the user wants more after the boundary is found | |

**User's choice:** Stop at the established boundary.
**Notes:** Move to the next relevant area; complete the Contribution when all areas are verified, skipped, or unresolved.

---

## Responsibility and assistance

### Responsibility and assistance sequence

| Option | Description | Selected |
|--------|-------------|----------|
| Two separate turns | Establish responsibility first, then assistance | ✓ |
| One combined question | Ask responsibility and assistance together | |
| Infer from artifacts | Let repository or project records decide without asking | |

**User's choice:** Two separate turns.
**Notes:** This preserves the one-decision-per-turn contract.

### Conflict handling

| Option | Description | Selected |
|--------|-------------|----------|
| Show conflict and clarify boundary | Ask for the user's concrete portion; retain unresolved status if clarification fails | ✓ |
| Prefer user statement | Record personal ownership without reconciling project evidence | |
| Prefer project material | Record team ownership without hearing the user's boundary | |

**User's choice:** Show conflict and clarify boundary.
**Notes:** Preserve both the source claim and the user's response.

### Assisted independent work

| Option | Description | Selected |
|--------|-------------|----------|
| Clarify division of work | Establish who decided, generated, modified, debugged, tested, and accepted the work | ✓ |
| Transfer responsibility to the tool | Treat any agent use as tool-owned work | |
| Record assistance only | Add an assistance label without establishing the division of work | |

**User's choice:** Clarify division of work.
**Notes:** The user corrected the original Codex-specific framing: the product category must cover coding agents generally.

### Coding-agent metadata granularity

| Option | Description | Selected |
|--------|-------------|----------|
| Generic category plus optional tool/model provenance | Use `coding-agent-assisted`; record concrete tool and model when known | ✓ |
| Generic category only | Never retain tool or model details | |
| Vendor-specific assistance categories | Make Codex, Claude Code, Cursor, and others separate domain categories | |

**User's choice:** Approved generic category plus optional provenance.
**Notes:** Capability semantics remain provider-neutral.

---

## Conclusion review

### Conclusion contents and review scope

| Option | Description | Selected |
|--------|-------------|----------|
| Reviewable capability entries inside one Contribution conclusion | Include established boundary, next higher gap, basis, attribution, verification status, and unresolved points; allow entry-level and whole-Contribution review | ✓ |
| Single non-editable summary | Produce one final paragraph without entry-level review | |
| Numeric score only | Reduce the interview result to one number | |

**User's choice:** Approved reviewable entries and both entry-level and whole-Contribution edit, confirm, or reject actions.
**Notes:** Original proposals and human corrections or rejections remain separate in history.

### Phase 3 scoring behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Capability statements only for verified interviews | Do not calculate a Phase 3 score; preserve only explicitly entered skip self-ratings as unverified | ✓ |
| Generate a 0–100 interview score | Convert answers directly into a numeric mastery result | |
| Require a self-rating after every interview | Always ask the user for a number in addition to the boundary | |

**User's choice:** Approved capability statements without automatic scoring.
**Notes:** Calibration and admission into mastery or aggregation remain Phase 4 decisions.

## the agent's Discretion

- Exact CLI command names and state file shapes.
- Exact neutral question wording within the approved progression and guardrails.
- Whether artifact-inspection details are exposed through an explicit inspect command, the conclusion packet, or both.

## Deferred Ideas

- Calibrated numeric mastery and Skill aggregation — Phase 4.
- JD-specific comparison and evaluation — Phase 5.
- Résumé-submission effectiveness — later empirical product validation.
