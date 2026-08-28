# Phase 4: Contribution–Skill Assessment and Aggregation Calibration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-27
**Phase:** 4-contribution-skill-assessment-and-aggregation-calibration
**Areas discussed:** Skill determination and granularity, three-score review process, low-confidence handling, multi-Contribution aggregation

---

## Skill determination and granularity

### Scored Skill granularity

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Score only concrete, verifiable specific Skills; use broad areas only for classification | ✓ |
| 2 | Score broad areas and specific Skills | |
| 3 | Score broad areas first and split them later | |

**User's choice:** Option 1.

### One Contribution supporting multiple Skills

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Propose every directly supported specific Skill and assess each independently | ✓ |
| 2 | Choose only one primary Skill | |
| 3 | Create one combined Skill | |

**User's choice:** Option 1.

### Skill-name normalization

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Auto-normalize deterministic synonyms; require human review for ambiguous or unmatched candidates | ✓ |
| 2 | Require human review for every normalization | |
| 3 | Allow model-selected normalization without confirmation | |

**User's choice:** Option 1.

### Phase 3 skip or self-rating

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Keep it permanently provisional unless a complete new audit is performed | |
| 2 | Permit formal Phase 4 scoring after one explicit human confirmation while preserving its unverified origin | ✓ |
| 3 | Admit it automatically as a formal score | |

**User's choice:** Option 2.
**Notes:** Later low-confidence decisions clarified that this confirmation must inspect the basis, responsibility attribution, and anchor fit; it is not a bare confirmation click.

---

## Three-score review process

### Initial score authority

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | System proposes each score and a human confirms or edits every item | |
| 2 | Human fills all three scores; the system only stores them | |
| 3 | System determines all three scores; a human edits only on exception | ✓ |

**User's choice:** Option 3.

### Mastery band and exact score

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Select the satisfied anchor band, then an exact score inside it and preserve the rationale | ✓ |
| 2 | Store only the anchor band | |
| 3 | Store only an exact number without an anchor explanation | |

**User's choice:** Option 1.

### Separate dimensions and simplified display

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Preserve three independent scores and also derive a convenience composite | ✓ |
| 2 | Preserve only the three independent scores | |
| 3 | Replace the three dimensions with one combined score | |

**User's choice:** The user initially selected a single combined score. The option was withdrawn because it contradicted the locked project requirement that mastery, centrality, and confidence retain different meanings. The user then selected Option 1: preserve all three internally and add a convenience composite.

### Human correction history

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Preserve the system proposal, human result, and reason; make the human result current-effective | ✓ |
| 2 | Overwrite the system proposal | |
| 3 | Keep both without identifying which is effective | |

**User's choice:** Option 1.

---

## Low-confidence handling

### Admission of a high-mastery, low-confidence proposal

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Mark pending, prompt for human confirmation, and exclude it from the formal aggregate until confirmed | ✓ |
| 2 | Include it with a confidence-based discount | |
| 3 | Include it equally and only display a warning | |

**User's choice:** Option 1.
**Notes:** The user explicitly requested the `pending-confirmation` label and a visible request for human confirmation.

### Meaningful human confirmation

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Inspect the basis, responsibility attribution, and anchor fit, then accept or modify all three scores | ✓ |
| 2 | Click confirm without reviewing the basis | |
| 3 | Repeat the complete Grill-Me audit | |

**User's choice:** Option 1.

### Insufficient basis after review

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Retain an unverified candidate outside the aggregate for later evidence or re-audit | ✓ |
| 2 | Delete the Skill record | |
| 3 | Record formal mastery as zero | |

**User's choice:** Option 1.

### Later evidence or audit

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Create a new assessment version and preserve the original candidate, basis, and human decisions | ✓ |
| 2 | Overwrite the old candidate | |
| 3 | Automatically admit the candidate without a new confidence decision | |

**User's choice:** Option 1.

---

## Multi-Contribution aggregation

### User-level mastery baseline

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Use the strongest admitted Contribution as the baseline and use others to establish stability | ✓ |
| 2 | Average all Contribution mastery scores | |
| 3 | Add all scores so more Contributions always increase mastery | |

**User's choice:** Option 1.

### Promotion beyond the strongest Contribution

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Promote only when the combined Contributions observably satisfy the higher anchor and preserve the rationale | ✓ |
| 2 | Never exceed the strongest individual assessment | |
| 3 | Add a fixed bonus for each additional Contribution | |

**User's choice:** Option 1.

### Evidence reused across Skills

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Allow one evidence item to support multiple Skills, assess relevance independently, and suppress duplicate weighting only within the same Skill | ✓ |
| 2 | Increase evidence weight on every reference, including duplicates within the same Skill | |

**User's choice:** Option 1.
**Notes:** The original duplicate-evidence wording was unclear. The user clarified that a mathematics PhD or a complex project naturally can support probability, mathematics, numerical analysis, statistics, and other Skills. The final decision explicitly permits this legitimate cross-Skill reuse.

### Aggregation-policy changes

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Version policies, recalculate identical inputs for comparison, explicitly activate a version, and preserve old results | ✓ |
| 2 | Overwrite the old policy and all old results | |
| 3 | Always choose the highest result among policies | |

**User's choice:** Option 1.

## the agent's Discretion

- Exact confidence thresholds and replaceable policy parameters.
- Exact formula for the convenience composite and the constrained user-level aggregate.
- Internal schema envelopes, command names, identifiers, and report layout.
- Deterministic, structured-model, or hybrid implementation of system proposals, subject to provider isolation and deterministic offline tests.

## Deferred Ideas

- JD comparison and usefulness evaluation belong to Phase 5.
- Resume generation and evidence-producing gap work remain downstream.
- Application, interview, and hiring effectiveness require later real-world observation and are not inferred from Phase 4 execution.
