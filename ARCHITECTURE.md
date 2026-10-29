# Architecture

The checkout contains a local native application, its browser executor and the
Career Evidence Graph research harness. [APP-01–18](docs/single-job-flow.md) define
the current product target. [The audit](docs/system-audit-2026-10-20.md) records
actual gaps; [the development plan](docs/development-plan.md) orders changes.
This architecture describes existing modules and the smallest changes needed.
It does not assert that the target loop has passed real acceptance.

The [responsibility audit](docs/codebase-responsibilities.md) defines one purpose
per workflow and records the current cleanup. Intake owns source deliveries;
the native model Adapter owns recorded-result validation; pure scoring owns
candidate comparison; Flow owns effective qualifications and material read state.
Worker snapshots do not create persistent measurement events. Shared identities,
private record directories and information semantics no longer belong to the
browser executor. Pure source projection and input limits no longer depend on the
reader or matcher. Supplemental materials consume fixed deliveries through their
own Module; browser execution consumes the result. Flow owns analysis outcomes,
and target validation no longer constructs a handoff prompt.

`CoverLetterModule` owns fixed author inputs, attempt directories, retries and
result reads. The consistency Module resolves the exact current résumé and letter
pair reserved by Flow. Supplemental field delivery reuses CoverLetter-owned body
and edit rules, with PDF generation only when a file is required. MaterialEdit
coordinates human successors through Worker-owned conditional validation and
commit operations against the original edit record. Mapped imported résumé
successors validate their original template mapping and archive a real slot
template for later reads and reuse. The [three-ticket implementation record](.scratch/mc01-mc02-mc04-implementation-2026-10-26/README.md)
tracks source verification and the remaining control/scheduling boundaries.

Flow exposes read-only preparation progress, ordinary stage continuation and
original-attempt reconciliation. Pipeline consumes those business results and keeps
current-job routing and control. Flow owns bound-material candidate preparation and
export reservation; Worker provides the read-only application/task/batch permission.
Cancelled or stale preparation cannot start new material work, and late results
remain unadopted history. The original material-update record and journal remain
authoritative. See the [ordinary preparation migration](.scratch/mc13-preparation-scheduling-2026-10-26/README.md).

Pipeline reads the current task through `Flow.task_snapshot(task_id)`, which keeps
the Worker and handoff checks without projecting unrelated tasks. Full history
remains available through `snapshot` for display and recovery. Application record
reads reuse each verified JSON only within that call; writes still reread their
baseline. Single-job screening calculates only the selected job while retaining
the complete duplicate and company history. Preparation measurement requests
belong to committed material/group deliveries; GET state projections do not write
those events.

Browser commands retain one loaded, locked state through form sampling and
transport recording, so a later command save cannot discard newly observed
failures or document history. Required supplemental attachments are uploaded and
read back before the final readiness check; a successful upload returns to the
normal parser sampling loop. Explicit original-page inspection remains separate
from final form readiness and preserves unknown action intent. Material Continue
reconciles only its existing local commit journal before reading strict bindings;
completed edits do not restart material generation.
The Ashby attachment Adapter rejects a known remote attachment ID shared by
different material hashes before adopting its receipt and during final verification.
Missing-answer observations are reconciled with current saved answers under the
existing write lock before questions and waiting status are published. Pending
one-use answers are read without consuming commands; late observations preserve
newer execution context and user control. Rejected question publication ends the
old executor turn. Pure readiness publication checks the same current context,
while actual action receipts retain their existing completion history.

Closing a browser does not require lossless session restoration. A saved Codex
handoff can prepare a fresh attempt for the same application and exact PDF.
`application_handoff` owns attempt release/reservation and a local restart receipt;
`application_existing_handoff` owns the unchanged Flow material binding and its
current-attempt projection. Old readbacks remain historical. Saved field values
are scoped hints, not current page state or new global facts. Each new attempt
uses the App's declared information library and obtains fresh claim/readback
state. Read projections neither recreate an execution owner nor commit a Flow
transition. Recommendation snapshots build one request-local identity index to
recognize existing records without a scan for every candidate.

Research contracts remain in [.planning/PROJECT.md](.planning/PROJECT.md).
Their mastery/snapshot reviews do not gate ordinary application facts and materials.

## Codex assistance metadata — 2026-10-25

