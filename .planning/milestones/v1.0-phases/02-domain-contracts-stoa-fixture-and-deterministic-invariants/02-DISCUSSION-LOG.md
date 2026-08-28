# Phase 2: Domain Contracts, STOA Fixture, and Deterministic Invariants - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-30
**Phase:** 2-domain-contracts-stoa-fixture-and-deterministic-invariants
**Areas discussed:** STOA material sources, Contribution boundaries, Evidence and responsibility attribution, Known-good and known-bad fixture generation

---

## STOA material sources

### Initial source

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Inspect material in the STOA repositories | ✓ |
| 2 | Start from the user's narration | |
| 3 | Start from résumé wording | |

**User's choice:** Inspect `stoa-backend`, `stoa-frontend`, `stoa-infra`, `stoa-docs`, and related projects.
**Notes:** The user later narrowed this choice: do not read implementation code; use development plans and audit documentation.

### Snapshot policy

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Pin the current HEAD of all four repositories | ✓ |
| 2 | Pin one historical milestone | |
| 3 | Use current HEAD plus repository history | |

**User's choice:** Current HEAD.
**Notes:** Exact commits were recorded in `02-CONTEXT.md`.

### Allowed material

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Git-tracked planning, handoff, acceptance, and audit documents only | ✓ |
| 2 | Tracked documents plus selected private files | |
| 3 | Any available repository material | |

**User's choice:** Tracked development documentation only.
**Notes:** Secrets, production/user data, caches, untracked files, and implementation code are excluded.

### Personal responsibility

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Documents propose facts; the user confirms responsibility | ✓ |
| 2 | Authored commits prove personal Contribution | |
| 3 | Project documentation is accepted as personal truth | |

**User's choice:** Candidate facts require user confirmation.
**Notes:** Repository material cannot independently establish personal capability or mastery.

---

## Contribution boundaries

### Minimum auditable unit

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | One independently explainable and auditable outcome | ✓ |
| 2 | One repository | |
| 3 | One commit or development phase | |

**User's choice:** Split by durable work outcome.
**Notes:** One Contribution may span repositories.

### STOA coverage

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | A small contrasting subset | |
| 2 | One complete outcome first | |
| 3 | All major STOA outcomes in one Experience | ✓ |

**User's choice:** Organize all major STOA outcomes at once.
**Notes:** This is still one Experience with multiple Contributions, not one undifferentiated project claim.

### Consolidating development phases

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Group phases by durable product or system outcome | ✓ |
| 2 | Treat every phase as a Contribution | |
| 3 | Copy audit-module categories directly | |

**User's choice:** Group by durable outcome.
**Notes:** Development-process granularity must not leak into the career evidence model.

### Delivery status

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Include delivered and partial outcomes; preserve limitations; exclude planned-only work from Contributions | ✓ |
| 2 | Include every major plan as a Contribution | |
| 3 | Include only fully complete outcomes | |

**User's choice:** Delivered and partial work may enter, with explicit limitations.
**Notes:** Planned-only items remain background and cannot generate Skills or mastery.

---

## Evidence and responsibility attribution

### Attribution granularity

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Attribute every concrete work claim | ✓ |
| 2 | Use one responsibility label for the entire Contribution | |
| 3 | Attribute Evidence only | |

**User's choice:** Claim-level attribution.
**Notes:** User, team, other-person, non-responsibility, Codex-assisted, and third-party work may coexist in one Contribution.

### Document proof roles

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Give each document type a bounded proof role | ✓ |
| 2 | Treat every document type as equally strong | |
| 3 | Use audit reports only | |

**User's choice:** Typed Evidence with explicit limits.
**Notes:** Plans show intent; handoffs/acceptance record delivery; audits record observed state and limitations; user confirmation establishes personal responsibility for the fixture.

### Shared Evidence

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Store once and link to multiple claims with locators | ✓ |
| 2 | Copy Evidence into every Contribution | |
| 3 | Assign each document to one primary Contribution | |

**User's choice:** Store once and link.
**Notes:** Multiple references to one source do not become independent Evidence.

### Conflicting sources

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Preserve the conflict and require review | ✓ |
| 2 | Let the latest document win | |
| 3 | Let the audit report win automatically | |

**User's choice:** Preserve all conflicting sources.
**Notes:** The claim remains partial or unresolved, and definite mastery is prohibited until review.

---

## Known-good and known-bad fixture generation

### Known-good origin

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | System drafts candidates and the user confirms each item | ✓ |
| 2 | Treat extracted document content as known-good automatically | |
| 3 | Author the entire fixture manually | |

**User's choice:** Candidate extraction followed by human confirmation.
**Notes:** Only the confirmed version is known-good.

### Known-bad origin

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Copy known-good and violate exactly one rule | ✓ |
| 2 | Let a model freely generate erroneous cases | |
| 3 | Use only contradictions already found in source material | |

**User's choice:** Single-fault mutation from known-good.
**Notes:** This makes each rejection cause stable and automatically testable.

### Confirmation granularity

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Confirm facts, responsibility, Evidence links, status, and limitations separately | ✓ |
| 2 | Approve each Contribution as one package | |
| 3 | Approve the whole Experience only at the end | |

**User's choice:** Confirm each semantic component before sealing.
**Notes:** Unresolved items must be explicitly retained as unresolved rather than silently accepted.

### Phase 2 score meaning

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Use labeled test values or ranges without claiming calibration | ✓ |
| 2 | Assign exact real mastery scores now | |
| 3 | Omit all score cases until Phase 4 | |

**User's choice:** Test-only score expectations.
**Notes:** Scores exercise domain contracts and invariants; real calibration and aggregation remain Phase 4 work.

---

## the agent's Discretion

- Exact schema class and field names beyond the locked semantics.
- Fixture directory layout, deterministic identifier format, and section-locator syntax.
- Additional single-fault negative variants beyond required coverage.

## Deferred Ideas

- Phase 3: interactive Grill-Me audit and resumability.
- Phase 4: mastery calibration and aggregation.
- Phase 5: JD usefulness and adversarial full-loop evaluation.
- Later empirical work: résumé-submission, interview, hiring, and product-effectiveness outcomes.
