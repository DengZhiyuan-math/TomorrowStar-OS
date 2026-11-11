# Repository guide

Start at [README.md](README.md) for the harness, workflow and personal-data map.
Current product behavior is defined by [APP-01–18](docs/single-job-flow.md), with
work ordered by [the development plan](docs/development-plan.md). Research scope
is defined by `.planning/PROJECT.md`; research gates do not block ordinary applications.
Active workflow navigation is in [docs/workflows.md](docs/workflows.md).
Keep personal records in the explicit separate private workspace described by
[docs/data-boundaries.md](docs/data-boundaries.md). Use checkout launchers for tests
and CLI operations. Preserve uncommitted work and historical fixture paths.

Choose the smallest mature solution in this order: skip unnecessary work;
reuse repository code; use the standard library; use native platform/framework
capabilities; reuse installed dependencies; prefer one clear line; only then
write the minimum custom implementation. Avoid duplicate abstractions and
speculative dependencies.

## Native App identity and permissions

Keep one installed App: `~/Applications/TomorrowStar.app`, with bundle ID
`dev.tomorrowstar.desktop`. Reuse the pinned private signing identity; never create
another `.app`, rotate its certificate, fall back to ad-hoc signing, or reset TCC
as a routine development step. Use `macos/main_app.py` for checked maintenance
and `macos/check_main_permissions.py` for actual host permissions. Follow
[CONVENTIONS.md](CONVENTIONS.md) and [the App workflow](docs/macos-app.md).
Request user action only when actual missing host capabilities block the current operation.
Do not turn diagnostic checks, package/version proofs or repeated permission checks
into daily application approvals. Final Submit remains manual.

<!-- GSD:project-start source:.planning/PROJECT.md -->

## Project

**TomorrowStar OS — Local Automatic Applications and Career Evidence Research**

The current application product follows [APP-01–18](docs/single-job-flow.md).
Email recommendations enter a persistent sequential queue; no active job
concurrency is planned. Existing facts are reused from the two libraries.
Important missing facts, conflicts and unknown results stop the current job;
only mail ingestion continues while waiting. User edits are retained and one
Continue resumes remaining steps. Explicit career corrections are saved directly
with history. Ordinary materials, filling and upload require no repeated approval;
final Submit is manual. Use [the development plan](docs/development-plan.md).

**Independent research scope:**

The v1.0 foundation received a partial closeout; it did not empirically validate
the complete hypothesis. The active v1.1 milestone validates a user-confirmed
full-career graph against exactly three user-supplied real JDs. Grill-Me audits
what the user can explain, implement, reproduce, defend or operate within bounded
Contributions before reviewed Skill assessments can inform career decisions.

The broader product will use this reusable skill-oriented career graph to dynamically select and rewrite relevant experiences for tailored résumés and to propose evidence-producing gap-closing work. Those downstream product loops remain central to the product vision, but the research milestone stops at validating the Grill-Me → skill graph → JD usefulness hypothesis. This does not postpone the separately authorized application product.

**Core Value:** Accurately determine what the user can genuinely do within specific contributions and convert that understanding into skill scores and graph relationships that are useful for JD-relevant career decisions.

### Constraints

- **Validation scope**: Prove the Grill-Me → Contribution–Skill assessment → user Skill graph → JD usefulness hypothesis with a user-confirmed full-career inventory and exactly three user-supplied real JDs for research claims. Application product work proceeds independently. STOA remains the foundation fixture.
- **Assessment semantics**: Every user-level score evaluates one specific Skill; unrelated capabilities must not be hidden as generic subdimensions of that score.
- **Audit granularity**: Contribution is the minimum auditable fact unit; Experience alone cannot produce a Skill score.
- **Score separation**: Mastery, evidence confidence, verified duration, context, and JD match must retain different meanings.
- **Anchor integrity**: Higher mastery bands require observable higher-order capability; they cannot be reached through mechanical accumulation of weaker evidence.
- **Truthfulness**: User, team, other-person, Codex-assisted, and third-party work must remain distinguishable wherever responsibility affects assessment.
- **Decision timing**: Formula details, confidence gates, calibration rules, and implementation boundaries are phase-level decisions to validate with fixtures rather than assumptions to freeze during initialization.
- **Open-source provenance**: Reused or adapted code and patterns must identify their upstream repository, pinned revision, license, and local divergence.

