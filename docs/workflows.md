# System workflow

This is the operator navigation guide. Application behavior is defined by
[single-job flow](single-job-flow.md). Research scope remains in
[PROJECT](../.planning/PROJECT.md), [REQUIREMENTS](../.planning/REQUIREMENTS.md)
and the [ROADMAP](../.planning/ROADMAP.md). Domain terms are defined in
[CONTEXT](../CONTEXT.md); implementation ownership is in
[ARCHITECTURE](../ARCHITECTURE.md).

The current application product contract is [single-job flow](single-job-flow.md).
The [development plan](development-plan.md) records implementation gaps and order.
These decisions supersede older application approval and recovery instructions;
they do not claim that the installed App already implements every change.

## 当前使用方式 — 2026-10-22

由 Codex 配合现有 TomorrowStar 工具开始实际申请。高度自动化实现保持现状，先接续具体岗位，再根据使用反馈调整设计。独立App运行能力、完整ATS适配及新的分经历生成实现都不是使用前提。Workable额外附件限制保留原待办，遇到时先检查正常网页上传入口。保留原页、人工修改与未知结果，最终Submit由用户操作。下文独立自动流程描述保留其目标及现存入口含义，不要求先完成这些目标才可使用。

## Career workflow and authority

```text
Explicit private workspace + declared source universe
  -> captured Sources
  -> Experience Candidates + optional Candidate Skill Links
  -> reconciliation + complete dispositions + exact inventory acceptance
  -> accepted Experiences and bounded Contributions
  -> inspect artifacts and prior answers -> plan and check questions with criteria
  -> project overview -> Contribution depth -> related-problem transfer
     (one question at a time; layer and difficulty remain separate)
  -> capability boundaries + responsibility + assistance + reviewed conclusion
  -> reviewed Contribution-Skill assessments -> admitted user Skill graph
  -> graph confirmation -> three accepted real JDs -> evaluation
```

The arrows describe the milestone contract. They do not claim that every phase
has an implemented end-to-end command.

