---
phase: 01
slug: validation-charter-provenance-and-technical-decision-gate
status: complete
researched: 2026-07-30
requirements:
  - VAL-01
  - VAL-02
  - OSS-01
---

# Phase 1 Research — Validation Charter, Provenance, and Technical Decision Gate

## Research Question

What must be known to plan Phase 1 so that it establishes a falsifiable
functional-validation contract, reproducible formal runs, and enforceable
open-source provenance without prematurely building the later audit, scoring,
or résumé product?

## Executive Summary

Phase 1 should build one narrow local vertical slice:

```text
versioned functional charter
  → validate a synthetic formal-run request
  → store an immutable run bundle
  → replay the recorded model response exactly
  → verify linked rerun and provenance metadata
```

The phase should not create STOA domain fixtures, conduct Grill-Me, score
Skills, compare real JDs, or claim employment outcomes. Those are later
phases. Its job is to make later results auditable before those results exist.

The implementation should be a small packaged Python 3.13 CLI/library using
Pydantic v2 contracts and JSON/JSONL storage. Use `argparse`, `pathlib`,
`hashlib`, `uuid`, `tempfile`, and atomic `os.replace` from the standard
library. Do not add a database, web UI, or generic agent framework.

The highest-risk planning issue is semantic, not technical:
`.planning/REQUIREMENTS.md` and `.planning/ROADMAP.md` still mention sealed
holdouts and `supported` / `partially supported` / `rejected` conclusions,
while the approved Phase 1 context limits the project to functional operation
and explicitly says no product-effectiveness verdict. The plan must encode that
reconciliation in the charter:

- product-effectiveness verdicts are out of scope and prohibited;
- functional checks produce criterion-level pass/fail evidence, not a claim
  that the product improves job-search outcomes;
- holdouts are governed by an eligibility rule and remain unavailable until
  enough independent cases exist;
- real résumé-submission outcomes are deferred.

## Recommended Architecture

### Package and artifact boundaries

```text
src/career_evidence_graph/
  cli.py
  validation/
    models.py
    hashing.py
    store.py
    replay.py
    provenance.py

validation/
  charter/v1.json
  provenance/registry.json

tests/
  test_charter.py
  test_run_store.py
  test_replay.py
  test_provenance.py
  test_cli_tracer.py
  fixtures/validation_contract/
```

No persisted `validation/runs/` directory should be committed as product data.
Tests create run workspaces under pytest temporary directories. A later CLI
user may choose a local workspace path.

### Core contracts

Use strict Pydantic models with `ConfigDict(extra="forbid")`.

`ValidationCharter` should include:

- `schema_version`
- `charter_version`
- `validation_target = "functional_operation"`
- `prohibited_claims`, including any claim about improving application,
  interview, or hiring outcomes
- `required_paths`: user-completed STOA flow, automated replay, critical
  negative cases
- `critical_failure_classes`: fabrication, attribution error, broken lineage,
  material instability, unreproducible formal run
- `expected_result_policy`: exact structural fields plus approved semantic
  sets/ranges
- `case_policy`: coverage-based, no arbitrary count
- `holdout_policy`: unavailable until explicitly eligible; no fake sealed set
- `formal_run_policy`
- `provenance_policy`
- `model_gate`

`RunManifest` should include:

- immutable `run_id`
- `run_kind`: `exploratory` or `formal`
- `created_at`
- optional `parent_run_id`
- hashes and relative references for fixture, source artifacts, prompt,
  configuration, policy, and reviewer inputs
- Codex CLI version
- requested model, effective model/snapshot when observable, and reasoning
  effort
- raw-response path and SHA-256
- proposal, correction, and correction-reason artifact references
- status and declared limitations, including model drift when no immutable
  snapshot is available

`ProvenanceRecord` needs two validation profiles:

1. `reuse` / copied code or data: repository, pinned commit, source path,
   license, attribution, local target, and divergence are required.
2. `adapt` / `inspired-by`: one subsystem-level entry is sufficient; repository,
   pinned commit, classification, local subsystem, and rationale are required,
   but line-level annotations are not.

### Identity and hashing

