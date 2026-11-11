# Stack Research

**Domain:** v1.1 full-career evidence graph and real-JD validation
**Researched:** 2026-08-28
**Confidence:** HIGH for retaining the current stack; MEDIUM for deferred provider/parser choices

## Executive Recommendation

**Add no runtime or development dependency for v1.1.** Keep Python 3.13.14, Pydantic
2.13.4, schema-versioned JSON/JSONL, pytest 9.1.1, Ruff 0.16.0, and uv exactly as
currently pinned. The repository already contains the required primitives: frozen
strict models, canonical JSON and SHA-256 identity, create-only bundles, atomic
replacement, resumable audit state, provider-neutral decision ports, reviewed-user-truth
admission, raw-JD hash/span custody, and deterministic comparison.

Implement the milestone by adding project-owned contracts and adapters, not libraries:

1. A full-career inventory manifest and canonical graph snapshot composed from the
   existing Experience, Contribution, Evidence, Skill, audit, and assessment records.
2. A small source-adapter protocol for heterogeneous evidence, with native adapters only
   for formats actually present in the user-confirmed corpus.
3. A JD extraction port following the existing recorded/fake/opt-in-live audit pattern.
   Pydantic supplies the output schema; a human review remains the sole acceptance step.
4. A reusable private-workspace store hardened to directories mode 0700 and files mode
   0600, while preserving symlink/hardlink checks, fsync, hashes, and create-only history.
5. A stdlib-plus-pytest evaluation runner that materializes the frozen charter, case
   assignments, repetitions, judgments, and final decision as immutable JSON artifacts.

This is a codebase-derived recommendation: no inspected v1.1 requirement needs
concurrency, graph queries beyond bounded in-memory indexes, general document conversion,
provider switching at runtime, or statistical tooling.

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose in v1.1 | Why Recommended | Confidence |
|------------|---------|-----------------|-----------------|------------|
| CPython | Keep 3.13.14 and `>=3.13,<3.14` | Inventory composition, source adapters, private stores, graph projection, JD/evaluation runners | `pathlib`, `json`, `hashlib`, `os`, `stat`, `tempfile`, `subprocess`, `statistics`, and `typing.Protocol` cover every new infrastructure need. | HIGH |
| Pydantic | Keep 2.13.4 | Strict status records, inventory/graph manifests, extraction proposals, review decisions, evaluation outputs, JSON Schema | The installed dependency already provides strict validation, frozen models, validators, serialization, and JSON Schema. Do not introduce a second contract system. | HIGH |
| Canonical JSON + JSONL | Existing schema-versioned format | Authoritative snapshots, append-only events, source manifests, review history, accepted JD packets, evaluation evidence | Existing hashing and storage code makes these artifacts inspectable, replayable, diffable, and local. The v1.1 corpus is bounded and single-user. | HIGH |
| In-memory indexes over canonical records | Project code; no package | Traverse Experience → Contribution → Skill and compute coverage/status projections | Dictionaries and tuples are sufficient for the real corpus and exactly three JDs; persist records, not a second graph engine. | HIGH |

### New Project-Owned Seams

| Seam | Implementation | Integration point | Authority rule |
|------|----------------|-------------------|----------------|
| `CareerSourceAdapter` protocol | Return raw-source identity plus non-authoritative candidate records from one declared source type | New v1.1 ingestion module; reuse hash/store helpers | An adapter can propose inventory items and evidence links, never mastery or confirmation. |
| `RecordedCareerSourceAdapter` | Load checked, local JSON/text proposals for deterministic replay | Mirror `RecordedDecisionPort` in `audit/decision.py` | Default implementation for tests and reproducible runs. |
| `JDExtractionPort` protocol | Convert exact raw JD bytes plus a Pydantic schema into a recorded proposal | Insert before `prepare_jd_intake` in `jd.py` | Extraction cannot correct, accept, compare, or mutate the user graph. |
| `RecordedJDExtractionPort` | Reopen an exact input-hash/prompt-hash/schema-hash/model-config-hash response | Reuse formal-run and canonical-bundle patterns | Default offline implementation and replay authority. |
| Optional live JD adapter | One adapter for the provider selected during implementation | Follow the fake/recorded/opt-in-live pattern in `audit/decision.py` | Pin one SDK or CLI version only after selection; retain raw response and model/config identity. |
| `PrivateEvidenceStore` | Shared stdlib create-only/atomic store with 0700 directories and 0600 files | Extract from `validation/store.py`, `audit/store.py`, and `JDIntakeStore` without duplicating engines | Public status APIs expose identifiers/counts/hashes only; source text stays below `.career-evidence/`. |

