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

**Step 4 — material-packet reading, done (uncommitted).**

- Each reading page is sent with `send(previous=<earlier attempt>/<same page>)`.
  An identical, intact answer is replayed; a page with no answer (unknown or
  failed) is sent again; a changed question gets a new call.
- `_reusable` stays. It reuses a fully read source by its content, even when
  page folder numbering shifts, which per-call replay cannot do.
- Deleted from the material packet: `_recover_native_reading` (~180 lines), the
  `pending_call` / `_unreceipted_reading` "stop for recheck" guards, and its use
  of `_undispatched_argv_page`. `_unreceipted_reading` and
  `_undispatched_argv_page` remain for `application_match_refresh`'s own proofs.
  `known_budget_failure` is unchanged: an unknown call next to a size failure is
  already resendable through `ended_without_answer`.
- New: a reading answer the stage rejects writes `validation-failure.json`, like
  retrieval does. Without it, a retry would replay the same bad answer forever.
- `model_call`:
  - When `send` refuses because the earlier record is damaged, it leaves a
    `{"status": "not_sent"}` receipt, so the attempt is not mistaken for
    unknown and resent three times.
  - A result file that is a symlink is never adopted (verdict *unknown*, so it
    is sent again). A symlinked prompt or schema is a damaged record.
- Observation: the old recovery rejected a duplicated selection, but a fresh
  answer with one was always accepted. A replayed answer now goes through
  exactly the fresh-answer checks.
- Ratchet: the private import and the `application_match_refresh` ↔
  `application_material_packet` mutual import are gone.
- Tests:
  - The 13 tamper variants now assert the per-case outcome: replayed (context,
    duplicate), sent again (missing, symlink, source, source_metadata,
    requirements), damaged stop (prompt, schema, raw), rejected stop with a
    marker (selection, requirement, business).
  - Unknown reading calls (3 tests and the analysis-interface reading branch)
    are now sent again.
  - New module tests cover the not-sent receipt and the symlinked result.
  - 1000 of 1005 targeted, Flow and Pipeline tests pass; the same 5 fail on the
    base commit.

**Step 5 — analysis-level resume, done (uncommitted).**

- `analyze_with_retrieval`:
  - If the saved progress cannot be reused as it is, the job is analysed from
    the start. Before, it stopped with `match_resume_invalid` unless a complete
    evaluation answer or a proven size refusal "hid no result". That guard
    existed only to protect unknown calls, which are now simply resent.
  - `_same_upstream_binding` lost its rejected-brief and pending-follow-up
    cases. A pending follow-up search resumes whenever inputs and model
    configuration match (provenance is ignored as before), and its unknown page
    is resent.
  - The context-budget-only reuse case stays.
  - `_recorded_failed_followup` and `_answered_evaluation` are deleted.
- `Analysis.prepare`: under the scope's execution lock the latest attempt has
  ended, so one that ended on a call without an answer counts as failed and is
  resumed, instead of `match_result_needs_recheck` refusing every new request.
  Without this, the App's auto-resend could stop after its first try.
- Tests:
  - 11 tests that pinned the refusals now assert a fresh analysis (model or
    budget change), a resume with that call resent (unknown follow-up page,
    newer unknown evaluation, lineage), or an admission stop (new request with
    `admit_call` refusing).
  - The private `_answered_evaluation` test is deleted.
  - The private `_same_upstream_binding` test now expects every pending
    follow-up to resume.
  - 997 of 1002 targeted, Flow and Pipeline tests pass; the same 5 fail on the
    base commit.

**Step 6 — Flow reads no code table, done (uncommitted).**

- `_analysis_outcome` no longer lists error codes, and `_known_attempt_failure`
  (with its `Analysis.reconcile` directory check) is deleted. A modern failed
  analysis stage is an ended attempt: every call in it holds a recorded verdict,
  so whatever its code it is *rejected* / `needs_input` and Continue retries it.
  Safety stays in Analysis: the execution lock refuses while an attempt still
  runs, `prepare` resumes from the failed attempt and resends calls without an
  answer, and a damaged record stops with `match_resume_invalid`.
- `resendable` still comes from `model_call.ended_without_answer`;
  `legacy_analysis_failure` and the output/handoff checks are unchanged.
- Behaviour change: codes that used to stop as *unknown* with no Continue
  (`retrieval_execution_incomplete`, `match_model_unavailable`,
  `match_result_needs_recheck`, `flow_stage_failed`, `flow_interrupted`) now wait
  for the user's Continue, which retries.
- Tests: the code table test asserts *rejected* for every code; the
  callback-forged `reconcile` test is deleted; the interrupted-analysis and queue
  failure-mode tests expect `needs_input`. 807 of 813 targeted tests pass; the
  same 6 fail on the base commit.

**Step 7 — résumé author, done (uncommitted).**

