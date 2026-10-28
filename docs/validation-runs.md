# Validation Runs

This guide covers the formal-run tracer and the separate, explicitly enabled
Codex CLI technical gate. For the full audit, assessment, and private-source
workflow, start with [workflows](workflows.md) and [architecture](../ARCHITECTURE.md).

## Generic interview adapter and frozen synthetic trials — 2026-10-08

The [delivery record](interview-delivery-2026-10-08.md) documents current state
synchronization, the inventory-bound three-layer adapter and private linked-seal
successors. The complete offline checkout suite passed **627 tests**, with one
opt-in test deselected (133.10 s). The last failure-evidence repair passed 47
focused regressions. The private synthetic suite passed 30 tests.

The opt-in model experiment is separate: three nine-case batches under the
same final frozen input/configuration matched 27/27 protocol reference labels,
with zero critical inflation and zero unstable cases. Three generated plan
candidates passed structure; semantic review accepted one and required two
explicit successors. All three reviewed plans passed. Failed raw outputs and
v1/v2 corpus lineage are retained. These are synthetic reference labels and
assistant semantic review; real personal anchor/confidence calibration remains
pending. No personal data was sent to the model, no new inventory was accepted,
and no personal score was created. Ruff, format and diff checks passed.

## Claim boundary

### Question and scoring pipeline — 2026-10-07

The [first pipeline](question-scoring-pipeline.md) reuses audit and assessment
records, adds predeclared difficulty-specific criteria, and records context
requests separately from capability answers. Its eight new offline regressions
cover context routing, legacy snapshots, criterion validation, distinct stage
schemas and the checkout CLI. A scripted audit reaches a specific-Skill proposal
without treating the recall request as a capability answer or a numeric score.

The checkout offline suite passed: **586 passed, 1 opt-in test deselected**.
Ruff check, format check and diff whitespace checks passed. No live model was
called and no private career records were scored. Mock transport and scripted
decisions establish plumbing behavior only; question quality, semantic grading
and anchor calibration remain separate pending gates.

### Three-layer question update — 2026-10-07

The later user clarification requires project overview, project technical depth
and transfer to similar problems as separate layers. The preparation model now
keeps all three, rejects mixed layers or missing changed conditions, and binds
each depth/transfer plan to the exact selected Contribution facts. Questions in
the existing audit engine retain layer and transfer-condition metadata while
difficulty changes independently.

The expanded pipeline tests passed (14 cases), the focused audit/assessment
regressions passed (64 cases), and the full offline suite passed:
**592 passed, 1 opt-in test deselected**. Ruff and formatting checks passed.
The generated project-interview schema matches its typed model. This supersedes
the earlier 586-test result for the updated checkout; it does not claim a live
model evaluation or complete private interview sequencing.

### System protocol integration — 2026-10-07

The three-layer protocol now appears in PROJECT, AGENTS, CONTEXT and the existing
GRF-01/GRF-02/GRF-06 requirements and Phase 9/10 success criteria. Requirement IDs
and phase mappings remain unchanged. README and workflow navigation link the
same detailed pipeline.

Generation and read-only `audit inspect-plan` share one context-binding validator.
Nine new CLI cases cover valid preparation, incorrect Experience/Contribution
bindings, foreign fact references, missing context, mismatched overview locators,
malformed input, missing depth criteria and whitespace-only overview criteria.
The cases assert unchanged input files and absence of sensitive context in output.
They do not verify raw-source custody or semantic question quality.

The final focused selection passed **51 tests**, including all **23 pipeline
cases**. The complete offline suite passed **601 tests, 1 opt-in test deselected**
in 150.87 seconds after the final criterion-validation change. Ruff check, format
check (105 files) and diff whitespace checks passed. Schema/model equivalence,
the 32 unique requirements and unchanged mappings, and linked document paths
were checked. No live model, private capability assessment or phase acceptance
was run.

### Web interview preparation entry — 2026-10-08

The portal now exposes project interview preparation from navigation, the overview
card and evidence details. It supports source search, the three ordered layers,
the current system protocol, and local plan inspection with layer/difficulty
previews. The Web and CLI entrypoints share the audit inspection API.

The focused portal/CLI/pipeline selection passed **86 tests**. The complete
offline suite passed **616 tests, 1 opt-in test deselected** in 179.43 seconds.
Fifteen added HTTP cases cover preparation results, mismatched bindings and
invalid structure, source-body containment, unchanged private files, current
protocol reads, and the existing same-origin/CSRF and body limits on the new POST.