### Domain Contract Additions

Use new schema-versioned Pydantic records that reference existing entity IDs and hashes;
do not rewrite sealed v1 records.

| Contract | Required role | Implementation note |
|----------|---------------|---------------------|
| Full-career inventory manifest | Records cutoff time, declared source set, every known item, and coverage status | Use explicit status enums/literals; absence is not confirmation. |
| Source envelope | Binds raw bytes/hash, origin, capture time, adapter/version, and derived-text hash | Derived text remains a proposal; retain the raw source identity. |
| Canonical graph snapshot | References exact Experience, Contribution, Evidence, Skill, audit, and admitted-assessment versions | Compute one content hash over canonical ordering; never copy JD-derived fields into it. |
| Inventory/graph review | Stores item-level confirm/edit/reject/insufficient/unresolved decisions | Create a new immutable review version; do not overwrite prior user truth. |
| JD extraction proposal and review | Binds each requirement and byte span to one raw JD and item-level correction history | Only explicit user acceptance can create an `AcceptedJDPacket`. |
| Evaluation run bundle | Binds charter, three accepted JDs, graph hash, baseline, blind assignment, repetitions, judgments, and decision | Separate deterministic metrics from human judgments and model outputs. |

Keep the milestone statuses semantically separate:

- inventory coverage: known, pending, reviewed, excluded-with-reason;
- responsibility/evidence resolution: resolved, insufficient-evidence,
  unresolved-responsibility;
- graph authority: candidate versus confirmed;
- assessment admission: existing admitted/pending/unverified states.

Do not compress these into one generic `status` whose meaning changes by context.

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | Keep 9.1.1 | Deterministic, adversarial, stability, holdout, replication, and store-safety cases | Use built-in parametrization, fixtures, markers, and `tmp_path`; no plugin is required. |
| Ruff | Keep 0.16.0 | Lint/format new modules | Keep the current `py313` target and rule set. |
| Provider SDK | **Do not add yet** | Optional live structured extraction | Add exactly one pinned SDK only after a phase selects a provider and proves that the existing CLI/recorded seam is insufficient. |
| PDF/DOCX parser | **Do not add yet** | Optional text derivation from a concrete source format | Add one format-specific parser only if the confirmed source inventory contains that format and human-supplied UTF-8 extraction would invalidate the evaluation. |

### Development and Evaluation Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| Existing uv lockfile | Reproducible environment | No dependency update is part of v1.1 stack work. |
| Existing pytest suite | Offline contract and workflow evidence | Keep live/provider tests opt-in under the existing markers. |
| Python `statistics`, `csv`, and deterministic ordering | Small empirical result summaries | Three JDs and a frozen case matrix do not justify pandas, NumPy, scikit-learn, or an experiment platform. |
| Content-addressed JSON bundles | Blind assignment, repetitions, reviewer results, final decision | Freeze before execution and verify hashes on reopen. |

## Integration With the Current Codebase

| Current component | v1.1 action |
|-------------------|-------------|
| `validation/models.py::StrictModel` | Reuse unchanged. It already sets `extra="forbid"` and `frozen=True`; continue using tuples/frozen children because Pydantic freezing is shallow. |
| `validation/hashing.py` | Reuse canonical JSON and SHA-256 for inventory, graph, source, proposal, review, and evaluation identities. |
| `validation/store.py` | Extract one reusable private-bundle primitive; add explicit permission verification without changing old sealed artifacts. |
| `audit/store.py` | Reuse its 0700-root, regular-file, single-link, fsync, and atomic-replace checks. |
| `audit/decision.py` | Reuse the provider-neutral Protocol plus fake/recorded/opt-in-live adapter pattern for source/JD extraction. |
| `domain/models.py` | Add v1.1 manifest/status/review contracts that reference existing v1 entities; avoid widening old literals in ways that reinterpret sealed evidence. |
| `domain/fixtures.py` | Leave the fixed STOA fixture boundary intact. Build a separate full-career registry/composer rather than generalizing STOA constants into a second authority. |
| `assessment.py` | Preserve the existing rule that only admitted, reviewed-user-truth assessments contribute mastery. Inventory completeness cannot bypass admission. |
| `jd.py` | Keep raw source, size/Unicode checks, proposal custody, immutable acceptance, and read-only comparison. Add extraction and item-review before the current prepare/accept boundary. |
| `.gitignore` | Keep `/.career-evidence/` excluded. Tests must prove public CLI output and error messages never echo private source text. |

## Installation

```bash
# No pyproject.toml or uv.lock change is recommended.
uv sync --locked

# Existing verification tools are sufficient.
uv run --locked pytest
uv run --locked ruff check .
```

