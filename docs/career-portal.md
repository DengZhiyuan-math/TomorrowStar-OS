# Local career workspace

## Product requirement — 2026-10-20

Daily application behavior is defined by the [single-job flow](single-job-flow.md);
implementation work is ordered in the [development plan](development-plan.md).
The App is a local personal tool. Existing tracker, interview, graph and handoff
interfaces below describe their own implementation, not additional approvals for
the automatic application flow. This update does not change code or installed behavior.

Enable once to ingest recommendation email continuously, with no fixed mail/job
count or overall run limit. Persist the original email, recommendation entries
and links, then label and archive it; read/unread is independent of processing.
Read each full JD when its job is processed, reusing login state. Handle jobs
strictly one at a time. Ordinary jobs proceed automatically to manual Submit;
high-value jobs first receive complete analysis and material drafts for precise
user adjustment, and low-match jobs are skipped with a reason.

An important missing fact, actual conflict, login challenge, stalled/timed-out
operation or unknown result stops the current job. Only email ingestion continues.
The user may skip and return later. After manual edits, one Continue action preserves
them and resumes remaining work. Reopen resumes normal work; deliberate pauses and
user waits stay waiting. Clear submission success is recognized and recorded
automatically after manual Submit, without separate submission/receipt declarations.

Career facts belong to the career library; application information, reusable answers
and miscellaneous facts belong to the information library. Explicit additions or
corrections are saved with source and history. Scope and ordinary prose are decided
by the system. Changes update only affected material, based on the user's edited
version; usable results survive model-configuration changes. Neither library update
nor each source/PDF version needs another approval. Skill scoring remains a separate
research responsibility.

The local Web UI joins application tracking and career-document retrieval in one
workspace. It reads the existing Obsidian application notes and the separately
selected private career repository. The notes remain the application source of
truth; no second application database is created.

For the shared application worker, resume review, scoped answers and recovery,
use the [current workflow and test overview](application-worker-workflow.md).

This interface was explicitly requested after the harness organization review.
It adds a local operator surface; it does not close the v1.1 inventory, Grill-Me,
Skill assessment or three-JD acceptance gates.

## Start

From the system checkout, supply both existing private locations once:

```sh
uv run --locked python scripts/run_career_portal.py \
  --applications "/path/to/private/Job Applications" \
  --career-workspace "/path/to/private/career-data" \
  --save-config --open
```

The application folder must be outside the system repository. The career folder
must pass the existing separate-Git-workspace check. The server listens only on
`127.0.0.1`, normally port `8765`; use `--port` to change it. Stop with Ctrl-C.

`--save-config` stores only the selected paths in
`~/Library/Application Support/TomorrowStar/portal.json`, with owner-only file
permissions. It does not store personal records or credentials there. Subsequent
launches can use:

```sh
uv run --locked python scripts/run_career_portal.py --open
```

Without `--save-config`, pass both paths on every launch. The source-custody
module API keeps its explicit-workspace contract; it does not consume the UI
configuration. Tests never read this configuration or real personal data.

## Daily workflow

The native source defaults to the [single-job application workspace](single-job-flow.md).
The current pipeline is not yet the complete continuous product flow described above;
its implementation gaps and verification are tracked in the development plan.
The following steps describe only the retained
[explicit Codex handoff mode](codex-handoff.md), enabled with `--handoff-root` in the
checkout server. Its approved-PDF, review and submission-confirmation steps are old
interface restrictions, not requirements for normal operation. The browser lab remains separate.

1. Open **今日工作**. The first card reads the persistent handoff state and shows
   the current job, required next action and five workflow stages. Missing or
   unverified state shows connection/recheck guidance instead of completed progress.
   Application-note actions and deadlines follow below.
2. In **岗位与进度**, add or find a job, review its evaluation and routing, and save
   the source link, JD, relevant evidence and next action.
3. Open **申请交接** from the job detail or overview. Prepare the saved job with its
   country and approved PDF. Copy the prepared task to Codex for claiming and execution.
4. After Codex saves readback, review the original fields and attachment. Record
   review, submit manually on the original page, then confirm submission in the
   workspace. Record synchronization and receipt sources remain separate steps.
   Unknown results stop for explicit recheck. Task metadata, execution instructions
   and event history are available in disclosures.
5. Explore the career relationship graph or switch to the document list. Select a
   skill to see connected projects, inspect each relationship's source, and open
   the original material. Link relevant documents to an application from its editor.
   These are documentary associations, not audited skills or accepted JD packets.
