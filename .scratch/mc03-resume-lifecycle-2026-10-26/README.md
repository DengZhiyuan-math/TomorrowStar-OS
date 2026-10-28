# Resume lifecycle ownership

Date: 2026-10-26, Europe/Zurich. Status: complete for checkout source and
related synthetic verification; the ticket is closed. This record concerns
[the Resume lifecycle ticket](../module-completion-2026-10-26/issues/03-resume-lifecycle-interface.md).

## Change

Resume now owns normal preparation, retained-material and PDF reuse selection,
template selection, saved handoff continuation, reviewed version adoption and
complete material reads. Portal assembles the existing input providers and calls
these operations. Flow retains task admission, attempts, cancellation and
conditional adoption. Its remaining material structure checks and source
projections delegate to Resume-owned functions, including the existing standalone
Flow callback path.

The existing author state, generation adapters, immutable versions, mapped-import
successors and PDF archive implementations remain in use. No new material store,
author state machine, model provider or dependency was introduced. The existing
legacy entrypoints and response shapes remain available.

`progress_generation` accepts the existing ID selector and validates immutable
reference fields when supplied. Mutable progress snapshots do not override saved
state. Preparation checks saved handoff inputs before author calls. Flow can adopt
a new candidate only when its complete material projection matches the verified
archive; a matching ID/hash alone cannot replace saved wording.

Material-contract classification now belongs to Resume. Flow keeps its public
compatibility function and delegates to the same unchanged rule; Resume does not
gain a new dependency on the Flow controller.

## PDF effects

| Operation | Effect |
| --- | --- |
| `build_pdf` | Uses the existing material-specific build/capture path; an existing attempt is reconciled before any new work. |
| `capture_compiled_pdf` | Reads an already completed Prism result and saves a verified local archive, even if the App never requested a build; it does not compile. The prior argument form remains supported. |
| `read_pdf` | Reads and verifies the saved PDF and its material binding, including declared content/template/renderer and human-successor identities; it does not request a new build. |
| `reconcile_build` | Reads the original registered attempt and verified receipt. Missing/unknown results remain unresolved; this operation cannot create a fresh capture. |

The default Portal previously routed a local-material export recheck through
capture before examining the reconcile flag. A Flow regression reproduced that
behavior. Rechecks now call the owner’s reconcile operation. A separate Flow
regression covers a completed PDF whose response was lost: recovery retains the
same ID and bytes after later human source edits, without contacting Prism.
Build and reconcile request IDs must match the attempt already registered on the
task. An explicit capture can still use its separately registered capture ID.

## Acceptance coverage

| Ticket requirement | Implementation and verification entry |
| --- | --- |
| Normal preparation/reuse, version adoption and read belong to Resume | `prepare`, `read`, `validate_prepared`, `verify_for_task`, `select_template`; default Portal/Flow integration and existing independent preparation tests. |
| Handoff identity is explicit; no second author state | `progress_generation`, saved input check in `generation_state`; fixed-field, stale-progress, input-conflict and original author recovery tests. |
| Distinct build/capture/read/reconcile effects | Four Resume operations; `test_resume_pdf_interface.py` and `test_resume_lifecycle_flow.py`. |
| Preserve response loss, drift, corruption and human successors | Original version/reconciliation regressions plus saved-PDF recovery, tamper rejection and mapped/unmapped successor tests. |
| Default and independent consumers retain their contracts | Existing Flow, Portal, retained baseline, PDF reuse, explicit LaTeX import/export and browser cases. |

## Evidence

The implementation diff is measured against `before/`, captured from the dirty
checkout at task entry, rather than against Git HEAD. It changes four production
files and two existing test files, and adds three test files with 33 additional
parameterized cases overall. See `change-summary.json`, `final-diff.patch` and
`review-source-final.json`. Pre-existing edits are retained.

- [Preparation implementation and red/green records](preparation/implementation.md).
- [PDF implementation and red/green records](pdf/implementation.md).
- `integration/reconcile-red.log` preserves the reproduced default recheck defect;
  `integration/reconcile-green.log` records the first passing check.
- The initial consumer selection passed 83 tests; the later template/Flow selection
  passed 22. These are intermediate checks, not the final frozen-suite result.
- Final verification passed on one unchanged 668-file snapshot: full default
  offline 7,755 passed and two explicit opt-in benchmark skips, followed by
  102 related isolated browser passes. Both JUnit reports exactly cover their
  disjoint collected manifests. Ruff, format and diff checks passed. See
  [final verification](final-verification.json), `verification/offline-final-r2/`
  and `verification/browser-final/`. The two test layers ran sequentially.
- [Preparation/consumer review](reviews/preparation-review.md) found a new
  Resume-to-Flow dependency in material classification. The rule was moved to
  Resume and its AST matched the original; the reviewer verified the correction.
- [PDF review](reviews/pdf-review.md) reproduced request-ID bypass of an unknown
  build and omitted PDF reference identities. Both were fixed and added to the
  permanent regressions. Independent rechecks passed the four original counterexamples
  and three compatibility cases; the revised six-file PDF selection passed 93 tests.
- The original full-suite batch was deliberately stopped after the PDF findings.
  `verification/offline-interruption.json` and the original `verification/offline/`
  preserve it. It is not a passing full-suite result. Final checks use
  `verification/offline-final-r2/` on the corrected source.
- The first completed frozen batch (`verification/offline-final/`) recorded
  7,752 passed, two opt-in skips and three failures. The grouped-review export
  callback required the original keyword argument calling convention; it is
  restored. Two scheduler cases paired a synthetic draft producer with the real
  archive verifier; their fixture now supplies the matching in-memory validation
  port. Production archive validation is unchanged. The affected 15 cases passed,
  and both independent reviewers approved the corrections. This failed batch
  remains preserved and is excluded from final passing evidence.

- The first browser batch (`verification/browser/`) failed during Chromium launch
  with `TargetClosedError`, `SIGABRT` and `kill EPERM` in the restricted environment.
  All 102 cases retained their failure/setup records; none is counted as a behavior
  pass. The same frozen selection is rerun with host browser-launch permission in
  `verification/browser-final/`, using temporary synthetic profiles and no native,
  real-model or application opt-ins.

## Scope

Only this ticket is implemented. The previously assigned JSON original-page
takeover ticket keeps its owner. Bound material-update scheduling remains with
the existing M4 preparation ticket; Runtime/UI and final AC audit remain separate.
No commit, remote publication, installed-App update, Prism upstream update,
real model call or real ATS operation is part of this change. Existing user data,
human material and unrelated working-tree edits are retained.
