# System and personal data boundaries

The [2026-10-24 JSON design](json-resume-design.md) defines the storage and
handoff target. Career facts, application records and resume content use semantic
JSON fields; original source bytes and historical Markdown/TeX remain preserved.
Content revisions own generated TeX/PDF builds, with no separate PDF business
acceptance or reuse decision. Existing stores, correction scope, private custody
and history remain. J03 implements structured experience storage, explicit import
and fact-only default analysis. J04 changes the existing default reading/matching
flow to deliver complete facts by ID, retain input-bound stage results and preserve
each failed attempt during recovery. Canonical completed analysis can reuse
unchanged selected facts across unrelated library or diagnostic metadata changes.
These checkpoints remain private operational state; they do not copy private
records into the system repository. See [J04 verification](../.scratch/json-resume-delivery-2026-10-24/j04-verification.md).
J06 retains human source/diff and protected content versions in the existing private
material store. Unsupported edits remain unmerged and cannot be replaced using stale
JSON. J07 uses JSON-primary application records, retaining legacy Markdown bytes,
IDs and import history; both-side changes remain explicit conflicts. Preview is read-only.
See [J06](../.scratch/json-resume-delivery-2026-10-24/j06-verification.md) and
[J07](../.scratch/json-resume-delivery-2026-10-24/j07-verification.md).
That source-verification stage did not migrate private records. The later
[existing-library curation](career-experiences.md#职业经历库整理标准--2026-10-25)
has published organized career facts and regenerated the directory while preserving
original captures, history and independent information records. It does not add
automatic future organization or change the installed runtime.
Older TeX-centered material descriptions
below document retained compatibility, not a second current source of truth.

Application behavior follows [single-job flow](single-job-flow.md); implementation
work follows the [development plan](development-plan.md). These storage boundaries
do not create per-operation privacy, material or model-use approval steps inside
an activated local workflow. Historical acceptance records retain their scope.
The 2026-10-23 design below is a target contract, not a claim that the current
implementation already follows it. See the
[implementation map](../.scratch/resume-agent-delivery-2026-10-22/map.md).

## Ownership map

| Material | Home | Meaning |
| --- | --- | --- |
| Models, workflow guards, source-workspace API, reusable tests | Public system `src/` and `tests/` | Executable harness contracts |
| Workflow guidance, vocabulary, phase requirements | Public system docs and `.planning/` | Process and acceptance requirements |
| Synthetic fixtures and explicitly reviewed historical documentary fixture | Public `tests/fixtures/` and `validation/` | Contract verification; not a private career-data mirror |
| Raw source bodies and exact retained captures | Private `.career-evidence/raw/`, ignored by Git | Candidate source provenance; never mastery by itself |
| Source registry and immutable source-universe successors | Private `.career-evidence/` | Source identity and lineage |
| Inventory proposals, review successors, coverage and acceptance | Private `.career-evidence/inventory/` | Candidate or accepted inventory, according to the exact recorded review state |
| Personal source notes, reports, Contribution records and Skill graph | Private `sources/`, `reports/`, `contributions/`, `skill-graph/` | Personal artifacts; authority must be inspected in each record, not inferred from folder names |
| Source-specific inventory operators and their tests | Currently private `scripts/` and `tests/` | Local adapters; not a second canonical system workflow |
| Application JSON records, retained Markdown originals and exact-byte history | Existing private application folder | Current application status, full JD, actions and documentary links; stable IDs and explicit legacy imports |
| Optional Web UI folder configuration | User Application Support directory, outside the checkout | Selected paths only; no assessment or source-custody authority |
| Selected public website presentation | Private `reports/public-site/site-content.json` | Editorial selection; not accepted inventory or mastery |
| Exported public presentation snapshot | Existing personal website checkout | Explicitly selected presentation fields only; no private records or locators. See [website integration](public-website.md). |
| Codex handoff tasks, retained PDF copies, claim credentials and readback/user assertions | Explicit separate `handoff-root` outside the checkout and application-note directory | Alternate handoff mode; no browser or provider execution in this adapter. See [Codex handoff](codex-handoff.md). |
| Basic information library | Selected existing private information/answer library and unified directory entry point | Personal facts, reusable answers and preferences with their scope; exposes the career directory, without maintaining a second copy of career content. Existing storage names need not change merely for this target terminology. |
| Career library | Selected private career workspace | One main factual body per experience, with subproject sections, related materials and history; automatically owns and updates the lightweight experience directory. Direct corrections are usable without research-snapshot acceptance. |
| Application worker PDF copies, run checkpoints and browser profile | Explicit worker directory outside the system checkout | Private operational state. Synthetic tests use separate temporary data; they do not populate the user's information or career libraries. |

No private path, URL, personal source-derived label, count, hash or report should
be added to new public documentation. Existing historical artifacts stay in place;
this organization pass does not sanitize or certify past Git history.

New system acceptance reports retain Boolean verification conclusions only,
including nested groups. Keep measurements, logs, fingerprints and private
locators in the separate private evidence workspace. When correcting a report
under explicit authorization, preserve its original bytes there and verify the
copy before replacing the system report. Keep the correction's lineage private;
do not add a private evidence path or fingerprint to the public replacement.
Field names also follow a reviewed allowlist at each report group; a naming
pattern alone is insufficient. Do not encode measurements or fingerprints in
keys. The artifact-query report's contract is checked independently in
`tests/test_system_verification_report.py`; new fields require explicit review.

## Selecting a workspace

Supply a private workspace explicitly for each source operation. Use an existing
Git repository outside the system checkout's ancestor/descendant tree, with a
different Git common directory. A second worktree of the system repository shares
its object database and is not a private data repository.

The private repository's own `.gitignore` must designate `.career-evidence/raw/`.
Effective Git ignore rules must still exclude the target raw file, and no raw
vault files may already be tracked in the current index. These are local boundary
checks; they do not attest remote visibility, history, backups or encryption.

Source-custody operations do not store a default private path. The separately
requested [local Web UI](career-portal.md) may remember explicitly selected folders
in the user's Application Support directory. Neither surface adds a personal-data
submodule or automatically inspects personal records during tests. A Git repository being
separate is not proof that its remote is private. Remote publication remains a
separate action. Activating the application workflow includes its normal model
processing of the applicable saved information; it does not require a new privacy
approval for each fact, résumé or job. This document does not initiate that work.

## Record handling

Keep raw bytes append-only. Failed publication can leave an orphan; preserve it
for explicit diagnosis. Do not delete old captures, regenerate a reviewed packet
in place or rewrite an accepted revision to make a new result appear historical.
Use a new destination and explicit predecessor lineage.

This immutable-capture rule protects historical source and research records. It
does not require the user to reseal an inventory to correct a current fact. Save
the correction and its source in the career library, retain the prior record,
and synchronize the affected current experience body and directory. This does not
automatically invalidate completed application materials or analyses. The basic
information library holds reusable
form answers with their applicable scope; a scoped answer does not silently
overwrite a conflicting career fact. Ask about an actual conflict when it matters
to the current job. Missing research review is not itself a factual conflict.

Job matching, résumé selection and generation trust the saved career and information
libraries. User statements are usable facts; a self-reported language level does not
need an examination record to count as that level. Preserve the distinction between
a stated level and an examination credential when a form asks for the latter.
Preserve applicable scope, dates, numbers, planned/completed status and team roles.
Incomplete project audits or Skill assessments do not lower or exclude library
content in the application workflow. That workflow does not repeat the library's
credibility review or create an assessment result.

## Application-facing library organization

The experience is the default retrieval unit. Its main body records identity,
dates and status, context and goals, actual work, methods and technologies,
collaboration, results and associated materials. Large experiences use subproject
or workstream sections. A repository, paper or subproject may have a linked
material entry without becoming a separate career experience by force.

The career library generates each directory entry from its content. The target default
selection input includes stable identity, grounded skill and technology retrieval
terms, a short account of work and problem domains, and detail locators with their
revision. Names support display; institutions
and dates remain in full experiences and are read when an explicit condition needs them,
rather than being mandatory inputs for every relevance selection. Responsibility,
assistance and completion status likewise remain in full experiences; they are not
mandatory directory fields or admission conditions for initial discovery. After selection,
full content supplies these boundaries for matching judgments and writing. Skill terms
do not establish independent personal responsibility or mastery. Work summaries also support
semantic discovery without an exact skill-label match. See the
[directory selection contract](career-experiences.md#目录的筛选内容); adapting the existing
stored directory and default delivery remains implementation work.
Summary and retrieval terms are extracted
separately from the underlying content so that shortening a summary does not erase
technical or domain terms. The basic information library exposes this directory;
it does not independently edit the same career facts. Internal content versions
and indexing status support maintenance, not capability scores or qualifications.

Initially build directory coverage for all current experiences and linked materials.
Thereafter additions and edits update the affected entries and relationships.
Indexing failure preserves the saved body and a discoverable basic entry rather
than hiding the experience. This maintenance checks extraction, omissions and
relationships; it does not reassess the truth of user statements or require proof.
Explicit user corrections supersede current facts with history retained. Ask only
about an actual unresolved conflict that matters, not missing certificates or an
unfinished project assessment.

Preserve unique facts and merge repeated expressions. A TeX source and its matching
PDF represent one content item, with a source/export relation. Repeated formats,
old exports, logs, caches, dependencies and generated files do not each become daily
retrieval candidates. Supplementary papers, code and reports remain available for
needed detail. Keep their distinct facts and time/status history; do not delete
material merely because it is not relevant to one JD. Generated tailored résumés
are outputs, not new career-fact authorities. A deliberate new global fact is saved
to its owning library explicitly; application-only edits remain application scoped.

Retrieval reads the complete lightweight directory and then relevant bodies and
linked details. It does not rescore credibility. Matching evaluates the complete
background rather than the résumé's selected subset. A direct fact, deterministic
derivation and semantic inference have distinct operational meanings, not different
credibility ranks. A matching inference is stored with that application and may be
used for writing, but is not silently promoted into a permanent personal fact.
An invalid citation, incomplete read or missing file is an execution problem, not
negative capability evidence.

## Completed material and manual edits

Each application step consumes the fixed result delivered by its predecessor.
New library data, JD revisions, account refreshes, model/prompt settings, App updates
and configuration changes do not automatically revoke a completed résumé, review
or PDF. An explicit rerun adopts new inputs and produces a new version. Research
source lineage may retain strict revision rules without imposing those rules as
daily application approval or global material invalidation.

Prism-local owns automatic compilation and preview. The application keeps the
relation between a PDF and its TeX plus actual compile dependencies; it does not
add another automatic compiler or content/PDF review. An unexported edit is different
from an invalid old PDF. Retain prior successful outputs and prevent old asynchronous
results from overwriting new edits. A new PDF version does not establish that a
website's existing attachment has been replaced.

Entering manual Prism editing suspends system writes to that TeX. Explicitly
finishing manual editing invokes fast proofreading only: spelling, grammar,
capitalization, punctuation and duplicate words. It cannot challenge facts,
rewrite meaning, polish prose, reorder content or change layout/TeX commands.
Keep ambiguous text and show a suggestion. This is not a repeat of AI content
review. Preserve human edits and historical outputs.

## Form values and external state

Saved answers retain applicability: visa answers and privacy consent must not
silently become global permissions. Before upload preserve current nonempty fields
and attachment state. Treat unknown-origin values as protected, like known manual
values. Website parsing may fill empty fields; nonempty differences from current
applicable information are presented together for the user to select. Do not
silently overwrite either the form or a library, or restore an old baseline that
may itself be out of date. Equivalent formatting is not a substantive conflict.

Record action intent and observed before/after state in private operational records.
Upload completion, parser completion and field stability are separate observations.
Use explicit parser signals when available; otherwise wait for stable observations
and keep monitoring. Late autofill pauses writing and triggers a new merge. Unknown
outcomes stop writes for the current job until checked, without replaying the action
or discarding history. A same-name attachment alone is not proof of the same PDF
version. Final Submit remains manual, including equivalent keyboard or network actions.

Complete base captures and derived mappings before publishing a source-universe
successor. Once successors exist, `capture_source` and `record_derived_mapping`
return `registry-frozen` before writing: changing the base registry would break
their parent hashes. Append a later captured Source with
`record_captured_source_successor`, using the exact parent registry hash. This API
verifies the parent captures and retains the caller-supplied Source type. The
self-report helper delegates to it. It preserves the original cutoff and records
the new capture time separately; it does not accept or rebind an inventory.
Do not bypass the freeze guard by editing the base registry or removing revisions.
These are existing source-custody API constraints, not an application approval
protocol. Simplifying their implementation belongs to the development plan;
normal application work must not require an operator to execute this research API.

Within the research assessment process, source presence, reports, candidate wording
and code ownership do not establish audited capability. An accepted inventory
establishes Experience identity and coverage; reviewed Contribution-Skill assessments
establish assessed capability. These research distinctions do not gate reuse of
saved facts in ordinary applications.

Generic source APIs return content-free status/errors. The detached source
snapshot API and audit inspection are intentionally data-bearing: their caller
must keep payloads and output in the selected private context. Do not paste them
into public logs or review reports.

## Keeping operators and data understandable

The public workflow guide owns system-wide rules. The private README locates
personal records and gives local adapter commands. Private execution notes should
link to that guide and describe only private handoff details, avoiding a competing
definition of assessment authority.

Do not move source-specific inventory scripts into the public package by copying
them wholesale. First separate personal seeds and extraction assumptions, retain
input/output compatibility, and test the reusable core on synthetic data. That
extraction is future implementation work, not required to navigate today's system.