[T01/T02](.scratch/codex-assist-t01-t02-2026-10-25/implementation.md) add the first
Worker-owned assistance record and a dormant `application_codex_assist` Adapter.
The Worker retains fixed run/page/document/material/answer references and one
writer reservation. Request and claim metadata fence existing script dispatch;
neither grants Codex page authority. Old records retain their script behavior.

The Adapter owns its dedicated stdio process and metadata-only protocol. It
checks the selected version, an empty global MCP table and the thread's verified
four-tool catalog (those tools are pre-approved, since `approvalPolicy: never`
would otherwise refuse their writes), rejects server tool and approval requests,
and exposes no model-turn entry. Narrow configuration
crosses the existing worker launcher; the Adapter is constructed inside the
Worker, without starting a process. It belongs to the existing loaded-code roles.
T01/T02 source verification does not establish original-page tools, active-action
draining, backend-loss recovery, GUI acceptance, real-model isolation, or an App update.

[T03](.scratch/codex-assist-t03-2026-10-25/implementation.md) adds an explicit
read-only original-Page callback and event service. `progress()` consumes and
queues protocol events; `service_readonly()` performs at most one observation
on the owning Worker thread. Control-only ticks keep control and browser events
moving without dispatching queued page work. The observer checks the saved
claim, source, Page, document and material references before and after capture.
It returns bounded text and PNG content. No model turn or page write is enabled.
T03 source and isolated-loopback evidence do not establish active-action draining,
backend-loss recovery, real-model isolation, GUI acceptance or an App update.

[T04/T05](.scratch/codex-assist-t04-t05-2026-10-26/implementation.md) add durable
revocation and separate native terminal, local tool drain and dedicated-process
stop evidence. Backend authority binds a nonce to the kernel process generation;
UI polling is unrelated. Closing revokes before waiting for scheduler cleanup.
Recovery reads the original Page outside the business lock, saves a historical
document proof and retains pause and the original reservation. It does not release
the writer or re-enable the old authority. Actual visual actions and model turns
remain disabled; T06–T11 and the wider Module migration are still in progress.

## JSON content seam — 2026-10-24

[The codebase design](docs/json-resume-design.md) maps the current owning functions,
target Module Interfaces and migration risks. [J01–J08](.scratch/json-resume-delivery-2026-10-24/map.md)
record the delivery order. J01/J02 provide the pure content-contract
Module and fixed renderer Module; see the [synthetic entry](docs/json-resume-operations.md).
The synthetic templates generate English resumes with default LaTeX fonts. Real
accepted templates preserve their existing style without extra font dependencies.
J03 extends the existing
`ExperienceStore` and `CareerLibrary` with semantic JSON content, immutable history,
explicit import coverage and fact-only default analysis inputs. Retained TeX remains
in the material archive and is read by the legacy generator at generation time.
Explicit user-saved application records enter the same library independently of
research `record_class`. Admission verifies the immutable saved record's `origin`
on read and delivery; a directory origin alone cannot establish user authority.
Directory failures retain the existing unavailable diagnostics. This does not reopen
research identity or assessment decisions. The initial current application records
have been converted with original IDs, raw sources, materials and history preserved.
Human-accepted wording is backfilled with references and edit protection. See the
[full real-input record](.scratch/json-resume-delivery-2026-10-24/full-real-input-verification.md).
J04 refactors the existing default retrieval/matching pipeline and Flow attempt
binding. Structured facts are selected by ID and delivered by code with references
and responsibility context. Durable stage checkpoints retain completed JD, planning,
reading and matching results; explicit retry continues the unfinished stage in a new
attempt and preserves the old attempt. Exhausted unread candidates stop follow-up
searches. Completed canonical analyses can reuse unchanged selected facts despite
unrelated library or diagnostic metadata changes, after semantic input checks.
Unknown model outcomes remain unresolved until they can be verified; no blind replay
is added. See [J04 verification](.scratch/json-resume-delivery-2026-10-24/j04-verification.md).
J05 directly refactors the existing experience handoff to `content-writing/v1` for
structured-fact deliveries. Scoped writers return semantic JSON, the program validates
and renders it, and one independent reviewer patches allowed JSON fields or returns
specific experiences for rewriting. Adoption persists reviewed `content.json`, a
render manifest and TeX in the existing draft store. The current `resume-template-plan/v1` and
`resume-template-content/v1` contain variable wording and application/template
metadata, without `profile` or `education`. The required frozen LaTeX template
owns fixed style, literal name, LinkedIn, website, email and education; rendering
replaces only three marked bodies and preserves all other template text. See [J05 verification](.scratch/json-resume-delivery-2026-10-24/j05-verification.md).
J06 reconciles supported human item edits through the fixed renderer and exact re-rendering.
Unsupported template/layout changes retain their exact TeX and diff as unmerged versions;
these versions retain the manual build/export path and cannot be regenerated from stale content JSON.
Every adopted version persists human list protection and omitted experience IDs;
consecutive manual returns or narrower deliveries cannot erase earlier edit intent.
Finishing checkpoints resume captured text, saved proofreading responses, conditional
writes and draft adoption without repeating unknown operations. Existing Git-backed
Prism projects are supported without enabling sync; metadata never enters source archives.
J07 makes versioned JSON the ApplicationStore primary format. Existing Markdown notes
remain readable and retain their bytes, IDs and history when explicitly or lazily adopted.
See [J06](.scratch/json-resume-delivery-2026-10-24/j06-verification.md) and
[J07](.scratch/json-resume-delivery-2026-10-24/j07-verification.md) for evidence scope.
J08 marks new Flow tasks with `material_contract="content-writing/v1"`; incomplete
raw deliveries wait for structured facts instead of entering legacy TeX writing.
Saved tasks without that marker retain their original recovery route. Automatic
template selection resolves the archived fixed template rather than a previous
rendered resume. The initial binding supports Git-backed project roots while
excluding Git metadata from source snapshots and keeping synchronization disabled.

