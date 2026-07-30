---
phase: 02
slug: domain-contracts-stoa-fixture-and-deterministic-invariants
status: verified
# threats_open counts OPEN threats at or above workflow.security_block_on (high).
threats_open: 0
asvs_level: 1
block_on: high
register_authored_at_plan_time: true
created: 2026-07-30
verified: 2026-07-30
---

# Phase 02 — Security

> Per-phase security contract for the domain contracts, STOA fixture, review,
> sealing, replay, and deterministic mutation-suite boundaries.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| JSON file → strict domain core | Untrusted fixture bytes enter frozen Pydantic contracts and deterministic aggregate invariants. | Structured career-evidence records |
| documentary metadata → personal claims | Documents may propose evidence, but cannot establish personal responsibility or capability without human review. | Career evidence and attribution |
| repeated evidence → assessment basis | Duplicate references cannot become independent support or alter a score. | Evidence links and assessment basis |
| indirect career source → assessment lineage | Experience, title, repository, résumé, and ontology proximity cannot become Contribution-grounded mastery. | Assessment provenance |
| ownership and assistance → definite assessment | User, team, other-person, Codex-assisted, and third-party work remain distinguishable. | Responsibility and assistance |
| normalization metadata → mastery records | Aliases and ontology relations remain descriptive and cannot mutate mastery. | Skill metadata |
| local STOA repositories → source manifest | Only named documentation at pinned Git objects may enter the fixture process. | Repository documentation |
| pinned documents → candidate ledger | Documents are bounded evidence proposals, not instructions or personal facts. | Candidate claims and proof limits |
| multiple source sections → STOA Experience | Consolidation must retain limitations, conflicts, attribution, and planned-only isolation. | Candidate Evidence and Contributions |
| candidate facts → human-authorized record | Only explicit per-candidate human decisions cross the personal-truth boundary. | Review decisions |
| checkpoint response → canonical review | Human decisions must transfer exactly, with reviewer identity and reasons. | Review authority and corrections |
| reviewed record → immutable formal bundle | Only fully validated reviewed truth may enter FormalRunStore. | Confirmed fixture and provenance |
| formal bundle → known-good JSON | Published output remains bound to verified immutable bytes during duplicate, concurrent, or interrupted execution. | Canonical fixture |
| known-good → mutation engine | Mutations operate on an in-memory deep copy and cannot rewrite accepted truth. | Sealed fixture copy |
| mutation declaration → invariant evaluator | Malformed or multi-fault declarations cannot masquerade as deterministic negative cases. | Typed mutation case |
| suite results → validation status | Missing, stale, zero-error, multi-error, or wrong-error cases cannot report green. | Validation result |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation / Evidence | Status |
|-----------|----------|-----------|----------|-------------|-----------------------|--------|
| T-02-01 | Spoofing | `ContributionClaim` / `ContributionSkillAssessment` | high | mitigate | Strict attribution and basis fields in `domain/models.py`; definite-assessment gates in `domain/invariants.py`. | closed |
| T-02-02 | Tampering | `Evidence` / `ClaimEvidenceLink` | high | mitigate | Global IDs, content identity, unique links, and aggregate link validation in `domain/models.py` and `domain/invariants.py`. | closed |
| T-02-03 | Elevation of Privilege | `AssessmentLineage` | high | mitigate | Contribution lineage is mandatory and prohibited source kinds fail deterministically. | closed |
| T-02-04 | Information Disclosure | model/CLI tracer | low | accept | Synthetic checked-in records only; the tracer reads no STOA source, secret, production data, user data, cache, or untracked path. See AR-02-01. | closed |
| T-02-05 | Elevation of Privilege | `AssessmentLineage` | high | mitigate | Closed source vocabulary and `validate_contribution_lineage` reject all six indirect mastery paths. | closed |
| T-02-06 | Spoofing | claim attribution gate | high | mitigate | Definite assessment rejects non-user, unconfirmed, unresolved, partial, or obscured assisted support. | closed |
| T-02-07 | Tampering | Evidence links / user-Skill views | high | mitigate | Unique IDs and links, one view per Skill, stable ordering, and no-mutation validation are tested in `tests/test_domain_invariants.py`. | closed |
| T-02-08 | Tampering | Skill alias / ontology metadata | high | mitigate | Normalization is metadata-only; canonical mastery bytes remain unchanged across relation changes. | closed |
| T-02-09 | Tampering | `verify_source_manifest` | high | mitigate | Four pins and ten paths are allowlisted; reads use pinned Git objects, unsafe paths fail, hashes are checked, and no working-tree fallback exists. | closed |
| T-02-10 | Information Disclosure | source ingestion | high | mitigate | Non-allowlisted and unsafe paths are rejected before parsing, excluding code, untracked files, caches, secrets, production/user data, and private operations material. | closed |
| T-02-11 | Spoofing | document → personal claim | high | mitigate | Documentary candidates remain unconfirmed and non-personal with proof limits until hash-bound human review. | closed |
| T-02-12 | Tampering | candidate consolidation | high | mitigate | Source coverage, durable-outcome grouping, limitations/conflicts, planned-only isolation, and unique Evidence identities are enforced. | closed |
| T-02-13 | Spoofing | human review checkpoint | high | mitigate | Reviewer identity and six explicit decisions per candidate are required; omitted or blanket decisions cannot seal. | closed |
| T-02-14 | Tampering | checkpoint decision packet | high | mitigate | The exact checkpoint response is retained in `02-04-SUMMARY.md` and hash-bound before sealing. | closed |
| T-02-15 | Repudiation | reviewer edits / rejections | medium | mitigate | Corrections require reasons; unresolved state and correction history are retained. | closed |
| T-02-16 | Spoofing | review materialization | high | mitigate | Candidate hash, checkpoint hash, reviewer, exact coverage, corrections, rejections, and unresolved decisions are validated. | closed |
| T-02-17 | Tampering | `seal_reviewed_fixture` | high | mitigate | Source, domain, and review checks run before FormalRunStore publication; manifest, lineage, and exact replay are verified before known-good materialization. | closed |
| T-02-18 | Repudiation | correction / review history | high | mitigate | The formal bundle retains original proposal and hash, corrections, reasons, reviewer, and checkpoint hash. | closed |
| T-02-19 | Tampering | known-good publication | high | mitigate | Exclusive atomic publication, divergent-overwrite rejection, temporary cleanup, and verified-bundle-only recovery are implemented. | closed |
| T-02-20 | Spoofing | fixture score interpretation | medium | mitigate | Fixture-only and non-calibration notices are retained; known-good carries no aggregation, JD, product-effect, or user-mastery conclusion. | closed |
| T-02-21 | Tampering | `apply_fixture_mutation` | high | mitigate | Mutations use a deep copy, closed operation kinds, exactly one operation, base-hash validation, and before/after base-byte assertions. | closed |
| T-02-22 | Repudiation | `FixtureMutationCase` | high | mitigate | Each case records ID, base hash, one operation, expected code, and stable actual result; invalid declarations fail closed. | closed |
| T-02-23 | Spoofing | shortcut / attribution / assistance cases | high | mitigate | Dedicated one-fault variants cover all declared shortcut and laundering classes and require one sole expected code. | closed |
| T-02-24 | Tampering | suite / validation status | high | mitigate | Exact inventory, sealed-base control, sole-code checks, deterministic ordering/repeat, and the full offline gate are required before green status. | closed |
| T-02-25 | Information Disclosure | mutation fixtures / diagnostics | low | accept | Cases contain only the reviewed fixture and declared structural mutations; source scope and sensitive-data exclusion occur before sealing. See AR-02-02. | closed |

