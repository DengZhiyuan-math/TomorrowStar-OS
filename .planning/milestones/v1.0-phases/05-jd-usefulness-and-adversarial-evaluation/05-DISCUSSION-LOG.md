# Phase 5: JD Usefulness and Adversarial Evaluation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-28
**Phase:** 5-jd-usefulness-and-adversarial-evaluation
**Areas discussed:** Match scoring and application routing, Match report contents, Priority
target management, Development-only evaluation boundary

---

## Match Scoring and Application Routing

### Normal JD input

| Option | Description | Selected |
|--------|-------------|----------|
| One JD at a time | Paste JD text or read one local file and compare it with the complete Skill graph. | ✓ |
| Batch comparison | Analyze several JDs together. | |

**User's choice:** One JD at a time.
**Notes:** This is a private personal resume-application system; batch and multi-user workflow
were rejected as needless complexity.

### Customized-resume triggers

| Option | Description | Selected |
|--------|-------------|----------|
| Evidence-proven exception | A rare core requirement has direct high-confidence Contribution evidence. | ✓ |
| Manual priority only | Only explicit user preference can trigger special treatment. | |
| Both | Evidence can prove strong match and the user can mark priority targets, with distinct reasons. | ✓ |

**User's choice:** Preserve both evidence-based and user-priority routes.
**Notes:** Evidence-based strong match and personal preference must remain distinct.

### Core hard-requirement compensation

| Option | Description | Selected |
|--------|-------------|----------|
| No full compensation | A missing core hard requirement caps the maximum match tier. | ✓ |
| Weighted compensation | Other strengths may fully compensate through the total score. | |
| Per-JD manual decision | Ask the user whenever a core requirement is missing. | |

**User's choice:** No full compensation.
**Notes:** A priority-company route may still customize, but it cannot hide the gap.

### Routing thresholds

| Option | Description | Selected |
|--------|-------------|----------|
| Transparent configurable policy | Version the three bands, calibrate initial values, and retain the policy used. | ✓ |
| Fixed thresholds | Choose once during development. | |
| No numeric thresholds | Let a model directly choose the route. | |

**User's choice:** Transparent, configurable, versioned thresholds.

---

## Match Report Contents

### Report opening

| Option | Description | Selected |
|--------|-------------|----------|
| Score, route, and key reasons | Lead with `0-100`, route, strongest match, and core gap. | ✓ |
| Score and route only | Hide reasons unless separately requested. | |
| Full requirements first | Put the total score after the detailed table. | |

**User's choice:** Score, route, and key reasons first.

### Requirement detail

| Option | Description | Selected |
|--------|-------------|----------|
| Key items plus expandable full list | Default to decision-critical items but retain all structured requirements. | ✓ |
| Key items only | Discard ordinary requirements from the report. | |
| Always show everything | Open with every requirement and its evidence. | |

**User's choice:** Key items by default with expandable complete analysis.

### Evidence presentation

| Option | Description | Selected |
|--------|-------------|----------|
| Readable evidence summary | Show Experience, Contribution, established capability, and limitations. | ✓ |
| Complete audit by default | Show IDs, policy, anchors, confidence, and lineage immediately. | |
| Conclusion only | Hide supporting evidence unless queried separately. | |

**User's choice:** Human-readable evidence summary with technical expansion.

### Resume-source selection

| Option | Description | Selected |
|--------|-------------|----------|
| Recommend relevant Contributions | Select and explain the best source Contributions without writing resume copy. | ✓ |
| List every related experience | Leave all selection to the user. | |
| Do not select experiences | Limit the report to score and gaps. | |

**User's choice:** Recommend the most relevant Contributions and explain why.

---

## Priority Target Management

### Persistent preference scope

| Option | Description | Selected |
|--------|-------------|----------|
| Company and role list | Persist both kinds of priority target. | |
| Company list only | Persist priority companies and analyze each JD normally. | ✓ |
| Per-JD choice only | Do not retain a priority list. | |

**User's choice:** Company-level priority list only.
**Notes:** Apple and Google were given as examples.

### Route for priority companies

| Option | Description | Selected |
|--------|-------------|----------|
| Customize only when it adds evidence | Ordinary matches may still use the standard resume. | |
| Customize every role | Every JD at a priority company enters customized-resume flow. | ✓ |
| User decides each time | Show analysis but make no route recommendation. | |

**User's choice:** Customize every role at a priority company.
**Notes:** Honest score, gaps, and risks remain visible.

### Reason label

| Option | Description | Selected |
|--------|-------------|----------|
| Distinct reasons | Separate evidence-strong-match from user-priority-company. | ✓ |
| Generic customization label | Show only `customized resume`. | |

**User's choice:** Explicitly distinguish the trigger reason.

### Historical behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Preserve old results | Apply preference changes forward and retain prior list versions. | ✓ |
| Recalculate all history | Mutate all historical routes after a list change. | |
| Overwrite on rerun | Keep only the newest analysis. | |

**User's choice:** Preserve old reports; explicit reruns create new results.

---

## Development-Only Evaluation Boundary

### Independent review placement

| Option | Description | Selected |
|--------|-------------|----------|
| One development checkpoint | Produce one fixed packet for an independent reviewer. | ✓ |
| Automated tests only | Remove the independent-review requirements. | |
| Full reviewer product | Build recurring multi-review and adjudication features. | |

**User's choice:** One-time independent development acceptance checkpoint.

### Fixed JD corpus

| Option | Description | Selected |
|--------|-------------|----------|
| Three JDs plus counterfactual | Cover strong, ordinary, low, and priority-route isolation. | ✓ |
| Four independent JDs | Use a separate JD for each route. | |
| Random current postings | Fetch new web postings for each run. | |

**User's choice:** Three fixed JDs plus one priority-company counterfactual.

### Trust-boundary failure

| Option | Description | Selected |
|--------|-------------|----------|
| Block without a score | Require repair or confirmation followed by a new run. | ✓ |
| Score with warning | Emit a lower-confidence best-effort result. | |
| Ignore suspect portions | Score only the remaining input. | |

**User's choice:** Fail closed without score or route.

### Three-run stability

| Option | Description | Selected |
|--------|-------------|----------|
| Exact offline plus bounded live stability | Offline is identical; live route, core judgments, and evidence stay stable. | ✓ |
| Exact score everywhere | Require identical numeric live-model output. | |
| Route only | Allow requirement and evidence judgments to drift. | |

**User's choice:** Exact deterministic offline results and bounded optional live-model variance.

---

## the agent's Discretion

- Exact transparent score weights, initial threshold values, schema/file/CLI names, and report
  envelope, within the locked truth and routing constraints.
- Exact fixed baseline packet and independent-review record format.
- Exact priority-company alias normalization and number/order of recommended Contributions.

## Deferred Ideas

- Actual customized-resume generation, rewriting, review, formatting, and export.
- Measuring real application, interview, offer, or hiring effectiveness through later
  multi-round use.
- Multi-user and recurring reviewer workflows.

## Post-Discussion Planning Constraint

**User instruction:** The user will provide the real test JDs when execution reaches the test
step. Research and planning must not find, choose, or generate those JDs.

**Planning consequence:** Plans may build the strict intake contract and checkpoint first, but
fixture-dependent execution and completion remain blocked until the user supplies the inputs.
