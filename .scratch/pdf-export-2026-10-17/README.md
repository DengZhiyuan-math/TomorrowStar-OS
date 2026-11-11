# PDF export verification — 2026-10-17

Scope: preparation-policy/v1.0, one saved and explicitly reviewed draft, independent PDF export and retry. Real applications remain paused.

- `verification.json`: final gate results and boundaries.
- `source-manifest.json`, `source-readback.json`, `owned-changes.diff`, `baseline/`: bounded changes over the preserved dirty checkout.
- `preserved-legacy-tests.json`: seven pre-existing affected test files retained byte for byte.
- `review.json`: independent review, concrete findings and corrections.
- `renderer-run.json`, `draft.json`, `source-snapshot.json`, `export-intent.json`, `export.json`, `resume.html`: actual Chrome export through the public loopback preparation flow with four synthetic source records. One fake content-generation call; no real model.
- `pdf-quality.json`, `extracted-text.txt`, `page-1.png`, `page-2.png`: actual PDF parsing, A4/page/content checks and visual inspection of both pages. Product page count is not capped.
- `renderer-final.log`: successful actual renderer gate. Earlier setup errors and rejected native export attempts remain separately named.
- `renderer-metadata-diagnosis.json`: real Chrome startup changed ctime only. Content hash and stable file attributes stayed equal. Stable executable plus framework identity now rejects real changes without rejecting this startup noise.
- `observed-renderer-startup-failure.json`: the first constrained Chrome launch aborted during macOS application registration; a separate isolated launch succeeded. This is test-process evidence, not an installed-App or historical failure closeout.
- `pdf-export-*-red*.log`, `tomorrowstar-pdf-export-*.log`: red/green and regression evidence. `store-tracer-baseline-replay.py` and its explicitly named baseline replay log reconstruct the missing-API failure from the immutable pre-ticket baseline; that replay is not the original-time log.

Copied complete PDF fixtures exercise transport, receipts and workflow only. They do not count as renderer-quality evidence. The separate final two-page PDF was rendered from the exact saved synthetic draft, and all four full texts were extracted and checked.

No private career records, Gmail, external model, real job page, ATS, upload or Submit was used. No TomorrowStar App launch, installed-App replacement, staging, commit or remote write. Installed use and real-content human acceptance retain separate successor gates.