For an already bound Worker, Prism edits create a staged material candidate. Finishing
and capturing preserve the old active draft, PDF and Worker binding. A capture
requires the returned editable draft. One Pipeline Continue verifies the original
page and adopts the candidate through the existing material transaction; it reuses
the saved build result. Failed or late results retain the old material. Worker
answer reads, writes, corrections and send checks resolve the information-library
root from the verified local Flow task, never from a browser-supplied path. Legacy
standalone jobs retain their existing answer store. See
[J08 verification](.scratch/json-resume-delivery-2026-10-24/j08-verification.md).
The prior stable source passed the full default suite and Ruff. The standalone
full real-application experience JSON, independent content review, fixed rendering and PDF QA
passed; see the [full real-input record](.scratch/json-resume-delivery-2026-10-24/full-real-input-verification.md).
The subsequent [P04 and main-flow verification](.scratch/json-resume-delivery-2026-10-24/p04-mainflow-verification.md)
reaches `materials_ready` through the same-ID source task snapshot and retained
history. Saved JD and reading results survive recovery. Fixed adopted deliveries
also own export eligibility; unknown or conflicting qualifications still stop.
The original installed runtime remains unchanged. These checks do not establish
installed-App or real ATS acceptance.
The table below describes current code and retained legacy contracts.

## Existing modules and implementation limits