- Each author call (plan, one per experience, review) goes through
  `model_call`: files `prompt.json`, `schema.json`, `result.json`, rejection
  `validation-failure.json`. An answered call is reused (`earlier_answer`); a call
  without an answer is sent again in the same directory; a rejected answer still
  moves to the next directory, whose prompt carries the rejection.
- A runner failure now raises `resume_author_no_answer` (stage *failed*, not
  `needs_recheck`). Flow routes it like `resume_author_failed`: a continuation that
  keeps the handoff, so finished fragments are not rewritten. Before, an unknown
  author result became `resume_author_needs_recheck`, and Continue discarded the
  handoff and rewrote the whole résumé (17952ff5).
- Pipeline: the 30 s resend (`model_resend`) records its `stage`; a résumé author
  without an answer is resent through the same continuation as the user's
  Continue (`_continue_author`), up to 3 times.
- Legacy directories (`intent.json`, wrapped `result.json`) are still read; one
  without a result is resent in place.
- Receipt-only reconcile (`allow_calls=False`) still never sends.
- Tests: the two "never replay" tests now assert that only the unanswered call
  is resent; new tests cover a legacy reservation and the Pipeline's automatic
  author resend. 1867 of 1873 targeted tests pass; the same 6 fail on the base
  commit. The ratchet gains 2 `pipeline._tick()` uses in the new test.

**Still to do**, in order:

1. Migrate the cover letter and material consistency check. Other callers
   (gmail, jd_extract, account check, employer page search, audit, cli) are
   one-shot calls with no resume semantics and stay as they are; the Claude second
   opinion already never blocks a job.
2. Delete the private-helper tests; run the full suite once; generate one real
   résumé in the App.

## Follow-up enabled

Once the analysis chain no longer opens journal files, `application_match` and
`application_matching_pipeline` stop importing each other's private names, and
merging them becomes a cheap follow-up (review candidate, deletion test currently
fails both ways).

## Unified material lifecycle (agreed 2026-11-10)

The résumé and the cover letter take the same inputs and each produce one PDF, so
they share one design and one state mechanism ("material", kind `resume` or
`cover_letter`):

1. State: both live in `task["stages"]` with the same shape (`resume`/`export`,
   `letter`/`letter_export`), status values, failure-code meaning, startup
   recovery, cancel, retry and recheck. Old `task["cover_letter"]` records stay
   read-only; no migration.
2. Writing: both use the same writing call on Model Call Record. The résumé is
   plan → one writer per experience → review; the letter is one writer → review.
   Rejected / no answer / paused / material required mean the same for both.
3. Export: both render, compile and check their PDF once in Flow's export stage.
   The Worker uploads the finished letter PDF like the résumé (user default:
   once, not per upload field; field size limits are checked at upload).
4. Per kind only: content schema and validator, writer/review prompts, render
   template, PDF check (letter: one page).
5. Pipeline/UI: one material list for progress, waits, Continue and automatic
   resend; one materials panel.
6. Order: résumé first, then letter, in one queue (user default), which removes
   the mutual sibling waits.

Steps: (1) letter writing through the shared call, codes aligned; (2) letter
state into `task["stages"]`, delete the `task["cover_letter"]` handling; (3) letter
PDF in Flow's export stage, delete Worker/Pipeline letter PDF builds; (4) UI,
old tests, full suite, real App run.

**Material step 1 — letter writing on the shared call, done (uncommitted).**

- New `material_author.py` holds `author_call` (moved from the résumé author's
  `_call`), `record_rejection` and the legacy-record reader. The résumé author is a
  thin wrapper; the letter's writer and review are two more callers.
- Letter calls live in `cover-letters/authors/`, beside the attempts, so a retry
  attempt reuses every answered call and resends only the one without an answer.
  A malformed writer or review answer is marked rejected and asked again with the
  reason; an unsupported review verdict is an answer and triggers the local
  rewrite as before. Each attempt still keeps copies of its calls' prompt, schema
  and answer so `read_cover_letter_result` is unchanged until step 2.
- Codes: no answer → `letter_generation_no_answer` (Flow: known failure);
  admission refused → `letter_generation_failed` with stage `cancelled`; damaged
  record → `letter_generation_needs_recheck`.
- `material_author` is registered in both loaded-code roles. A module-level
  `threading.Lock` broke loaded identity (unserialisable), so the letter passes
  `nullcontext()`: Flow runs one letter per task.
- Tests: letter fakes read the call role from the prompt (`phase(prompt)`), as
  every call now uses `schema.json`; retry tests use realistic native answers
  (`native`), since reuse verifies the recorded invocation. The obsolete "unknown
  review never reissued" test is replaced by one asserting only the lost call is
  resent. Same failures as the base commit (6 known + 2 role-coverage).
