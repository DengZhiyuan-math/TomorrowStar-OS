# Model Call Record — design decisions (2026-11-09)

Source: architecture review candidate 1 and its grilling session. Glossary term:
**Model Call Record (模型调用记录)** in `CONTEXT.md`. Nothing is implemented yet.

## Why

At least six modules decide on their own whether a model call was sent, whether
its failure is known and whether it can resume. Each guesses from which files
exist and keeps its own error-code list. There were 10 resume fixes in ~48 h
across 4 modules (ee1af146, 54341431, e1545fed, b262937d, 02d150b6, 5019d594,
3f32d7f7, f1873d0f, ed980a0d, 794675fb), and the UBS case was fixed twice.

## Decisions

1. **Scope**: every structured model call goes through one module
   (`model_call.py`) sitting directly on `codex_cli.run_codex_exec`. Migrate in
   this order: job-analysis chain (job brief, retrieval pages, material packet,
   evaluation, match refresh), then résumé and cover letter, then the rest
   (full_latex, jd_extract, gmail, proofread, …).
2. **Unit**: the module owns exactly one call directory. Call order inside an
   analysis and the walk back to earlier attempts (`_recovery_directory`) stay in
   the analysis chain, which asks each call for its verdict and no longer opens
   journal files.
3. **On-disk format**: keep today's file names (`context-input.json`,
   `*-schema.json`, `model-result.json`, `dispatch-stopped.json`,
   `adapter-rejection.json`, `validation-failure.json`). The module becomes their
   only reader and writer. No migration of historical directories or fixtures.