| Module | Responsibility |
|---|---|
| `domain/models.py`, `domain/invariants.py` | Strict records and Contribution-grounded lineage, attribution, and score-separation checks. |
| `domain/fixtures.py` | Pinned STOA source scope, reviewed documentary fixture sealing, and deterministic negative cases. |
| `audit/` | Prepare project-overview, technical-depth and transfer question plans; validate supplied-context binding through the shared `validate_project_interview_plan` API and read-only CLI; inspect a Contribution, ask one capability question at a time, record attribution, and review a conclusion. The decision port supplies data; the workflow owns state transitions. |
| `interview.py` | Inventory-bound three-layer sequencing, original prior-answer context, independent layer review, pause/resume and complete inventory queue. It reuses the audit engine; a private callback supplies full seal verification. |
| `interview_calibration.py`, `scripts/run_interview_calibration.py` | Opt-in frozen synthetic trials, exact case coverage, separate boundary/anchor observations and retained failures. They authorize no personal scores. |
| `assessment.py` | Create and review assessment proposals, apply admission policy, preserve reassessment lineage, and aggregate admitted same-Skill observations. |
| `jd.py` | Retain and accept source-bound JD packets, then project relevance without mutating the career graph. |
| `validation/` | Charter, hashing, immutable formal-run bundles, recorded-response replay, and upstream provenance. |
| `workspace.py` | Explicit private-workspace selection, source registry, retained raw bytes, optional derived-text mappings, and source-universe snapshots/successors. |
| `career_experiences.py`, `application_career_library.py`, `career_experience_import.py`, `scripts/run_career_experiences.py` | Existing candidate IDs and immutable history now support v2 semantic facts. Explicit user-saved application records are admitted independently of research classification, with immutable origin checks at read and delivery and retained directory-error diagnostics. The pure import helper validates literal source coverage and fact/source mappings before the existing store publishes a revision. Sync preserves structured corrections and tracks changed supplements as pending import. The directory derives from full fact fields; analysis delivers individual facts with their responsibility, status and source binding. Legacy records remain readable; historical/generated material does not enter current fact retrieval. See [operations](docs/career-experiences.md). |
| `application_job_brief.py`, `application_matching_pipeline.py` | P02 publishes one JD-only business interpretation before applicant retrieval. A durable fixed brief supplies atomic requirements, original Boolean group relations and conserved group weights to retrieval, matching, refresh and writing. J04 checkpoints the existing stages and reconciles saved results on explicit retry, so a P04 failure retains the completed JD interpretation and reads. Unknown results are not blindly repeated. Program scoring preserves unknown intervals and separate group-aware eligibility; no numeric auto-skip threshold is added. Historical analyses retain their legacy contract. See [framework rules](docs/job-brief.md). |
| `application_retrieval.py`, `application_material_packet.py`, `application_matching_pipeline.py` | P03 searches every thin-directory page and overlapping fragment, reads bodies for incomplete discovery entries, expands selected related records and delivers a fixed material packet. J04 selects complete structured facts by ID; code obtains their full text, references and responsibility context. Legacy raw sources retain bounded ranges and literal offsets through the existing adapter. Input-bound read receipts resume completed reads. Follow-up matching stops when all candidates have actually been read, while selected but unread candidates remain eligible. Failed, partial or oversized required reads stop before scoring. Writers receive only their allocated source subset and keep unrelated fragment reuse. See [packet operations](docs/material-packet.md). |
| `application_material_sources.py`, `application_input_limits.py` | Pure source expansion, model projection, structured facts, literal quotation and source offsets; explicit environment-based input limits. Reader, matcher and writer share this Interface without depending on each other's Implementation. |
| `application_match_scoring.py` | Pure scoring and qualification classification over a fixed framework and supplied judgments. JD construction owns the framework; matching supplies judgments; display consumes the delivered result. |
| `application_inference.py`, `application_match.py`, `application_explanations.py` | P04 binds direct, deterministic and semantic conclusions to fixed atomic requirements and program-owned literal fact references. Date calculations fail on inconsistent output; semantic conclusions receive no automatic discount. Business fit, qualification, reading coverage and adopted resume coverage remain separate. No second matching reviewer or permanent fact write is added. See [inference rules](docs/match-inference.md). |
| `application_writing.py`, `application_experience_latex.py`, `application_experience_content.py` | The existing P05 handoff uses `content-writing/v1` when delivered sources contain canonical facts. It freezes a `resume-template-plan/v1` content plan and explicit TeX template, scopes each assignment and JSON output schema, validates per-item references and renders variable `resume-template-content/v1` through `application_resume_render.py`. Fixed literal identity, education, section headings and style remain in the template. The main writer owns global JSON; one independent reviewer patches AI text/links or returns affected experience IDs. Human JSON and omissions are protected; unmapped human TeX stops regeneration. Existing CLI/actions and saved legacy contracts continue. See [operations](docs/resume-agent-operations.md). |
| `application_resume_versions.py` | J05 adopts reviewed content into the existing immutable material store as `content.json`, `render-manifest.json`, TeX/source archives and `draft.json`. Read-time checks rebuild archived content and verify the final review/content/render binding without live-library reads. J06 persists mapped or unmerged human versions, recoverable finishing checkpoints and build receipts bound to actual source and reconciliation identity. `application_content_reconcile.py` is a pure exact-renderer mapper, not a general TeX parser. |
| `application_materials.py`, `application_single_binding.py` | Supplemental material generation consumes observed requirements and verified fixed inputs. The material Module owns attempts, retained results, versions and adoption; browser execution owns fresh observation, field mapping and writes. Shared binding readers and qualification policy validate current delivery lineage without reopening the career catalog or rerunning language screening. Legacy tasks retain their existing Adapter. |
| `cli.py`, `codex_cli.py` | Operator dispatch and the separately enabled model transport gate. |
| `career_portal.py`, `career_portal_data.py`, `portal_static/` | Loopback Web UI, JSON-primary `ApplicationStore` with explicit legacy Markdown import/preview, read-only career-document catalog and three-layer interview preparation; plan inspection shares the audit API, and documentary links remain outside assessment admission. |
| `career_portal_graph.py`, `portal_static/graph.js` | Source-cited documentary project/skill projection and interactive graph; no canonical Skill writes or scoring. |
| `public_site.py`, `scripts/run_public_site.py` | Explicitly selected public presentation, typed export, one atomic website snapshot and declared skill-to-project navigation. The private source remains separate. No source-vault traversal, assessment writes or remote publication. |
| `application_automation.py` | Read-only, revision-bound target validation shared by execution callers. The separate handoff composition restricts the external Codex Job Apply pilot to Lever/Greenhouse and constructs its prompt only when requested. No browser execution or submission occurs in this Module. |
| `application_pipeline.py`, `application_flow.py`, `application_material_batch.py`, `portal_static/application_flow.js`, `macos/server.py` | Native default application workspace. One workflow activation consumes a persistent sequential recommendation queue, applies the existing matching route, generates checked complete materials and coordinates filling/upload. The backend owns current-job advancement and its worker heartbeat independently of the WebView route. Only mail capture continues during a user wait. Reopening verifies the retained owner and page before resuming healthy work; explicit pauses and unknown outcomes stay waiting. Final Submit is manual. `--prepare-materials` retains its separate material workspace and batches. Current source, installed behavior and real-window acceptance remain separate. |
| `application_match.py`, `application_benchmark.py` | Retained legacy/raw-source analysis and benchmark Adapter. Its required/preferred weights 3:1 and partial support 0.5 produce lower/upper/coverage; current fixed-framework scoring belongs to `application_match_scoring.py`. Unknown is not a known gap. Hard eligibility stays separate. Historical intervals provide descriptive references, not hiring predictions or Skill mastery. |
| `application_gmail.py`, `application_intake.py`, `application_recommendations.py`, `application_job_source.py` | Incremental asynchronous Gmail search/read through the existing connector, durable original mail/recommendation/link capture and an independent processing ledger. Label/archive follows successful local capture; failed or unknown mailbox steps retain their own recovery state. API page size does not limit the total queue. Complete-JD acquisition and idempotent application adoption occur per current job. No copied credentials are needed. Captures remain private; real mailbox acceptance is separate from synthetic verification. |
| `application_single_binding.py` | Cross-process validation of exact adopted analysis, draft/export artifacts, PDF, target, country, send scope and execution owner. Delivered local materials retain saved inputs across upstream changes; P03 input and selected-read snapshots remain distinct. Legacy raw materials keep their current-input checks. All paths are read-only and preserve unresolved actions. See [combined delivery](docs/combined-delivery.md). |
| `application_handoff.py`, `scripts/run_codex_handoff.py`, `portal_static/handoff.js` | Retained explicit Codex handoff: approved PDF and scoped answers, version-bound claim, executor readback, human review/submission/receipt assertions, recoverable note sync and retained unknown outcomes. No browser or provider execution. Independent private root; human assertions are not independently verified ATS receipts. |
| `application_execution.py` | Persistent exact-owner reservations shared by Codex and the explicit automated lane. No automatic expiry or takeover; released receipts support crash recovery without changing a new owner's reservation. |
| `application_resume.py`, `application_draft.py` | Job-specific private drafts from current analysis selection and the same source snapshot. Preparation saves an independently readable draft checkpoint, with English-default language admission and mechanical source differences. Original/final text, attribution, explicit regeneration and the retained application mode's exact PDF bytes remain reviewable. Candidate Skill records do not establish mastery. |
| `application_resume_versions.py`, `application_proofread.py`, `application_prism.py` | P06 captures explicit human returns as immutable main-text versions, runs one bounded proofreading attempt, and applies only local text patches through Prism's source-hash conditional save. Final PDFs separately archive the native recorder's actual dependencies and output hash through read-only build-result receipts. Pending source edits, old final PDFs and uploaded attachments retain independent identities. Missing capabilities, unsupported layouts and unknown results preserve the old final. See [Prism operations and limits](docs/prism-resume-review.md). |
| `application_experience_latex.py`, `scripts/run_experience_generation.py` | Retained legacy/raw-source Adapter for durable experience fragments inside existing resume versions. Explicit source/body mapping, bounded reads, unchanged-fragment reuse, program assembly and hash-bound review/adoption remain. Current structured-fact writing uses JSON through `application_writing.py`. Python launches no agents; Flow resumes an adopted result through existing automatic export. See [operations](docs/resume-agent-operations.md). |
| `application_source_reuse.py`, `application_full_latex.py` | Retained legacy/raw-source Adapter for hash-bound reuse of human-accepted excerpts. Its education mapping binds the documentary record and original interval; current JSON writing keeps fixed identity and education in the explicit LaTeX template. Reused wording and source references do not create new factual or PDF acceptance. See [source reuse](docs/retained-resume-sources.md). |
| `job_screening.py` | Read-only AI/ML and Quant relevance, unresolved requirements, platform compatibility, canonical duplicates and saved deadline/language checks. Routes saved JD/evidence judgments, personal priority, target-company preference and compensation value to batch, manual precision, review or hold. Live batch admission and single-job precision review reuse this projection. Hints do not establish qualification or change application status. |
| `application_form_state.py`, `application_form_runner.py` | P07 extends the existing Worker: retained-document field/attachment baselines, bounded parser stability observations, conservative comparisons and application-only choices. Exact target readback reconciles existing attempts; uncertain outcomes retain their original intent. Every send re-reads its bound snapshot, and readiness plus handoff keep the independent manual Submit boundary. See [ATS continuation](docs/ats-continuation.md). |
| `application_worker.py`, `application_worker_browser.py`, `ats_forms.py`, `hosted_ats.py`, `ashby_drafts.py`, `portal_static/worker.js` | Shared managed executor for the explicit single-job flow and older lab: scoped answers, approved PDF binding, dedicated browser, checkpoints, controller lease and manual handoff. The Pipeline prepares and starts its explicitly selected job; standalone preparation remains paused until explicitly resumed. Its HTTP surface rejects legacy unbound mutations. Standalone synthetic mode and the explicit live lab retain separate stores; the latter admits at most three jobs. Supported adapters share generic controls and the independent final-Submit boundary. Ordinary reads, draft saves, filling and uploads do not add per-request approval; unsupported controls and unknown outcomes retain concrete recovery states. `lever_worker.py` preserves the old import path; model question-equivalence judgments remain disabled. See the [single-job guide](docs/single-job-flow.md) and [worker contracts/history](docs/application-worker-workflow.md). |
| `cua_driver.py` | Optional macOS CuaDriver native MCP transport and worker-owned isolated browser. LaunchServices starts hidden with no page; bounded Cua sessions attach to the exact native window. Background tabs share that hidden window. User-requested review restores the original page and attachment. Session refresh preserves the browser and pages. The worker delegates only confirmed select-only combobox operations. It retains the same intent, lease, input checks, request guards, readback and manual final submission. No Hermes runtime or second state store. See [Cua integration](docs/cua-worker.md). |

