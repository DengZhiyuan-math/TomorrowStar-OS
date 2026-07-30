# Validation Runs

Phase 1 provides an offline validation tracer and a separate, explicitly
enabled Codex CLI technical gate. Neither one is a STOA assessment case.

## Claim boundary

The offline commands prove that the charter, immutable bundle, verification,
replay, and provenance boundaries connect correctly. The live command can prove
only that the installed Codex CLI can invoke the configured model and preserve
the required runtime metadata.

Neither result proves that:

- the Grill-Me → Contribution–Skill assessment → Skill graph → JD comparison
  flow is functionally accepted;
- the system improves résumé submissions, interviews, or hiring outcomes;
- any mastery or responsibility conclusion about the user is correct.

Those claims require future human-confirmed STOA cases and the later validation
phases.

## Offline verification

Run the complete default suite:

```bash
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked career-evidence validate-charter validation/charter/v1.json
uv run --locked career-evidence provenance verify validation/provenance/registry.json
```

The default pytest configuration excludes the `live_model` marker.

## Offline create, verify, and replay

Prepare four JSON inputs:

- `raw-response.json` — a retained response envelope containing a `result`.
- `proposal.json` — the original system proposal.
- `confirmed-result.json` — the human-confirmed expected structure.
- `lineage.json` — exactly `fixture`, `artifacts`, `prompt`, `model`,
  `configuration`, `policy`, and `reviewer`.

Then run:

```bash
uv run --locked career-evidence run create \
  --workspace /absolute/path/to/validation-workspace \
  --charter validation/charter/v1.json \
  --run-id offline-case-001 \
  --raw-response /absolute/path/to/raw-response.json \
  --proposal /absolute/path/to/proposal.json \
  --confirmed-result /absolute/path/to/confirmed-result.json \
  --lineage /absolute/path/to/lineage.json

uv run --locked career-evidence run verify \
  --workspace /absolute/path/to/validation-workspace \
  --run-id offline-case-001

uv run --locked career-evidence replay \
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

The committed technical-gate prompt and schema are read-only inputs. Choose a
new run ID for every invocation:

```bash
CAREER_EVIDENCE_ENABLE_LIVE_MODEL=1 \
uv run --locked career-evidence live-run codex \
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
uv run --locked pytest -q -m live_model tests/test_codex_cli.py
```

Live execution may use authenticated model capacity. It is never required by
the offline suite.

## Sensitive data

Only an allowlisted environment is passed to Codex. Known API credential values
are redacted from diagnostic stderr and the prompt is replaced by its hash in
stored argv metadata. Raw model JSONL is intentionally retained unchanged for
reproducibility and may contain supplied user data. Use a private workspace,
minimize prompt content, inspect the bundle before sharing it, and do not commit
`formal-runs/`.
