---
phase: 07-career-source-custody-and-private-workspace
reviewed: 2026-08-30T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - src/career_evidence_graph/career_sources.py
  - src/career_evidence_graph/cli.py
  - src/career_evidence_graph/domain/models.py
  - src/career_evidence_graph/workspace.py
  - tests/test_career_source_custody.py
  - tests/test_career_source_security.py
findings:
  critical: 5
  warning: 1
  info: 0
  total: 6
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-08-30T00:00:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

The reviewed implementation has correct basic synthetic-path coverage, but it does not yet preserve the promised custody and privacy invariants under declaration evolution, transformation tampering, adversarial namespace links, or non-ASCII bidi controls. The CLI also fails to select the capture named by its required `--source-id` argument.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01 [BLOCKER]: Transform ignores the requested source and only works when exactly one capture exists

**File:** `src/career_evidence_graph/cli.py:830`
**Issue:** `career-source transform --source-id` never reads or validates `args.source_id`. Instead it enumerates every capture and accepts only a workspace containing exactly one. A valid declared universe with two captured logical sources therefore cannot be transformed at all; worse, a caller can name a different source ID and get a transformation bound to the sole unrelated capture. This breaks the stable logical-source/capture provenance contract.
**Fix:** Resolve the explicit current-capture pointer for `args.source_id` (or require an explicit capture ID), validate its manifest through `CareerSourceStore._verify_capture`, and reject an absent/mismatched pointer. Do not derive selection from the total number of capture directories.

### CR-02 [BLOCKER]: `verify` reports success without verifying any transformation

**File:** `src/career_evidence_graph/career_sources.py:341`
**Issue:** Global verification checks declaration and capture bundles only. It never traverses `transformations`, calls `verify_transformation`, or rejects extra files/symlinks in a transformation bundle. Consequently a stored transformer identity, output hash, or locator can be altered after recording and `career-source verify` still emits `verified: true`. That falsely attests to the provenance of every derived candidate.
**Fix:** Enumerate `transformations` as a non-symlink directory, require each bundle to have the exact manifest-only shape, and verify each stored transformation against its verified input capture. Reject malformed, undeclared, symlinked, or mismatched transformation records before returning success.

### CR-03 [BLOCKER]: Captures are tied to mutable `current.json`, invalidating valid historical evidence after a declaration revision

**File:** `src/career_evidence_graph/career_sources.py:122`
**Issue:** `_verify_capture` validates a capture's `source_id` only against `declarations/current.json`. A later valid revision can retire or rename a source while preserving the earlier declaration and capture; after that update, every old capture for the retired source fails verification. `CareerSourceCapture` has no declaration-revision hash/ID to bind it to the immutable registry that was current when it was recorded. This violates immutable historical capture lineage and prevents later consumers from relying on prior captures.
**Fix:** Add the declaration revision ID (and preferably its canonical hash) to `CareerSourceCapture`, validate it at creation, and use that immutable declaration manifest during verification. Validate predecessor declaration lineage separately rather than substituting the mutable current pointer.

### CR-04 [BLOCKER]: Private semantic subpaths can follow symlinks outside the selected workspace

**File:** `src/career_evidence_graph/career_sources.py:67`
**Issue:** Only `.career-evidence`, `sources`, and `raw` are checked in `_ensure_root`. Subdirectories/files subsequently read or written (`declarations`, `captures`, `current-captures`, `transformations`, and `current.json`) are not consistently checked as non-symlinks resolving below `PrivateWorkspace.root`. For example, an attacker-controlled `current-captures` symlink is followed by `mkdir` and `atomic_write_canonical_json` at lines 178-182, allowing a capture operation to write outside the selected private workspace. Declaration/current manifest reads similarly follow linked paths.
**Fix:** Centralize a helper that opens/validates every semantic directory and manifest: reject symlinks, require `resolve(strict=True).is_relative_to(self.workspace.root)`, and use it before every read, `iterdir`, `mkdir`, or atomic write. Apply it to both existing and newly created namespaces.

### CR-05 [BLOCKER]: Bidi override/isolate characters bypass the hostile-text rejection gate

**File:** `src/career_evidence_graph/career_sources.py:23`
**Issue:** The security boundary rejects NUL and five zero-width code points, but permits Unicode bidi override and isolate controls such as `U+202E` and `U+2066`. The phase requires hostile control/bidi/zero-width input to fail closed; these controls can make reviewed source text render differently from its logical ordering, defeating safe text/JSON review.
**Fix:** Extend the rejected set to include bidi embeddings/overrides/isolate controls (`U+202A`–`U+202E`, `U+2066`–`U+2069`) and add parameterized regression tests for each class. Keep ordinary line breaks/tabs only if they are explicitly supported by the raw-text contract.

## Warnings

### WR-01 [WARNING]: A failed capture can leave an unreferenced private raw object behind

**File:** `src/career_evidence_graph/career_sources.py:169`
**Issue:** `capture` writes the raw bytes before publishing the create-only capture manifest. If `create_only_canonical_bundle` then fails because the capture ID already exists, the command returns an error but the new raw object remains in the vault without a capture manifest or lineage. This creates undeclared private retention and makes retry/cleanup behavior ambiguous.
**Fix:** Stage the raw object and manifest together, or remove a newly-created raw object when manifest publication fails and no existing capture references its hash. Add a collision test asserting the raw-vault contents are unchanged after failure.

---

_Reviewed: 2026-08-30T00:00:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