Source-derived Candidate Skill Links are optional retrieval/recall context for
an audit. They do not establish canonical Skills or mastery. The authoritative vocabulary is in [CONTEXT.md](CONTEXT.md). Product behavior
is in [the application specification](docs/single-job-flow.md);
[workflows](docs/workflows.md) separates operational and research entries.

The application Pipeline owns the current job, run intention, wait and next-job
selection. Flow persists material stages, attempts, adopted artifacts and history;
new Worker bindings contain only batch/job references. Worker owns page execution,
commands, intent and observations. Flow snapshots derive the current page status
without saving it or changing the material revision. Old copied page fields are
readable history, not recovery authority. Material reuse reads retained material
records, so a temporarily unreadable page does not invalidate an existing PDF.
Bound-material adoption also saves references rather than a new page-state copy.

Default application and preparation material stages share JSON content validation,
fixed-template rendering, compilation and reuse. One semantic reviewer checks new
content before adoption. Compilation checks actual source/PDF correspondence;
automatic materials do not require a separate user PDF confirmation. Saved legacy
tasks retain their original writing contract.
Ordinary application materials do
not require draft, group or PDF approval. Explicit preparation, Prism, handoff and
lab modes retain their useful editing and historical compatibility. The default
overview displays the same Flow/Pipeline read view; it does not schedule work.
The [source reconciliation](.scratch/ticket39-41-source-2026-10-21/README.md)
records the exact changes, retained calls and verification scope.

