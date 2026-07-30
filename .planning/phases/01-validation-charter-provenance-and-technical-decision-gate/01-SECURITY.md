---
phase: 01
slug: validation-charter-provenance-and-technical-decision-gate
status: verified
threats_open: 0
asvs_level: 1
block_on: high
register_authored_at_plan_time: true
created: 2026-07-30
---

# Phase 1 — Security

> Phase 1 threat mitigations were verified against the plan-time register and
> deterministic tests. No open threat at or above the high-severity gate remains.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Validated request → Codex subprocess | A local request becomes a fixed non-interactive `codex exec` invocation | Prompt, model profile, schema path, workspace path |
| Process environment/output → formal store | Selected environment values and untrusted JSONL cross into validated immutable artifacts | Credentials in process environment, model output, diagnostics |
| Model alias → acceptance evidence | A mutable model alias must not be represented as immutable model identity | Alias, optional configured snapshot, drift limitation, raw JSONL |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-01-04 | Tampering | Codex subprocess launcher | high | mitigate | Fixed argv, `shell=False`, literal prompt argument, locked executable and flags; verified by `test_argv_locks_luna_medium_json_schema_workspace_and_read_only`, `test_argv_excludes_every_out_of_scope_or_privilege_expanding_surface`, and `test_runner_uses_shell_false_redacts_secrets_and_retains_raw_jsonl` | closed |
| T-01-05 | Information disclosure | Process environment and stored invocation metadata | high | mitigate | Allowlisted child environment, no serialized credential values, stderr credential redaction, prompt represented by hash in stored argv; verified by `test_runner_uses_shell_false_redacts_secrets_and_retains_raw_jsonl` | closed |
| T-01-06 | Elevation of privilege | Codex workspace and filesystem sandbox | high | mitigate | Forced `--sandbox read-only`, resolved workspace/schema containment, symlink rejection, parent-process-only formal publication; verified by `test_schema_and_workspace_symlink_escapes_are_rejected` and the hostile path cases in `test_security_boundaries.py` | closed |
| T-01-07 | Repudiation | Model identity and formal-run evidence | medium | mitigate | Only an operator-configured snapshot may be treated as immutable; alias runs retain raw JSONL, CLI/config metadata, and a non-empty drift limitation; verified by `test_untrusted_event_cannot_claim_an_immutable_model_snapshot`, `test_live_store_rejects_alias_without_drift_limitation`, and `test_successful_live_metadata_is_immutable_and_verifiable` | closed |

*Status: open · closed · open — below high threshold (non-blocking)*

---

## Accepted Risks Log

No accepted risks.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-30 | 4 | 4 | 0 | Codex inline security audit |

---

## Verification Evidence

- Full offline suite: 52 passed, 1 explicitly deselected live-model smoke.
- Security/Codex targeted suite: 33 passed, 1 explicitly deselected live-model smoke.
- Static quality gates: Ruff lint and formatting checks passed.
- Code review additionally closed untrusted snapshot promotion, undeclared
  bundle-file acceptance, and stale parent-lineage verification in `98372f8`.

## Sign-Off

- [x] All threats have a disposition.
- [x] No accepted risk requires logging.
- [x] `threats_open: 0` confirmed.
- [x] `status: verified` set in frontmatter.

**Approval:** verified 2026-07-30