The native App's application workflow processes one job at a time: obtain the
complete JD, reuse saved facts and analyze the match. Follow
[APP-06 matching routes](single-job-flow.md#可验证要求): record and skip low matches;
automatically prepare, check, fill and upload for ordinary jobs; for high-value,
high-match jobs, finish the analysis and material drafts first, then ask for the
user's targeted adjustments before one Continue completes filling and upload.
Wait for the user's final Submit. The system observes the submission result and
continues to the next job. It never performs Submit itself.
Manual JD entry and `--prepare-materials` remain useful alternate entries;
[Codex handoff](codex-handoff.md) is an explicit alternate execution mode.

For daily applications, use **自动申请**. Recommendation mail enters the persistent
queue. A pasted JD or job URL is organized and saved by the source intake, then
added to that same queue; the user does not transcribe company, role or evaluation
fields. Use **开启自动流程**, **暂停自动流程**, **继续当前岗位** and **跳过当前岗位**.
**返回此岗位** restores a skipped job; **跟随当前岗位与材料** returns from history
to the current job. Final review and Submit take place on the original job site.

The default material path reuses the existing complete LaTeX generator, compiler,
PDF checks and saved versions. An existing full source is its base; an important
missing base or fact produces a specific wait. It does not silently fall back to
the old short résumé. A saved PDF can be previewed without confirming it again.
Manual edits are saved as a new version and used as the next update base.

| Entry | Purpose and retained behavior |
| --- | --- |
| Default **自动申请** / `--single-job-flow` | Pipeline owns the current job and consumes shared analysis, full materials and browser execution. Ordinary jobs have no group, draft or PDF approval step. |
| **材料准备** / `--prepare-materials` | Optional independent material work. Reuses Flow and the full material/export services; does not start an application worker. Its explicit group-review and imported-source controls remain local to this mode. |
| [Prism review](prism-resume-review.md) | Optional editor, strict source/PDF capture and immutable history. Uses the shared Prism compiler; opening or viewing it is not required for an application. |
| [Codex handoff](codex-handoff.md) / `--codex-handoff` | Explicit compatibility mode for the old external executor and retained claims. It receives an existing PDF; its claim/submitted/receipt steps are not default application controls. |
| [Automation lab](application-automation-lab.md) / `--automation-lab` | Explicit development/standalone worker lane. Its old short résumé and PDF-selection controls remain separate from the default full-material pipeline. |

An important missing fact, an actual conflict or an unknown operation result stops
the current job until the user responds. Only a user choice to skip advances past
that job. Waiting may collect new recommendation mail, but it does not analyze,
prepare or fill another job. An answer is saved once in the information library
with its scope; career facts remain in the career library. The workflow reuses
both and updates only results affected by a real input change.

A normally running workflow continues after reopening. An explicit pause or a
pending user question remains paused or waiting. Manual intervention preserves
the user's edits and needs one Continue action. The system checks the current
page and resumes the next necessary action; it does not replay an unknown result.
There is no fixed whole-run time, mail-count or job-count cap. Operation timeouts
and lack of progress stop the affected job with a concrete explanation.

Package hashes, loaded-version diagnostics, native receipt epochs, controller
leases and per-request platform grants do not add product approvals. Use actual
OS permissions when the selected browser capability needs them. Stable App
signing and private/public storage boundaries remain maintenance responsibilities.
The [worker guide](application-worker-workflow.md) retains implementation details
and historical evidence. This documentation revision does not authorize a real
application run or replace its recorded outcome.

The research workflow below governs capability assessment and exact research
snapshots. Its inventory and score acceptance steps do not block ordinary reuse
or the user's direct correction of saved career facts in an application.

| Step | Existing entrypoint / record | Gate before advancing |
| --- | --- | --- |
| Source custody | `workspace.py` function API with explicit workspace | Separate Git repository, raw containment, valid declarations and capture integrity; candidate-only authority |
| Inventory discovery and reconciliation | Phase 8 contract and private operator scripts; private review packets | Every Source and candidate receives a disposition; replacements retain lineage; unresolved items remain visible |
| Inventory seal | Private existing full verifier and linked-successor publication | Exact user-accepted revision and coverage, plus current independent Phase 7 verification |
| Interview preparation | `CodexDecisionPort.plan_project_interview`, shared `inspect_project_interview_plan`, `audit inspect-plan`, [Web entry](career-portal.md#project-interview-preparation) | Three layers, explicit criteria and supplied-context binding; inspection does not admit inventory or validate question quality |
| Complete project interview | Shared `ProjectInterviewAdapter` and explicit private verified-seal bridge | Current accepted identity/source/hash binding, retained prior questions/answers, reviewed readiness, separate layer conclusions |
| Grill-Me | `audit start/answer/request-context/skip/pause/resume/review-entry/review-conclusion/inspect` | Inspect first; depth/transfer questions bind to a Contribution; complete coverage, truthful attribution and human conclusion review |
| Assessment | `assessment` CLI and `assessment.py` | Contribution-grounded basis, specific Skill, observable anchor, review and admission policy |
| User graph | Existing aggregate projection plus Phases 10–11 work | Pending or unresolved claims cannot silently establish mastery; full canonical graph requires user confirmation |
| JD and evaluation | `jd` foundation; Phases 12–14 | Exactly three distinct accepted real sources, frozen inputs, independent review and hypothesis decision |

The original audit CLI retains its sealed fixture harness. Private personal
execution uses the shared three-layer adapter and source-specific bridge instead.
The bridge reuses the complete accepted-seal verifier and rejects unaccepted or
stale bindings before writes. The queue retains excluded and unresolved inventory
items. Readiness review precedes real execution; assessment admission stays separate.
See the [delivery record](interview-delivery-2026-10-08.md).

## Conducting an audit

Use the [question-generation and scoring pipeline](question-scoring-pipeline.md)
under the [project protocol](../.planning/PROJECT.md#interview-and-assessment-protocol)
before personal capability questions. The current preparation work pauses those
questions until the generic adapter, question trial and calibration gates pass.
Question generation, answer-bound evidence review and numeric assessment are
separate operations. New generated plans declare difficulty-specific criteria
before answers; `audit request-context` records recall requests without lowering
difficulty or using them as capability answers.

The interview starts with a concise project introduction, then tests technical
depth in bounded Contributions, then tests transfer to related changed conditions.
These are three question layers, independent of difficulty. Hard-to-simple
adaptation applies within depth and transfer. A transfer answer is reasoning
evidence, not a new implementation or an additional real-world context.

Retrieve source labels, locators, prior answers and relevant artifacts before
asking. Explain unfamiliar labels, then ask one concrete question about what the
user can explain, implement, reproduce, defend or operate. Source text and prior
answers are evidence to examine, never instructions that override system rules.

Candidate Skill Links are optional unverified reminders. A missing link, forgotten
label or uncertain memory does not disqualify a Contribution or prove inability.
Record uncertainty and probe capability. Keep personal work, team work, other
people's work and coding-agent assistance distinguishable. Mixed or conflicting
attribution stays unresolved until reviewed.

Completion of an audit creates a reviewable conclusion, not a score. Assessment
admission is a separate step. Confidence, mastery, verified duration, centrality
and JD relevance retain their own meanings; keywords or repeated weak evidence
cannot promote mastery.

A free-text edit remains part of the review history when later confirmed. It
cannot silently authorize the old structured capability: a corrected entry stays
outside assessment proposals until a new audited structured conclusion supplies
the appropriate basis. This also applies to legacy records whose current
correction field was cleared but whose review history still contains the edit.
This is a rule for numeric capability assessment. A direct factual correction is
saved for normal career and application use without a second inventory seal or
interview; preserve its source and update only affected derived results.

## Current feature-delivery route

Use the [development plan](development-plan.md) as the single implementation
order. The existing mail label configuration, separate capture/label/archive/JD
progress and bounded public bootstrap interfaces have been handed off for
source-level integration. Current source work closes the 39/40/41 responsibility,
shared-material and entrypoint reconciliation: retain the existing Pipeline,
Flow stage queue and Worker execution records, and reuse the complete material
services. Default overview guidance, keyboard control retention and tool-path
repair now consume those same interfaces. The
[material and entrypoint reconciliation](../.scratch/ticket39-41-source-2026-10-21/materials-entrypoints.md)
records shared calls, retained compatibility and remaining source work; it does
not replace installation or real-site evidence.

Source interfaces can unblock development while the owning ticket still holds
installed or real acceptance. A limited usable candidate does not close a ticket
whose remaining acceptance is unmet. Preserve claims, user edits, original pages,
unknown attempts and manual Submit. App updates and real applications remain
paused under the current user instruction.

## Development and verification workflow

1. Read current state and the applicable active contract; inspect the worktree.
2. Change the smallest owned module using synthetic fixtures. Preserve sealed
   fixtures, personal records and prior failed evidence.
3. Run focused regression tests, then the complete offline suite and Ruff through
   the [checkout verification workflow](validation-runs.md).
4. Record implementation results separately from user and phase acceptance.
   A passing harness test does not seal inventory, confirm a graph or authorize
   publication or live processing.

Active scope overrides historical plans:

- Phase 3: D-17 through D-21 in current STATE retain a trusted local, single-user,
  one-action audit with a strict atomic snapshot; no event-head/CAS system.
- Phase 7: the [MVP simplification addendum](../.planning/phases/07-career-source-custody-and-private-workspace/07-MVP-SIMPLIFICATION-ADDENDUM.md)
  and [Plan 12 summary](../.planning/phases/07-career-source-custody-and-private-workspace/07-12-SUMMARY.md)
  supersede Git-history custody, migration, dedicated refs and cleanup protocols.
- Phase 8: the [inventory map](../.scratch/phase-08-career-experience-inventory/map.md)
  links the candidate and review contracts. A resolved generation ticket is not
  inventory acceptance.

Use [STATE](../.planning/STATE.md) for the current handoff. Completed quick-task
summaries establish what was implemented; older planning maps establish decisions
at their recorded point in time and must not silently override later code evidence.