## Target responsibility changes

Reuse the existing controller and stores before introducing a framework or a new
database. These are implementation seams, not a new set of approval services.

| Existing area | Required change |
| --- | --- |
| Gmail / intake / recommendations | Durable original mail and recommendation/link capture; processing ledger separate from read/unread; label/archive only after capture; automatic incremental continuation. Full JD acquisition remains per job. |
| Pipeline / flow / screening | One durable job cursor and actual match-route dispatch; continuous linear advancement, explicit waits, skip/return and checkpoint recovery. No total count or elapsed-run cap. |
| Career catalog / information / worker answers | Career facts read and corrected through the career library; application answers in the information library. Semantic applicability, direct saved answers and important ambiguity handling. |
| Resume / full LaTeX / PDF reuse | Share the mature complete-material path with ordinary applications; automatic checks and necessary attachments; high-value draft handoff. Recompute only affected outputs and preserve edited versions. |
| Worker / browser / ATS adapters | Adapted or general browser execution, normal navigation/upload and current-page readback. One Continue after manual intervention; separate final-submit restriction; observe the user's submission result. |
| Readiness / native host | Actual current capability failures stop affected operations. Keep owner/atomicity correctness. Do not invalidate a healthy run when a successful permission check changes a diagnostic epoch. Package/identity proofs support maintenance, not every action. |

