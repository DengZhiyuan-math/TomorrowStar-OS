# API Coverage — Codex CLI

> Full coverage by default. Opt-outs are explicit, reasoned decisions.

Phase 1 integrates only the non-interactive `codex exec` surface needed to
record and replay a formal validation model call. It does not expose Codex as a
general-purpose user-facing agent.

| capability | decision | reason |
|---|---|---|
| non-interactive `codex exec` | INTEGRATE | required live-model boundary |
| explicit `--model gpt-5.6-luna` | INTEGRATE | locked Phase 1 decision D-17 |
| `model_reasoning_effort="medium"` configuration | INTEGRATE | locked Phase 1 decision D-17 |
| JSONL event output via `--json` | INTEGRATE | raw-response preservation and exact replay |
| final-response validation via `--output-schema` | INTEGRATE | structured-output contract when a schema is supplied |
| explicit workspace via `--cd` | INTEGRATE | deterministic input boundary |
| read-only sandbox selection | INTEGRATE | live smoke must not mutate the project |
| CLI version capture | INTEGRATE | formal-run reproducibility |
| exit code, stdout, and stderr capture | INTEGRATE | failure diagnosis without hiding partial output |
| immutable model snapshot when available | INTEGRATE | preferred formal-run pin under D-18 |
| alias fallback with drift limitation | INTEGRATE | permits formal runs when no snapshot identifier is exposed |
| `--output-last-message` | OPT-OUT | JSONL is the canonical raw record; duplicating only the last message weakens lineage |
| session persistence and `exec resume` | OPT-OUT | exact replay uses recorded artifacts, not a resumed live session |
| interactive TUI | OPT-OUT | Phase 1 requires an automatable formal-run boundary |
| code review mode | OPT-OUT | unrelated to career-evidence validation |
| image input | OPT-OUT | Phase 1 fixtures are text/JSON only |
| live web search | OPT-OUT | default and formal tracer inputs must be closed and reproducible |
| MCP servers and plugins | OPT-OUT | additional external state would expand the reproducibility surface |
| Codex Cloud tasks | OPT-OUT | local-first validation is the approved architecture |
| open-source/local model provider mode | OPT-OUT | selected runtime is hosted GPT-5.6 Luna through Codex CLI |
| danger-full-access / sandbox bypass | OPT-OUT | unnecessary and incompatible with the live-smoke threat model |