Formal-run identity must not depend on filenames. Build a canonical input
fingerprint from stable JSON serialization (`sort_keys=True`, compact
separators, UTF-8) over:

- fixture/artifact hashes;
- prompt content/version;
- model and reasoning configuration;
- policy and schema versions;
- reviewer-input versions.

Use a UUID for run identity and store the fingerprint separately. A rerun gets
a new UUID and links to its parent. This preserves history even when inputs are
identical.

### Storage rules

Each formal run occupies a new directory:

```text
<workspace>/runs/<run_id>/
  manifest.json
  raw-response.jsonl
  proposal.json
  review.json
  result.json
  diff.json                 # reruns only
```

Required invariants:

- formal-run creation fails closed if `<run_id>` already exists;
- all JSON files validate before publication;
- write to a same-directory temporary file, `fsync`, then `os.replace`;
- once a formal bundle is published, application code has no update or delete
  operation for it;
- reruns write a new bundle and an explicit diff;
- exploratory runs use a separate namespace and cleanup policy;
- exact replay reads the recorded raw response and performs no live model call;
- live re-execution is a different command and reports variance.

## Upstream Findings

### CV Market Learning Planner

Relevant upstream:

- `references/upstream/cv-market-learning-planner/scripts/workspace_model.py`
- `references/upstream/cv-market-learning-planner/scripts/run_cycle.py`
- pinned commit `ea507847c7a42a1a54becc853fadd15506479b38`, MIT

Useful adaptations:

- explicit current/history separation;
- small deterministic JSON/time helpers;
- snapshot-before-regeneration workflow.

Required local divergence:

- upstream `write_json` writes directly and is not atomic;
- timestamp-based history filenames may collide;
- file snapshots do not capture prompt/model/policy/reviewer lineage;
- Phase 1 needs validated immutable run bundles and content hashes.

### Hiring Agent

Relevant upstream:

- `references/upstream/hiring-agent/models.py`
- `references/upstream/hiring-agent/score.py`
- pinned commit `70fd3ea9aa74d8f76519ec643a99f9871003e70d`, MIT

Useful adaptations:

- a project-owned `LLMProvider` protocol;
- Pydantic validation when loading cached structured output;
- stage-specific intermediate artifacts.

Required local divergence:

- upstream cache filenames are derived from the input PDF basename only;
- invalid cache entries are deleted, which is inappropriate for formal audit
  history;
- cache keys omit prompt, model, settings, policy, and input-content hashes;
- GitHub and résumé content must not become evidence of mastery.

### Tabiya Compass

Relevant upstream:

- `references/upstream/tabiya-compass/backend/app/store/json_application_state_store.py`
- pinned commit `8470bea7f68d0990898f441a12bbb6a261a0ef34`, MIT

Useful adaptation:

- explicit state-store boundary and one directory per session.

Required local divergence:

- upstream overwrites `state.json` and exposes delete;
- formal validation runs must be immutable and separately versioned;
- Tabiya's application state is much larger than Phase 1 requires.

## Codex CLI Technical Gate

Local inspection found:

- Codex CLI version: `0.146.0`
- `codex exec` supports `--model`, `--config key=value`, `--output-schema`,
  `--json`, `--output-last-message`, `--cd`, and explicit sandbox selection.

Recommended adapter boundary:

```text
CodexRunner.run(request) -> RecordedModelResponse
```

The subprocess argument vector should specify:

- `codex exec`
- `--model gpt-5.6-luna`
- `--config model_reasoning_effort="medium"`
- `--json`
- `--output-schema <path>` when the phase has a concrete response schema
- `--cd <workspace>`

Do not invoke a real model in the deterministic default test suite. Unit and
tracer tests use a fake command runner or recorded JSONL. A separately marked,
opt-in live smoke test verifies CLI availability and captures the command,
CLI version, stdout JSONL, stderr, exit code, and requested/effective model
metadata.

OpenAI's current model documentation identifies `gpt-5.6-luna` as the
cost-sensitive GPT-5.6 tier and supports reasoning efforts including `medium`.
The model page describes snapshot pinning, but an immutable snapshot identifier
must be discovered and recorded at formal-run time rather than invented in
source code. If no immutable snapshot is exposed, retain the raw response and
record the drift limitation.

