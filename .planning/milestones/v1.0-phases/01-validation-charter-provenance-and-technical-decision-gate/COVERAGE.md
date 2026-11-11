# API Coverage — Codex CLI

> Full coverage by default. Opt-outs are explicit, reasoned decisions.

Phase 1 integrates only the non-interactive `codex exec` surface needed to
record and replay a formal validation model call. It does not expose Codex as a
general-purpose user-facing agent.

| capability | decision | reason | implementation / exclusion proof |
|---|---|---|---|
| non-interactive `codex exec` | INTEGRATE | required live-model boundary | `tests/test_codex_cli.py#test_argv_locks_luna_medium_json_schema_workspace_and_read_only` |
| explicit `--model gpt-5.6-luna` | INTEGRATE | locked Phase 1 decision D-17 | same argv contract test |
| `model_reasoning_effort="medium"` configuration | INTEGRATE | locked Phase 1 decision D-17 | argv contract plus installed-CLI syntax test |
| JSONL event output via `--json` | INTEGRATE | raw-response preservation and exact replay | raw-retention and malformed-stream tests |
| final-response validation via `--output-schema` | INTEGRATE | structured-output contract when a schema is supplied | schema-boundary and missing-result tests |
| explicit workspace via `--cd` | INTEGRATE | deterministic input boundary | argv and symlink-escape tests |
| read-only sandbox selection | INTEGRATE | live smoke must not mutate the project | argv contract test |
| CLI version capture | INTEGRATE | formal-run reproducibility | fake-runner metadata test |
| exit code, stdout, and stderr capture | INTEGRATE | failure diagnosis without hiding partial output | failure, retention, and redaction tests |
| immutable model snapshot when available | INTEGRATE | preferred formal-run pin under D-18 | model-identity contract and formal-store validation |
| alias fallback with drift limitation | INTEGRATE | permits formal runs when no snapshot identifier is exposed | alias-without-drift rejection test |
| `--output-last-message` | OPT-OUT | JSONL is the canonical raw record; duplicating only the last message weakens lineage | forbidden-capability argv test |
| session persistence and `exec resume` | OPT-OUT | exact replay uses recorded artifacts, not a resumed live session | forbidden-capability argv test and replay subprocess guard |
| interactive TUI | OPT-OUT | Phase 1 requires an automatable formal-run boundary | adapter exposes only `exec` |
| code review mode | OPT-OUT | unrelated to career-evidence validation | forbidden-capability argv test |
| image input | OPT-OUT | Phase 1 fixtures are text/JSON only | forbidden-capability argv test |
| live web search | OPT-OUT | default and formal tracer inputs must be closed and reproducible | no enable/search flag in fixed argv |
| MCP servers and plugins | OPT-OUT | additional external state would expand the reproducibility surface | allowlisted fixed argv and environment tests |
| Codex Cloud tasks | OPT-OUT | local-first validation is the approved architecture | local subprocess and workspace contract |
| open-source/local model provider mode | OPT-OUT | selected runtime is hosted GPT-5.6 Luna through Codex CLI | forbidden-capability argv test |
| danger-full-access / sandbox bypass | OPT-OUT | unnecessary and incompatible with the live-smoke threat model | forbidden-capability argv test |
