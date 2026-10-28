# M4 preparation and job scheduling ownership

Date: 2026-10-26, Europe/Zurich. Status: complete for checkout source and
related synthetic verification; the ordinary-preparation ticket is closed.

This record concerns [M4 收拢剩余准备与岗位调度职责](../module-completion-2026-10-26/issues/13-m4-preparation-scheduling.md).
The user explicitly requested execution after the Resume lifecycle ticket closed.
`before/` captures the existing dirty checkout; only this baseline is used to
attribute this task's edits. Earlier source and test results keep their own scope.

## Delivered ownership

- Flow owns résumé retry/start/export and exposes a read-only business result.
  Pipeline retains routing, current job, pause/continue/skip/return and Worker admission.
- Flow owns bound-material inputs, editing coordination and candidate preparation; the original update ID, candidate and journal remain authoritative.
- Worker owns the read-only permission to prepare against its paused execution.
  Flow consumes that permission without interpreting raw Worker control, page or Codex stop records.
- Flow constructs candidate tasks and reserves their original export attempts.
  Portal wires owning interfaces; Resume retains material construction and source rules.
- Queued candidate preparation must check cancellation before material calls. Late
  output remains historical and cannot reactivate a cancelled task or replace its PDF.

## Ownership during implementation

| Owner | Files and regions |
| --- | --- |
| Preparation worker | Flow ordinary preparation methods beside task progress; Pipeline ordinary preparation and Continue consumers |
| Bound preparation worker | Flow bound preparation/input/edit methods; bound-material compatibility helpers; Worker read-only preparation permission |
| Parent | Portal bound-material assembly; Flow candidate construction/export reservation; Resume retained-source preparation |

Workers shared the dirty checkout and edited disjoint method regions. Final
verification used one unchanged 672-file snapshot: full default offline
7,804 passed, two opt-in benchmark skips, followed by 152 related
isolated browser passes. Both JUnit reports exactly cover their disjoint manifests.
Ruff, format, diff and independent review checks passed. See
[final verification](final-verification.json) and [closeout checks](closeout-check.json).

## Existing execution admission bridge

`Flow.prepare_worker/configure_worker/worker_action` retain the accepted M1
compatibility boundary: Flow checks its task/material binding and adopts only the
returned execution reference; Worker owns `prepare_execution/control_execution`
and its execution state. Pipeline selects the current job and when admission/start
occurs. This is existing ordinary scheduling, not deferred MC08 work. A new default
queue regression follows the actual Pipeline path through both Worker operations
and verifies one execution, exact fixed material binding and separate progress.

## Retained scope

The existing Pipeline remains the only job scheduler. Waiting continues mail
capture only. Unknown, conflicting or missing necessary results stay on the same
job. Exact fixed inputs, local recovery, human materials and one Continue remain.
Legacy HTTP/CLI routes keep their existing contract.

Original-page inspection/dispatch, editing stop/drain and the new Codex takeover
control remain with the T09 ticket. No second queue, journal or persisted state
machine is introduced. No commit, publication, installed-App update, real model,
real Prism or real ATS acceptance is authorized by this source task.

## Review corrections and verification records

Independent review used this task's dirty-checkout baseline, not Git HEAD. The
[ordinary preparation review](reviews/preparation-review.md) and
[bound preparation review](reviews/bound-review.md) retain original findings,
reproduction evidence and final review conclusions. Final reviewed file hashes
are compared with the full verification snapshot before closure.

- A reused Continue ID could retry a later failed author attempt. It now binds to
  the actual scheduled attempt in task-owned attempt history, atomically with
  the stage reservation. This covers initial analysis/material/export/letter work
  and paused-author continuation as well as known-failure retries. The same ID cannot repeat work, including after restart or lost
  response; a different fixed input or explicitly supplied attempt conflicts.
- A pending bound candidate could be hidden by the old active PDF. Progress now
  reports candidate state separately and prevents execution admission until the
  update completes. Original active materials and execution references remain.
- A saved draft from a different application/analysis could be reused when the
  inputs happened to match. Resume now checks task, old task, saved application,
  analysis, applicable inputs and fixed draft hash before any provider/build work.
  Both prepare and edit use the same saved-reference check.
- Parent/worker tests also reproduced dispatch after queued cancellation, stale
  Worker permission or fixed input changes, second-controller preparation, and
  adoption after cancellation. Flow now gates queued work and preserves late
  source/candidate outputs as unadopted history, including cancellation between
  source completion and PDF export.

The actual default queue test follows Pipeline through the accepted Flow bridge
and real Worker prepare/control methods. It verifies one execution and exact
material binding. Retained complete content reuse makes zero new author/provider/
build calls. Original unknown export recovery keeps the same export attempt.

Detailed targeted evidence:

- [Ordinary preparation](preparation/implementation.md): final affected selection
  235 passed before the final all-dispatch Continue correction; final continuation
  selection 36 passed, including both independent known/paused probes and all
  first-dispatch branches. Complete frozen verification below covers the final
  combined source.
- [Bound preparation](bound-preparation/implementation.md): cancelled/stale/owner
  and history regressions, with separate chronological RED/GREEN records.
- Parent final material compatibility: [21 passed, 6 browser cases deselected](consumers/material-final-green.log).
  Those browser cases are included in the later isolated browser selection.
- [Final source diff](final-source-diff.patch) and
  [change list](final-change-summary.json) include six production files, three
  updated test files and four new test files. Initial review snapshots remain
  separate and are not final verification evidence.

The earlier `consumers/foreign-material-import-error.log` was a missing fixture
helper, not a product defect. Review's fixture-adoption failure and the intermediate
mixed-source 8-case run are also retained as diagnostic history only. Final frozen
verification supplies combined evidence after all source edits and independent
review corrections.

The first Continue correction covered explicit known-failure retries only. A later
independent probe found that paused-author continuation and other first-dispatch
paths could still reuse an unrecorded request ID. The final correction records the
actual scheduled attempt for every Continue dispatch. The task-owned attempt
history is new metadata in this change, not a pre-existing field; current stages
remain authoritative and no new lifecycle, recovery router or global command
ledger is introduced. Both review rounds retain their own evidence.


## First complete offline batch

The [first complete batch](verification/offline-final/summary.json) selected all
7,801 default offline nodes and finished with 7,796 passed, 3 failed and 2 skipped.
All 672 frozen files stayed unchanged. It is retained as a failed batch and cannot
serve as final acceptance.

Two unchanged synthetic HTTP regressions found that application-mode input refresh
correctly resets analysis to pending and marks the task stale, but the new ordinary
preparation projection recognized only draft/pending as not started. Consequently
Continue after a location correction did not schedule the new analysis. The correction recognizes only the explicit reset shape, keeps old unknown
attempts blocked, and preserves retained materials/history. The third failure was an old SimpleNamespace test double without
Flow; it was adapted to the existing real Flow/handoff fixture with stronger
no-redispatch and read-only assertions.

The original HTTP assertions remain unchanged. The corrected focused selection
passed 166 cases, including five actual reset/unknown-state cases and the real Flow
handoff fixture.

The final rerun keeps the complete default selection. Partition placement uses
file durations from the completed first batch, with exact node coverage checked
again before execution. It does not select only previously failing tests.


An additional proposed legacy-coordination probe manually combined states that
independent source review found unreachable through the current update/start
paths. Its diagnostic log `preparation/analysis-reset-coordination-red.log` is
retained, but it is not a product finding or acceptance result. The temporary
probe parameters were removed and no production guard was added for that
hypothetical case. The final independent reset/HTTP/handoff review passed 11
cases against the restored source, followed by the full frozen rerun.
