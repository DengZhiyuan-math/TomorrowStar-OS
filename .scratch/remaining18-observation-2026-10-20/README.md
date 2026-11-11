# Original-page capture owner boundary

## Outcome

- `synthetic_owner_expiry_reproduced`: true
- `post_screenshot_owner_recheck_implemented`: true
- `synthetic_browser_regressions_passed`: true
- `affected_offline_regressions_passed`: true
- `scoped_lint_passed`: true
- `installed_app_acceptance_completed`: false
- `real_page_accessed`: false
- `real_application_resumed`: false
- `ticket_claim_changed`: false
- `ticket_closed`: false

The retained transport now proves its owner again after screenshot capture.
An expired or refused owner discards the capture before any observation is
published. Final DOM, document and connection checks still follow this read.
The worker retains its original Page and client, its paused state and unresolved
intent. No fallback transport or page selection is introduced.

## Remaining boundary

The installed observation positive case still requires valid native host
permissions and an isolated acceptance run. Existing ticket ownership must be
coordinated before that run. Request diagnostics remains dependent on original
page observation acceptance. The historical request failures are not uniquely
attributed by this fix. Real application work remains paused.

Raw verification logs stay in temporary private storage. The before-image here
contains checkout source only and supports scoped review.
