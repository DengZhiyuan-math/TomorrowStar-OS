# Installed Prism LaTeX/PDF readback — 2026-10-18

## Review contract

The App's **显示 → 简历审阅（Prism）** (**⌘8**) opens an independent review page.
It does not create a job, draft, material approval or application task. The editor
button opens the existing Prism instance. Explicit readback strictly compiles the
current saved source, then preserves a distinct source/archive/PDF receipt.

The displayed source and PDF share an immutable version ID. The banner identifies
capture UTC, source revision, main-file SHA-256, PDF SHA-256 and page count.
History remains selectable. Later saved edits are reported separately from the
selected snapshot. Every version stays `pending_human_review`.

Unknown compilation or inspection outcomes remain durable across restarts and
block re-execution. Reconciliation only inspects an existing receipt. A definite
local PDF validation failure retains its attempt and permits only another explicit
capture. Synthetic modes do not read host résumé configuration.

## Verification history

- Initial tracer test: independent state route RED → GREEN.
- HTTP readback: immutable source/PDF served by one ID, source-change detection,
  no prepared task, worker disabled, same-origin CSRF required.
- Browser regression reproduced an empty direct-entry page. Initialization was
  repaired. Capture, edit detection, history selection and reload without a second
  build passed.
- Initial complete offline suite: 2,642 passed, 272 deselected.
- Initial installed real capture exposed a PDF compatibility defect: the classic
  validator rejected a valid Tectonic compressed-object PDF. The attempt was
  retained and was not adopted as a version.
- Native PDFKit inspection accepts the four-page object-stream fixture. The fixed
  signed package also verified the existing real PDF as four pages without
  recompilation. No Python dependency was added. The tool and its source are
  bound by the package manifest and code signature.
- The exact observed legacy `resume_pdf_invalid` attempt is retained as a known
  local validation failure. No PDF/build/version receipt is reconstructed for it.
  This correction does not apply to unknown network or process outcomes.

## Final installed verification

The compatibility fix passed **2,652 offline tests** (272 deselected), browser
capture/edit/history/reload regression, Ruff checks/format and `git diff --check`.
A narrow independent audit found no remaining blocker.

The authorized primary App was normally quit and transactionally replaced.
The old bundle is fully retained. All 1,453 installed entries match the signed
stage; 80 engine assets and the fixed native PDF tool were verified.

The installed App's native **⌘8** opened the review page. An explicit capture of
the current real résumé succeeded. The App displayed its saved LaTeX, four-page
PDF, immutable version ID, UTC time and pending-human-review status. Direct
readback verified that source and PDF hashes match the same receipt, and the
source matches the current saved project file. The real source was not edited.

All 380 previously protected non-clock private files remain byte-identical. The
paused worker run is semantically unchanged except its two known periodic clock
fields. All eight preserved worker/browser/Prism process identities remain alive.
The App is in preparation mode, with its filling worker disabled and zero job
preparation tasks. No ATS, upload or Submit action was performed.

[Machine-readable checks](verification.json)

Personal paths,
source bodies, document fingerprints, raw receipts and screenshots remain private.
Real material approval and real applications remain paused; the three human-review
items remain open.
