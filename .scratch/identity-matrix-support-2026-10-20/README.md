# Installed admission matrix support — 2026-10-20

Supports the existing **核验当前安装身份与在途版本交接** ticket. Its original
assignee, dependencies, open state and installed/native acceptance gates remain.
No native App, daemon, browser, permissions, external service or real application
was used. Permission and measured-package receipts are synthetic injections.

## Implemented correction

An exact historical worker combination declared compatible by the existing
`VERIFIED_WORKERS` policy could accept explicit resume, then its first heartbeat
always failed because lease validation only accepted the current packaged worker.
The isolated regression reached this product failure before implementation; the
raw RED transcript is retained privately. Earlier local attempts corrected test fixture setup and were not
product failures.

The admitted lease now retains the historical exact key and a deep copy of its
compatibility evidence. A historical heartbeat requires that same managed
process, exact worker/source tuple, unchanged allowlist evidence and a declared
command with a nonempty basis. Existing runtime identity, package/controller,
configuration, native revocation, file and freshness checks still apply. There
is no version-number tolerance. The production historical allowlist stays empty.

## Verification

`tests/test_installed_admission_matrix.py` adds 14 cases:

- Exact synthetic historical compatibility permits explicit resume and heartbeat
  while preserving process, run, page and attachment identities.
- A command absent from the compatibility evidence is denied after legal resume.
- Removed compatibility, removed command, changed evidence basis and changed
  runtime identity each deny heartbeat without business writes.
- Seven actual loopback prepare POST cases reject mismatched native PID, backend
  PID, bundle or executable, closed session, background-only scope and invalid
  revocation epoch; flow, worker and application bytes remain unchanged.
- A proof that merely ages out between scan and the locked save denies before
  approval, worker preparation or spawn.

The new tests plus installed HTTP admission, installed write admission and
readiness tests passed: **89 tests**. The Boolean result is recorded in
[the summary](summary.json), and raw execution logs are retained privately. Ruff check and
format check passed for the two changed executable files. Parent owns full-suite
verification because `career_portal.py` is shared workflow code.

The [scoped patch](career_portal.scoped.patch) contains only this task's production
change. The [before image](career_portal.before.py) was reconstructed by reversing
these exact edits after implementation; it is not an independently captured
original snapshot. It is retained because the shared production file is untracked
in the checkout and ordinary `git diff` cannot describe this task's change.

## Remaining acceptance

Synthetic policy injection does not admit a real historical combination. Actual
current-host permissions, separate permission causality, installed controller /
worker / disk identities, retained old bundle and exact compatible handover,
original Page/attachment scope and native failure recovery remain open. Current
installation and real applications stay untouched and paused. No ticket closes.
