---
phase: 05-jd-usefulness-and-adversarial-evaluation
plan: "01"
subsystem: jd-comparison
tags: [python, pydantic, argparse, deterministic-scoring, career-evidence]
requires:
  - phase: 04-contribution-skill-assessment-and-aggregation-calibration
    provides: reviewed-user-truth assessment lineage and exact-Skill aggregation
provides:
  - Content-free accepted-JD source, proposal, span, judgment, policy, report, and result contracts
  - Pure reviewed-user-truth comparison with deterministic score, core cap, route, gap, and source-selection projections
  - Offline CLI tracer and adversarial boundary tests without any real JD fixture
affects: [05-02, 05-03, jd-intake, adversarial-evaluation]
actuals:
  tokens: 14844
  tasks: 3
  commits: 6
tech-stack:
  added: []
  patterns:
    - Frozen content-bound packet contracts with reconstructable UTF-8 byte spans
    - Read-only deterministic relevance projection over existing reviewed-user-truth mastery
    - Inclusive integer policy routing with evidence-only customization overlay
key-files:
  created:
    - tests/test_jd_models.py
    - src/career_evidence_graph/jd.py
  modified:
    - src/career_evidence_graph/domain/models.py
    - src/career_evidence_graph/domain/invariants.py
    - src/career_evidence_graph/cli.py
    - tests/test_jd_comparison.py
key-decisions:
  - "Accepted source spans and recorded proposal JSON are independently content-bound before comparison."
  - "JD relevance remains a pure projection: ordinary routing uses capped integer scores, and only direct high-confidence reviewed-user-truth evidence can apply the evidence-strong overlay."
  - "Positive and partial judgments retain every exact Skill constituent plus admitted Contribution evidence and an explicit limitation."
patterns-established:
  - "Canonical JD projections sort by relevance rank, source byte offset, then stable identifier."
  - "A JD may change only derived judgments, gaps, selections, score, and route; graph hashes must remain unchanged."
requirements-completed: [JD-02, JD-03, JD-04]
coverage:
  - id: D1
    description: Checkout-source CLI compares one schema-only accepted packet against reviewed-user-truth lineage without graph mutation.
    requirement: JD-02
    verification:
      - kind: e2e
        ref: tests/test_jd_comparison.py#test_schema_only_packet_reaches_checkout_cli_without_mutating_reviewed_graph
        status: pass
    human_judgment: false
  - id: D2
    description: Strict packet custody rejects empty, duplicate, extra, non-reconstructing, and ungrounded inputs and canonically orders projections.
    requirement: JD-04
    verification:
      - kind: unit
        ref: tests/test_jd_models.py
        status: pass
    human_judgment: false
  - id: D3
    description: Integer score thresholds, core caps, exact-Skill evidence-strong combinations, typed gaps, and immutable graph projections are deterministic offline.
    requirement: JD-03
    verification:
      - kind: unit
        ref: tests/test_jd_comparison.py#test_scoring_uses_inclusive_thresholds_and_core_cap_without_mutating_graph
        status: pass
      - kind: unit
        ref: tests/test_jd_comparison.py#test_evidence_strong_exception_requires_every_ordered_skill_constituent
        status: pass
    human_judgment: false
duration: 17min
completed: 2026-08-28
status: complete
---

# Phase 05 Plan 01: JD Comparison Architecture Summary

**A content-free, reviewed-user-truth-only JD comparison path with source-custodied packets, deterministic 0–100 scoring and routing, typed gaps, and truthful Contribution selection.**

## Performance

- **Duration:** 17 min
- **Started:** 2026-08-28T16:52:12Z
- **Completed:** 2026-08-28T17:09:19Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- Added a checkout-source `jd analyze` tracer that accepts one schema-only packet, validates reviewed-user-truth lineage, emits deterministic JSON, and preserves graph bytes.
- Bound accepted packets to retained UTF-8 source bytes, reconstructable spans, recorded proposal JSON, exact Skill constituents, Contribution evidence, and canonical presentation order.
- Added inclusive integer score boundaries, non-compensating core caps, direct high-confidence evidence-strong routing, four typed gaps, and report projections that make no employment-effectiveness claim.

## Task Commits

1. **Task 1: Carry one accepted requirement through reviewed graph verification to a JSON route** - `644e0e8`, `a9973b0` (test → feat)
2. **Task 2: Close strict accepted-packet, judgment, source-span, and ordering boundaries** - `cfb7893`, `9e6340e` (test → feat)
3. **Task 3: Expand transparent scoring, core caps, evidence routing, gaps, and report projections** - `82dfded`, `7c74aeb` (test → feat)

## Files Created/Modified

- `src/career_evidence_graph/domain/models.py` - Frozen JD custody, policy, judgment, gap, selection, report, and result contracts.
- `src/career_evidence_graph/domain/invariants.py` - Canonical ordering for requirements, judgments, evidence, gaps, and selected Contributions.
- `src/career_evidence_graph/jd.py` - Pure reviewed-user-truth graph loading, exact-Skill comparison, scoring, routing, gap, and report projection.
- `src/career_evidence_graph/cli.py` - Existing stdlib CLI integration kept lint-clean for `jd analyze`.
- `tests/test_jd_models.py` - Schema-only source and proposal custody, grounding, and ordering probes.
- `tests/test_jd_comparison.py` - Offline tracer, threshold, cap, combination, gap, and isolation probes.

## Decisions Made

- Stored proposal JSON is hashed as its exact retained bytes, while its declared source identity must still match the packet's raw source hash and ID.
- Score thresholds are inclusive and use integer floor arithmetic; a missing unsupported or uncertain core hard requirement applies the policy cap before ordinary routing.
- The `evidence-strong-match` overlay requires direct high-confidence admitted reviewed-user-truth evidence for every exact Skill constituent, including every member of a linked group.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated the existing tracer for the newly strict packet and positive-judgment contracts**

- **Found during:** Task 2
- **Issue:** The Task 1 schema-only packet lacked the now-required recorded proposal JSON/hash, and the prior positive judgment projection did not expose the exact-Skill evidence basis required by the stricter model.
- **Fix:** Added the content-bound synthetic proposal fields to the tracer and preserved exact-Skill evidence IDs, established capability, and an explicit limitation in positive/partial projections.
- **Files modified:** `tests/test_jd_comparison.py`, `src/career_evidence_graph/jd.py`
- **Verification:** `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_models.py tests/test_jd_comparison.py tests/test_skill_aggregation.py tests/test_domain_invariants.py -x`
- **Committed in:** `9e6340e`

**Total deviations:** 1 auto-fixed (1 Rule 3 blocking compatibility repair).

## Verification

- `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_models.py tests/test_jd_comparison.py tests/test_skill_aggregation.py tests/test_domain_invariants.py -x` — **44 passed**
- `uv run --offline --locked ruff check src/career_evidence_graph/domain/models.py src/career_evidence_graph/domain/invariants.py src/career_evidence_graph/jd.py src/career_evidence_graph/cli.py tests/test_jd_models.py tests/test_jd_comparison.py` — **passed**

## Known Stubs

None. The plan intentionally uses only synthetic schema probes and does not create real JD bodies, companies, résumé wording, or a numeric policy fixture.

## Self-Check: PASSED

- Summary file exists and all six Task 1–3 TDD commits are present in Git history.

## Next Phase Readiness

Plan 05-02 can add hostile-input, intake, and read-only inspection boundaries atop the content-free accepted-packet and comparison core. Real user-supplied JD fixtures remain blocked behind the later explicit checkpoint.

---
*Phase: 05-jd-usefulness-and-adversarial-evaluation*
*Completed: 2026-08-28*