Sources:

- `https://developers.openai.com/api/docs/models/gpt-5.6-luna`
- `https://developers.openai.com/api/docs/guides/latest-model`
- local `codex exec --help` from Codex CLI `0.146.0`

## Tracer-First and MVP Mode

The ROADMAP marks Phase 1 as `mvp`, which activates GSD's generic Walking
Skeleton guidance. That template assumes a web application, database, UI, and
deployment. Applying it literally would violate the project constraints and
the approved context.

Use the tracer-first principle, but adapt the skeleton to this local CLI:

```text
charter fixture
  → CLI validation command
  → immutable JSON run bundle
  → exact recorded-response replay
  → provenance verification
```

The plan may produce `01-SKELETON.md` to document this validation skeleton, but
it must explicitly mark web routing, database, auth, and UI as not applicable
to Phase 1. The local full-stack run command is the documented CLI tracer and
pytest suite.

## Validation Architecture

### Test layers

| Layer | Purpose | Example assertions |
|-------|---------|--------------------|
| Contract unit tests | Reject missing/extra/invalid schema fields | formal manifest without raw-response hash fails validation |
| Storage invariant tests | Prove immutability and lineage | duplicate run ID fails; parent run remains byte-identical |
| Replay tests | Separate exact replay from live re-execution | replay does not invoke runner; recorded JSONL hash matches |
| Provenance tests | Enforce exact vs lightweight profiles | copied-data entry without source path fails |
| Charter tests | Lock approved semantics | product-effectiveness claims prohibited; holdout unavailable |
| CLI tracer | Exercise one vertical path | command exits 0 and creates a valid immutable bundle |
| Opt-in live smoke | Verify Codex CLI contract | explicitly marked test records CLI/model/config/raw JSONL |

### Required negative cases

- product-effectiveness claim appears in the charter;
- critical failure class is omitted;
- a sealed holdout is declared despite ineligible case inventory;
- formal run attempts to overwrite an existing ID;
- rerun omits `parent_run_id` or change summary;
- fixture, prompt, model, configuration, policy, or reviewer version is absent;
- correction overwrites the original proposal;
- exact replay attempts a live subprocess call;
- copied code/data provenance omits source path, license, commit, or divergence;
- an invalid/corrupt stored manifest is treated as valid;
- model alias is used without snapshot metadata or a drift limitation.

### Commands

Expected execution commands after scaffolding:

```text
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run career-evidence validate-charter validation/charter/v1.json
uv run career-evidence trace-validation --workspace <tmp-workspace>
```

Default tests must be offline and deterministic. The live Codex smoke test is
opt-in and credential-gated.

## Planning Recommendations

1. Lead with one production-quality tracer plan that scaffolds the package and
   proves charter → immutable run → replay → provenance through the CLI.
2. Add a second plan for exhaustive negative/invariant coverage and formal
   Codex CLI metadata capture.
3. Keep Phase 1 to two plans unless source-audit coverage proves a third is
   necessary.
4. Every plan must reference `VAL-01`, `VAL-02`, and/or `OSS-01` explicitly and
   cite the relevant D-IDs from CONTEXT.md in `must_haves`.
5. Include a security threat model even though there is no network service:
   path traversal, symlink escape, command injection, secret capture, artifact
   tampering, and untrusted model output are the relevant threats.
6. Do not put actual STOA content, real JD data, or user-sensitive evidence in
   Phase 1 fixtures.
7. Treat `references/README.md` as the human-readable reuse matrix and add a
   machine-validated registry only if it remains synchronized by tests.

## Open Questions Resolved for Planning

- **Holdouts:** unavailable for now; implement an eligibility rule, not a fake
  sealed set.
- **Verdicts:** criterion-level functional pass/fail only; prohibit product
  effectiveness claims.
- **Model:** Codex CLI + `gpt-5.6-luna` + `medium`; snapshots are runtime
  metadata, never a guessed constant.
- **Database/UI:** not applicable; preserve local CLI/JSON architecture.
- **Live network calls:** opt-in smoke test only, never part of the default
  verification suite.

## RESEARCH COMPLETE