6. Export the current application collection as CSV when needed. The download
   contains personal data and belongs in a private location.
7. Open **项目访谈** from navigation, the overview card, or a document's
   **用于访谈准备** action. Search source context and review the three ordered
   layers before preparing questions.

The older [read-only task prompt](application-automation.md) is a secondary
preparation tool. It does not replace persistent claiming, readback or review.
The old tracker does not infer employer replies or outcomes from age. The product
records observed submission success automatically; it does not infer a hiring outcome.
Checkout UI changes require a new native build before they
appear in an installed App.

The keyboard shortcuts are `/` for search and `N` for a new application, while
outside text inputs. Browser refresh rereads the original folders.

## Project interview preparation

The `#interview` view integrates the [three-layer protocol](question-scoring-pipeline.md)
into the local workspace. It preserves the order: project overview, technical
depth, then transfer under an explicit changed condition. Layer and difficulty
are separate. The view explains criteria, recall handling and attribution, and
reads the full current protocol from the system document on demand.

Search by project name or source path. Select a catalog document to open its
existing read-only detail. A document's **用于访谈准备** action returns to this
view with that source selected. The source is retrieval context; selection does
not accept an inventory identity or bind it to a submitted question plan.

Under **检查已有问题计划**, select the prepared plan JSON and inspected-facts
JSON described in the protocol, then enter the expected Experience ID. The UI
sends this bounded input only to the same loopback server. The CLI and Web UI
share `inspect_project_interview_plan` and its context-binding validator.
The response contains preparation metadata and counts, never source bodies or
scores. The files and answers are not saved, and no model is called.

A passing check enables three-layer question previews. Depth and transfer each
offer independent difficulty previews. Questions and predeclared criteria are
rendered as text. Changing either file or the expected Experience ID invalidates
the old result immediately. Clearing the preview discards browser-session state.
The combined request limit is 1 MiB; existing same-origin, Host and CSRF guards
apply to the inspection POST even though it is read-only.

This view supports preparation. It does not implement a full interview runner,
verify raw-source custody or inventory acceptance, validate semantic question
quality, or admit Skill scores. The generic adapter, question trial and reviewed
calibration gates remain visible as pending before formal personal questioning.

## Career relationship graph

The career page starts with a dark, interactive graph. Gold project nodes and
cyan skill nodes reveal shared context; document nodes can be enabled separately.
Search keeps matching nodes and their immediate neighbors visible. Select a node
to inspect related projects/skills and source-line citations in the side panel.
The neighborhood toggle isolates its connections. Drag nodes, pan empty canvas,
scroll to zoom, or use the zoom/fit/reset controls. The keyboard-accessible node
list provides the same selection and source actions without using the canvas.

Relationships are an inspectable projection of existing local documents:

- Explicit candidate-skill tables retain the reason and examination state. A
  statement excluding assisted implementation does not exclude a separate user
  design candidate. Rows explicitly excluded as a whole produce no candidate edge.
- A finite display vocabulary recognizes literal technology names only inside
  explicitly titled Technology/technology-stack sections. These edges are labelled
  as documentary mentions, with the exact source line; they do not assert mastery.
- Markdown references, backticked catalog paths and unambiguous wikilinks connect
  only already admitted catalog documents. They cannot load arbitrary paths or
  expand access to hidden raw/inventory records. Project context is resolved from
  explicit source/full-report references, not fuzzy title similarity.
- When a `reports/projects/` hierarchy is present, its substantive reports define
  project contexts. Flat report folders also work. Index/catalog files and reports
  explicitly excluded from career-skill evidence remain document nodes.
- Repeated relationships are combined while preserving their distinct citations.
  Node size represents the number of neighbors, never mastery or confidence.

This graph is deliberately separate from the canonical reviewed Skill graph.
Missing edges mean no supported relationship was extracted by these rules; they
are not negative capability evidence. Conflicting statements in different source
documents remain reviewable in their own context. Nothing is written back by graph
browsing, and no external model or graph database is involved.

`/api/graph` loads lazily so ordinary application tracking remains fast. Successful
document reads are cached only in process memory and invalidated by file mtime
and size; removed files are dropped. Reads reuse the existing 2 MB/3-second limit,
with at most eight concurrent reads and an approximately eight-second total wait
bound. At most 300 catalog files are processed per snapshot. Unavailable or omitted
inputs produce visible source warnings instead of fabricated relationships.

## Storage and compatibility

