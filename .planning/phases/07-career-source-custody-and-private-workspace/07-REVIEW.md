---
phase: 07-career-source-custody-and-private-workspace
reviewed: 2026-08-30T22:53:24Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - src/career_evidence_graph/workspace.py
  - src/career_evidence_graph/domain/models.py
  - src/career_evidence_graph/career_sources.py
  - src/career_evidence_graph/cli.py
  - tests/test_career_source_custody.py
  - tests/test_career_source_security.py
findings:
  critical: 5
  warning: 0
  info: 0
  total: 5
status: resolved
---

# Phase 07: Code Review Report

**Reviewed:** 2026-08-30T22:53:24Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** resolved

## Summary

The six scoped files were read in full against Phase 07's explicit-workspace, full-OID, symlink, raw-byte, and synthetic-only contracts. The original review found five custody boundary violations; all five are resolved by the commits recorded in `07-REVIEW-FIX.md`. The full source-aware synthetic custody and security suites now pass (`132 passed`), and scoped Ruff passes.

## Resolution

All five blockers are resolved. The final regression migration in `7727182` updates only synthetic test helpers and call sites to construct and pass an explicit full-OID Git baseline; it adds no production fallback or unanchored mutation path.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Store mutations can bypass the mandatory explicit Git snapshot

**Classification:** BLOCKER

**File:** `/Users/zhdeng/Documents/TomorrowStar OS/src/career_evidence_graph/career_sources.py:216`

**Issue:** `capture()` and `transform()` make `expected_workspace_commit` optional and only authenticate it when callers happen to supply one (lines 250-251 and 375-376). Any in-process caller, including `run_synthetic_tracer()` (lines 1225-1241), can therefore write raw bytes, manifests, and current pointers without a full-OID baseline. This directly contradicts Plan 07-08's requirement that store mutation routes, not merely the CLI parser, carry an explicit baseline and makes cleanup unable to prove committed/working absence for those calls. A synthetic reproduction accepted an unanchored `store.capture()`.

**Fix:** Make the keyword-only parameter required (`expected_workspace_commit: str`), call `_commit_blob_inventory()` unconditionally before any mutation, and update the test/build helpers to establish and pass a synthetic baseline. Remove or constrain `run_synthetic_tracer()` so it cannot offer an unanchored mutation path.

### CR-02: Declaration manifests can be read through an unchecked symlink

**Classification:** BLOCKER

**File:** `/Users/zhdeng/Documents/TomorrowStar OS/src/career_evidence_graph/career_sources.py:1825`

**Issue:** `_read_declaration()` builds `self.root / "declarations" / revision_id / "manifest.json"` directly instead of using `_semantic_path()`. `declare()` similarly follows an unchecked predecessor bundle at line 125. A symlink at `declarations/<revision_id>` can redirect declaration verification outside the selected workspace; `_declaration_binding()` then trusts that external manifest during capture. A synthetic reproduction replaced the revision directory with a symlink and `capture()` succeeded.

**Fix:** Resolve both declaration reads and predecessor checks through a strict semantic manifest helper such as `_semantic_path(f"declarations/{revision_id}/manifest.json")`, and reject a symlinked bundle or leaf before every access. Add regression cases for declaration-bundle and declaration-manifest symlinks on `declare`, `capture`, and verification.

### CR-03: Transformed output bytes bypass the bidi/control gate before raw publication

**Classification:** BLOCKER

**File:** `/Users/zhdeng/Documents/TomorrowStar OS/src/career_evidence_graph/career_sources.py:352`

**Issue:** `transform()` hashes and writes caller-supplied `output_bytes` at lines 352-369 and 390-396 without calling `validate_source_bytes()` or the shared bidi-control check. The normal CLI currently transforms existing capture bytes, but the public store API accepts arbitrary output bytes. Consequently a transformation can publish U+202A–U+202E/U+2066–U+2069 bytes despite the Phase 07 requirement that these controls be rejected before hashing or raw publication. A synthetic direct transform accepted U+202E output.

**Fix:** Validate every transformed output byte payload with the same raw-content control policy before calculating `output_hash` or touching the raw vault. Add a direct-store regression for all nine controls in `output_bytes`, asserting no raw object, output manifest, transformation manifest, pointer, or ref is created.

### CR-04: Routine status follows semantic namespace symlinks and leaks external counts

**Classification:** BLOCKER

**File:** `/Users/zhdeng/Documents/TomorrowStar OS/src/career_evidence_graph/career_sources.py:1296`

**Issue:** `safe_status()` checks only `sources` and then directly traverses `declarations`, `captures`, and `transformations` (lines 1309-1324). A symlinked `captures` directory is followed by `glob()` and its entries are returned as `capture_count`, contrary to the required rejection of every semantic namespace symlink and the content-safe routine-output boundary. A synthetic reproduction pointed `captures` at a sibling directory with two entries and received `capture_count: 2`.

**Fix:** Route all status inspection through the same no-symlink semantic traversal used for snapshot inventory (or validate each namespace with `PrivateWorkspace` immediately before enumeration). Return a stable safe error on a symlink rather than reporting derived counts. Cover declarations, captures, current-captures, transformations, migration receipts, derived outputs, and raw.

### CR-05: Check-then-use path handling permits operation-time symlink swaps

**Classification:** BLOCKER

**File:** `/Users/zhdeng/Documents/TomorrowStar OS/src/career_evidence_graph/career_sources.py:264`

**Issue:** `PrivateWorkspace.child()` validates a path before returning it, but callers later perform separate `exists()`/`is_symlink()` checks and path-based opens. For example, capture checks `raw_path.is_symlink()` and then uses `raw_path.open("xb")` at lines 264-271; transformation repeats the pattern at lines 390-395. An attacker with access to the selected workspace can replace the leaf or parent with a symlink in that interval, making the later open/read/write follow the replacement. This violates the explicit Plan 07-08 operation-time-swapped-symlink requirement and can write raw material outside the selected workspace.

**Fix:** Perform raw and semantic reads/writes relative to a verified directory descriptor, using `lstat` plus no-follow descriptor operations (`dir_fd`/`O_NOFOLLOW` where available) immediately at the operation. Revalidate parent identity before atomic replace/unlink, and treat any change as a redacted path-unsafe failure. Add deterministic swap tests around raw creation, manifest creation, pointer replacement, and cleanup.

---

_Reviewed: 2026-08-30T22:53:24Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