### Interview and Assessment Protocol

Follow the [project protocol](.planning/PROJECT.md#interview-and-assessment-protocol)
and [question-generation and scoring pipeline](docs/question-scoring-pipeline.md).
Use three ordered layers: project overview, project depth, then transfer to a
related problem with an explicit changed condition. Layer and difficulty are
different concepts; depth and transfer each have their own difficulty ladder.
Declare evaluation criteria before the answer and ask one focused question at a time.
Preserve each layer's conclusions separately. Score only reviewed Contribution–Skill
relationships. Do not average layers or treat transfer reasoning as completed work
or repeated responsibility in real contexts. Reuse prior answers and preserve
user, team, other-person, coding-agent and third-party attribution.

### Grill-Me Recall Policy

Grill-Me assesses the user's capability and reviews their real work; it is not a memory test.
Before asking, retrieve and preserve relevant document labels, source locators, prior answers, and
artifact context. Explain unfamiliar labels in the question and use them to ground a concrete,
one-at-a-time capability prompt. A user not recalling a label, exact wording, or a project detail
is not negative capability evidence and must not cause an otherwise relevant Contribution to be
excluded. Record the resulting uncertainty explicitly, then assess only what the user can
actually explain, implement, reproduce, defend, or operate.

### Resume Content Policy

Education is fixed documentary information. Reuse applicable confirmed institutions,
degrees, dates, status and details. Do not rewrite or omit it for JD relevance, or
ask the user to confirm unchanged recorded facts again. Resolve actual source
conflicts separately; do not infer an awarded degree from an in-progress record.

Select and order evidenced skills and work experience for the current JD. Adapt
their wording and emphasis without inventing skills, proficiency, results or
responsibility, or turning planned work into completed work.

Keep AI assistance, coding-agent attribution and editor/tool-use provenance in
internal evidence records. Do not put these disclosures in the employer-facing
resume. Preserve actual team and collaborator responsibility in the wording.
Relevant technical skills and project technologies remain valid resume content.
Reuse recorded facts without repeated interviews. Ask only about important unresolved
conflicts or substantive choices. Automatic materials use APP-07, including checks
and preservation of user edits; no routine draft/PDF acceptance is required.
Research or optional artifact acceptance binds its own source/PDF and does not
perform final Submit.

<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

The tables below retain the original stack research. Installed dependency pins
are defined by `pyproject.toml` and `uv.lock`; current implementation boundaries
are in `ARCHITECTURE.md`. Historical recommendations do not require adding an
unused provider protocol, event log or framework.

## Executive Recommendation

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| CPython | `3.13.14` via `.python-version`; project range `>=3.13,<3.14` | Runtime for domain models, CLI workflow, adapters, and evaluation harness | It is a current bugfix-supported line and is the strongest common baseline in the pinned code: CV Market Learning Planner targets 3.13 and Resume Matcher requires 3.13+. Python 3.14.6 is newer, but Hiring Agent contains a Python 3.14 protobuf workaround; adopting 3.14 adds compatibility risk with no validation benefit. | MEDIUM |
| Pydantic | `2.13.4` | Strict domain contracts, JSON serialization, validation, JSON Schema for model output | Tabiya Compass, Hiring Agent, and Resume Matcher independently use Pydantic v2 at extraction/evaluation boundaries. The project needs explicit `Experience`, `Contribution`, `Evidence`, `Skill`, `ContributionSkillAssessment`, `UserSkillAssessment`, and `JDRequirement` contracts more than it needs an application framework. | MEDIUM |
| Python standard library | Python 3.13 | `pathlib`, `json`, `datetime`, `uuid`, `hashlib`, `argparse`, `typing.Protocol` | Covers the validation project's persistence, IDs, CLI, input hashing, and provider abstraction without dependencies. Plain files are inspectable and versionable, which is essential for calibration work. | HIGH |
| JSON + JSONL workspace | Schema-versioned; no external package | Current snapshots, append-only audit events, golden fixtures, model-call records, and JD cases | Directly supports reproducibility and provenance. It adapts CV Market Learning Planner's current/history separation without inheriting its learning-plan domain or requiring a database. | HIGH |
| Project-owned `LLMClient` protocol | Local interface; provider SDK selected per phase | Structured completion request/response boundary | Hiring Agent's `LLMProvider` protocol demonstrates the useful seam. Keep the provider/model choice unfrozen; tests use a fake/recorded implementation. Do not make LiteLLM, Gemini, OpenAI, or an agent framework part of the domain. | HIGH |

### Supporting Libraries

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| pytest | `9.1.1` | Unit, fixture, golden-case, invariant, replay, and opt-in live-model tests | Use from the first phase. Default suite must be deterministic and offline; mark real model calls separately and require explicit credentials/opt-in. | MEDIUM |
| Ruff | `0.16.0` | Linting and formatting | Pin and configure an explicit rule set because 0.16.0 substantially expanded default rules. Use `target-version = "py313"`. | MEDIUM |
| Provider SDK | **Unfrozen** | Execute the selected model's structured-output call | Add only after the provider/model experiment is chosen. Implement one adapter plus a fake; do not install a multi-provider abstraction speculatively. | HIGH |
| `markitdown`, PDF, or DOCX parser | **Deferred** | Convert résumé/evidence documents to text | Add only if the concrete STOA/JD fixture set includes formats that cannot first be represented as UTF-8 Markdown/text/JSON. Document parsing is not part of the hypothesis. | HIGH |

### Development Tools

| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| uv | `0.12.0` | Python installation, environment, dependency groups, lockfile, commands | Commit `pyproject.toml`, `.python-version`, and `uv.lock`. Use `uv run --locked` in verification. uv 0.12 creates a packaged `src/` layout by default, which is appropriate because tests must import the core. |
| Git submodules | Pinned commits listed below | Exact upstream source and license baseline | Keep upstreams unchanged under `references/upstream/`; record local adaptations separately. |
| pyproject.toml dependency groups | PEP 735 form | Keep runtime dependencies separate from test/lint tools | Put pytest and Ruff in `[dependency-groups].dev`; do not publish them as runtime dependencies. |

## Minimal Project Shape

## Installation

# Toolchain and packaged project

# Runtime

# Development

# Reproducibility and verification

## Exact Upstream Reuse Decisions

### Tabiya Compass — pinned `8470bea7f68d0990898f441a12bbb6a261a0ef34` (MIT)

| Classification | Exact upstream file or component | Decision and local use |
|----------------|----------------------------------|------------------------|
| **Adapt** | `backend/app/agent/skill_explorer_agent/_responsibilities_extraction_tool.py` | Preserve the separation between sentence decomposition and responsibility classification, especially `responsibilities`, `non_responsibilities`, and `other_peoples_responsibilities`. Extend locally to explicit user/team/other-person/Codex-assisted/third-party attribution and attach results to Contributions. |
| **Adapt** | `backend/app/agent/collect_experiences_agent/collect_experiences_agent.py` | Preserve separate conversation, structured extraction, and transition-decision passes. Replace its work-type loop with Contribution coverage and evidence/mastery coverage. |
| **Adapt** | `backend/app/agent/collect_experiences_agent/_transition_decision_tool.py` | Copy the pattern of deterministic guards overriding invalid LLM transition decisions. Local guards must prevent completion while required Contribution–Skill assessment fields, responsibility attribution, or assessment basis are missing. |
| **Adapt** | `backend/app/agent/collect_experiences_agent/_types.py` | Preserve strict validated state and the semantic distinction between “not asked” and “asked but declined.” Do not reuse the employment-specific fields as the local Experience model. |
| **Inspired-by** | `backend/app/application_state.py`; `backend/app/store/json_application_state_store.py` | Use explicit state/store interfaces and resumability, but implement a much smaller file workspace rather than Tabiya's aggregated multi-agent application state. |
| **Adapt** | `backend/evaluation_tests/collect_experiences_agent/`; `backend/evaluation_tests/skill_explorer_agent/` | Use scripted-user cases, simulated-user cases only as optional evals, loop detection, and extraction tests. Local goldens must target Contribution grounding and score-anchor evidence. |
| **Reject** | `frontend-new/`, Mongo/Motor stores, Firebase, Gemini-specific LLM infrastructure, `features/skills_ranking/`, fixed `WorkType` taxonomy | These are production/application or occupation-ranking concerns and would distort the validation model. |

### Matt Pocock Skills — pinned `2ab958093e83e0ec752e6c1c5932da465bf23e0c` (MIT)

| Classification | Exact upstream file or component | Decision and local use |
|----------------|----------------------------------|------------------------|
| **Adapt** | `skills/productivity/grilling/SKILL.md` | Preserve one question at a time and “inspect facts from available artifacts before asking.” Local question choice must be driven by unresolved Contribution evidence and capability anchors, not generic decision-tree completion. |
| **Adapt** | `skills/engineering/grill-with-docs/SKILL.md`; `skills/engineering/domain-modeling/` | Preserve a canonical vocabulary and explicit domain decisions as they stabilize. Store vocabulary changes as versioned artifacts rather than relying on transcript memory. |
| **Reject** | Literal “relentless” tone, mandatory recommended answer for every question, and “do not act until shared understanding” as a universal state rule | Career assessment needs psychologically safe questioning, neutral capability probes, skip/uncertainty handling, and resumability. The user is supplying evidence, not approving an engineering plan. |
| **Reject** | Plain chat transcript as the source of truth | The transcript is evidence/audit history. Validated Experience, Contribution, Evidence, Skill, and assessment records are canonical. |

### MIND Tech Ontology — pinned `2367527d1a2f5665f595d6e0518294cc69dfb0fe` (MIT)

| Classification | Exact upstream file or component | Decision and local use |
|----------------|----------------------------------|------------------------|
| **Reuse** | `__aggregated_skills.json`, `__aggregated_concepts.json`, and only the needed source slices under `skills/*.json` and `concepts/*.json` | Use as a version-pinned, read-only normalization snapshot behind an adapter. Preserve upstream IDs/names where available and record the pinned commit on normalized matches. Start with only skills observed in STOA and the JD fixtures. |
| **Adapt** | `skills/programming_languages.json` and analogous category files | Build a deterministic alias/case/misspelling index from `name` and `synonyms`; keep candidate matches reviewable. |
| **Inspired-by** | `technicalDomains`, `conceptualAspects`, tasks, and architectural relations | Retain as descriptive metadata or question-generation hints only. They must never establish user mastery. |
| **Reject** | `skills.py` class hierarchy as the internal model; `impliesKnowingSkills` and `impliesKnowingConcepts` as mastery propagation | The local Skill entity should remain small. Ontology implication is not evidence that this user can perform a skill and cannot alter mastery. |

### CV Market Learning Planner — pinned `ea507847c7a42a1a54becc853fadd15506479b38` (MIT)

| Classification | Exact upstream file or component | Decision and local use |
|----------------|----------------------------------|------------------------|
| **Reuse or adapt narrowly** | `scripts/workspace_model.py`: `ensure_dir`, JSON read/write helpers, UTC timestamps | These small deterministic helpers may be copied with attribution if doing so is cheaper than rewriting and local tests cover atomicity/encoding. Add atomic replacement and schema validation before writes. |
| **Adapt** | `scripts/run_cycle.py`: `snapshot_current_analysis`; `references/schemas.md`: `analysis/current` versus `analysis/history` | Snapshot current validated artifacts before a new calibration run; keep history immutable and append audit events in JSONL. |
| **Adapt** | `tests/test_skill_refactor.py` | Reuse the pattern of building complete deterministic fixtures and running helpers as subprocesses. Replace learning-level cases with mastery-anchor, no-inflation, attribution, and JD-usefulness cases. |
| **Reject** | `ABSTRACT_LEVELS`, learning-plan/exercise schemas, HTML plan rendering, daily tasks, and gap scoring | Gap planning is outside this validation project, and its fixed levels are not the accepted 0–100 mastery anchors. |

### Hiring Agent — pinned `70fd3ea9aa74d8f76519ec643a99f9871003e70d` (MIT)

| Classification | Exact upstream file or component | Decision and local use |
|----------------|----------------------------------|------------------------|
| **Adapt** | `models.py`: `LLMProvider` protocol, Pydantic contracts, `build_scores_model`, `build_evaluation_model` | Preserve provider isolation and schema-constrained structured output. Use explicit local models instead of dynamically creating the core mastery model; dynamic models are acceptable only for JD-specific evaluation rubrics. |
| **Adapt** | `score.py`: validated cache loading and stage-specific cache files | Cache by hash of input, prompt/schema version, provider, model, and settings. Never key only by filename. Invalid or stale cache entries must fail closed or be ignored with an audit record. |
| **Inspired-by** | `roles.py` and `roles/software_engineering_intern/role.json` | Represent each JD fixture as versioned structured expectations and evaluation criteria, but do not turn role weights into user mastery. |
| **Reject** | `evaluator.py` LLM-generated category scores as final truth; `github.py`; résumé/GitHub/blog concatenation in `score.py`; permissive transform fallbacks in `transform.py` | Capability must be grounded in audited Contributions. GitHub activity, résumé content, or a parser fallback cannot bypass Grill-Me, evidence confidence, calibration, or human review. |
| **Reject** | `google-generativeai==0.4.0` and the full `requirements.txt` as a dependency baseline | The Google package line is legacy relative to current provider SDKs, and the upstream dependency set includes PDF and formatting concerns outside this hypothesis. |

### Resume Matcher — pinned `ad7754c8b2c3ecee21314ee0b49b0e07d89e3e09` (Apache-2.0)

| Classification | Exact upstream file or component | Decision and local use |
|----------------|----------------------------------|------------------------|
| **Inspired-by now; adapt later** | `apps/backend/tests/evals/golden/cases.py`, `tests/evals/test_tailoring_eval.py` | Use paired good/bad golden cases, deterministic structural scorers, and separately marked opt-in model judges. Current cases should evaluate Skill normalization, Contribution selection, mismatch explanations, and truthfulness—not résumé prose. |
| **Adapt** | `apps/backend/tests/unit/test_prompt_guardrails.py` | Lock critical prompt invariants in tests: no fabrication, no inferred mastery from ontology/JD keywords, no hidden responsibility transfer, and gaps are not capabilities. |
| **Inspired-by** | `apps/backend/app/services/parser.py` | Its “LLM extraction followed by deterministic repair and Pydantic validation” pattern is useful if document parsing becomes necessary. Do not add MarkItDown during initial text/JSON fixture work. |
| **Reject for this project** | `apps/backend/app/database.py`, FastAPI backend, SQLAlchemy/SQLite persistence, frontend, tailoring/refinement services, Playwright/PDF pipeline | These solve multi-record application and résumé-output workflows that are explicitly deferred. |
| **Reject as source of truth** | `apps/backend/app/schemas/models.py` flat résumé-facing `Experience`/`Project`/skills schema | It lacks the required unified Experience → Contribution → Skill relationships and separate mastery, centrality, and confidence semantics. |

## Reuse Classification Summary

| Upstream | Reuse | Adapt | Inspired-by | Reject |
|----------|-------|-------|-------------|--------|
| Tabiya Compass | None wholesale | Interview/extraction/transition separation; responsibility classification; eval cases | Resumable store interfaces | UI, deployment, Gemini/Mongo/Firebase, work taxonomy, occupation ranking |
| Matt Pocock Skills | None verbatim by default | One-question flow, inspect-before-ask, vocabulary discipline | Domain-document workflow | Relentless tone, generic plan approval, transcript-only state |
| MIND Tech Ontology | Pinned JSON data slice | Alias index and reviewable normalization | Descriptive relations as question hints | Class hierarchy and implication-to-mastery |
| CV Market Learning Planner | Small deterministic helpers with attribution | Current/history workspace and fixture patterns | Append-only operational discipline | Learning/gap/exercise product |
| Hiring Agent | None wholesale | Pydantic/provider/caching/rubric boundaries | Role configurations | Résumé/GitHub-derived mastery and uncalibrated final scores |
| Resume Matcher | None in initial core | Prompt guard tests; later parsing/tailoring patterns | Golden eval split and later presentation/export | Full stack, flat source model, database/UI/export now |

## Integration and License Rules

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Python 3.13 packaged CLI/library | Python 3.14 | Move after the chosen provider SDK and all locked dependencies pass the full suite on 3.14; there is no hypothesis-level feature requiring it now. |
| Pydantic models | Dataclasses + hand-written validation | Only if Pydantic becomes a measured performance or packaging problem; that is unlikely at validation scale. |
| JSON/JSONL workspace | SQLite | Introduce SQLite when concurrent writes, transactional cross-record updates, or query volume become concrete requirements. Preserve exportable versioned JSON fixtures regardless. |
| Plain relationship records | Neo4j or another graph database | Introduce a graph store only after real query patterns exceed simple indexed in-memory traversal and the model has stabilized. |
| Project-owned provider protocol + one SDK | LiteLLM or an agent framework | Use a multi-provider layer only when a validated experiment requires switching several providers at runtime and the maintenance cost is justified. |
| Stdlib `argparse` CLI | Typer/Rich | Add only if interactive operator use becomes a material bottleneck; the first workflow can be driven by simple commands and files. |
| Text/Markdown/JSON fixtures | PDF/DOCX parsing | Add parsers only when fixture provenance requires original documents and manual text extraction would invalidate the experiment. |
| Explicit pure orchestration | LangGraph or workflow engine | Adopt only if resumable branching, concurrency, and checkpoint recovery become complex enough that the home-grown state machine is demonstrably failing. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| FastAPI, React/Next.js, or a multi-user web UI | Adds API/auth/UI state before the assessment model is validated | Importable Python core plus CLI and inspectable reports |
| Graph database | The graph is small and its semantics are still being calibrated | Pydantic relationship records and in-memory indexes |
| Vector database / embeddings-first skill matcher | Obscures normalization decisions and complicates reproducibility | Deterministic alias matching plus reviewable model-assisted candidates |
| MongoDB, PostgreSQL, SQLAlchemy, or TinyDB | No concurrency or scale requirement; migrations would distract from schema calibration | Schema-versioned JSON/JSONL workspace |
| Full agent framework | Hides transitions that must be audited and tested | Explicit state machine and narrow provider port |
| Generic LLM-generated final score | Violates anchor integrity and calibration requirements | Evidence-bearing Contribution–Skill assessments plus replaceable, tested aggregation |
| Ontology implication propagation | “X implies Y” is not evidence this user can do Y | Use relations only to suggest follow-up questions |
| GitHub/repository keywords as mastery | Confuses artifact presence with personal responsibility and capability | Attribute evidence to Contributions and verify through Grill-Me |
| Full résumé generator, tailoring UI, PDF export, gap sprint, learning planner | Explicitly outside the core-hypothesis validation | JD expectation fixtures and usefulness evaluation only |
| Wholesale copying of any upstream architecture | Upstreams solve different products and contain incompatible semantics | Provenance-tracked, test-backed local adaptations |

## Version Compatibility and Pinning

| Package or Tool | Compatible With | Notes |
|-----------------|-----------------|-------|
| Python `3.13.14` | Pydantic `2.13.4`, pytest `9.1.1`, Ruff `0.16.0` | Pydantic supports Python 3.9+; pinned upstreams demonstrate the ecosystem on Python 3.13. |
| Pydantic `2.13.4` | Python `>=3.9` officially | Use v2 APIs (`model_validate`, `model_dump`, `ConfigDict`); do not copy deprecated v1-style `class Config` patterns unchanged from older upstream files. |
| pytest `9.1.1` | Python 3.13 | Prefer native `[tool.pytest]` configuration. Keep live-model tests behind an explicit marker and key/provider gate. |
| Ruff `0.16.0` | `target-version = "py313"` | Configure selected rule groups explicitly because 0.16.0 changed the default rule set substantially. |
| uv `0.12.0` | Python 3.13 project and `uv.lock` | Commit the universal lockfile; run CI/verification with `--locked`. Pin uv in CI/tooling because lockfile schema compatibility can change across minor releases. |
| Provider SDK | Python 3.13 and Pydantic schema output | Select and pin only after a provider experiment. Verify actual structured-output behavior and retries with contract tests. |

## Decisions Intentionally Left Unfrozen

- LLM provider, model, SDK, temperature/reasoning settings, and structured-output transport.
- Exact aggregation formula, confidence gates, score thresholds, and calibration rules.
- Whether model-assisted normalization is needed beyond deterministic ontology aliases.
- Whether a live conversational interface is needed beyond the CLI/replay harness.
- Whether parsing PDF/DOCX source material is necessary for the STOA fixtures.
- Whether SQLite becomes useful after the validation data model stabilizes.

## Sources

### Official/current stack sources

- [Python downloads and active release status](https://www.python.org/downloads/) — Python 3.14.6 current; 3.13 remains in bugfix support. **Confidence: MEDIUM**
- [Pydantic current documentation](https://docs.pydantic.dev/latest/) — v2.13.4, Python 3.9+, JSON Schema capability. **Confidence: MEDIUM**
- [pytest changelog](https://docs.pytest.org/en/stable/changelog.html) — pytest 9.1.1 and pytest 9 native TOML configuration. **Confidence: MEDIUM**
- [uv 0.12.0 release](https://github.com/astral-sh/uv/releases/tag/0.12.0) — current release and packaged-project behavior. **Confidence: MEDIUM**
- [uv project locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/) and [project layout](https://docs.astral.sh/uv/concepts/projects/layout/) — committed `uv.lock`, automatic sync, and locked runs. **Confidence: MEDIUM**
- [Ruff 0.16.0 release](https://github.com/astral-sh/ruff/releases/tag/0.16.0) — current release and default-rule expansion. **Confidence: MEDIUM**
- [Python Packaging User Guide: dependency groups](https://packaging.python.org/en/latest/specifications/dependency-groups/) — standardized development dependency groups. **Confidence: MEDIUM**

### Pinned code sources

- `references/README.md` and `git submodule status` — commit and license baseline. **Confidence: HIGH**
- `references/upstream/tabiya-compass/backend/app/agent/` and `backend/evaluation_tests/` — interview, responsibility, state, transition, and eval patterns. **Confidence: HIGH**
- `references/upstream/mattpocock-skills/skills/productivity/grilling/SKILL.md` — one-question and inspect-before-ask pattern. **Confidence: HIGH**
- `references/upstream/mind-tech-ontology/skills.py`, `skills/*.json`, and `concepts/*.json` — ontology data model and implication fields. **Confidence: HIGH**
- `references/upstream/cv-market-learning-planner/scripts/`, `references/schemas.md`, and `tests/test_skill_refactor.py` — workspace and deterministic fixture patterns. **Confidence: HIGH**
- `references/upstream/hiring-agent/models.py`, `score.py`, `evaluator.py`, `roles/`, and `requirements.txt` — contracts, provider boundary, caching, role rubrics, and rejected scoring/dependency patterns. **Confidence: HIGH**
- `references/upstream/resume-matcher/apps/backend/app/` and `apps/backend/tests/` — parser repair, prompt guards, golden evals, persistence, and deferred presentation stack. **Confidence: HIGH**

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

See [CONVENTIONS.md](CONVENTIONS.md) for current checkout commands, synthetic
testing, privacy boundaries and minimal-change rules.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for module ownership, entrypoints, storage
and the separation between implemented harness contracts and milestone acceptance.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->
