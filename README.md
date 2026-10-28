# TomorrowStar OS

TomorrowStar is a local personal career and application tool. It ingests jobs
recommended by email and processes one job at a time through analysis, tailored
materials, form filling and upload. **The user performs final Submit.**

## Current product and development

[MC05 original-page takeover](.scratch/remaining-tickets-2026-10-26/mc05-native/final-acceptance-r5.md)
is accepted for controlled-agent, synthetic-page and actual native-tool scope. The same
1799-file snapshot passed7843 default offline cases (2 explicit benchmark skips),224
isolated browser cases (5 native opt-in skips), and8 actual native cases; independent
review verified exact coverage and evidence. MC06 material delivery is claimed, not implemented.
Real-model, installed-App and real-ATS acceptance, T07/T08 and full module acceptance remain
separate. Historical failures and two overwritten static-log originals are disclosed in the report.


The [ordinary preparation migration](.scratch/mc13-preparation-scheduling-2026-10-26/README.md)
moves preparation progression and bound candidates into Flow while Pipeline remains
the single job scheduler. Worker owns exact execution permission; cancelled or
unknown preparation preserves original materials and history. One unchanged
672-file snapshot passed 7,804 default offline cases (two opt-in skips),
then 152 related isolated browser cases. Independent findings were fixed and
reviewed. The installed App and real-service acceptance remain separate.

The [Resume lifecycle migration](.scratch/mc03-resume-lifecycle-2026-10-26/README.md)
brings preparation, reuse, template selection, version reads and PDF operations
under Resume ownership. Recovery reads the original registered attempt and cannot
replay an unknown build. One unchanged 668-file snapshot passed 7,755 default
offline cases (two opt-in skips), followed by 102 related isolated browser cases.
Independent findings were fixed and reviewed. The installed App was not updated.

The [three-ticket module successor](.scratch/mc01-mc02-mc04-implementation-2026-10-26/README.md)
repairs mapped-import Prism successors, moves supplemental human-version adoption
behind Worker-owned conditions, and brings letter lifecycle and exact-version
consistency under their owners. One unchanged source snapshot passed the full
default offline suite (7,722 passed, two explicit opt-in skips), then 89 related
isolated browser cases. Independent findings were fixed and reviewed. The installed
App and Prism upstream were not updated; the remaining module migration stays open.

The [Cover Letter integration](.scratch/cover-letter-integration-2026-10-25/implementation.md)
adds independent same-job body generation, semantic review, text-first delivery
and lazy LaTeX PDF output. The existing JSON resume handoff now has a durable
automatic author adapter; the external handoff mode remains available. Personal
letter templates are explicitly configured outside packaged resources. Source
checks and synthetic regressions remain separate from installed-App and real ATS
acceptance.

The [codebase responsibility audit](docs/codebase-responsibilities.md) maps each
workflow to its Module Interface, records the implemented cleanup and identifies
the remaining legacy migrations. Existing data, human edits and history remain.