4. **Verdicts**: not sent · known failure (with code) · unknown (sent, no result)
   · answer recorded · answer rejected (the stage passes its validator in; the
   module writes the rejection receipt with the stage's error code).
5. **Admission**: the "is this call still allowed?" check (Flow's
   `analysis_call_allowed`, `resume_call_allowed`, `cover_letter_call_allowed`)
   is passed into the module and run immediately before sending. A refusal is
   recorded as *not sent*. Replaces `Analysis._admitted_runner` and the separate
   `dispatch-stopped.json` writer.
6. **Replay**: a recorded answer is reused only when prompt, schema and model
   configuration are identical (input digest). Otherwise a new call is made.
   Replaces stage-specific identity checks such as `_same_upstream_binding`.
7. **Automatic resend**: *unknown* and failures that produced no answer
   (timeout, CLI error) are resent after a fixed 30 s wait, up to 3 more times
   (4 sends at most). Only then does the current job stop with today's message
   ("请检查模型服务或登录状态后重试"). *Answer rejected* is never resent this way.
   This intentionally changes product behaviour: model-service faults used to
   stop the job immediately.
8. **Retry state**: the resend count and next-send time live in the call record,
   so App restarts do not reset the count. The wait is advanced by the existing
   Pipeline tick, not by a sleeping thread.
9. **UI**: while waiting, the current-job panel shows one line such as
   "模型调用失败，30 秒后第 2 次重试".
10. **Flow**: delete the 10-code table in `_analysis_outcome` and the directory
    check in `_known_attempt_failure`; Flow reads the verdict kind recorded by the
    stage. `legacy_analysis_failure` stays as a read-only reader for old tasks.
11. **Adapters at the runner seam**: Codex (prod), Claude second opinion (prod),
    fake runner (tests). The Claude second opinion is *not* resent: a call option
    turns resending off, because the analysis report waits for its result and it
    is only a reference score. Its failure never blocks the job.
12. **Tests**: delete tests that call private helpers or hand-build call
    directories (e.g. `_same_upstream_binding` in
    `test_matching_stage_recovery.py`, callback-forged codes in
    `test_analysis_outcome.py`). Add scenario tests through the module interface
    with a fake runner: admission refused, crash before prompt saved, crash after
    send (unknown), timeout, answer, rejected answer, changed input (no replay),
    resend count surviving a restart. End-to-end analysis tests switch to the
    fake runner.
13. **Process**: commit the current uncommitted work first (it touches
    `application_flow.py` and `application_pipeline.py`), then branch from that
    commit. Targeted tests per migration step; one full suite before merge; one
    real job analysis in the App, ideally a job that was interrupted before.

## Progress

**Step 1 — done (branch `model-call-record`, uncommitted).**

- `src/career_evidence_graph/model_call.py` added. It provides `Files` layouts
  (`EVALUATION`, `JOB_BRIEF`, `PAGE`), `send` (the single writer of a call's result
  file, with the admission hook run inside it), `verdict` (five outcomes),
  `is_known_failure` (moved from `application_match._known_failed_model_result`)
  and `failure_code` (moved from `_model_failure_code`).
- Sends are migrated in evaluation, job brief, retrieval pages and material-packet
  pages. Failure checks are migrated in `_resume_evaluation`, retrieval and job-brief
  resume, the material-packet origin scan and `_ended_on_known_failure`.
- Behaviour is unchanged, apart from one difference: every exception a runner
  raises now leaves a failed receipt. The verdict for such a receipt is still
  *unknown*, the same as before.
- Ratchet: 5 private imports and the job_brief ↔ match mutual import are removed.
- Tests: `tests/test_model_call.py` (scenarios). Of 755 targeted analysis-chain
  tests, 750 pass; the 5 failures also fail on the base commit f0e459e0. They are
  ratchet drift in job_source/worker_browser, the adoption-write test and two
  pipeline route tests.

**Step 2 — replay, mostly done (uncommitted).**

- `model_call.earlier_answer` checks an earlier call before a new attempt saves
  anything. It returns the checked answer, or None when nothing was sent, the
  failure is known or the answer was rejected. It raises `UnknownCall` for an
  unknown outcome and `DamagedRecord` when the saved answer, prompt, schema or
  rejection marker disagree.
- `model_call.recorded_answer` / `send(previous=...)` replay only when the prompt
  hash, schema hash and model all match. Any other difference means a new call.
- Job brief, retrieval pages and evaluation (`_resume_evaluation`) use this. Their
  own prompt/schema/context comparisons are gone, as is
  `_compatible_page_schema`.
- Behaviour change (decision 6): a changed question now gets a new call
  instead of stopping with `job_brief_invalid` / `retrieval_invalid` /
  `match_resume_invalid`. Pages answered under the pre-minItems follow-up schema
  are asked again. Damaged records still stop the job, and unknown calls still
  wait (until step 3).
- Tests: 7 replay scenarios in `test_model_call.py`. Two tests were updated:
  the rejected-under-earlier-prompt test now builds a consistent earlier record,
  and the legacy follow-up test now expects both pages to be asked again.
  757 of 762 targeted tests pass; the same 5 fail on the base commit.

**Step 3 — automatic resend, done (uncommitted).**

- `earlier_answer` no longer raises for an unknown outcome. Resuming an ended
  attempt sends an unknown call again, exactly like a known failure.
  `UnknownCall` is gone.
- `model_call.ended_without_answer(directory)`: a sent call under an ended
  attempt produced no answer (known failure or unknown). A refusal before
  sending (size, admission) does not count.
- Flow: `_known_attempt_failure` treats such an attempt as known, so Continue
  retries it. `analysis_outcome` gains `resendable`.
- Pipeline:
  - A rejected analysis with `resendable` stops with "模型调用失败，30 秒后第 n
    次重试。", the existing page notice line.
  - `_resend_when_due` runs the same retry as Continue (`_retry_analysis`, now
    shared) after `MODEL_RESEND_WAIT` = 30 s, up to `MODEL_RESENDS` = 3 times.
    After that the usual stop message shows.
  - A manual Continue starts a fresh round of three.
- **Deviation from decision 8:** the resend count lives in the Pipeline's saved
  state (`model_resend`: task, count, due), not in each call directory. It still
  survives an App restart, and the count is saved before each retry. The resend
  is a job-level Continue, so the Pipeline is the one place that needs the count.
  Keeping it there also stops the Pipeline from reading call files.
- Login or missing-CLI failures are also calls without an answer, so they get
  the three resends too (about 1.5 minutes) before the stop.
- Not covered yet:
  - Material-packet reading unknowns (`pending_call`, `_unreceipted_reading`)
    still stop the job.
  - An App closed mid-call whose Flow stage is not yet `failed` follows the
    existing restart handling.
- Tests:
  - `test_model_call` covers the resend and `ended_without_answer` cases.
  - Two new Pipeline tests cover the notice and wait, and 3 automatic resends
    followed by a fresh round after a manual Continue.
  - 11 tests that pinned "unknown never resends" were rewritten to assert a
    single resend of only that call (job brief, retrieval page, empty page,
    evaluation, retry-interrupted evaluation, planner ×2, analysis interface ×4).
  - The outcome tests gained `resendable`.
  - 982 of 987 targeted, Flow and Pipeline tests pass; the same 5 fail on the
    base commit.

**Still to do**, in order:

1. Finish replay: the material-packet source reuse (`_reusable`,
   `_recover_native_reading`) and the analysis-level `_same_upstream_binding`
   still carry their own identity rules. Material-packet unknowns should resend
   too.
2. Flow: replace the `_analysis_outcome` code table and `_known_attempt_failure`
   with the recorded verdict kind.
3. Migrate the remaining callers: résumé, cover letter, full_latex, jd_extract,
   gmail, proofread, and others. Add the Claude second opinion as an adapter with
   resend off.
4. Delete the private-helper tests; run the full suite once; do one real job
   analysis in the App.

## Follow-up enabled

Once the analysis chain no longer opens journal files, `application_match` and
`application_matching_pipeline` stop importing each other's private names, and
merging them becomes a cheap follow-up (review candidate, deletion test currently
fails both ways).
