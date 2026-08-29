---
phase: 07-career-source-custody-and-private-workspace
verified: 2026-08-29T22:44:36Z
status: gaps_found
score: 2/7 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "The transform command binds its derived candidate to the explicitly requested logical source."
    status: failed
    reason: "The CLI ignores --source-id and selects the only capture in the workspace."
    artifacts:
      - path: "src/career_evidence_graph/cli.py"
        issue: "Lines 830-839 enumerate captures and never read args.source_id."
    missing:
      - "Resolve and verify the current capture for the requested source ID, or require an explicit capture ID."
  - truth: "An evaluator can verify every persisted transformation and its input capture before accepting its provenance."
    status: failed
    reason: "CareerSourceStore.verify() never enumerates or verifies transformation bundles."
    artifacts:
      - path: "src/career_evidence_graph/career_sources.py"
        issue: "Lines 341-367 verify declarations and captures only."
    missing:
      - "Traverse transformations with containment and exact-shape checks, then call fail-closed transformation verification."
  - truth: "Immutable captures remain bound to the declaration revision in effect when they were created."
    status: failed
    reason: "Capture verification validates source_id against mutable declarations/current.json; a valid later revision can invalidate historical capture lineage."
    artifacts:
      - path: "src/career_evidence_graph/domain/models.py"
        issue: "CareerSourceCapture has no declaration revision identifier or hash."
      - path: "src/career_evidence_graph/career_sources.py"
        issue: "Lines 122-131 use the mutable current declaration during capture verification."
    missing:
      - "Persist the declaration revision identity (preferably canonical hash) in each capture and verify against that immutable manifest."
  - truth: "All personal-data writes remain contained in the explicitly selected private workspace."
    status: failed
    reason: "Unchecked semantic subpaths can be symlinks; current-captures redirects a capture write outside the workspace."
    artifacts:
      - path: "src/career_evidence_graph/career_sources.py"
        issue: "Lines 178-182 mkdir/write current-captures without no-symlink containment validation."
    missing:
      - "Apply one non-symlink, resolve-below-workspace check to every semantic directory and manifest before every read, iteration, mkdir, or write."
  - truth: "Hostile controls in source text fail closed before custody processing."
    status: failed
    reason: "validate_source_bytes() does not reject Unicode bidi embedding, override, or isolate controls."
    artifacts:
      - path: "src/career_evidence_graph/career_sources.py"
        issue: "_UNSAFE_CODEPOINTS at line 23 omits U+202A-U+202E and U+2066-U+2069."
    missing:
      - "Reject bidi embedding/override/isolate controls and add parameterized regression cases."
---

# Phase 7: Career Source Custody and Private Workspace Verification Report

**Phase Goal:** The user can declare the career-source boundary while accepted facts remain traceable and raw career material remains contained in one private workspace.
**Verified:** 2026-08-29T22:44:36Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | The user can declare a source universe, unavailable sources, and a cutoff for one inventory revision. | ✓ VERIFIED | `CareerSourceUniverse` requires cutoff/categories/sources and validates availability; `test_declaration_requires_complete_unique_two_level_synthetic_registry` and the focused suite pass. |
| 2 | A transform binds to the explicitly requested logical source. | ✗ FAILED | Synthetic spot check with captured source `a` and requested source `b` returned `{"candidate_only": true, "transformed": true}`. `cli.py:830-839` never reads `args.source_id`. |
| 3 | An evaluator can trace derived candidate material through verified transformation lineage. | ✗ FAILED | After changing a stored transformation output hash, `CareerSourceStore.verify()` accepted the workspace. Its loop checks captures but never transformations (`career_sources.py:341-367`). |
| 4 | Historical captures remain traceable after a valid declaration revision changes the current source list. | ✗ FAILED | A synthetic capture under revision `r1` was rejected as `career-source-capture-invalid` after valid revision `r2` retired its source. Capture verification consults mutable `declarations/current.json`. |
| 5 | Raw career material remains contained in the selected private workspace. | ✗ FAILED | A synthetic `current-captures` symlink to a temporary sibling directory was followed; capture succeeded and wrote `a.json` outside the workspace. |
| 6 | Hostile source-text controls fail closed. | ✗ FAILED | Synthetic U+202E input was accepted by `validate_source_bytes`; bidi override/isolate controls are absent from `_UNSAFE_CODEPOINTS`. |
| 7 | Phase 7 custody operations create no inventory, graph, mastery, assessment, JD, gap, or resume authority. | ✓ VERIFIED | The career-source routes only create candidate-only declaration/capture/transformation records; focused regression includes `test_complete_synthetic_cli_flow_has_no_later_phase_authority_side_effects` and passed. |