## Alternatives Considered

| Recommended | Alternative | Use the alternative only when |
|-------------|-------------|-------------------------------|
| Canonical JSON/JSONL bundles | stdlib SQLite | Concurrent writers, transactional updates spanning several authoritative records, or measured indexed-query pressure become real requirements. |
| In-memory graph indexes | Neo4j, RDF store, NetworkX | A measured query cannot be expressed or performed acceptably over the bounded canonical records. No such query exists in v1.1. |
| Project-owned extraction Protocol | LangChain, LangGraph, LlamaIndex, PydanticAI | Orchestration complexity is demonstrated beyond the current explicit state machines and custody boundaries. |
| One selected adapter | LiteLLM or multi-provider router | Runtime provider switching becomes a tested product requirement, not an experiment convenience. |
| Exact aliases plus human review | Embeddings/vector search | Deterministic normalization recall is empirically insufficient and a reviewable embedding candidate process is specified. |
| Format-specific adapter after inventory | Universal document-conversion stack | The accepted corpus contains several unavoidable formats and conversion fidelity is itself validated. |
| pytest plus stdlib metrics | evaluation SaaS/framework | The frozen protocol requires scale, collaboration, or metrics not representable in small checked-in fixtures and immutable local bundles. |

## What NOT to Use

| Avoid in v1.1 | Why | Use Instead |
|---------------|-----|-------------|
| Any new dependency by default | No inspected requirement has a capability gap in the current stack. | Extend current Pydantic models, stdlib stores, Protocols, and pytest fixtures. |
| Neo4j, RDFLib, NetworkX, or another graph authority | Creates a second representation and migration/synchronization problem while semantics are still being validated. | One canonical JSON graph snapshot plus in-memory indexes. |
| SQLite, PostgreSQL, MongoDB, SQLAlchemy, or an ORM | The milestone is single-user, bounded, and create-mostly; database migrations add no hypothesis evidence. | Content-addressed JSON/JSONL. |
| Vector database, embeddings-first matching, or RAG pipeline | Obscures exact Skill normalization and can convert semantic similarity into false capability evidence. | Deterministic aliases, explicit candidates, and human review. |
| LangChain, LangGraph, LlamaIndex, PydanticAI, or a generic agent framework | Hides transitions and provenance that must remain independently testable. | Explicit workflow functions and narrow Protocol ports. |
| Provider SDK or multi-provider abstraction before provider selection | Prematurely freezes a vendor and expands the lockfile without validating a need. | Recorded adapter first; add one pinned live adapter after selection. |
| MarkItDown, unstructured, OCR, PDF, or DOCX packages preemptively | Source heterogeneity does not prove format-parsing necessity; parsers add supply-chain and fidelity risks. | Hash raw bytes, accept UTF-8/JSON now, and add one adapter only for an observed format. |
| pandas, NumPy, scikit-learn, notebooks as authority, or an experiment platform | The three-JD evaluation is small; these add serialization and reproducibility surfaces. | pytest, `statistics`, canonical JSON, and frozen manifests. |
| FastAPI, React, desktop GUI, authentication stack, or cloud service | Multi-user delivery is outside the milestone and increases privacy exposure. | Local CLI and inspectable private artifacts. |
| Cloud object storage, external telemetry, or automatic source upload | Full-career records and raw JDs are private; remote transfer is not required for the hypothesis. | Local gitignored storage and redacted/count-only public status. |
| Application-level cryptography added casually | File encryption needs key lifecycle, recovery, and platform threat-model decisions; a package alone does not solve them. | Enforce local permissions now; if encryption-at-rest becomes explicit, research OS-backed encrypted storage/key management as a separate security requirement. |
| Automatic acceptance of extractor/model output | Structured output proves shape, not truth or user authority. | Immutable proposal → item-level correction → explicit acceptance. |

## Stack Patterns by Variant

**If the source is UTF-8 text, Markdown, JSON, or a pinned Git object:**

- Use a stdlib adapter and retain exact bytes/hash plus a safe locator.
- Produce candidates only; require item review before confirmation or mastery admission.

**If a confirmed source is PDF, DOCX, image, or another binary format:**

- Retain and hash the raw file locally first.
- Record the converter and version and hash derived text.
- Add one parser only after a corpus-specific fidelity fixture demonstrates necessity.

**If live JD extraction is selected:**

- Implement exactly one adapter behind `JDExtractionPort`.
- Pin its executable/SDK and record provider, model/snapshot or drift limitation, prompt,
  schema, settings, raw response, and hashes.
