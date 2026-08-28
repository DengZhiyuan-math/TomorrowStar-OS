---
phase: 05-jd-usefulness-and-adversarial-evaluation
plan: "02"
subsystem: jd-intake-and-evaluation-custody
tags: [python, argparse, pydantic, immutable-storage, security, jd-comparison]
requires:
  - phase: 05-01
    provides: content-bound accepted-JD packet and reviewed-user-truth comparison contracts
provides:
  - Provider-independent, fail-closed raw JD prepare and explicit accept boundaries
  - Ignored private intake storage and read-only JD workflow inspection
  - Forward-only route-only priority inputs and a content-free evaluation charter
affects: [05-03, 05-04, jd-intake, adversarial-evaluation]
actuals:
  tokens: 25490
  tasks: 3
  commits: 8
tech-stack:
  added: []
  patterns:
    - Exact raw-byte custody with safe code-point disclosures and redacted errors
    - Create-only canonical JSON bundles shared by formal-run and JD private storage
    - Route-only private priority overlay over unchanged comparison truth
key-files:
  created:
    - tests/test_jd_security.py
    - validation/jd/README.md
    - validation/jd/proposal.schema.json
    - validation/jd/evaluation-charter.json
  modified:
    - src/career_evidence_graph/jd.py
    - src/career_evidence_graph/cli.py
    - src/career_evidence_graph/validation/store.py
    - .gitignore
key-decisions:
  - "Raw JD bytes are validated and source-bound before any private bundle write; no provider or silent repair path exists."
  - "Priority-company preference is a separate forward-only private input that changes only the final route and reason."
  - "The evaluation inventory, fallback baseline, blind review conditions, and no-employment-effectiveness limitation are frozen without any JD body."
patterns-established:
  - "Use `JDIntakeStore` for private prepared and accepted packet custody and `jd inspect` for redacted read-only status."
  - "Use `create_only_canonical_bundle` for immutable declared JSON bundles without altering FormalRunManifest semantics."
requirements-completed: [JD-04]
coverage:
  - id: D1
    description: Raw JD intake rejects malformed, hidden, oversized, mismatched, and unsafe source/proposal inputs before acceptance or scoring.
    requirement: JD-04
    verification:
      - kind: integration
        ref: tests/test_jd_security.py#test_prepare_enforces_exact_byte_ceiling_before_any_proposal_parse
        status: pass
      - kind: integration
        ref: tests/test_jd_security.py#test_prepare_cli_keeps_one_private_packet_unaccepted
        status: pass
    human_judgment: false
  - id: D2
    description: Priority preference remains a forward-only route overlay and the preregistered evaluation charter remains content-free and complete.
    requirement: JD-04
    verification:
      - kind: unit
        ref: tests/test_jd_security.py#test_priority_overlay_changes_only_route_reason_and_forward_list_version
        status: pass
      - kind: unit
        ref: tests/test_jd_security.py#test_checked_in_evaluation_charter_rejects_missing_preregistered_field
        status: pass
    human_judgment: false
duration: 10min
completed: 2026-08-28
status: complete
---

# Phase 05 Plan 02: Secure JD Intake and Evaluation Custody Summary

**A provider-independent private JD prepare/accept boundary with exact-byte security checks, read-only workflow status, route-only priority versions, and a preregistered content-free evaluation charter.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-08-28T17:14:30Z
- **Completed:** 2026-08-28T17:24:20Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments

- Validated one raw UTF-8 source and its recorded packet before publishing an unaccepted private bundle; controls, invalid UTF-8, bad IDs, oversize sources, and mismatches fail closed without leaking source text.
- Added ignored `.career-evidence/phase-05` prepare/accept custody, safe `jd inspect` status, and read-only unmet workflow expectations with exit status 2.
- Preregistered priority overlays and the development-only evaluation inventory, fallback, blind-review rule, zero-fabrication gate, and D-19 limitation without adding any JD body or fixture.

## Task Commits

1. **Task 1: Reject unsafe raw JD input and stale graph custody before authority exists** - `fc92be8`, `899a0bd` (test → feat)
2. **Task 2: Wire private prepare, accept, inspect, and zero-publication CLI flows** - `8b53a97`, `24321b5` (test → feat)
3. **Task 3: Preregister route-only preference and the blind evaluation charter** - `ace472d`, `b82932e` (test → feat)
4. **Follow-up correctness fix: expose safe `jd inspect` status without an expectation** - `d01b124`, `8bdeba1` (test → fix)

## Files Created/Modified

- `.gitignore` - Excludes the fixed private `.career-evidence/` runtime root.
- `src/career_evidence_graph/jd.py` - Raw-source validation, private prepare/accept custody, inspect status, priority overlay/versioning, and charter validation.
- `src/career_evidence_graph/cli.py` - Adds `jd prepare`, `jd accept`, and `jd inspect` commands with structured redacted failures.
- `src/career_evidence_graph/validation/store.py` - Reusable atomic create-only canonical JSON bundle helper.
- `tests/test_jd_security.py` - Content-free raw-input, CLI, private-storage, priority, and charter adversarial coverage.
- `validation/jd/README.md` - D-20 fixture-custody and private-workspace instructions.
- `validation/jd/proposal.schema.json` - Checked-in recorded-proposal contract marker.
- `validation/jd/evaluation-charter.json` - Content-free preregistered evaluation inventory and boundaries.

## Decisions Made

- `max_raw_jd_bytes=262144` is enforced before proposal parsing or any storage write; exact equality proceeds to ordinary validation.
- Unsafe code points are reported only by code-point labels, never copied from a private source.
- A priority-company match preserves the comparison payload and changes only its final route/reason; list versions are create-only.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added safe status output when `jd inspect` is called without `--expect`**

- **Found during:** Final plan verification
- **Issue:** The command accepted an optional expectation argument but rejected the no-expect inspection flow instead of exposing the required redacted status.
- **Fix:** Added a read-only status projection with prepared/accepted counts and evaluation presence; it never creates the private workspace.
- **Files modified:** `src/career_evidence_graph/jd.py`, `src/career_evidence_graph/cli.py`, `tests/test_jd_security.py`
- **Verification:** `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_security.py tests/test_security_boundaries.py tests/test_run_store.py tests/test_policy_calibration.py -x`
- **Committed in:** `8bdeba1`

**Total deviations:** 1 auto-fixed (1 Rule 1 bug fix).

## Issues Encountered

The sandbox could not read the existing uv cache, so verification ran through the approved locked offline command path. No dependency installation or network access occurred.

## Known Stubs

None. The deliberately content-free charter does not provide an evaluation output, corpus, or real JD input; those are explicitly deferred to Plans 05-03 and 05-04.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 05-03 can stop at its explicit D-20 user-fixture checkpoint with the repository content-free. Plan 05-04 can reuse the immutable bundle helper and preregistered charter after accepted fixtures exist.

## Verification

- `uv run --offline --locked python scripts/run_pytest.py -q tests/test_jd_security.py tests/test_security_boundaries.py tests/test_run_store.py tests/test_policy_calibration.py -x` — **64 passed**
- `uv run --offline --locked ruff check .` — **passed**
- `uv run --offline --locked ruff format --check .` — **62 files already formatted**

## Self-Check: PASSED

- Task commits `fc92be8`, `899a0bd`, `8b53a97`, `24321b5`, `ace472d`, `b82932e`, `d01b124`, and `8bdeba1` exist in Git history.
- All eight plan-owned implementation, test, configuration, and content-free contract files exist.

---
*Phase: 05-jd-usefulness-and-adversarial-evaluation*
*Completed: 2026-08-28*