**Score:** 2/7 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `src/career_evidence_graph/workspace.py` | Single explicit private-workspace resolver | ✗ INCOMPLETE | Used by the custody store, but `child()` only bounds lexical joins; downstream semantic paths are not all checked against symlink escape. |
| `src/career_evidence_graph/domain/models.py` | Strict declaration, capture, transformation, locator contracts | ✗ INCOMPLETE | Substantive and used, but captures do not bind an immutable declaration revision. |
| `src/career_evidence_graph/career_sources.py` | Candidate-only custody and lineage service | ✗ INCOMPLETE | Substantive and CLI-wired, but global transformation verification, historical linkage, full containment, and bidi rejection are absent. |
| `src/career_evidence_graph/cli.py` | Explicit `career-source --workspace` operator surface | ✗ UNWIRED | The `transform --source-id` interface is declared but not connected to source selection. |
| `tests/test_career_source_custody.py` | Declaration/capture/lineage regression coverage | ⚠️ PARTIAL | 47 focused tests pass with the security module, but no test covers revision retirement or global verification of a tampered transformation. |
| `tests/test_career_source_security.py` | Boundary/no-echo/containment regression coverage | ⚠️ PARTIAL | Covers raw-root symlinks but not semantic subpath symlinks or Unicode bidi controls. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| CLI `--workspace` | `PrivateWorkspace` | `CareerSourceStore(Path(args.workspace))` | PARTIAL | Explicit workspace is wired, but semantic namespace writes can escape through a symlink. |
| CLI `transform --source-id` | Current capture for that source | Source-ID lookup | NOT WIRED | `args.source_id` is never read on the transform route. |
| Capture/transformation manifests | Canonical hash and create-only storage | `sha256_digest`, `create_only_canonical_bundle` | PARTIAL | Capture hash linkage is checked, but `verify()` does not traverse transformations. |
| Capture | Immutable source-universe revision | Declaration revision identity | NOT WIRED | Verification uses mutable `current.json`, not the historic declaration. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| `CareerSourceStore.declare` | `CareerSourceUniverse` | Explicit CLI declaration / caller-provided JSON | Yes — immutable private manifest | ✓ FLOWING |
| `CareerSourceStore.capture` | Raw bytes and capture manifest | Explicit private input | Yes — raw vault plus capture bundle | ✗ ESCAPABLE | A semantic symlink can redirect a current-capture write outside the workspace. |
| `CareerSourceStore.transform` / `verify` | Transformation manifest | Stored private transformation bundle | No reliable verification path | ✗ DISCONNECTED | Global verifier omits the transformation namespace. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Focused Phase 7 regression suite | `uv run --locked python scripts/run_pytest.py -q tests/test_career_source_custody.py tests/test_career_source_security.py` | `47 passed in 2.76s` | ✓ PASS (coverage incomplete) |
| Phase 7 lint | `uv run --locked ruff check` on six scoped files | `All checks passed!` | ✓ PASS |
| Transform source selection | Synthetic temporary workspace, request source `b` with only source `a` captured | Exit 0; transformed unrelated capture | ✗ FAIL |
| Global transformation verification | Synthetic temporary workspace, tamper stored output hash, call `verify()` | Accepted | ✗ FAIL |
| Historical declaration linkage | Synthetic capture, valid revision retires source, verify old capture | Rejected as `career-source-capture-invalid` | ✗ FAIL |
| Semantic symlink containment | Synthetic `current-captures` symlink to sibling directory | Accepted; outside write observed | ✗ FAIL |
| Bidi control rejection | Synthetic U+202E source text | Accepted | ✗ FAIL |

### Probe Execution

Step 7c: SKIPPED — no phase-declared or conventional `probe-*.sh` files exist.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| INV-01 | 07-00 through 07-03 | Declare universe, unavailable sources, and cutoff | ✓ SATISFIED | Strict universe model and passing declaration tests establish the declared candidate-only boundary. |
| INV-06 | 07-00 through 07-03 | Trace accepted facts/Evidence to identity, hash, metadata, and transformations | ✗ BLOCKED | Transform selection is disconnected, global verification skips transformations, and captures are not bound to their historical declaration revision. |
| INV-07 | 07-00 through 07-03 | Private workspace with safe public/routine outputs | ✗ BLOCKED | An unchecked private semantic symlink writes outside the workspace; bidi controls are not fail-closed. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| `cli.py` | 830-839 | Required source selector is unused | 🛑 BLOCKER | Derived provenance can bind to the wrong logical source. |
| `career_sources.py` | 341-367 | Verification omits transformation namespace | 🛑 BLOCKER | Tampered derived lineage is reported verified. |
| `career_sources.py` | 122-131 | Mutable-current declaration used for historical capture verification | 🛑 BLOCKER | Valid historic provenance becomes unverifiable. |
| `career_sources.py` | 178-182 | Semantic subpath write without containment check | 🛑 BLOCKER | Private-workspace boundary can be escaped. |
| `career_sources.py` | 23, 275 | Bidi controls omitted from hostile-input gate | 🛑 BLOCKER | Reviewed source text can render differently from stored ordering. |
| `career_sources.py` | 169-184 | Raw object is written before create-only capture bundle publication | ⚠️ WARNING | A capture collision can leave unreferenced raw private retention. |

### Decision Coverage

All 20 trackable `07-CONTEXT.md` decisions are textually represented in shipped artifacts according to `check.decision-coverage-verify`. This non-blocking heuristic does not override the executable failures above.

### Gaps Summary

Five blocking gaps falsify the central custody contract. The focused suite proves only the single-capture, root-symlink, and direct-verification paths it exercises; it does not prove source selection, transformation traversal, historical declaration binding, every semantic symlink boundary, or bidi handling. None is explicitly assigned to a later roadmap phase: Phases 8–14 consume this custody boundary rather than repair it. No private career repository or material was accessed during verification.

---

_Verified: 2026-08-29T22:44:36Z_
_Verifier: the agent (gsd-verifier)_