The [automatic application specification](docs/single-job-flow.md) defines the product.
The current [JSON content and fixed-rendering design](docs/json-resume-design.md)
and [J01–J08 map](.scratch/json-resume-delivery-2026-10-24/map.md) describe the current
implementation: structured facts and writer JSON, program validation, one fixed
subsection per experience, then TeX/PDF build outputs. J01/J02 provide an
[English synthetic JSON-to-PDF slice](docs/json-resume-operations.md), using default
LaTeX fonts. J03 changes the existing experience store and career-library interfaces
to save and deliver structured facts, with explicit legacy import and preserved
correction history; see [career operations](docs/career-experiences.md). Default
analysis no longer treats retained resume TeX as facts. J04 refactors the existing
default retrieval and matching flow: programs deliver selected facts and references,
stop follow-up searches when no unread candidates remain, and resume a failed stage
from saved upstream results. Completed analysis can reuse unchanged selected facts
across unrelated library or diagnostic metadata changes. Original attempts and
manual materials remain preserved; see [J04 verification](.scratch/json-resume-delivery-2026-10-24/j04-verification.md).
J05 connects the existing default handoff to `content-writing/v1`: actual experience
writers return scoped content JSON, program validation and fixed rendering produce
TeX, and one independent reviewer returns content-field patches or local rewrite
requests. Adoption saves the reviewed content and render manifest in the existing
material version store. The explicit frozen LaTeX template owns style and literal
name, LinkedIn, website, email and education. Current plan/content JSON contains
only variable wording plus application/template metadata. See [operations](docs/resume-agent-operations.md) and
[J05 verification](.scratch/json-resume-delivery-2026-10-24/j05-verification.md).
J06 reconciles uniquely mapped human TeX edits into content versions, retains
unmerged source/diff without overwriting it, and resumes interrupted proofreading
or conditional saves from persisted results. Existing Git-backed Prism projects
are supported without enabling sync. J07 makes ApplicationStore records JSON-primary,
preserving legacy note bytes, IDs and history through preview/import and conflict checks.
See [J06](.scratch/json-resume-delivery-2026-10-24/j06-verification.md),
[J07](.scratch/json-resume-delivery-2026-10-24/j07-verification.md) and
[operations](docs/json-resume-operations.md). J08 connects these contracts through
the default Flow, existing Pipeline and Worker. New tasks require content JSON;
saved legacy tasks remain resumable. Bound Prism edits retain the active PDF until
the original page verifies the candidate and one Continue adopts it. Worker reads
and corrections use the same declared information library as Flow. See
[J08 verification](.scratch/json-resume-delivery-2026-10-24/j08-verification.md)
for offline, actual-author, temporary native Prism and synthetic browser evidence.
The initial current application experience records have now been converted through
the existing conditional-save Interface. Explicitly saved application facts are
available independently of research classification; immutable source identity is
verified on read and delivery, and directory errors remain visible. Original IDs,
raw sources, materials and history remain preserved. Human-accepted wording has
source references and edit protection. See the [full real-input record](.scratch/json-resume-delivery-2026-10-24/full-real-input-verification.md).
The complete default suite and Ruff pass on the stable source. Full real-application experience
writer outputs, one independent content review, fixed rendering and PDF QA have
passed. The fixed real template preserves its accepted style and literal
personal information and education without extra fonts. The subsequent
[P04 and main-flow check](.scratch/json-resume-delivery-2026-10-24/p04-mainflow-verification.md)
has reached `materials_ready` in the same-ID source task snapshot, preserving
the original failure and history. It reuses the saved JD and completed reads,
then validates actual writer JSON, one content review, fixed rendering and native
PDF export. The installed runtime remains unchanged. User Prism service,
installed-App and real ATS acceptance remain separate.
The [development plan](docs/development-plan.md#json-plan-2026-10-24)
and [implementation map](.scratch/resume-agent-delivery-2026-10-22/map.md#implementation-2026-10-23)
record stage boundaries and acceptance order. The source status above does not
claim installed-App or real-application acceptance. Existing facts are reused
from the career library and basic-information library, whose unified experience
directory is generated from career content. Important missing facts, actual conflicts and unknown action
results pause the current job. Manual edits are preserved; one Continue resumes
remaining steps. Healthy work resumes from checkpoints, and explicit waits stay
waiting. Mail ingestion may continue while job execution waits.

The [system audit](docs/system-audit-2026-10-20.md) records implementation gaps and
superseded approval mechanisms. The [development plan](docs/development-plan.md)
is the current execution order, with ticket acceptance criteria and dependencies.
These documents define work to complete; they do not claim the installed App
already implements the complete design. No real application is started by this
document revision.

Default structured-fact deliveries use variable content JSON and an explicitly
bound LaTeX template to produce English TeX. Program rendering replaces only the
summary, skills and experience slots; all other template text remains literal.
The former HTML path is retired. Saved legacy TeX contracts remain readable and
continue through their original adapter. Old sources and manual edits are preserved.
The target workflow reuses Prism-local automatic compilation, preserves the current
template and human edits, and limits post-edit proofreading to small text errors;
see the [resume workflow](docs/resume-agent-generation.md). Existing source template
compaction and export APIs remain implementation history, not additional approval gates.

The native source defaults to the automatic application workspace.
`--prepare-materials` keeps the alternate preparation workspace. The existing
checkout uses persistent recommendation intake and a sequential application
queue. The pipeline coordinates checked complete materials, filling and upload;
healthy reopening verifies the retained worker and page, while explicit pauses,
user waits and unknown outcomes keep waiting. Source verification, installed-App
behavior and real-application acceptance remain separate. Use the
[native App guide](docs/macos-app.md) for setup and
[architecture](ARCHITECTURE.md) for actual modules.

## Data and research

| Responsibility | Home | Contract |
| --- | --- | --- |
| Application product | Native App, `application_*`, worker and browser | [Product specification](docs/single-job-flow.md) |
| Career facts and application information | Explicit separate private workspace | [Two libraries](docs/single-job-flow.md#可验证要求), [data boundaries](docs/data-boundaries.md) |
| Capability research | Contribution audits, assessments, graph and JD experiment | [Research scope](.planning/PROJECT.md), [research requirements](.planning/REQUIREMENTS.md) |
| Developer commands and tests | `scripts/`, `tests/`, `validation/` | [Conventions](CONVENTIONS.md), [verification](docs/validation-runs.md) |

The v1.1 research milestone studies a reviewed career graph and exactly three
real JDs. It does not gate ordinary application preparation or direct user fact
corrections. Research review remains necessary for personal mastery claims.
The v1.0 partial closeout did not empirically validate the full hypothesis.

Personal records stay in the selected private repository. Keep source bodies,
private paths and reports out of this system repository. Reusing those records
for the user's enabled application flow does not require repeated privacy or
material approval.

## Earlier usable-first handoffs (historical)

The following records retain their original scope. Source/JD updates no longer
automatically invalidate saved TeX/PDF or require repeated content review; use the
current development plan. This documentation pass changes no production code or App.

[Ticket 36 now follows the clarified library and application scopes](docs/development-plan.md#ticket36-current-scope):
users maintain the career and information libraries; edits to one application's
resume stay with that application. Keep the existing selective merge and history
protections. The [two scoped checks](.scratch/ticket36-two-mainlines-2026-10-22/README.md) now cover
local-edit isolation/continuation and the fix for explicit library education
corrections being blocked or repeatedly questioned. Existing manual work and
acceptance history remain. No third engineering goal is added; ownership and both pauses remain.

<details>
<summary>Ticket 36 engineering records and earlier bounded evidence</summary>

The [new-context impact follow-up](.scratch/ticket36-new-context-2026-10-22/README.md)
assesses added or unmapped career context against the actual manual TeX. It merges
only affected groups and can retain TeX unchanged when the context is unrelated.
New citations remain bounded to changed sources; manual omissions and wording stay.
Ticket ownership, the App-update pause and the real-application pause remain.

The [omitted-content source mapping follow-up](.scratch/ticket36-omitted-source-map-2026-10-22/README.md)
keeps source impact coverage after manual omissions and repeated updates. Omitted
text stays out of TeX; shared sources still refresh adopted groups. Current manual
source associations take priority, and unaffected wording stays unchanged.
Ticket 36 keeps its owner and status. App updates and real applications stay paused.

The [pending TeX merge follow-up](.scratch/ticket36-unresolved-manual-merge-2026-10-22/README.md)
now preserves manual changes made after a factual verification draft. It rechecks
only pending groups and groups affected by source or JD changes, retaining manual
wording, deletions and order elsewhere. Actual conflicts continue waiting.
Ticket ownership, historical acceptance, the App-update pause and the real-application pause remain.

The [ticket 36 TeX update slice](.scratch/ticket36-tex-impact-2026-10-22/README.md)
uses the latest adopted complete TeX for source and JD updates. It preserves
unaffected text and manual wording, updates contacts directly, and pauses for
important factual conflicts. The report records tests and remaining merge limits;
36 stays claimed with its existing owner. App updates and real applications stay paused.

</details>

The [2026-10-22 fixes](.scratch/two-fixes-remaining-2026-10-22/README.md)
cover qualification confirmation inheritance and retrying a known failed current
JD through Continue. Review content in TeX; a successful build is sufficient for
automatic PDF output, with no separate PDF review or confirmation. Existing
acceptance records remain history. App updates and real applications stay paused.

The [2026-10-22 work and code audit](.scratch/work-audit-2026-10-22/README.md)
records 128 current tickets, 111 closed/resolved and 17 unclosed, the current
source checks and remaining findings. Tickets 39–41 are closed for their source
scope. Latest source, installed App and real acceptance remain separate.

The [39/40/41 source reconciliation](.scratch/ticket39-41-source-2026-10-21/README.md)
records derived Worker page state, shared complete materials and the consolidated
default overview and controls. It preserves explicit compatibility modes and
separates source verification from installed and real-application acceptance.

The [current development plan](docs/development-plan.md) records the delivered
mail-processing setting and progress display, plus the bounded Ashby bootstrap
compatibility slice. Reuse the existing queue, materials and continuation
contracts. The [source handoff](.scratch/mail-settings-implementation-2026-10-21/README.md)
records 4597 default offline passes, two opt-in benchmark skips, and the prepared
minimal installed journey. Installed and real acceptance remain separate; the
App update and real applications are still paused.

The [2026-10-21 audit and dependency ledger](.scratch/usable-first-wayfinder-audit-2026-10-21/README.md)
records exact remaining work, preserved ticket ownership and the latest verified
source inputs. Historical root-cause investigations and research acceptance do
not gate ordinary application feature development.

## Historical delivery evidence

Dated reports describe their own versions and scopes; their old limits are not
current product requirements. Preserve their results without extending a green
synthetic check to real applications or hiring outcomes.

- [2026-10-20 work audit](.scratch/work-audit-2026-10-20/README.md) reconciles the
  current tracker, checkout verification, installed source and remaining acceptance.
- [2026-10-19 audit](.scratch/work-audit-2026-10-19/README.md) and
  [2026-10-20 native continuation](.scratch/remaining18-resumed-2026-10-20/README.md).
- [Material preparation map](.scratch/gmail-resume-preparation-2026-10-17/map.md),
  [single-job map](.scratch/single-job-application-flow-2026-10-16/map.md) and
  [cross-job reuse map](.scratch/cross-job-resume-reuse-2026-10-19/map.md).
- [Installed synthetic material journey](.scratch/material19-installed-journey-2026-10-19/README.md),
  [source reuse](docs/retained-resume-sources.md) and
  [Prism connector](docs/prism-resume-review.md).

The local Markdown tracker remains the status record. From the checkout run
`uv run --locked --offline --no-sync python -B scripts/query_tickets.py --json`.
Use current ticket fields and the new development plan together. A dated count,
a mechanical frontier or a ticket claim does not establish implemented behavior.

## Run the current checkout

The [personal website integration](docs/public-website.md) makes the existing
website a public presentation of selected TomorrowStar content. One public
snapshot supplies the profile, experience, project, skill and library pages.
The local Web UI's **公开展示** panel previews the same selection.

From this repository root:

```sh
uv run --locked python scripts/run_career_evidence.py --help
uv run --locked python scripts/run_pytest.py -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```

The launchers explicitly import this checkout's `src/`. Tests are offline by
default; live model runs require separate opt-in. No personal data is needed to
run the synthetic harness. See [verification details](docs/validation-runs.md).

## Current readiness

| Surface | Implemented | Remaining acceptance boundary |
| --- | --- | --- |
| Contribution audit, assessment, aggregation and JD foundation | Checkout code and deterministic fixtures | Full-career generalization and empirical validation remain milestone work |
| Three-layer question and scoring pipeline | [Protocol](docs/question-scoring-pipeline.md), typed plans, context requests, read-only CLI inspection and [Web preparation entry](docs/career-portal.md#project-interview-preparation) | Inventory-bound generic adapter and three-layer execution delivered; synthetic trials and reviewed personal calibration have separate gates |
| Candidate Skill Links | Optional reminder context in audit/assessment; CLI support | Links never establish mastery or require an extractor |
| Local career workspace | Native macOS App and Web UI: application tracking, documentary retrieval and links | Operational UI only; documentary links do not admit skills or JDs |
| Single-job application workspace | Persistent Gmail/JD intake, sequential routing, documentary match intervals with historical references, checked full-source PDF bindings, required supplemental materials and managed filling | Current source has separate offline and local-browser evidence; later changes still require installed and real-job acceptance in the execution map; final Submit remains manual |
| Private source custody | Explicit-workspace module API | [Independent MVP verification passed](.planning/phases/07-career-source-custody-and-private-workspace/07-VERIFICATION-2026-10-07.md); this does not establish capability |
| Experience inventory | Exact private inventory accepted; first immutable seal independently checked | Linked successor implementation delivered; research snapshot successors retain their acceptance history; APP-04 direct career correction and bounded material updates have source evidence; broader impact precision and real acceptance remain separate; capability assessment still requires review |
| Full graph and three real JDs | Roadmap requirements | No full-hypothesis acceptance claimed |

See the [2026-10-08 delivery record](docs/interview-delivery-2026-10-08.md) for the requested status, adapter and trial work.
See the [completed 2026-10-13 independent verification](.scratch/phase-07-independent-verification-complete-2026-10-13/README.md)
and the [inventory map](.scratch/phase-08-career-experience-inventory/map.md)
for the passed current prerequisite and remaining successor review/seal gates.
The [2026-10-13 open-ticket follow-up](.scratch/open-ticket-audit-2026-10-13-followup/README.md)
retains the claims and dependencies before this verification ticket closed.
The [earlier same-day index](.scratch/open-ticket-audit-2026-10-13/README.md)
retains the queue before the remaining worker decisions were resolved.
The [2026-10-12 work audit](.scratch/work-audit-2026-10-12/README.md)
retains the earlier source and verification snapshot.
The [2026-10-08 project review](docs/project-review-2026-10-08.md) records that dated
readiness and verification snapshot.
See the [2026-09-18 harness review](docs/harness-review-2026-09-18.md) for this
organization pass, confirmed defects, checks and remaining limits.

## Where to change things

- Product behavior: [application specification](docs/single-job-flow.md).
  Current work: [development plan](docs/development-plan.md).
  Research scope: [PROJECT](.planning/PROJECT.md), [REQUIREMENTS](.planning/REQUIREMENTS.md), [ROADMAP](.planning/ROADMAP.md).
- Domain terms: [CONTEXT](CONTEXT.md). Development rules:
  [CONVENTIONS](CONVENTIONS.md) and [AGENTS](AGENTS.md).
- Interview generation and evaluation: [three-layer pipeline](docs/question-scoring-pipeline.md).
  Product authority: [interview protocol](.planning/PROJECT.md#interview-and-assessment-protocol).
- Upstream reuse and licenses: [references](references/README.md).
- Prior decisions: `.planning/milestones/` and completed plan summaries.
  `.scratch/` contains task maps and research, not active runtime state.

Existing fixture, plan and provenance paths remain stable. Historical plans can
describe superseded mechanisms; follow the active contracts linked by the workflow.
