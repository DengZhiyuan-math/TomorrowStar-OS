# Phase 01 — Existing Pattern Map

**Phase:** Validation Charter, Provenance, and Technical Decision Gate  
**Generated:** 2026-07-30

## Codebase State

No local application package exists yet. The closest analogs are pinned,
read-only upstream submodules and the project-level architecture research.
Phase 1 may establish the packaged Python layout, but it must not copy an
upstream architecture wholesale.

## File-to-Pattern Map

| Planned local file or role | Closest existing analog | Pattern to retain | Required local divergence |
|---|---|---|---|
| `src/career_evidence_graph/validation/models.py` | `references/upstream/hiring-agent/models.py` | Project-owned provider protocol and Pydantic validation boundaries | Use explicit Phase 1 contracts with `extra="forbid"`; no résumé-derived scores or dynamic core models |
| `src/career_evidence_graph/validation/store.py` | `references/upstream/cv-market-learning-planner/scripts/workspace_model.py` and `run_cycle.py` | Small JSON helpers, UTC timestamps, current/history separation | Atomic writes, immutable run directories, UUID identity, schema validation, and content hashes |
| `src/career_evidence_graph/validation/store.py` | `references/upstream/tabiya-compass/backend/app/store/json_application_state_store.py` | One directory per session/run behind a store boundary | No overwrite/delete API for formal runs; distinguish exploratory and formal namespaces |
| `src/career_evidence_graph/validation/replay.py` | `references/upstream/hiring-agent/score.py` | Validate stored structured output before reuse | Never key by filename; key with full input/config fingerprint; retain invalid formal artifacts rather than deleting them |
| `src/career_evidence_graph/validation/provenance.py` | `references/README.md` | `reuse` / `adapt` / `inspired-by` / `reject` classification and pinned revisions | Add machine validation while keeping `references/README.md` human-readable |
| `src/career_evidence_graph/codex_cli.py` | Local `codex exec --help` plus project-owned provider-port decision | Narrow command-runner boundary | Use explicit argv, read-only sandbox, JSONL capture, model/reasoning metadata, and fake runner in default tests |
| `tests/test_*.py` | `references/upstream/tabiya-compass/backend/app/store/test_json_application_state_store.py` | Temporary workspaces and save/load round-trip tests | Add overwrite rejection, byte-stability, traversal/symlink, replay-no-live-call, and corrupt-manifest cases |

## Established Local Conventions

- Python package uses `src/` layout.
- Pydantic v2 models are strict and schema-versioned.
- JSON is UTF-8, stable-key serialized for hashing, and published atomically.
- Formal artifacts are append-only; corrections and reruns create new linked
  records.
- Default test commands are offline and deterministic.
- Every copied or adapted upstream seam is accompanied by provenance and a
  local semantic test in the same implementation change.

## Data Flow

```text
validation/charter/v1.json
  → ValidationCharter.model_validate
  → CLI tracer
  → RunManifest + raw-response JSONL
  → immutable run directory
  → exact replay
  → provenance registry verification
```

## Landmines

- `workspace_model.write_json` writes directly and is not atomic.
- `run_cycle.snapshot_current_analysis` uses timestamps rather than immutable
  run identity and full lineage.
- Hiring Agent caches by PDF basename and deletes invalid cache files.
- Tabiya's JSON store overwrites `state.json` and exposes deletion.
- The generic GSD Walking Skeleton template assumes web UI and a database;
  Phase 1 must use the approved local CLI/JSON validation tracer instead.
- Existing ROADMAP and REQUIREMENTS wording must not reintroduce a claim of
  product effectiveness or pretend a sealed holdout already exists.

## Provenance Entries Required During Execution

| Local subsystem | Upstream | Classification | Exact path requirement |
|---|---|---|---|
| JSON workspace helpers | CV Market Learning Planner | `adapt` unless code is copied | Exact source path required only if code/data is copied; subsystem-level entry otherwise |
| Provider protocol | Hiring Agent | `adapt` / `inspired-by` | Record `models.py`; if signature/code is copied, include exact divergence |
| Run directory store | Tabiya Compass | `inspired-by` | Subsystem-level entry is sufficient unless code is copied |
| Human reuse matrix | Existing local `references/README.md` | local source of truth | Machine registry tests must ensure it is not contradicted |