`ApplicationStore` keeps its existing create/read/update Interface. New records use
`application-record/v1` JSON with a persisted application ID, full JD, status, links
and existing query fields. Daily JSON reads and writes do not parse Markdown.
No new dependency is required.

- Existing Markdown records remain readable. Their first ordinary update adopts
  JSON with the same ID and retains the original Markdown byte for byte. Explicit
  `preview_application_import()` and `import_application()` use the same store.
- Preview reports normalized fields, old/new file mapping and unmapped properties
  without writing files. Unknown legacy properties and sections remain in the
  original source/archive; they are not silently claimed as normalized fields.
- JSON is authoritative after adoption. `legacy_source_name` and
  `legacy_source_changed` show whether the retained original has changed. Such
  changes require explicit import. If both sources changed, import reports a
  conflict and preserves both. No Markdown mirror becomes a second authority.
- Updates require the current record revision. Exact pre-update JSON or Markdown
  bytes are retained under `.tomorrowstar-history/<record-id>/`. Publication is
  atomic; malformed or redirected primary JSON fails closed.
- Creation request IDs and import parent revisions allow an interrupted publication
  to be adopted locally. Changed request content or later human changes still
  conflict. Recommendation recovery recognizes the JSON record without creating
  another application. Workflow, material and action references retain the old ID.
  The pending creation payload survives closing and reopening the form in the same
  page. After a full reload, inspect existing records before creating again.
- Saving and screening retain separate outcomes. A failed screening does not undo
  a saved record or require saving it again. The UI reports the saved record and
  a separate warning; refreshing retries screening.
- Worker checkpoints continue to bind the selected application directory. A copied
  or changed directory cannot reuse the old worker. Legacy checkpoints without
  a directory binding require an independent worker directory. Ordinary record
  operations, original pages, attachments and runtime files remain available.
- `linked_evidence` retains career-document associations. These links are navigation,
  not immutable assessment provenance. Renamed documents need updated associations.
- The read-only document catalog still allows Markdown/JSON under its declared
  folders; hidden files, symlinks and raw private sources stay excluded. Documentary
  presence does not establish reviewed mastery or acceptance.
- The document list uses filenames and filesystem metadata without opening every
  body. This keeps macOS cloud placeholders from blocking the whole workspace.
  Detail reads are bounded; if a file is unavailable, download the original in
  Finder and reopen it. Catalog search covers names and paths, not full text.

The original tracker and Obsidian can still read the retained Markdown sources.
Their edits do not replace adopted JSON automatically. Use the explicit import
entry in [JSON operations](json-resume-operations.md#申请记录-json-主存储j07).
Private history has not been migrated by this source implementation. There is no
new delete or automatic restore operation in the UI.

## Existing local server and verification scope

The supported deployment is a trusted, single-user local computer. Do not expose
this stdlib HTTP server through a LAN binding, public proxy or shared host.
Requests enforce exact loopback Host and same-origin checks. Mutations require a
per-process CSRF token and JSON bodies with a size limit. Static routes are fixed;
private file paths are not HTTP paths. Responses disable caching, embedding and
MIME sniffing; the UI renders personal text as text, with no external scripts.
CSV export neutralizes spreadsheet-formula prefixes.

The basic tracking and graph handlers do not themselves call email or models.
The automatic application entry additionally uses configured Gmail/model/browser
services. The server is not an authentication system against other processes running as the same local user,
nor a transaction coordinator for simultaneous external file writers. Revision
checks and backups reduce accidental overwrite risk but cannot eliminate every
filesystem race with unrelated programs. These are implementation facts; they do
not require separate privacy, material or sending approvals in the local product.

Run the focused synthetic suites and the complete checkout suite using:

```sh
uv run --locked python scripts/run_pytest.py tests/test_career_portal_data.py tests/test_career_portal_http.py -q
uv run --locked python scripts/run_pytest.py tests/test_career_portal_graph.py -q
uv run --locked python scripts/run_pytest.py -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```

HTTP integration tests bind an ephemeral loopback port; restrictive sandboxes
must permit that operation. Browser write checks use temporary synthetic notes.
The UI is supported through the checkout launcher. The current minimal wheel
builder does not package the static assets or the wider checkout workflow.

Graph verification on 2026-09-18: the complete offline checkout suite passed
562 tests with one deselected; Ruff checks and JavaScript syntax checks passed.
Browser checks covered shared-skill search, node selection, neighborhood filters,
zoom, document nodes, source viewing, and switching back to the document list.
Desktop and 389-CSS-pixel layouts were inspected; long node labels stay within
the sidebar, and changing selection returns the detail panel to its top.