Browser checks exercised source search, document detail/return, valid synthetic
plan inspection, transfer conditions, difficulty switching, rejection of a wrong
Experience ID, immediate preview invalidation, clearing, and protocol retrieval.
Measured CSS widths of 1910, 1280, 580 and 388 showed no horizontal page overflow.
Temporary viewport settings were reset and synthetic inputs were cleared. These
checks establish the preparation UI, not semantic grading or personal capability.

The offline commands prove that the charter, immutable bundle, verification,
replay, and provenance boundaries connect correctly. The live command can prove
only that the installed Codex CLI can invoke the configured model and preserve
the required runtime metadata.

Neither result proves that:

- the Grill-Me → Contribution–Skill assessment → Skill graph → JD comparison
  flow is functionally accepted;
- the system improves résumé submissions, interviews, or hiring outcomes;
- any mastery or responsibility conclusion about the user is correct.

The repository already contains a documentary, human-reviewed STOA fixture and
offline audit/assessment harnesses. Their existence does not establish a reviewed
full-career graph or real JD usefulness. Current acceptance and pending work are
recorded in the [roadmap](../.planning/ROADMAP.md).

## Offline verification

Run from the repository root. The launchers explicitly import this checkout's
`src` package, so an older installed package cannot supply the implementation:

```bash
uv run --locked python scripts/run_pytest.py -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python scripts/run_career_evidence.py validate-charter validation/charter/v1.json
uv run --locked python scripts/run_career_evidence.py provenance verify validation/provenance/registry.json
```

The default pytest configuration excludes both `live` and `live_model` tests.
An explicit marker override does not grant permission to send personal data to
a provider. Live execution also requires its environment opt-in.

## Preparation candidate freeze

Freeze a new public source handoff before the final preparation checks:

```sh
uv run --locked python scripts/freeze_preparation_candidate.py create \
  --output /absolute/path/to/new-candidate
uv run --locked python scripts/freeze_preparation_candidate.py verify \
  --candidate /absolute/path/to/new-candidate --source-root "$PWD"
```

Creation reads the working tree, including untracked source. Its explicit public
allowlist includes the preparation engine and static UI, launch/build sources,
locked configuration, core guidance, upstream license notices and selected
synthetic test files. It excludes private workspaces, runtime state, Git/cache,
scratch, builds, outputs and historical application-pilot records. Existing
destinations and unsafe filesystem entries are refused. The candidate ID binds
the manifest's policy and exact payload; verification checks its inventory and
bytes without executing the payload or writing a result into the candidate.
Pass `--source-root` to also compare the current checkout with that payload.

Run the complete default offline suite in the checkout that supplied the
candidate. Keep the default marker exclusions and verify candidate/source equality
before and after the checks. The handoff payload is not a standalone clone of
every historical full-suite fixture. Preserve each command, selection, JUnit/log
hash, runtime/configuration identity and candidate ID in a separate acceptance
report. Keep the original candidate manifest unchanged when appending evidence.

Composed preparation checks use synthetic Gmail pages, job sources, applicant
facts and model responses. Every selected row must finish or keep an accurate
pending, deferred, qualification, stale or unknown disposition. A confirmed PDF
still pauses at `waiting_application_record`; it cannot authorize another job or
stand in for application submission. Known failures require explicit retry;
unknown writes require the original read-only receipt reconciliation.

The applicable real-renderer check exports the exact saved synthetic draft with
the current A4 template, then checks complete extracted text, page sizes and
rendered pages. Copied PDF workflow fixtures prove transport only. Browser and
actual-renderer checks use separate explicit opt-ins; they do not authorize real
Gmail, model, job-site, ATS, upload or Submit activity. A source candidate and
passing checks do not replace installed-window, real-sample or human acceptance.

## Offline create, verify, and replay

Prepare four JSON inputs:

- `raw-response.json` — a retained response envelope containing a `result`.
- `proposal.json` — the original system proposal.
- `confirmed-result.json` — the human-confirmed expected structure.
- `lineage.json` — exactly `fixture`, `artifacts`, `prompt`, `model`,
  `configuration`, `policy`, and `reviewer`.

Then run:

```bash
uv run --locked python scripts/run_career_evidence.py run create \
  --workspace /absolute/path/to/validation-workspace \
  --charter validation/charter/v1.json \
  --run-id offline-case-001 \
  --raw-response /absolute/path/to/raw-response.json \
  --proposal /absolute/path/to/proposal.json \
  --confirmed-result /absolute/path/to/confirmed-result.json \
  --lineage /absolute/path/to/lineage.json

uv run --locked python scripts/run_career_evidence.py run verify \
  --workspace /absolute/path/to/validation-workspace \
  --run-id offline-case-001

uv run --locked python scripts/run_career_evidence.py replay \
  --workspace /absolute/path/to/validation-workspace \
  --run-id offline-case-001
```

Exact replay reads only the stored raw response. It never resumes a Codex
session or invokes a model.

## Formal history and corrections

A formal run directory is immutable. Reusing an existing run ID fails. A rerun
creates a new directory with `parent_run_id`, a non-empty change reason, and an
explicit diff. Correction records retain the complete original proposal, its
hash, the reviewer, the correction, the reason, and the timestamp; they do not
replace the original.

There is currently no persisted exploratory-run API. Debug output outside the
formal store is not acceptance evidence and must not be relabeled as formal.

## Opt-in Codex CLI technical gate

The committed technical-gate prompt and schema are read-only, synthetic inputs.
Choose a new run ID for every invocation. This is an optional model transport
check, separate from offline regression and milestone acceptance:

```bash
CAREER_EVIDENCE_ENABLE_LIVE_MODEL=1 \
uv run --locked python scripts/run_career_evidence.py live-run codex \
  --workspace "$PWD" \
  --charter validation/charter/v1.json \
  --run-id technical-gate-manual-001 \
  --prompt-file validation/prompts/technical-gate.txt \
  --output-schema validation/schemas/technical-gate-result.schema.json
```

This invokes a shell-free argument vector containing:

```text
codex exec
  --model gpt-5.6-luna
  --config model_reasoning_effort="medium"
  --json
  --output-schema <schema>
  --cd <workspace>
  --sandbox read-only
  <prompt>
```

If an immutable model snapshot is available, add
`--model-snapshot <snapshot-id>`. Otherwise the bundle retains the complete raw
JSONL and an explicit alias-drift limitation. A successful bundle contains the
Codex CLI version, sanitized invocation, exit code, raw stdout JSONL, redacted
stderr, requested configuration, input hashes, model identity, and either the
snapshot or drift record.

The direct pytest smoke is also opt-in:

```bash
CAREER_EVIDENCE_ENABLE_LIVE_MODEL=1 \
uv run --locked python scripts/run_pytest.py -q -m live_model tests/test_codex_cli.py
```

Live execution may use authenticated model capacity. It is never required by
the offline suite.

## Sensitive data

Only an allowlisted environment is passed to Codex. Known API credential values
are redacted from diagnostic stderr and the prompt is replaced by its hash in
stored argv metadata. Raw model JSONL is intentionally retained unchanged for
reproducibility. This technical gate uses synthetic material only; private
career/JD material has no external-transfer authorization in the current
milestone. Inspect any bundle before sharing it, and do not commit generated
`formal-runs/`. See [data boundaries](data-boundaries.md) for the separate private
workspace and raw-vault responsibilities.

## Captured Source successors — 2026-10-06

`record_captured_source_successor` appends a captured Source to an exact parent
revision. It retains the supplied Source type, verifies parent captures, and
preserves base and parent registry bytes. The self-report helper reuses this API.
Invalid metadata fails before writing raw bytes.

The focused custody/security run passed 38 tests. The full offline selection
passed 530 tests in the sandbox; 36 HTTP setup cases could not bind a loopback
port there. Repeating those cases outside the sandbox passed all 36: 566 distinct
selected tests passed, with one opt-in test deselected. Ruff checks, formatting
checks and `git diff --check` passed. These results verify implementation
contracts; they do not establish independent phase verification or personal
inventory acceptance.

## Independent custody repair verification — 2026-10-07

The active declaration contract permits an unavailable Source to omit its reason.
If supplied, the reason must be a nonempty string. An available Source must omit
the field. The implementation and synthetic regressions now enforce this rule.

The focused custody/security selection passed 50 tests. The complete offline
suite passed 578 tests, with one opt-in test deselected. The full run used a local
environment that permits loopback binding. Ruff checks and formatting passed for
all 103 files. The private operator's synthetic suite passed 21 tests, including
rejection of unauthorized acceptance in ordinary review nodes and ancestors.

The [independent Phase 7 report](../.planning/phases/07-career-source-custody-and-private-workspace/07-VERIFICATION-2026-10-07.md)
binds the reviewed public inputs and passes the active single-user MVP boundary.
Inventory acceptance and capability assessment remain separate gates.
