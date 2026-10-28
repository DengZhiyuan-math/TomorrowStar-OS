# In-flight PDF export after backend loss

Date: 2026-10-20. Supporting engineering for [诊断原生会话中断并验证阶段恢复](../single-job-application-flow-2026-10-16/issues/27-native-interruption-recovery.md).
Existing assignee and open status remain. Real applications stay paused.

## Reproduced defect and minimal fix

The earlier process-boundary test killed the backend after the PDF child exited
and a completed receipt existed. The new test kills the backend while its actual
synthetic PDF child is still alive, waiting at a bounded filesystem barrier.
The test observes child PID, parent PID and process group and uses a new session
owned only by this test. No pre-existing process is signalled.

Before the fix, the missing completion receipt was returned as `not_complete`
for a non-Prism renderer. Rechecking changed the flow to `export_failed`, allowing
an explicit retry even though the original child was demonstrably still alive.
RED: `pytest.raises(PortalDataError)` failed with `DID NOT RAISE`.

The sole production change is in `ApplicationResumeStore.reconcile_export`:
missing completion receipts now remain unknown for every renderer. It does not
infer either that the child is alive or that it has exited. It keeps the existing
attempt pending inspection and prevents a retry based on absence alone.
The flow's explicit `not_complete` callback contract is unchanged.

The new test proves both the in-flight and late-result boundaries: reopening and
rechecking preserve task, inputs, draft review, attempt and history; retry remains
blocked; no stage callback runs; a late raw PDF without a valid completion receipt
remains unadopted. No materials are confirmed and no application worker exists.
The synthetic child has a 20-second self-deadline; controller waits are bounded,
and failure cleanup targets only its own process group.

The pre-edit production bytes are retained in `application_resume.before.py`.
No production process tracking, termination, receipt synthesis or auto-retry was
introduced. The test is a synthetic fixture copier, not a compiler.

## Verification

Use the checkout launcher with a writable uv cache and `--locked --offline --no-sync`.

- Reproduced product RED: one failure at the unsafe recheck.
- Affected suite: **100 passed, 2 deselected in 8.37s** across in-flight recovery,
  saved-receipt recovery, close races, export flow and resume store tests.
- Final formatted regression rerun: **1 passed**.
- Scoped Ruff and Ruff format check passed; scoped whitespace check passed.
- Raw logs retained privately; parent performs broad verification.

## Installed main App experiment readiness

Read-only inspection only. No App, browser, permission pane or provider launched.
The main installed package is `/Users/zhdeng/Applications/TomorrowStar.app`.
A serial experiment must pin the package manifest/signature and preserve any
already-running session before launching its actual executable with fresh external
synthetic inputs. No installation or permission mutation is necessary to inspect.

The current `--synthetic-preparation` route injects `SyntheticPrismClient.compile`,
which reads a fixed local PDF in process. It cannot establish a real in-flight PDF
subprocess boundary. `--synthetic-flow` uses the actual HTML/Chrome PDF exporter,
but also represents the legacy application workflow, so reaching a final stage
must not be confused with preparation-only acceptance. Never advance to a worker.
The native `--pdf-export-check` route runs one fixed offline HTML export under the
native host, but is a diagnostic without the task/draft/attempt recovery contract.

None of these existing routes exposes a deterministic readiness barrier for an
actual compiler child. Polling for an arbitrary Chrome PID is not an adequate
substitute. To count as installed in-flight acceptance, the operator must bind an
actual newly spawned exporter PID/process group and task attempt before disruption
and preserve complete native/backend logs; if that binding or trigger cannot be
proven within the existing deadline, stop and record the boundary unverified.
A native diagnostic can independently verify Chrome launch/export, but cannot
close the task-recovery acceptance requirement.

No native experiment is scheduled by this support report. Historical root cause,
current installed-version interruption acceptance and actual compiler ownership
remain unresolved; this source fix does not close the ticket or change its gates.

## Full-suite contract correction follow-up

The first parent full offline run found exactly two old store assertions expecting
`not_complete` on a missing completion receipt. After that run finished, only
those cases in `tests/test_resume_export.py` were updated. Both now require
unknown status from read-only reconciliation and preserve all existing bytes.
The intent-save case also checks whether the intent exists for each original
saved/not-saved variant. No production edit followed the original minimal fix.
The test before-image is retained as `test_resume_export.before.py`.

The expanded affected suite, including the entire store export test module and
explicit terminal-failure retry behavior, passes: **52 passed**. Raw follow-up logs are retained in the private evidence register.
Scoped Ruff and format checks pass. The parent runs the final complete suite.