- Never let the adapter accept requirements or write to the user graph.

**If concurrent authoritative writes or multi-record transactions appear:**

- Re-evaluate stdlib SQLite with explicit transaction policy and JSON export.
- Until then, retain create-only bundles and atomic current pointers.

**If privacy requirements expand to encryption at rest or synchronization:**

- Stop and perform a separate threat-model and platform-key-management decision.
- Do not infer permission to upload or encrypt/migrate existing evidence.

## Version Compatibility

| Component | Compatible With | v1.1 rule |
|-----------|-----------------|-----------|
| Python 3.13.14 | Current Pydantic, pytest, Ruff, uv lock | Keep the current interpreter and project range; no upgrade is required. |
| Pydantic 2.13.4 | Existing `StrictModel` contracts | Use v2 `model_validate*`, `model_dump`, validators, and `model_json_schema`; avoid a parallel schema library. |
| pytest 9.1.1 | Existing Python 3.13 dev group | Built-in parametrization, markers, fixtures, and `tmp_path` cover v1.1 evaluation. |
| Optional future provider adapter | Python 3.13 plus generated Pydantic schema | Pin and contract-test only after provider selection; successful shape validation does not grant acceptance authority. |
| Optional future parser | One observed source format | Pin only after raw/derived hash custody and fidelity tests are defined. |

## Evidence and Confidence

| Finding | Basis | Confidence |
|---------|-------|------------|
| No new dependency is required | Direct inspection of `pyproject.toml`, `uv.lock`, required domain/JD files, stores, audit ports, and tests | HIGH |
| Pydantic covers strict/frozen contracts and JSON Schema | Current official Pydantic documentation, cross-checked against `StrictModel` and current models | MEDIUM external / HIGH codebase fit |
| Python stdlib covers hashing and atomic/create-only local custody | Python 3.13 official `hashlib` and `os` documentation, cross-checked against existing stores | MEDIUM external / HIGH codebase fit |
| pytest needs no plugin for the frozen evaluation matrix | Official pytest parametrization, fixture, marker, and temporary-directory documentation | MEDIUM |
| SQLite should remain deferred | Official sqlite3 transaction/locking capabilities compared with the bounded single-user requirements | HIGH recommendation |
| Local, limited, human-reviewed handling is appropriate | OWASP untrusted-content/file guidance and NIST AI RMF privacy, provenance, oversight, and TEVV guidance | MEDIUM |

## Sources

### Current codebase evidence

- `pyproject.toml`, `.python-version`, and `uv.lock` — installed versions and complete dependency surface.
- `src/career_evidence_graph/validation/models.py` — frozen, extra-forbid strict contracts.
- `src/career_evidence_graph/validation/hashing.py` and `validation/store.py` — canonical bytes, SHA-256, atomic/create-only bundles.
- `src/career_evidence_graph/audit/decision.py` and `audit/store.py` — provider-neutral ports and private resumable storage.
- `src/career_evidence_graph/domain/models.py`, `domain/fixtures.py`, and `jd.py` — authority, provenance, JD custody, immutable acceptance, and read-only graph comparison.

### Current official/primary sources

- [Pydantic models](https://pydantic.dev/docs/validation/latest/concepts/models/) — validation, extra-field policy, serialization, frozen-model caveat.
- [Pydantic strict mode](https://pydantic.dev/docs/validation/latest/concepts/strict_mode/) — per-call, field, and model strictness.
- [Pydantic JSON Schema](https://pydantic.dev/docs/validation/latest/concepts/json_schema/) — `model_json_schema` and standards-compatible schemas.
- [Python 3.13 hashlib](https://docs.python.org/3.13/library/hashlib.html) — SHA-256 content identity.
- [Python 3.13 os](https://docs.python.org/3.13/library/os.html) — create/exclusive flags, permissions, symlink controls, fsync, and atomic POSIX replacement.
- [Python 3.13 sqlite3](https://docs.python.org/3.13/library/sqlite3.html) — transactions, locks, and concurrency considerations used for the deferral gate.
- [pytest parametrization](https://docs.pytest.org/en/stable/example/parametrize.html) and [pytest temporary directories](https://docs.pytest.org/en/stable/getting-started.html#request-a-unique-temporary-directory-for-functional-tests) — built-in evaluation support.
- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) — allowlists, size limits, restricted storage, and file-processing cautions.
- [OWASP LLM Prompt Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html) — untrusted external content, structured separation, least privilege, and human review.
- [NIST AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/) — privacy requirements, provenance/TEVV, documented limitations, and human oversight.

---
*Stack research for: Career Evidence Graph v1.1*
*Researched: 2026-08-28*
