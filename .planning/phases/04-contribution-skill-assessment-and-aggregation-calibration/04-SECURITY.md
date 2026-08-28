---
phase: 04
slug: contribution-skill-assessment-and-aggregation-calibration
status: verified
# Counts only OPEN threats at or above workflow.security_block_on (high).
threats_open: 0
asvs_level: 1
created: 2026-08-28
---

# Phase 04 — Security

> Fresh L1 audit after gap remediation plans 04-06 through 04-08. This record verifies declared mitigations; it does not assert external effectiveness or reviewer authentication.

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| corpus declarations to calibration | Custody identifiers are assertions until derived from fixture, manifest, and completed confirmed audit bytes. | JSON identities and audit snapshot data |
| retained history to activation | Policy, result, and comparison content must be rehashed before activation references are trusted. | Calibration history and policy payloads |
| normal retry to reviewed assessment | A repeated CLI command must not become permission to replace reviewed state. | Requested audit/policy and persisted sidecar |
| reviewer or reassessment payload to current projection | Mutations require expected hashes and append-only version lineage. | Reviewer decisions and assessment versions |
| derived calibration evidence to user mastery | Synthetic or counterfactual support cannot raise reviewed-user-truth mastery. | Assessment records and aggregate results |
| validation evidence to completion claim | Offline deterministic tests establish contracts, not JD or job-market effectiveness. | Test evidence and planning claims |

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-04-G06-01 | Tampering | calibration audit custody | high | mitigate | Materialize completed confirmed audit and derive custody identities before input hashes. Evidence: `assessment.py:480-531,1363-1388`; `test_policy_calibration.py:362`. | closed |
| T-04-G06-02 | Tampering | retained policy runs and comparisons | high | mitigate | Recompute policy, result, and comparison semantics on read. Evidence: `assessment.py:1193-1208,1527-1568`; `test_policy_calibration.py:424`. | closed |
| T-04-G06-03 | Elevation of privilege | active policy ancestry | high | mitigate | Recompute and validate result, comparison, policy, and activation ancestry. Evidence: `assessment.py:1570-1611`; `history.json:4-28,494-500`. | closed |
| T-04-G06-04 | Repudiation | unkeyed content hashes | low | accept | Trusted-local single-operator scope only; SHA-256 detects local content identity, not hostile-writer authentication. | open — below high threshold (non-blocking) |
| T-04-G07-01 | Elevation of privilege | normal assessment rerun | high | mitigate | Validate and return the existing record; reject audit or policy mismatch. Evidence: `assessment.py:1135-1162`; `test_assessment_cli.py:186`. | closed |
| T-04-G07-02 | Tampering | reviewer correction lineage | high | mitigate | Append hash-linked versions and guard reassessment with current hash. Evidence: `assessment.py:1016-1119`; `cli.py:251-256,614-631`. | closed |
| T-04-G07-03 | Repudiation | review and reassessment history | medium | mitigate | Retain source audit, proposals, effective assessments, admission, reviews, and version hashes. Evidence: `domain/models.py:620-638`; `assessment.py:199-251`. | closed |
| T-04-G07-04 | Information disclosure | CLI error paths | medium | mitigate | Return structured generic errors and retain raw-answer redaction tests. Evidence: `cli.py:614-632,678-680`; `test_assessment_cli.py:121-144`. | closed |
| T-04-G08-01 | Elevation of privilege | mixed-authority promotion | high | mitigate | Partition exact Skill aggregation by authority and reject mixed promotion support. Evidence: `assessment.py:896-981`; `test_anchor_promotion.py:150`. | closed |
| T-04-G08-02 | Tampering | aggregate authority label | high | mitigate | Derive authority from validated partitions and reject mismatches. Evidence: `assessment.py:957-981`; `domain/models.py:669-696`. | closed |
| T-04-G08-03 | Repudiation | reviewed-user-truth support | medium | mitigate | Require audit-verified origin, substantive review, and immutable retained lineage for promotion support. Evidence: `assessment.py:779-837`; `test_anchor_promotion.py:187`. | closed |
| T-04-G08-04 | Information disclosure | calibration-only CLI disposition | low | accept | Emit only safe record IDs and authority disposition; raw audit answers remain outside aggregate errors. | open — below high threshold (non-blocking) |
| T-04-G08-05 | Misrepresentation | validation completion | medium | mitigate | Limit validation claims to deterministic offline contracts and forbid JD or job-market effectiveness claims. Evidence: `04-VALIDATION.md:9-21,29-50`. | closed |

*Status: open · closed · open — below high threshold (non-blocking). Only open threats at or above the configured `high` threshold count toward `threats_open`.*

## Accepted Risks Log

No accepted risks. `T-04-G06-04` and `T-04-G08-04` retain their explicit low-severity, non-blocking open status until an accountable owner elects to accept them; this audit does not make that decision on the user's behalf.

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open at/above high | Run By |
|------------|---------------|--------|--------------------|--------|
| 2026-08-28 | 13 | 11 | 0 | gsd-security-auditor (fresh L1 audit) |

## Sign-Off

- [x] All threats have a disposition (mitigate or accept).
- [ ] Accepted risks documented in Accepted Risks Log (no owner acceptance was supplied).
- [x] `threats_open: 0` confirmed for the configured `high` blocking threshold.
- [x] `status: verified` set after the 04-06 through 04-08 remediation evidence.

**Approval:** verified 2026-08-28 — blocking security gate clear; two low-severity non-blocking scope boundaries remain explicit.
