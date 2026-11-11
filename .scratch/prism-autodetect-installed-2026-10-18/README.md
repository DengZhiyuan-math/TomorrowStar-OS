# Installed Prism saved-source detection — 2026-10-18

The review page checks saved LaTeX every three seconds while visible. Window focus
and visibility return trigger an immediate read. Checks are serialized and skipped
while capturing. A saved-source change updates the notice and live source digest;
it does not compile, capture or approve anything.

An unchanged receipt set preserves the selected historical version, source node,
PDF iframe and reading position. Temporary HTTP failures retain the displayed
version and retry. Capture remains explicit; its preflight reads the latest source
identity before using the backend's existing source-version guard. Unknown results
still block capture and require explicit reconciliation.

Verification: automatic saved-change detection first failed, then passed after the
implementation. Four isolated browser regressions passed: existing readback and
history, automatic notification without PDF reload, selected-history preservation
and one-click latest readback, and transient failure/recovery without another build.
61 related offline tests passed. Ruff, formatting and JavaScript syntax checks
passed. A narrow independent audit found no blocker. The backend and storage
contracts were unchanged; the prior 2,652-test full-suite record remains historical.

The signed package and native PDF tool were checked against staged resources.
Private-history protection includes original source and PDF snapshot receipts.
The installed App was normally restarted after transactional replacement. Its
native ⌘8 entry displayed automatic detection enabled and the same four-page
source/PDF version. All 1,453 installed entries match the signed stage. 390
protected private files are byte-identical, including ten existing source/PDF
receipt files; the old paused run differs only in its two periodic clock fields.
Eight original worker/browser/Prism process identities remain alive. No new real
capture, compile, job task, filling, upload or Submit was performed. The old App
bundle is retained for rollback.

Saved-edit notification, selected-history retention and connection recovery were
exercised with synthetic browser fixtures. The actual installed App was checked
against the unchanged real résumé; the user's real source was not edited to
manufacture a change. Private full evidence and native screenshots remain outside
this repository. [Machine-readable checks](verification.json).

Real material approval and real applications remain paused.