## Existing persistence and alternate-mode scope

The descriptions below record current stores and their retained implementation
contracts. Incompatible approval, fixed-snapshot and restart rules are migration
work in the development plan; they do not override APP-01–18. Preserve historical
receipts and research acceptance without replaying their ceremonies per job.


The native preparation entry reuses `ApplicationFlowService` in a mode-bound
`material-preparation` root, with no worker, legacy ownership reads or filling
callbacks. `application_preparation.py` projects local dependency readiness and
binds the selected career directory, confirmed policy version and local connection
context to task inputs. It does not verify remote accounts or execute dependencies.
The native App defaults to the complete application path; `--single-job-flow`
remains an explicit alias, and `--prepare-materials` selects this local-only mode.

`application_explanations.py` projects the existing documentary match formula,
independent qualification, task progress and original source reasons. It retains
historical results when inputs change. Manual ordering changes only order.
`application_information.py` reads bounded, validated snapshots of the explicit
existing answer library without initialization or migration. Only reviewed single
language CEFR conditions can be automatically supported; unresolved conditions
retain user clarification. Qualification corrections invalidate résumé materials
and prevent adoption of an in-flight result from the old facts. Library or policy
refresh can retain documentary analysis while requiring current fact confirmation.

Preparation's résumé stage adopts `kind=draft` as `draft_ready`, with separate
draft ID/hash and no PDF binding. The immutable `draft.json` checkpoint precedes
any export; reads verify bounded regular files and the artifact's expected hash.
The user explicitly records review of that exact version and input binding;
append-only review history survives regeneration and input changes. Review is
separate from PDF confirmation and real-content acceptance. Empty selection or
empty model output cannot become a successful draft. Deterministic token findings
are review aids, not semantic fact verification. A separate preparation `export`
stage prints the reviewed checkpoint with the existing A4 template. Each attempt
saves an intent, PDF/HTML hashes and a complete manifest in its own directory.
Renderer identity is independent of model configuration; export retry never calls
the model. Unknown publication or an interrupted running export requires read-only
receipt reconciliation. A recovered queued export was never admitted and permits
explicit retry. Cancelled, stale or superseded attempts cannot adopt late output.
Preview requires an adopted manifest and verified bytes; current material approval
also checks draft review, input and renderer bindings. Structural PDF checks are
bounded integrity checks; real renderer text/page/pixel QA and real-content human
acceptance are separate evidence. The legacy application mode keeps its existing PDF path.

Material batches are optional records in the same `flow.json`, with immutable
batch snapshots, explicit selected versions, a control epoch, per-item reasons and
the current task binding. They reuse the one flow queue and thread. Creation,
GET, refresh and restart never start work. Explicit resume admits at most one
job; known failures and missing qualifications retain independent dispositions.
Retry only re-enables a selected failed item. Required source capture uses the
existing intake controls and receipts before manual retry; a changed existing
Application JD is not silently replaced by a recommendation. Unknown results stop
admission and require exact bound reconciliation evidence. Materials confirmation
stops at `waiting_application_record`; it does not mark submission or move to the
next job. Batch cancellation preserves records. Task input epochs and latest-task
admission prevent A→B→A changes from reviving an older result.