*Status: open · closed · open — below high threshold (non-blocking).*

*Severity: critical > high > medium > low. Only open threats at or above
`workflow.security_block_on: high` count toward `threats_open`.*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-02-01 | T-02-04 | Residual disclosure risk is limited to synthetic, checked-in, offline tracer records. No STOA source, secret, production/user data, cache, or untracked path enters this boundary. | Phase 02 plan disposition | 2026-07-30 |
| AR-02-02 | T-02-25 | Mutation diagnostics operate only on the already reviewed fixture plus closed structural mutations. The pinned source allowlist and sensitive-source exclusion run before sealing. | Phase 02 plan disposition | 2026-07-30 |

These are Low-severity residual risks below the configured High blocking
threshold. Recording them closes the accepted dispositions; they do not
authorize broader source ingestion or production/user-data processing.

---

## Verification Evidence

- Independent `gsd-security-auditor` review classified 23 mitigations as
  implemented and the two planned Low-risk acceptances as requiring this log.
- No unregistered `## Threat Flags` were present in Phase 02 summaries.
- The auditor reran the security-relevant offline fixture and domain checks:
  **115 passed**.
- The deterministic fixture suite accepted the sealed known-good control and
  all **16** one-fault cases with exactly their declared sole error codes.
- The active known-good remains provenance-bound to confirmed-result hash
  `sha256:f393c1034a6d604ae915a18dac3bd206ce146e9c050b4e938048eb10a6378242`.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-30 | 25 | 23 | 2 non-blocking, pending accepted-risk documentation | `gsd-security-auditor` |
| 2026-07-30 | 25 | 25 | 0 | Codex orchestrator |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-30