Preparation recovery appends a task-local interruption record for each queued or
running stage, bound to its original attempt, input generation and JD. Reopening
an already recovered or completed task adds no interruption and queues no work.
The existing owner lock prevents a new service from retrying while the prior
executor is still alive. Closing and checkpoint adoption share the application
lock, so their ordering defines which result can be retained.
The preparation HTTP snapshot exposes a startup service identity and loaded
engine revision separately from task, input and served UI revisions. These are
diagnostic identities, not installed-version or human-acceptance claims.

The audit uses one schema-validated atomic snapshot per audit ID. Assessment and
formal-run records preserve their proposal/review lineage in separate bundles.
These stores serve a trusted local operator; they are not a multi-user database
or a general transaction/recovery engine.

The explicitly requested [career workspace UI](docs/career-portal.md) reuses the
private-workspace check and existing application-note format. Application edits
retain original-byte backups, check the editor's revision, and atomically replace
only the selected note. The UI uses a stdlib HTTP server and native browser APIs;
it introduces no framework or database. Gmail access reuses the connected Codex
CLI; the App stores no mailbox credentials or separate mailbox client. Career
documents are read-only in the current catalog; APP-04 requires direct user
correction with source/history in that same career authority, not a second ledger. Its optional saved folder selection stays outside the checkout.

`application_intake.py` persists a fixed query/window, connector identity, private
cursor, unread range and pending candidates. Before each mailbox page, a separate
read-only profile call verifies the connected account; changed account or local
scope stops continuation. UTC dates become epoch seconds because Gmail date
strings use PST ([Gmail filtering](https://developers.google.com/workspace/gmail/api/guides/filtering)).
`RecommendationStore` journals acquisition per job before publishing a complete
JD. Completed captures are reused; known failures need explicit retry, while an
uncertain save permits only local receipt reconciliation. Structured candidate
acquisition also works without Gmail. Raw captures and checkpoints remain private;
the UI receives progress counts and source details, without mailbox identity or cursor.

The native flow and worker use separate `single-job-flow` and `single-job-worker`
roots. Old handoff/lab/worker roots participate only in strict occupancy checks.
New captures, model records, generated materials and task snapshots remain private.
These operational application tools do not complete the career-graph hypothesis gates.

Phase 7 source custody is a direct function API in `workspace.py`. There is no
`career-source` CLI, separate source store, or private-workspace auto-discovery.
The [MVP simplification addendum](.planning/phases/07-career-source-custody-and-private-workspace/07-MVP-SIMPLIFICATION-ADDENDUM.md)
supersedes the old commit/ref/migration/cleanup custody design. Later
source-universe snapshots and captured-source successors preserve candidate
provenance, not accepted inventory or mastery authority.

Public code, synthetic test inputs, project workflow records, and personal
records have separate homes. Their exact responsibilities are in
[data boundaries](docs/data-boundaries.md). The first full-career inventory is accepted and sealed. A source-specific private
operator verifies that seal and its complete lineage before the shared adapter
can act. Linked successors preserve parent bytes and require exact acceptance when used as research inputs. APP-04 requires direct operational career correction with history; the current catalog is still read-only, so this remains implementation work. The
adapter stores one atomic interview snapshot with separate embedded layer audits.
A changed accepted revision blocks continuation without rewriting history. Real
personal calibration, the confirmed career graph and real-JD evaluation remain
pending; synthetic harness coverage does not substitute for those gates.

## Checkout and package boundary

Use `scripts/run_career_evidence.py` and `scripts/run_pytest.py` from the repository
root for checkout work. The launchers select the local source package explicitly.
The in-tree build backend creates wheels containing Python modules and metadata;
it does not package `validation/`, `.planning/`, or reference repositories.

Fixture sealing depends on the checkout's validation inputs and its unique
active-or-archived Phase 2 checkpoint. Private-workspace boundary checking also uses the
checkout identity. A successful wheel import/metadata test therefore does not
establish installed-package support for the complete operator workflow. Formal
bundle publication currently uses native no-replace rename on macOS/Linux and
fails closed when that operation is unavailable.

Upstream reuse decisions and pinned licenses are maintained in
[references/README.md](references/README.md), with the machine-readable registry
in `validation/provenance/registry.json`.
